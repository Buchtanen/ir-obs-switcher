# Spec: Event graph editor (nice-to-have)

**Status:** idea — not scheduled, no implementation in this document  
**Priority:** nice-to-have  
**Baseline:** Event Engine V4 catalog + `/config` FieldSpec UI (master). Visual node chrome is stronger after Pit Wall themes land ([#118](https://github.com/Buchtanen/ir-obs-switcher/pull/118)).  
**Related:** [`EVENT_ENGINE_V4_PARALLEL_PLAN.md`](../EVENT_ENGINE_V4_PARALLEL_PLAN.md) §0.5.2 (INI + FieldSpec stays the config contract)

This file captures a product idea so it is not rediscovered from scratch. It is **not** current behavior. Do not treat anything below as a shipping contract until a later work item promotes a slice.

---

## 1. Intent

Add a web UI that lets a user **see** the overlay event pipeline, **edit known knobs** on each event, and **watch a live or replayed run** — without turning the engine into a user-defined rule language.

Today the knobs exist (or already live on dataclasses) but the only editor is a flat `/config` form. The graph is the UI for width, not a second source of truth.

---

## 2. Current baseline (accurate)

Pipeline (unchanged by this idea):

```text
iRacing / bio / system
  → Python emitters (FSM + hysteresis)
  → EventManager (+ cooldown, slots, pit-guard)
  → OverlayBus / WS
  → V4 renderer (catalog state → plate + icon + zone)
```

| Layer | Today | Unlocked? |
| --- | --- | --- |
| Event types | `themes-v4/event_catalog.json` (33 wired states) | list is fixed |
| Thresholds | INI + `FieldSpec` + `PUT /api/config` | hunting/hunted + some durations/priorities |
| Hidden settings | `EventPrioritySettings` / `EventSettings` fields not in `FieldSpec` | code can read them; UI cannot |
| Hardcoded emitter constants | e.g. `RivalThreatEmitter` `_MIN_CLOSING`, `_MAX_GAP_S`, `_COOLDOWN_S` | not config |
| Presentation | adapter-hardcoded zone / hold / accent | not config |
| Per-event enable | family flags only (`event_engine.practice`, `pit_story`, …) | cannot disable one catalog entry |
| Explainability | `DecisionLog` in `EventManagerV2` | not on HTTP |
| Emitter internal state | `NONE` / `CANDIDATE` / `ACTIVE` | not on WS (only resulting events) |
| Web UI | `/config` form, `/overlay/debug` JSON, `/overlay/demo` loop | no graph |
| Scene switcher | `logic/` mode → OBS scene | **separate product**; do not mix |

`EVENT_ENGINE_V4_PARALLEL_PLAN.md` already rejected a second config format beside INI (no YAML trees as a parallel source of truth).

---

## 3. Goal vs non-goals

### Goal

A new page (working name `/overlay/editor`) that:

1. Renders a **fixed** graph: signals → predicates → event nodes → arbitration → overlay zones.
2. Uses catalog + V4 assets for node chrome (plates/icons), not generic grey boxes.
3. Edits **existing** dotted keys (and later promoted keys) via the current config API.
4. Visualizes runtime: live values on edges, node state, suppress/cooldown reason, optional replay.

### Non-goals (explicit)

- Free-form node programming (drag any node, wire any connector, invent conditions).
- User-defined event types or new emitters from the UI.
- Changing FSM topology (`NONE → CANDIDATE → ACTIVE`).
- Replacing arbitration with a user graph (slots, pit-guard, preemption stay in code).
- Mixing overlay events with the OBS scene switcher in one canvas.
- New Python/JS dependencies or a frontend bundler.
- INI → YAML migration (separate track if ever approved).

Free-form graphs would be a different product (`semver:major`). Out of scope forever unless a later spec replaces this one.

---

## 4. Unlock path (when we pick this up)

Same contract every slice: **schema + test first, UI second**. Editor is a view. Writes stay `PUT /api/config`.

### Slice 1 — Surface (no new knobs)

- Static graph from catalog + existing `FieldSpec` rows.
- Click a node → that node's fields → Save through the current API.
- Live values from `/ws/overlay` where already present.
- Optional: `GET` for `DecisionLog` (log already exists; it is not exposed).

Effect: the settings *feel* wide. Behavior is unchanged.

### Slice 2 — Promote hidden knobs

Move values that already exist on dataclasses (or module constants) into `FieldSpec` + `CONFIG.md` + `config.example.ini`:

- remaining `events.priorities.*` (`overtake`, `pit`, `bio`, `gain_found`, …)
- `alert_duration`, `session_duration`, `battle_update_hz` if still missing from the schema
- emitter constants such as rival-threat gap / closing / cooldown

Engine keeps the same predicates; it stops reading magic numbers.

### Slice 3 — Per-event policy (the actual “wide unlock”)

One optional INI section per catalog entry. Missing key = today's hardcoded default.

```ini
[event.POSITION_LOST]
enabled = true
priority = 70
min_hold_ms = 2500
max_hold_ms = 8000
overlay = true
```

This is how 33 events become configurable without a rule engine: mute `RIVAL_THREAT`, shorten `LAP_COMPLETE`, keep `INCIDENT` off the overlay.

### Slice 4 — Typed predicates (only after 1–3 are in use)

Not AND/OR trees. Each emitter keeps a **fixed predicate list** with a whitelist of signals and operators (`<`, `>`, `<=`). Hunting may edit `gap` / `closing` / `hold`. Wiring `hr_delta` to `PIT_EXIT` is rejected by the API.

Do not start here. Do not apply to all 33 types in one change.

### Never in this spec

- User-authored topology
- Custom boolean ASTs
- Scene-switcher nodes on the same graph

---

## 5. Proposed UI (slice 1)

Vanilla SVG/Canvas in the existing static web tree. No React Flow / Rete / npm build.

Fixed columns (connectors are illustrative, not user-rewirable):

1. **Signals** — `gap_ahead`, `closing`, `class_position`, `hr_delta`, `on_pit_road`, …
2. **Predicates** — FieldSpec thresholds on that emitter
3. **Event node** — catalog `eventType` + V4 plate/icon
4. **Arbitration** — priority, slot, cooldown, pit-guard
5. **Output** — zone `battle` / `event` + active story

Runtime overlay:

- edge label: current value vs threshold (`gap 1.2 / enter 3.0`)
- node chrome: idle / candidate / active / cooldown / suppressed
- sidebar: `DecisionLog` (`emitted`, `suppressed`, `cooldown`, `pit_cycle`)
- replay: existing input-replay harness / demo fixtures, no iRacing required

Invalid config must not crash the main loop. Live reload only for keys already marked `live=True`. Every slice needs reset-to-default.

---

## 6. Backend gaps (only when implementing)

| Gap | Why |
| --- | --- |
| `DecisionLog` not on HTTP | needed for the sidebar |
| Emitter tracks not on WS | candidate/hold timers are invisible today |
| Static graph descriptor | catalog + FieldSpec → layout JSON; layout is not policy |
| Per-event INI sections | slice 3 only; requires config + docs + tests |

Do not add a second writer beside `apply_overlay_values`.

---

## 7. Docs / config impact (when a slice ships)

| Slice | Docs | Config |
| --- | --- | --- |
| 1 | `README.md` (new page URL), `API.md` if a decisions endpoint ships | none, unless a new GET is added |
| 2–3 | `CONFIG.md` + `config/config.example.ini` + migration note (missing key = old default) | new `FieldSpec` rows / `[event.*]` sections |
| 4 | same + predicate whitelist documented | operators/signals as typed fields |

This idea doc stays the pointer until a slice is implemented. Do not copy defaults here; `CONFIG.md` remains the live contract.

---

## 8. Acceptance criteria (for a future work item)

Not claimed done. When a slice is scheduled, that issue/PR should check a subset of:

- [ ] Page is reachable from existing overlay nav
- [ ] Graph nodes match catalog entries (no invented types)
- [ ] Edits persist only through `PUT /api/config` and survive reload
- [ ] Missing new keys keep current runtime behavior
- [ ] Live/replay view does not crash when iRacing is disconnected
- [ ] No new dependencies
- [ ] Tests for any newly exposed FieldSpec / per-event policy
- [ ] `CONFIG.md` / `API.md` updated for that slice only

TDD-exception for **this** file: docs-only capture. Implementation slices are not exempt.

---

## 9. Test plan (for a future work item)

- Unit: FieldSpec promote / per-event defaulting / API reject of illegal predicate wiring
- Replay: existing overlay input fixtures drive the live graph
- Manual: `/overlay/editor` + demo loop / golden fixtures; disconnect iRacing; save + reload

---

## 10. Open questions (do not block capturing the idea)

- Exact route name (`/overlay/editor` vs `/events`)
- Whether scene-switcher gets its own tiny `mode → scene` page later
- How much emitter-internal state is safe to put on WS (verbosity vs usefulness)
- Whether slice 3 uses `[event.TYPE]` INI sections or dotted `event.TYPE.enabled` keys (dotted keys match today's UI)

Decide these on the first implementation issue, not here.
