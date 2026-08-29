# Pit Wall Light - V4 state visual map

This is the human-readable mirror of `accents/event-visual-map.json`. The JSON file is authoritative for the renderer.

| V4 state | Template | Icon | Tone / rail | Zone | Reuse decision |
|---|---|---|---|---|---|
| `hunting` | `hunting` | `pl-icon-hunting` | `primary` / `blue` | `BATTLE_AHEAD` | Approved HUNTING plate. |
| `hunted` | `hunted` | `pl-icon-hunted` | `warning` / `amber` | `BATTLE_BEHIND` | Approved HUNTED plate; critical payload may select red rail. |
| `approach` | `hunting` | `pl-icon-approach` | `primary` / `blue` | `BATTLE_AHEAD` | Reuses HUNTING plate with approach glyph and copy. |
| `attack_range` | `battle` | `pl-icon-attack-range` | `warning` / `amber` | `BATTLE_AHEAD` | Reuses BATTLE plate with attack-range glyph. |
| `side_by_side` | `battle` | `pl-icon-side-by-side` | `warning` / `amber` | `BATTLE_AHEAD` | Reuses BATTLE plate with side-by-side glyph. |
| `battle_for_position` | `battle` | `pl-icon-battle-for-position` | `warning` / `dual blue + amber` | `BATTLE_AHEAD` | Approved dual-rail BATTLE plate. |
| `battle_won` | `battle` | `pl-icon-battle-won` | `positive` / `green` | `BATTLE_AHEAD` | Reuses BATTLE plate as a result state. |
| `target` | `lap` | `pl-icon-target` | `primary` / `blue` | `EVENT` | Reuses LAP timing plate with target glyph. |
| `projected_lap` | `lap` | `pl-icon-projected-lap` | `timing` / `cyan` | `EVENT` | Reuses LAP timing plate with projection glyph. |
| `pb_attack` | `pb` | `pl-icon-pb-attack` | `positive` / `green` | `EVENT` | Reuses PB plate with PB-attack glyph. |
| `lap_complete` | `lap` | `pl-icon-lap-complete` | `timing` / `cyan` | `EVENT` | Approved LAP plate. |
| `personal_best` | `pb` | `pl-icon-personal-best` | `positive` / `green` | `EVENT` | Approved PB plate. |
| `hot_lap` | `lap` | `pl-icon-hot-lap` | `warning` / `amber` | `EVENT` | Reuses LAP plate with hot-lap glyph. |
| `position_attack` | `position` | `pl-icon-position-attack` | `warning` / `amber` | `EVENT` | Reuses POSITION plate with grid-attack glyph. |
| `gain_found` | `pb` | `pl-icon-gain-found` | `positive` / `green` | `EVENT` | Reuses PB plate with gain glyph. |
| `clean_streak` | `pb` | `pl-icon-clean-streak` | `positive` / `green` | `EVENT` | Reuses PB plate with clean-streak glyph. |
| `overtake` | `position` | `pl-icon-overtake` | `positive` / `green` | `EVENT` | Reuses POSITION plate with overtake glyph. |
| `position_gained` | `position` | `pl-icon-position-gained` | `positive` / `green` | `EVENT` | Approved POSITION plate, upward motion direction. |
| `position_lost` | `position` | `pl-icon-position-lost` | `warning` / `amber` | `EVENT` | Approved POSITION plate, downward motion direction; red only if critical. |
| `rival_threat` | `position` | `pl-icon-rival-threat` | `warning` / `amber` | `EVENT` | Reuses POSITION plate with rival-threat glyph. |
| `invalid_lap` | `exception` | `pl-icon-invalid-lap` | `critical` / `red` | `EVENT` | New EXCEPTION family plate. |
| `incident` | `exception` | `pl-icon-incident` | `warning` / `amber` | `EVENT` | New EXCEPTION family plate. |
| `link_drop` | `exception` | `pl-icon-link-drop` | `critical` / `red` | `EVENT` | New EXCEPTION family plate with broken-link glyph. |
| `pit_entry` | `pit` | `pl-icon-pit-entry` | `warning` / `amber` | `EVENT` | New PIT family plate, phase 1/6. |
| `pit_lane` | `pit` | `pl-icon-pit-lane` | `warning` / `amber` | `EVENT` | New PIT family plate, phase 2/6. |
| `pit_stopped` | `pit` | `pl-icon-pit-stopped` | `warning` / `amber` | `EVENT` | New PIT family plate, phase 3/6. |
| `pit_released` | `pit` | `pl-icon-pit-released` | `primary` / `blue` | `EVENT` | New PIT family plate, phase 4/6. |
| `pit_exit` | `pit` | `pl-icon-pit-exit` | `primary` / `blue` | `EVENT` | New PIT family plate, phase 5/6. |
| `pit_outcome` | `pit` | `pl-icon-pit-outcome` | `positive` / `green` | `EVENT` | New PIT family plate, result phase 6/6. |
| `hr_pressure` | `bio` | `pl-icon-hr-pressure` | `bio` / `violet` | `BIO_EXPANDED` | Approved BIO plate. |
| `composure_test` | `bio` | `pl-icon-composure-test` | `bio` / `violet` | `BIO_EXPANDED` | Reuses BIO plate with composure glyph. |
| `high_load` | `bio` | `pl-icon-high-load` | `critical` / `red` | `BIO_EXPANDED` | Reuses BIO plate with high-load glyph. |
| `ble_reconnecting` | `bio` | `pl-icon-ble-reconnecting` | `warning` / `amber` | `BIO_EXPANDED` | Reuses BIO plate with BLE reconnect glyph. |
| `final_lap` | `final-lap` | `pl-icon-final-lap` | `warning` / `amber` | `SESSION` | Approved FINAL LAP plate. |
| `finish` | `finish` | `pl-icon-finish` | `positive` / `green` | `SESSION` | Approved FINISH plate. |

## Event and zone routing

The same JSON also contains all 35 uppercase event routes from `themes-v4/event_catalog.json`. `BATTLE_AHEAD` and `BATTLE_BEHIND` are explicit aliases of the `BATTLE` layout; they differ only by semantic direction and stack order.

CPU/GPU thermal events route to the `incident` state and override only the glyph (`cpu-temp-high` / `gpu-temp-high`).
