# Build a nasazení

Návod pro vytvoření EXE souboru a nastavení aplikace jako Windows služby.

## Obsah

- [Vytvoření EXE souboru](#vytvoření-exe-souboru)
- [Výstup build procesu](#výstup-build-procesu)
- [Instalace a provoz](#instalace-a-provoz)
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
  ├── config/
  │   ├── config.example.ini  # Příklad konfigurace
  │   └── config.ini         # Tvá konfigurace (uprav si)
  └── README.txt             # Instrukce k použití
```

**Důležité**: Celý `dist/` adresář je samostatná distribuce - můžeš ho zkopírovat kamkoliv a spustit.

---

## Instalace a provoz

### 1. Příprava konfigurace

1. Zkopíruj `dist/config/config.example.ini` na `dist/config/config.ini`
2. Uprav `config.ini` podle svých potřeb:
   - Nastav OBS WebSocket heslo
   - Uprav názvy scén podle OBS
   - Nastav cesty k obrázkům (pokud používáš)
   - Nastav jazyk (pokud chceš jiný než čeština)

**Více informací**: Viz [CONFIG.md](CONFIG.md) pro detailní popis konfigurace.

### 2. Spuštění aplikace

**Z adresáře `dist/`**:
```powershell
cd dist
.\irswitchd.exe --config config\config.ini
```

Aplikace běží **silent na pozadí** (bez konzole). Pro zastavení:
- Použij GR Dashboard (`http://127.0.0.1:17321/gr-status`) a klikni "Shutdown Service"
- Nebo použij Task Manager a ukonči proces `irswitchd.exe`

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

## Automatické spuštění při startu systému

### Možnost A: Windows Task Scheduler (doporučeno pro EXE)

1. Otevři Task Scheduler (`taskschd.msc`)
2. Vytvoř nový task:
   - **Trigger**: "At startup"
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
    src\irswitch\main.py
```

**Parametry**:
- `--onefile` - vytvoří jeden EXE soubor (všechny závislosti jsou zabalené)
- `--name irswitchd` - název výstupního souboru
- `--noconsole` - vytváří silent EXE bez konzole (doporučeno pro background proces)
- `--collect-all irswitch` - zahrne všechny moduly z balíčku irswitch
- `--distpath dist` - výstupní adresář
- `--workpath build` - pracovní adresář pro build
- `--clean` - vyčistí cache před buildem

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
