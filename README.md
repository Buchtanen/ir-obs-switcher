# iRacing → OBS Auto Scene Switcher (Python) + External TUI

**Status projektu**: Viz [STATUS.md](STATUS.md) pro přehled co je hotové a co následuje.

Tento repozitář obsahuje službu, která:

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

## Quick Start

### 1. Instalace

```powershell
# Vytvoření virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Instalace závislostí
pip install -U pip
pip install -e .
```

### 2. Konfigurace

Zkopíruj `config/config.example.ini` na `config/config.ini` a uprav:

```ini
[obs]
ws_url = ws://127.0.0.1:4455
password = tvé_obs_heslo
```

**Důležité**: Nastav správné heslo pro OBS WebSocket (nastavení v OBS: Tools → WebSocket Server Settings).

### 3. Nastavení OBS

1. Otevři OBS Studio
2. Tools → WebSocket Server Settings
3. Povol "Enable WebSocket server"
4. Nastav port (výchozí: 4455)
5. Nastav heslo (stejné jako v `config.ini`)
6. Vytvoř scény s názvy podle `[scenes]` v config (Idle, Pits, Race, Replay)

### 4. Spuštění služby

```powershell
irswitchd --config config/config.ini
```

Mělo by se zobrazit:
```
Starting iRacing OBS switcher service
Connected to OBS at 127.0.0.1:4455
API server started on http://127.0.0.1:17321
Starting main loop
```

### 5. Spuštění TUI (volitelné)

V novém terminálu:

```powershell
irswitch-tui --url http://127.0.0.1:17321
```

### 6. Testování

1. Spusť iRacing
2. V TUI nebo logu sleduj změny módu (IDLE → GARAGE → RACE)
3. OBS by měl automaticky přepínat scény podle módu

## Konfigurace (INI)

Viz `config/config.example.ini` pro kompletní příklad.

### Sekce konfigurace

- `[app]` - HTTP server nastavení (host, port, log level)
- `[iracing]` - Polling frekvence (poll_hz)
- `[obs]` - WebSocket URL a heslo
- `[switching]` - Debounce, cooldown, override nastavení
- `[scenes]` - Mapování módu na názvy OBS scén

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

**Dokumentace testů**: Detailní popis všech testů, co testují a proč, najdeš v [tests.md](tests.md).

## Vytvoření EXE souborů

### Automatické build skripty

**Windows (PowerShell)**:
```powershell
.\build_exe.ps1 --all
# Nebo jednotlivě:
.\build_exe.ps1 --core    # Pouze core service
.\build_exe.ps1 --tui     # Pouze TUI
```

**Linux/Mac (Bash)**:
```bash
chmod +x build_exe.sh
./build_exe.sh --all
```

Výstupní EXE soubory budou v `dist/`:
- `dist/irswitchd.exe` - Core service
- `dist/irswitch-tui.exe` - TUI klient

### Ruční build (PyInstaller)

Pokud preferuješ ruční build:

**Core service**:
```powershell
pip install pyinstaller
pyinstaller --onefile --name irswitchd --collect-all irswitch src\irswitch\main.py
```

**TUI**:
```powershell
pyinstaller --onefile --name irswitch-tui --collect-all irswitch_tui src\irswitch_tui\main.py
```

### Spuštění EXE

**Core service**:
```powershell
dist\irswitchd.exe --config config\config.ini
```

**TUI**:
```powershell
dist\irswitch-tui.exe --url http://127.0.0.1:17321
```

## Instalace jako Windows Service

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

## Stavový model (návrh)

- connected_iracing: bool
- connected_obs: bool
- autoswitch: bool
- override_scene: str | None
- override_until: datetime | None
- mode: IDLE | GARAGE | RACE | REPLAY | SETTINGS
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

- `IsReplay` → běží replay (REPLAY)
- `SessionState` / `SessionStateNum` → menu/nastavení (SETTINGS)
- `IsOnTrack` / `IsOnTrackCar` → simulace běží a jezdec je na trati (RACE)
- `PlayerCarInGarage` / `IsInGarage` → jezdec je v garáži (GARAGE)

Navržená priorita:

1. `IsReplay` → `REPLAY`
2. `SessionState` = "menu"/"settings" nebo `SessionStateNum` = 0 → `SETTINGS`
3. `IsOnTrack` nebo `IsOnTrackCar` → `RACE`
4. `PlayerCarInGarage` nebo `IsInGarage` → `GARAGE`
5. jinak → `IDLE`

Konkrétní mapování scén řešíte v `[scenes]` v INI souboru.

---

## Další dokumentace

- **[tests.md](tests.md)** - Detailní dokumentace všech testů
- **[STATUS.md](STATUS.md)** - Přehled stavu projektu a co je hotové
- **[CHANGELOG.md](CHANGELOG.md)** - Historie změn projektu

---

## API Dokumentace

Služba vystavuje REST API na `http://127.0.0.1:17321` (nebo podle konfigurace).

### REST Endpointy

#### `GET /status`

Získání aktuálního stavu služby.

**Response** (200 OK):
```json
{
  "connected_iracing": true,
  "connected_obs": true,
  "autoswitch": true,
  "override_scene": null,
  "override_until": null,
  "mode": "RACE",
  "target_scene": "Race",
  "current_scene": "Race",
  "last_switch_ts": 1704110400000,
  "reason": "mode:RACE (debounced)",
  "streaming": true,
  "stream_duration_ms": 3600000
}
```

**Pole v response**:
- `streaming` (boolean) - zda OBS právě streamuje
- `stream_duration_ms` (int | null) - délka streamu v milisekundách (null pokud nestreamuje)

**Error Response** (503 Service Unavailable):
```json
{
  "error": "Service not initialized"
}
```

#### `POST /override`

Dočasné přepnutí scény s časovým limitem.

**Request Body**:
```json
{
  "scene": "Race",
  "seconds": 120
}
```

**Response** (200 OK): Aktualizovaný stav (stejný formát jako `/status`)

**Error Responses**:
- `400 Bad Request` - chybějící nebo neplatný parametr
- `503 Service Unavailable` - služba není inicializovaná

#### `POST /autoswitch/toggle`

Přepnutí autoswitch on/off.

**Response** (200 OK): Aktualizovaný stav s novým `autoswitch` flagem

**Error Response** (503 Service Unavailable):
```json
{
  "error": "Service not initialized"
}
```

### WebSocket Endpoint

#### `WS /ws`

Real-time updates stavu služby.

**Připojení**: `ws://127.0.0.1:17321/ws`

**Zprávy**:
- Po připojení se okamžitě pošle aktuální stav (JSON)
- Při každé změně stavu se pošle aktualizace (JSON)
- Formát je stejný jako `/status` response

**Příklad použití** (JavaScript):
```javascript
const ws = new WebSocket('ws://127.0.0.1:17321/ws');
ws.onmessage = (event) => {
  const status = JSON.parse(event.data);
  console.log('Status update:', status);
};
```

---

## TUI Dokumentace

Textual TUI poskytuje real-time monitoring a ovládání služby.

### Spuštění

```powershell
irswitch-tui --url http://127.0.0.1:17321
```

### Ovládání

#### Keybindings

- `q` - Ukončit TUI
- `t` - Přepnout autoswitch on/off

#### Tlačítka

- **Toggle Autoswitch** - Zapne/vypne automatické přepínání scén
- **Override: Race** - Dočasně přepne na Race scénu (120 sekund)
- **Override: Pits** - Dočasně přepne na Pits scénu (120 sekund)
- **Override: Idle** - Dočasně přepne na Idle scénu (120 sekund)

### Zobrazení

**Status Panel** zobrazuje:
- **iRacing**: Connected/Disconnected
- **OBS**: Connected/Disconnected
- **Mode**: Aktuální iRacing mód (IDLE, GARAGE, RACE, REPLAY)
- **Current Scene**: Aktuální OBS scéna
- **Target Scene**: Cílová scéna (kam se má přepnout)
- **Autoswitch**: ON/OFF
- **Reason**: Důvod aktuálního stavu (např. "mode:RACE (debounced)")

**Control Panel** obsahuje tlačítka pro ovládání.

### Real-time Updates

TUI automaticky aktualizuje zobrazení při změně stavu přes WebSocket.

---

## Troubleshooting

### OBS se nepřipojuje

**Příznaky**: V logu vidíš "Failed to connect to OBS" nebo "OBS: Disconnected" v TUI

**Řešení**:
1. Zkontroluj, že OBS Studio běží
2. Ověř, že WebSocket server je povolený (Tools → WebSocket Server Settings)
3. Zkontroluj port v `config.ini` (výchozí: 4455)
4. Ověř heslo v `config.ini` - musí být stejné jako v OBS
5. Zkontroluj firewall - port 4455 musí být otevřený

### iRacing není detekován

**Příznaky**: "iRacing: Disconnected" v TUI, mode zůstává IDLE

**Řešení**:
1. Zkontroluj, že iRacing běží
2. Spusť iRacing jako administrátor (někdy je potřeba pro shared memory)
3. Zkontroluj, že simulace skutečně běží (ne jen menu)
4. Restartuj službu po spuštění iRacing

### Scény se nepřepínají

**Příznaky**: Mode se mění, ale OBS scéna ne

**Řešení**:
1. Zkontroluj `autoswitch` - pokud je OFF, zapni ho (tlačítko v TUI nebo API)
2. Zkontroluj názvy scén v OBS - musí přesně odpovídat `[scenes]` v config
3. Zkontroluj cooldown - možná je příliš krátký interval mezi změnami
4. Podívej se na `reason` v TUI - může být "cooldown" nebo "debouncing"
5. Zkontroluj logy pro detailní informace

### Služba se nespustí

**Příznaky**: Chyba při spuštění `irswitchd`

**Řešení**:
1. Zkontroluj, že config soubor existuje a je validní
2. Ověř, že všechny závislosti jsou nainstalované: `pip install -e .`
3. Zkontroluj, že port 17321 není obsazený jinou aplikací
4. Podívej se na error message - často obsahuje konkrétní problém

### TUI se nepřipojuje k API

**Příznaky**: "Failed to connect" při spuštění TUI

**Řešení**:
1. Zkontroluj, že core služba běží (`irswitchd`)
2. Ověř URL - musí být `http://127.0.0.1:17321` (nebo podle config)
3. Zkontroluj firewall
4. Zkontroluj logy core služby - mělo by být "API server started"

### Jak zkontrolovat logy

Logy se vypisují na stderr (konzole). Pro uložení do souboru:

```powershell
irswitchd --config config/config.ini 2> irswitch.log
```

Nebo změň `log_level = DEBUG` v config pro více detailů.

**Strukturované logy**:
- `state_changed` - změna stavu
- `scene_switch` - přepnutí scény (s latencí)
- `override_applied` - aplikace override
- `connection_lost` / `connection_restored` - změna připojení
