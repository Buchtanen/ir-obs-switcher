# Pit Wall Dark - V4 state visual map

This is the human-readable mirror of `accents/event-visual-map.json`. The JSON file is authoritative for the renderer.

| V4 state | Template | Icon | Tone / rail | Zone | Reuse decision |
|---|---|---|---|---|---|
| `hunting` | `hunting` | `pw-icon-hunting` | `primary` / `cyan` | `BATTLE_AHEAD` | Approved HUNTING plate. |
| `hunted` | `hunted` | `pw-icon-hunted` | `warning` / `amber` | `BATTLE_BEHIND` | Approved HUNTED plate; critical payload may select red rail. |
| `approach` | `hunting` | `pw-icon-approach` | `primary` / `cyan` | `BATTLE_AHEAD` | Reuses HUNTING plate with approach glyph and copy. |
| `attack_range` | `battle` | `pw-icon-attack-range` | `warning` / `amber` | `BATTLE_AHEAD` | Reuses BATTLE plate with attack-range glyph. |
| `side_by_side` | `battle` | `pw-icon-side-by-side` | `warning` / `amber` | `BATTLE_AHEAD` | Reuses BATTLE plate with side-by-side glyph. |
| `battle_for_position` | `battle` | `pw-icon-battle-for-position` | `warning` / `dual cyan + amber` | `BATTLE_AHEAD` | Approved dual-rail BATTLE plate. |
| `battle_won` | `battle` | `pw-icon-battle-won` | `positive` / `green` | `BATTLE_AHEAD` | Reuses BATTLE plate as a result state. |
| `target` | `lap` | `pw-icon-target` | `primary` / `cyan` | `EVENT` | Reuses LAP timing plate with target glyph. |
| `projected_lap` | `lap` | `pw-icon-projected-lap` | `timing` / `cyan` | `EVENT` | Reuses LAP timing plate with projection glyph. |
| `pb_attack` | `pb` | `pw-icon-pb-attack` | `positive` / `green` | `EVENT` | Reuses PB plate with PB-attack glyph. |
| `lap_complete` | `lap` | `pw-icon-lap-complete` | `timing` / `cyan` | `EVENT` | Approved LAP plate. |
| `personal_best` | `pb` | `pw-icon-personal-best` | `positive` / `green` | `EVENT` | Approved PB plate. |
| `hot_lap` | `lap` | `pw-icon-hot-lap` | `warning` / `amber` | `EVENT` | Reuses LAP plate with hot-lap glyph. |
| `position_attack` | `position` | `pw-icon-position-attack` | `warning` / `amber` | `EVENT` | Reuses POSITION plate with grid-attack glyph. |
| `gain_found` | `pb` | `pw-icon-gain-found` | `positive` / `green` | `EVENT` | Reuses PB plate with gain glyph. |
| `clean_streak` | `pb` | `pw-icon-clean-streak` | `positive` / `green` | `EVENT` | Reuses PB plate with clean-streak glyph. |
| `overtake` | `position` | `pw-icon-overtake` | `positive` / `green` | `EVENT` | Reuses POSITION plate with overtake glyph. |
| `position_gained` | `position` | `pw-icon-position-gained` | `positive` / `green` | `EVENT` | Approved POSITION plate, upward motion direction. |
| `position_lost` | `position` | `pw-icon-position-lost` | `warning` / `amber` | `EVENT` | Approved POSITION plate, downward motion direction; red only if critical. |
| `rival_threat` | `position` | `pw-icon-rival-threat` | `warning` / `amber` | `EVENT` | Reuses POSITION plate with rival-threat glyph. |
| `invalid_lap` | `exception` | `pw-icon-invalid-lap` | `critical` / `red` | `EVENT` | New EXCEPTION family plate. |
| `incident` | `exception` | `pw-icon-incident` | `warning` / `amber` | `EVENT` | New EXCEPTION family plate. |
| `link_drop` | `exception` | `pw-icon-link-drop` | `critical` / `red` | `EVENT` | New EXCEPTION family plate with broken-link glyph. |
| `pit_entry` | `pit` | `pw-icon-pit-entry` | `warning` / `amber` | `EVENT` | New PIT family plate, phase 1/6. |
| `pit_lane` | `pit` | `pw-icon-pit-lane` | `warning` / `amber` | `EVENT` | New PIT family plate, phase 2/6. |
| `pit_stopped` | `pit` | `pw-icon-pit-stopped` | `warning` / `amber` | `EVENT` | New PIT family plate, phase 3/6. |
| `pit_released` | `pit` | `pw-icon-pit-released` | `primary` / `cyan` | `EVENT` | New PIT family plate, phase 4/6. |
| `pit_exit` | `pit` | `pw-icon-pit-exit` | `primary` / `cyan` | `EVENT` | New PIT family plate, phase 5/6. |
| `pit_outcome` | `pit` | `pw-icon-pit-outcome` | `positive` / `green` | `EVENT` | New PIT family plate, result phase 6/6. |
| `hr_pressure` | `bio` | `pw-icon-hr-pressure` | `bio` / `amber` | `BIO_EXPANDED` | Approved BIO plate. |
| `composure_test` | `bio` | `pw-icon-composure-test` | `bio` / `amber` | `BIO_EXPANDED` | Reuses BIO plate with composure glyph. |
| `high_load` | `bio` | `pw-icon-high-load` | `critical` / `red` | `BIO_EXPANDED` | Reuses BIO plate with high-load glyph. |
| `ble_reconnecting` | `bio` | `pw-icon-ble-reconnecting` | `warning` / `amber` | `BIO_EXPANDED` | Reuses BIO plate with BLE reconnect glyph. |
| `final_lap` | `final-lap` | `pw-icon-final-lap` | `warning` / `amber` | `SESSION` | Approved FINAL LAP plate. |
| `finish` | `finish` | `pw-icon-finish` | `positive` / `green` | `SESSION` | Approved FINISH plate. |

## Event and zone routing

The same JSON also contains all 35 uppercase event routes from `themes-v4/event_catalog.json`. `BATTLE_AHEAD` and `BATTLE_BEHIND` are explicit aliases of the `BATTLE` layout; they differ only by semantic direction and stack order.

CPU/GPU thermal events route to the `incident` state and override only the glyph (`cpu-temp-high` / `gpu-temp-high`).
