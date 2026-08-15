# Build a nasazení

Návod pro vytvoření EXE souboru a nastavení aplikace jako Windows služby.

Oficiální releasy (tag `vX.Y.Z`, GitHub Release artefakty) řídí **Release PR** — viz [RELEASE_POLICY.md](RELEASE_POLICY.md) a [VERSIONING.md](VERSIONING.md).

## Obsah

- [Vytvoření EXE souboru](#vytvoření-exe-souboru)
- [Výstup build procesu](#výstup-build-procesu)
- [Instalace a provoz](#instalace-a-provoz)
- [Zastavení služby (Stopping the service)](#zastavení-služby-stopping-the-service)
- [Automatické spuštění při startu systému](#automatické-spuštění-při-startu-systému)
- [Cesty v konfiguraci](#cesty-v-konfiguraci)
- [Ruční build (PyInstaller)](#ruční-build-pyinstaller)

---

## Vytvoření EXE souboru

Aplikace se builduje jako **silent background proces** (bez konzole) pomocí PyInstaller.

### Windows (PowerShell)

```powershell
.\build_exe.ps1 --all
# Nebo pouze core service:
.\build_exe.ps1 --core
```

### Linux/Mac (Bash)

```bash
chmod +x build_exe.sh
./build_exe.sh --all
```

**Poznámka**: Na Linux/Mac se vytvoří spustitelný soubor (ne EXE), ale proces je stejný.

---

## Výstup build procesu

Po buildu najdeš v `dist/` adresáři kompletní distribuci:

```
dist/
  ├── irswitchd.exe          # Hlavní aplikace (silent, bez konzole)
  ├── Install.ps1            # Installer (wizard + autostart + shortcuts)
  ├── Open-Dashboard.ps1     # Otevře dashboard podle config.ini
  ├── config/
  │   ├── config.example.ini  # Příklad konfigurace
  │   └── config.ini         # Startovní config (safe template) / tvoje konfigurace
  └── README.txt             # Instrukce k použití
```

**Důležité**: Celý `dist/` adresář je samostatná distribuce - můžeš ho zkopírovat kamkoliv a spustit.

---

## Instalace a provoz

### 1. Instalace (doporučeno: wizard)

Z adresáře `dist/` spusť instalátor (vytvoří/aktualizuje `config/config.ini`, nastaví autostart přes Task Scheduler a udělá zkratky):

```powershell
cd dist
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -Wizard
```

Wizard se ptá jen na nutný základ (hlavně OBS WebSocket heslo) a volitelně nabídne:
- logování do souboru
- nastavení YouTube OAuth přes **User env vars** (pokud chceš)

### Odinstalace (EXE)

Odinstalace odstraní jen:
- autostart (`Scheduled Task`)
- desktop zkratky

`config/` a `logs/` nechává (můžeš smazat ručně celý `dist/` adresář).

```powershell
cd dist
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -Uninstall
```

**Více informací**: Viz [CONFIG.md](CONFIG.md) pro detailní popis konfigurace.

### 2. Ruční konfigurace (pokud nechceš wizard)

Uprav `dist/config/config.ini` podle svých potřeb:
- Nastav OBS WebSocket heslo
- Uprav názvy scén podle OBS
- Nastav cesty k obrázkům (pokud používáš)
- Nastav jazyk (pokud chceš jiný než čeština)

### 3. Spuštění aplikace

**Z adresáře `dist/`**:
```powershell
cd dist
.\irswitchd.exe --config config\config.ini
```

Aplikace běží **silent na pozadí** (bez konzole). Jak ji bezpečně zastavit: viz [Zastavení služby](#zastavení-služby-stopping-the-service).

### 3. Logování

- **Výchozí**: Logy jdou na konzoli (stderr) - pokud spouštíš z PowerShell, uvidíš je
- **Do souboru**: Nastav v `config.ini`:
  ```ini
  [app]
  log_file = logs/irswitch.log
  log_max_bytes = 10485760  # 10 MB
  log_backup_count = 5      # Počet backup souborů
  ```
  Log soubory se automaticky rotují při dosažení maximální velikosti.

**Poznámka**: Cesty k log souborům jsou relativní k working directory (adresáři, ze kterého spouštíš aplikaci).

---

## Zastavení služby (Stopping the service)

`irswitchd` běží jako silent proces (bez konzole). Preferuj **graceful** shutdown; kill až jako poslední možnost.

### 1. Graceful: Dashboard / `POST /shutdown` (doporučeno)

Ukončí main loop čistě (dokončí běžící operace, pak exit).

- **GR Dashboard**: otevři `http://127.0.0.1:17321/gr-status` → **Shutdown Service**
- **API** (stejný efekt):

```powershell
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:17321/shutdown"
```

Detail API: [API.md – POST /shutdown](API.md#post-shutdown).

Pokud dashboard/API neodpovídá (proces hangne, port nedostupný), pokračuj níže.

### 2. Task Scheduler – End běžící instance

Když je app nainstalovaná přes `Install.ps1` (Scheduled Task **iRacing OBS Switcher**):

1. Otevři Task Scheduler (`taskschd.msc`)
2. Najdi task **iRacing OBS Switcher**
3. Pravý klik → **End** (ukončí běžící instanci)

To zastaví aktuální běh. Autostart při příštím přihlášení zůstane, dokud task neodinstaluješ.

### 3. `Install.ps1 -Uninstall` / `-UninstallTask`

Z `dist/` (ověřeno v `scripts/Install.ps1`):

| Flag | Co dělá |
|------|---------|
| `-UninstallTask` | Odstraní jen Scheduled Task **iRacing OBS Switcher** |
| `-Uninstall` | Odstraní task + desktop zkratky (+ nabídne cleanup OAuth User env vars) |

```powershell
cd dist
# Jen autostart task:
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -UninstallTask

# Kompletní odinstalace autostartu + zkratek:
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -Uninstall
```

**Důležité**: tyto flagy **neukončí** už běžící `irswitchd.exe`. Nejdřív graceful shutdown (nebo End v Task Scheduler / Task Manager), pak teprve `-Uninstall` / `-UninstallTask`, pokud chceš zrušit autostart.

`config/` a `logs/` se nemažou.

### 4. Task Manager (last resort)

1. Task Manager (`Ctrl+Shift+Esc`)
2. Najdi `irswitchd.exe` → **End task**

Použij jen když graceful shutdown ani Task Scheduler End nefungují.

### Graceful vs kill

| | Graceful (`POST /shutdown` / Dashboard) | Kill (Task Manager End / násilné ukončení) |
|--|----------------------------------------|--------------------------------------------|
| Jak | API nastaví shutdown event → main loop se ukončí | OS proces zabije okamžitě |
| Stav / I/O | Čisté dokončení běžících kroků | Možné přerušení zápisu (logy, dočasný stav) |
| Kdy | Běžný provoz | Hang, neodpovídající API, nouze |

Dev konzole (ne EXE): `Ctrl+C` je také graceful (SIGINT), pokud běžíš s viditelnou konzolí.

---

## Automatické spuštění při startu systému

### Možnost A: Windows Task Scheduler (doporučeno pro EXE)

**Doporučený postup**: použij `Install.ps1 -Wizard` – nastaví autostart automaticky (trigger: **At log on**, aby app běžela ve stejném user kontextu jako OBS).

1. Otevři Task Scheduler (`taskschd.msc`)
2. Vytvoř nový task:
   - **Trigger**: "At log on"
   - **Action**: Start a program
   - **Program**: `C:\path\to\dist\irswitchd.exe`
   - **Arguments**: `--config C:\path\to\dist\config\config.ini`
   - **Start in**: `C:\path\to\dist`
   - **Run whether user is logged on or not**: ✓ (volitelné)

**Výhody**:
- Jednoduché nastavení
- Integrace do Windows
- Možnost spuštění i bez přihlášeného uživatele

**Nevýhody**:
- Aplikace běží pod uživatelským účtem
- Pokud se uživatel odhlásí, aplikace se ukončí (pokud není nastaveno "Run whether user is logged on")

---

### Možnost B: Windows Service (NSSM)

Pokud preferuješ Windows Service, použij [NSSM](https://nssm.cc/) (Non-Sucking Service Manager).

#### Instalace NSSM

1. Stáhni NSSM z [https://nssm.cc/download](https://nssm.cc/download)
2. Rozbal do `C:\nssm\` (nebo jiného adresáře)

#### Vytvoření služby

```powershell
# Přejdi do adresáře s NSSM
cd C:\nssm\win64

# Vytvoř službu
.\nssm.exe install irswitchd
```

V GUI nastav:
- **Path**: `C:\path\to\dist\irswitchd.exe`
- **Arguments**: `--config C:\path\to\dist\config\config.ini`
- **Startup directory**: `C:\path\to\dist`
- **Startup**: Automatic

#### Správa služby

**Spuštění služby**:
```powershell
nssm start irswitchd
```

**Zastavení služby**:
```powershell
nssm stop irswitchd
```

**Restart služby**:
```powershell
nssm restart irswitchd
```

**Odinstalace služby**:
```powershell
nssm remove irswitchd confirm
```

**Zobrazení stavu služby**:
```powershell
nssm status irswitchd
```

**Výhody**:
- Aplikace běží jako systémová služba
- Spouští se automaticky při startu systému
- Běží i když není uživatel přihlášen
- Lepší integrace do Windows

**Nevýhody**:
- Vyžaduje instalaci NSSM
- O něco složitější nastavení

---

## Cesty v konfiguraci

**Důležité**: Všechny cesty v `config.ini` jsou **relativní vzhledem k working directory** (adresáři, ze kterého spouštíš aplikaci).

**Příklady**:
- Pokud spouštíš z `C:\irswitch\dist\`:
  ```ini
  log_file = logs/irswitch.log              # → C:\irswitch\dist\logs\irswitch.log
  dashboard_gr_background_image = bg.png    # → C:\irswitch\dist\bg.png
  dashboard_vr_icons_path = icons/          # → C:\irswitch\dist\icons\
  ```

- Pokud chceš absolutní cesty, použij plnou cestu:
  ```ini
  log_file = C:/irswitch/logs/irswitch.log
  dashboard_gr_background_image = C:/irswitch/bg.png
  ```

**Tip**: Pro distribuci doporučujeme používat relativní cesty - aplikace pak funguje bez úprav, i když ji přesuneš do jiného adresáře.

**Poznámka**: Pokud používáš Windows Service (NSSM), working directory je adresář nastavený v "Startup directory" v NSSM GUI.

---

## Ruční build (PyInstaller)

Pokud preferuješ ruční build nebo potřebuješ upravit build proces:

```powershell
pip install pyinstaller
pyinstaller --onefile `
    --name irswitchd `
    --noconsole `
    --collect-all irswitch `
    --distpath dist `
    --workpath build `
    --clean `
    --add-data "assets;assets" `
    --noupx `
    src\irswitch\main.py
```

**Parametry**:
- `--onefile` - vytvoří jeden EXE soubor (všechny závislosti jsou zabalené)
- `--name irswitchd` - název výstupního souboru
- `--noconsole` - vytváří silent EXE bez konzole (doporučeno pro background proces)
- `--collect-all irswitch` - zahrne všechny moduly z balíčku irswitch
- `--add-data "assets;assets"` - zahrne assets adresář do EXE (favicon, logo, atd.)
- `--distpath dist` - výstupní adresář
- `--workpath build` - pracovní adresář pro build
- `--clean` - vyčistí cache před buildem
- `--noupx` - zakáže UPX kompresi (může způsobovat problémy s antiviry a runtime extrakcí)

**Poznámka**: `--noconsole` vytváří silent EXE bez konzole (doporučeno pro background proces). Pokud chceš vidět konzoli pro debugging, odstraň tento parametr.

---

## Troubleshooting

### EXE se nespustí

**Příznaky**: Dvojklik na EXE nic nedělá nebo se objeví chyba.

**Řešení**:
1. Zkontroluj, že máš všechny potřebné DLL knihovny (Visual C++ Redistributable)
2. Spusť z PowerShell pro zobrazení chyb:
   ```powershell
   .\irswitchd.exe --config config\config.ini
   ```
3. Zkontroluj logy (pokud jsou nastaveny v config)

### Chyba "Failed to extract VC runtime"

**Příznaky**: Při spuštění EXE se zobrazí chybová zpráva "Failed to extract VC runtime" nebo podobná chyba týkající se Visual C++ Runtime.

**Příčina**: PyInstaller se snaží extrahovat Visual C++ Runtime DLL do dočasného adresáře, ale může selhat kvůli konfliktům s systémovými DLL nebo oprávněními.

**Řešení**:
1. **Instalace Visual C++ Redistributable** (doporučeno):
   - Stáhni a nainstaluj [Visual C++ Redistributable 2015-2022](https://aka.ms/vs/17/release/vc_redist.x64.exe)
   - Restartuj počítač po instalaci
   - Zkus znovu spustit EXE

2. **Spuštění jako administrátor**:
   - Klikni pravým tlačítkem na `irswitchd.exe` → "Run as administrator"
   - To může pomoci s oprávněními pro extrakci runtime

3. **Kontrola antiviru**:
   - Některé antiviry blokují extrakci dočasných souborů
   - Přidej výjimku pro `irswitchd.exe` nebo celý `dist/` adresář

4. **Použití buildu bez `--noconsole`** (pro debugging):
   - Uprav `build_exe.ps1` a odstraň `--noconsole` parametr
   - Znovu builduj a spusť - uvidíš chybové zprávy v konzoli

**Poznámka**: Build skript používá parametr `--noupx`, který může pomoci s problémy extrakce runtime. Hlavní řešení je však instalace Visual C++ Redistributable na cílovém systému. Pokud problém přetrvává i po instalaci VC Redistributable, zkuste spustit EXE jako administrátor nebo zkontrolujte antivir.

### Služba se nespustí

**Příznaky**: Služba se nespustí nebo se okamžitě ukončí.

**Řešení**:
1. Zkontroluj logy služby v NSSM GUI (tlačítko "Log on" → "Log on" tab)
2. Ověř, že cesty v NSSM jsou správné
3. Zkontroluj, že config soubor existuje a je validní
4. Zkontroluj oprávnění - služba musí mít přístup k souborům

### Aplikace běží, ale nepřipojuje se k OBS

**Příznaky**: Aplikace běží, ale v logu vidíš "Failed to connect to OBS".

**Řešení**:
1. Zkontroluj, že OBS běží
2. Ověř, že WebSocket server je povolený v OBS
3. Zkontroluj heslo v config - musí být stejné jako v OBS
4. Pokud používáš službu, zkontroluj, že má přístup k síti
