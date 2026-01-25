# Security Best Practices - iRacing OBS Switcher

## 🔒 Přehled

Tento dokument popisuje security best practices pro projekt iRacing OBS Switcher. Projekt pracuje s citlivými daty (OBS WebSocket password, YouTube OAuth credentials, OAuth tokens).

## ✅ Aktuální stav

### Co je správně nastaveno:

1. **Secrets management:**
   - ✅ `config.ini` je v `.gitignore` (necommitne se do gitu)
   - ✅ OAuth tokeny se ukládají do `data/youtube_oauth_token.json` (lokálně)
   - ✅ `data/*.json` je v `.gitignore` (kromě `*.example.json`)
   - ✅ Log soubory jsou v `.gitignore`
   - ✅ OAuth credentials podporují environment variables jako alternativu k `config.ini`

2. **Network security:**
   - ✅ HTTP server běží pouze na `127.0.0.1` (localhost)
   - ✅ OBS WebSocket je lokální připojení
   - ✅ YouTube API calls přes HTTPS

3. **Code security:**
   - ✅ OAuth tokeny se ukládají do souboru (ne do paměti dlouhodobě)
   - ✅ Token refresh mechanismus implementován
   - ✅ Token revocation podporováno

## ⚠️ Doporučení pro zlepšení

### 1. Secrets Management

#### A. Environment Variables (doporučeno pro produkci)

**Pro OAuth credentials:**
```powershell
# Windows PowerShell
$env:GOOGLE_OAUTH_CLIENT_ID = "your_client_id_here.apps.googleusercontent.com"
$env:GOOGLE_OAUTH_CLIENT_SECRET = "GOCSPX-your_secret_here"
```

**Pro OBS WebSocket password:**
```powershell
# Můžeš přidat podporu pro environment variable v config.py
$env:OBS_WEBSOCKET_PASSWORD = "your_password_here"
```

**Výhody:**
- Secrets nejsou v souborech na disku
- Snadnější rotace secrets
- Lepší pro CI/CD a deployment

**Implementace:**
- V `config.py` přidej fallback na environment variables pro `obs_password`
- Priorita: `config.ini` > environment variables > error

#### B. File Permissions

**Ověř, že citlivé soubory mají správná oprávnění:**

```powershell
# Windows - nastav oprávnění pouze pro vlastníka
icacls "config\config.ini" /inheritance:r /grant:r "$env:USERNAME:(R)"
icacls "data\youtube_oauth_token.json" /inheritance:r /grant:r "$env:USERNAME:(R)"
```

**Linux/Mac:**
```bash
chmod 600 config/config.ini
chmod 600 data/youtube_oauth_token.json
```

### 2. Logging Security

#### A. Ověř, že se tokeny neukládají do logů

**Kontrola:**
- ✅ V kódu nejsou `logger.info()` nebo `print()` s password/token/secret
- ⚠️ Ověř, že při chybách se neukládají citlivé data

**Doporučení:**
```python
# ❌ ŠPATNĚ
logger.error(f"OAuth failed with token: {token}")

# ✅ SPRÁVNĚ
logger.error("OAuth token exchange failed")
logger.debug("OAuth token exchange failed (token not logged)")
```

#### B. Log File Permissions

```powershell
# Windows - pokud se logy ukládají do souboru
icacls "logs\*.log" /inheritance:r /grant:r "$env:USERNAME:(R,W)"
```

### 3. Dependencies Security

#### A. Pravidelné aktualizace

**Kontrola zranitelností:**
```powershell
# Instalace safety (security checker)
pip install safety

# Kontrola dependencies
safety check
```

**Automatizace:**
- Přidej do CI/CD workflow kontrolu `safety check`
- Použij `dependabot` nebo `renovate` pro automatické PR s aktualizacemi

#### B. Pinování verzí (volitelné)

**Pro produkci:**
```toml
# pyproject.toml - místo >= použij == pro kritické závislosti
dependencies = [
  "aiohttp==3.9.0",  # místo >=3.9
  "obsws-python==1.6.0",
  # ...
]
```

**Nebo použij `requirements.txt` s přesnými verzemi:**
```bash
pip freeze > requirements.txt
```

### 4. Network Security

#### A. HTTP Server Binding

**Aktuální stav:** ✅ Server běží na `127.0.0.1` (localhost)

**Doporučení:**
- ⚠️ Pokud někdy budeš potřebovat externí přístup, použij firewall rules
- ⚠️ Zvaž HTTPS pro produkci (pokud bude externí přístup)

#### B. OBS WebSocket

**Aktuální stav:** ✅ Lokální připojení (`ws://127.0.0.1:4455`)

**Doporučení:**
- ✅ Zůstaň na localhost (neexponuj OBS WebSocket na internet)
- ⚠️ Pokud potřebuješ vzdálený přístup, použij VPN nebo SSH tunnel

### 5. OAuth Security

#### A. Token Storage

**Aktuální stav:** ✅ Tokeny se ukládají do `data/youtube_oauth_token.json`

**Doporučení:**
- ✅ Soubor je v `.gitignore` (správně)
- ⚠️ Zvaž šifrování tokenů na disku (volitelné, pro vyšší security)
- ⚠️ Implementuj automatické mazání tokenů po X dnech nečinnosti (volitelné)

#### B. Token Refresh

**Aktuální stav:** ✅ Automatický refresh implementován

**Doporučení:**
- ✅ Margin 120 sekund před expirací je rozumný
- ✅ Refresh token se zachovává (správně)

#### C. CSRF Protection

**Aktuální stav:** ✅ Používá se `state` parameter v OAuth flow

**Doporučení:**
- ✅ `secrets.token_urlsafe(32)` je bezpečné (používá se v `api.py`)
- ✅ Ověř, že `state` se validuje při callback

### 6. CI/CD Security

#### A. GitHub Actions Secrets

**Aktuální stav:** ✅ Workflow nepoužívá secrets (správně, není potřeba)

**Doporučení:**
- ✅ Pokud budeš potřebovat secrets v CI/CD, použij GitHub Secrets
- ⚠️ Nikdy necommitni secrets do workflow YAML

#### B. Artifact Security

**Aktuální stav:** ✅ Build artifacts se ukládají s retention 30 dní

**Doporučení:**
- ✅ Retention je rozumný
- ⚠️ Ověř, že artifacts neobsahují `config.ini` nebo tokeny

### 7. Code Security

#### A. Input Validation

**Doporučení:**
- ✅ Používáš `pydantic` pro validaci (správně)
- ⚠️ Ověř, že všechny user inputs jsou validovány
- ⚠️ Ověř, že file paths jsou sanitizovány (prevence path traversal)

#### B. Error Handling

**Doporučení:**
- ⚠️ Ověř, že error messages neodhalují citlivé informace
- ⚠️ Používej generické error messages pro uživatele, detailní jen v debug logu

### 8. Branch Protection (volitelné, když budeš mít spolupracovníky)

**Aktuální stav:** ⚠️ Pracuješ sám na masteru

**Doporučení pro budoucnost:**
- Branch protection rules na `master`
- Require pull request reviews
- Require status checks (tests)
- Require up-to-date branches

## 📋 Security Checklist

### Před každým commitem:
- [ ] Žádné secrets v kódu
- [ ] Žádné secrets v commit message
- [ ] `config.ini` není v gitu
- [ ] Token soubory nejsou v gitu
- [ ] Log soubory nejsou v gitu

### Před release:
- [ ] `safety check` prošel
- [ ] Dependencies jsou aktualizované
- [ ] File permissions jsou správné
- [ ] Žádné hardcoded secrets
- [ ] Error messages neodhalují citlivé informace

### Pravidelně (měsíčně):
- [ ] Aktualizace dependencies (`pip list --outdated`)
- [ ] Kontrola zranitelností (`safety check`)
- [ ] Review log souborů (neobsahují tokeny?)
- [ ] Rotace OAuth credentials (pokud je potřeba)

## 🛠️ Nástroje pro Security

### 1. Safety (Python dependencies)
```powershell
pip install safety
safety check
```

### 2. Bandit (Python code security)
```powershell
pip install bandit
bandit -r src/
```

### 3. Git Secrets (prevence commitování secrets)
```powershell
# Instalace (Windows - přes WSL nebo Git Bash)
git secrets --install
git secrets --register-aws  # pokud používáš AWS
```

### 4. TruffleHog (scan historie pro secrets)
```powershell
# Instalace
pip install trufflehog

# Scan repozitáře
trufflehog git file://. --json
```

## 🚨 Incident Response

### Pokud se secret dostane do gitu:

1. **Okamžitě:**
   - Rotuj všechny exposed secrets
   - Odstraň secret z gitu (pomocí `git filter-repo`)
   - Force push (POZOR: přepíše historii)

2. **Postup:**
   ```powershell
   # Zálohuj repozitář
   git clone --mirror https://github.com/user/repo.git backup.git
   
   # Odstraň secret z historie
   git filter-repo --path config/config.ini --invert-paths --force
   
   # Force push
   git push origin --force --all
   ```

3. **Ověření:**
   - Zkontroluj, že secret není v historii
   - Ověř, že secret není v GitHub (web UI, API)

## 📚 Další zdroje

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/secrets.html)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)
- [OAuth 2.0 Security Best Practices](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)

## 🔄 Aktualizace tohoto dokumentu

Tento dokument by měl být aktualizován při:
- Změnách v secrets management
- Přidání nových dependencies
- Změnách v network security
- Security incidentech

---

**Poslední aktualizace:** 2026-01-25
