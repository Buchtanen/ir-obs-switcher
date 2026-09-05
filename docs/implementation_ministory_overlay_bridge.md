# MiniStory overlay presentation bridge

## Problem

Commentary already made its final freshness decision after Qwen returned, but V4 cards still followed the raw source `EXIT` and browser hold timers. A correct spoken story could therefore outlive its matching card, while delayed worker callbacks had no safe route back to the asyncio-owned overlay bus.

## Implemented contract

- `RacePipeline` assigns one MiniStory identity before immutable accepted-event fan-out. The optional frozen sidecar is replay-compatible and is consumed by both peers.
- `MiniStoryRegistry` remains the shared thread-safe source of story/run/order revision truth. Commentary can adopt the sidecar during replay without generating a second identity.
- TTS opens a presentation lease at queue acceptance and emits versioned lifecycle transitions. Queue replacement/interruption explicitly closes dropped leases.
- `RaceRuntime` forwards worker transitions with `loop.call_soon_threadsafe()`; no TTS-thread code touches `OverlayBus` or asyncio-owned state.
- `OverlayConsumer` owns a bounded/coalesced lifecycle inbox and merges leased cards with the producer's source snapshot. Older revisions are ignored.
- Source `EXIT` changes a leased card to `RESULT` and carries the EXIT event's fresh identity, sequence and timestamps; `completed`, `interrupted`, `invalidated`, session reset and run reset remove it. A terminal correlation tombstone prevents a stale source snapshot from reviving the card.
- The V4 renderer reconciles authoritative snapshots instead of clearing every card. A snapshot may adopt an already rendered card at an equal sequence, then removes that snapshot-managed or leftover-leased card when it disappears from a later snapshot. Live narrative leases (`building` / `committed` / `speaking`) disable client hold timers. Terminal `resolved` (and later) states drop the lease so the RESULT hold timer can fire; the same-or-older snapshot cannot revive an expired RESULT.
- Overlay asset cache identity is `1.2.21` so OBS CEF cannot retain the previous renderer.
  EXIT, empty/terminal snapshots and RESULT hold share one sequence tombstone; speaking no
  longer revives a same-or-older card after teardown.

## Evidence

- Producer/consumer tests cover shared frozen identity, replay adoption and preserved hero-order preemption.
- MiniStory/TTS tests cover building, resolved revision propagation and orphan-free queue replacement.
- Overlay tests cover live/building/speaking/completed, source EXIT to result, stale revision rejection, reset/reconnect state and thread marshalling.
- JS contract tests require incremental snapshot reconciliation, equal-sequence adoption, terminal removal and MiniStory-aware rendering.

## Docs and config impact

- Updated `API.md` and `COMMENTARY_ENGINE.md`.
- Config: no change. Existing unleased V4 event behavior remains compatible.

## Remaining manual gate

Workstream G must replay the curated tape corpus, run localhost Qwen, and visually verify the live-to-result-to-completed and live-to-interrupted timelines in OBS after a Browser Source cache refresh.
