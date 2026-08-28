# V4 golden layout — fixture URLs

Deterministic acceptance views for the V4 renderer. All URLs require `demo=1` (injected fixtures only; live flags stay off).

**Base pattern**

```
/overlay?demo=1&renderer=v4&layout=golden&fixture=<id>&theme=<theme>&motion=off
```

**Themes:** `cyber_racing` (default), `stealth_graphite`, `night_attack`

**Gallery (all fixtures):** omit `fixture` or use `fixture=all`

```
/overlay?demo=1&renderer=v4&layout=golden&fixture=all&theme=cyber_racing&motion=off
```

**Shortcut:** `/overlay/golden` redirects to the gallery URL above.

---

## Timing

### lap_complete

- Fixture id: `lap_complete`
- Event type: `LAP_COMPLETE`
- Phase: `RESULT`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=lap_complete&theme=cyber_racing&motion=off`

### personal_best

- Fixture id: `personal_best`
- Event type: `PERSONAL_BEST`
- Phase: `RESULT`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=personal_best&theme=cyber_racing&motion=off`

---

## Battle

### hunting

- Fixture id: `hunting`
- Event type: `HUNTING`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=hunting&theme=cyber_racing&motion=off`

### hunted

- Fixture id: `hunted`
- Event type: `HUNTED`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=hunted&theme=cyber_racing&motion=off`

### approach

- Fixture id: `approach`
- Event type: `APPROACH`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=approach&theme=cyber_racing&motion=off`

### attack_range

- Fixture id: `attack_range`
- Event type: `ATTACK_RANGE`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=attack_range&theme=cyber_racing&motion=off`

### side_by_side

- Fixture id: `side_by_side`
- Event type: `SIDE_BY_SIDE`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=side_by_side&theme=cyber_racing&motion=off`

### battle_stack (combo)

- Shows hunting + hunted together (not a catalog state)
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=battle_stack&theme=cyber_racing&motion=off`

---

## Position

### position_gained

- Fixture id: `position_gained`
- Event type: `POSITION_GAINED`
- Phase: `RESULT`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=position_gained&theme=cyber_racing&motion=off`

### position_lost

- Fixture id: `position_lost`
- Event type: `POSITION_LOST`
- Phase: `RESULT`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=position_lost&theme=cyber_racing&motion=off`

### overtake

- Fixture id: `overtake`
- Event type: `OVERTAKE`
- Phase: `RESULT`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=overtake&theme=cyber_racing&motion=off`

---

## Pit

### pit_entry

- Fixture id: `pit_entry`
- Event type: `PIT_ENTRY`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=pit_entry&theme=cyber_racing&motion=off`

### pit_lane

- Fixture id: `pit_lane`
- Event type: `PIT_LANE`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=pit_lane&theme=cyber_racing&motion=off`

### pit_stopped

- Fixture id: `pit_stopped`
- Event type: `PIT_STOPPED`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=pit_stopped&theme=cyber_racing&motion=off`

### pit_released

- Fixture id: `pit_released`
- Event type: `PIT_RELEASED`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=pit_released&theme=cyber_racing&motion=off`

### pit_exit

- Fixture id: `pit_exit`
- Event type: `PIT_EXIT`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=pit_exit&theme=cyber_racing&motion=off`

### pit_outcome

- Fixture id: `pit_outcome`
- Event type: `PIT_OUTCOME`
- Phase: `RESULT`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=pit_outcome&theme=cyber_racing&motion=off`

---

## Bio

### hr_pressure

- Fixture id: `hr_pressure`
- Event type: `HR_PRESSURE_RISING`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=hr_pressure&theme=cyber_racing&motion=off`

### ble_reconnecting

- Fixture id: `ble_reconnecting`
- Event type: `BLE_LOST`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=ble_reconnecting&theme=cyber_racing&motion=off`

---

## Session

### final_lap

- Fixture id: `final_lap`
- Event type: `FINAL_LAP`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=final_lap&theme=cyber_racing&motion=off`

### finish

- Fixture id: `finish`
- Event type: `FINISH`
- Phase: `RESULT`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=finish&theme=cyber_racing&motion=off`

---

## Exception

### incident

- Fixture id: `incident`
- Event type: `INCIDENT`
- Phase: `ACTIVE`
- URL: `/overlay?demo=1&renderer=v4&layout=golden&fixture=incident&theme=cyber_racing&motion=off`

---

## Theme variants

Replace `theme=cyber_racing` with:

- `theme=stealth_graphite`
- `theme=night_attack`

Example (night attack gallery):

```
/overlay?demo=1&renderer=v4&layout=golden&fixture=all&theme=night_attack&motion=off
```
