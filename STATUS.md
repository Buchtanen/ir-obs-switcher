# Status projektu - Co je hotové a co následuje

## ✅ Hotové (100% implementováno)

### Core funkcionalita
- ✅ **Konfigurace** (`config.py`) - načítání INI, validace, hot reload
- ✅ **iRacing Reader** (`iracing/reader.py`) - async wrapper pro pyirsdk
- ✅ **Extractors** (`iracing/extractors.py`) - extrakce módu s prioritou
- ✅ **OBS Client** (`obs/client.py`) - async WebSocket klient s retry logikou
  - ✅ YouTube Data API v3 integrace pro získávání stream title/description
  - ✅ Cachování stream info pro snížení API volání
  - ✅ YouTube API quota handling (403 error detection)
  - ✅ YouTube API key missing detection
- ✅ **State Machine** (`logic/state_machine.py`) - debounce, cooldown, override
- ✅ **Policy** (`logic/policy.py`) - mapování módu na scény
- ✅ **API Server** (`server/api.py`) - REST + WebSocket endpointy
  - ✅ Health check endpoint (`GET /health`)
  - ✅ Metrics endpoint (`GET /metrics`)
  - ✅ Config reload endpoint (`POST /config/reload`)
  - ✅ Shutdown endpoint (`POST /shutdown`)
- ✅ **Main Loop** (`main.py`) - koordinace všech komponent
- ✅ **Metrics Collector** (`server/metrics.py`) - sběr metrik (scene switches, latence, connection times, stream duration)
- ✅ **Internationalization** (`i18n.py`) - lokalizace podporující 7 jazyků (CS, EN, DE, FR, SP, PL, HU)
- ✅ **Utilities** (`util/`) - clock, logging (s file rotation)

### Testy
- ✅ **79+ unit testů** - všechny prošly
  - Extractors (4 testy)
  - Policy (1 test)
  - iRacing Reader (8 testů)
  - OBS Client (11 testů)
  - State Machine (11 testů)
  - API Server (15 testů) - včetně health, metrics, config/reload, shutdown
  - Main Service (3 testy)
  - Loading Tracker (9 testů)
  - Event Log (9 testů)
  - E2E Main Loop (7 testů)
  - Metrics Collector (13 testů) - nové
  - Logging (8 testů) - nové
- ✅ **0 warnings** - vše opraveno
- ✅ **Dokumentace testů** (`tests.md`) - detailní popis všech testů
- ✅ **Testovací checklist** (`TESTING_CHECKLIST.md`) - přehled testovacího pokrytí

### Dokumentace
- ✅ **README.md** - základní dokumentace projektu (reorganizováno - pouze Quick Start, Troubleshooting, odkazy na další dokumenty)
- ✅ **CONFIG.md** - kompletní popis všech konfiguračních parametrů
- ✅ **API.md** - dokumentace REST API a WebSocket endpointů
- ✅ **LOCALIZATION.md** - popis lokalizace a podporovaných jazyků
- ✅ **BUILD_AND_DEPLOY.md** - návod pro vytvoření EXE a nastavení jako služby
- ✅ **YOUTUBE_API_SETUP.md** - postup nastavení YouTube API tokenu v Google Console
- ✅ **VR_SUPPORT.md** - VR support - příslib, záměr a popis problému
- ✅ **RACELAB_VR_SETUP.md** - návod pro nastavení VR dashboardu v RaceLab VR
- ✅ **tests.md** - dokumentace testů
- ✅ **config.example.ini** - příklad konfigurace
- ✅ **CHANGELOG.md** - historie změn projektu

### Build & Scripts
- ✅ **pyproject.toml** - konfigurace projektu
- ✅ **run_tests.ps1** / **run_tests.sh** - skripty pro spouštění testů
- ✅ **build_exe.ps1** / **build_exe.sh** - skripty pro vytváření EXE souborů
- ✅ **start_app.ps1** - PowerShell skript pro spuštění aplikace

---

## ⚠️ Chybí / Mělo by následovat

### Kritické (doporučeno před prvním použitím)

#### 1. `.gitignore`
**Priorita**: Vysoká  
**Důvod**: Ignorovat `__pycache__/`, `.venv/`, `*.pyc`, atd.

#### 2. `LICENSE`
**Priorita**: Vysoká  
**Důvod**: Projekt má v `pyproject.toml` MIT licenci, ale chybí LICENSE soubor

#### 3. Reálný `config/config.ini`
**Priorita**: Střední  
**Důvod**: `config.example.ini` je jen template, uživatel potřebuje vlastní config

---

### Důležité (pro produkční použití)

#### 4. API dokumentace ✅
**Status**: Hotovo  
**Dokumentace**: [API.md](API.md) - kompletní dokumentace všech REST a WebSocket endpointů


#### 6. Troubleshooting sekce v README ✅
**Status**: Hotovo  
**Dokumentace**: [README.md](README.md) - sekce Troubleshooting obsahuje řešení běžných problémů

#### 7. Quick Start Guide ✅
**Status**: Hotovo  
**Dokumentace**: [README.md](README.md) - sekce Quick Start obsahuje kompletní návod

---

### Rozšíření (nice to have)

#### 8. Integrační testy
**Priorita**: Nízká  
**Důvod**: End-to-end testy s mockovanými iRacing a OBS

**Co by mělo testovat**:
- Celý flow: iRacing → state machine → OBS switch
- API komunikace s reálným serverem

#### 9. CI/CD konfigurace
**Priorita**: Nízká  
**Důvod**: Automatické spouštění testů

**Možnosti**:
- GitHub Actions workflow
- GitLab CI config
- Automatické testy při push/PR

#### 10. CHANGELOG.md
**Priorita**: Nízká  
**Důvod**: Sledování změn mezi verzemi

#### 11. Build skripty pro EXE
**Priorita**: Nízká  
**Důvod**: Automatizace vytváření EXE souborů

**Možnosti**:
- `build_exe.ps1` - Windows build script
- `build_exe.sh` - Linux/Mac build script
- Automatické verzování

#### 12. Příklady konfigurací
**Priorita**: Nízká  
**Důvod**: Různé use cases

**Možnosti**:
- `config/config.racing.ini` - pro závody
- `config/config.practice.ini` - pro trénink
- `config/config.replay.ini` - pro replay

#### 13. Logging dokumentace
**Priorita**: Nízká  
**Důvod**: Jak interpretovat logy

**Co by mělo obsahovat**:
- Co znamenají různé log úrovně
- Jak číst structured logs
- Kde najít logy

---

## 📋 Doporučený postup implementace

### Fáze 1: Základní dokončení ✅
1. ✅ Vytvořit `.gitignore`
2. ✅ Vytvořit `LICENSE` (MIT)
3. ✅ Přidat Quick Start do README
4. ✅ Přidat Troubleshooting do README

### Fáze 2: Dokumentace ✅
5. ✅ API dokumentace (v README)
7. ✅ Aktualizovat README s více detaily

### Fáze 3: Rozšíření ✅
8. ⏳ Integrační testy (volitelné - unit testy jsou dostatečné)
9. ✅ CI/CD setup (GitHub Actions)
10. ✅ Build skripty (`build_exe.ps1`, `build_exe.sh`)
11. ✅ CHANGELOG.md

---

## 🎯 Aktuální stav

**Projekt je kompletní a připravený k produkčnímu použití!**

✅ **Všechny fáze dokončeny**:
1. ✅ Základní dokončení (`.gitignore`, `LICENSE`)
2. ✅ Dokumentace (Quick Start, Troubleshooting, API)
3. ✅ Rozšíření (CI/CD, Build skripty, CHANGELOG)

**Testy**: ✅ Všechny prošly (79+ testů, 29 nových testů přidáno v lednu 2026)  
**Kód**: ✅ Implementováno podle plánu  
**Dokumentace**: ✅ Kompletní (README, tests.md, STATUS.md, CHANGELOG.md, TESTING_CHECKLIST.md)  
**CI/CD**: ✅ GitHub Actions workflow  
**Build**: ✅ Automatizované skripty (silent EXE build s `--noconsole`)

### Co je volitelné (nice to have)

- **Integrační testy** - unit testy jsou dostatečné pro aktuální rozsah projektu
- **Příklady konfigurací** - lze přidat později podle potřeby
- **Logging dokumentace** - základní info je v Troubleshooting sekci

---

## 🔧 Real-world Debugging (leden 2026)

### Dokončené úpravy na základě testování

#### ✅ iRacing Mode Detection
- **IDLE**: Menu/lobby - funguje správně
- **GARAGE**: Garáž ve hře - funguje správně
- **RACE**: Na trati v autě - funguje správně
- **REPLAY**: Přehrávání - funguje správně
- **QUIT**: Detekce ukončení hry - implementováno pomocí `SessionTime` stall detection
- **SETTINGS**: Odstraněno - iRacing SDK nehlásí tuto informaci spolehlivě

#### ✅ QUIT Detection
- Detekce ukončení iRacing na základě zamrznutí `SessionTime`
- Konfigurovatelný práh `quit_stall_seconds` (výchozí 0.4s)
- Automatické přepnutí na QUIT scénu při opuštění hry

#### ✅ RESTART Hotkey (VR podpora)
- Globální hotkey pro RESTART mód (`pynput` knihovna)
- Konfigurovatelné přes `[hotkeys]` sekci v config.ini
- Výchozí: `ctrl+shift+f7` (změnitelné)
- Sticky mód - RESTART přetrvává do dalšího skutečného IDLE

#### ✅ Grace Period (Loading Screen Handling)
- **Problém**: Po loading screen iRacingu se krátce zobrazovala špatná scéna (GARAGE z inspekčního režimu)
- **Řešení**: Implementována grace period v state machine
  - Po reconnect se aktivuje `_waiting_for_idle`
  - Ignoruje všechny módy kromě IDLE dokud nepřijde IDLE po non-IDLE módu
  - Zajišťuje správné přepnutí scény až po skutečném načtení hry do lobby

#### ✅ OBS Connection States
- Rozlišení mezi "OBS not running" a "OBS connection failed"
- Validace konfigurovaných scén proti dostupným OBS scénám
- Detekce aktivního OBS profilu (volitelné)


#### ✅ Loading Time Tracker
- Sledování doby trvání loading screenů iRacing
- Ukládání historie do JSON souboru (`loading_history.json`)
- Výpočet průměrné doby loadingu pro automatické spuštění broadcastu
- Konfigurovatelný výchozí čas (`default_loading_time_seconds`)
- Automatické ukládání po každém ukončení loadingu

#### ✅ Event Log System
- Thread-safe FIFO event log pro ukládání událostí
- Používá se pro HTML dashboards (event log sekce)
- Konfigurovatelná velikost (`dashboard_event_log_size`)
- Typy eventů: `connection_lost`, `connection_restored`, `scene_switch`, `override_applied`, `loading_started`, `loading_ended`, `stream_started`, `stream_stopped`, atd.

#### ✅ HTML Dashboards
- **GR Dashboard** (`/gr-status`): Velký dashboard s JavaScript auto-update
  - Zobrazuje status připojení, scény, streaming, OBS profil
  - Event log s posledními X událostmi
  - Cache-busting headers pro zabránění cachování
  - Konfigurovatelné obrázky (background, loga)
- **VR Dashboard** (`/vr-status`): Minimalistický dashboard pro VR
  - Bílé písmo, větší fonty, oranžový border
  - Bez JavaScriptu (RaceLab VR nepodporuje)
  - Silné cache-control headers

#### ✅ Broadcast Management
- Automatické spuštění broadcastu během loadingu
  - Konfigurovatelné: `auto_start_broadcast`, `auto_start_at_percent`
  - Spouští se v X% průměrné doby loadingu
  - Kontrola připravenosti broadcastu (`is_broadcast_ready`)
- Automatické zastavení streamu po QUIT
  - Konfigurovatelné: `auto_stop_stream`, `stop_stream_after_seconds`
  - Zastaví stream X sekund po detekci QUIT módu

#### ✅ Session Information Detection
- Detekce typu session během loadingu (`SessionType`, `SessionName`, `SessionNum`)
- Extrakce: Practice, Qualify, Race, atd.
- Ukládání do event logu při startu/konci loadingu

#### ✅ Background OBS Connection
- Non-blocking připojení k OBS při startu aplikace
- Pokud OBS neběží, aplikace startuje okamžitě
- Background task pro opakované pokusy o připojení
- API server startuje i bez OBS připojení

#### ✅ Notifications Control
- Globální flag pro zapnutí/vypnutí notifikací
- Konfigurovatelné přes `notifications_enabled` v configu
- Respektuje se i v `show_toast()` funkci

#### ✅ PowerShell Start Script
- `start_app.ps1` pro snadné spuštění aplikace
- Podporuje `-Config` i `--config` formát
- Kontrola existence config souboru
- Kontrola Python a balíčku
- Automatická instalace v dev módu

#### ✅ Health Check & Metrics (leden 2026)
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

#### ✅ Config Hot Reload (leden 2026)
- **Config Reload Endpoint** (`POST /config/reload`)
  - Dynamické reloadování konfigurace bez restartu služby
  - Validace nového configu před aplikací
  - Error handling pro neplatné configy
  - Aktualizace `app["config"]` objektu

#### ✅ Graceful Shutdown (leden 2026)
- **Shutdown Endpoint** (`POST /shutdown`)
  - API-triggered graceful shutdown
  - Nastavení shutdown eventu pro ukončení main loopu
  - Tlačítko v GR Dashboard pro shutdown
  - Error handling když shutdown není dostupný

#### ✅ File Logging s Rotací (leden 2026)
- **Logging do souboru** (`util/logging.py`)
  - Vždy loguje do stderr (console)
  - Volitelné logování do souboru s rotací
  - Konfigurovatelné: `log_file`, `log_max_bytes`, `log_backup_count`
  - Automatické vytváření log directory
  - UTF-8 encoding
  - Rotace při dosažení max_bytes
  - Omezení počtu backup souborů

#### ✅ Session Info v API (leden 2026)
- **Session Information** v status endpointu
  - `session_type` - typ session (Practice, Qualify, Race, atd.)
  - `session_name` - název session
  - `session_num` - číslo session
  - Ignorování "Test" session (nastavení na `None`)
  - Zobrazení v GR Dashboard

#### ✅ GR Dashboard Vylepšení (leden 2026)
- **Metrics sekce** - zobrazení všech metrik
- **Session Info sekce** - zobrazení session informací
- **Reload Config tlačítko** - hot reload configu
- **Shutdown Service tlačítko** - graceful shutdown
- **Cumulative | Current formát** - pro connection times a stream duration
- **Sublabels** - popisky hodnot s potlačenou barvou
- **Vertikální zarovnání** - konzistentní spacing napříč řádky
- **Stream Info sekce** - zobrazení stream title a description z YouTube API
- **YouTube API varování** - zobrazení varování při quota exceeded nebo missing API key
- **Lokalizované texty** - všechny texty v dashboardu jsou lokalizovány podle nastaveného jazyka

### Konfigurační změny

```ini
[iracing]
quit_stall_seconds = 0.4  # Práh pro detekci QUIT

[hotkeys]
restart_hotkey = ctrl+shift+f7  # Globální hotkey pro RESTART mód

[scenes]
QUIT = End       # Scéna při ukončení hry
RESTART = Restart # Scéna při RESTART módu (sticky)

[switching]
# Automatické spuštění broadcastu během loadingu
auto_start_broadcast = false
auto_start_at_percent = 50
default_loading_time_seconds = 12.0

# Automatické zastavení streamu po QUIT
auto_stop_stream = false
stop_stream_after_seconds = 30

[dashboards]
dashboard_update_fps = 2
dashboard_event_log_size = 50
dashboard_gr_background_image = path/to/bg.png
dashboard_gr_logo_obs = path/to/obs.png
dashboard_gr_logo_iracing = path/to/iracing.png
dashboard_gr_logo_app = path/to/app.png
dashboard_vr_icons_path = path/to/icons/

[app]
notifications_enabled = true  # Globální zapnutí/vypnutí notifikací
log_file = logs/irswitch.log  # Volitelné: cesta k log souboru
log_max_bytes = 10485760  # 10 MB default
log_backup_count = 5  # Počet backup souborů
language = CS  # Jazyk rozhraní (CS, EN, DE, FR, SP, PL, HU)
```

### Odstraněné funkce

- **SETTINGS mód** - iRacing SDK nehlásí otevření nastavení spolehlivě, odstraněno z `DrivingMode` enum

---

## 📝 Poznámky

- Projekt je **funkčně kompletní** - všechny požadované funkce jsou implementované
- **79+ testů** pokrývají všechny klíčové komponenty včetně nových funkcí
- **Nové funkce (leden 2026)**: Health check, Metrics, Config hot reload, Shutdown, File logging, Session info, Lokalizace (i18n), YouTube API integrace
- **Testovací pokrytí**: Všechny nové endpointy a funkcionality jsou plně otestované
- **Dokumentace**: Kompletní dokumentace rozdělena do samostatných dokumentů (CONFIG.md, API.md, LOCALIZATION.md, BUILD_AND_DEPLOY.md, YOUTUBE_API_SETUP.md, VR_SUPPORT.md)
- Pro vývoj je projekt připravený, pro end-usery je k dispozici kompletní dokumentace

## 🆕 Poslední aktualizace (leden 2026)

### Nové funkce
- ✅ Health check endpoint (`GET /health`)
- ✅ Metrics endpoint (`GET /metrics`) s cumulative/current session časy
- ✅ Config hot reload (`POST /config/reload`)
- ✅ Graceful shutdown endpoint (`POST /shutdown`)
- ✅ File logging s rotací (console vždy, file volitelně)
- ✅ Session info v API a GR Dashboard
- ✅ GR Dashboard vylepšení (metrics, session info, tlačítka)
- ✅ **Lokalizace (i18n)** - podpora 7 jazyků (CS, EN, DE, FR, SP, PL, HU)
  - Lokalizované texty v HTML dashboardech, event logu, toast notifikacích
  - Konfigurovatelné přes `language` v `config.ini`
  - Automatické použití při startu aplikace
- ✅ **YouTube Data API v3 integrace**
  - Získávání stream title a description z YouTube
  - Cachování pro snížení API volání
  - Quota exceeded detection a varování
  - API key missing detection
  - Lokalizované zprávy o kvótě a API klíči
- ✅ **Reorganizace dokumentace**
  - Nové dokumenty: CONFIG.md, API.md, LOCALIZATION.md, BUILD_AND_DEPLOY.md, YOUTUBE_API_SETUP.md, VR_SUPPORT.md
  - README.md zjednodušen - pouze Quick Start, Troubleshooting, odkazy na další dokumenty

### Nové testy (29 testů)
- ✅ 9 testů pro nové API endpointy (`tests/test_api.py`)
- ✅ 13 testů pro MetricsCollector (`tests/test_metrics.py`)
- ✅ 8 testů pro file logging (`tests/test_logging.py`)

### Build & Distribuce
- ✅ Silent EXE build (`--noconsole` pro background executable)
- ✅ Automatické kopírování config/ do dist/
- ✅ README.txt v dist/ pro uživatele

### Úpravy a cleanup (leden 2026)
- ✅ Odstraněn testovací kód z VR Dashboard (testy location a xhr)
- ✅ Odstraněn VR status wrapper endpoint (`/vr-status-wrapper`) s iframe
- ✅ VR Dashboard nyní zobrazuje pouze čisté jméno scény bez testovacích informací
- ✅ YouTube API optimalizace - cachování stream info, volání pouze při změně broadcast_id
- ✅ YouTube API error handling - správné zpracování 403 (quota exceeded) a missing API key
- ✅ Lokalizované YouTube API zprávy v dashboardu a event logu
