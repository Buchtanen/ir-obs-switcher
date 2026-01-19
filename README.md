# iRacing → OBS Auto Scene Switcher (Python)

**Status projektu**: Viz [STATUS.md](STATUS.md) pro přehled co je hotové a co následuje.

Tento repozitář obsahuje službu, která:

- čte stav iRacingu přes `pyirsdk` (shared memory)
- automaticky přepíná OBS scény přes `obs-websocket` v5
- vystavuje lokální HTTP + WebSocket API

## Obsah

- [Cíle](#cíle)
  - [Jak to pracuje](#jak-to-pracuje)
- [Technologie](#technologie)
- [Struktura projektu](#struktura-projektu)
- [Quick Start](#quick-start)
  - [Instalace](#1-instalace)
  - [Konfigurace](#2-konfigurace)
  - [Nastavení OBS](#3-nastavení-obs)
  - [Spuštění služby](#4-spuštění-služby)
  - [Testování](#5-testování)
  - [HTML Dashboards](#6-html-dashboards-volitelné)
- [Konfigurace (INI)](#konfigurace-ini)
  - [Sekce konfigurace](#sekce-konfigurace)
- [Build a distribuce](#build-a-distribuce)
  - [Vytvoření EXE souboru](#vytvoření-exe-souboru)
  - [Výstup build procesu](#výstup-build-procesu)
  - [Instalace a provoz](#instalace-a-provoz)
  - [Cesty v konfiguraci](#cesty-v-konfiguraci)
- [Testy](#testy)
- [API Dokumentace](#api-dokumentace)
  - [REST Endpointy](#rest-endpointy)
  - [WebSocket Endpoint](#websocket-endpoint)
- [Troubleshooting](#troubleshooting)
- [Nové funkce](#nové-funkce-leden-2026)
- [Další dokumentace](#další-dokumentace)

## Cíle

- **Automatické ovládání streamu** - spuštění a zastavení OBS streamu podle stavu iRacing
- spolehlivé přepínání scén bez flappingu (debounce + cooldown)
- override s časovým limitem z konfigurace
- bezpečné chování při výpadku iRacing nebo OBS (čekání v loopu)

### Jak to pracuje

Aplikace automatizuje celý workflow streamování iRacing:

1. **Detekce stavu iRacing**
   - Sleduje stav iRacing přes shared memory (pyirsdk)
   - Detekuje módy: IDLE (menu), GARAGE, RACE, REPLAY, QUIT
   - Detekuje loading screeny a měří jejich délku

2. **Automatické přepínání OBS scén**
   - Podle módu iRacing automaticky přepíná OBS scény
   - Mapování: IDLE → Idle scéna, GARAGE → Pits scéna, RACE → Race scéna, atd.
   - Debounce a cooldown zajišťují stabilní přepínání bez flappingu

3. **Automatické spuštění streamu** (volitelné)
   - Během loadingu iRacing sleduje průběh
   - V X% průměrné doby loadingu automaticky spustí OBS broadcast
   - Používá historii loading časů pro přesné načasování
   - Kontroluje, zda je broadcast připravený před spuštěním

4. **Automatické zastavení streamu** (volitelné)
   - Po ukončení iRacing (QUIT mód) počká X sekund
   - Automaticky zastaví OBS stream
   - Dává čas na ukončení hry před zastavením streamu

5. **Grace period při připojení**
   - Po připojení iRacing čeká na IDLE po non-IDLE módu (inspection)
   - Zabraňuje přepnutí scény během loading screenu
   - Aplikuje správnou scénu až po dokončení inspection

6. **Background připojení**
   - Aplikace startuje i když OBS neběží
   - Na pozadí se opakovaně pokouší připojit k OBS
   - Nezablokuje start aplikace při výpadku OBS

7. **Monitoring a metriky**
   - Sleduje uptime, connection times, scene switches
   - Kumulativní a current session časy pro všechny metriky
   - Event log pro sledování všech událostí
   - Web dashboard pro real-time monitoring

**Výsledek**: Kompletně automatizovaný stream - stačí spustit aplikaci a iRacing, vše ostatní se děje automaticky.

## Technologie

Core:
- Python 3.11+
- pyirsdk
- obsws-python
- aiohttp
- pydantic
- logging

Testy:
- pytest
- pytest-asyncio
- freezegun

## Struktura projektu

```
iracing-obs-switcher/
  README.md
  STATUS.md
  CHANGELOG.md
  tests.md
  RACELAB_VR_SETUP.md
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
        dashboards.py
        event_log.py
      util/
        __init__.py
        logging.py
        clock.py
        hotkeys.py
        loading_tracker.py
        notifications.py
  tests/
    test_*.py
  start_app.ps1
  build_exe.ps1
  build_exe.sh
  loading_history.json  # Generuje se automaticky
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

**PowerShell skript (doporučeno)**:
```powershell
.\start_app.ps1 --config config\config.ini
```

**Nebo přímo**:
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

**Poznámka**: Pokud OBS neběží, aplikace se spustí i tak - připojení k OBS proběhne na pozadí.

### 5. Testování

1. Spusť iRacing
2. V logu nebo HTML dashboardech sleduj změny módu (IDLE → GARAGE → RACE)
3. OBS by měl automaticky přepínat scény podle módu

### 6. HTML Dashboards (volitelné)

Aplikace poskytuje dva HTML dashboardy:

**GR Dashboard** (velký monitor):
- URL: `http://127.0.0.1:17321/gr-status`
- JavaScript auto-update
- Zobrazuje status, event log, streaming info, metrics
- Konfigurovatelné obrázky a loga
- **Screenshot**: [GR Dashboard](img/rg-status-screen.png) (otevře se v novém tabu)

**VR Dashboard** (pro VR):
- URL: `http://127.0.0.1:17321/vr-status`
- Minimalistický design, bílé písmo, větší fonty
- Bez JavaScriptu (pro RaceLab VR)
- ⚠️ **Omezení**: RaceLab VR widgety nepodporují auto-refresh - widget se neaktualizuje automaticky
- Viz [RACELAB_VR_SETUP.md](RACELAB_VR_SETUP.md) pro detaily a alternativy

## Konfigurace (INI)

Viz `config/config.example.ini` pro kompletní příklad.

### Sekce konfigurace

#### `[app]` - HTTP server nastavení

- **`http_host`** (výchozí: `127.0.0.1`)
  - IP adresa, na které běží HTTP server
  - **Kdy použít**: Změň na `0.0.0.0` pokud chceš přístup z jiných počítačů v síti
  - **Příklad**: `http_host = 0.0.0.0` pro přístup z jiných zařízení

- **`http_port`** (povinné)
  - Port pro HTTP server a WebSocket
  - **Kdy použít**: Změň pokud je port obsazený jinou aplikací
  - **Příklad**: `http_port = 17321`

- **`log_level`** (výchozí: `INFO`)
  - Úroveň logování: `DEBUG`, `INFO`, `WARNING`, `ERROR`
  - **Kdy použít**: 
    - `DEBUG` - pro ladění problémů (zobrazuje všechny detaily)
    - `INFO` - normální provoz (doporučeno)
    - `WARNING` - jen varování a chyby
  - **Příklad**: `log_level = DEBUG` pro detailní logy

- **`notifications_enabled`** (výchozí: `true`)
  - Zapne/vypne Windows notifikace při změně připojení
  - **Kdy použít**: Nastav na `false` pokud nechceš notifikace
  - **Příklad**: `notifications_enabled = false`

#### `[iracing]` - iRacing detekce

- **`poll_hz`** (povinné)
  - Frekvence čtení dat z iRacing SDK (polling rate)
  - **Kdy použít**: 
    - Nižší hodnoty (3-5 Hz) = menší zátěž CPU, pomalejší reakce
    - Vyšší hodnoty (10-20 Hz) = rychlejší reakce, větší zátěž
  - **Doporučení**: `5` Hz je dobrý kompromis (200ms interval)
  - **Příklad**: `poll_hz = 5`

- **`quit_stall_seconds`** (výchozí: `0.4`)
  - Práh pro detekci ukončení iRacing (v sekundách)
  - **Kdy použít**: 
    - Pokud se QUIT detekuje příliš brzy → zvyš hodnotu (např. `0.6`)
    - Pokud se QUIT nedetekuje → sniž hodnotu (např. `0.3`)
  - **Jak to funguje**: Aplikace detekuje, když `SessionTime` přestane měnit hodnotu
  - **Příklad**: `quit_stall_seconds = 0.4`

#### `[obs]` - OBS WebSocket připojení

- **`ws_url`** (povinné)
  - WebSocket URL OBS serveru
  - **Kdy použít**: Změň pokud OBS běží na jiném počítači nebo portu
  - **Příklad**: `ws_url = ws://127.0.0.1:4455` (lokální), `ws://192.168.1.100:4455` (síť)

- **`password`** (povinné)
  - Heslo pro OBS WebSocket server
  - **Kdy použít**: Musí odpovídat heslu nastavenému v OBS (Tools → WebSocket Server Settings)
  - **Příklad**: `password = tvé_obs_heslo`

- **`required_profile`** (volitelné)
  - Název OBS profilu, který musí být aktivní
  - **Kdy použít**: Pokud máš více OBS profilů a chceš, aby switcher fungoval jen s konkrétním
  - **Příklad**: `required_profile = RacingProfile`

#### `[switching]` - Logika přepínání scén

- **`autoswitch_default`** (povinné)
  - Výchozí stav automatického přepínání při startu
  - **Kdy použít**: 
    - `true` - automatické přepínání zapnuté hned po startu
    - `false` - automatické přepínání vypnuté (musíš ho zapnout ručně přes API)
  - **Příklad**: `autoswitch_default = true`

- **`debounce_ms`** (povinné)
  - Čekací doba před přepnutím scény po změně módu (v milisekundách)
  - **Kdy použít**: 
    - Vyšší hodnoty (1000-2000ms) = stabilnější, ale pomalejší reakce
    - Nižší hodnoty (500-900ms) = rychlejší reakce, ale může dojít k flappingu
  - **Jak to funguje**: Po změně módu čeká X ms, než skutečně přepne scénu (zabraňuje flappingu)
  - **Doporučení**: `900` ms je dobrý kompromis
  - **Příklad**: `debounce_ms = 900`

- **`cooldown_ms`** (povinné)
  - Minimální interval mezi přepnutími scén (v milisekundách)
  - **Kdy použít**: 
    - Vyšší hodnoty (1500-2000ms) = zabraňuje příliš rychlému přepínání
    - Nižší hodnoty (500-1000ms) = umožňuje rychlejší přepínání
  - **Jak to funguje**: Po přepnutí scény musí uplynout X ms před dalším přepnutím
  - **Doporučení**: `1000` ms (1 sekunda)
  - **Příklad**: `cooldown_ms = 1000`

- **`override_seconds`** (povinné)
  - Délka trvání manuálního override scény (v sekundách)
  - **Kdy použít**: 
    - Vyšší hodnoty (180-300s) = override trvá déle
    - Nižší hodnoty (60-120s) = override trvá kratší dobu
  - **Jak to funguje**: Když použiješ override přes API, trvá X sekund než se vrátí automatické přepínání
  - **Doporučení**: `120` sekund (2 minuty)
  - **Příklad**: `override_seconds = 120`

- **`safe_scene`** (povinné)
  - Název scény, která se použije když není iRacing připojen nebo při chybách
  - **Kdy použít**: Nastav na scénu, která je bezpečná pro zobrazení (např. menu, idle scéna)
  - **Příklad**: `safe_scene = Idle`

- **`auto_start_broadcast`** (výchozí: `false`)
  - Automatické spuštění OBS broadcastu během loadingu iRacing
  - **Kdy použít**: 
    - `true` - pokud chceš automaticky spouštět stream během loadingu
    - `false` - pokud chceš spouštět stream ručně
  - **Jak to funguje**: Spustí broadcast v X% průměrné doby loadingu (viz `auto_start_at_percent`)
  - **Příklad**: `auto_start_broadcast = true`

- **`auto_start_at_percent`** (výchozí: `50`)
  - Procento průměrné doby loadingu, kdy se spustí broadcast (0-100)
  - **Kdy použít**: 
    - `30-50` - spustí se brzy během loadingu
    - `70-90` - spustí se později, téměř na konci loadingu
  - **Jak to funguje**: Pokud průměrný loading trvá 12s a nastavíš `50`, broadcast se spustí po 6s
  - **Příklad**: `auto_start_at_percent = 50`

- **`default_loading_time_seconds`** (výchozí: `12.0`)
  - Výchozí doba loadingu, pokud nemáš historii (použije se při prvním spuštění)
  - **Kdy použít**: Nastav podle typické doby loadingu na tvém systému
  - **Jak to funguje**: Aplikace sleduje historii loadingu a počítá průměr, ale při prvním spuštění použije tuto hodnotu
  - **Příklad**: `default_loading_time_seconds = 12.0`

- **`auto_stop_stream`** (výchozí: `false`)
  - Automatické zastavení OBS streamu po ukončení iRacing (QUIT mód)
  - **Kdy použít**: 
    - `true` - pokud chceš automaticky zastavit stream po ukončení hry
    - `false` - pokud chceš zastavit stream ručně
  - **Příklad**: `auto_stop_stream = true`

- **`stop_stream_after_seconds`** (výchozí: `30`)
  - Po kolika sekundách po QUIT se zastaví stream
  - **Kdy použít**: 
    - Nižší hodnoty (10-20s) - zastaví se rychle po ukončení
    - Vyšší hodnoty (30-60s) - zastaví se později (dává čas na ukončení hry)
  - **Příklad**: `stop_stream_after_seconds = 30`

#### `[hotkeys]` - Globální hotkey (volitelné)

- **`restart_hotkey`** (volitelné)
  - Globální klávesová zkratka pro RESTART mód
  - **Kdy použít**: Pokud chceš mít možnost přepnout na RESTART scénu při ukončení iRacing (např. pro VR restarty)
  - **Jak to funguje**: Drž tuto kombinaci kláves když ukončuješ iRacing → aplikace detekuje QUIT a přepne na RESTART scénu místo QUIT
  - **Formát**: `modifier+modifier+key` (např. `ctrl+shift+f7`, `alt+r`)
  - **Příklad**: `restart_hotkey = ctrl+shift+f7`

#### `[scenes]` - Mapování módu na OBS scény

- **`IDLE`** (povinné)
  - Název OBS scény pro IDLE mód (menu/lobby)
  - **Kdy nastává**: Když je iRacing v menu nebo lobby
  - **Příklad**: `IDLE = Idle`

- **`GARAGE`** (povinné)
  - Název OBS scény pro GARAGE mód (garáž ve hře)
  - **Kdy nastává**: Když je hráč v garáži během session
  - **Příklad**: `GARAGE = Pits`

- **`RACE`** (povinné)
  - Název OBS scény pro RACE mód (na trati)
  - **Kdy nastává**: Když je hráč na trati v autě
  - **Příklad**: `RACE = Race`

- **`REPLAY`** (povinné)
  - Název OBS scény pro REPLAY mód (přehrávání)
  - **Kdy nastává**: Když běží replay v iRacing
  - **Příklad**: `REPLAY = Replay`

- **`QUIT`** (povinné)
  - Název OBS scény pro QUIT mód (ukončení hry)
  - **Kdy nastává**: Když je iRacing ukončen (detekce přes `quit_stall_seconds`)
  - **Příklad**: `QUIT = End`

- **`RESTART`** (volitelné)
  - Název OBS scény pro RESTART mód
  - **Kdy nastává**: Když je detekován QUIT a zároveň je držen `restart_hotkey`
  - **Kdy použít**: Pouze pokud používáš `restart_hotkey`
  - **Příklad**: `RESTART = Restart`

**Důležité**: Názvy scén musí přesně odpovídat názvům scén v OBS (case-sensitive)!

#### `[dashboards]` - HTML dashboardy (volitelné)

- **`dashboard_update_fps`** (výchozí: `2`)
  - Frekvence aktualizace HTML dashboardů (FPS)
  - **Kdy použít**: 
    - Nižší hodnoty (1-2 FPS) = menší zátěž, pomalejší aktualizace
    - Vyšší hodnoty (5-10 FPS) = rychlejší aktualizace, větší zátěž
  - **Doporučení**: `2` FPS (500ms interval) je dostatečné
  - **Příklad**: `dashboard_update_fps = 2`

- **`dashboard_event_log_size`** (výchozí: `50`)
  - Počet posledních eventů zobrazených v GR dashboardu
  - **Kdy použít**: 
    - Vyšší hodnoty (100-200) = více historie, ale větší paměť
    - Nižší hodnoty (20-50) = méně historie, menší paměť
  - **Příklad**: `dashboard_event_log_size = 50`

- **`log_file`** (volitelné)
  - Cesta k log souboru (relativní k working directory)
  - **Kdy použít**: Pokud chceš logy do souboru místo jen na konzoli
  - **Příklad**: `log_file = logs/irswitch.log` (relativní) nebo `log_file = C:/irswitch/logs/irswitch.log` (absolutní)

- **`log_max_bytes`** (výchozí: `10485760` = 10 MB)
  - Maximální velikost log souboru před rotací
  - **Příklad**: `log_max_bytes = 10485760`

- **`log_backup_count`** (výchozí: `5`)
  - Počet backup log souborů k uchování
  - **Příklad**: `log_backup_count = 5`

- **`dashboard_gr_background_image`** (volitelné)
  - Cesta k obrázku pozadí pro GR dashboard (`/gr-status`)
  - **Kdy použít**: Pokud chceš vlastní pozadí místo černé
  - **Poznámka**: Cesta je relativní k working directory
  - **Příklad**: `dashboard_gr_background_image = images/background.png` (relativní) nebo `dashboard_gr_background_image = C:/path/to/background.png` (absolutní)

- **`dashboard_gr_logo_obs`** (volitelné)
  - Cesta k OBS logu pro GR dashboard (relativní k working directory)
  - **Příklad**: `dashboard_gr_logo_obs = images/obs_logo.png`

- **`dashboard_gr_logo_iracing`** (volitelné)
  - Cesta k iRacing logu pro GR dashboard (relativní k working directory)
  - **Příklad**: `dashboard_gr_logo_iracing = images/iracing_logo.png`

- **`dashboard_gr_logo_app`** (volitelné)
  - Cesta k logu aplikace pro GR dashboard (relativní k working directory)
  - **Příklad**: `dashboard_gr_logo_app = images/app_logo.png`

- **`dashboard_vr_icons_path`** (volitelné)
  - Cesta k adresáři s ikonami pro VR dashboard (`/vr-status`) (relativní k working directory)
  - **Příklad**: `dashboard_vr_icons_path = icons/` (relativní) nebo `dashboard_vr_icons_path = C:/path/to/vr_icons/` (absolutní)

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

## Testy

```powershell
pip install -e .[test]
pytest
```

**Dokumentace testů**: Detailní popis všech testů, co testují a proč, najdeš v [tests.md](tests.md).

**Test coverage**: Projekt obsahuje 50+ unit testů pokrývajících všechny klíčové komponenty včetně E2E testů hlavní smyčky.

## Build a distribuce

### Vytvoření EXE souboru

Aplikace se builduje jako **silent background proces** (bez konzole) pomocí PyInstaller.

**Windows (PowerShell)**:
```powershell
.\build_exe.ps1 --all
# Nebo pouze core service:
.\build_exe.ps1 --core
```

**Linux/Mac (Bash)**:
```bash
chmod +x build_exe.sh
./build_exe.sh --all
```

### Výstup build procesu

Po buildu najdeš v `dist/` adresáři kompletní distribuci:

```
dist/
  ├── irswitchd.exe          # Hlavní aplikace (silent, bez konzole)
  ├── config/
  │   ├── config.example.ini  # Příklad konfigurace
  │   └── config.ini         # Tvá konfigurace (uprav si)
  └── README.txt             # Instrukce k použití
```

**Důležité**: Celý `dist/` adresář je samostatná distribuce - můžeš ho zkopírovat kamkoliv a spustit.

### Instalace a provoz

#### 1. Příprava konfigurace

1. Zkopíruj `dist/config/config.example.ini` na `dist/config/config.ini`
2. Uprav `config.ini` podle svých potřeb:
   - Nastav OBS WebSocket heslo
   - Uprav názvy scén podle OBS
   - Nastav cesty k obrázkům (pokud používáš)

#### 2. Spuštění aplikace

**Z adresáře `dist/`**:
```powershell
cd dist
.\irswitchd.exe --config config\config.ini
```

Aplikace běží **silent na pozadí** (bez konzole). Pro zastavení:
- Použij GR Dashboard (`http://127.0.0.1:17321/gr-status`) a klikni "Shutdown Service"
- Nebo použij Task Manager a ukonči proces `irswitchd.exe`

#### 3. Logování

- **Výchozí**: Logy jdou na konzoli (stderr) - pokud spouštíš z PowerShell, uvidíš je
- **Do souboru**: Nastav v `config.ini`:
  ```ini
  [app]
  log_file = logs/irswitch.log
  log_max_bytes = 10485760  # 10 MB
  log_backup_count = 5      # Počet backup souborů
  ```
  Log soubory se automaticky rotují při dosažení maximální velikosti.

#### 4. Automatické spuštění při startu systému

**Možnost A: Windows Task Scheduler** (doporučeno pro EXE)

1. Otevři Task Scheduler (`taskschd.msc`)
2. Vytvoř nový task:
   - **Trigger**: "At startup"
   - **Action**: Start a program
   - **Program**: `C:\path\to\dist\irswitchd.exe`
   - **Arguments**: `--config C:\path\to\dist\config\config.ini`
   - **Start in**: `C:\path\to\dist`
   - **Run whether user is logged on or not**: ✓ (volitelné)

**Možnost B: Windows Service (NSSM)**

Pokud preferuješ Windows Service, použij [NSSM](https://nssm.cc/):

```powershell
# Stáhni a rozbal NSSM do C:\nssm\
nssm install irswitchd
```

V GUI nastav:
- **Path**: `C:\path\to\dist\irswitchd.exe`
- **Arguments**: `--config C:\path\to\dist\config\config.ini`
- **Startup directory**: `C:\path\to\dist`
- **Startup**: Automatic

Spuštění služby:
```powershell
nssm start irswitchd
```

Zastavení služby:
```powershell
nssm stop irswitchd
```

Odinstalace služby:
```powershell
nssm remove irswitchd confirm
```

### Cesty v konfiguraci

**Důležité**: Všechny cesty v `config.ini` jsou **relativní vzhledem k working directory** (adresáři, ze kterého spouštíš aplikaci).

**Příklady**:
- Pokud spouštíš z `C:\irswitch\dist\`:
  ```ini
  log_file = logs/irswitch.log              # → C:\irswitch\dist\logs\irswitch.log
  dashboard_gr_background_image = bg.png    # → C:\irswitch\dist\bg.png
  dashboard_vr_icons_path = icons/          # → C:\irswitch\dist\icons\
  ```

- Pokud chceš absolutní cesty, použij plnou cestu:
  ```ini
  log_file = C:/irswitch/logs/irswitch.log
  dashboard_gr_background_image = C:/irswitch/bg.png
  ```

**Tip**: Pro distribuci doporučujeme používat relativní cesty - aplikace pak funguje bez úprav, i když ji přesuneš do jiného adresáře.

### Ruční build (PyInstaller)

Pokud preferuješ ruční build:

```powershell
pip install pyinstaller
pyinstaller --onefile `
    --name irswitchd `
    --noconsole `
    --collect-all irswitch `
    --distpath dist `
    --workpath build `
    --clean `
    src\irswitch\main.py
```

**Poznámka**: `--noconsole` vytváří silent EXE bez konzole (doporučeno pro background proces).

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
- **[RACELAB_VR_SETUP.md](RACELAB_VR_SETUP.md)** - Návod pro nastavení VR dashboardu v RaceLab VR

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

## Test Widget

Pro testování JavaScript funkcionality v běžném webovém prohlížeči:

**URL**: `http://127.0.0.1:17321/test`

Widget zobrazí "JS JEDE" pokud JavaScript funguje správně.

**Poznámka**: Tento widget **není určen pro RaceLab VR**, protože RaceLab VR widgety nepodporují JavaScript ani auto-refresh. VR dashboard (`/vr-status`) je dostupný, ale v RaceLab VR se neaktualizuje automaticky - viz [RACELAB_VR_SETUP.md](RACELAB_VR_SETUP.md) pro detaily.

---

## Troubleshooting

### OBS se nepřipojuje

**Příznaky**: V logu vidíš "Failed to connect to OBS" nebo "OBS: Disconnected"

**Řešení**:
1. Zkontroluj, že OBS Studio běží
2. Ověř, že WebSocket server je povolený (Tools → WebSocket Server Settings)
3. Zkontroluj port v `config.ini` (výchozí: 4455)
4. Ověř heslo v `config.ini` - musí být stejné jako v OBS
5. Zkontroluj firewall - port 4455 musí být otevřený

### iRacing není detekován

**Příznaky**: "iRacing: Disconnected" v logu, mode zůstává IDLE

**Řešení**:
1. Zkontroluj, že iRacing běží
2. Spusť iRacing jako administrátor (někdy je potřeba pro shared memory)
3. Zkontroluj, že simulace skutečně běží (ne jen menu)
4. Restartuj službu po spuštění iRacing

### Scény se nepřepínají

**Příznaky**: Mode se mění, ale OBS scéna ne

**Řešení**:
1. Zkontroluj `autoswitch` - pokud je OFF, zapni ho (přes API nebo GR dashboard)
2. Zkontroluj názvy scén v OBS - musí přesně odpovídat `[scenes]` v config
3. Zkontroluj cooldown - možná je příliš krátký interval mezi změnami
4. Podívej se na `reason` v logu nebo GR dashboardu - může být "cooldown" nebo "debouncing"
5. Zkontroluj logy pro detailní informace

### Služba se nespustí

**Příznaky**: Chyba při spuštění `irswitchd`

**Řešení**:
1. Zkontroluj, že config soubor existuje a je validní
2. Ověř, že všechny závislosti jsou nainstalované: `pip install -e .`
3. Zkontroluj, že port 17321 není obsazený jinou aplikací
4. Podívej se na error message - často obsahuje konkrétní problém


### Jak zkontrolovat logy

**Výchozí chování**:
- Logy se vypisují na stderr (konzole)
- Pokud spouštíš z PowerShell, uvidíš je v konzoli

**Logování do souboru**:
1. Nastav v `config.ini`:
   ```ini
   [app]
   log_file = logs/irswitch.log
   log_max_bytes = 10485760  # 10 MB
   log_backup_count = 5
   ```
2. Log soubory se automaticky rotují při dosažení maximální velikosti
3. Backup soubory: `irswitch.log.1`, `irswitch.log.2`, atd.

**Poznámka**: Cesty k log souborům jsou relativní k working directory (adresáři, ze kterého spouštíš aplikaci).

**Pro více detailů**: Změň `log_level = DEBUG` v config.

**Strukturované logy**:
- `state_changed` - změna stavu
- `scene_switch` - přepnutí scény (s latencí)
- `override_applied` - aplikace override
- `connection_lost` / `connection_restored` - změna připojení
- `loading_started` / `loading_ended` - začátek/konec loadingu
- `stream_started` / `stream_stopped` - spuštění/zastavení streamu

## Nové funkce (leden 2026)

### Loading Time Tracker
- Automatické sledování doby trvání loading screenů iRacing
- Historie se ukládá do `loading_history.json`
- Průměrná doba se používá pro automatické spuštění broadcastu
- Konfigurovatelný výchozí čas pro první spuštění

### Event Log System
- Thread-safe event log pro ukládání událostí
- Zobrazuje se v GR dashboardu
- Konfigurovatelná velikost (výchozí 50 eventů)
- Typy: connection, scene_switch, loading, stream, override, atd.

### HTML Dashboards
- **GR Dashboard**: Velký dashboard s JavaScript auto-update, event log, streaming status, metrics
  - Screenshot: [GR Dashboard](img/rg-status-screen.png)
- **VR Dashboard**: Minimalistický dashboard pro VR (⚠️ RaceLab VR nepodporuje auto-refresh)
- Konfigurovatelné obrázky a loga
- Cache-busting pro zabránění cachování

### Broadcast Management
- Automatické spuštění broadcastu během loadingu (konfigurovatelné)
- Automatické zastavení streamu po QUIT (konfigurovatelné)
- Kontrola připravenosti broadcastu před spuštěním

### Session Information
- Detekce typu session během loadingu (Practice, Qualify, Race)
- Ukládání do event logu
- Zobrazení v dashboardech

### Background OBS Connection
- Non-blocking připojení k OBS při startu
- Aplikace startuje i když OBS neběží
- Background task pro opakované pokusy o připojení

### Notifications Control
- Globální zapnutí/vypnutí notifikací přes config
- Respektuje se v `show_toast()` funkci