# Changelog

Všechny významné změny v projektu budou zdokumentovány v tomto souboru.

Formát je založen na [Keep a Changelog](https://keepachangelog.com/cs/1.0.0/),
a tento projekt dodržuje [Semantic Versioning](https://semver.org/lang/cs/).

## [Unreleased]

### Přidáno
- **Stream Cache Optimization**
  - Cache-aware auto-start logika využívající cached hodnot z `stream_selected` eventu
  - Konstanty `STREAM_CACHE_FRESH_MS = 5000` (5 sekund) a `STREAM_CACHE_GRACE_MS = 10000` (10 sekund)
  - Fallback mechanism pro stará cache data (API volání při cache > 5s)
  - Proměnné pro sledování cache freshness: `last_stream_ready_selected`, `last_stream_selection_check_ts`
  - Lepší diagnostika díky logování `data_source` a `cache_age_ms` v event logu
- **Lokalizace (i18n)** - podpora 7 jazyků (CS, EN, DE, FR, SP, PL, HU)
  - Lokalizované texty v HTML dashboardech, event logu, toast notifikacích
  - Konfigurovatelné přes `language` v `config.ini`
  - Automatické použití při startu aplikace
  - Unit testy (`tests/test_i18n.py`)
- **YouTube Data API v3 integrace**
  - Získávání stream title a description z YouTube API
  - Cachování stream info pro snížení API volání
  - Detekce quota exceeded (HTTP 403) s varováním
  - Detekce missing API key s varováním
  - Lokalizované zprávy o kvótě a API klíči
  - Testy pro caching a error handling (`tests/test_obs_client.py`)
- **Kompletní dokumentace**
  - `CONFIG.md` - popis všech konfiguračních parametrů
  - `API.md` - dokumentace REST API a WebSocket endpointů
  - `LOCALIZATION.md` - popis lokalizace a podporovaných jazyků
  - `BUILD_AND_DEPLOY.md` - návod pro vytvoření EXE a nastavení jako služby
  - `YOUTUBE_API_SETUP.md` - postup nastavení YouTube API tokenu v Google Console
  - `VR_SUPPORT.md` - VR support - příslib, záměr a popis problému
- **Session info extrakce testy** - rozšířeno `tests/test_extractors.py`
  - Testy pro `extract_session_type()` (všechny metody extrakce)
  - Testy pro `extract_session_num()` a `extract_total_sessions()`
  - Testy pro priority mezi různými zdroji dat

### Změněno
- **README.md** - reorganizováno, zjednodušeno
  - Odstraněny technické detaily
  - Ponechán pouze Quick Start, Troubleshooting, odkazy na další dokumenty
- **STATUS.md** - aktualizován podle aktuálního stavu projektu
- **TESTING_CHECKLIST.md** - doplněn o nové testy (i18n, YouTube API, session info)
- **Auto-start logika** (`main.py`)
  - Nahrazeni 2× API call (`is_broadcast_ready()`, `get_stream_status()`) za cache-aware logiku
  - Fresh cache (< 5s): použití cached hodnot přímo
  - Stale cache (5-10s): API fallback pro spolehlivost
  - Expired cache (> 10s): forced API call

### Opraveno
- N/A

### Odstraněno
- N/A

---

## [0.3.0] - 2026-01-24

### Přidáno
- **State Machine Redesign**
  - Nové stavy: `CONNECTING`, `LOADING`, `LOBBY` (nahrazuje IDLE pro aktivní hru)
  - Explicitní handling pro QUIT a RESTART módy
  - Vylepšené přechody mezi stavy
- **Loading Screen Detection**
  - Vylepšená detekce loading screenů pomocí process checks
  - Lepší handling i když SDK není připojen
  - Tracking doby loadingu pro automatické spuštění broadcastu
- **Session Management**
  - Extrakce `session_type` (Practice, Qualify, Race, Warmup, Test)
  - Extrakce `session_name` a `session_num`
  - Extrakce `total_sessions` z WeekendInfo
  - Zobrazení session info v GR Dashboard
- **API Enhancements**
  - Endpoint `/reset` pro reset stavu a metrik na CONNECTING
  - Vylepšené error handling v API
- **iRacing Mode Extraction**
  - Priorita LOBBY nad IDLE pro aktivní hru
  - Vylepšené přechody mezi LOBBY a IDLE stavy
- **OBS Connection Logging**
  - Logování úspěšných připojení při startu
  - Event notifikace pro background reconnection

### Změněno
- **State Machine** - kompletní redesign s novými stavy
- **Main Loop** - vylepšené handling loading screenů a state transitions
- **Extractors** - rozšířená extrakce session informací
- **VR Dashboard** - aktualizován pro nové stavy a session info

### Opraveno
- N/A

### Odstraněno
- **SDK Snapshot API endpoint** - odstraněn `/api/snapshot` endpoint
- **Console Alerts** - odstraněn `util/console_alerts.py` (285 řádků)

---

## [0.2.0] - 2026-01-19

### Přidáno
- **Health Check Endpoint** (`GET /health`)
  - Kontrola stavu připojení iRacing a OBS
  - Status: `healthy`, `degraded`, `unhealthy`
  - Timestamp a detailní checks
- **Metrics Endpoint** (`GET /metrics`)
  - Scene switches total a průměrná latence
  - Uptime služby
  - Connection durations (cumulative + current session) pro iRacing a OBS
  - Stream duration (cumulative + current session)
  - Error tracking
  - Current state info
- **Config Hot Reload** (`POST /config/reload`)
  - Dynamické reloadování konfigurace bez restartu služby
  - Validace nového configu před aplikací
  - Error handling pro neplatné configy
- **Graceful Shutdown** (`POST /shutdown`)
  - API-triggered graceful shutdown
  - Nastavení shutdown eventu pro ukončení main loopu
  - Tlačítko v GR Dashboard pro shutdown
- **File Logging s Rotací**
  - Volitelné logování do souboru s rotací
  - Konfigurovatelné: `log_file`, `log_max_bytes`, `log_backup_count`
  - Automatické vytváření log directory
  - UTF-8 encoding
  - Rotace při dosažení max_bytes
  - Omezení počtu backup souborů
- **Event Log System**
  - Thread-safe FIFO event log pro ukládání událostí
  - Používá se pro HTML dashboards (event log sekce)
  - Konfigurovatelná velikost (`dashboard_event_log_size`)
  - Typy eventů: `connection_lost`, `connection_restored`, `scene_switch`, `override_applied`, `loading_started`, `loading_ended`, `stream_started`, `stream_stopped`, atd.
- **Loading Time Tracker**
  - Sledování doby trvání loading screenů iRacing
  - Ukládání historie do JSON souboru (`loading_history.json`)
  - Výpočet průměrné doby loadingu pro automatické spuštění broadcastu
  - Konfigurovatelný výchozí čas (`default_loading_time_seconds`)
- **HTML Dashboards**
  - **GR Dashboard** (`/gr-status`): Velký dashboard s JavaScript auto-update
    - Zobrazuje status připojení, scény, streaming, OBS profil
    - Event log s posledními X událostmi
    - Metrics sekce s cumulative/current session časy
    - Session Info sekce
    - Reload Config a Shutdown tlačítka
    - Cache-busting headers pro zabránění cachování
    - Konfigurovatelné obrázky (background, loga)
  - **VR Dashboard** (`/vr-status`): Minimalistický dashboard pro VR
    - Bílé písmo, větší fonty, oranžový border
    - Bez JavaScriptu (RaceLab VR nepodporuje)
    - Silné cache-control headers
- **Broadcast Management**
  - Automatické spuštění broadcastu během loadingu
    - Konfigurovatelné: `auto_start_broadcast`, `auto_start_at_percent`
    - Spouští se v X% průměrné doby loadingu
    - Kontrola připravenosti broadcastu (`is_broadcast_ready`)
  - Automatické zastavení streamu po QUIT
    - Konfigurovatelné: `auto_stop_stream`, `stop_stream_after_seconds`
    - Zastaví stream X sekund po detekci QUIT módu
- **Metrics Collector**
  - Sběr metrik: scene switches, latence, connection times, stream duration
  - Kumulativní a current session časy pro všechny metriky
  - Error tracking
- **PowerShell Start Script** (`start_app.ps1`)
  - Snadné spuštění aplikace
  - Podporuje `-Config` i `--config` formát
  - Kontrola existence config souboru
  - Kontrola Python a balíčku
  - Automatická instalace v dev módu
- **Testy**
  - 9 testů pro nové API endpointy (`tests/test_api.py`)
  - 13 testů pro MetricsCollector (`tests/test_metrics.py`)
  - 8 testů pro file logging (`tests/test_logging.py`)
  - 9 testů pro Event Log (`tests/test_event_log.py`)
  - 9 testů pro Loading Tracker (`tests/test_loading_tracker.py`)
  - E2E Main Loop testy (`tests/test_main_loop_e2e.py`)

### Změněno
- **Build Process**
  - Silent EXE build (`--noconsole` pro background executable)
  - Automatické kopírování config/ do dist/
  - README.txt v dist/ pro uživatele
- **Config System**
  - Nové parametry: `log_file`, `log_max_bytes`, `log_backup_count`
  - Nové parametry pro broadcast management
  - Nové parametry pro dashboardy
- **OBS Client**
  - Vylepšené metody pro broadcast management
  - `is_broadcast_ready()` pro kontrolu připravenosti
  - `is_stream_selected()` pro kontrolu výběru streamu

### Opraveno
- N/A

### Odstraněno
- **TUI (Textual UI)** - kompletně odstraněn
  - `src/irswitch_tui/` adresář
  - TUI build options z build skriptů
  - TUI dependencies z `pyproject.toml`
  - TUI dokumentace

---

## [0.1.0] - 2026-01-18

### Přidáno
- **Core funkcionalita**
  - iRacing reader s async podporou (`iracing/reader.py`)
  - OBS WebSocket klient s retry logikou (`obs/client.py`)
  - State machine s debounce, cooldown a override logikou (`logic/state_machine.py`)
  - Policy pro mapování módu na scény (`logic/policy.py`)
  - Main loop pro koordinaci všech komponent (`main.py`)
- **REST API**
  - `GET /status` - získání aktuálního stavu služby
  - `POST /override` - dočasné přepnutí scény s časovým limitem
  - `POST /autoswitch/toggle` - přepnutí autoswitch on/off
  - `POST /restart-mode/reset` - reset RESTART módu
- **WebSocket API**
  - `WS /ws` - real-time updates stavu služby
- **Konfigurační systém**
  - INI soubor (`config/config.example.ini`)
  - `AppConfig` třída pro načítání a validaci
- **Strukturované logování**
  - Barevný výstup v konzoli
  - Strukturované logy s kontextem
- **Build & Scripts**
  - `build_exe.ps1` / `build_exe.sh` - skripty pro vytváření EXE souborů
  - `run_tests.ps1` / `run_tests.sh` - skripty pro spouštění testů
- **CI/CD**
  - GitHub Actions workflow pro automatické testy
- **Dokumentace**
  - `README.md` - základní dokumentace projektu
  - `tests.md` - dokumentace testů
  - `STATUS.md` - přehled stavu projektu
  - `CHANGELOG.md` - historie změn
- **Testy**
  - Unit testy pro všechny komponenty (43+ testů)
    - Extractors (4 testy)
    - Policy (1 test)
    - iRacing Reader (8 testů)
    - OBS Client (11 testů)
    - State Machine (11 testů)
    - API Server (8 testů)
    - Main Service (3 testy)

### Změněno
- N/A (první verze)

### Opraveno
- N/A (první verze)

### Odstraněno
- N/A (první verze)

---

## Typy změn

- **Přidáno** - nové funkce
- **Změněno** - změny v existujících funkcích
- **Zastaralé** - funkce, které budou brzy odstraněny
- **Odstraněno** - odstraněné funkce
- **Opraveno** - opravy bugů
- **Bezpečnost** - opravy bezpečnostních problémů
