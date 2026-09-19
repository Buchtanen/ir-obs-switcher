# Live relation state — implementation evidence

Issue: #207  
Branch: `fix/live-relation-story-state`

## Delivered scope

- Battle gaps and closing rates must be finite; gaps cannot be negative. Target order must agree with the claimed front/rear direction using class positions together or overall positions together.
- The accepted ENTER envelope is the lifecycle identity authority. UPDATE/EXIT reuse its correlation, subject, target and relation epoch even when current telemetry is partial or the target changes.
- A stale EXIT for an older target cannot remove its replacement. Duplicate/unmatched exits are idempotently ignored and counted.
- Car index `0` remains a valid identity instead of becoming `unknown`.
- `run_epoch` namespaces emitted correlations and the authoritative active-story snapshot consistently.
- `OverlayBus` marks active-story changes dirty, emits the final empty snapshot and always sends an authoritative snapshot (including `[]`) to a new client.
- `RIVAL_THREAT` validates finite non-negative data and rear order before entry. Active invalid data exits immediately even during the entry cooldown.
- `BATTLE_WON` requires a confirmed hero order gain and the original target behind the hero; widening gap alone is not a result.

## Verification

- 87 focused relation, replay-scenario, battle, manager, rival and overlay snapshot tests passed after the final source/outcome guards.
- Replay fixtures were corrected to provide the hero order required by the now-explicit relation contract. The battle-won fixture now models a real order change; a paired regression proves the same gap evolution without a pass does not emit `BATTLE_WON`.

Full recording replay remains the integration gate after the run-epoch branch is merged.
