# Buchtanen iRacer — zadání overlay assetů

Jsi grafik. Z PDF přiloženého k tomuto promptu vygeneruj **grafické podklady** pro OBS Browser Source overlay (1920×1080, transparentní).

Kód overlaye už existuje. Ty **neděláš HTML, CSS, JS ani čísla**. Děláš jen vizuální vrstvy (PNG + volitelné WebM), které se nasadí do existujících widgetů.

Produkce v2 je raster: PNG masky/pláty a 3× VP9 alpha WebM.

PDF = vizuální source of truth (směr, zóny, themes, widgety, sysinfo, bio). Tento MD = technický export, pojmenování a tvrdé zákazy.

---

## Cíl

Tmavý technický motorsport HUD, ne klasický telemetry dashboard.

- cyan = primary / neutral
- amber = pressure / warning
- red = jen alert / critical, nikdy permanentní dominantní barva
- angular plates, tenké linky, radar/wireframe, chevrons, graphite/carbon
- čitelnost i ve zmenšeném playeru; glow jen lokálně
- střed obrazu (driving sight) musí zůstat prázdný

Není součástí: rychloměr, otáčkoměr, gear, palivo, pneu, velký telemetry panel, text/čísla zapečené do obrázku.

---

## Themes = 3 skiny, stejná geometrie

Vygeneruj **identickou sadu souborů** pro každé theme. Liší se jen barvy, glow síla, kontrast panelu.

1. `cyber_racing` — výchozí cyan/amber tech
2. `stealth_graphite` — míň glow, graphite, cyan jen jako tenký puls
3. `night_attack` — agresivnější, red/orange jen jako state accent

Složky:

```text
themes/cyber_racing/assets/
themes/stealth_graphite/assets/
themes/night_attack/assets/
```

V tomto repu: `src/irswitch/web/themes/<theme>/assets/`.

---

## Tvrdé zákazy

- Žádný text, písmena, čísla, jednotky, „HUNTING“, „BPM“, „P6“, časy, teploty v SVG/PNG.
- Žádné sloučení vrstev, které se mají zvlášť animovat.
- Žádný full-frame esports rámeček kolem celého 1920×1080.
- Žádné velké cyan plochy / full-screen glow.
- Žádný soubor s mezerou v názvu.
- Neexportovat jeden „celý widget screenshot“. Jen komponenty.

---

## Formáty a technika

- **PNG s alfa** (produkce v2): pláty, rámy, ikony, glow. Ikony / dividery / corners / radar / pulse / accent = bílá maska pro CSS `mask-image`. Background a frame = běžný `background-image`, ne maska.
- **WebM VP9 alpha** (volitelné): `battle_radar_loop`, `battle_scan_enter`, `finish_accent_sweep`. Ne na celý widget a ne místo 320/280 ms enter/exit.
- Master v přesných widget pixelech (battle 420×140, sysinfo 1920×72, …).
- Transparentní pozadí.
- Žádný zapečený text / čísla.

Každý asset, který se má umět zvlášť přijet / pulznout / změnit barvu / zmizet = **samostatný soubor**.

Povinné vrstvení (logické skupiny / soubory):

1. background plate
2. border / edge light
3. accent color layer
4. icon
5. decorative micro detail
6. glow (PNG, pokud je potřeba)
7. mask / reveal (pokud dává smysl)

HTML text se kreslí přes to kódem. Nech v plátu prázdné místo pro titulek + velké číslo + meta řádek.

---

## Zóny (1080p)

- Battle stack: lower-left, nad sysinfo, šířka cca 420px, stacking 2 karet (HUNTING + HUNTED).
- Event (lap / position / incident): pravá strana nad sysinfo, cca 380px.
- Major session (FINAL LAP / FINISH): nahoře na střed, mimo driving sight, cca 520px.
- Bio expanded: vpravo nahoře, cca 280px.
- SYSINFO: spodní permanentní pruh, výška **60–78 px**, branding max ~10–13 % šířky.
- Compact HR: nad sysinfo vpravo (malý).

Karty jsou úhlové pláty (clip/chamfer), ne round-rect chat bubliny.

---

## Povinný export — stejné názvy ve všech 3 themes

### Battle

- `battle_background.png` — deska karty, bez textu
- `battle_frame.png` — tenký rám / wireframe
- `battle_glow.png` — lokální glow (ne přes celou kartu agresivně)
- `battle_target_icon.png` — radar / target (HUNTING, cyan)
- `battle_pressure_icon.png` — shield / pressure (HUNTED, amber)
- `battle_corner_caps.png` — rohy, které můžou přijet samostatně
- `battle_radar_rings.png` — kroužky, fallback když není WebM
- `battle_radar_loop.webm` — 116×116, loop jen HUNTING
- `battle_scan_enter.webm` — 420×140, one-shot na battle ENTER

Rozměr karty cílit na cca 420×140 px @1080p (logický box). HUNTING a HUNTED sdílí geometrii, liší se accent + ikona.

### Lap / PB

- `lap_background.png`
- `lap_frame.png`
- `lap_flag_icon.png` — checkered flag, bez písmen (lap complete, ne finish)
- `lap_stopwatch_icon.png` — PB, bez čísel

### Position / alert

- `alert_banner.png` — úzký banner
- `position_banner.png`
- `chevron_up.png`
- `chevron_down.png`

### Session

- `session_background.png`
- `final_lap_flag.png` — **celá bílá vlajka** (plná látka, žádný checker), bez textu „FINAL LAP“. Není CSS maska — musí zůstat bílá.
- `finish_flag.png` — checkered až po úplném konci (FINISH), větší důraz než lap flag
- `finish_accent_sweep.webm` — 520×126, one-shot na FINISH ENTER

### Bio / BLE

- `bio_compact_plate.png` — malá deska pro heart + BPM (BPM nekreslit)
- `bio_expanded_plate.png`
- `heart_icon.png`
- `ble_icon.png`
- `bio_pulse_trace.png` — jemná pulse křivka, ne agresivní EKG
- `bio_accent.png` — oddělená cyan/amber/red vrstva

### SYSINFO strip

- `sysinfo_background.png` — celý pruh 1920×(60–78), branding zóna vlevo prázdná (~12 % šířky)
- `sysinfo_module_segment.png` — jeden modul (opakovatelný)
- `sysinfo_dividers.png` — svislé čáry na 230, 380, … 1730 (brand + 11×150 px)
- `cpu_icon.png`
- `gpu_icon.png`
- `ram_icon.png`
- `temp_icon.png`
- `power_icon.png`
- `fps_icon.png`

SYSINFO je statický tvarem. HTML overlay drží stejný grid (ne 13 flex sloupců). Žádný running animation artwork. State barvy řeší kód (cyan/amber/red na hodnotě).

### Motion fragments (sdílené)

- `accent_slash.png`
- `scan_line.png`
- `thin_divider.png`
- `wireframe_fragment.png` — malý ornament, ne auto přes půlku obrazu

---

## Stavy, které musí jít obarvit kódem

Nekresli 9 bitmap na každý stav. Jedna geometrie + accent vrstva.

Widgety potřebují vizuálně unést:

- HUNTING (cyan, closing)
- HUNTED (amber/red-orange, pressure)
- LAP COMPLETE / PERSONAL BEST
- POSITION GAINED / LOST
- INCIDENT / PIT
- FINAL LAP / FINISH (FINISH nejvyšší důraz, delší display)
- BIO compact vs expanded/high-load
- SYSINFO normal / warn / critical (jen lokálně u hodnoty)

Entry/active/exit animaci dělá CSS. Připrav vrstvy, které jdou fadetnout / posunout / masknout (250–450 ms).

---

## Checklist před odevzdáním

- [ ] 3 themes, stejné filenames
- [ ] žádný text v assetu
- [ ] alfa kanál všude
- [ ] battle stacking 2 karet vizuálně sedí
- [ ] sysinfo 60–78 px, čitelná čísla (místo na HTML číslo)
- [ ] glow jen lokální PNG
- [ ] driving sight uprostřed prázdný
- [ ] night_attack nemá permanentní červenou na všech modulech
- [ ] soubory pojmenované přesně jak výše (snake_case)

Výstup: ZIP se třemi `themes/*/assets/` adresáři. Krátké MD v ZIPu: seznam souborů + px velikost každého PNG a WebM.
