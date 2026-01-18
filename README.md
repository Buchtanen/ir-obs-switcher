# iRacing → OBS Auto Scene Switcher (Python) + External TUI

Tento repozitář obsahuje skeleton projektu pro službu, která:

- čte stav iRacingu přes `pyirsdk` (shared memory)
- automaticky přepíná OBS scény přes `obs-websocket` v5
- vystavuje lokální HTTP + WebSocket API
- poskytuje externí Textual TUI dashboard jako samostatný proces

## Cíle

- spolehlivé přepínání scén bez flappingu (debounce + cooldown)
- override s časovým limitem z konfigurace
- bezpečné chování při výpadku iRacing nebo OBS (čekání v loopu)

## Technologie

Core:
- Python 3.11+
- pyirsdk
- obsws-python
- aiohttp
- pydantic
- logging

TUI:
- textual

Testy:
- pytest
- pytest-asyncio
- freezegun

## Struktura projektu

```
iracing-obs-switcher/
  README.md
  pyproject.toml
  config/
    config.example.ini
  src/
    irswitch/
      __init__.py
      main.py
      config.py
      models.py
      iracing/
        __init__.py
        reader.py
        extractors.py
      obs/
        __init__.py
        client.py
      logic/
        __init__.py
        state_machine.py
        policy.py
      server/
        __init__.py
        api.py
        commands.py
      util/
        __init__.py
        logging.py
        clock.py
    irswitch_tui/
      __init__.py
      main.py
      ui.py
      client.py
```

## Konfigurace (INI)

Viz `config/config.example.ini`.

## Spuštění (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -U pip
pip install -e .
```

Core:

```powershell
irswitchd --config config/config.ini
```

TUI:

```powershell
irswitch-tui --url http://127.0.0.1:17321
```

## Testy

```powershell
pip install -e .[test]
pytest
```

## Windows: vytvoření EXE + služba

### Core service jako EXE

Příklad s PyInstallerem (single-file):

```powershell
pip install pyinstaller
pyinstaller --onefile --name irswitchd --collect-all irswitch src\irswitch\main.py
```

Výstupní EXE bude v `dist\irswitchd.exe`. Spouštění s konfigurací:

```powershell
dist\irswitchd.exe --config config\config.ini
```

### Instalace core jako Windows Service

Doporučený postup je použít [NSSM](https://nssm.cc/) (Non-Sucking Service Manager).

```powershell
nssm install irswitchd
```

V GUI nastav:
- **Path**: `C:\path\to\dist\irswitchd.exe`
- **Arguments**: `--config C:\path\to\config\config.ini`
- **Startup directory**: složka s EXE

Poté službu spusť:

```powershell
nssm start irswitchd
```

### TUI jako EXE (bez služby)

```powershell
pip install pyinstaller
pyinstaller --onefile --name irswitch-tui --collect-all irswitch_tui src\irswitch_tui\main.py
```

Spuštění:

```powershell
dist\irswitch-tui.exe --url http://127.0.0.1:17321
```

## Stavový model (návrh)

- connected_iracing: bool
- connected_obs: bool
- autoswitch: bool
- override_scene: str | None
- override_until: datetime | None
- mode: IDLE | GARAGE | RACE | REPLAY
- target_scene: str
- current_scene: str
- last_switch_ts
- reason

## Logování

- switch
- status_changed
- latency

## iRacing SDK proměnné (návrh pro detekci stavu)

Níže jsou doporučené proměnné z iRacing SDK (pyirsdk), které lze použít
pro odvození stavu:

- `IsOnTrack` / `IsOnTrackCar` → simulace běží a jezdec je na trati (RACE)
- `PlayerCarInGarage` / `IsInGarage` → jezdec je v garáži (GARAGE)
- `IsReplay` → běží replay (REPLAY)

Navržená priorita:

1. `IsReplay` → `REPLAY`
2. `IsOnTrack` nebo `IsOnTrackCar` → `RACE`
3. `PlayerCarInGarage` nebo `IsInGarage` → `GARAGE`
4. jinak → `IDLE`

Konkrétní mapování scén řešíte v `[scenes]` v INI souboru.
