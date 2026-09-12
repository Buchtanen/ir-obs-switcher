# §24.9 stream-test checklist (Windows live smoke)

**Status:** composition-safety gate cleared — [#349](https://github.com/Buchtanen/ir-obs-switcher/issues/349) slices 1–5 on tip; **this is not a formal §24.9 GO**.

**Track:** [#278](https://github.com/Buchtanen/ir-obs-switcher/issues/278) live Windows gates  
**Tip baseline:** `codex/commentary-story-flow-spec` @ `a063143` (CI green)  
**Not on `master`.** Do not claim release GO from this smoke.

## Preconditions

- [ ] Checkout / build / restart from tip @ `a063143` (or newer tip with green CI)
- [ ] Windows box with iRacing (iRSDK), OBS, Ollama/Qwen (if testing realization), TTS backend reachable
- [ ] Operator config known: overlay `commentary.enabled`, v2 `commentary.tape.enabled`, Qwen/TTS endpoints (`CONFIG.md`)
- [ ] Logs + HTTP status endpoints reachable (`/health`, commentary/narrative status as documented in `API.md`)
- [ ] Know how to collect evidence: log excerpt, status JSON, optional tape dir when enabled

## Pass / fail rules

| Result | Meaning |
| --- | --- |
| **PASS (smoke)** | No composition bypass; kill-switch, mailbox, TTS, Qwen fail-closed, mediums behave as below |
| **FAIL** | Speech/planning/shadow while disabled; fabricated TTS callbacks; silent Qwen template live fallback; tape/journal contradict config |
| **§24.9 GO** | **Not** decided here — needs full live gate write-up under #278 after measured latency + fail-soft evidence |

Deferred (non-blocking for this smoke): shutdown wait for TTS idle; wire `commentary.tape.output_dir` / flush timeout from v2 config.

---

## 1) Kill-switch (#349 slice 1)

- [ ] Start with `commentary.enabled=false`
- [ ] No automatic speech
- [ ] No shadow hard-enable / narrative run active while disabled (`narrativeRunActive` stays false)
- [ ] No live Qwen generation while disabled
- [ ] Enable → speech/planning only after enable
- [ ] Disable mid-session → speech stops; no stranded “still speaking” live path

**Evidence:** status snapshot before/after toggle + log lines around enable/disable.

## 2) Mailbox cutover (#349 slice 2)

- [ ] With commentary enabled, session/context updates still admit (`SessionReset` / `ConfigUpdate` path alive)
- [ ] Mid-broadcast disable → re-enable allocates a **new** coherent run identity (no permanent stale context)
- [ ] After re-enable, commentary can speak again without restarting the whole process

**Evidence:** run/session ids in status before disable, after disable, after re-enable.

## 3) TTS protocol (#349 slice 3)

- [ ] Normal utterance: real accept → playback → terminal from backend (no fabricated success)
- [ ] Induce **timeout**: lane fails soft / silent; no fake accept/complete callback
- [ ] Induce **cancel/reject**: terminal reason matches backend; no double-speak overlap
- [ ] Status/tape (if on) show real backend identity, not a stub

**Evidence:** TTS log + status last-terminal / failure reason.

## 4) Qwen / verifier fail-closed (#349 slice 4)

- [ ] With Qwen allowed: stop/break Ollama or return unframed output → **no** silent template live speech
- [ ] Realization fails closed (`REALIZATION_FAILED` / verify reject path); no TTS for that attempt
- [ ] Cached authored draft (if present) may still speak — that is allowed; live Qwen miss must not invent template copy

**Evidence:** failure reason in status/logs (`realization_transport` / verify reject / missing frame).

## 5) HTTP + mediums (#349 slice 5)

- [ ] Default / `commentary.tape.enabled=false`: narrative tape **not** opened for live race
- [ ] Sync command journal **not** on live reduce hot path (`command_journal_path=None`)
- [ ] When `commentary.tape.enabled=true`: tape writer opens; status `components.tape.enabled` reflects truth
- [ ] Clean process stop: no crash; no unbounded hang (best-effort flush; idle-TTS wait still optional polish)

**Evidence:** tape directory presence/absence + status `components.tape` + confirm no live `narrative-command-journal.ndjson` growth on hot path.

## 6) Happy-path stream smoke (optional same session)

- [ ] Practice/race session connected; commentary enabled; at least one factual/ops line spoken
- [ ] OBS scene flow still stable (irswitch main loop does not die on TTS/Qwen faults)
- [ ] Note rough event→audio feel (latency); on timeout system stays quiet

**Evidence:** short VOD or operator notes + timestamped log window.

---

## Report template (paste into #278)

```markdown
## §24.9 stream smoke – YYYY-MM-DD
Tip SHA: a063143 (or newer)
Host: Windows …

### Results
- [ ] Kill-switch
- [ ] Mailbox cutover
- [ ] TTS protocol
- [ ] Qwen fail-closed
- [ ] HTTP/mediums
- [ ] Happy-path (optional)

### FAIL notes
- …

### Evidence
- Logs: …
- Status JSON: …
- Tape dir: on/off …

### Verdict
- Smoke PASS/FAIL
- Formal §24.9 GO: not claimed / blocked on …
```

## Out of scope for this checklist

- Formal atomic cutover GO in spec §24.9 (replay hash, pressure characterization, rollback drill, etc.)
- Shipping to `master` / release-please
- Flipping frozen `FAMILY_ROUTE` or enabling live v2 speech families beyond what tip already wires
