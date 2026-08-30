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
  - [GET /logging/level](#get-logginglevel)
  - [POST /logging/level](#post-logginglevel)
  - [POST /reset](#post-reset)
  - [POST /shutdown](#post-shutdown)
  - [POST /restart](#post-restart)
  - [GET /api/events](#get-apievents)
- [WebSocket Endpoint](#websocket-endpoint)
  - [WS /ws](#ws-ws)
- [HTML Dashboardy](#html-dashboardy)
  - [GET /gr-status](#get-gr-status)
  - [GET /vr-status](#get-vr-status)
  - [GET /test](#get-test)
  - [GET /overlay](#get-overlay)
  - [GET /overlay/debug](#get-overlaydebug)
  - [GET /overlay/demo](#get-overlaydemo)
  - [GET /config](#get-config)
- [Overlay API](#overlay-api)
  - [WS /ws/overlay](#ws-wsoverlay)
  - [V4 event envelopes (`v2_payload=true`)](#v4-event-envelopes-v2_payloadtrue)
  - [GET /api/overlay/snapshot](#get-apioverlaysnapshot)
  - [POST /overlay/debug/emit](#post-overlaydebugemit)
  - [GET /api/config](#get-apiconfig)
  - [PUT /api/config](#put-apiconfig)

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
- `stream_status` (string | null) - stav YouTube broadcastu (`live`, `complete`, …) z cache
- `stream_privacy_status` (string | null) - privacy YouTube broadcastu
- `youtube_quota_exceeded` (boolean) - zda byla překročena YouTube API kvóta
- `youtube_api_key_missing` (boolean) - zda chybí YouTube API klíč
- `stream_chapters` (array, pouze když `[stream_chapters] enabled = true`) - in-memory kapitoly aktuálního streamu; každá položka: `title`, `offset_seconds`, `session_type`, `created_at_ms`. Když je feature vypnutá, pole chybí.

**YouTube status auto-refresh**: při hraně OBS streamu (start / stop) služba force-refreshe `liveBroadcasts` (title/status/privacy) a pushne aktualizovaný status na `WS /ws`. Po stopu ještě jednou po ~45 s (`obs_stream_stopped_delayed`), protože YouTube často krátce drží `live` → `complete`. Vyžaduje OAuth; chyby se logují a main loop nespadne. Manuální `POST /stream/reinit` zůstává.

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
  "status": "success",
  "message": "Config reloaded successfully",
  "applied_live": ["switching.debounce_ms", "iracing.poll_hz"],
  "needs_restart": ["app.http_port"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `applied_live` | `string[]` | Changed keys that apply without process restart (diff old vs new; whitelist from `CONFIG.md`) |
| `needs_restart` | `string[]` | Changed keys that still require a process restart |

Prázdné seznamy = žádný tracked klíč se nezměnil, nebo nebylo s čím porovnat (chybí předchozí runtime config).

**Error Response** (400/500):
```json
{
  "error": "Failed to reload config: ..."
}
```

**Poznámka**: Hot-reload aktualizuje sdílený runtime config + switching (scenes, debounce/cooldown, auto-start/stop, `poll_hz`). **Nepřestartuje** HTTP server ani OBS/OAuth spojení — detaily a whitelist klíčů viz `CONFIG.md` sekce Hot-reload. GR dashboard po reloadu ukáže toast + panel se seznamy `applied_live` / `needs_restart`.

---

### GET /logging/level

Aktuální runtime log level procesu (nepersistuje do `config.ini`).

**URL**: `http://127.0.0.1:17321/logging/level`

**Method**: `GET`

**Response** (200 OK):
```json
{
  "level": "INFO",
  "persistent": false
}
```

---

### POST /logging/level

Dočasná změna log levelu běžícího procesu. Nepíše do `config.ini`; po restartu procesu platí znovu `app.log_level`.

**URL**: `http://127.0.0.1:17321/logging/level`

**Method**: `POST`

**Body**:
```json
{
  "level": "DEBUG"
}
```

Povolené hodnoty: `DEBUG`, `INFO` (case-insensitive).

**Response** (200 OK):
```json
{
  "status": "success",
  "level": "DEBUG",
  "persistent": false,
  "message": "Log level updated for this process only; resets on restart"
}
```

**Error Response** (400):
```json
{
  "error": "level must be DEBUG or INFO"
}
```

**Poznámka**: GR dashboard má badge + „Toggle Debug Logging“. Pro trvalou změnu uprav `app.log_level` v INI a restartuj proces.

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
  "status": "shutting_down",
  "message": "Service shutdown initiated"
}
```

**Poznámka**: Aplikace se ukončí po dokončení aktuálních operací.

---

### POST /restart

Detached respawn stejného procesu (`irswitchd` / aktuální interpreter + `--config`), pak stejný graceful shutdown jako `/shutdown`.

**URL**: `http://127.0.0.1:17321/restart`

**Method**: `POST`

**Response** (200 OK) — spawn OK, shutdown zahájen:
```json
{
  "status": "restarting",
  "message": "Service restart initiated"
}
```

**Response** (500) — spawn selhal (**fail-closed**: služba **zůstane běžet**):
```json
{
  "error": "Failed to spawn restart process: ..."
}
```

**Response** (503) — shutdown/restart wiring není k dispozici:
```json
{
  "error": "Restart not available"
}
```

**Chování**:
1. Nejdřív se pokusí spustit nový detached proces se stejným exe a `--config`.
2. Až když spawn uspěje, provede graceful shutdown (jako `/shutdown`).
3. Při selhání spawnu vrátí 500 a **neukončí** běžící službu.

Krátký backoff před startem child procesu uvolní `http_port`. Task Scheduler po graceful exitu **sám nespouští** app znovu — restart jde přes re-exec, ne přes task trigger. Detail: [BUILD_AND_DEPLOY.md – Restart služby](BUILD_AND_DEPLOY.md#restart-služby-restarting-the-service).

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
- Po připojení se okamžitě pošle aktuální stav (JSON) — **flat status** stejný jako `/status` (bez obálky `type`)
- Při každé změně stavu se pošle aktualizace (stejný flat status JSON)
- Když je `[stream_chapters] enabled = true` a právě se streamuje, po úvodním statusu přijde historie kapitol:
  ```json
  {"type":"stream_chapters_snapshot","chapters":[{"title":"Stream start","offset_seconds":0,"session_type":null,"created_at_ms":1704110400000}]}
  ```
- Nový marker (start streamu / změna `session_type`) přijde jako **additive** zpráva (ne nahrazuje status):
  ```json
  {"type":"stream_chapter","chapter":{"title":"Race","offset_seconds":842,"session_type":"Race","created_at_ms":1704111242000}}
  ```
- Legacy klienti, kteří každou zprávu parsují jako `/status`, musí **ignorovat** objekty s polem `type` (`stream_chapter` / `stream_chapters_snapshot`) — status snapshoty `type` nemají.
- `offset_seconds` je floor z `stream_duration_current_session_seconds` (monotonic session clock); při nedostupnosti duration = `0`.
- Seznam se maže při potvrzeném stopu streamu (debounce ≥ 2 s proti flickeru) nebo na začátku nové stream session.
- **Mimo scope**: zápis kapitol do YouTube description / OBS `CreateRecordChapter` — jen WS + `/status` historie.

**Příklad použití** (JavaScript):
```javascript
const ws = new WebSocket('ws://127.0.0.1:17321/ws');

ws.onopen = () => {
  console.log('WebSocket connected');
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'stream_chapter') {
    console.log('Chapter:', msg.chapter);
    return;
  }
  if (msg.type === 'stream_chapters_snapshot') {
    console.log('Chapters so far:', msg.chapters);
    return;
  }
  // Flat status (same as GET /status)
  console.log('Status update:', msg);
  if (msg.mode === 'RACE') {
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
            msg = json.loads(message)
            if msg.get("type") in ("stream_chapter", "stream_chapters_snapshot"):
                print(f"Chapter event: {msg}")
            else:
                print(f"Status update: {msg['mode']}")

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

---

## Overlay API

Overlay používá **samostatný** WebSocket. Switcher `WS /ws` se nemění.

Envelope:

```json
{ "type": "event", "name": "battle", "phase": "enter", "channel": "battle", "priority": 20, "timestamp": 0, "data": {} }
{ "type": "state", "domain": "system", "data": {} }
{ "type": "snapshot", "race": {}, "bio": {}, "system": {}, "activeEvents": [], "theme": "cyber_racing", "assets": {} }
```

### GET /overlay

OBS Browser Source, 1920×1080, transparentní pozadí. Live HUD (SYSINFO + karty) se ukáže jen když `race.connected` je true; jinak je overlay prázdný (link drop / iRacing pryč). `?demo=1` / golden / preview tohle nerespektují.

### GET /overlay/debug

Ruční TEST eventy (HUNTING, LAP, …). Write volá `POST /overlay/debug/emit`.

### GET /overlay/demo

Suchý test HUD v prohlížeči. Tmavé jeviště + iframe `/overlay?demo=1&renderer=v4` (default), auto-scénář V4 (HUNTING → HUNTED → LAP COMPLETE → PB → POSITION → INCIDENT → HR → FINAL → FINISH) v ~28&nbsp;s loopu. Bez OBS a bez iRacing. Theme a renderer (v4 / legacy v3) se přepínají v UI.

### GET /config

Schema-driven editor overlay nastavení. Navigace je i na `/gr-status`.

### WS /ws/overlay

Po connectu okamžitý `snapshot` včetně `theme` a `assets` (relativní cesty pod `/overlay/web/`). State se coalescuje, eventy jdou hned. Reconnect backoff 1/2/5/10 s řeší frontend.

Ikony se stavovou barvou (`currentColor`) se na HUD kreslí přes CSS `mask-image`, ne jako `<img>`.

### V4 event envelopes (`v2_payload=true`)

Když je v `config.ini` zapnuto `[event_engine] v2_payload = true`, transientní overlay eventy na `WS /ws/overlay` používají **V4 obálku** místo legacy `{type, name, phase, channel, …}`. Legacy tvar zůstává, dokud je flag vypnutý (výchozí).

**Zprávy na stejném socketu**

| `type` | Kdy | Účel |
|--------|-----|------|
| `snapshot` | hned po connectu | race / bio / system + `activeEvents` (legacy aktivní eventy) |
| `STATE_SNAPSHOT` | po connectu, pokud běží V4 stories | autoritativní seznam aktivních V4 příběhů (`activeStories`) |
| `state` | coalesced | doménový patch (`race`, `bio`, `system`) |
| `event` | okamžitě | transientní událost — legacy nebo V4 podle flagu |

**Fáze (`phase`) — v1 wire**

| Phase | Význam |
|-------|--------|
| `ENTER` | začátek příběhu / widgetu |
| `ACTIVE` | držení persistentního widgetu (manager může poslat hned po `ENTER`, např. battle / pit) |
| `UPDATE` | in-place refresh metrik / copy |
| `RESULT` | jednorázový výsledek (lap complete, finish, battle won, …) |
| `EXIT` | ukončení příběhu (expirace, preemption, session reset) |

Schéma definuje také `COMPACT`, `SUSPEND`, `RESUME`; v1 je většinou neposílá.

**V4 event tvar** (`format: "v4"`):

```json
{
  "type": "event",
  "format": "v4",
  "schemaVersion": "1.0",
  "eventId": "subsession:0:LAP_COMPLETE:42",
  "sequence": 42,
  "sessionId": "subsession:0",
  "eventType": "LAP_COMPLETE",
  "mode": "RACE",
  "phase": "RESULT",
  "monotonicMs": 120000,
  "priority": 10,
  "dedupeKey": "lap:12",
  "correlationId": "lap:12",
  "storyKey": "lap:12",
  "subject": { "carId": "player" },
  "metrics": { "lap": 12, "lapTime": 92.4 },
  "copy": { "headlineToken": "lap.headline", "statusToken": "lap.status" },
  "presentation": {
    "widget": "lap_complete",
    "zone": "EVENT",
    "preferredState": "RESULT",
    "minHoldMs": 2500,
    "maxHoldMs": 12000
  },
  "reason": { "detector": "lap", "rules": [], "suppressedAlternatives": [] }
}
```

Časy v `metrics` jsou **sekundy** (iRSDK float). HUD je formátuje jako `m:ss.fff` a delty jako `+0.318` / `-0.418`. Do WS neposílej předformátované stringy.

**`STATE_SNAPSHOT`** — druhá zpráva po reconnectu, pokud manager drží aktivní V4 stories:

```json
{
  "type": "STATE_SNAPSHOT",
  "activeStories": [
    {
      "eventType": "HUNTING",
      "phase": "ACTIVE",
      "sequence": 7,
      "correlationId": "battle:hunting:17"
    }
  ]
}
```

Frontend (`overlay.js`) aplikuje `activeStories` před live streamem, aby reconnect obnovil persistentní battle / pit widgety. Když `race.connected` je false, frontend přidá `html.overlay-idle` a karty + SYSINFO schová.

### Overlay session tape (JSONL)

Když je `[overlay] session_tape = true` (výchozí), při PRACTICE/QUALIFYING/RACE vzniká soubor `recordings/overlay-<utc>-<subsession>-<sessionNum>.jsonl`. Overlay `overlay_mode` bere z téhož `extract_session_type()` jako switcher (live `SessionType` / `SessionName` / `WeekendInfo`), ne jen z numeric SessionType v race vars.

Každý řádek má hodiny v sekundách:

| Pole | Význam |
|------|--------|
| `t` | sync clock: `t_stream` jinak `t_session` jinak `t_mono` |
| `t_mono` | od otevření tape — **tohle používá `--replay`** (nespí na VOD offsetu) |
| `t_stream` | od startu OBS streamu (`null` když nestreamuješ) |
| `t_session` | iRacing `SessionTime` |
| `t_green` | od prvního `SessionState=4` (Racing) na tomto tape |

`type`: `header`, `event` (WS obálka), `decision`, `stories`, `scene`, `green`, `stream_origin`. Telemetry ticky se nezapisují. `--replay` skipne `header`/`decision`/`scene`/`green`.

**Event catalog**

Mapování `eventType` → renderer state, debug inject key a family:

- soubor: [`src/irswitch/web/themes-v4/event_catalog.json`](src/irswitch/web/themes-v4/event_catalog.json)
- golden acceptance URLs: [`src/irswitch/web/overlay/GOLDEN_V4.md`](src/irswitch/web/overlay/GOLDEN_V4.md)

V1 catalog: **33** wired states (manifest 35; `composure_test` / `high_load` deferred). Povolené debug názvy: `GET /api/overlay/debug/events`.

Související flagy: viz [CONFIG.md](CONFIG.md) — `[event_engine]` (`v2_payload`, `practice`, `quali_projection`, …) a `[overlay]` (`v4_assets`, `v4_renderer`).

### GET /api/overlay/snapshot

JSON snapshot + `theme` + `assets` (stejný payload jako první WS zpráva). Chybějící soubor je `null`, overlay spadne na CSS desku.

### POST /overlay/debug/emit

Body: `{ "name": "hunting" }`. Povolené názvy: `GET /api/overlay/debug/events`.

Security: jen localhost + header `X-Requested-With: irswitch`.

### GET /api/config

Vrací `schema`, `overlay` hodnoty a redacted `switcher` (OBS password je `***`).

### PUT /api/config

Body: `{ "values": { "sampling.default_hz": 6 } }`. Atomický zápis INI + `.bak`. Response: `applied`, `applied_live`, `needs_restart`.

Security: localhost + CSRF header. Neznámé klíče a path traversal se odmítnou.
