# Broadcast/chapter clock — implementation evidence

Issue: #205  
Branch: `fix/broadcast-chapter-clock`

- Metrics and chapter generation consume one `BroadcastClock` snapshot and epoch.
- OBS WebSocket v5 `outputDuration` is interpreted as milliseconds (the previous implementation multiplied it by 1000 again).
- An unavailable OBS status is unknown, not a confirmed stream stop.
- Short stop/start transitions retain a cumulative offset. A known unchanged broadcast ID also survives a longer reconnect.
- A changed broadcast ID, or a confirmed stop without matching identity, starts a new epoch and resets chapter history with the clock.
- The clock never moves backwards on a transient counter regression and falls back to monotonic progression if the OBS counter is unavailable.
- Removing a provisional end marker on resume requests an authoritative chapter snapshot for clients.

Verification: 101 focused tests passed across clock, chapter, status, metrics, YouTube and OBS client suites before commit.
