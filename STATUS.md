# Status projektu - Co je hotové a co následuje

## ✅ Hotové (100% implementováno)

### Core funkcionalita
- ✅ **Konfigurace** (`config.py`) - načítání INI, validace
- ✅ **iRacing Reader** (`iracing/reader.py`) - async wrapper pro pyirsdk
- ✅ **Extractors** (`iracing/extractors.py`) - extrakce módu s prioritou
- ✅ **OBS Client** (`obs/client.py`) - async WebSocket klient s retry logikou
- ✅ **State Machine** (`logic/state_machine.py`) - debounce, cooldown, override
- ✅ **Policy** (`logic/policy.py`) - mapování módu na scény
- ✅ **API Server** (`server/api.py`) - REST + WebSocket endpointy
- ✅ **Main Loop** (`main.py`) - koordinace všech komponent
- ✅ **Utilities** (`util/`) - clock, logging

### Testy
- ✅ **50+ unit testů** - všechny prošly
  - Extractors (4 testy)
  - Policy (1 test)
  - iRacing Reader (8 testů)
  - OBS Client (11 testů)
  - State Machine (11 testů)
  - API Server (6 testů)
  - Main Service (3 testy)
  - Loading Tracker (9 testů)
  - Event Log (9 testů)
  - E2E Main Loop (7 testů)
- ✅ **0 warnings** - vše opraveno
- ✅ **Dokumentace testů** (`tests.md`) - detailní popis všech testů

### Dokumentace
- ✅ **README.md** - základní dokumentace projektu
- ✅ **tests.md** - dokumentace testů
- ✅ **config.example.ini** - příklad konfigurace
- ✅ **RACELAB_VR_SETUP.md** - návod pro nastavení VR dashboardu v RaceLab VR
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

#### 4. API dokumentace
**Priorita**: Střední  
**Důvod**: 
- Popis REST endpointů (parametry, response formáty)
- WebSocket message formáty
- Možnost: OpenAPI/Swagger spec

**Co by mělo obsahovat**:
- `GET /status` - response schema
- `POST /override` - request/response schema
- `POST /autoswitch/toggle` - response schema
- `WS /ws` - message formáty


#### 6. Troubleshooting sekce v README
**Priorita**: Střední  
**Důvod**: Pomoc při běžných problémech

**Co by mělo obsahovat**:
- OBS se nepřipojuje → zkontroluj password, port
- iRacing není detekován → zkontroluj jestli běží
- Scény se nepřepínají → zkontroluj autoswitch, cooldown
- Jak zkontrolovat logy

#### 7. Quick Start Guide
**Priorita**: Střední  
**Důvod**: Rychlý start pro nové uživatele

**Co by mělo obsahovat**:
1. Instalace závislostí
2. Vytvoření config.ini z example
3. Nastavení OBS WebSocket
4. Spuštění služby
6. Testování

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

**Testy**: ✅ Všechny prošly (43/43)  
**Kód**: ✅ Implementováno podle plánu  
**Dokumentace**: ✅ Kompletní (README, tests.md, STATUS.md, CHANGELOG.md)  
**CI/CD**: ✅ GitHub Actions workflow  
**Build**: ✅ Automatizované skripty

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
  - Wrapper endpoint (`/vr-status-wrapper`) s iframe a meta refresh

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
```

### Odstraněné funkce

- **SETTINGS mód** - iRacing SDK nehlásí otevření nastavení spolehlivě, odstraněno z `DrivingMode` enum

---

## 📝 Poznámky

- Projekt je **funkčně kompletní** - všechny požadované funkce jsou implementované
- Testy pokrývají všechny klíčové komponenty
- Chybí hlavně **dokumentace pro uživatele** a **projektové soubory** (.gitignore, LICENSE)
- Pro vývoj je projekt připravený, pro end-usery by bylo dobré doplnit dokumentaci
