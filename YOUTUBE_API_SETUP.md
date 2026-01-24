# YouTube API Setup

Návod pro nastavení YouTube Data API v3 pro získávání názvu a popisu streamu.

## Obsah

- [Přehled](#přehled)
- [Postup nastavení](#postup-nastavení)
- [Nastavení API klíče v aplikaci](#nastavení-api-klíče-v-aplikaci)
- [Kvóty a limity](#kvóty-a-limity)
- [Troubleshooting](#troubleshooting)

---

## Přehled

Aplikace používá YouTube Data API v3 pro získávání názvu a popisu streamu z YouTube. API klíč je volitelný - pokud není nastaven, aplikace funguje normálně, ale nebude zobrazovat název streamu.

**Co aplikace dělá s API**:
- Získává název streamu (`title`) z YouTube
- Získává popis streamu (`description`) z YouTube
- Zobrazuje tyto informace v GR Dashboardu

**Kdy se API volá**:
- Pouze když je stream vybrán v OBS Broadcast Manager
- Pouze jednou při výběru streamu (cachování)
- Automaticky se resetuje cache při změně broadcast_id

---

## Postup nastavení

### 1. Vytvoření projektu v Google Cloud Console

1. Otevři [Google Cloud Console](https://console.cloud.google.com/)
2. Přihlas se pomocí svého Google účtu
3. Vytvoř nový projekt nebo vyber existující:
   - Klikni na dropdown s názvem projektu v horní části
   - Klikni na "New Project"
   - Zadej název projektu (např. "iRacing OBS Switcher")
   - Klikni na "Create"

### 2. Povolení YouTube Data API v3

1. V Google Cloud Console přejdi na **APIs & Services** → **Library**
2. Vyhledej "YouTube Data API v3"
3. Klikni na výsledek
4. Klikni na tlačítko **"Enable"** (Povolit)

**Poznámka**: Pokud API není povolené, API klíč nebude fungovat.

### 3. Vytvoření API klíče

1. V Google Cloud Console přejdi na **APIs & Services** → **Credentials**
2. Klikni na **"Create Credentials"** → **"API Key"**
3. Zobrazí se dialog s vytvořeným API klíčem
4. **Zkopíruj API klíč** - budeš ho potřebovat později

**Důležité**: API klíč je citlivá informace - neukládej ho do git repozitáře!

### 4. (Volitelné) Omezení API klíče

Pro zvýšení bezpečnosti můžeš omezit API klíč:

1. V dialogu s API klíčem klikni na **"Restrict Key"**
2. V sekci **"API restrictions"**:
   - Vyber **"Restrict key"**
   - Zaškrtni pouze **"YouTube Data API v3"**
3. V sekci **"Application restrictions"** (volitelné):
   - Můžeš omezit klíč pouze na IP adresu tvého počítače
   - Nebo nechat bez omezení (pro jednoduchost)
4. Klikni na **"Save"**

**Poznámka**: Omezení API klíče je doporučeno, ale není povinné pro základní funkčnost.

---

## Nastavení API klíče v aplikaci

### Windows (PowerShell)

Nastav proměnnou prostředí:

```powershell
# Pro aktuální session
$env:YOUTUBE_API_KEY = "tvůj_api_klíč_zde"

# Nebo trvale pro uživatele
[System.Environment]::SetEnvironmentVariable("YOUTUBE_API_KEY", "tvůj_api_klíč_zde", "User")
```

**Poznámka**: Po nastavení trvalé proměnné prostředí restartuj aplikaci.

### Linux/Mac (Bash)

```bash
# Pro aktuální session
export YOUTUBE_API_KEY="tvůj_api_klíč_zde"

# Nebo trvale (přidej do ~/.bashrc nebo ~/.zshrc)
echo 'export YOUTUBE_API_KEY="tvůj_api_klíč_zde"' >> ~/.bashrc
source ~/.bashrc
```

### Ověření nastavení

Po nastavení API klíče restartuj aplikaci a zkontroluj:

1. Otevři GR Dashboard (`http://127.0.0.1:17321/gr-status`)
2. Pokud je stream vybrán v OBS, měl by se zobrazit název streamu
3. Pokud API klíč chybí, zobrazí se varování: "YouTube API Klíč Nenastaven"

---

## Kvóty a limity

### Denní kvóta

YouTube Data API v3 má **denní kvótu**:
- **Výchozí kvóta**: 10,000 jednotek denně
- **Reset**: Každý den o půlnoci Pacific Time (PT)

### Spotřeba jednotek

- `liveBroadcasts.list` - **1 jednotka** na request
- `videos.list` - **1 jednotka** na request

**Poznámka**: Aplikace používá pouze tyto dva endpointy. `search.list` endpoint není používán kvůli vysoké spotřebě (100 jednotek).

### Co se stane při překročení kvóty

Pokud je kvóta překročena:
- Aplikace zobrazí varování v dashboardu: "YouTube API Kvóta Vyčerpána"
- Zobrazí se čas resetu kvóty (převádí se do lokálního časového pásma)
- Varování se zobrazí také v event logu
- Aplikace přestane volat API až do resetu kvóty

### Zvýšení kvóty

Pokud potřebuješ vyšší kvótu:
1. V Google Cloud Console přejdi na **APIs & Services** → **Quotas**
2. Vyhledej "YouTube Data API v3"
3. Můžeš požádat o zvýšení kvóty (vyžaduje ověření projektu)

---

## Troubleshooting

### API klíč není rozpoznán

**Příznaky**: V dashboardu se zobrazuje "YouTube API Klíč Nenastaven".

**Řešení**:
1. Zkontroluj, že proměnná prostředí `YOUTUBE_API_KEY` je nastavena:
   ```powershell
   # Windows PowerShell
   $env:YOUTUBE_API_KEY
   
   # Linux/Mac
   echo $YOUTUBE_API_KEY
   ```
2. Pokud není nastavena, nastav ji podle [Nastavení API klíče v aplikaci](#nastavení-api-klíče-v-aplikaci)
3. Restartuj aplikaci po nastavení proměnné prostředí

### API vrací chybu 403 (Forbidden)

**Příznaky**: V logu vidíš "YouTube API returned status 403".

**Možné příčiny**:
1. **API není povolené**: Zkontroluj, že YouTube Data API v3 je povolené v Google Cloud Console
2. **API klíč je omezený**: Zkontroluj omezení API klíče v Google Cloud Console
3. **Kvóta překročena**: Zkontroluj, zda není překročena denní kvóta

**Řešení**:
1. V Google Cloud Console přejdi na **APIs & Services** → **Library**
2. Ověř, že YouTube Data API v3 je **Enabled**
3. V **APIs & Services** → **Credentials** zkontroluj omezení API klíče
4. V **APIs & Services** → **Quotas** zkontroluj využití kvóty

### API vrací chybu 401 (Unauthorized)

**Příznaky**: V logu vidíš "YouTube API returned status 401".

**Možné příčiny**:
1. **Neplatný API klíč**: API klíč je nesprávný nebo byl smazán
2. **API klíč není správně nastaven**: Proměnná prostředí není správně načtena

**Řešení**:
1. Zkontroluj, že API klíč je správně nastaven v proměnné prostředí
2. Vytvoř nový API klíč v Google Cloud Console
3. Aktualizuj proměnnou prostředí s novým klíčem
4. Restartuj aplikaci

### Název streamu se nezobrazuje

**Příznaky**: Stream běží, ale název se nezobrazuje v dashboardu.

**Možné příčiny**:
1. **Stream není vybrán v OBS**: Aplikace získává název pouze když je stream vybrán v Broadcast Manager
2. **API klíč není nastaven**: Nastav `YOUTUBE_API_KEY` proměnnou prostředí
3. **Kvóta překročena**: Zkontroluj varování v dashboardu
4. **Broadcast nemá broadcast_id**: Stream musí být správně nastaven v OBS

**Řešení**:
1. Otevři OBS → Tools → Broadcast Manager
2. Vyber stream, který chceš použít
3. Zkontroluj, že stream má nastavený YouTube broadcast
4. Zkontroluj, že API klíč je nastaven a aplikace je restartovaná

---

## Bezpečnost

### Ochrana API klíče

**Důležité**: API klíč je citlivá informace. Chraň ho před zveřejněním:

- ❌ **NEUKLÁDEJ** API klíč do git repozitáře
- ❌ **NESDÍLEJ** API klíč veřejně
- ✅ **POUŽÍVEJ** proměnné prostředí pro uložení klíče
- ✅ **OMEZ** API klíč v Google Cloud Console (doporučeno)

### Omezení API klíče

Pro zvýšení bezpečnosti:
1. Omez API klíč pouze na YouTube Data API v3
2. Omez API klíč na IP adresu tvého počítače (pokud je statická)
3. Pravidelně rotuj API klíče (vytvoř nový, použij ho, smaž starý)

---

## Další informace

- [YouTube Data API v3 Dokumentace](https://developers.google.com/youtube/v3)
- [Google Cloud Console](https://console.cloud.google.com/)
- [YouTube API Quotas](https://developers.google.com/youtube/v3/getting-started#quota)
