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
  - [GET /api/admin/status](#get-apiadminstatus)
  - [GET /api/admin/activity](#get-apiadminactivity)
- [WebSocket Endpoint](#websocket-endpoint)
  - [WS /ws](#ws-ws)
- [HTML Dashboardy](#html-dashboardy)
  - [GET /admin](#get-admin)
  - [GET /gr-status](#get-gr-status)
  - [GET /vr-status](#get-vr-status)
  - [GET /test](#get-test)
  - [GET /overlay](#get-overlay)
  - [GET /overlay/debug](#get-overlaydebug)
  - [GET /overlay/demo](#get-overlaydemo)
  - [GET /config](#get-config)
  - [GET /commentary](#get-commentary)
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
- `stream_chapters` (array, pouze když `[stream_chapters] enabled = true`) - in-memory kapitoly aktuálního streamu; každá položka: `title`, `offset_seconds`, `session_type`, `created_at_ms`. Když je feature vypnutá, pole chybí. Při `youtube_vod = true` se stejný seznam po skončení streamu (fail-soft, s retry) zapisuje do YouTube description VOD.

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
  "commentary": {
    "status": "disabled",
    "reason": null
  },
  "timestamp": 1704110400000
}
```

**Status hodnoty**:
- `healthy` - oba připojené (iRacing i OBS)
- `degraded` - jeden připojený
- `unhealthy` - žádný připojený

**Commentary** (`#273` / `#284` bounded field via `project_commentary_health_component`):
- Top-level `{status, reason}` only — never flips overall `/health` alone.
- Resolves process `get_narrative_runtime()` when attached; otherwise library disabled snapshot.
- Full operator detail remains on `GET /api/commentary/runtime`.

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
  "needs_restart": ["app.http_port"],
  "commentary_config": {
    "installed": true,
    "desired_generation": 7,
    "apply_sequence": 21,
    "desired_hash": "sha256:...",
    "effective_hash": "sha256:...",
    "pending_changes": [
      {
        "key": "commentary.tts.voice",
        "boundary": "next_utterance",
        "desired_generation": 7
      }
    ],
    "automatic_enabled": true,
    "speech_language": "en",
    "diagnostics": [],
    "preflights": [{"component": "tts", "generation": 7}]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `applied_live` | `string[]` | Changed keys that apply without process restart (diff old vs new; whitelist from `CONFIG.md`) |
| `needs_restart` | `string[]` | Changed keys that still require a process restart |
| `commentary_config` | `object` | Persistent v2 ConfigLedger projection for this reload |

Prázdné seznamy = žádný tracked klíč se nezměnil, nebo nebylo s čím porovnat (chybí předchozí runtime config).

`commentary_config.installed=false` znamená, že commentary kandidát byl odmítnut bez nové generace. HTTP odpověď přesto zůstává 200 a ostatní validní aplikační domény se reloadují. `diagnostics` obsahuje `reason`, `source_key`, případné `replacement_keys` a bezpečnou zprávu bez hodnoty. `pending_changes` zveřejňuje pouze klíč, přesnou apply boundary a desired generation, nikdy citlivou hodnotu. `command` boundary se aplikuje uvnitř reload coordinatoru; ostatní boundaries čekají na svého runtime ownera. `preflights` jsou generation-tagged požadavky pro změněné LLM/TTS komponenty a `speech_language` je vždy `en`.

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

### GET /api/admin/status

Agregovaný stav pro admin shell (`/admin`): extensions + features + switcher subset + server-side `health`.

**URL**: `http://127.0.0.1:17321/api/admin/status`

**Method**: `GET`

**Response** (200 OK) — klíčová pole (`schemaVersion: 1`, additive):
- `runtime.overlay` / `runtime.switcher` (bool)
- `health` — server-side aggregation:
  - `ready` (bool) — `false` jen když existuje alespoň jedna **blocking** položka
  - `blocking[]` — `{id, reason, tip}` (např. iRacing/OBS disconnected)
  - `warnings[]` — doporučené závislosti (LHM unreachable, sysinfo degraded, …); samy o sobě `ready` neflipují
- `switcher` (object | null) — legacy snake_case subset: `connected_iracing`, `connected_obs`, `autoswitch`, `mode`, scény, `reason`
- `extensions.ble` / `extensions.sysinfo` — karty: `enabled`, `available`, `active`, `busy`, `status`, `severity`, `detail`
- `extensions.lhm` — `required`, `requirementMode` (`optional`|`recommended`|`required`), ne falešné `enabled`; tip jen když required/recommended a unhealthy
- `extensions.lhm.detail` — cache observability: `checkedAt`, `lastSuccessAt` (wall-clock epoch), `stale`, `errorCode`, `lastBaseUrl`, `sensorRows`, `connection`
- `features.overlay` / `features.commentary` / `features.tape` — stejné osy; commentary `ready` = active+not busy
- `features.eventEngine` — rollout flagy (`v2Payload`, `practice`, …)

Aggregator čte **public** `status_snapshot()` (overlay runtime) + LHM cache (`force=False`). LHM probe je fail-soft (TTL + worker thread); HTTP 200 i při unreachable. Kontrakt: [`docs/admin_dashboard_spec.md`](docs/admin_dashboard_spec.md).

---

### GET /api/admin/activity

Merged activity feed (newest-first): switcher EventLog + commentary decisions + overlay **lifecycle ring** (`OverlayActivityLog`; bounded, `dedupeKey`, wall `occurredAt`).

**URL**: `http://127.0.0.1:17321/api/admin/activity?limit=50`

**Query**: `limit` (1–200, default 50; neplatné → 50)

**Response**:
```json
{
  "schemaVersion": 1,
  "items": [
    {
      "occurredAt": 1710000000.12,
      "monoMs": 12345,
      "dedupeKey": "commentary:spoken:overtake:…",
      "source": "commentary",
      "kind": "spoken",
      "message": "He takes P5 from Rossi.",
      "ephemeral": false,
      "data": { "nodeId": "overtake", "reason": "ok" }
    },
    {
      "occurredAt": 1710000001.0,
      "monoMs": 100000,
      "dedupeKey": "overlay:hunting:ENTER:100000",
      "source": "overlay",
      "kind": "hunting",
      "phase": "ENTER",
      "message": "Widget hunting (ENTER)",
      "ephemeral": false
    }
  ]
}
```

`occurredAt` = wall-clock UTC epoch seconds (všechny zdroje). `source`: `switcher` | `commentary` | `overlay`. Overlay items are **lifecycle history**, not a live `active_events` dump.

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
- `offset_seconds` je floor ze společných broadcast hodin. Autoritativní zdroj je OBS WebSocket v5 `outputDuration` v milisekundách; při jeho výpadku hodiny pokračují monotónně a v rámci jednoho broadcastu se nikdy nevrátí zpět.
- Krátký stop (< 2 s) zachová čas i historii. Známý stejný broadcast ID zachová stejnou osu i přes delší reconnect. Historie a čas se resetují společně až při potvrzeném novém broadcastu. Pokud se po reconnectu odstraní dříve přidaný koncový marker, server pošle nový `stream_chapters_snapshot`, aby klient nahradil celou historii.
- Při `[stream_chapters] youtube_vod = true` se timestampy zapisují do YouTube VOD description **až po skončení streamu** (blok `--- irswitch chapters ---`), s retry 0 s / 30 s / 3 min / 10 min. Formát `00:00` první, mezery ≥ 10 s. Vyžaduje OAuth write scope `youtube` (ne jen `readonly`). OBS `CreateRecordChapter` se nepoužívá. Pokud description obsahuje řádek `Track:`, flush ho přepíše display name z `WeekendInfo` (ne šablona Imola).

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

### GET /admin

Primární **admin shell** (live): overview + extensions + features + activity.

**URL**: `http://127.0.0.1:17321/admin`

**Podstránky**:
- `/admin/extensions` — BLE, Libre Hardware Monitor, sysinfo
- `/admin/features` — overlay / commentary / tape enabled vs active
- `/admin/activity` — merged live log
- Static: `/admin/web/css/admin.css`, `/admin/web/js/admin.js`

Live data: poll `GET /api/admin/status` + `GET /api/admin/activity` (~2 s); optional WS invalidate (`/ws`, `/ws/overlay`) debounced — stránky otevírají jen potřebné sockety. Overview zobrazuje server-side `health`.

---

### GET /gr-status

Velký dashboard / switcher controls (legacy GR Dashboard).

**URL**: `http://127.0.0.1:17321/gr-status`

**Method**: `GET`

**Popis**: 
- JavaScript auto-update
- Zobrazuje status, event log, streaming info, metrics
- Konfigurovatelné obrázky a loga
- Real-time aktualizace přes JavaScript
- Navigace odkazuje na `/admin`

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

### GET /commentary

Testovací stránka komentáře / TTS (`src/irswitch/web/commentary/index.html`).

- **Mluvit v prohlížeči** — Web Speech API (Edge/Chrome), bez serverového enginu
- **Mluvit na serveru** — `POST /api/commentary/speak` → SAPI / SuperTonic / espeak (jen `audio_device`) a duck OBS `duck_input` (fade `duck_fade_ms`; SuperTonic syntéza běží během fade-out, play až je duck dole)
- **Proč ticho** — načítá `GET /api/commentary/decisions` (ring buffer z CommentaryDirector)
- V2 commentary konfigurace se na této legacy testovací stránce neukládá. Upravuje se v `config.ini` a načítá přes `POST /config/reload`; legacy `commentary.*` ani `commentary.graph_runtime.mode` nejsou v `PUT /api/config` schématu.

**API**

| Method | URL | Poznámka |
| --- | --- | --- |
| `GET` | `/api/commentary/status` | backend, hlasy, nody grafu, rollout nastavení a sample řádek, `audioHint` (VAD) |
| `GET` | `/api/commentary/runtime` | `#284` commentary-runtime/2 subset from `project_runtime_status` (library/disabled when no provider; `APP_NARRATIVE_RUNTIME` or process-level `set_narrative_runtime`; does not start NarrativeRuntime) |
| `GET` | `/api/commentary/runtime/decisions?limit=20` | `#284` / `#273` commentary-runtime/2 decisions ring from NarrativeRuntime (`limit` clamp 1–100; newest-first; capacity `DECISION_CAPACITY=128`; additive to legacy `/api/commentary/decisions`) |
| `POST` | `/api/commentary/runtime/validate` | `#284` / `#273` offline validate against caller bindings (`commentary-runtime/2`; **200** even when `valid=false`; **400** malformed; no live runtime required) |
| `POST` | `/api/commentary/runtime/speak` | `#284` / `#273` manual speak via `NarrativeRuntime.try_manual_speak` + `ManualAdmissionLatch` (**202** accepted / **409** `speech_busy` / **422** `validation_failed` / **503** `component_unavailable`\|`mailbox_overloaded`\|`admission_timeout`; additive to legacy `/api/commentary/speak`) |
| `GET` | `/api/commentary/decisions?limit=20` | legacy speak/skip decisions; `{decisions, runtime}` |
| `POST` | `/api/commentary/validate` | legacy localhost + CSRF; `{text, nodeId}` — unchanged; final cutover to runtime validate deferred |
| `POST` | `/api/commentary/speak` | legacy localhost + CSRF; `{text, nodeId, locale, voice, rate, backend}` — unchanged; final cutover to runtime speak deferred |
| `GET` | `/api/commentary/assignments` | markdown zadání pro textový model |

`speak` nejdřív pustí TTS validator.

### GET /api/commentary/runtime

`#284` read-only mount of the `commentary-runtime/2` status subset produced by `project_runtime_status`.

**URL**: `http://127.0.0.1:17321/api/commentary/runtime`

**Behavior**
- Additive to legacy `GET /api/commentary/status` (TTS test page); does not replace it.
- Status provider resolution: `APP_NARRATIVE_RUNTIME` on the aiohttp app first, then process-level `set_narrative_runtime` / `get_narrative_runtime` (race shadow fanout cutover path). If neither is set, returns a **disabled** library snapshot (no actor loop).
- Does **not** start `NarrativeRuntime.run()`, does **not** speak, and does **not** cut over live `CommentaryConsumer` EventSubscription.
- `#273` identity subset on `timeline` + fixed `language=en` + full idle `speech` shape + bounded `components.{llm,tts,tape,detectors,facts}`: `broadcastEpoch`, `streamEpoch`, `narrativeRunActive`, `streamActive`, `streamState`, `historyComplete`.
- `#273` thin status_ready stubs (feat `03c34b2`): `catalog` (`narrative-catalog/2`, packaged catalog `hash`, `eventIdentifierCount: 60`, `beatCount: 64`), `config` (unloaded zeros), `episodes` (empty counts + capacity constants), `byTapeChannel: {}`, `queues.opportunities` (depth 0, capacity 128), `components.detectors` / `components.facts` ready stubs. **Not** live product wiring — defaults only.
- `#273` decisions ring at `GET /api/commentary/runtime/decisions`; validate/speak at `POST /api/commentary/runtime/validate|speak` (thin slice landed; `ManualAdmissionLatch` rendezvous at feat `ca0f2f6`; legacy `/api/commentary/validate|speak` cutover deferred). Full live catalog/config/episodes/tape-channel/detectors/facts wiring remains later.
- Full schema / live actor attachment remain a later #284 cutover slice.

**Example (disabled / no provider)**

```json
{
  "schemaVersion": "commentary-runtime/2",
  "status": "disabled",
  "reason": null,
  "language": "en",
  "catalog": {
    "schemaVersion": "narrative-catalog/2",
    "hash": "sha256:7dafad15db5de649d857cbe7964a2c94abd3182c459bb06d5e415415b9e101a0",
    "eventIdentifierCount": 60,
    "beatCount": 64
  },
  "config": {
    "schemaVersion": "commentary-config/2",
    "desiredGeneration": 0,
    "desiredHash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "effectiveHash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "applySequence": 0,
    "pendingChanges": []
  },
  "episodes": {
    "active": 0,
    "candidate": 0,
    "suspended": 0,
    "retainedCurrentCapacity": 64,
    "resolved": 0,
    "resolvedCapacity": 256
  },
  "byTapeChannel": {},
  "speech": {
    "state": "idle",
    "sourceKind": null,
    "utteranceId": null,
    "beatId": null,
    "opportunityId": null,
    "backend": null,
    "backendGeneration": null,
    "dispatchedAtMonoMs": null,
    "acceptedAtMonoMs": null,
    "lastTerminal": null
  },
  "components": {
    "llm": { "status": "ready", "reason": null },
    "tts": { "status": "ready", "reason": null },
    "tape": {
      "status": "disabled",
      "reason": null,
      "path": null,
      "drops": 0,
      "dropsByPriority": { "sample": 0, "normal": 0, "critical": 0 }
    },
    "detectors": { "status": "ready", "reason": null, "disabled": [] },
    "facts": {
      "status": "ready",
      "reason": null,
      "viewRevision": 0,
      "active": 0,
      "historicalSummaries": 0,
      "historyComplete": true
    }
  },
  "queues": {
    "mailbox": { "depth": 0, "capacity": 64, "overflows": 0 },
    "opportunities": { "depth": 0, "capacity": 128, "expired": 0, "evicted": 0 }
  },
  "timeline": {
    "broadcastEpoch": 0,
    "streamEpoch": 0,
    "narrativeRunActive": false,
    "streamActive": null,
    "streamState": "unknown",
    "historyComplete": true
  },
  "recovery": {
    "count": 0,
    "lossFirst": null,
    "lossLast": null,
    "safetyEffectCount": 0,
    "cancelledLane": null
  },
  "diagnostics": {
    "lastAdmissionReason": null,
    "admissionDiagnostics": [],
    "reasonCodes": []
  }
}
```

Golden subset lock: `tests/fixtures/commentary_runtime/status_ready_library.json` (catalog/config/episodes/byTapeChannel/opportunities/detectors/facts stubs only; feat `03c34b2`).

### GET /api/commentary/runtime/decisions

`#284` / `#273` read-only mount of the `commentary-runtime/2` decisions ring recorded by `NarrativeRuntime` on each StoryDirector consult (selected / silence / replaced).

**URL**: `http://127.0.0.1:17321/api/commentary/runtime/decisions?limit=20`

**Behavior**
- Additive to legacy `GET /api/commentary/decisions` (CommentaryDirector speak/skip log); does not replace it.
- Provider resolution matches `GET /api/commentary/runtime` (`APP_NARRATIVE_RUNTIME` then process-level `set_narrative_runtime`). No provider → `{schemaVersion, runtime:false, decisions:[]}`.
- `limit` defaults to 20 and clamps to 1–100; rows are newest-first; ring capacity is `DECISION_CAPACITY` (128).
- Does **not** start the actor loop. Rows are projected by `build_runtime_decision_entry` / `project_runtime_decisions`.

**Example (selected)**

```json
{
  "schemaVersion": "commentary-runtime/2",
  "runtime": true,
  "decisions": [
    {
      "reducerSequence": 418,
      "atMonoMs": 90231,
      "decision": "selected",
      "reason": "highest_valid_candidate",
      "beatId": "battle.approach",
      "episodeId": "battle-ahead:3:17:22:4",
      "opportunityId": "opp:401",
      "tapeChannel": "race.battle.closing",
      "candidateSource": "event_opportunity",
      "candidateOrder": {"reducerSequence": 417, "sourceOrdinal": 0},
      "relation": "updates_active_episode",
      "urgency": "story",
      "score": 68.5,
      "threshold": 35.0,
      "runnerUp": {"beatId": "battle.pursuit", "score": 56.0},
      "terminalReason": null
    }
  ]
}
```

Invalid `limit` query values fall back to the default **20** (clamped to 1–100); the handler does not return 400.

### POST /api/commentary/runtime/validate

`#284` / `#273` offline validate: projects caller-supplied EN text against one `beatId` and immutable `actorBindings` / `factBindings` via `project_validate_response` (`events/narrative_validate_projection.py`).

**URL**: `http://127.0.0.1:17321/api/commentary/runtime/validate`

**Method**: `POST`

**Content-Type**: `application/json`

**Behavior**
- Additive to legacy `POST /api/commentary/validate` (sequence-graph `nodeId` validator + CSRF); does **not** replace it. Final legacy cutover deferred.
- **Offline** — does not read live `NarrativeRuntime` state, roster, or Qwen; no provider required.
- Syntactically valid requests always return **200** with a `ValidateResponse` body; `valid` is `false` when any issue has severity `error`.
- Malformed requests (schema/ binding violations) return **400** with `commentary-runtime/2` error envelope `{schemaVersion, error: {code, fields, message}}` (`code`: `invalid_json` | `invalid_request`).

**Request** (`commentary-runtime/2`): `schemaVersion`, `text` (1–512 chars, no control chars), `beatId`, `evaluationAtMonoMs`, `actorBindings` (1–16 actors, 1–8 aliases each), `factBindings` (1–32 `atomic-fact/2` rows; actors must cover fact subjects/objects exactly).

**Example (supported)** — golden `tests/fixtures/commentary_runtime/validate_supported.json`:

```json
{
  "schemaVersion": "commentary-runtime/2",
  "valid": true,
  "beatId": "battle.approach",
  "issues": [],
  "claims": [
    {
      "predicate": "battle.approaching",
      "subjectId": "hero",
      "objectId": "car:22",
      "verdict": "supported"
    }
  ]
}
```

**Example (rejected, actor reversed)** — golden `tests/fixtures/commentary_runtime/validate_rejected.json`: `valid: false`, issue `actor_reversed`.

### POST /api/commentary/runtime/speak

`#284` / `#273` manual EN speak: admits one utterance through `NarrativeRuntime.try_manual_speak` with a one-shot `ManualAdmissionLatch` (`events/narrative_manual_latch.py`; default `ADMISSION_TIMEOUT_S=1.0`).

**URL**: `http://127.0.0.1:17321/api/commentary/runtime/speak`

**Method**: `POST`

**Content-Type**: `application/json`

**Behavior**
- Additive to legacy `POST /api/commentary/speak` (TTS test page + CSRF + sequence-graph validator); does **not** replace it. Final legacy cutover deferred.
- Provider resolution matches status mount (`APP_NARRATIVE_RUNTIME` then `get_narrative_runtime()`). Provider must expose `try_manual_speak`.
- Requires `schemaVersion: commentary-runtime/2` and `language: en`. Does **not** use legacy CSRF middleware.
- Allocates a latch per `requestId`, nonblocking-admits `MANUAL_SPEAK_REQUEST`, then awaits actor resolution (default 1s). `_on_manual` claims the latch before lane mutation and resolves `accepted` / `speech_busy` / `component_unavailable`. On timeout the caller abandons the latch and returns `admission_timeout`; the abandoned latch stays registered so a later reduce cannot speak (`ignored_stale_or_inapplicable` / `manual_abandoned`).
- When the actor loop is **not** running, `try_manual_speak` reduces inline (`reduce_inline` default) so library/HTTP tests stay deterministic; when the actor loop **is** running, admission waits on the latch instead of inline reduce.
- Does **not** start the actor loop by itself (do not call `try_manual_speak` concurrently with `run()` in library tests).

**Request** (`commentary-runtime/2`): `schemaVersion`, `language` (`en` only), `text` (non-empty string).

**Responses**

| Status | Body | When |
| --- | --- | --- |
| **202** | `{schemaVersion, accepted: true, requestId, admittedState}` | Manual speak admitted (`admittedState` typically `committed`) |
| **409** | `{schemaVersion, error: {code: speech_busy, …}}` | Speech lane busy |
| **422** | `{schemaVersion, error: {code: validation_failed, …}}` | Missing/invalid `text` or command construction failed |
| **503** | `{schemaVersion, error: {code: component_unavailable\|mailbox_overloaded\|admission_timeout, …}}` | No provider / no `try_manual_speak` / mailbox full / reduce miss / latch await timed out |
| **400** | `{schemaVersion, error: {code: invalid_json\|invalid_request, …}}` | Bad JSON or wrong `schemaVersion` / `language` |

**Example (accepted)** — shape from golden `tests/fixtures/commentary_runtime/speak_accepted.json` (`requestId` is server-generated, e.g. `manual:7f5b`):

```json
{
  "schemaVersion": "commentary-runtime/2",
  "accepted": true,
  "requestId": "manual:7f5b",
  "admittedState": "committed"
}
```

**Example (admission timeout)** — golden `tests/fixtures/commentary_runtime/error_admission_timeout.json`:

```json
{
  "schemaVersion": "commentary-runtime/2",
  "error": {
    "code": "admission_timeout",
    "fields": {},
    "message": "Bounded public detail."
  }
}
```

### GET /api/commentary/decisions (legacy)

Legacy CommentaryDirector speak/skip log (`{decisions, runtime}`). Unrelated to the NarrativeRuntime ring above.

 Neplatný řádek → 400, audio se nespustí.

**Decision reason codes** (`action` = `spoken` \| `skipped`):

| reason | Význam |
| --- | --- |
| `spoken` | řádek odeslán do TTS sinku |
| `disabled` | `commentary.enabled=false` |
| `busy` | TTS ještě hraje předchozí řádek |
| `global_cooldown` | `commentary.cooldown_s` |
| `no_speak_phase` | envelope phase není ENTER/RESULT/EXIT |
| `no_node` | žádný uzel v grafu pro event type |
| `node_cooldown` | per-node cooldown |
| `hr_gate` | emoce mimo `hr_states` uzlu |
| `no_variant` | prázdný emotion bucket |
| `slot_unbound` | žádný řádek bez nevyplněných `{slot}` |
| `validator_reject` | `validate_utterance` odmítl |

Config: `commentary.decision_log_size` (default 32). Live readiness matrix: [docs/commentary_live_node_matrix.md](docs/commentary_live_node_matrix.md).

### WS /ws/overlay

Po connectu okamžitý `snapshot` včetně `theme` a `assets` (relativní cesty pod `/overlay/web/`). State se coalescuje, eventy jdou hned. Reconnect backoff 1/2/5/10 s řeší frontend.

Ikony se stavovou barvou (`currentColor`) se na HUD kreslí přes CSS `mask-image`, ne jako `<img>`.

### V4 event envelopes (`v2_payload=true`)

Když je v `config.ini` zapnuto `[event_engine] v2_payload = true`, transientní overlay eventy na `WS /ws/overlay` používají **V4 obálku** místo legacy `{type, name, phase, channel, …}`. Legacy tvar zůstává, dokud je flag vypnutý (výchozí).

**Zprávy na stejném socketu**

| `type` | Kdy | Účel |
|--------|-----|------|
| `snapshot` | hned po connectu | race / bio / system + `activeEvents` (legacy aktivní eventy) |
| `STATE_SNAPSHOT` | vždy po connectu a coalesced po změně V4 stories | autoritativní seznam aktivních V4 příběhů (`activeStories`), i prázdný |
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
  "correlationId": "run:1:lap:12",
  "storyKey": "run:1:lap:12",
  "subject": { "carId": "player" },
  "metrics": { "lap": 12, "lapTime": 92.4, "runEpoch": 1 },
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

`runEpoch` rozlišuje opakované starty pod stejným iRacing session klíčem. Po potvrzeném přetočení `SessionTime` se zvýší a `correlationId` dostane prefix `run:<epoch>:`. ENTER/UPDATE/EXIT z předchozího runu se proto nemohou spárovat s novým závodem.

Event, který může sdílet commentary a overlay lifecycle, nese objekt `miniStory`:

```json
{
  "storyId": "story:1:42",
  "storyRevision": 2,
  "runEpoch": 1,
  "heroOrderRevision": 3,
  "correlationId": "run:1:battle:hunting:17",
  "eventType": "HUNTING",
  "state": "speaking"
}
```

`state` je `ready`, `building`, `committed`, `speaking`, `resolved`, `completed`, `interrupted` nebo `invalidated`. Vyšší `storyRevision` je autoritativní; opožděný nižší stav se ignoruje.

**`STATE_SNAPSHOT`** — vždy druhá zpráva po reconnectu; dále při změně autoritativního seznamu. Seznam slučuje živý source snapshot s kartami, které drží MiniStory presentation lease. Běžný source `EXIT` leased kartu přepne na `RESULT`, ale odstraní ji až TTS `completed`/`interrupted`/`invalidated` nebo reset. Poslední odstranění a session reset posílají `activeStories: []`. Nezměněný seznam se znovu neposílá:

```json
{
  "type": "STATE_SNAPSHOT",
  "activeStories": [
    {
      "eventType": "HUNTING",
      "phase": "ACTIVE",
      "sequence": 7,
      "correlationId": "run:1:battle:hunting:17"
    }
  ]
}
```

Frontend (`overlay.js`) snapshoty inkrementálně reconciliuje. Leased karta nepoužívá běžný `minHoldMs`/`maxHoldMs` timer; neleased eventy zůstávají kompatibilní se starým chováním. Když `race.connected` je false, frontend přidá `html.overlay-idle` a karty + SYSINFO schová.

### Overlay session tape (JSONL)

Když je `[overlay] session_tape = true` (výchozí), při PRACTICE/QUALIFYING/RACE vzniká soubor `recordings/overlay-<utc>-<subsession>-<sessionNum>.jsonl`. Overlay `overlay_mode` i switcher `session_type` berou z téhož `extract_session_type()`: aktivní řádek `SessionInfo.Sessions[SessionNum]` (YAML). Live telemetry `SessionType` v moderním irsdk chybí; `WeekendInfo.EventType` je produkt víkendu (často Race), ne aktuální session — proto se nepoužívá.

Každý řádek má hodiny v sekundách:

| Pole | Význam |
|------|--------|
| `t` | sync clock: `t_stream` jinak `t_session` jinak `t_mono` |
| `t_mono` | od otevření tape — **tohle používá `--replay`** (nespí na VOD offsetu) |
| `t_stream` | od startu OBS streamu (`null` když nestreamuješ) |
| `t_session` | iRacing `SessionTime` |
| `t_green` | od prvního `SessionState=4` (Racing) v aktuálním `run_epoch` |

Každý řádek navíc nese `run_epoch`. Potvrzený restart závodu ve stejné session zachová soubor, `t_mono` i `t_stream`, zapíše řádek `run_reset` a vynuluje pouze původ `t_green` pro nový run.

`type`: `header`, `event` (WS obálka), `decision`, `stories`, `scene`, `green`, `run_reset`, `stream_origin`, `commentary`, `llm_polish`. Telemetry ticky se nezapisují. `--replay` skipne `header`/`decision`/`commentary`/`llm_polish`/`scene`/`green`/`run_reset`.

Řádky `commentary` a `llm_polish` se zapisují **jen při runtime DEBUG** (`GET/POST /logging/level` → `DEBUG`) — pro offline vyhodnocení speak/skip a LLM request/response bez spamu na disk. Ostatní tape typy (`event`, `decision`, …) zůstávají pod `[overlay] session_tape`.

| Typ | Obsah |
|-----|--------|
| `commentary` | enqueue/speak/skip a MiniStory lifecycle (`action`, `reason`, `eventType`, `nodeId`, `text`, `storyId`, `storyRevision`, `runEpoch`, `heroOrderRevision`, …) |
| `llm_polish` | jeden polish pokus (`outcome`, `skeleton`, `spoken`, `request`, `response`, `latencyMs`, …) |

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

Legacy `commentary.*` klíče nejsou součástí tohoto schema-driven endpointu a vrací chybu neznámého klíče. V2 commentary se zapisuje do přesných INI sekcí z `CONFIG.md` a aktivuje přes `POST /config/reload`, který vlastní ConfigLedger generace.

Security: localhost + CSRF header. Neznámé klíče a path traversal se odmítnou.
