# VR Support - Příslib, záměr a popis problému

## Příslib a záměr

Aplikace byla vytvořena primárně pro **použití ve VR** - když jezdíš ve VR headsetu, nevidíš monitor a nemůžeš ručně ovládat OBS stream. Proto je podpora VR dashboardu jednou z klíčových funkcí aplikace.

**Záměr**: Poskytnout VR uživatelům způsob, jak vidět aktuální stav aplikace přímo ve VR headsetu, bez nutnosti sundat headset a podívat se na monitor.

---

## Implementované řešení

### VR Dashboard (`/vr-status`)

Aplikace poskytuje specializovaný VR dashboard endpoint:

- **URL**: `http://127.0.0.1:17321/vr-status`
- **Design**: Minimalistický, bílé písmo na tmavém pozadí, větší fonty pro čitelnost ve VR
- **Obsah**: 
  - Aktuální scéna
  - Status připojení (iRacing, OBS)
  - Streaming indikátor
  - Délka streamu
- **Formát**: Statický HTML bez JavaScriptu (kvůli kompatibilitě s VR overlay nástroji)

**Více informací**: Viz [RACELAB_VR_SETUP.md](RACELAB_VR_SETUP.md) pro detailní návod nastavení.

---

## Známé problémy a omezení

### ⚠️ RaceLab VR - Auto-refresh nefunguje

**Problém**: RaceLab VR widgety pro custom URL se načítají jen jednou při startu a **neaktualizují se automaticky**.

**Otestované metody, které nefungují**:
- ❌ JavaScript (RaceLab VR widgety JS nepodporují)
- ❌ Meta refresh tagy (`<meta http-equiv="refresh">`)
- ❌ Wrapper endpoint s iframe
- ❌ Refresh interval v nastavení widgetu (není dostupný)
- ❌ Externí refresh mechanismy

**Důsledek**: VR dashboard zobrazí stav pouze v momentě, kdy se RaceLab VR spustí nebo když se widget manuálně obnoví (pokud je to vůbec možné).

**Status**: Toto je **omezení RaceLab VR**, ne aplikace. VR dashboard endpoint (`/vr-status`) je funkční a vrací správná data, ale RaceLab VR nepodporuje žádný refresh mechanismus.

---

## Možná řešení

### 1. Použít jiný VR overlay nástroj

Pokud potřebuješ auto-refresh funkcionalitu, zvaž použití jiného VR overlay nástroje, který podporuje auto-refresh:

- **OVR Toolkit** - podporuje auto-refresh pro custom URL widgety
- **Desktop+** - podporuje auto-refresh
- **OpenVR Overlay** - podporuje auto-refresh

**Poznámka**: VR dashboard (`/vr-status`) by měl fungovat s těmito nástroji, protože poskytuje statický HTML obsah.

### 2. Použít GR Dashboard na externím monitoru

Místo VR widgetu můžeš použít GR Dashboard (`/gr-status`) na externím monitoru, který má:
- Plnou JavaScript podporu
- Auto-refresh funkcionalitu
- Kompletní informace o stavu aplikace
- Event log a metriky

**Výhoda**: Můžeš mít monitor vedle sebe a sledovat stav bez nutnosti být ve VR.

### 3. Kontaktovat RaceLab VR support

Pokud chceš, aby RaceLab VR podporoval auto-refresh, kontaktuj jejich support a požádej o:
- Podporu auto-refresh pro custom URL widgety
- API pro vynucení refresh widgetu
- Dokumentaci o refresh mechanismu

---

## Budoucí vylepšení

### Plánované funkce

1. **Podpora dalších VR overlay nástrojů**
   - Testování s OVR Toolkit, Desktop+, OpenVR Overlay
   - Optimalizace pro různé VR overlay nástroje

2. **Vylepšení VR dashboardu**
   - Větší fonty pro lepší čitelnost
   - Lepší kontrasty
   - Možnost přizpůsobení vzhledu

3. **Alternativní řešení**
   - WebSocket podpora pro real-time updates (pokud VR overlay podporuje)
   - REST API pro externí VR overlay nástroje
   - Desktop notifikace jako alternativa k VR dashboardu

### Omezení

- **RaceLab VR**: Neexistuje způsob, jak vynutit refresh widgetu bez podpory ze strany RaceLab VR
- **JavaScript**: Většina VR overlay nástrojů nepodporuje JavaScript v widgetech
- **Auto-refresh**: Záleží na podpoře konkrétního VR overlay nástroje

---

## Technické detaily

### VR Dashboard Endpoint

**URL**: `http://127.0.0.1:17321/vr-status`

**Formát**: Statický HTML bez JavaScriptu

**Obsah**:
- Status indikátory (iRacing, OBS) - zelené/červené diody
- Streaming indikátor s délkou streamu
- Aktuální název scény

**Cache busting**: URL obsahuje timestamp parametr pro zabránění cachování při manuálním refreshi

**Příklad URL**: `http://127.0.0.1:17321/vr-status?t=1704110400000`

### Proč bez JavaScriptu?

VR overlay nástroje často nepodporují JavaScript v widgetech kvůli bezpečnostním důvodům. Proto je VR dashboard navržen jako statický HTML, který může být zobrazen i v nejzákladnějších VR overlay nástrojích.

---

## Závěr

Aplikace poskytuje VR dashboard endpoint, který je funkční a vrací správná data. Problém s auto-refreshem je způsoben omezením RaceLab VR, které nepodporuje žádný refresh mechanismus pro custom URL widgety.

**Doporučení**: 
- Pro auto-refresh použij jiný VR overlay nástroj (OVR Toolkit, Desktop+, atd.)
- Nebo použij GR Dashboard na externím monitoru
- Pokud musíš používat RaceLab VR, widget zobrazí stav při startu, ale nebude se aktualizovat automaticky

**Více informací**: Viz [RACELAB_VR_SETUP.md](RACELAB_VR_SETUP.md) pro detailní návod nastavení VR dashboardu v RaceLab VR.
