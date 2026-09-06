# Commentary dataset map (agents)

Where polish pairs, eval cases, and ChatML live. **Do not copy raw tapes or SFT
into this public repo.** HUD bugs stay on skill `overlay-tape-triage`.

Canonical manipulation (keep/drop, gold rules, CLI) lives in the **private**
sibling [ir-commentary-lora](https://github.com/Buchtanen/ir-commentary-lora)
(`DATASETS.md`). Clone next to irswitch:

`C:\Users\richa\Projekty\obs-switcher\ir-commentary-lora`

## Look here first

| Need | Path | Notes |
| --- | --- | --- |
| Raw live tape (this PC) | `recordings/overlay-*.jsonl` | Gitignored. Newest file matching stream UTC. |
| `llm_polish` request/response | same tape, `type: llm_polish` | Full `request.messages`, `response`, `factPack`, `attemptLog`. |
| Spoken line vs skip | tape `type: commentary` | Speak/skip spam is **DEBUG-only** on current master / Test 7. |
| Proposition eval (no gold sentence) | `tests/fixtures/commentary/commentary_eval_cases.json` | Points at **2026-09-01** tapes (`overlay-20260901T*.jsonl`), ANCHOR/skeleton era. Not facts/3. |
| Replay those cases | `python -m irswitch.commentary.replay_eval` | Optional `--live-url http://192.168.0.38:11434/v1`. CI does not call Ollama. |
| Clean archive + ChatML | `../ir-commentary-lora/tapes/clean/` and `datasets/facts3/{sft,dpo}/` | After `clean_tapes.py`. Empty until inbox is filled. |
| Cleaner (no model) | `../ir-commentary-lora/scripts/clean_tapes.py` | Stdlib only. Tests: `../ir-commentary-lora/tests/test_clean_tapes.py`. |
| Push from irswitch | `scripts/push_tapes_to_lora_repo.ps1` | On branch `feat/commentary-llm-dataset` (#219). Copies into `tapes/inbox/`. |
| Production prompt builder | `src/irswitch/commentary/polish.py` (`_build_request`, `_user_content`) | Live user prefix is `DATA:` (Test 7+). |

`logs/irswitch.log` is not a dataset (BLE/OBS noise, no prompt/completion).

## When `llm_polish` is missing

On current `master`, `[overlay] session_tape_llm=true` (default after #228) writes
`llm_polish` pairs on INFO while `commentary.llm_polish=true` and a tape is open.

- Missing pairs: polish off, tape off, or `session_tape_llm=false` (DEBUG-only).
- Still open (#219): compile/export into the private `ir-commentary-lora` datasets.

Replay never writes polish rows.

## Prompt families — never mix in one SFT file

Detect from `request.messages[1].content` (first attempt in `attemptLog` if present):

| Family | User content | Typical tapes |
| --- | --- | --- |
| `skeleton` | starts with `SKELETON:` | 2026-08-31 |
| `anchor` | starts with `ANCHOR:` | 2026-09-01 (eval corpus) |
| `facts3` (Sep 2) | starts with `TIME FRAME` or contains `SOURCE FACTS` | 2026-09-02 |
| live microplan | starts with `DATA:` | current `polish.py` |

Default `clean_tapes.py --family facts3` only keeps the Sep-2 detector
(`TIME FRAME` / `SOURCE FACTS`). **`DATA:` is classified `other` today** and is
skipped unless you pass `--family all` and filter yourself. Do not treat that
as “no data”.

Accepted (`outcome=ok`) is **not** gold. The cleaner uses polished text only when
numbers stay inside `factPack`; otherwise canonical/skeleton. Training on the 4B’s
own accepted lines without that check is negative EV.

## Hard cases for a model test

Prefer these `nodeId` values over `quali_recap`:

- `field_fact` — relation bind (“gap to Hudson” ≠ “Hudson’s gap to the leader”)
- `two_front_battle` — hero vs car ahead vs car behind, two gaps
- `overtake` — who passed whom

Live request shape: English-only. System from `_system_prompt` microplan (professional
commentator, 160 characters, no future/pass prediction); user is only
`DATA: {role keys…}` — no STYLE, no example, no “Write a NEW broadcast line.”
Probed 4B keys: hunted `chaser`+`gap`+`situation`; hunting `hero`+`target`+`gap`;
overtake `hero`+`passed`+`new_position`; two-front `hero`+`car_ahead`+`car_behind`
(plus gaps when selected) with names inside `situation`; field_fact gap
`chaser`+`target`+`gap` (no `hero`); field_fact place `chaser`+`position`+
`situation: holds P…`; lost `hero`+`lost_to`+`new_position`;
leader `new_leader`+`old_leader`; rival `threat`+`gap`; incident / quali / wrap
`hero`+`situation` (+ position when selected); gained `hero`+`new_position`;
field leader `{leader} sets the pace out front`; weather `skies`/`air_temp`/
`wind_speed`+`current conditions`; lap `hero`+lap+time; personal best adds
`position` so `-0.4` is not read as a race lead. Color, energy and a bit of
showmanship are allowed; new names/numbers/events/future/pass are not.
Ollama: `POST {llm_base_url}/chat/completions` with `think: false`,
`max_tokens` / `options.num_predict` from `commentary.llm_num_predict` (45).

## Do not

- Commit `recordings/` or `tapes/inbox/` HUD dumps (`event` / `decision` / `stories`).
- Mix skeleton, ANCHOR, and `DATA:` / SOURCE FACTS in one train split.
- Point new eval cases at 2026-09-01 tapes and call that the live prompt.
- Copy this private dataset into irswitch.
