# RaceLab VR Widget Setup

## ⚠️ Známé omezení: RaceLab VR widgety nepodporují auto-refresh

**RaceLab VR widgety pro custom URL se načítají jen jednou při startu a neaktualizují se automaticky.**

Otestované metody, které **nefungují**:
- ❌ JavaScript (RaceLab VR widgety JS nepodporují)
- ❌ Meta refresh tagy (`<meta http-equiv="refresh">`)
- ❌ Wrapper endpoint s iframe (`/vr-status-wrapper`)
- ❌ Refresh interval v nastavení widgetu (není dostupný)
- ❌ Externí refresh mechanismy

## Aktuální stav

VR dashboard endpoint (`/vr-status`) je funkční a vrací správná data, ale **v RaceLab VR se neaktualizuje automaticky**. Widget zobrazí stav pouze v momentě, kdy se RaceLab VR spustí nebo když se widget manuálně obnoví (pokud je to vůbec možné).

## Možná řešení

### 1. Použít jiný VR overlay nástroj

Pokud potřebuješ auto-refresh funkcionalitu, zvaž použití jiného VR overlay nástroje, který podporuje auto-refresh:

- **OVR Toolkit** - podporuje auto-refresh pro custom URL widgety
- **Desktop+** - podporuje auto-refresh
- **OpenVR Overlay** - podporuje auto-refresh

### 2. Použít GR Dashboard na externím monitoru

Místo VR widgetu můžeš použít GR Dashboard (`/gr-status`) na externím monitoru, který má plnou JavaScript podporu a auto-refresh.

### 3. Kontaktovat RaceLab VR support

Pokud chceš, aby RaceLab VR podporoval auto-refresh, kontaktuj jejich support a požádej o:
- Podporu auto-refresh pro custom URL widgety
- API pro vynucení refresh widgetu
- Dokumentaci o refresh mechanismu

## Technické detaily

VR dashboard endpoint je stále dostupný a funkční:
- **URL**: `http://127.0.0.1:17321/vr-status`
- **Formát**: Statický HTML bez JavaScriptu
- **Cache busting**: URL obsahuje timestamp parametr pro zabránění cachování
- **Obsah**: Zobrazuje aktuální stav (scéna, připojení, streaming)

Problém není v endpointu, ale v omezení RaceLab VR widgetů, které nepodporují žádný refresh mechanismus.
