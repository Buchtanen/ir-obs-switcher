# Testy - Dokumentace

Tento dokument popisuje všechny testy v projektu iRacing OBS Switcher. Pro základní informace o projektu viz [README.md](README.md).

## Přehled

Projekt obsahuje **84+ unit testů** pokrývající všechny klíčové komponenty:

- **Extractors** (4 testy) - extrakce módu z iRacing dat
- **Policy** (1 test) - mapování módu na scény
- **iRacing Reader** (8 testů) - čtení dat z iRacing SDK
- **OBS Client** (11 testů) - komunikace s OBS WebSocket
- **State Machine** (11 testů) - logika přepínání scén
- **Version** (`tests/test_version.py`) - `resolve_version()` (pyproject vs metadata vs EXE)
- **API Server** (6 testů) - REST a WebSocket API
- **Main Service** (8 testů) - včetně 5 nových testů pro stream cache
- **Loading Tracker** (9 testů) - sledování doby loadingu
- **Event Log** (9 testů) - thread-safe event log systém
- **E2E Main Loop** (7 testů) - end-to-end testy hlavní smyčky
- **Overlay** — sampling, race context, eventy, BLE parser, sysinfo, config write, overlay WS, theme asset pack, dry-test demo (`tests/test_sampling.py`, `test_race_context.py`, `test_event_*.py`, `test_bio.py`, `test_system_info.py`, `test_overlay_*.py`)

## Spuštění testů

```powershell
# Všechny testy
pytest

# Konkrétní test soubor
pytest tests/test_state_machine.py

# S verbose výstupem
pytest -v

# S detailním výstupem při selhání
pytest -v --tb=short
```

Viz také [README.md](README.md#testy) pro základní instrukce.

---

## 1. Extractors (`tests/test_extractors.py`)

**Cíl**: Ověřit správnou extrakci `DrivingMode` z iRacing SDK dat podle priorit.

**Testované soubory**: `src/irswitch/iracing/extractors.py`

### Testy

#### `test_extract_mode_prioritizes_replay`
- **Co testuje**: Priorita REPLAY módu
- **Proč**: REPLAY má nejvyšší prioritu - i když je hráč na trati nebo v garáži, pokud běží replay, musí být detekován jako REPLAY
- **Očekávaný výsledek**: `DrivingMode.REPLAY` i když jsou nastaveny i jiné flagy

#### `test_extract_mode_race_when_on_track`
- **Co testuje**: Detekce RACE módu když je hráč na trati
- **Proč**: Základní funkcionalita - když `IsOnTrack` je True, musí být detekován RACE mód
- **Očekávaný výsledek**: `DrivingMode.RACE`

#### `test_extract_mode_garage_when_garage_visible`
- **Co testuje**: Detekce GARAGE módu když je vidět garage screen (`IsGarageVisible`)
- **Proč**: Správná detekce garáže je důležitá pro přepnutí na správnou scénu
- **Očekávaný výsledek**: `DrivingMode.GARAGE`
- **Poznámka**: Testuje i string hodnoty ("true") pro robustnost

#### `test_extract_mode_in_garage_physics_without_screen_is_lobby`
- **Co testuje**: `IsInGarage` bez `IsGarageVisible` není GARAGE
- **Proč**: Po loadu je auto ve stání i v lobby; to nesmí přepnout na Back
- **Očekávaný výsledek**: `DrivingMode.LOBBY`

#### `test_extract_mode_session_screen_with_stall_physics_is_lobby`
- **Co testuje**: Session screen + stall physics = LOBBY
- **Proč**: GetInCar lobby po joinu session
- **Očekávaný výsledek**: `DrivingMode.LOBBY`

#### `test_extract_mode_garage_fallback_without_visible_flag`
- **Co testuje**: Fallback když `IsGarageVisible` v snapshotu chybí
- **Proč**: Starší/částečná telemetrie
- **Očekávaný výsledek**: `DrivingMode.GARAGE`

#### `test_extract_mode_idle_by_default`
- **Co testuje**: Výchozí mód když nejsou žádná data
- **Proč**: Když iRacing není připojen nebo data nejsou dostupná, musí být vrácen IDLE jako bezpečný výchozí stav
- **Očekávaný výsledek**: `DrivingMode.IDLE`

---

## 2. Policy (`tests/test_policy.py`)

**Cíl**: Ověřit mapování `DrivingMode` na názvy OBS scén.

**Testované soubory**: `src/irswitch/logic/policy.py`

### Testy

#### `test_policy_maps_modes_to_scenes`
- **Co testuje**: Mapování módu na scény a fallback na safe_scene
- **Proč**: 
  - Policy musí správně mapovat známé módy na scény
  - Pro neznámé módy musí použít safe_scene jako fallback
- **Očekávaný výsledek**: 
  - IDLE → "Idle"
  - GARAGE → "Pits"
  - REPLAY (není v mapě) → "Safe" (safe_scene)

---

## 3. iRacing Reader (`tests/test_reader.py`)

**Cíl**: Ověřit async wrapper pro pyirsdk a správné čtení dat.

**Testované soubory**: `src/irswitch/iracing/reader.py`

### Testy

#### `test_read_mode_connected_race`
- **Co testuje**: Čtení RACE módu když je iRacing připojen
- **Proč**: Základní funkcionalita - reader musí správně číst a extrahovat mód
- **Očekávaný výsledek**: `DrivingMode.RACE`

#### `test_read_mode_connected_replay`
- **Co testuje**: Čtení REPLAY módu
- **Proč**: Ověření správné detekce replay módu
- **Očekávaný výsledek**: `DrivingMode.REPLAY`

#### `test_read_mode_connected_garage`
- **Co testuje**: Čtení GARAGE módu
- **Proč**: Ověření správné detekce garáže
- **Očekávaný výsledek**: `DrivingMode.GARAGE`

#### `test_read_mode_connected_idle`
- **Co testuje**: Čtení IDLE módu když nejsou nastaveny žádné flagy
- **Proč**: Výchozí stav když není aktivní žádný jiný mód
- **Očekávaný výsledek**: `DrivingMode.IDLE`

#### `test_read_mode_disconnected`
- **Co testuje**: Chování když iRacing není připojen
- **Proč**: Reader musí správně detekovat disconnected stav a vrátit None
- **Očekávaný výsledek**: `None`

#### `test_read_mode_missing_variables`
- **Co testuje**: Robustnost při chybějících proměnných
- **Proč**: iRacing SDK může vracet chybějící proměnné - reader musí to zvládnout bez crash
- **Očekávaný výsledek**: Vrací IDLE nebo None (podle implementace)

#### `test_is_connected`
- **Co testuje**: Metoda `is_connected()`
- **Proč**: Správná detekce připojení je důležitá pro state machine
- **Očekávaný výsledek**: `True` když připojen, `False` když ne

#### `test_read_vars`
- **Co testuje**: Synchronní metoda `read_vars()` pro čtení proměnných
- **Proč**: Základní funkcionalita pro čtení dat z SDK
- **Očekávaný výsledek**: Vrací dictionary s hodnotami, None pro chybějící proměnné

---

## 4. OBS Client (`tests/test_obs_client.py`)

**Cíl**: Ověřit async wrapper pro obs-websocket v5 s retry logikou.

**Testované soubory**: `src/irswitch/obs/client.py`

### Testy

#### `test_connect_success`
- **Co testuje**: Úspěšné připojení k OBS
- **Proč**: Základní funkcionalita - klient se musí umět připojit
- **Očekávaný výsledek**: `is_connected()` vrací `True`

#### `test_connect_retry_on_failure`
- **Co testuje**: Retry logika při selhání připojení
- **Proč**: OBS může být dočasně nedostupný - klient musí zkusit znovu s backoff
- **Očekávaný výsledek**: Po retry se připojí úspěšně

#### `test_connect_max_retries_exceeded`
- **Co testuje**: Chování když jsou vyčerpány všechny retry pokusy
- **Proč**: Musí vyhodit `ConnectionError` když se nepodaří připojit
- **Očekávaný výsledek**: `ConnectionError` exception

#### `test_disconnect`
- **Co testuje**: Graceful disconnect
- **Proč**: Správné ukončení připojení je důležité pro cleanup
- **Očekávaný výsledek**: `is_connected()` vrací `False` po disconnect

#### `test_get_current_scene_success`
- **Co testuje**: Získání aktuální scény z OBS
- **Proč**: State machine potřebuje znát aktuální scénu pro rozhodování
- **Očekávaný výsledek**: Vrací název aktuální scény

#### `test_get_current_scene_not_connected`
- **Co testuje**: Chování když není připojen
- **Proč**: Musí vrátit None místo crash
- **Očekávaný výsledek**: `None`

#### `test_get_current_scene_error`
- **Co testuje**: Error handling při chybě
- **Proč**: Network chyby jsou běžné - klient musí být robustní
- **Očekávaný výsledek**: Vrací None a označí jako disconnected

#### `test_set_scene_success`
- **Co testuje**: Úspěšné přepnutí scény
- **Proč**: Hlavní funkcionalita - přepnutí scény v OBS
- **Očekávaný výsledek**: Vrací `True`, scéna se přepne

#### `test_set_scene_idempotent`
- **Co testuje**: Idempotentní chování - přepnutí na stejnou scénu
- **Proč**: Pokud už jsme na cílové scéně, nemělo by se nic stát (optimalizace)
- **Očekávaný výsledek**: Vrací `True` bez volání OBS API

#### `test_set_scene_not_connected`
- **Co testuje**: Chování když není připojen
- **Proč**: Musí vrátit False místo crash
- **Očekávaný výsledek**: `False`

#### `test_set_scene_error`
- **Co testuje**: Error handling při chybě přepnutí
- **Proč**: OBS může být dočasně nedostupný - klient musí být robustní
- **Očekávaný výsledek**: Vrací False a označí jako disconnected

---

## 5. State Machine (`tests/test_state_machine.py`)

**Cíl**: Ověřit logiku přepínání scén včetně debounce, cooldown a override.

**Testované soubory**: `src/irswitch/logic/state_machine.py`

### Testy

#### `test_tick_mode_change_triggers_debounce`
- **Co testuje**: Debounce logika při změně módu
- **Proč**: Debounce zabraňuje flappingu - čeká na stabilní stav před přepnutím
- **Očekávaný výsledek**: Při změně módu se target_scene nezmění okamžitě, ale začne debounce timer

#### `test_tick_debounce_expires_and_switches`
- **Co testuje**: Přepnutí po expiraci debounce
- **Proč**: Po čekání na stabilní stav se musí scéna přepnout
- **Očekávaný výsledek**: Po uplynutí debounce_ms se target_scene aktualizuje

#### `test_tick_cooldown_prevents_rapid_switches`
- **Co testuje**: Cooldown logika - minimální interval mezi přepnutími
- **Proč**: Cooldown zabraňuje příliš rychlému přepínání scén
- **Očekávaný výsledek**: 
  - Při pokusu o přepnutí před uplynutím cooldown se nepřepne
  - Po uplynutí cooldown se přepne

#### `test_tick_override_active`
- **Co testuje**: Override má přednost před normálním módem
- **Proč**: Override umožňuje dočasné přepnutí scény nezávisle na iRacing módu
- **Očekávaný výsledek**: I když je jiný mód, override scéna se použije

#### `test_tick_override_expires`
- **Co testuje**: Expirace override po časovém limitu
- **Proč**: Override musí automaticky expirovat a vrátit se k normálnímu módu
- **Očekávaný výsledek**: Po expiraci se použije normální mód z iRacing

#### `test_tick_autoswitch_disabled`
- **Co testuje**: Chování když je autoswitch vypnutý
- **Proč**: Uživatel musí mít možnost vypnout automatické přepínání
- **Očekávaný výsledek**: I když se změní mód, scéna se nepřepne

#### `test_tick_iracing_disconnected`
- **Co testuje**: Chování když iRacing není připojen
- **Proč**: iRacing disconnect je normální stav, ne error - služba musí pokračovat
- **Očekávaný výsledek**: Zachová aktuální stav, nepřepíná scény

#### `test_apply_override`
- **Co testuje**: Aplikace override s časovým limitem
- **Proč**: Override musí být aplikovatelný s konfigurovatelným časovým limitem
- **Očekávaný výsledek**: Override je nastaven s `override_until` timestampem

#### `test_toggle_autoswitch`
- **Co testuje**: Přepínání autoswitch on/off
- **Proč**: Uživatel musí mít možnost zapnout/vypnout autoswitch
- **Očekávaný výsledek**: Autoswitch flag se přepne

#### `test_tick_same_scene_no_switch`
- **Co testuje**: Optimalizace - nepřepínat když je target stejný jako current
- **Proč**: Zbytečné přepínání na stejnou scénu je neefektivní
- **Očekávaný výsledek**: `last_switch_ts` se neaktualizuje, žádné přepnutí

#### `test_post_load_garage_flicker_does_not_switch_to_garage`
- **Co testuje**: První GARAGE po CONNECTING nesmí přepnout scénu
- **Proč**: Po loadu SDK hlásí stall physics (falešný GARAGE) ještě v lobby
- **Očekávaný výsledek**: ignore GARAGE, po přechodu na LOBBY target lobby scéna

#### `test_post_load_stable_garage_switches_after_grace`
- **Co testuje**: Stabilní GARAGE 3 s po loadu přepne na garage scénu
- **Proč**: Skutečná garáž (load přímo do garage UI) se nesmí zaseknout
- **Očekávaný výsledek**: `grace_period_timeout:GARAGE`

#### `test_post_load_race_still_switches_after_debounce`
- **Co testuje**: RACE po CONNECTING jde hned po debounce
- **Proč**: Grace period se netýká RACE/REPLAY
- **Očekávaný výsledek**: po debounce target race/VR scéna

---

## 6. API Server (`tests/test_api.py`)

**Cíl**: Ověřit REST API endpointy a WebSocket funkcionalitu.

**Testované soubory**: `src/irswitch/server/api.py`, `src/irswitch/server/commands.py`

### Testy

#### `test_get_status`
- **Co testuje**: GET `/status` endpoint
- **Proč**: API musí vracet aktuální stav služby
- **Očekávaný výsledek**: JSON s aktuálním stavem (mode, scenes, connections, atd.)

#### `test_get_status_not_initialized`
- **Co testuje**: Chování když služba není inicializovaná
- **Proč**: API musí správně reagovat na neinicializovaný stav
- **Očekávaný výsledek**: HTTP 503 s error message

#### `test_override`
- **Co testuje**: POST `/override` endpoint
- **Proč**: API musí umožnit aplikaci override scény
- **Očekávaný výsledek**: Override je aplikován, vrací aktualizovaný stav

#### `test_override_missing_scene`
- **Co testuje**: Validace - chybějící scene parametr
- **Proč**: API musí validovat vstupní data
- **Očekávaný výsledek**: HTTP 400 s error message

#### `test_override_invalid_seconds`
- **Co testuje**: Validace - neplatný seconds parametr
- **Proč**: API musí validovat časový limit (musí být pozitivní integer)
- **Očekávaný výsledek**: HTTP 400 s error message

#### `test_toggle_autoswitch`
- **Co testuje**: POST `/autoswitch/toggle` endpoint
- **Proč**: API musí umožnit přepnutí autoswitch
- **Očekávaný výsledek**: Autoswitch flag se přepne, vrací aktualizovaný stav

---

## 7. Main Service (`tests/test_main.py`)

**Cíl**: Ověřit inicializaci a spuštění hlavní služby včetně stream cache optimalizace.

**Testované soubory**: `src/irswitch/main.py`

### Testy

#### `test_run_service_initialization`
- **Co testuje**: Inicializace všech komponent služby
- **Proč**: Všechny komponenty (reader, OBS client, state machine, API server) se musí správně inicializovat
- **Očekávaný výsledek**: Všechny komponenty jsou vytvořeny a připojeny

#### `test_main_invalid_config`
- **Co testuje**: Chování při neplatné konfiguraci
- **Proč**: Aplikace musí správně ohlásit chybu při neplatném config souboru
- **Očekávaný výsledek**: Exit code 1, error message

#### `test_main_valid_config`
- **Co testuje**: Parsování validní konfigurace
- **Proč**: Aplikace musí správně načíst a parsovat config soubor
- **Očekávaný výsledek**: Config je načten bez chyb

#### `test_stream_cache_fresh_scenario`
- **Co testuje**: Fresh cache je použito přímo pro auto-start rozhodování
- **Proč**: Když je cache mladší 5 sekund, nemusíme volat API - stačí cached hodnoty
- **Očekávaný výsledek**: Cache age <= 5000ms, použijeme cached `is_ready` hodnotu

#### `test_stream_cache_stale_scenario`
- **Co testuje**: Stará cache (5-10s) triggruje API fallback
- **Proč**: Pro spolehlivost potřebujeme aktuální data když cache stárne
- **Očekávaný výsledek**: 5000 < cache_age <= 10000ms, použijeme API fallback

#### `test_stream_cache_expired_scenario`
- **Co testuje**: Expired cache (>10s) vynutí API volání
- **Proč**: Příliš stará cache není spolehlivá - musíme získat свежие данные
- **Očekávaný výsledek**: Cache age > 10000ms, forced API call

#### `test_stream_no_cache_scenario`
- **Co testuje**: Absence cache vynutí API volání
- **Proč**: Když stream nikdy nebyl vybrán, musíme získat stav z API
- **Očekávaný výsledek**: `last_stream_selected = False`, API call required

#### `test_stream_cache_constants`
- **Co testuje**: Konstanty cache threshold jsou definovány správně
- **Proč**: Module-level konstanty musí být importovatelné a správně nastavené
- **Očekávaný výsledek**: `STREAM_CACHE_FRESH_MS = 5000`, `STREAM_CACHE_GRACE_MS = 10000`

---

## 8. Loading Tracker (`tests/test_loading_tracker.py`)

**Cíl**: Ověřit sledování doby trvání loading screenů iRacing a ukládání historie.

**Testované soubory**: `src/irswitch/util/loading_tracker.py`

### Testy

#### `test_load_empty_history`
- **Co testuje**: Inicializace trackeru s prázdnou historií
- **Proč**: Při prvním spuštění nebo bez historie musí použít výchozí čas
- **Očekávaný výsledek**: `get_average_loading_time()` vrací `default_loading_time_seconds`

#### `test_load_existing_history`
- **Co testuje**: Načtení existující historie z JSON souboru
- **Proč**: Tracker musí správně načíst a použít uloženou historii
- **Očekávaný výsledek**: Průměrná doba loadingu se počítá z načtené historie

#### `test_start_loading`
- **Co testuje**: Označení začátku loadingu
- **Proč**: Tracker musí správně detekovat start loadingu
- **Očekávaný výsledek**: `is_loading()` vrací `True` po `start_loading()`

#### `test_end_loading_without_start`
- **Co testuje**: Ukončení loadingu bez předchozího startu
- **Proč**: Robustnost - tracker musí zvládnout edge case
- **Očekávaný výsledek**: Vrací `None`, historie se nezmění

#### `test_start_end_loading`
- **Co testuje**: Kompletní cyklus loadingu (start → end)
- **Proč**: Základní funkcionalita - měření doby trvání
- **Očekávaný výsledek**: 
  - `end_loading()` vrací správnou dobu v sekundách
  - Doba se přidá do historie
  - `is_loading()` vrací `False`

#### `test_history_limit`
- **Co testuje**: Omezení velikosti historie na `MAX_HISTORY_SIZE` (50)
- **Proč**: Historie nesmí růst neomezeně
- **Očekávaný výsledek**: Po přidání více než 50 záznamů se zachová jen posledních 50 (FIFO)

#### `test_get_average_with_history`
- **Co testuje**: Výpočet průměru s existující historií
- **Proč**: Průměr se používá pro automatické spuštění broadcastu
- **Očekávaný výsledek**: Průměr se počítá z historie, ne z výchozí hodnoty

#### `test_get_average_without_history`
- **Co testuje**: Výpočet průměru bez historie
- **Proč**: Při prvním spuštění musí použít výchozí hodnotu
- **Očekávaný výsledek**: Vrací `default_loading_time_seconds`

#### `test_save_history`
- **Co testuje**: Uložení historie do JSON souboru
- **Proč**: Historie se musí persistovat mezi spuštěními
- **Očekávaný výsledek**: Po `end_loading()` se historie uloží do souboru

#### `test_duplicate_start_loading`
- **Co testuje**: Ignorování duplicitních `start_loading()` volání
- **Proč**: Robustnost - tracker nesmí resetovat čas při duplicitním volání
- **Očekávaný výsledek**: Druhé `start_loading()` se ignoruje, čas se počítá od prvního

#### `test_cancel_loading_does_not_record`
- **Co testuje**: `cancel_loading()` zahodí clock bez zápisu do historie
- **Proč**: QUIT / zmizení procesu nesmí kazit průměr
- **Očekávaný výsledek**: historie prázdná, průměr = default

#### `test_keep_clock_during_connecting_after_auto_start`
- **Co testuje**: CONNECTING po auto-startu se nezapisuje
- **Proč**: dřív se ukládalo ~7 s (delay auto-startu) místo ~55 s do hry
- **Očekávaný výsledek**: `decide_process_loading_clock` → `keep`

#### `test_record_when_obs_is_on_in_sim_scene`
- **Co testuje**: zápis až když OBS je na LOBBY/RACE scéně
- **Proč**: to je přepnutí do hry
- **Očekávaný výsledek**: `record`

#### `test_cancel_on_quit_or_process_gone`
- **Co testuje**: QUIT a zmizení procesu → cancel; GARAGE neuzavírá clock
- **Proč**: stall flicker / End scéna nesmí jít do průměru
- **Očekávaný výsledek**: `cancel` / `keep` podle módu

---

## 10. Event Log (`tests/test_event_log.py`)

**Cíl**: Ověřit thread-safe event log systém pro ukládání událostí.

**Testované soubory**: `src/irswitch/server/event_log.py`

### Testy

#### `test_add_event`
- **Co testuje**: Přidání eventu do logu
- **Proč**: Základní funkcionalita - eventy se musí ukládat
- **Očekávaný výsledek**: Event se přidá s timestampem, typem, zprávou a daty

#### `test_get_recent_events`
- **Co testuje**: Získání posledních N eventů
- **Proč**: Dashboards potřebují zobrazit poslední události
- **Očekávaný výsledek**: Vrací poslední N eventů (nejnovější poslední)

#### `test_get_all_events`
- **Co testuje**: Získání všech eventů
- **Proč**: Pro debugging a analýzu
- **Očekávaný výsledek**: Vrací všechny eventy v logu

#### `test_event_log_max_size`
- **Co testuje**: Omezení velikosti logu (FIFO)
- **Proč**: Log nesmí růst neomezeně
- **Očekávaný výsledek**: Po přidání více než `max_size` eventů se zachová jen posledních `max_size`

#### `test_event_timestamp`
- **Co testuje**: Timestamp každého eventu
- **Proč**: Eventy musí mít časovou značku pro zobrazení
- **Očekávaný výsledek**: Každý event má `timestamp > 0` (monotonic time v ms)

#### `test_get_recent_events_zero_count`
- **Co testuje**: Získání eventů s `count=0`
- **Proč**: Edge case - `count=0` by mělo vrátit všechny eventy
- **Očekávaný výsledek**: Vrací všechny eventy

#### `test_get_recent_events_more_than_available`
- **Co testuje**: Získání více eventů než je dostupných
- **Proč**: Robustnost - nesmí crashnout
- **Očekávaný výsledek**: Vrací všechny dostupné eventy

#### `test_clear_events`
- **Co testuje**: Vymazání všech eventů
- **Proč**: Pro resetování logu
- **Očekávaný výsledek**: Po `clear()` je log prázdný

#### `test_global_event_log`
- **Co testuje**: Globální instance event logu
- **Proč**: Aplikace používá globální instanci pro sdílení mezi komponentami
- **Očekávaný výsledek**: `get_event_log()` vrací stejnou instanci, `set_event_log()` ji může změnit

---

## 11. E2E Main Loop (`tests/test_main_loop_e2e.py`)

**Cíl**: Ověřit end-to-end funkcionalitu hlavní smyčky s mockovanými iRacing a OBS.

**Testované soubory**: `src/irswitch/main.py`

### Testy

#### `test_main_loop_mode_change_triggers_scene_switch`
- **Co testuje**: Změna módu spustí přepnutí scény přes OBS
- **Proč**: Hlavní funkcionalita - změna módu musí vést k přepnutí scény
- **Očekávaný výsledek**: `set_scene()` je voláno s správnou scénou po debounce

#### `test_main_loop_debounce_delays_switch`
- **Co testuje**: Debounce zpožďuje přepnutí scény
- **Proč**: Debounce zabraňuje flappingu při rychlých změnách
- **Očekávaný výsledek**: `set_scene()` není voláno během debounce, ale po jeho expiraci

#### `test_main_loop_cooldown_prevents_rapid_switches`
- **Co testuje**: Cooldown zabraňuje rychlému přepínání scén
- **Proč**: Cooldown zabraňuje příliš častým přepnutím
- **Očekávaný výsledek**: Po prvním přepnutí se další přepnutí zpozdí o cooldown

#### `test_main_loop_autoswitch_disabled_no_switch`
- **Co testuje**: Vypnutý autoswitch zabraňuje přepínání
- **Proč**: Uživatel musí mít možnost vypnout automatické přepínání
- **Očekávaný výsledek**: `set_scene()` není voláno když je `autoswitch=False`

#### `test_main_loop_override_takes_precedence`
- **Co testuje**: Override má prioritu před automatickým přepínáním
- **Proč**: Override umožňuje manuální přepnutí scény
- **Očekávaný výsledek**: `set_scene()` je voláno s override scénou, ne s módovou scénou

#### `test_main_loop_connection_state_tracking`
- **Co testuje**: Sledování změn stavu připojení
- **Proč**: Aplikace musí detekovat připojení/odpojení iRacing a OBS
- **Očekávaný výsledek**: Eventy `connection_lost`/`connection_restored` jsou logovány

#### `test_main_loop_scene_switch_logs_event`
- **Co testuje**: Přepnutí scény je logováno do event logu
- **Proč**: Dashboards potřebují zobrazit historii přepnutí
- **Očekávaný výsledek**: Event `scene_switch` je přidán do event logu

---

## 12. Ladění na reálném systému

**Cíl**: Ověřit funkcionalitu aplikace na reálném systému s iRacing a OBS.

**Poznámka**: Tyto testy jsou manuální a vyžadují běžící iRacing a OBS.

### Dokončené úkoly ✅

#### ✅ `debug_obs_connection_states`
- **Co bylo testováno**: Různé stavy připojení OBS
- **Výsledek**: 
  - ✅ Aplikace správně rozlišuje mezi "OBS not running" (ConnectionRefusedError) a "OBS connection failed" (autentizace)
  - ✅ Notifikace se zobrazují s přesnými zprávami
  - ✅ Periodické notifikace fungují s cooldown mechanismem
- **Status**: Dokončeno

#### ✅ `debug_obs_scene_validation`
- **Co bylo testováno**: Validace scén při připojení OBS
- **Výsledek**:
  - ✅ Aplikace kontroluje všechny konfigurované scény při připojení OBS
  - ✅ Zobrazuje chybové hlášení s chybějícími scénami a seznamem dostupných scén
  - ✅ Aplikace pokračuje v běhu i při chybějících scénách (graceful degradation)
- **Status**: Dokončeno


#### ✅ `debug_logging`
- **Co bylo testováno**: Debug logování do `.cursor/debug.log`
- **Výsledek**:
  - ✅ Logy se zapisují do správného souboru
  - ✅ Strukturované NDJSON logy pro analýzu
  - ✅ Logování pokrývá klíčové body v kódu
- **Status**: Dokončeno

#### ✅ `debug_notifications`
- **Co bylo testováno**: Windows notifikace pro změny připojení
- **Výsledek**:
  - ✅ MessageBox notifikace fungují spolehlivě
  - ✅ PowerShell toast notifikace jako sekundární metoda
  - ✅ Notifikace lze vypnout přes `notifications_enabled = false` v configu
- **Status**: Dokončeno

### Dokončené úkoly (iRacing) ✅

#### ✅ `debug_iracing_connection`
- **Co bylo testováno**: Připojení k iRacing a detekce stavu
- **Výsledek**:
  - ✅ Aplikace správně detekuje připojení/odpojení iRacing
  - ✅ Periodická obnova SDK stavu (`startup()`) pro detekci nových připojení
  - ✅ Timeout pro SDK volání (2s) zabraňuje zablokování
- **Status**: Dokončeno

#### ✅ `debug_iracing_mode_detection`
- **Co bylo testováno**: Detekce módu z iRacing SDK dat
- **Výsledek**:
  - ✅ IDLE: Menu/lobby - funguje správně
  - ✅ GARAGE: Garáž ve hře - funguje správně
  - ✅ RACE: Na trati v autě - funguje správně
  - ✅ REPLAY: Přehrávání - funguje správně (priorita nad ostatními)
  - ✅ QUIT: Detekce ukončení hry - implementováno pomocí `SessionTime` stall
  - ❌ SETTINGS: Odstraněno - iRacing SDK nehlásí spolehlivě
- **Status**: Dokončeno

#### ✅ `debug_quit_detection`
- **Co bylo testováno**: Detekce ukončení iRacing hry
- **Výsledek**:
  - ✅ Detekce zamrznutí `SessionTime` (konfigurovatelný práh `quit_stall_seconds`)
  - ✅ Kontrola `CamCameraState` bit 0 (session screen)
  - ✅ Kontrola `IsOnTrack = false`
  - ✅ Přepnutí na QUIT scénu při detekci
- **Status**: Dokončeno

#### ✅ `debug_restart_hotkey`
- **Co bylo testováno**: Globální hotkey pro RESTART mód (VR podpora)
- **Výsledek**:
  - ✅ `pynput` knihovna pro globální keyboard monitoring
  - ✅ Konfigurovatelný hotkey přes `[hotkeys]` sekci
  - ✅ Detekce hotkey v 10s okně před QUIT
  - ✅ Sticky RESTART mód (přetrvává do skutečného IDLE)
  - ✅ Fungující kombinace: `ctrl+shift+f7`
- **Status**: Dokončeno

#### ✅ `debug_loading_screen_handling`
- **Co bylo testováno**: Grace period pro loading screen
- **Výsledek**:
  - ✅ Detekce loading screen (`SessionTime` je prázdný seznam nebo None)
  - ✅ Grace period po reconnect - čeká na IDLE po non-IDLE módu
  - ✅ Ignorování inspekčního režimu (GARAGE) po loading screen
  - ✅ Správné přepnutí scény až po skutečném načtení hry
- **Status**: Dokončeno

### Referenční úkoly (popis postupu)

#### `debug_iracing_connection`
- **Co testuje**: Připojení k iRacing a detekce stavu
- **Proč**: Aplikace musí správně detekovat, zda iRacing běží a je připojen
- **Postup**:
  1. Zajisti, že iRacing není spuštěno
  2. Spusť aplikaci
  3. Ověř v logách, že `connected_iracing = False`
  4. Spusť iRacing
  5. Ověř, že aplikace detekuje připojení (`connected_iracing = True`)
  6. Ověř, že se zobrazí notifikace "iRacing connected" (pokud jsou notifikace povolené)
  7. Zastav iRacing
  8. Ověř, že aplikace detekuje odpojení (`connected_iracing = False`)
  9. Ověř, že se zobrazí notifikace "iRacing disconnected"
- **Očekávaný výsledek**: 
  - Aplikace správně detekuje stav připojení iRacing
  - Notifikace se zobrazují při změně stavu
  - Aplikace pokračuje v běhu i když iRacing není připojen

#### `debug_iracing_mode_detection`
- **Co testuje**: Detekce módu z iRacing dat
- **Proč**: Aplikace musí správně extrahovat mód (IDLE/GARAGE/RACE/REPLAY) z iRacing SDK
- **Postup**:
  1. Spusť iRacing a aplikaci
  2. Otestuj různé módy:
     - **IDLE**: Menu nebo hlavní obrazovka → Ověř, že `mode = IDLE`
     - **GARAGE**: V garáži → Ověř, že `mode = GARAGE`
     - **RACE**: Na trati → Ověř, že `mode = RACE`
     - **REPLAY**: Přehrávání → Ověř, že `mode = REPLAY` (má prioritu)
  3. Ověř v logách, že se mód správně extrahuje
  4. Ověř v logách, že se mód zobrazuje správně
- **Očekávaný výsledek**: 
  - Aplikace správně detekuje všechny módy
  - REPLAY má prioritu nad ostatními módy
  - Mód se aktualizuje v real-time

#### `debug_scene_switching_with_iracing`
- **Co testuje**: Přepínání scén na základě iRacing módu
- **Proč**: Aplikace musí automaticky přepínat OBS scény podle módu iRacing
- **Postup**:
  1. Spusť iRacing, OBS a aplikaci
  2. Ověř, že všechny scény z configu existují v OBS
  3. Testuj přepínání scén:
     - **IDLE → Practice**: Přejdi do menu → Ověř, že se přepne na Practice scénu
     - **GARAGE → Back**: Přejdi do garáže → Ověř, že se přepne na Back scénu
     - **RACE → VR**: Přejdi na trať → Ověř, že se přepne na VR scénu
     - **REPLAY → VR**: Spusť replay → Ověř, že se přepne na VR scénu
  4. Ověř v logách, že se scény přepínají s správným důvodem (`reason`)
  5. Ověř, že debounce a cooldown fungují (rychlé přepínání mezi módy nezpůsobí flapping)
- **Očekávaný výsledek**: 
  - Scény se přepínají podle módu iRacing
  - Debounce a cooldown zabraňují flappingu
  - Logy obsahují informace o přepínání scén

#### `debug_override_with_iracing`
- **Co testuje**: Override scén při běžícím iRacing
- **Proč**: Uživatel musí mít možnost manuálně přepnout scénu i když iRacing běží
- **Postup**:
  1. Spusť iRacing, OBS a aplikaci
  2. Přejdi do módu RACE (na trať)
  3. Použij override přes API:
     - **Override: Race**: Ověř, že se aplikuje override na Race scénu
     - **Override: Pits**: Ověř, že se aplikuje override na Pits scénu
     - **Override: Safe**: Ověř, že se aplikuje override na Safe scénu
  4. Ověř, že override má časový limit (podle `override_seconds` v configu)
  5. Ověř, že po vypršení override se vrátí automatické přepínání
  6. Ověř, že override má prioritu nad automatickým přepínáním
- **Očekávaný výsledek**: 
  - Override funguje i když iRacing běží
  - Override má časový limit
  - Po vypršení override se vrátí automatické přepínání

#### `debug_state_machine_with_iracing`
- **Co testuje**: State machine logika s reálnými iRacing daty
- **Proč**: State machine musí správně zpracovávat změny módu z iRacing
- **Postup**:
  1. Spusť iRacing, OBS a aplikaci
  2. Sleduj state machine v logách:
     - **Debounce**: Rychlé změny módu → Ověř, že se debounce aplikuje
     - **Cooldown**: Přepínání scén → Ověř, že se cooldown aplikuje
     - **State transitions**: Změny módu → Ověř, že se stav správně aktualizuje
  3. Testuj edge cases:
     - **Rychlé přepínání**: Rychle přepínej mezi módy → Ověř, že debounce funguje
     - **Dlouhé přepínání**: Počkej déle než debounce → Ověř, že se scéna přepne
     - **Override během přepínání**: Aplikuj override během debounce → Ověř, že override má prioritu
- **Očekávaný výsledek**: 
  - State machine správně zpracovává všechny scénáře
  - Debounce a cooldown fungují správně
  - Override má prioritu nad automatickým přepínáním

---

## Testovací strategie

### Mocking

Všechny testy používají mocking pro externí závislosti:

- **pyirsdk** - mockován v testech readeru
- **obsws-python** - mockován v testech OBS klienta
- **aiohttp** - používá TestServer pro API testy
- **asyncio** - používá pytest-asyncio pro async testy

### Časové testy

State machine testy používají mock `now_ms()` místo freezegun, protože:
- `time.monotonic()` není ovlivněno systémovým časem
- Freezegun nefunguje s monotonic time
- Mock umožňuje přesnou kontrolu času v testech

### Test isolation

Každý test je izolovaný:
- API testy resetují globální stav pomocí `reset_state()`
- State machine testy používají čisté instance
- Mocky jsou vytvářeny pro každý test zvlášť

---

## Pokrytí

Testy pokrývají:

- ✅ Všechny veřejné API metody
- ✅ Error handling a edge cases
- ✅ Async funkcionalita
- ✅ State transitions
- ✅ Validace vstupů
- ✅ Retry logika
- ✅ Debounce a cooldown logika
- ✅ Override funkcionalita

---

## Spuštění v CI/CD

Pro automatické spouštění testů v CI/CD:

```yaml
# Příklad GitHub Actions
- name: Run tests
  run: |
    pip install -e .[test]
    pytest -v --tb=short
```

---

## 10. Nové funkce (leden 2026)

### QUIT Detection

**Co bylo implementováno**:
- Detekce ukončení iRacing na základě zamrznutí `SessionTime`
- Konfigurovatelný práh `quit_stall_seconds` v `[iracing]` sekci

**Jak testovat**:
1. Spusť iRacing a aplikaci
2. Ověř, že `mode = RACE` nebo `IDLE` (podle stavu)
3. Ukonči iRacing
4. Ověř, že aplikace detekuje `mode = QUIT` do 0.5s
5. Ověř, že se přepne na QUIT scénu

### RESTART Hotkey

**Co bylo implementováno**:
- Globální hotkey listener (`pynput`)
- Konfigurovatelný hotkey v `[hotkeys]` sekci
- Sticky RESTART mód

**Jak testovat**:
1. Spusť iRacing a aplikaci
2. Drž `Ctrl+Shift+F7` (nebo konfigurovaný hotkey)
3. Ukonči iRacing
4. Ověř, že aplikace přepne na RESTART scénu (ne QUIT)
5. Ověř, že RESTART mód přetrvává i po restartu iRacing
6. Ověř, že se resetuje až po skutečném IDLE (lobby)

### Grace Period (Loading Screen)

**Co bylo implementováno**:
- Grace period po reconnect - čeká na IDLE po non-IDLE módu
- Ignorování inspekčního režimu (GARAGE) hned po loading screen

**Jak testovat**:
1. Spusť OBS a aplikaci (bez iRacing)
2. Ověř, že je aktuální scéna (safe_scene)
3. Spusť iRacing
4. Ověř, že během loading screen zůstává safe scéna
5. Ověř, že po loading screen (inspekční režim) zůstává safe scéna
6. Ověř, že až po skutečném IDLE (lobby) se přepne na IDLE scénu
7. **Kritické**: Nesmí se krátce zobrazit GARAGE scéna během loading

---

## Odkazy

- [README.md](README.md) - základní dokumentace projektu
- [.cursorrules](.cursorrules) - pravidla vývoje a architektury
- [pyproject.toml](pyproject.toml) - konfigurace projektu a závislosti
