# Changelog

Všechny významné změny v projektu budou zdokumentovány v tomto souboru.

Formát je založen na [Keep a Changelog](https://keepachangelog.com/cs/1.0.0/),
a tento projekt dodržuje [Semantic Versioning](https://semver.org/lang/cs/).

## [1.1.0] — 2026-08-25

### Features

* race overlay pipeline: telemetry extract, race context, event manager, HTML OBS overlay
* overlay BLE heart-rate (`bleak`) and system info (`psutil` / NVML) as core deps; LHM stays extra
* overlay WebSocket `/ws/overlay`, debug inject, schema-driven `/config` page
* per-component sampling Hz (global default + override, bio push by default)
* mock (`--mock`) and JSONL replay (`--replay`) without iRacing
* overlay theme asset pack (3×37 SVG/PNG) wired into the OBS HUD via snapshot `assets`
* `/overlay/demo` dry-test stage: auto-play HUD sequence without OBS or iRacing

### Security

* config write and debug emit require localhost + CSRF header; OBS password redacted on GET

## [1.0.0](https://github.com/Buchtanen/ir-obs-switcher/compare/v0.7.0...v1.0.0) (2026-08-16)


### ⚠ BREAKING CHANGES

* public surface moves from 0.x to 1.0.0; treat config/API as stable going forward.

### Features

* add dashboard Restart Service (POST /restart) ([66f5275](https://github.com/Buchtanen/ir-obs-switcher/commit/66f52756608abfe8477268131d1439a0a9410490))
* add GR dashboard button to reinit OBS stream info ([7ff1310](https://github.com/Buchtanen/ir-obs-switcher/commit/7ff1310b89647c364b2c4443ad20ae785a5c3494))
* add runtime DEBUG/INFO logging toggle ([4aa067f](https://github.com/Buchtanen/ir-obs-switcher/commit/4aa067f99d23b02c02bd22ff7e46b00f823b86d4))
* apply config hot-reload into main loop and state machine ([dd6c060](https://github.com/Buchtanen/ir-obs-switcher/commit/dd6c060acdb0f39cb7b669c3613e8301f30f597b))
* auto OAuth reauth + startup robustness ([b788f2d](https://github.com/Buchtanen/ir-obs-switcher/commit/b788f2de5c3a83f693f78e3a9b3b47d378e5f4ec))
* auto-reauth YouTube OAuth on revoked token ([03f6f49](https://github.com/Buchtanen/ir-obs-switcher/commit/03f6f49fdcaa23b1c5983278de30650f66aed177))
* config reload response lists live vs restart keys ([458e793](https://github.com/Buchtanen/ir-obs-switcher/commit/458e793372970426b7143def1d2fe080a0a43e18))
* dashboard Restart Service (POST /restart) ([9d6cb72](https://github.com/Buchtanen/ir-obs-switcher/commit/9d6cb720bf9c30a3c2cb346c4a7151c2ec1f250e))
* GR dashboard button to reinit OBS stream info ([dedc494](https://github.com/Buchtanen/ir-obs-switcher/commit/dedc4943e8132577f9128ab8bb07c47767c1dbf3))
* GR dashboard health banner for degraded state ([58d309b](https://github.com/Buchtanen/ir-obs-switcher/commit/58d309bb08c19d5a642ef38df21fa402dc1c33b4))
* real config hot-reload into main loop and state machine ([e7c42e1](https://github.com/Buchtanen/ir-obs-switcher/commit/e7c42e1230aff033d5c3d0f12a307d92e42f3ba1))
* refuse second instance when http_port is already in use ([67fd8d4](https://github.com/Buchtanen/ir-obs-switcher/commit/67fd8d42a14300a1d01c919c56cfaa9df77932d9))
* report live vs restart keys on config reload ([ca8c09f](https://github.com/Buchtanen/ir-obs-switcher/commit/ca8c09fbc2a5ba96500f904d97ee4a675fc9e423))
* runtime debug logging toggle from GR ([ebaf7ae](https://github.com/Buchtanen/ir-obs-switcher/commit/ebaf7ae939e943de4b6bbe5021006f4968dea6dc))
* show errors_total on GR metrics section ([0df9631](https://github.com/Buchtanen/ir-obs-switcher/commit/0df96310e08931a40fe5881d945216f68349fdc7))
* show errors_total on GR metrics section ([fd95941](https://github.com/Buchtanen/ir-obs-switcher/commit/fd959414d43cda4b4bab6499587491314b84b5ae)), closes [#54](https://github.com/Buchtanen/ir-obs-switcher/issues/54)
* show GR health banner when iRacing/OBS offline ([d948580](https://github.com/Buchtanen/ir-obs-switcher/commit/d948580731ca20bd3156e823adb0fe077a363337)), closes [#51](https://github.com/Buchtanen/ir-obs-switcher/issues/51)
* single-instance guard on http_port ([116e740](https://github.com/Buchtanen/ir-obs-switcher/commit/116e740535376338f683f06a3c98a51771721840))


### Bug Fixes

* auto-refresh stream info when OBS broadcast_id changes ([1bac349](https://github.com/Buchtanen/ir-obs-switcher/commit/1bac34918a61b778e35ec70d1e5aa1c47c8c403b))
* ci: run CI on push (no PR duplicates) and scope CodeQL to PRs ([6ab742b](https://github.com/Buchtanen/ir-obs-switcher/commit/6ab742b9fab89296829dd18be4146e64f555293f))
* harden Install.ps1 / Open-Dashboard path resolution ([2d20935](https://github.com/Buchtanen/ir-obs-switcher/commit/2d2093514b09183b789936a64110b2745dcc9a8c))
* harden Install.ps1 / Open-Dashboard path resolution ([4cee4d2](https://github.com/Buchtanen/ir-obs-switcher/commit/4cee4d2d6c47bb66790ad28a5b37f8de790ef2b3))
* harden startup and OBS reconnect path ([36668e3](https://github.com/Buchtanen/ir-obs-switcher/commit/36668e31bed75354c413e3389c3e1ad702f81b3a))
* make POST /restart work with Windows irswitchd shim ([373d9a6](https://github.com/Buchtanen/ir-obs-switcher/commit/373d9a6f477e65c1541b4083f6c6f40c0b2d2cfc))
* make POST /restart work with Windows irswitchd shim ([2000718](https://github.com/Buchtanen/ir-obs-switcher/commit/200071861bf4db8f43beafe13688af7b503fc199))
* rate-limit OBS reconnect ERROR logs ([3b953e7](https://github.com/Buchtanen/ir-obs-switcher/commit/3b953e7e495da686d5b62acf6dfad6f92702fde1))
* rate-limit OBS reconnect final-fail ERROR logs ([979cb94](https://github.com/Buchtanen/ir-obs-switcher/commit/979cb947e4173e3f6b1aa6c717e479e60d3d41c8)), closes [#27](https://github.com/Buchtanen/ir-obs-switcher/issues/27)
* refresh stream info when OBS broadcast_id changes ([60304cd](https://github.com/Buchtanen/ir-obs-switcher/commit/60304cd378ffb9ec46e5c60b163dfd47473ecaff))
* resolve mypy SwitchState|None in stream reinit handler ([acc6789](https://github.com/Buchtanen/ir-obs-switcher/commit/acc6789e567f81b6fc80d57b76ce2308073f0c2d))
* resolve ruff UP042 by using StrEnum for DrivingMode ([2a8dc1c](https://github.com/Buchtanen/ir-obs-switcher/commit/2a8dc1cda1d5ea8861909470a087dccb87fe911a))
* seed runtime config in main_loop to avoid test pollution ([cb1b4f2](https://github.com/Buchtanen/ir-obs-switcher/commit/cb1b4f27fdfc495c62be6fb76dde4b00e0c005a0))
* silence bandit B104 on single-instance probe addresses ([a65d6af](https://github.com/Buchtanen/ir-obs-switcher/commit/a65d6af5b4b855cff37c3cab0c103e9081f6f1a1))


### Documentation

* add Install.ps1 real-dist smoke checklist ([3f8fe5c](https://github.com/Buchtanen/ir-obs-switcher/commit/3f8fe5c2eeca850941d4bbb89e15490e6b35de4d))
* align VERSIONING.md with Release PR model ([70e8531](https://github.com/Buchtanen/ir-obs-switcher/commit/70e8531abe07607db41396d1ce8b456e2dc9c40c))
* align VERSIONING.md with Release PR model ([406106d](https://github.com/Buchtanen/ir-obs-switcher/commit/406106d76df8d7eff5a7eb0b64508d109edf8fe8))
* clarify Windows service stop and uninstall ([acb615d](https://github.com/Buchtanen/ir-obs-switcher/commit/acb615d8e3dc874c123e8fb08eb78f8583c5cfe0))
* clarify Windows service stop and uninstall paths ([da0e9fc](https://github.com/Buchtanen/ir-obs-switcher/commit/da0e9fc25252ceb2264b8fa4998a25e773cb59e4))
* document OAuth Testing-mode refresh token expiry ([333d38f](https://github.com/Buchtanen/ir-obs-switcher/commit/333d38f2a50efda284803f8469e71c7e251b7306))
* document OAuth Testing-mode refresh token expiry ([5d42bd9](https://github.com/Buchtanen/ir-obs-switcher/commit/5d42bd9881efa473fb6dcae854b75b131e741811))
* Install.ps1 real-dist smoke checklist ([5bce7af](https://github.com/Buchtanen/ir-obs-switcher/commit/5bce7af13b01231e2df69515e68e466f65a6f5a5))
* recommend Python 3.11-3.13 for development ([41820ba](https://github.com/Buchtanen/ir-obs-switcher/commit/41820ba4f219bb6c0d6e995aecd51edee04b35dd))
* recommend Python 3.11–3.13 for development ([3dc5d89](https://github.com/Buchtanen/ir-obs-switcher/commit/3dc5d89c576fcaed57a67824d2fb271fb48e2b20))


### Miscellaneous Chores

* bump Actions to Node 24 and release as 1.0.0 ([c796754](https://github.com/Buchtanen/ir-obs-switcher/commit/c7967543c79e53eea55cb04ff30de823e9bc0a74)), closes [#68](https://github.com/Buchtanen/ir-obs-switcher/issues/68)

## [Unreleased]

### Přidáno
- N/A

### Změněno
- N/A

### Opraveno
- N/A

### Odstraněno
- N/A

---

## [0.6.1] - 2026-01-24

### Přidáno
- N/A

### Změněno
- N/A

### Změněno
- **CI konfigurace** - aktualizace pro testování více Python verzí
  - Přidání testování pro Python verze 3.11, 3.12 a 3.13
  - Detailní logy pro test execution napříč různými prostředími
  - Nové test result soubory pro každou Python verzi pro sledování výkonu a výsledků

### Opraveno
- **CI testy** - vylepšená stabilita testů
  - Potlačení barevného výstupu v CI test logech pro lepší čitelnost
  - Úprava sleep duration v metrics testech pro přesnější měření connection duration
  - Odstranění redundantních importů v testech
  - Úprava uptime assertion v metrics testech pro povolení nulové hodnoty
  - Odstranění zastaralých konfigurací z CI

### Odstraněno
- N/A

---

## [0.5.1] - 2026-01-24

### Přidáno
- **Vylepšené stream information retrieval a caching**
  - Cachování detailních stream informací jako dictionary (title, description, scheduled start time, actual start time, concurrent viewers, status, privacy status)
  - Nová metoda `get_cached_stream_info_full` pro získání plných cachovaných stream informací bez API volání
  - Rozšířené zobrazení stream detailů v dashboardech pro lepší viditelnost stream statusu a metrik

### Změněno
- **Stream information handling** - refaktorování v OBS klientu a API
  - Změna návratové hodnoty na tuple (title, description) pro zpětnou kompatibilitu
  - Odstranění dříve cachovaných polí
  - Přidání flagu pro missing API keys v `get_cached_stream_info`
  - Aktualizace server API a dashboardů pro novou strukturu stream dat
  - Vylepšené testy pro stream information retrieval a caching logiku
- **Git hooks** - další vylepšení pro správu verzí a error handling
  - Prevence rekurze během amend operací v `post-commit-hook.sh`
  - Přidání error handling pro staging failures
  - Oprava cest pro version hash storage pro zajištění správné detekce verzí během commitů

### Opraveno
- N/A

### Odstraněno
- N/A

---

## [0.5.0] - 2026-01-24

### Přidáno
- **OAuth 2.0 token management pro YouTube API**
  - Nový modul `oauth.py` pro správu OAuth tokenů včetně funkcí pro získání a obnovu tokenů
  - Integrace OAuth flow do main service pro automatické zpracování YouTube API autentizace
  - Nové API endpointy pro OAuth iniciaci, callback a status
  - Vylepšené logování a error handling pro OAuth procesy
  - Testy pro novou OAuth funkcionalitu

### Změněno
- **Main service** - aktualizace pro OAuth flow a správu tokenů
- **API server** - přidání OAuth endpointů

### Opraveno
- N/A

### Odstraněno
- N/A

---

## [0.4.2] - 2026-01-24

### Přidáno
- N/A

### Změněno
- N/A

### Opraveno
- **pytest asyncio mode** - oprava umístění v `pyproject.toml`
  - Správné nastavení pytest asyncio módu pro async testy

### Odstraněno
- N/A

---

## [0.4.1] - 2026-01-24

### Přidáno
- N/A

### Změněno
- N/A

### Opraveno
- N/A

### Odstraněno
- N/A

---

## [0.4.0] - 2026-01-24

### Přidáno
- **Git hooks enhancements**
  - Vylepšená instalace Git hooks s lepším path handlingem a output messages
  - Nový skript `test_version_bump.ps1` pro testování automatického versioningu
  - Commit message hook pro konzistentní commit zprávy
  - Dokumentace pro testování version bump procesu (`scripts/TEST_VERSION_BUMP.md`)

### Změněno
- **Version bumping script** - vylepšený skript pro správu verzí
  - Kontrola změn před zápisem do `__init__.py` a `pyproject.toml`
  - Varování pokud nedojde k žádným změnám
  - Commit message hook změněn pro správné cesty a kontrolu existence version souborů před stagingem
- **Git hook installation** - aktualizace pro použití bash skriptů
  - Nahrazení Windows batch wrapperu přímou kopií bash hook skriptu
  - Kompatibilita s Git Bash i Git CMD
  - Vylepšené error handling pro chybějící bash hook skripty

### Opraveno
- N/A

### Odstraněno
- N/A

---

## [0.3.0] - 2026-01-24

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
- **State Machine** - kompletní redesign s novými stavy
- **Main Loop** - vylepšené handling loading screenů a state transitions
- **Extractors** - rozšířená extrakce session informací
- **VR Dashboard** - aktualizován pro nové stavy a session info

### Opraveno
- N/A

### Odstraněno
- **SDK Snapshot API endpoint** - odstraněn `/api/snapshot` endpoint
- **Console Alerts** - odstraněn `util/console_alerts.py` (285 řádků)

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
