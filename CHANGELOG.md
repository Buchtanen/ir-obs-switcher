# Changelog

Všechny významné změny v projektu budou zdokumentovány v tomto souboru.

Formát je založen na [Keep a Changelog](https://keepachangelog.com/cs/1.0.0/),
a tento projekt dodržuje [Semantic Versioning](https://semver.org/lang/cs/).

## [Unreleased]

### Přidáno
- Kompletní implementace core služby
- iRacing reader s async podporou
- OBS WebSocket klient s retry logikou
- State machine s debounce, cooldown a override logikou
- REST API s endpointy: `/status`, `/override`, `/autoswitch/toggle`
- WebSocket API pro real-time updates
- Textual TUI pro monitoring a ovládání
- Kompletní test suite (43 testů)
- Dokumentace testů (`tests.md`)
- Build skripty pro EXE (`build_exe.ps1`, `build_exe.sh`)
- CI/CD workflow (GitHub Actions)
- Quick Start guide
- API dokumentace
- TUI dokumentace
- Troubleshooting sekce

### Změněno
- N/A (první verze)

### Opraveno
- N/A (první verze)

### Odstraněno
- N/A (první verze)

## [0.2.0] - 2026-01-19

### Přidáno
- **QUIT Detection**: Detekce ukončení iRacing hry pomocí sledování zamrznutí `SessionTime`
  - Konfigurovatelný práh `quit_stall_seconds` (výchozí 0.4s)
  - Automatické přepnutí na QUIT scénu při detekci
- **RESTART Hotkey**: Globální hotkey pro VR použití (knihovna `pynput`)
  - Konfigurovatelný hotkey v `[hotkeys]` sekci
  - Sticky RESTART mód - přetrvává do skutečného IDLE
  - API endpoint `/restart-mode/reset` pro manuální reset
- **Grace Period**: Inteligentní handling loading screen
  - Ignorování inspekčního režimu (GARAGE) po loading screen
  - Čekání na skutečný IDLE (lobby) před přepnutím scény
- **OBS Scene Validation**: Kontrola konfigurovaných scén při připojení OBS
- **OBS Profile Detection**: Volitelná kontrola aktivního OBS profilu
- **Windows Notifications**: MessageBox notifikace pro změny připojení
- **TUI Improvements**: Dynamické scény, barevné indikátory, in-app notifikace

### Změněno
- iRacing Reader: Přidán timeout (2s) pro SDK volání
- iRacing Reader: Periodická obnova SDK stavu pro detekci nových připojení
- State Machine: Rozšířena logika pro grace period a sticky módy
- Config: Nové sekce `[hotkeys]` a rozšířená `[iracing]` a `[scenes]`

### Opraveno
- Krátké zobrazení GARAGE scény (Back) po loading screen
- Detekce iRacing připojení, pokud hra startuje po aplikaci
- Blokování aplikace při nedostupném iRacing SDK

### Odstraněno
- **SETTINGS mód**: iRacing SDK nehlásí otevření nastavení spolehlivě

## [0.1.0] - 2024-01-18

### Přidáno
- Počáteční implementace projektu
- Základní architektura: iRacing reader, OBS client, State machine, API server, TUI
- Konfigurační systém (INI)
- Strukturované logování
- Unit testy pro všechny komponenty
- Dokumentace projektu

---

## Typy změn

- **Přidáno** - nové funkce
- **Změněno** - změny v existujících funkcích
- **Zastaralé** - funkce, které budou brzy odstraněny
- **Odstraněno** - odstraněné funkce
- **Opraveno** - opravy bugů
- **Bezpečnost** - opravy bezpečnostních problémů
