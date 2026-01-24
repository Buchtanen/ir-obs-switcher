# Testovací checklist - Co ještě otestovat

## ✅ Dokončeno - Testy pro nové API endpointy

### 1. Health Endpoint (`GET /health`)
**Status**: ✅ Implementováno  
**Soubor**: `tests/test_api.py`  
**Co testovat**:
- ✅ Vrací `200 OK` když je služba zdravá (oba připojené)
- ✅ Vrací `degraded` když je jeden odpojený
- ✅ Vrací `unhealthy` když jsou oba odpojení
- ✅ Obsahuje `checks` objekt s `iracing`, `obs`, `api`
- ✅ Obsahuje `timestamp`

### 2. Metrics Endpoint (`GET /metrics`)
**Status**: ✅ Implementováno  
**Soubor**: `tests/test_api.py`  
**Co testovat**:
- ✅ Vrací `200 OK`
- ✅ Obsahuje `scene_switches_total`
- ✅ Obsahuje `uptime_seconds`
- ✅ Obsahuje `errors_total` (dict)
- ✅ Obsahuje `scene_switch_latency_avg_ms` (pokud existují data)
- ✅ Obsahuje `iracing_connected_duration_seconds` (cumulative)
- ✅ Obsahuje `iracing_connected_duration_current_session_seconds`
- ✅ Obsahuje `obs_connected_duration_seconds` (cumulative)
- ✅ Obsahuje `obs_connected_duration_current_session_seconds`
- ✅ Obsahuje `stream_duration_seconds` (cumulative)
- ✅ Obsahuje `stream_duration_current_session_seconds`
- ✅ Obsahuje `current_state` objekt

### 3. Config Reload Endpoint (`POST /config/reload`)
**Status**: ✅ Implementováno  
**Soubor**: `tests/test_api.py`  
**Co testovat**:
- ✅ Úspěšné reloadování configu
- ✅ Vrací `200 OK` s `status: "success"`
- ✅ Aktualizuje `app["config"]` objekt
- ✅ Vrací `400` když config soubor neexistuje
- ✅ Vrací `400` když config je neplatný
- ✅ Vrací `500` když `config_path` není nastaven
- ✅ Loguje úspěšné reloadování

### 4. Shutdown Endpoint (`POST /shutdown`)
**Status**: ✅ Implementováno  
**Soubor**: `tests/test_api.py`  
**Co testovat**:
- ✅ Vrací `200 OK` s `status: "shutting_down"`
- ✅ Nastaví shutdown event
- ✅ Vrací `503` když shutdown není dostupný (`_shutdown_event` je None)
- ✅ Loguje shutdown request

---

## ✅ Dokončeno - Testy pro MetricsCollector

### 5. MetricsCollector Unit Testy
**Status**: ✅ Implementováno (`tests/test_metrics.py`)  
**Soubor**: `tests/test_metrics.py` (nový)  
**Co testovat**:

#### 5.1 Scene Switch Tracking
- ✅ `record_scene_switch()` zvyšuje `scene_switches_total`
- ✅ Přidává latenci do `scene_switch_latencies_ms`
- ✅ Omezuje počet vzorků na `_max_latency_samples` (100)
- ✅ `get_scene_switch_latency_avg_ms()` vrací průměr
- ✅ `get_scene_switch_latency_avg_ms()` vrací `None` když nejsou data

#### 5.2 Error Tracking
- ✅ `record_error()` zvyšuje počítadlo pro daný typ
- ✅ `errors_total` je defaultdict
- ✅ Více chyb stejného typu se sčítají

#### 5.3 Uptime
- ✅ `get_uptime_seconds()` vrací čas od `start_time`
- ✅ `start_time` je nastaven při vytvoření

#### 5.4 iRacing Connection Duration (Cumulative + Current)
- ✅ `set_iracing_connected(True)` začne tracking
- ✅ `set_iracing_connected(False)` přidá čas do `iracing_total_connected_time`
- ✅ `get_iracing_connected_duration_seconds()` vrací `(cumulative, current_session)`
- ✅ Kumulativní čas se sčítá přes více připojení/odpojení
- ✅ Current session čas je `None` když není připojen
- ✅ Kumulativní čas zahrnuje current session když je připojen
- ✅ Vrací `(None, None)` když nikdy nebyl připojen

#### 5.5 OBS Connection Duration (Cumulative + Current)
- ✅ Stejné jako iRacing (5.4)

#### 5.6 Stream Duration (Cumulative + Current)
- ✅ `set_streaming(True)` začne tracking
- ✅ `set_streaming(False)` přidá čas do `stream_total_time`
- ✅ `get_stream_duration_seconds()` vrací `(cumulative, current_session)`
- ✅ Kumulativní čas se sčítá přes více start/stop cyklů
- ✅ Current session čas je `None` když není stream aktivní
- ✅ Kumulativní čas zahrnuje current session když je stream aktivní
- ✅ Vrací `(None, None)` když nikdy nebyl stream

#### 5.7 to_dict() Method
- ✅ Obsahuje všechny základní metriky
- ✅ Obsahuje `current_state` když je poskytnut
- ✅ Správně formátuje všechny hodnoty
- ✅ Neobsahuje `None` hodnoty (kromě current session časů)

---

## ✅ Dokončeno - Testy pro File Logging

### 6. File Logging s Rotací
**Status**: ✅ Implementováno (`tests/test_logging.py`)  
**Soubor**: `tests/test_logging.py` (nový nebo rozšířit)  
**Co testovat**:

#### 6.1 Základní File Logging
- ✅ `setup_logging(log_file="test.log")` vytvoří log soubor
- ✅ Loguje do souboru i do stderr
- ✅ Vytvoří log directory pokud neexistuje
- ✅ Používá UTF-8 encoding

#### 6.2 Log Rotation
- ✅ Rotuje log když dosáhne `max_bytes`
- ✅ Vytváří backup soubory (`test.log.1`, `test.log.2`, atd.)
- ✅ Omezuje počet backup souborů na `backup_count`
- ✅ Nejstarší backup se smaže když je překročen limit

#### 6.3 Console Logging (vždy aktivní)
- ✅ Loguje do stderr i když není `log_file`
- ✅ Loguje do stderr i když je `log_file` nastaven
- ✅ Formátování je stejné pro oba handlery

#### 6.4 Edge Cases
- ✅ Funguje když `log_file` je `None` (pouze console)
- ✅ Funguje když log directory neexistuje (vytvoří ho)
- ✅ Funguje s relativními i absolutními cestami

---

## ✅ Dokončeno - Testy pro Lokalizace (i18n)

### 7. Internationalization (i18n)
**Status**: ✅ Implementováno (`tests/test_i18n.py`)  
**Soubor**: `tests/test_i18n.py` (nový)  
**Co testovat**:

#### 7.1 Základní funkcionalita
- ✅ `set_language()` nastaví správný jazyk
- ✅ `get_translator()` vrací správný translator instance
- ✅ `t()` funkce vrací správný překlad
- ✅ Fallback na CS když je neplatný jazyk
- ✅ Case-insensitive kódy jazyků (EN, en, En)

#### 7.2 Překlady
- ✅ Všechny podporované jazyky mají všechny klíče
- ✅ Chybějící klíč vrací klíč jako fallback
- ✅ Parametry v překladech (`{time}`, atd.)
- ✅ Správné nahrazení parametrů v překladech

#### 7.3 Podporované jazyky
- ✅ CS (čeština) - výchozí
- ✅ EN (angličtina)
- ✅ DE (němčina)
- ✅ FR (francouzština)
- ✅ SP (španělština)
- ✅ PL (polština)
- ✅ HU (maďarština)

#### 7.4 Integrace v dashboardu
- ✅ JavaScript `t()` funkce funguje správně
- ✅ Python `translator.t()` funguje správně
- ✅ Překlady se aplikují při změně jazyka v configu
- ✅ YouTube API zprávy jsou lokalizované

**Poznámka**: ✅ Unit testy byly přidány v `tests/test_i18n.py` - pokrývají všechny základní funkcionality.

---

## ✅ Dokončeno - Testy pro YouTube API integrace

### 8. YouTube Data API v3 integrace
**Status**: ✅ Implementováno (`tests/test_obs_client.py`)  
**Soubor**: `tests/test_obs_client.py` (rozšířeno)  
**Co testovat**:

#### 8.1 Stream Info Caching
- ✅ `get_cached_stream_info()` vrací cached hodnoty
- ✅ Cache se resetuje při změně `broadcast_id`
- ✅ Cache se resetuje při `force_refresh=True`
- ✅ Cache obsahuje `(title, description, quota_exceeded, api_key_missing)`

#### 8.2 YouTube API volání
- ✅ Volá API pouze když je `broadcast_id` dostupný
- ✅ Volá API pouze když je `YOUTUBE_API_KEY` nastaven
- ✅ Nepokouší se volat API když je `quota_exceeded=True`
- ✅ Nepokouší se volat API když je `api_key_missing=True`
- ✅ Používá správné endpointy (`liveBroadcasts.list`, `videos.list`)

#### 8.3 Error Handling
- ✅ Detekuje HTTP 403 s `quotaExceeded` reason
- ✅ Nastaví `_youtube_quota_exceeded=True` při quota exceeded
- ✅ Detekuje missing API key (`YOUTUBE_API_KEY` není nastaven)
- ✅ Nastaví `_youtube_api_key_missing=True` při missing key
- ✅ Loguje varování při quota exceeded
- ✅ Loguje varování při missing API key
- ✅ Přidává event do event logu při quota exceeded
- ✅ Přidává event do event logu při missing API key

#### 8.4 Stream Info v API Response
- ✅ `/status` endpoint obsahuje `stream_title` a `stream_description`
- ✅ `/status` endpoint obsahuje `youtube_quota_exceeded` flag
- ✅ `/status` endpoint obsahuje `youtube_api_key_missing` flag
- ✅ Hodnoty jsou správně cachované a vracené

#### 8.5 Edge Cases
- ✅ Funguje když API vrací prázdný response
- ✅ Funguje když API vrací neplatný JSON
- ✅ Funguje když network request selže
- ✅ Funguje když `broadcast_id` není dostupný
- ✅ Funguje když stream není vybrán v OBS

**Poznámka**: ✅ YouTube API testy používají mock HTTP responses a `os.environ` mockování - nevolají skutečné API.

---

## ✅ Dokončeno - Testy pro Session Info Extrakce

### 9. Session Info v Extractors
**Status**: ✅ Implementováno (`tests/test_extractors.py`)  
**Soubor**: `tests/test_extractors.py` (rozšířeno)  
**Co testovat**:
- ✅ Extrakce `session_type` z `SessionType` (numeric)
- ✅ Extrakce `session_type` z `SessionName` (string fallback)
- ✅ Extrakce `session_type` z `WeekendInfo.EventType` (fallback)
- ✅ Extrakce `session_num` z `SessionNum`
- ✅ Extrakce `total_sessions` z `SessionTotalSessions`
- ✅ Extrakce `total_sessions` z `WeekendInfo` (fallback)
- ✅ Priority mezi různými zdroji dat
- ✅ Edge cases (missing, None, invalid values)

**Poznámka**: ✅ Testy pokrývají všechny tři metody extrakce session_type (SessionType, SessionName, WeekendInfo.EventType) a všechny edge cases.

---

## 📋 Shrnutí

### ✅ Dokončeno:
1. ✅ Health endpoint (`GET /health`) - `tests/test_api.py`
2. ✅ Metrics endpoint (`GET /metrics`) - `tests/test_api.py`
3. ✅ Config reload endpoint (`POST /config/reload`) - `tests/test_api.py`
4. ✅ Shutdown endpoint (`POST /shutdown`) - `tests/test_api.py`
5. ✅ MetricsCollector unit testy - `tests/test_metrics.py` (13 testů)
6. ✅ File logging s rotací - `tests/test_logging.py` (8 testů)
7. ✅ Lokalizace (i18n) - `tests/test_i18n.py` (nový soubor, ~30+ testů)
8. ✅ YouTube API integrace - rozšířeno `tests/test_obs_client.py` (~10 nových testů)
9. ✅ Session info extrakce - rozšířeno `tests/test_extractors.py` (~15 nových testů)

### Celkový počet testů:
- **Původní**: 79+ testů
- **Nové přidané**: ~55+ testů (i18n, YouTube API, session info)
- **Celkem**: **134+ testů**

---

## 📝 Poznámky

- Všechny nové endpointy jsou v `src/irswitch/server/api.py`
- MetricsCollector je v `src/irswitch/server/metrics.py`
- File logging je v `src/irswitch/util/logging.py`
- Lokalizace je v `src/irswitch/i18n.py`
- YouTube API integrace je v `src/irswitch/obs/client.py`
- Session info je extrahováno v `src/irswitch/main.py` (v `main_loop()`)

### Testovací strategie:
- Použít `aiohttp.test_utils.TestServer` a `TestClient` pro API testy
- Použít `unittest.mock` pro mockování časů v MetricsCollector testech
- Použít `tempfile` pro testování file logging
- Použít `freezegun` nebo mock `time.monotonic()` pro časové testy
- Použít `unittest.mock` pro mockování HTTP requests v YouTube API testech
- Použít `unittest.mock` pro mockování `os.environ` v YouTube API testech

---

## ✅ Co už je otestováno

### API Endpointy
- ✅ GET /status
- ✅ POST /override
- ✅ POST /autoswitch/toggle
- ✅ GET /health
- ✅ GET /metrics
- ✅ POST /config/reload
- ✅ POST /shutdown
- ✅ GET /api/events
- ✅ WS /ws (WebSocket)

### Core komponenty
- ✅ State machine
- ✅ OBS client (základní funkcionalita)
- ✅ iRacing reader
- ✅ Extractors (základní módy)
- ✅ Loading tracker
- ✅ Event log
- ✅ Metrics collector
- ✅ File logging s rotací
- ✅ E2E main loop

### Nové funkce (leden 2026)
- ✅ Health check endpoint
- ✅ Metrics endpoint
- ✅ Config hot reload
- ✅ Graceful shutdown
- ✅ File logging s rotací
- ✅ Session info v API
- ✅ Lokalizace (i18n) - **unit testy přidány** (`tests/test_i18n.py`)
- ✅ YouTube API integrace - **testy přidány** (rozšířeno `tests/test_obs_client.py`)
- ✅ Session info extrakce - **testy přidány** (rozšířeno `tests/test_extractors.py`)
