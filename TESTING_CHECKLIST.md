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

## 🟢 Volitelné - Session Info Extrakce

### 7. Session Info v Extractors
**Status**: ⚠️ Možná chybí testy  
**Soubor**: `tests/test_extractors.py` (rozšířit)  
**Co testovat**:
- ✅ Extrakce `session_type` z `SessionType`
- ✅ Extrakce `session_name` z `SessionName`
- ✅ Extrakce `session_num` z `SessionNum`
- ✅ Ignorování "Test" session (nastavení na `None`)
- ✅ Správné parsování různých session typů (Practice, Qualify, Race, atd.)

**Poznámka**: Pokud je session info extrahováno v `main.py` místo `extractors.py`, testy by měly být v `test_main.py` nebo `test_main_loop_e2e.py`.

---

## 📋 Shrnutí

### ✅ Dokončeno:
1. ✅ Health endpoint (`GET /health`) - `tests/test_api.py`
2. ✅ Metrics endpoint (`GET /metrics`) - `tests/test_api.py`
3. ✅ Config reload endpoint (`POST /config/reload`) - `tests/test_api.py`
4. ✅ Shutdown endpoint (`POST /shutdown`) - `tests/test_api.py`
5. ✅ MetricsCollector unit testy - `tests/test_metrics.py` (13 testů)
6. ✅ File logging s rotací - `tests/test_logging.py` (8 testů)

### Volitelné (nice to have):
7. ⚠️ Session info extrakce (pokud není otestováno)

---

## 📝 Poznámky

- Všechny nové endpointy jsou v `src/irswitch/server/api.py`
- MetricsCollector je v `src/irswitch/server/metrics.py`
- File logging je v `src/irswitch/util/logging.py`
- Session info je extrahováno v `src/irswitch/main.py` (v `main_loop()`)

### Testovací strategie:
- Použít `aiohttp.test_utils.TestServer` a `TestClient` pro API testy
- Použít `unittest.mock` pro mockování časů v MetricsCollector testech
- Použít `tempfile` pro testování file logging
- Použít `freezegun` nebo mock `time.monotonic()` pro časové testy

---

## ✅ Co už je otestováno

- ✅ GET /status
- ✅ POST /override
- ✅ POST /autoswitch/toggle
- ✅ State machine
- ✅ OBS client
- ✅ iRacing reader
- ✅ Extractors (základní módy)
- ✅ Loading tracker
- ✅ Event log
- ✅ E2E main loop
