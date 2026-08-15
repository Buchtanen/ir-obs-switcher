# API Dokumentace

Kompletní popis REST API a WebSocket endpointů aplikace.

Služba vystavuje REST API na `http://127.0.0.1:17321` (nebo podle konfigurace v `config.ini`).

## Obsah

- [REST Endpointy](#rest-endpointy)
  - [GET /status](#get-status)
  - [POST /override](#post-override)
  - [POST /autoswitch/toggle](#post-autoswitchtoggle)
  - [POST /restart-mode/reset](#post-restart-modereset)
  - [GET /health](#get-health)
  - [GET /metrics](#get-metrics)
  - [POST /config/reload](#post-configreload)
  - [POST /reset](#post-reset)
  - [POST /shutdown](#post-shutdown)
  - [GET /api/events](#get-apievents)
- [WebSocket Endpoint](#websocket-endpoint)
  - [WS /ws](#ws-ws)
- [HTML Dashboardy](#html-dashboardy)
  - [GET /gr-status](#get-gr-status)
  - [GET /vr-status](#get-vr-status)
  - [GET /test](#get-test)

---

## REST Endpointy

### GET /status

Získání aktuálního stavu služby.

**URL**: `http://127.0.0.1:17321/status`

**Method**: `GET`

**Response** (200 OK):
```json
{
  "version": "0.3.0",
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
  "restart_mode_active": false,
  "session_type": "Race",
  "session_name": "NASCAR Cup Series",
  "session_num": 0,
  "session_num_display": "1 of 3",
  "total_sessions": 3,
  "streaming": true,
  "stream_duration_ms": 3600000,
  "stream_duration_seconds": 3600,
  "stream_duration_current_session_seconds": 1800,
  "obs_profile": "RacingProfile",
  "stream_selected": true,
  "stream_ready_selected": true,
  "stream_title": "iRacing Stream - NASCAR Cup Series",
  "stream_description": "Live stream description",
  "youtube_quota_exceeded": false,
  "youtube_api_key_missing": false
}
```

**Pole v response**:
- `version` (string) - verze aplikace ve formátu `major.minor.patch` (např. "0.3.0")
- `connected_iracing` (boolean) - zda je iRacing připojen
- `connected_obs` (boolean) - zda je OBS připojen
- `autoswitch` (boolean) - zda je automatické přepínání zapnuté
- `override_scene` (string | null) - název scény při aktivním override, jinak null
- `override_until` (number | null) - timestamp do kdy trvá override, jinak null
- `mode` (string) - aktuální mód iRacing (IDLE, GARAGE, RACE, REPLAY, QUIT, RESTART)
- `target_scene` (string) - cílová scéna, která by měla být aktivní
- `current_scene` (string) - aktuálně aktivní scéna v OBS
- `last_switch_ts` (number) - timestamp posledního přepnutí scény
- `reason` (string) - důvod aktuálního stavu
- `restart_mode_active` (boolean) - zda je aktivní RESTART mód
- `session_type` (string | null) - typ sessionu (Practice, Qualify, Race, Test)
- `session_name` (string | null) - název sessionu
- `session_num` (number | null) - číslo sessionu (0-based)
- `session_num_display` (string | null) - zobrazení sessionu (např. "1 of 3")
- `total_sessions` (number | null) - celkový počet sessionů
- `streaming` (boolean) - zda OBS právě streamuje
- `stream_duration_ms` (number | null) - délka aktuálního streamu v milisekundách
- `stream_duration_seconds` (number | null) - kumulativní délka streamu v sekundách
- `stream_duration_current_session_seconds` (number | null) - délka streamu v aktuální sessioni v sekundách
- `obs_profile` (string | null) - název aktivního OBS profilu
- `stream_selected` (boolean) - zda je stream vybrán v OBS Broadcast Manager
- `stream_ready_selected` (boolean) - zda je stream vybrán a připraven (má broadcast_id)
- `stream_title` (string | null) - název streamu z YouTube API
- `stream_description` (string | null) - popis streamu z YouTube API
- `youtube_quota_exceeded` (boolean) - zda byla překročena YouTube API kvóta
- `youtube_api_key_missing` (boolean) - zda chybí YouTube API klíč

**Error Response** (503 Service Unavailable):
```json
{
  "error": "Service not initialized"
}
```

---

### POST /override

Dočasné přepnutí scény s časovým limitem.

**URL**: `http://127.0.0.1:17321/override`

**Method**: `POST`

**Content-Type**: `application/json`

**Request Body**:
```json
{
  "scene": "Race",
  "seconds": 120
}
```

**Parametry**:
- `scene` (string, povinné) - název scény, na kterou se má přepnout
- `seconds` (number, volitelné, výchozí: 120) - délka trvání override v sekundách

**Response** (200 OK): Aktualizovaný stav (stejný formát jako `/status`)

**Error Responses**:
- `400 Bad Request` - chybějící nebo neplatný parametr
  ```json
  {
    "error": "scene is required"
  }
  ```
  nebo
  ```json
  {
    "error": "seconds must be a positive integer"
  }
  ```
- `503 Service Unavailable` - služba není inicializovaná
  ```json
  {
    "error": "Service not initialized"
  }
  ```

**Příklad použití** (curl):
```bash
curl -X POST http://127.0.0.1:17321/override \
  -H "Content-Type: application/json" \
  -d '{"scene": "Race", "seconds": 180}'
```

---

### POST /autoswitch/toggle

Přepnutí autoswitch on/off.

**URL**: `http://127.0.0.1:17321/autoswitch/toggle`

**Method**: `POST`

**Response** (200 OK): Aktualizovaný stav s novým `autoswitch` flagem (stejný formát jako `/status`)

**Error Response** (503 Service Unavailable):
```json
{
  "error": "Service not initialized"
}
```

**Příklad použití** (curl):
```bash
curl -X POST http://127.0.0.1:17321/autoswitch/toggle
```

---

### POST /restart-mode/reset

Reset RESTART módu (deaktivuje RESTART mód).

**URL**: `http://127.0.0.1:17321/restart-mode/reset`

**Method**: `POST`

**Response** (200 OK):
```json
{
  "success": true,
  "message": "RESTART mode deactivated"
}
```

**Příklad použití** (curl):
```bash
curl -X POST http://127.0.0.1:17321/restart-mode/reset
```

---

### GET /health

Health check endpoint pro monitoring.

**URL**: `http://127.0.0.1:17321/health`

**Method**: `GET`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "version": "0.3.0",
  "checks": {
    "iracing": {
      "status": "connected",
      "available": true
    },
    "obs": {
      "status": "connected",
      "available": true
    },
    "api": {
      "status": "running",
      "available": true
    }
  },
  "timestamp": 1704110400000
}
```

**Status hodnoty**:
- `healthy` - oba připojené (iRacing i OBS)
- `degraded` - jeden připojený
- `unhealthy` - žádný připojený

**Použití**: Pro monitoring a health checks (např. Docker, Kubernetes, load balancery).

---

### GET /metrics

Získání metrik aplikace.

**URL**: `http://127.0.0.1:17321/metrics`

**Method**: `GET`

**Response** (200 OK):
```json
{
  "uptime_seconds": 3600,
  "scene_switches_total": 42,
  "scene_switch_latency_avg_ms": 125.5,
  "iracing_connected_duration_seconds": 3500,
  "iracing_connected_duration_current_session_seconds": 1800,
  "obs_connected_duration_seconds": 3600,
  "obs_connected_duration_current_session_seconds": 3600,
  "stream_duration_seconds": 1800,
  "stream_duration_current_session_seconds": 1800
}
```

**Pole v response**:
- `uptime_seconds` (number) - doba provozu aplikace v sekundách
- `scene_switches_total` (number) - celkový počet přepnutí scén
- `scene_switch_latency_avg_ms` (number | null) - průměrná latence přepnutí scény v milisekundách
- `iracing_connected_duration_seconds` (number | null) - kumulativní doba připojení iRacing v sekundách
- `iracing_connected_duration_current_session_seconds` (number | null) - doba připojení iRacing v aktuální sessioni v sekundách
- `obs_connected_duration_seconds` (number | null) - kumulativní doba připojení OBS v sekundách
- `obs_connected_duration_current_session_seconds` (number | null) - doba připojení OBS v aktuální sessioni v sekundách
- `stream_duration_seconds` (number | null) - kumulativní doba streamování v sekundách
- `stream_duration_current_session_seconds` (number | null) - doba streamování v aktuální sessioni v sekundách

---

### POST /config/reload

Přenačtení konfigurace ze souboru.

**URL**: `http://127.0.0.1:17321/config/reload`

**Method**: `POST`

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Configuration reloaded"
}
```

**Error Response** (500 Internal Server Error):
```json
{
  "error": "Failed to reload configuration",
  "details": "Error message"
}
```

**Poznámka**: Po přenačtení konfigurace se aplikace restartuje s novými nastaveními.

---

### POST /reset

Reset všech metrik a stavu aplikace.

**URL**: `http://127.0.0.1:17321/reset`

**Method**: `POST`

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Metrics and state reset"
}
```

**Poznámka**: Resetuje metriky, ale neukončuje aplikaci.

---

### POST /stream/reinit

Vyčistí cache stream info a znovu načte data z OBS (+ YouTube API pokud je OAuth).

**Kdy použít**: Po výběru / založení jiného broadcastu v OBS Manage Broadcast — dashboard jinak může držet starý title.

**URL**: `http://127.0.0.1:17321/stream/reinit`

**Method**: `POST`

**Response** (200 OK):
```json
{
  "status": "ok",
  "message": "Stream info refreshed",
  "stream_title": "My Race Stream",
  "stream_description": "...",
  "connected_obs": true,
  "stream_selected": true
}
```

**Error Response** (503 Service Unavailable) — OBS není připojené:
```json
{
  "error": "OBS not connected",
  "message": "Connect OBS before reinitializing stream info"
}
```

**Poznámka**: Nemění výběr broadcastu v OBS a nespouští/nestopuje stream. Jen refresh app cache + YouTube metadata.

---

### POST /shutdown

Graceful shutdown aplikace.

**URL**: `http://127.0.0.1:17321/shutdown`

**Method**: `POST`

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Shutdown initiated"
}
```

**Poznámka**: Aplikace se ukončí po dokončení aktuálních operací.

---

### GET /api/events

Získání posledních eventů z event logu.

**URL**: `http://127.0.0.1:17321/api/events?count=50`

**Method**: `GET`

**Query parametry**:
- `count` (number, volitelné, výchozí: 50) - počet eventů k vrácení

**Response** (200 OK):
```json
{
  "events": [
    {
      "timestamp": 1704110400000,
      "type": "scene_switch",
      "message": "Scene switched to Race",
      "data": {
        "scene": "Race",
        "mode": "RACE"
      }
    },
    {
      "timestamp": 1704110300000,
      "type": "connection_restored",
      "message": "iRacing connection restored",
      "data": {}
    }
  ]
}
```

**Pole v event objektu**:
- `timestamp` (number) - timestamp eventu v milisekundách
- `type` (string) - typ eventu (scene_switch, connection_lost, connection_restored, atd.)
- `message` (string) - textová zpráva eventu
- `data` (object) - dodatečná data eventu

---

## WebSocket Endpoint

### WS /ws

Real-time updates stavu služby.

**URL**: `ws://127.0.0.1:17321/ws`

**Protokol**: WebSocket

**Zprávy**:
- Po připojení se okamžitě pošle aktuální stav (JSON)
- Při každé změně stavu se pošle aktualizace (JSON)
- Formát je stejný jako `/status` response

**Příklad použití** (JavaScript):
```javascript
const ws = new WebSocket('ws://127.0.0.1:17321/ws');

ws.onopen = () => {
  console.log('WebSocket connected');
};

ws.onmessage = (event) => {
  const status = JSON.parse(event.data);
  console.log('Status update:', status);
  
  // Aktualizuj UI podle statusu
  if (status.mode === 'RACE') {
    console.log('Race mode detected!');
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket disconnected');
};
```

**Příklad použití** (Python):
```python
import asyncio
import websockets
import json

async def listen_to_updates():
    uri = "ws://127.0.0.1:17321/ws"
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            status = json.loads(message)
            print(f"Status update: {status['mode']}")

asyncio.run(listen_to_updates())
```

---

## HTML Dashboardy

Aplikace poskytuje HTML dashboardy pro vizualizaci stavu.

### GET /gr-status

Velký dashboard pro monitor (GR Dashboard).

**URL**: `http://127.0.0.1:17321/gr-status`

**Method**: `GET`

**Popis**: 
- JavaScript auto-update
- Zobrazuje status, event log, streaming info, metrics
- Konfigurovatelné obrázky a loga
- Real-time aktualizace přes JavaScript

**Screenshot**: Viz `assets/rg-status-screen.png`

---

### GET /vr-status

Minimalistický dashboard pro VR.

**URL**: `http://127.0.0.1:17321/vr-status`

**Method**: `GET`

**Popis**: 
- Minimalistický design, bílé písmo, větší fonty
- Bez JavaScriptu (pro RaceLab VR)
- ⚠️ **Omezení**: RaceLab VR widgety nepodporují auto-refresh - widget se neaktualizuje automaticky

**Více informací**: Viz [VR_SUPPORT.md](VR_SUPPORT.md) a [RACELAB_VR_SETUP.md](RACELAB_VR_SETUP.md) pro detaily a alternativy.

---

### GET /test

Test widget pro ověření JavaScript funkcionality.

**URL**: `http://127.0.0.1:17321/test`

**Method**: `GET`

**Popis**: 
- Jednoduchý widget pro testování JavaScript funkcionality v běžném webovém prohlížeči
- Zobrazí "JS JEDE" pokud JavaScript funguje správně

**Poznámka**: Tento widget **není určen pro RaceLab VR**, protože RaceLab VR widgety nepodporují JavaScript ani auto-refresh.
