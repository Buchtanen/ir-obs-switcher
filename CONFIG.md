# Konfigurace aplikace

Kompletní popis všech konfiguračních parametrů v `config.ini`.

Viz `config/config.example.ini` pro kompletní příklad konfigurace.

## Obsah

- [Sekce `[app]`](#sekce-app---základní-nastavení)
- [Sekce `[iracing]`](#sekce-iracing---iracing-detekce)
- [Sekce `[obs]`](#sekce-obs---obs-websocket-připojení)
- [Sekce `[switching]`](#sekce-switching---logika-přepínání-scén)
- [Sekce `[hotkeys]`](#sekce-hotkeys---globální-hotkey-volitelné)
- [Sekce `[scenes]`](#sekce-scenes---mapování-módu-na-obs-scény)
- [Sekce `[dashboards]`](#sekce-dashboards---html-dashboardy-volitelné)
- [Sekce `[stream_chapters]`](#sekce-stream_chapters---kapitoly-streamu-přes-ws-volitelné)

---

## Sekce `[app]` - Základní nastavení

### `http_host` (výchozí: `127.0.0.1`)

IP adresa, na které běží HTTP server.

**Kdy použít**: 
- `127.0.0.1` - pouze lokální přístup (výchozí, bezpečnější)
- `0.0.0.0` - přístup z jiných počítačů v síti

**Příklad**: 
```ini
http_host = 0.0.0.0
```

### `http_port` (povinné)

Port pro HTTP server a WebSocket.

**Validace**: musí být v rozsahu **1–65535** (jinak startup selže s `ValueError`).

**Kdy použít**: Změň pokud je port obsazený jinou aplikací.

**Příklad**: 
```ini
http_port = 17321
```

### `log_level` (výchozí: `INFO`)

Úroveň logování: `DEBUG`, `INFO`, `WARNING`, `ERROR`.

**Kdy použít**: 
- `DEBUG` - pro ladění problémů (zobrazuje všechny detaily)
- `INFO` - normální provoz (doporučeno)
- `WARNING` - jen varování a chyby
- `ERROR` - pouze chyby

**Příklad**: 
```ini
log_level = DEBUG
```

**Runtime toggle (nepersistuje)**: `POST /logging/level` s `{"level":"DEBUG"}` nebo `{"level":"INFO"}` změní úroveň jen pro běžící proces (GR badge/tlačítko). Po restartu se znovu použije `app.log_level` z INI. Změna `log_level` v INI + hot-reload **neaplikuje** logging handlers — viz Hot-reload / needs restart.

### `notifications_enabled` (výchozí: `true`)

Zapne/vypne Windows notifikace při změně připojení.

**Kdy použít**: Nastav na `false` pokud nechceš notifikace.

**Příklad**: 
```ini
notifications_enabled = false
```

### `log_file` (volitelné)

Cesta k souboru pro logování s rotací.

**Kdy použít**: Pokud chceš ukládat logy do souboru pro pozdější analýzu.

**Jak to funguje**: Logy se ukládají do souboru s automatickou rotací (když dosáhne `log_max_bytes`, vytvoří se nový soubor).

**Příklad**: 
```ini
log_file = logs/irswitch.log
```

**Poznámka**: Cesty jsou relativní k working directory (adresáři, ze kterého spouštíš aplikaci).

### `log_max_bytes` (výchozí: `10485760` = 10 MB)

Maximální velikost log souboru před rotací (v bajtech).

**Kdy použít**: Uprav podle potřeby - větší soubory = více historie, ale více místa na disku.

**Jak to funguje**: Když log soubor dosáhne této velikosti, vytvoří se nový soubor a starý se přejmenuje.

**Příklad**: 
```ini
log_max_bytes = 10485760  # 10 MB
```

### `log_backup_count` (výchozí: `5`)

Počet backup log souborů, které se uchovávají.

**Kdy použít**: Uprav podle potřeby - více backupů = více historie, ale více místa na disku.

**Jak to funguje**: Aplikace uchovává X nejnovějších rotovaných log souborů, starší se mažou.

**Příklad**: 
```ini
log_backup_count = 5
```

### `log_colors` (výchozí: `true`)

Zapne/vypne barevný výstup v konzoli.

**Kdy použít**: 
- `true` - barevné logy pro lepší čitelnost (doporučeno)
- `false` - prostý text bez barev (např. pokud terminál nepodporuje barvy)

**Jak to funguje**: Používá ANSI escape codes pro barvy (na Windows automaticky aktivuje podporu).

**Příklad**: 
```ini
log_colors = true
```

### `language` (výchozí: `CS`)

Jazyk rozhraní aplikace.

**Podporované jazyky**: 
- `CS` - čeština (výchozí)
- `EN` - angličtina
- `DE` - němčina
- `FR` - francouzština
- `SP` - španělština
- `PL` - polština
- `HU` - maďarština

**Kdy použít**: Nastav podle preferovaného jazyka pro zobrazení textů v dashboardu a event logu.

**Jak to funguje**: Aplikace automaticky použije zvolený jazyk pro všechny texty v HTML dashboardech a event logu.

**Příklad**: 
```ini
language = EN
```

**Poznámka**: Pokud je nastaven neplatný jazyk, použije se výchozí čeština (CS).

**Více informací**: Viz [LOCALIZATION.md](LOCALIZATION.md) pro detailní popis lokalizace.

---

## Sekce `[iracing]` - iRacing detekce

### `poll_hz` (povinné)

Frekvence čtení dat z iRacing SDK (polling rate).

**Validace**: musí být **>= 1** (jinak startup selže s `ValueError`; `0` by způsobilo dělení nulou v main loopu).

**Kdy použít**: 
- Nižší hodnoty (3-5 Hz) = menší zátěž CPU, pomalejší reakce
- Vyšší hodnoty (10-20 Hz) = rychlejší reakce, větší zátěž

**Doporučení**: `5` Hz je dobrý kompromis (200ms interval).

**Příklad**: 
```ini
poll_hz = 5
```

### `quit_stall_seconds` (výchozí: `0.4`)

Práh pro detekci ukončení iRacing (v sekundách).

**Kdy použít**: 
- Pokud se QUIT detekuje příliš brzy → zvyš hodnotu (např. `0.6`)
- Pokud se QUIT nedetekuje → sniž hodnotu (např. `0.3`)

**Jak to funguje**: Aplikace detekuje, když `SessionTime` přestane měnit hodnotu.

**Příklad**: 
```ini
quit_stall_seconds = 0.4
```

---

## Sekce `[obs]` - OBS WebSocket připojení

### `ws_url` (povinné)

WebSocket URL OBS serveru.

**Kdy použít**: Změň pokud OBS běží na jiném počítači nebo portu.

**Příklad**: 
```ini
ws_url = ws://127.0.0.1:4455  # lokální
ws_url = ws://192.168.1.100:4455  # síť
```

### `password` (povinné)

Heslo pro OBS WebSocket server.

**Kdy použít**: Musí odpovídat heslu nastavenému v OBS (Tools → WebSocket Server Settings).

**Příklad**: 
```ini
password = tvé_obs_heslo
```

### `required_profile` (volitelné)

Název OBS profilu, který musí být aktivní.

**Kdy použít**: Pokud máš více OBS profilů a chceš, aby switcher fungoval jen s konkrétním.

**Jak to funguje**: Pokud je nastaven, aplikace kontroluje, zda je aktivní tento profil. Pokud ne, nepřepíná scény.

**Příklad**: 
```ini
required_profile = RacingProfile
```

---

## Sekce `[switching]` - Logika přepínání scén

### `autoswitch_default` (povinné)

Výchozí stav automatického přepínání při startu.

**Kdy použít**: 
- `true` - automatické přepínání zapnuté hned po startu
- `false` - automatické přepínání vypnuté (musíš ho zapnout ručně přes API nebo dashboard)

**Příklad**: 
```ini
autoswitch_default = true
```

### `debounce_ms` (povinné)

Čekací doba před přepnutím scény po změně módu (v milisekundách).

**Validace**: musí být **>= 0**.

**Kdy použít**: 
- Vyšší hodnoty (1000-2000ms) = stabilnější, ale pomalejší reakce
- Nižší hodnoty (500-900ms) = rychlejší reakce, ale může dojít k flappingu

**Jak to funguje**: Po změně módu čeká X ms, než skutečně přepne scénu (zabraňuje flappingu).

**Doporučení**: `900` ms je dobrý kompromis.

**Příklad**: 
```ini
debounce_ms = 900
```

### `cooldown_ms` (povinné)

Minimální interval mezi přepnutími scén (v milisekundách).

**Validace**: musí být **>= 0**.

**Kdy použít**: 
- Vyšší hodnoty (1500-2000ms) = zabraňuje příliš rychlému přepínání
- Nižší hodnoty (500-1000ms) = umožňuje rychlejší přepínání

**Jak to funguje**: Po přepnutí scény musí uplynout X ms před dalším přepnutím.

**Doporučení**: `1000` ms (1 sekunda).

**Příklad**: 
```ini
cooldown_ms = 1000
```

### `override_seconds` (povinné)

Délka trvání manuálního override scény (v sekundách).

**Validace**: musí být **>= 0**.

**Kdy použít**: 
- Vyšší hodnoty (180-300s) = override trvá déle
- Nižší hodnoty (60-120s) = override trvá kratší dobu

**Jak to funguje**: Když použiješ override přes API nebo dashboard, trvá X sekund než se vrátí automatické přepínání.

**Doporučení**: `120` sekund (2 minuty).

**Příklad**: 
```ini
override_seconds = 120
```

### `safe_scene` (povinné)

Název scény, která se použije když není iRacing připojen nebo při chybách.

**Kdy použít**: Nastav na scénu, která je bezpečná pro zobrazení (např. menu, idle scéna).

**Příklad**: 
```ini
safe_scene = Idle
```

### `auto_start_broadcast` (výchozí: `false`)

Automatické spuštění OBS broadcastu během loadingu iRacing.

**Kdy použít**: 
- `true` - pokud chceš automaticky spouštět stream během loadingu
- `false` - pokud chceš spouštět stream ručně

**Jak to funguje**: Spustí broadcast v X% průměrné doby loadingu (viz `auto_start_at_percent`).

**Příklad**: 
```ini
auto_start_broadcast = true
```

### `auto_start_at_percent` (výchozí: `50`)

Procento průměrné doby loadingu, kdy se spustí broadcast (0-100).

**Kdy použít**: 
- `30-50` - spustí se brzy během loadingu
- `70-90` - spustí se později, téměř na konci loadingu

**Jak to funguje**: Pokud průměrný loading trvá 12s a nastavíš `50`, broadcast se spustí po 6s.

**Příklad**: 
```ini
auto_start_at_percent = 50
```

### `default_loading_time_seconds` (výchozí: `12.0`)

Výchozí doba loadingu, pokud nemáš historii (použije se při prvním spuštění).

**Kdy použít**: Nastav podle typické doby loadingu na tvém systému.

**Jak to funguje**: Aplikace sleduje historii loadingu a počítá průměr, ale při prvním spuštění použije tuto hodnotu.

**Příklad**: 
```ini
default_loading_time_seconds = 12.0
```

### `auto_stop_stream` (výchozí: `false`)

Automatické zastavení OBS streamu po ukončení iRacing (QUIT mód).

**Kdy použít**: 
- `true` - pokud chceš automaticky zastavit stream po ukončení hry
- `false` - pokud chceš zastavit stream ručně

**Příklad**: 
```ini
auto_stop_stream = true
```

### `stop_stream_after_seconds` (výchozí: `30`)

Po kolika sekundách po QUIT se zastaví stream.

**Kdy použít**: 
- Nižší hodnoty (10-20s) - zastaví se rychle po ukončení
- Vyšší hodnoty (30-60s) - zastaví se později (dává čas na ukončení hry)

**Příklad**: 
```ini
stop_stream_after_seconds = 30
```

---

## Sekce `[hotkeys]` - Globální hotkey (volitelné)

### `restart_hotkey` (volitelné)

Globální klávesová zkratka pro RESTART mód.

**Kdy použít**: Pokud chceš mít možnost přepnout na RESTART scénu při ukončení iRacing (např. pro VR restarty).

**Jak to funguje**: Drž tuto kombinaci kláves když ukončuješ iRacing → aplikace detekuje QUIT a přepne na RESTART scénu místo QUIT.

**Formát**: `modifier+modifier+key` (např. `ctrl+shift+f7`, `alt+r`)

**Příklad**: 
```ini
restart_hotkey = ctrl+shift+f7
```

---

## Sekce `[scenes]` - Mapování módu na OBS scény

Mapování jednotlivých módů iRacing na názvy OBS scén.

**Důležité**: Názvy scén musí přesně odpovídat názvům scén v OBS (case-sensitive)!

### `IDLE` (povinné)

Název OBS scény pro IDLE mód (menu/lobby).

**Kdy nastává**: Když je iRacing v menu nebo lobby.

**Příklad**: 
```ini
IDLE = Idle
```

### `GARAGE` (povinné)

Název OBS scény pro GARAGE mód (garáž ve hře).

**Kdy nastává**: Když je vidět iRacing garage screen (`IsGarageVisible`). Samotné `IsInGarage` / `PlayerCarInGarage` nestačí — ty znamenají jen fyziku auta ve stání, což je true i v lobby hned po loadu.

**Příklad**: 
```ini
GARAGE = Pits
```

### `RACE` (povinné)

Název OBS scény pro RACE mód (na trati).

**Kdy nastává**: Když je hráč na trati v autě.

**Příklad**: 
```ini
RACE = Race
```

### `REPLAY` (povinné)

Název OBS scény pro REPLAY mód (přehrávání).

**Kdy nastává**: Když běží replay v iRacing.

**Příklad**: 
```ini
REPLAY = Replay
```

### `QUIT` (povinné)

Název OBS scény pro QUIT mód (ukončení hry).

**Kdy nastává**: Když je iRacing ukončen (detekce přes `quit_stall_seconds`).

**Příklad**: 
```ini
QUIT = End
```

### `RESTART` (volitelné)

Název OBS scény pro RESTART mód.

**Kdy nastává**: Když je detekován QUIT a zároveň je držen `restart_hotkey`.

**Kdy použít**: Pouze pokud používáš `restart_hotkey`.

**Příklad**: 
```ini
RESTART = Restart
```

---

## Sekce `[dashboards]` - HTML dashboardy (volitelné)

### `dashboard_update_fps` (výchozí: `2`)

Frekvence aktualizace HTML dashboardů (FPS).

**Kdy použít**: 
- Nižší hodnoty (1-2 FPS) = menší zátěž, pomalejší aktualizace
- Vyšší hodnoty (5-10 FPS) = rychlejší aktualizace, větší zátěž

**Doporučení**: `2` FPS (500ms interval) je dostatečné.

**Příklad**: 
```ini
dashboard_update_fps = 2
```

### `dashboard_event_log_size` (výchozí: `50`)

Počet posledních eventů zobrazených v GR dashboardu.

**Kdy použít**: 
- Vyšší hodnoty (100-200) = více historie, ale větší paměť
- Nižší hodnoty (20-50) = méně historie, menší paměť

**Příklad**: 
```ini
dashboard_event_log_size = 50
```

### `dashboard_gr_background_image` (volitelné)

Cesta k obrázku pozadí pro GR dashboard (`/gr-status`).

**Kdy použít**: Pokud chceš vlastní pozadí místo výchozího.

**Formát**: Relativní nebo absolutní cesta k PNG/JPG souboru.

**Příklad**: 
```ini
dashboard_gr_background_image = assets/background.png
```

### `dashboard_gr_logo_obs` (volitelné)

Cesta k logu OBS pro GR dashboard.

**Kdy použít**: Pokud chceš zobrazit OBS logo v dashboardu.

**Formát**: Relativní nebo absolutní cesta k PNG/JPG souboru.

**Příklad**: 
```ini
dashboard_gr_logo_obs = assets/obs_logo.png
```

### `dashboard_gr_logo_iracing` (volitelné)

Cesta k logu iRacing pro GR dashboard.

**Kdy použít**: Pokud chceš zobrazit iRacing logo v dashboardu.

**Formát**: Relativní nebo absolutní cesta k PNG/JPG souboru.

**Příklad**: 
```ini
dashboard_gr_logo_iracing = assets/iracing_logo.png
```

### `dashboard_gr_logo_app` (volitelné)

Cesta k logu aplikace pro GR dashboard.

**Kdy použít**: Pokud chceš zobrazit logo aplikace v dashboardu.

**Formát**: Relativní nebo absolutní cesta k PNG/JPG souboru.

**Příklad**: 
```ini
dashboard_gr_logo_app = assets/app_logo.png
```

### `dashboard_vr_icons_path` (volitelné)

Cesta k adresáři s ikonami pro VR dashboard (`/vr-status`).

**Kdy použít**: Pokud chceš vlastní ikony pro VR dashboard místo výchozích.

**Formát**: Relativní nebo absolutní cesta k adresáři obsahujícímu ikony.

**Jak to funguje**: VR dashboard používá ikony z tohoto adresáře pro zobrazení stavu.

**Příklad**: 
```ini
dashboard_vr_icons_path = assets/vr_icons/
```

---

## Sekce `[stream_chapters]` - Kapitoly streamu přes WS (volitelné)

In-memory chapter markery pro aktuální OBS stream. Emitují se jako **additive** zprávy na `WS /ws` (viz `API.md`). **Nepíšou** YouTube description ani OBS `CreateRecordChapter` (to je budoucí práce).

Výchozí stav: vypnuto. Bez migrace — existující instalace se chovají stejně, dokud sekci nezapneš.

### `enabled` (výchozí: `false`)

Master switch. Při `false` se markery neukládají, neposílají se chapter WS zprávy a `/status` pole `stream_chapters` chybí.

### `start_title` (výchozí: `Stream start`)

Titulek start markeru při přechodu na `streaming: true` (`offset_seconds: 0`).

Krátký OBS flicker (< 2 s stop) **nevyvolá** clear ani nový start marker.

### `trigger_session_types` (výchozí: `Practice,Qualify,Race`)

Čárkou oddělené `session_type` hodnoty, při jejich **změně** (během streamu) se přidá marker. `Test` / prázdné / null se ignorují.

### Title templates (volitelné)

- `title_practice`, `title_qualify`, `title_race`, … — prefix `title_` + lowercase session type
- nebo holé klíče `practice` / `qualify` / `race`

Když template chybí, použije se raw `session_type`.

**Příklad**:
```ini
[stream_chapters]
enabled = true
start_title = Stream start
trigger_session_types = Practice,Qualify,Race
title_practice = Practice
title_qualify = Qualifying
title_race = Race
```

---

## Cesty v konfiguraci

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

---

## Hot-reload (`POST /config/reload`)

Po změně `config.ini` můžeš zavolat `POST /config/reload` (nebo tlačítko v dashboardu, pokud je). Aplikace **nepřepisuje** celý proces — živě se přenačte sdílený runtime config.

Response obsahuje diff vůči předchozímu runtime configu:

- `applied_live` — změněné klíče ze seznamu níže (platí ihned)
- `needs_restart` — změněné klíče ze restart whitelistu (stále vyžadují restart procesu)

GR dashboard po reloadu zobrazí toast a panel s oběma seznamy.

### Platí ihned (bez restartu)

- `[scenes]` mapování + `switching.safe_scene`
- `switching.debounce_ms`, `cooldown_ms`, `override_seconds`, `autoswitch_default`
- `iracing.poll_hz`
- `switching.auto_start_broadcast`, `auto_start_at_percent`, `default_loading_time_seconds`
- `switching.auto_stop_stream`, `stop_stream_after_seconds`
- většina `[dashboards]` klíčů čtených při requestu
- `[stream_chapters].*` (enabled, titles, triggers)
- overlay sampling Hz, battle thresholdy, HR/sysinfo feature flags, theme, event priority (`PUT /api/config` nebo reload INI)
- `overlay.language`, `overlay.v4_*`, `overlay.session_tape` a všechny `event_engine.*` flagy
- `commentary.enabled`, `commentary.use_hr_emotion`, `commentary.cooldown_s`, `commentary.max_utterance_s`, `commentary.tts_backend`, `commentary.tts_voice`, `commentary.tts_rate`, `commentary.audio_device`, `commentary.duck_input`, `commentary.duck_ratio`, `commentary.duck_fade_ms`, `commentary.decision_log_size`

### Vyžaduje restart procesu

- `app.http_host`, `app.http_port`
- `app.log_file` / rotace logů / `log_level` (handler už běží)
- `obs.ws_url`, `obs.password`, `obs.required_profile`
- OAuth / YouTube credentials (env / config)
- `hotkeys.restart_hotkey`
- `system_info.lhm_dll_path`
- `overlay.session_tape_dir`

## Overlay / race pipeline

Volitelné sekce v `config.ini` (defaults platí i bez nich). Kompletní klíče jsou v [`config/config.example.ini`](config/config.example.ini).

- `[sampling]` `default_hz` — globální vzorkování; `[sampling.race]`, `[sampling.system]`, `[sampling.bio]` můžou přetížit. `bio` 0 / prázdné = BLE notifications (ne poll). Clamp 0.2–30 Hz.
- `[overlay]` theme (`cyber_racing` | `stealth_graphite` | `night_attack` | `pit_wall_dark` | `pit_wall_light`) — V4 packs in `src/irswitch/web/themes-v4/<theme>/` (V3 legacy assets for the classic three remain under `src/irswitch/web/themes/<theme>/assets/`)
- `[overlay]` `language` (`en` | `cs`, default `en`) — overlay copy language. Event payloads carry copy tokens; the renderer resolves them via `irswitch.overlay.i18n.resolve_copy()`. English is the base catalog, missing translations fall back to it. Independent of `[app]` `language`, which drives the dashboards.
- `[overlay]` `v4_assets`, `v4_renderer` (`config.example.ini` defaults `true` for the full V4 demo profile; keep `false` in production until you want V4 live) — overlay V4 rollout flags. With `v4_renderer=true`, transient widgets use the V4 layer renderer and sysinfo uses V4 layered assets from `themes-v4/`.
- `[overlay]` `session_tape` (default **true**) — session HUD JSONL tape: WS eventy, DecisionLog (emitted/suppressed/preempted), změna OBS scény / driving mode, aktivní V4 stories. Ne telemetry ticky. Soubor `recordings/overlay-<utc>-<subsession>-<session>.jsonl`. Gate je stejný session type jako switcher (`extract_session_type`: Practice / Qualify / Race → overlay_mode PRACTICE/QUALIFYING/RACE). Warmup/Test tape nezapisují. Vypni `session_tape = false`.
- `[overlay]` `session_tape_dir` (default `recordings`) — adresář tape souborů; změna vyžaduje restart. `..` v cestě se ignoruje.
- `[event_engine]` `v2_payload`, `practice`, `quali_projection`, `overtake_classifier`, `pit_story`, `hr_pressure` (`config.example.ini` defaults `true` for full V4 demo; production defaults remain `false` in code) — event-engine rollout flags. All off = current MVP event behaviour. With `v2_payload=true`, the overlay bus emits V4 envelopes (wire phases include `ACTIVE`). `practice` enables practice minisector stories (`GAIN_FOUND`, `TIME_LOST`, `TARGET_LOCKED`). `quali_projection` enables qualifying projected lap / position attack / hot lap stories.
- `[commentary]` `enabled` (default `false`), `use_hr_emotion` (default `true`), `cooldown_s` (default `4.0`), `max_utterance_s` (default `6.0`), `tts_backend` (`auto`|`sapi`|`espeak`|`null`, default `auto`), `tts_voice` (empty = system default), `tts_rate` (`-10`…`10`, default `0`), `audio_device` (empty = Windows default playback; substring match e.g. `CABLE Input` routes SAPI to VB-CABLE so you do not hear it in the headset; stereo is preferred over 16ch), `duck_input` (empty = no ducking; OBS audio source name e.g. `Zvuk plochy`), `duck_ratio` (default `0.25` = 25% of the original OBS volume while commentary speaks, then restore), `duck_fade_ms` (default `750`; `0` = instant), `decision_log_size` (default `32`, ring buffer for speak/skip reasons) — spoken commentary. `auto` uses Windows SAPI (memory + winmm to `audio_device`) or `espeak-ng` on Linux. Test page: [`GET /commentary`](API.md#get-commentary). Live feed stays silent while `enabled=false`. See [COMMENTARY_ENGINE.md](COMMENTARY_ENGINE.md) and [docs/commentary_product_suite.md](docs/commentary_product_suite.md).

**Full V4 demo profile** (mirrored in `config/config.example.ini`; production code defaults stay off until you opt in):

```ini
[overlay]
theme = cyber_racing
language = cs
v4_assets = true
v4_renderer = true
session_tape = true

[event_engine]
v2_payload = true
practice = true
quali_projection = true
overtake_classifier = true
pit_story = true
hr_pressure = true
```

Golden gallery URL: `/overlay/golden?demo=1&renderer=v4&layout=golden&fixture=all&motion=off`
- `[battle.hunting]` / `[battle.hunted]` hysteresis
- `[heart_rate]` + `[heart_rate.bluetooth]` — `device=auto` picks a scanner result that **advertises** Heart Rate UUID `0x180D` (bleak `return_adv`, not empty WinRT `metadata.uuids`). Name fallback is only `heart` / `hr` / `hrm`. After GATT connect the provider calls `BleakClient.pair()` (fail-soft) so Windows can bond before `0x2A37` notify. Pin `device` to a name/address substring if more than one HR radio is nearby.
- `[system_info]` (+ cpu/gpu/memory enabled). CPU package on Windows: LibreHardwareMonitor 0.9.5+ HTTP `http://127.0.0.1:8085/data.json` (Remote Web Server; File → Hardware → CPU). If LHM binds a LAN NIC, overlay reads `LibreHardwareMonitor.config`. Older LHM WMI `root\LibreHardwareMonitor`. Stock Windows has no CPU package power class. FPS/frametime come from iRacing (empty in the garage).
- `[events]` / `[events.priorities]`

UI editor: `GET /config` (schema-driven). Zápis jen z localhost s hlavičkou `X-Requested-With: irswitch`.
