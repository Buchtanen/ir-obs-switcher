# Commentary LLM — skeleton polish PoC

**Status:** historical PoC for `commentary-facts/1`; superseded by the grounded anchor + `commentary-facts/2` contract in [COMMENTARY_ENGINE.md](../COMMENTARY_ENGINE.md)
**Date:** 2026-09-01  
**Depends on:** [COMMENTARY_ENGINE.md](../COMMENTARY_ENGINE.md), sequence graph + director pipeline  
**Hardware under test:** Ubuntu NTB, NVIDIA RTX A1000 Laptop 4GB, Ollama `qwen2.5:3b` @ LAN  
**Historical decision:** this PoC tested `qwen2.5:3b`. Current default evaluation uses `qwen3:4b-instruct-2507-q4_K_M`; keep this document as the baseline that motivated the redesign.

## 1. Goal

Live **viewer-facing** TV-style commentary (ex-GT driver / race-engineer voice), driven by irswitch events — not pit radio to the driver.

The LLM must **not** invent telemetry. It only **polishes style** over facts the app already knows.

## 2. What the model does (and does not)

| Does | Does not |
|------|----------|
| Rewrite / expand tone from a factual **SKELETON** | Fill `{slots}` (that is `fill_slots` today) |
| Keep numbers, names, relation, streak counts | Compute gaps, positions, weather, SoF |
| Produce viewer third-person copy | Address the driver (“you / stay focused”) |

**Skeleton** = deterministic prose (or bullets) built from the same truth as emitters + `slot_bindings` + graph node.  
Authored `sequence_graph` variants remain the **fallback** (and today’s production path).

```text
emitters / briefs / RaceState / Bio
  → facts + relation + node
  → SKELETON (app)
  → optional LLM polish (style)
  → validate + fact guards
  → TTS  |  fail after retries → skip speak (no skeleton)
```

This is **not** “replace emitters with an LLM tree.” The tree still decides *when* and *what is true*; the model only changes *how it sounds*.

## 3. LAN serving (tested)

| Item | Value |
|------|--------|
| Host | Ubuntu NTB, same L2 as Win stream PC (`192.168.0.0/24`) |
| GPU | RTX A1000 4GB — OK for `qwen2.5:1.5b` / `3b` Q4 |
| Runtime | Ollama, OpenAI-compatible `POST /v1/chat/completions` |
| Bind | `OLLAMA_HOST=0.0.0.0:11434` (default was `127.0.0.1` only) |
| Firewall | allow `192.168.0.0/24` → TCP 11434 |
| Models tried | `qwen2.5:1.5b` (weak), `qwen2.5:3b` (usable with skeleton) |

**Note:** Win on `192.168.0.x` and Ubuntu mistakenly on `192.168.1.x` = no route. Same subnet required.

## 4. Prompt contract (tested)

### System (short beats — chase / PB)

```text
Polish a TV race call for stream viewers (not pit radio).
Keep EVERY fact from SKELETON. Do not add new numbers, names, or events.
Never invent yellows, overtakes, final lap, Stay tuned, or BPM.
Viewers only, third person. Same sentence count as the skeleton; do not add a sentence.
Hard cap {cap} characters for this skeleton (not the full node TTS ceiling).
Do not pad, welcome, or recap. Commentary only.
```

### System (session welcome)

Same fact-lock. Polish may restyle, not grow a second sentence. Authored graph lines may use the ~160 / 13 s node budget when they already carry two true facts.

### User

Not a free-form “call this JSON” dump. A **filled skeleton**, e.g.:

```text
SKELETON (timing beat — personal best streak):
1) …
2) This is the 3rd personal best in a row …
3) New best: 2:17.041; previous: 2:17.384; gain: 0.343 seconds.
…
```

### Compact JSON facts (implemented as `commentary-facts/1`)

Useful fields we can already track / compute (iRSDK + derived + graph):

- `beat`: `node`, `event`, `phase`, `family`, `relation` (`hero_closing_on_target` | …), `next_possible[]`, `emotion`
- `session`: `track`, `mode`, `lap`, `laps_remain`, `is_final_lap`
- `hero`: `class_position`, lap times, `incidents`
- `target`: `name`, `gap_s`, `closing`
- `bio`: `hr_band` (+ optional `bpm` — prefer band in spoken polish)
- `recent[]`: anti-repeat ban list
- Briefs: `field_size`, `sof`, weather (from existing session_briefs sources)

Do **not** send the full `sequence_graph`, author notes, or cooldown numbers into the model.

## 5. Test results (evidence)

Judge: same-size LLM-as-judge was **unreliable**. Scoring used a deterministic rubric (geometry, `0.42` present, anti-recent, no clinical HR, no forbidden phrases) + human review.

| Scenario | Approach | Latency (warm, LAN) | Result |
|----------|----------|---------------------|--------|
| HUNTING one-shot free JSON | base 3B | ~0.6–1.9 s | Unstable: reversed chase, copied `recent`, final-lap / Stay tuned |
| HUNTING bushy graph dump | base 3B | ~1.9 s | Longer but confused persona / geometry |
| HUNTING **skeleton polish** (I2 ×3) | base 3B | **~1.0 s** | **3/3 fact-safe** |
| Session welcome (track/class/SoF/weather/P11) | skeleton polish | **~5.1 s** | Usable intro; minor drift (e.g. dropped wind; “Welcome back”) |
| Personal best | skeleton polish | **~1.5 s** | PB time + delta + lap + P OK |
| 3rd PB in a row | skeleton polish | **~1.5 s** | Streak + times + P OK |

**PoC gate:** skeleton-in → polish-out is good enough to consider building; free-form one-shot is not.

## 6. Implementation brainstorm (architecture)

The integration branch composes synchronously from frozen facts, then performs optional polish inside the serial TTS worker — never on the producer/race tick.

```text
CommentaryDirector.observe (commentary consumer task)
  → graph path + RaceObserver recent beats
  → deterministic 2–4 fact composer + validate
  → sink.enqueue(utterance)        (non-blocking)
       worker: optional polish → re-validate → SAPI
```

### Options

| Option | Idea | Verdict |
|--------|------|---------|
| **A. PolishingTtsSink** | Wrap `ProcessTtsSink`; polish on serial worker; timeout/fact-fail → retry then skip TTS | **Shipped** |
| B. TextProvider in director | Deferred speak / async task ownership | More churn, easy to break fail-soft |
| C. Parallel dry-run only | Log polish, speak authored | Safe A/B tooling, not product voice |
| D. `tts_backend=ollama` | Confuses TTS with text rewrite | Reject as primary design |

### Implemented components

- `commentary/polish.py` — OpenAI-compatible client, timeout and fact locks
- `commentary/composer.py` — shipped graph-path walker, compact fact pack and EN/CS clause tree
- Config (default **off**): `llm_polish`, `llm_base_url`, `llm_model`, `llm_timeout_s`, `llm_max_attempts`  
- Re-validation, fact guards, DEBUG tape and final-spoken anti-repeat hook
- Timeout/retry, bad-polish rejection, graph compatibility and `llm_polish=false` parity tests
- `CONFIG.md`, `config.example.ini`, this doc and `COMMENTARY_ENGINE.md`

**No new pip dependency** if using existing `aiohttp`.

### Refactor boundaries

- `build_tts_sink` owns the polish-capable serial worker
- `anti_repeat.remember` stores both the queued skeleton and the final successful spoken text
- Busy remains conservative from the validated skeleton; the sink's observed busy state covers polish/audio overrun
- Leave alone: emitters, EventManager, graph topology, `slot_bindings`, offline `assignments.py`, scene `logic/`

### Risks

- Latency 1–5 s → retries inside `llm_timeout_s`; exhausted → skip TTS (no skeleton)  
- Graph node TTS ~160 / 13 s vs long welcome → polish is skeleton-relative; authored two-fact lines may use the node budget  
- Fact drift → reject polish  
- CS locale → dedicated system prompt + fixtures (**shipped**)
- Ollama down → never raise into race loop  

## 7. Explicit non-goals (now)

- Fine-tuning / LoRA on a 4090 (revisit after the A1000 3B contract is stable)  
- Replacing Event Engine or sequence graph topology with an LLM  
- On-box training on the A1000 (serve only; train elsewhere if ever)

## 8. Delivered order and remaining manual gate

1. Config flags + polish worker — shipped.
2. Frozen fact pack + graph-path composer — shipped.
3. EN/CS prompts, retries, fact locks and DEBUG tape — shipped.
4. Automated 53-node / 22-edge compatibility — passed.
5. Manual LAN listen (welcome / PB / hunting / two-front) against NTB Ollama — pending on the integration branch.

## 9. Example skeletons used in tests

**Welcome (abbrev.):** session RACE, Spa GP, GT3 sprint, field 28, SoF 2.4k, weather partly cloudy 18/24 °C, wind 12 km/h dry, hero P11, promise live battles + HR color.

**PB streak:** Spa GT3, 3rd consecutive PB, 2:17.041 (was 2:17.384, −0.343), lap 11, P7, emotion pushing, timing-only beat.

---

**Docs impact:** documentation-only; no runtime change until a follow-up issue/PR implements Option A.
