# Bio / heart rate (`src/irswitch/bio/`)

**Účel:** BLE Heart Rate Service → `BioState` pro overlay a HR eventy. Fail-soft, scan/connect mimo event loop.

## Tok

`HeartRateProvider` (`provider.py`):

- Scan BLE (`bleak`), filtr na HR service UUID
- Notify `Heart Rate Measurement` → `parser.parse_heart_rate_measurement`
- `classify_hr_state` + `HeartRateHistory` (`history.py`)
- Callback do overlay bus (`OverlayRuntime._run_bio`)

Adresa zařízení se v logu hashuje. Chybějící `bleak` / žádný belt = prázdný bio, overlay žije.

`HrPressureEmitter` (`events/hr_pressure.py`) je **zvlášť** (feature flag `event_engine.hr_pressure`) — čte `BioState` v EventEngine ticku.

## Config

`[bio]` / heart-rate v overlay settings — [CONFIG.md](../../../CONFIG.md). Sampling 0 Hz = push.

Admin Extensions karta ukazuje BLE stav.

## Testy

Parser/provider testy v `tests/` (`test_hr_pressure_emitter.py` a související overlay/bio).

## Nepatří sem

iRacing telemetrie, TTS (HR může triggerovat envelope, větu skládá commentary).
