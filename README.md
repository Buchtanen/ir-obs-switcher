# iRacing → OBS Auto Scene Switcher (Python)

[![Tests](https://github.com/Buchtanen/richa/workflows/Tests/badge.svg)](https://github.com/Buchtanen/richa/actions)
[![CodeQL](https://github.com/Buchtanen/richa/workflows/CodeQL%20Security%20Analysis/badge.svg)](https://github.com/Buchtanen/richa/actions)
[![Security](https://github.com/Buchtanen/richa/workflows/Security%20Checks/badge.svg)](https://github.com/Buchtanen/richa/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Účel projektu

Tento projekt vznikl z praktické potřeby: **když jezdíš ve VR, nevidíš monitor** a nemůžeš ručně ovládat OBS stream. 

Představ si situaci:
- Jsi ve VR headsetu, soustředíš se na jízdu v iRacing
- Stream běží na pozadí, ale potřebuješ přepínat scény podle toho, co se děje ve hře
- Nemůžeš se dívat na monitor, nemůžeš používat klávesnici nebo myš
- Potřebuješ něco, co **automaticky detekuje stav hry a přepíná scény za tebe**

**Řešení**: Tato aplikace automaticky:
- Detekuje, v jakém módu se nacházíš (menu, garáž, závod, replay)
- Přepíná OBS scény podle stavu hry
- Spouští a zastavuje stream podle potřeby
- Poskytuje monitoring přes web dashboard (který můžeš mít na druhém monitoru nebo v telefonu)

**Výsledek**: Můžeš se soustředit na jízdu, zatímco aplikace se stará o celý stream workflow.

---

## Obsah

- [Quick Start](#quick-start)
  - [Instalace](#1-instalace)
  - [Konfigurace](#2-konfigurace)
  - [Nastavení OBS](#3-nastavení-obs)
  - [Spuštění služby](#4-spuštění-služby)
  - [Testování](#5-testování)
- [HTML Dashboards](#html-dashboards)
- [Obsluha aplikace](#obsluha-aplikace)
- [Troubleshooting](#troubleshooting)
- [Další dokumentace](#další-dokumentace)

---

## Quick Start

### 1. Instalace

Doporučená verze Pythonu pro vývoj: **3.11–3.13** (CI matrix). Python **3.14+** může fungovat, ale u závislostí bývá nestabilnější — `start_app.ps1` na to soft-warnuje.

```powershell
# Vytvoření virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Instalace závislostí
pip install -U pip
pip install -e .
```

### Distribuce (EXE)

Pokud používáš buildnutou distribuci z `dist/`, doporučený postup je:

```powershell
cd dist
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -Wizard
```

Tím se vygeneruje `config/config.ini`, nastaví autostart (Task Scheduler) a vytvoří se zkratky včetně **Open Dashboard**.

#### Odinstalace (EXE)

Odinstalace smaže jen autostart (Scheduled Task) a desktop zkratky. `config/` a `logs/` nechává.

```powershell
cd dist
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -Uninstall
```

### 2. Konfigurace

Zkopíruj `config/config.example.ini` na `config/config.ini` a uprav:

```ini
[obs]
ws_url = ws://127.0.0.1:4455
password = tvé_obs_heslo
```

**Důležité**: Nastav správné heslo pro OBS WebSocket (nastavení v OBS: Tools → WebSocket Server Settings).

**Více informací**: Viz [CONFIG.md](CONFIG.md) pro kompletní popis všech konfiguračních parametrů.

### 3. Nastavení OBS

1. Otevři OBS Studio
2. Tools → WebSocket Server Settings
3. Povol "Enable WebSocket server"
4. Nastav port (výchozí: 4455)
5. Nastav heslo (stejné jako v `config.ini`)
6. Vytvoř scény s názvy podle `[scenes]` v config (Idle, Pits, Race, Replay)

**Důležité**: Názvy scén v OBS musí přesně odpovídat názvům v `config.ini` (case-sensitive)!

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

---

## HTML Dashboards

Aplikace poskytuje operator admin + legacy switcher dashboard + VR widget:

### Admin (primární)

- **URL**: `http://127.0.0.1:17321/admin`
- **Funkce**: Live overview — switcher health, extensions (BLE, Libre Hardware Monitor, sysinfo), features (overlay / commentary enabled vs active), merged activity feed
- **Podstránky**: `/admin/extensions`, `/admin/features`, `/admin/activity`
- **API**: `GET /api/admin/status`, `GET /api/admin/activity` (viz [API.md](API.md))
- **Spec**: [docs/admin_dashboard_spec.md](docs/admin_dashboard_spec.md); sysinfo/LHM upgrade plán: [docs/sysinfo_lhm_upgrade_spec.md](docs/sysinfo_lhm_upgrade_spec.md)

### GR Dashboard / Switcher controls (legacy)

- **URL**: `http://127.0.0.1:17321/gr-status`
- **Funkce**: JavaScript auto-update, override/restart ovládání, YouTube stream info, switcher event log, metrics
- **Konfigurovatelné**: Obrázky pozadí a loga
- **Screenshot**: [GR Dashboard](assets/rg-status-screen.png)
- **Navigace**: odkazuje i na Admin

### Race overlay (OBS Browser Source)

- **URL**: `http://127.0.0.1:17321/overlay` — transparentní 1920×1080 overlay. Live HUD (SYSINFO + karty) je jen při zapojeném iRacing; link drop / quit → overlay je prázdný. `?demo=1` tohle nerespektuje.
- **Dry test**: `http://127.0.0.1:17321/overlay/demo` — tmavé jeviště, **V4** cyklický scénář HUD (~28&nbsp;s loop) bez OBS/iRacing; v UI lze přepnout na legacy V3
- **Časy na HUD**: iRSDK posílá sekundy (invalid často `-1`). Overlay je formátuje jako iRacing F3 / SimHub (`m:ss.fff`, delta `+0.318`). WS `metrics` zůstávají čísla.
- **Session tape**: při PRACTICE/QUALIFY/RACE zapisuje JSONL do `recordings/` (`t_stream` = VOD, `t_session` / `t_green` = iRacing, `t_mono` = replay delay). Vypnutí: `[overlay] session_tape = false`. Replay: `irswitchd --config config\config.ini --replay recordings\overlay-….jsonl`
- **Debug**: `http://127.0.0.1:17321/overlay/debug` — ruční TEST eventy
- **Config**: `http://127.0.0.1:17321/config` — sampling, battle, BLE, sysinfo, theme
- **WebSocket**: `ws://127.0.0.1:17321/ws/overlay` (oddělený od switcher `/ws`)
- Tři themes (`cyber_racing`, `stealth_graphite`, `night_attack`) mají shodnou geometrii, 50 PNG + 4 WebM na theme (SYSINFO 1920×72, battle karta 420×140, V3 vrstvy). Popis: `src/irswitch/web/themes/ASSETS.md`. Chybějící soubor = CSS fallback.
- **Battle golden freeze**: `http://127.0.0.1:17321/overlay?demo=1&layout=golden` (HUNTING + HUNTED, bez SYSINFO). Theme: `&theme=cyber_racing` / `stealth_graphite` / `night_attack`.
- **V4 cyclic demo (iframe)**: `http://127.0.0.1:17321/overlay?demo=1&renderer=v4` — DisplayV4 envelopes, stejný beat order jako V3 dry test.

Mock / replay (bez iRacing):

```powershell
irswitchd --config config\config.ini --mock
irswitchd --config config\config.ini --replay recordings\battle.jsonl
```

Overlay závislosti (`bleak`, `psutil`, `nvidia-ml-py`) jdou s `pip install -e .`. GPU čísla bere NVML. CPU package na Windows: LibreHardwareMonitor 0.9.5+ **zrušil WMI** — overlay čte `http://127.0.0.1:8085/data.json` (Options → Remote Web Server → Run, File → Hardware → CPU zaškrtnuté). Když LHM bindne jen na LAN IP, overlay to vezme z `LibreHardwareMonitor.config`. Starší LHM pořád WMI `root\LibreHardwareMonitor`. Stock Windows **nemá** CPU package power. FPS/FT berou iRacing — mimo 3D zůstanou prázdné. **LHM je prerekvizita** pro správné sysinfo CPU package údaje; admin Extensions kartu ukazuje, jestli LHM HTTP běží. Plán plného sysinfo přes LHM: [docs/sysinfo_lhm_upgrade_spec.md](docs/sysinfo_lhm_upgrade_spec.md).

### VR Dashboard (pro VR)

- **URL**: `http://127.0.0.1:17321/vr-status`
- **Funkce**: Minimalistický design, bílé písmo, větší fonty
- **Omezení**: RaceLab VR widgety nepodporují auto-refresh - widget se neaktualizuje automaticky
- **Více informací**: Viz [VR_SUPPORT.md](VR_SUPPORT.md) a [RACELAB_VR_SETUP.md](RACELAB_VR_SETUP.md)

---

## Obsluha aplikace

### GR Dashboard

GR Dashboard poskytuje webové rozhraní pro ovládání aplikace:

- **Toggle Autoswitch** - zapne/vypne automatické přepínání scén
- **Reset RESTART Mode** - deaktivuje RESTART mód
- **Reload Config** - přenačte konfiguraci ze souboru
- **Reset** - resetuje metriky a stav aplikace
- **Restart Service** - detached respawn + graceful stop (fail-closed při selhání spawnu)
- **Shutdown Service** - ukončí aplikaci

### API

Aplikace vystavuje REST API a WebSocket pro programové ovládání.

**Více informací**: Viz [API.md](API.md) pro kompletní dokumentaci API.

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
2. Spouštěj přes `.\start_app.ps1` (preferuje `.venv`, doinstaluje bleak/psutil, spouští `python -m irswitch.main`)
3. Ověř závislosti **tím samým** interpreterem: `.\.venv\Scripts\python.exe -m pip install -e .`
4. Zkontroluj, že port 17321 není obsazený jinou aplikací
5. Podívej se na error message - často obsahuje konkrétní problém

### Druhá instance / port už obsazený

**Příznaky**: Druhý start (zkratka, `start_app.ps1`, EXE) hned skončí; stderr/log obsahuje „already in use“ / „Another irswitch instance“; exit code **2**.

**Příčina**: Na `app.http_host`:`app.http_port` už naslouchá běžící irswitch (nebo jiná aplikace). Guard to detekuje **před** těžkou inicializací OBS/HTTP.

**Řešení**:
1. Zastav existující instanci (GR Dashboard **Shutdown Service**, `POST /shutdown`, nebo Task Manager)
2. Nebo změň `app.http_port` v `config.ini` a restartuj
3. Ověř, že neběží dvě zkratky / naplánované úlohy najednou

### Jak zastavit službu (Windows / EXE)

Preferuj graceful shutdown (GR Dashboard **Shutdown Service** nebo `POST /shutdown`). Pro Task Scheduler End, `Install.ps1 -Uninstall` / `-UninstallTask` a rozdíl graceful vs kill viz [BUILD_AND_DEPLOY.md – Zastavení služby](BUILD_AND_DEPLOY.md#zastavení-služby-stopping-the-service).

Pro **restart bez ručního startu** použij GR **Restart Service** / `POST /restart` (viz [BUILD_AND_DEPLOY.md – Restart služby](BUILD_AND_DEPLOY.md#restart-služby-restarting-the-service)).

### `PermissionError` / pád při `import aiohttp` (SSLKEYLOGFILE)

**Příznaky**: Traceback končí na `ssl.create_default_context()` / `PermissionError` s cestou typu `\\?\Volume{...}\virtual_file.log`

**Příčina**: Env `SSLKEYLOGFILE` ukazuje na nepřístupný soubor (časté u některých proxy/antivirus/IDE nástrojů). Python 3.14 pak při importu SSL kontextu spadne.

**Řešení**:
1. V aktuálním shellu: `Remove-Item Env:SSLKEYLOGFILE`
2. Nebo smaž User/System proměnnou `SSLKEYLOGFILE` v Windows (pokud ji nepotřebuješ)
3. `.\start_app.ps1` nepoužitelnou hodnotu vyčistí automaticky
4. Doporučený Python pro vývoj: **3.11–3.13** (CI); 3.14 může být nestabilní u závislostí

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

---

## Další dokumentace

- **[CONFIG.md](CONFIG.md)** - Kompletní popis konfigurace
- **[COMMENTARY_ENGINE.md](COMMENTARY_ENGINE.md)** - Komentář / TTS: graf sekvencí, EN mock (in-car / lap / pit / back on track), validator, zadání textů
- **[docs/commentary_content_db_plan.md](docs/commentary_content_db_plan.md)** - Plán content DB (JSON graf) + vlny plnění textů + handoff na textový model
- **[docs/commentary_product_suite.md](docs/commentary_product_suite.md)** - Produktová sada commentary (live readiness, why-quiet, stream start, sink, budget)
- **[API.md](API.md)** - Dokumentace REST API a WebSocket endpointů
- **[LOCALIZATION.md](LOCALIZATION.md)** - Popis lokalizace a podporovaných jazyků
- **[BUILD_AND_DEPLOY.md](BUILD_AND_DEPLOY.md)** - Návod pro vytvoření EXE a nastavení jako služby
- **[RELEASE_POLICY.md](RELEASE_POLICY.md)** - Release PR model, semver labely na PR
- **[VERSIONING.md](VERSIONING.md)** - Kde žije verze aplikace a jak se zobrazuje
- **[YOUTUBE_API_SETUP.md](YOUTUBE_API_SETUP.md)** - Postup nastavení YouTube API tokenu v Google Console
- **[VR_SUPPORT.md](VR_SUPPORT.md)** - VR support - příslib, záměr a popis problému
- **[RACELAB_VR_SETUP.md](RACELAB_VR_SETUP.md)** - Návod pro nastavení VR dashboardu v RaceLab VR
- **[STATUS.md](STATUS.md)** - Přehled stavu projektu a co je hotové
- **[CHANGELOG.md](CHANGELOG.md)** - Historie změn projektu
- **[tests.md](tests.md)** - Detailní dokumentace všech testů
- **[docs/event_graph_editor_spec.md](docs/event_graph_editor_spec.md)** - Nápad (nice-to-have): grafický editor eventů / prahů — není implementováno
