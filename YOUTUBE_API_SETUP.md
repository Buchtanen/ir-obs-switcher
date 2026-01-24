# YouTube API Setup

Navod pro nastaveni YouTube Data API v3 pro ziskavani nazvu a popisu streamu.

## Obsah

- [Prehled](#prehled)
- [Metody autentifikace](#metody-autentifikace)
- [Postup nastaveni API klicem](#postup-nastaveni-api-klicem)
- [Postup nastaveni OAuth](#postup-nastaveni-oauth)
- [Nastaveni v aplikaci](#nastaveni-v-aplikaci)
- [Kvoty a limity](#kvoty-a-limity)
- [Troubleshooting](#troubleshooting)

---

## Prehled

Aplikace pouziva YouTube Data API v3 pro ziskavani nazvu a popisu streamu z YouTube. Podporuje dve metody autentifikace:

1. **OAuth 2.0** (doporuceno) - pro pristup k `liveBroadcasts` endpointu
2. **API klic** (fallback) - pro pristup k `videos` endpointu

Obě metody jsou volitelne - pokud neni nastavena zadna, aplikace funguje normalne, ale nebude zobrazovat nazev streamu.

**Co aplikace dela s API**:
- Ziskava nazev streamu (`title`) z YouTube
- Ziskava popis streamu (`description`) z YouTube
- Zobrazuje tyto informace v GR Dashboardu

**Kdy se API vola**:
- Pouze kdyz je stream vybran v OBS Broadcast Manager
- Pouze jednou pri vyberu streamu (cachovani)
- Automaticky se resetuje cache pri zmene broadcast_id

---

## Metody autentifikace

### OAuth 2.0 (doporuceno)

Vyhody:
- Pristup k `liveBroadcasts.list` endpointu (prime pro live streamy)
- Automaticky refresh tokenu
- Bezpecnejsi (uzivatel muze kdykoliv odvolat pristup)

Omezeni:
- Nutna interaktivni autorizace (otevreni browsery)
- Ulozeni tokenu na disk

### API klic (fallback)

Vyhody:
- Jednoduche nastaveni (jen promenna prostredi)
- Ziadna interakce uzivatele

Omezeni:
- `liveBroadcasts.list` vraci 401 Unauthorized (OAuth required)
- Funguje pouze s `videos.list` endpointem (broadcast_id musi byt video_id)

---

## Postup nastaveni API klicem

### 1. Vytvoreni projektu v Google Cloud Console

1. Otevri [Google Cloud Console](https://console.cloud.google.com/)
2. Prihlas se pomoci sveho Google uctu
3. Vytvor novy projekt nebo vyber existujici:
   - Klikni na dropdown s nazvem projektu v hori casti
   - Klikni na "New Project"
   - Zadej nazev projektu (napr. "iRacing OBS Switcher")
   - Klikni na "Create"

### 2. Povoleni YouTube Data API v3

1. V Google Cloud Console prejdi na **APIs & Services** → **Library**
2. Vyhledej "YouTube Data API v3"
3. Klikni na vysledek
4. Klikni na tlacitko **"Enable"** (Povolit)

**Poznamka**: Pokud API neni povolene, API klic nebude fungovat.

### 3. Vytvoreni API klice

1. V Google Cloud Console prejdi na **APIs & Services** → **Credentials**
2. Klikni na **"Create Credentials"** → **"API Key"**
3. Zobrazi se dialog s vytvorenym API klicem
4. **Zkopiruj API klic** - budes ho potrebovat pozdeji

**Dulezite**: API klic je citliva informace - neukladej ho do git repozitare!

### 4. (Volitelne) Omezeni API klice

Pro zvyseni bezpecnosti muzes omezit API klic:

1. V dialogu s API klicem klikni na **"Restrict Key"**
2. V sekci **"API restrictions"**:
   - Vyber **"Restrict key"**
   - Zaskrtni pouze **"YouTube Data API v3"**
3. V sekci **"Application restrictions"** (volitelne):
   - Muzes omezit klic pouze na IP adresu tveho pocitace
   - Nebo nechat bez omezeni (pro jednoduchost)
4. Klikni na **"Save"**

**Poznamka**: Omezeni API klice je doporceno, ale neni povinne pro zakladni funkcnost.

---

## Postup nastaveni OAuth

### 1. Vytvoreni OAuth credentials

1. V Google Cloud Console prejdi na **APIs & Services** → **Credentials**
2. Klikni na **"Create Credentials"** → **"OAuth client ID"**
3. Vyber **"Application type"**: `Desktop application`
4. Zadej **Name**: `iRacing OBS Switcher`
5. Klikni na **"Create"**
6. Stahni `credentials.json` nebo zkopiruj `Client ID` a `Client Secret`

### 2. Nastaveni OAuth Consent Screen

1. Vlevo menu → **APIs & Services** → **OAuth consent screen**
2. Vyber **External** → **Create**
3. Vypln:
   - **App name**: `iRacing OBS Switcher`
   - **User support email**: tvuj Gmail ucet
   - **Developer contact email**: tvuj Gmail ucet
4. Klikni na **Save and Continue**
5. Na SCOPES klikni **Save and Continue** (bez pridavani scopes)
6. Na TEST USERS klikni **Add Users** a pridej tvuj Gmail ucet
7. Klikni na **Save and Continue**

### 3. Extrakce credentials z JSON

Stazeny JSON soubor ma tento format:

```json
{
  "web": {
    "client_id": "123456789-abcdefghij.apps.googleusercontent.com",
    "client_secret": "GOCSPX-xxxxxxxxxxxx",
    ...
  }
}
```

PowerShell pro extrakci:

```powershell
# Precti JSON a extrahuj hodnoty
$json = Get-Content "cesta/k/tvuj-soubor.json" | ConvertFrom-Json

# Nastav promenne
$env:GOOGLE_OAUTH_CLIENT_ID = $json.web.client_id
$env:GOOGLE_OAUTH_CLIENT_SECRET = $json.web.client_secret

# Overeni
Write-Host "Client ID: $($env:GOOGLE_OAUTH_CLIENT_ID)"
Write-Host "Client Secret: $($env:GOOGLE_OAUTH_CLIENT_SECRET.Substring(0, 4))..."
```

---

## Nastaveni v aplikaci

### Windows (PowerShell) - OAuth

```powershell
# Nastav z JSON souboru
$json = Get-Content "C:\cesta\k\credentials.json" | ConvertFrom-Json
$env:GOOGLE_OAUTH_CLIENT_ID = $json.web.client_id
$env:GOOGLE_OAUTH_CLIENT_SECRET = $json.web.client_secret

# Nebo rucne
$env:GOOGLE_OAUTH_CLIENT_ID = "123456789-abcdefghij.apps.googleusercontent.com"
$env:GOOGLE_OAUTH_CLIENT_SECRET = "GOCSPX-xxxxxxxxxxxx"

# Trvale pro uzivatele
[System.Environment]::SetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_ID", "hodnota", "User")
[System.Environment]::SetEnvironmentVariable("GOOGLE_OAUTH_CLIENT_SECRET", "hodnota", "User")
```

### Windows (PowerShell) - API klic

```powershell
# Pro aktualni session
$env:YOUTUBE_API_KEY = "tvuj_api_klic"

# Trvale pro uzivatele
[System.Environment]::SetEnvironmentVariable("YOUTUBE_API_KEY", "tvuj_api_klic", "User")
```

### Linux/Mac (Bash) - OAuth

```bash
# Pro aktualni session
export GOOGLE_OAUTH_CLIENT_ID="client_id_z_json"
export GOOGLE_OAUTH_CLIENT_SECRET="secret_z_json"

# Trvale (pridej do ~/.bashrc nebo ~/.zshrc)
echo 'export GOOGLE_OAUTH_CLIENT_ID="..."' >> ~/.bashrc
echo 'export GOOGLE_OAUTH_CLIENT_SECRET="..."' >> ~/.bashrc
source ~/.bashrc
```

### Linux/Mac (Bash) - API klic

```bash
# Pro aktualni session
export YOUTUBE_API_KEY="tvuj_api_klic"

# Trvale
echo 'export YOUTUBE_API_KEY="tvuj_api_klic"' >> ~/.bashrc
source ~/.bashrc
```

### Overeni nastaveni

Po nastaveni OAuth nebo API klice restartuj aplikaci a zkontroluj:

1. Otevri GR Dashboard (`http://127.0.0.1:17321/gr-status`)
2. Pokud je stream vybran v OBS, mel by se zobrazit nazev streamu
3. Over stav na `/oauth/status` endpointu:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:17321/oauth/status"
```

---

## Kvoty a limity

### Denni kvota

YouTube Data API v3 ma **denni kotu**:
- **Vychozi kvota**: 10,000 jednotek denne
- **Reset**: Kazdy den o pulnoci Pacific Time (PT)

### Spotreba jednotek

- `liveBroadcasts.list` - **1 jednotka** na request
- `videos.list` - **1 jednotka** na request

### Co se stane pri prekroceni kvoty

Pokud je kvota prekrocena:
- Aplikace zobrazi varovani v dashboardu: "YouTube API Kvota Vycerpana"
- Zobrazi se cas resetu kvoty (prevadi se do lokalniho casoveho pasma)
- Varovani se zobrazi take v event logu
- Aplikace prestane volat API az do resetu kvoty

### Zvyseni kvoty

Pokud potrebujes vyssi kvotu:
1. V Google Cloud Console prejdi na **APIs & Services** → **Quotas**
2. Vyhledej "YouTube Data API v3"
3. Muzes pozadat o zvyseni kvoty (vyzaduje overeni projektu)

---

## Troubleshooting

### OAuth: Nelze ziskat access token

**Priznaky**: Volani YouTube API vraci chybu nebo OAuth status ukazuje chybu.

Reseni:
1. Zkontroluj, ze `GOOGLE_OAUTH_CLIENT_ID` a `GOOGLE_OAUTH_CLIENT_SECRET` jsou spravne nastaveny
2. Over, ze OAuth consent screen je nastaven a Test Users jsou pridany
3. Zkus iniciovat OAuth flow znovu na `/oauth/initiate`

### OAuth: Token vyprsel

**Priznaky**: YouTube API vraci 401 Unauthorized i kdyz je OAuth nastaven.

Reseni:
- Aplikace se pokusi automaticky refreshnout token
- Pokud refresh selze, budes muset znovu autorizovat aplikaci

### API klic nerozpoznan

**Priznaky**: V dashboardu se zobrazuje "YouTube API klic nenastaven".

Reseni:
1. Zkontroluj, ze promenna prostredi `YOUTUBE_API_KEY` je nastavena:
   ```powershell
   $env:YOUTUBE_API_KEY
   ```
2. Pokud neni nastavena, nastav ji podle navodu vys
3. Restartuj aplikaci po nastaveni promenne prostredi

### API vraci chybu 403 (Forbidden)

**Priznaky**: V logu vidis "YouTube API returned status 403".

Mozne priciny:
1. **API neni povolene**: Zkontroluj, ze YouTube Data API v3 je povolene v Google Cloud Console
2. **API klic je omezeny**: Zkontroluj omezeni API klice v Google Cloud Console
3. **Kvota prekrocena**: Zkontroluj, zda neni prekrocena denni kvota

Reseni:
1. V Google Cloud Console prejdi na **APIs & Services** → **Library**
2. Over, ze YouTube Data API v3 je **Enabled**
3. V **APIs & Services** → **Credentials** zkontroluj omezeni API klice
4. V **APIs & Services** → **Quotas** zkontroluj vyuziti kvoty

### Nazev streamu se nezobrazuje

**Priznaky**: Stream bezi, ale nazev se nezobrazuje v dashboardu.

Mozne priciny:
1. **Stream neni vybran v OBS**: Aplikace ziskava nazev pouze kdyz je stream vybran v Broadcast Manager
2. **Autentifikace neni nastavena**: Nastav OAuth nebo API klic
3. **Kvota prekrocena**: Zkontroluj varovani v dashboardu
4. **Broadcast nema broadcast_id**: Stream musi byt spravne nastaven v OBS

Reseni:
1. Otevri OBS → Tools → Broadcast Manager
2. Vyber stream, ktery chces pouzit
3. Zkontroluj, ze stream ma nastaveny YouTube broadcast
4. Zkontroluj, ze autentifikace je nastavena a aplikace je restartovana

---

## Bezpecnost

### Ochrana credentials

**Dulezite**: Client ID a Client Secret jsou citlive informace. Chran je pred zverejnencim:

- ❌ **NEUKLADEJ** credentials do git repozitare
- ❌ **NESDILEJ** credentials verejne
- ✅ **POUZIVEJ** promenne prostredi pro ulozeni credentials
- ✅ **OMEZ** credentials v Google Cloud Console (doporuceno)

### Omezeni OAuth clienta

Pro zvyseni bezpecnosti:
1. Omez OAuth clienta na pouziti z konkretni domény/IP
2. Pravidelne rotuj credentials (vytvor novy, pouzij ho, smaz stary)
3. Odeber sebe z Test Users po overeni funkcnosti

---

## Další informace

- [YouTube Data API v3 Dokumentace](https://developers.google.com/youtube/v3)
- [Google Cloud Console](https://console.cloud.google.com/)
- [YouTube API Quotas](https://developers.google.com/youtube/v3/getting-started#quota)
- [Google OAuth 2.0 Dokumentace](https://developers.google.com/identity/protocols/oauth2)