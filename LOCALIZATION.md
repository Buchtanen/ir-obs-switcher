# Lokalizace (Internationalization)

Popis systému lokalizace aplikace a podporovaných jazyků.

## Obsah

- [Přehled](#přehled)
- [Podporované jazyky](#podporované-jazyky)
- [Nastavení jazyka](#nastavení-jazyka)
- [Rozsah lokalizace](#rozsah-lokalizace)
- [Přidání nového jazyka](#přidání-nového-jazyka)

---

## Přehled

Aplikace podporuje více jazyků pro rozhraní. Všechny texty v HTML dashboardech, event logu a toast notifikacích jsou lokalizovány.

**Výchozí jazyk**: Čeština (CS)

**Automatické použití**: Aplikace automaticky použije zvolený jazyk při startu - není potřeba restartovat pro změnu jazyka.

**Fallback**: Pokud je nastaven neplatný jazyk, použije se výchozí čeština (CS).

---

## Podporované jazyky

| Kód | Jazyk | Název |
|-----|-------|-------|
| `CS` | Čeština | Český |
| `EN` | Angličtina | English |
| `DE` | Němčina | Deutsch |
| `FR` | Francouzština | Français |
| `SP` | Španělština | Español |
| `PL` | Polština | Polski |
| `HU` | Maďarština | Magyar |

---

## Nastavení jazyka

Jazyk se nastavuje v konfiguračním souboru `config.ini` v sekci `[app]`:

```ini
[app]
language = EN
```

**Příklady**:
```ini
language = CS  # Čeština (výchozí)
language = EN  # Angličtina
language = DE  # Němčina
language = FR  # Francouzština
language = SP  # Španělština
language = PL  # Polština
language = HU  # Maďarština
```

**Poznámka**: Kód jazyka je case-insensitive - `EN`, `en`, `En` jsou ekvivalentní.

**Více informací**: Viz [CONFIG.md](CONFIG.md) pro detailní popis konfigurace.

---

## Rozsah lokalizace

Lokalizovány jsou všechny texty v:

### HTML Dashboardy

- **GR Dashboard** (`/gr-status`):
  - Status texty (Connected/Disconnected)
  - Health banner při offline iRacing/OBS (actionable tipy; skrytý když jsou oba připojení)
  - Názvy sekcí (iRacing Connection, OBS Connection, Stream Title, atd.)
  - Stream informace
  - Metriky (Scene Switches, Avg Latency, Uptime, atd.)
  - YouTube API zprávy

- **VR Dashboard** (`/vr-status`):
  - Název scény
  - Status indikátory

### Event Log

- Typy eventů (Application Started, Connection Lost, Scene Switched, atd.)
- Toast notifikace

### Stream Informace

- Stream Title label
- Stream Description label
- YouTube API zprávy (kvóta vyčerpána, API klíč chybí)
- Čas resetu kvóty (převádí se do lokálního časového pásma)

---

## Přidání nového jazyka

Pokud chceš přidat podporu pro nový jazyk:

1. Otevři `src/irswitch/i18n.py`
2. Přidej nový kód jazyka do `SUPPORTED_LANGUAGES`:
   ```python
   SUPPORTED_LANGUAGES = ["CS", "EN", "DE", "FR", "SP", "PL", "HU", "TVŮJ_KÓD"]
   ```
3. Přidej překlady do `TRANSLATIONS` slovníku:
   ```python
   "TVŮJ_KÓD": {
       "connected": "Překlad",
       "disconnected": "Překlad",
       # ... všechny ostatní klíče
   }
   ```
4. Aktualizuj dokumentaci (tento soubor a CONFIG.md)

**Seznam všech překladových klíčů**:
- `connected`, `disconnected`
- `iracing_connection`, `obs_connection`, `obs_profile`, `current_scene`, `mode`
- `stream`, `current_stream`, `planned_stream`, `stream_title`, `stream_description`, `not_available`, `streaming`
- `youtube_api_quota_exceeded`, `youtube_api_key_not_configured`, `youtube_quota_message`, `youtube_key_message`
- Všechny event typy (viz `i18n.py` pro kompletní seznam)
- `iracing_connected`, `obs_connected`, `cumulative`, `current`
- `n_a`, `stream_duration`, `session_type`, `session_name`, `session_num`
- `scene_switches`, `avg_latency`, `uptime`, `autoswitch`, `scene_switch_reason`
- `toggle_autoswitch`, `enabled`, `disabled`, `on`, `off`

**Poznámka**: Klíč `youtube_quota_message` podporuje parametr `{time}` pro zobrazení času resetu kvóty.

---

## Technické detaily

### Implementace

Lokalizace je implementována v modulu `src/irswitch/i18n.py`:
- `Translator` třída pro překlad klíčů
- Globální instance pro přístup z celé aplikace
- Automatická inicializace při startu aplikace podle konfigurace

### Použití v kódu

**Python**:
```python
from irswitch.i18n import t, get_translator

# Použití globální funkce
text = t('connected')

# Nebo přes translator instanci
translator = get_translator()
text = translator.t('connected')
```

**JavaScript** (v dashboardu):
```javascript
// Funkce t() je dostupná v JavaScriptu
const text = t('connected');
```

### Formátování s parametry

Některé překlady podporují parametry:

```python
# Python
text = t('youtube_quota_message', time='08:00')

# JavaScript
const text = t('youtube_quota_message', {time: '08:00'});
```

V překladu použij `{time}` pro parametr:
```python
"youtube_quota_message": "Název streamu nedostupný do resetu kvóty ({time})"
```
