# Buchtanen iRacer OBS Overlay - opravný výrobní brief V3

Tento dokument nahrazuje výtvarnou logiku raster balíku V2. Původní PDF zůstává vizuální referencí. V3 zpřesňuje, jak z referencí vyrobit skutečné produkční vrstvy a animace tak, aby složený overlay vypadal stejně kvalitně jako schválené ilustrace.

## 1. Co bylo ve V2 špatně

V2 neselhalo formátem PNG ani technickou validitou. Selhalo převodem návrhu do komponent.

- Reference mají vrstvené technické panely, víceúrovňové rámy, vnitřní konstrukční kresbu, mikrodetaily, asymetrii, materiálovou hloubku a lokální světlo.
- V2 většinu tohoto jazyka zredukovalo na tmavou desku, jednu obrysovou linku, jednoduchou ikonu a glow.
- Kontrolní preview nebylo tvrdým výsledkem kompozice produkčních vrstev. Vypadalo lépe než samotné vrstvy, takže vytvářelo falešný dojem hotového designu.
- Tři themes byly téměř jen přebarvení. PDF přitom ukazuje tři rozdílné výtvarné charaktery.
- Animace byly technicky přítomné, ale nebyly navržené jako součást identity jednotlivých widgetů.

## 2. Jediný zdroj pravdy

Pro další výrobu platí tyto vizuální reference z PDF:

- Theme `cyber_racing`: strana 09 PDF - "Widget Theme 1 - Cyan / Amber Tech".
- Theme `stealth_graphite`: strana 10 PDF - "Widget Theme 2 - Stealth Graphite + Cyan Pulse".
- Theme `night_attack`: strana 11 PDF - "Widget Theme 3 - Race Alert / Night Attack".
- SYSINFO: strany 14, 15 a 16 PDF, vždy odpovídající theme.
- Overall proposal na stranách 05-07 určuje atmosféru, hustotu detailu a motion jazyk. Není určen k doslovnému převzetí full-frame HUDu.

Reference se nesmí znovu "volně interpretovat" do chudšího panelu. Produkční kompozice musí zachovat:

- siluetu panelu,
- počet a rytmus hran,
- rozložení ikonické a textové zóny,
- hustotu mikrodetailu,
- hierarchii primary/secondary line,
- lokální glow a materiálovou hloubku,
- charakter konkrétního theme.

## 3. Golden master pravidlo

Každý schvalovací náhled se musí vyrenderovat výhradně z odevzdávaných produkčních vrstev, stejného manifestu a stejného compositingu, jaký použije overlay.

Zakázáno:

- vygenerovat nebo ručně dokreslit hezčí flattened preview a až potom ho přibližně rozřezat,
- přidat do preview světlo, texturu, stín nebo ornament, který nemá vlastní produkční vrstvu nebo implementované CSS pravidlo,
- schválit screenshot, který nelze znovu sestavit z dodaných souborů.

Povinné:

1. Nejdříve vzniknou produkční vrstvy.
2. Z nich sestavovací skript vytvoří widget preview.
3. Ze stejných vrstev a zkušebního HTML textu vznikne Full HD preview.
4. Preview se při každé změně generuje znovu; ručně se neupravuje.

Výsledek složení produkčních vrstev a schvalovacího preview musí být pixelově shodný mimo dynamický HTML text.

## 4. Co znamená jednotný styl a rozdílné themes

Themes nesdílejí pouze barvy. Sdílejí funkční geometrii a UX, ale mohou mít rozdílnou vnitřní kresbu.

### Musí zůstat shodné

- vnější pixelový box widgetu,
- bezpečné okraje,
- pozice icon well,
- textové sloty title/value/meta,
- anchor a směr vstupu/výstupu,
- význam cyan/amber/red stavů,
- čitelnost a priorita informací,
- názvy logických vrstev v manifestu.

### Může a má se lišit

- silueta vnitřního plátu a chamferů,
- konstrukce rámu a corner caps,
- textura a materiál,
- množství technické kresby,
- radar/scan ornament,
- divider styl,
- charakter glow,
- motion tempo, easing a glitch varianta.

V rámci jednoho theme musí battle, lap, position, session, bio a sysinfo působit jako jedna rodina. Mezi themes se rodiny smějí výtvarně lišit.

## 5. Charakter themes

### `cyber_racing`

- Nejbohatší technická kresba ze tří themes.
- Dvojitý až trojitý obrys: graphite base, steel edge, jemná cyan edge light.
- Jemný carbon/graphite materiál, grid, circuit traces a krátké diagnostické značky.
- Radar a target jsou skutečný hlavní motiv, ne jen kroužek s křížem.
- Cyan je aktivní/neutral; amber je pressure/warn. Bílá slouží jako krátký specular highlight.
- Motion: segmentovaný assembly, radar lock, scan sweep, krátké datové micro-glitche.

### `stealth_graphite`

- Luxusnější, tišší, tmavší a méně symetrický.
- Větší souvislé graphite plochy, tenké šedé kovové hrany, cyan jen na jednom až dvou aktivních úsecích.
- Wireframe auta nebo mechanický blueprint může být uvnitř panelu velmi slabě, ne jako dominantní obrázek.
- Méně ornamentů, ale každý je přesnější a jemnější.
- Motion: mask reveal, krátký cyan pulse po hraně, minimum blikání, téměř žádný chromatic glitch.

### `night_attack`

- Agresivnější vnitřní segmentace, ostřejší řezy, kratší horizontální moduly a výraznější chevron motiv.
- Základ je stále graphite/black. Permanentní červená plocha je zakázaná.
- Cyan zůstává neutral/positive. Orange/red-orange se objeví pouze v pressure, lost, incident a critical stavech.
- Motion: rychlejší shutter reveal, directional strikes, krátký pressure hit, kontrolovaný line-tear glitch.

## 6. Produkční formát

- Primární formát: transparentní PNG v přesné cílové velikosti widgetu při 1920x1080.
- Žádný požadavek na škálování. Asset se kreslí 1:1.
- WebM s alfou pouze pro organický nebo časově složitý efekt, který nedává smysl skládat z několika PNG/CSS vrstev.
- Celý widget nikdy nesmí být jedno video.
- Dynamické texty, čísla a jednotky zůstávají HTML.
- State accent má dvě části:
  - monochromatickou alpha masku pro základní přebarvení kódem,
  - samostatné pre-colored glow PNG pro `cyan`, `amber` a `red`, protože barevný falloff a bloom se plochou maskou věrně nevytvoří.
- Textura se nesmí znovu generovat pro každý widget. Každý theme má jednu schválenou materiálovou rodinu a sdílenou grain/noise charakteristiku.

## 7. Společný layer model

Každý větší widget používá následující pořadí. Ne každá vrstva musí být viditelná neustále, ale detail z preview musí mít jasného vlastníka.

| Z-index | Vrstva | Účel | Typ |
|---:|---|---|---|
| 10 | `shadow` | Lokální měkké oddělení od hry, žádný velký černý blok | PNG |
| 20 | `base_plate` | Hlavní silhouette a neprůhlednost panelu | PNG |
| 30 | `material` | Carbon/graphite, grain, vignette, brushed detail | PNG |
| 40 | `tech_diagram` | Grid, circuit traces, wireframe, micro labels bez textu | PNG |
| 50 | `frame_base` | Kovový/graphite strukturální rám | PNG |
| 60 | `frame_highlight` | Tenké specular hrany a bílé mikroodlesky | PNG |
| 70 | `state_accent_mask` | Cyan/amber/red linky barvené kódem | PNG alpha mask |
| 80 | `corner_caps` | Samostatně animovatelné rohy nebo boční bracket | PNG alpha mask |
| 90 | `icon_well` | Podklad a kruhová/hranatá klec ikony | PNG |
| 100 | `icon_rings` | Radar, tick marks, orbit, pressure segments | PNG alpha mask |
| 110 | `icon_glyph` | Target, flag, stopwatch, heart, BLE, chevrons | PNG alpha mask |
| 120 | `micro_details` | Slashes, status ticks, short dividers, ports | PNG alpha mask |
| 130 | `html_content` | Dynamický title, value, meta | HTML |
| 140 | `scan_or_glitch` | Krátký aktivní sweep/line tear | PNG/CSS/WebM |
| 150 | `local_glow` | Barevný bloom pouze kolem aktivních hran/ikony | PNG |

`base_plate`, `material`, `tech_diagram` a `frame_base` se nesmí sloučit, pokud se má theme v aktivním stavu nadechnout, odhalovat nebo přepnout do compact varianty.

## 8. Battle widget 420x140 - povinný rozpad

Battle je golden master pro celý systém. Pokud nebude odpovídat PDF, nesmí se vyrábět zbytek.

### Vrstvy

```text
battle_shadow.png
battle_base_plate.png
battle_material.png
battle_tech_diagram.png
battle_frame_base.png
battle_frame_highlight.png
battle_state_accent_mask.png
battle_corner_left.png
battle_corner_right.png
battle_icon_well.png
battle_radar_ticks.png
battle_radar_ring_inner.png
battle_radar_ring_outer.png
battle_target_icon.png
battle_pressure_icon.png
battle_micro_details.png
battle_scan_mask.png
battle_glow_cyan.png
battle_glow_amber.png
battle_glow_red.png
```

### Kompozice

- Icon well zabírá přibližně levou čtvrtinu karty, ale nesmí působit jako kruh nalepený na obdélník.
- Rám kolem icon well přechází konstrukčními linkami do textové části.
- Textová část má nejméně tři úrovně hloubky: base plate, slabý technický diagram a rám/highlight.
- Pravý konec nesmí být obyčejný kolmý nebo jednokrokový chamfer. Musí obsahovat theme-specific closing bracket nebo segmentované zakončení.
- Mikrodetail musí být viditelný při 100 % a pouze naznačený při zmenšení streamu. Nesmí soutěžit s HTML textem.

### HUNTING

- Cyan target, radar ticks, slabé sweep segmenty.
- Active loop pracuje hlavně v icon well. Celá karta se nehýbe.
- Closing stav může zkrátit interval radar blipu; nesmí zvyšovat permanentní jas celého panelu.

### HUNTED

- Stejný textový grid, ale pressure ikona a pravostranný tlakový akcent.
- Amber/orange se koncentruje na icon well, pravou hranu a krátké pressure segmenty.
- Red se zapne až pro explicitně kritický stav, ne automaticky pro každé HUNTED.

## 9. Další komponenty

### Lap / PB 380x112

- Sdílí materiál, rámový rukopis a icon well s battle kartou.
- Lap flag a stopwatch mají vlastní ring/ticks, ne jen samostatnou plochou ikonu.
- PB dostane krátký specular flash a jeden reward sweep. Žádné dlouhé blikání.
- `lap_base_plate`, `lap_material`, `lap_frame_base`, `lap_frame_highlight`, `lap_state_accent_mask`, `lap_icon_well`, `lap_icon_rings`, `lap_flag_icon`, `lap_stopwatch_icon`, `lap_micro_details`, `lap_glow_cyan`.

### Position / alert 380x84-96

- Nižší a údernější silhouette než battle, ale stejný frame DNA.
- Chevrony jsou nejméně tři samostatné segmenty pro cascade motion.
- Gained používá cyan/white reward accent. Lost používá amber/orange; red jen při kolizi/critical incidentu.
- Alert banner potřebuje samostatný `warning_hatch` nebo `shutter` pattern, který se zobrazuje jen v aktivním stavu.

### Session 520x126

- Širší banner se dvěma stupni rámu, výrazným flag well a delší accent trajectory.
- FINAL LAP je důrazný, ale stále čistý.
- FINISH smí mít nejsilnější jednorázovou animaci celého systému; po vstupu se ale ustálí do čitelného statického stavu.
- Flag cloth/ripple může být alpha WebM. Rám, text a glow zůstávají samostatně.

### Bio compact 240x64 a expanded 280x118

- Nesmí vypadat jako cizí fitness widget. Používá stejné chamfery, materiál, dividers a micro ticks jako event karty.
- Heart glyph, BLE glyph, pulse trace a connection state jsou oddělené.
- Pulse trace se kreslí z reálných hodnot/CSS/canvas, nebo se reveal-maskuje. Nemá být trvale předrenderovaný náhodný EKG loop.
- Expanded high-load může přidat amber accent bracket a silnější pulse glow. Red pouze pro explicitní alert nebo ztrátu spojení.

### SYSINFO 1920x72

- Jedna společná spodní lišta, ale jednotlivé moduly mají vlastní segment, divider a icon well.
- V2 textová řádka bez panelové struktury je nedostatečná. Referencí jsou strany 14-16 PDF.
- Každý modul potřebuje minimálně: `module_base`, `module_material`, `module_frame`, `module_accent_mask`, `module_icon_well`, `module_divider`.
- Branding zóna vlevo max. 10-13 % šířky.
- Permanentní animace je zakázaná. Povolen je jen velmi pomalý edge breathe s téměř neviditelným rozsahem nebo lokální změna při warn/critical.

## 10. Motion a glitch slovník

Animace musí mít společnou gramatiku, ale theme-specific provedení.

### Sdílené motion principy

- Transformace maximálně 8-18 px uvnitř widgetu; celý widget může při entry přijet 28-44 px.
- Glow se nikdy neanimuje z 0 na 100 % přes celý panel. Rozsvěcí se lokálně po hraně, v icon well nebo na stavu.
- Jeden dominantní motion motiv na event. Ostatní vrstvy ho jen doprovázejí.
- Active loop nesmí běžet nepřetržitě ve všech vrstvách.
- Exit je kratší a klidnější než entry, kromě explicitního glitch/disconnect stavu.

### Glitch varianty

| Název | Trvání | Vrstvy | Použití | Implementace |
|---|---:|---|---|---|
| `signal_lock` | 140-180 ms | radar rings, icon glyph | HUNTING/PB enter | 2-3 opacity steps, 1 px X jitter, krátký scan clip |
| `data_slice` | 120-160 ms | frame highlight, micro details | event enter | 2 horizontální clip pásy posunuté o 2-4 px, bez RGB duhy |
| `line_tear` | 160-220 ms | accent mask, divider | NIGHT ATTACK pressure/lost | lokální segmentový posun a okamžitý návrat |
| `pressure_hit` | 90-130 ms | right bracket, amber glow | HUNTED escalation | jeden jasový hit + 3 px komprese dovnitř |
| `link_drop` | 260-360 ms | BLE glyph, pulse trace | BLE lost | nepravidelný opacity dropout, jeden red-orange edge flash |
| `finish_burst` | 420-650 ms | flag, highlight, local glow | FINISH enter | flag sweep, dvojitý specular pass, pak settle |

Chromatic aberration se používá nejvýše 1-2 px a pouze u `night_attack`. Cyber používá cyan/white signal break. Stealth používá téměř výhradně mask reveal bez glitch efektu.

## 11. Animace podle widgetu

### HUNTING

**ENTER 360 ms**

1. `shadow` + `base_plate`: slide 36 px zleva, opacity 0 -> 1, ease-out.
2. `frame_base`: mask reveal zleva doprava v intervalu 40-260 ms.
3. `corner_left/right`: krátký opačný offset 8 px, dosednutí 180-300 ms.
4. `icon_well` + `radar_ticks`: scale 0.92 -> 1.0.
5. `radar_ring_inner/outer`: `signal_lock`.
6. HTML title/value/meta: stagger po 30-45 ms, celkem do 360 ms.
7. `glow_cyan`: lokální peak kolem 220 ms, potom settle na 25-35 %.

**ACTIVE**

- Radar blip jednou za 1.4-2.2 s.
- Inner ring se může otočit o 12-18 stupňů při nové telemetrické aktualizaci.
- Closing escalation pouze zrychlí blip a zvýrazní jeden pravý tick. Nezoomuje kartu.

**EXIT 260 ms**

- Text fade 0-120 ms.
- Accent a radar collapse 40-180 ms.
- Plate posun 22 px vlevo + opacity 0 do 260 ms.

### HUNTED

**ENTER 320 ms**

- Karta vstupuje zleva stejně jako battle rodina, ale pressure bracket přichází z pravé strany.
- Amber ring se nezvětšuje celý; rozsvítí se po segmentech.

**ACTIVE**

- `pressure_hit` při překročení prahu gapu, nejvýše jednou za 1.2 s.
- Critical state přidá krátký red-orange edge flash; základ zůstane graphite.

### LAP COMPLETE / PB

- Lap: flag arc reveal, jeden cyan sweep, zobrazení 3-4 s.
- PB: stopwatch ring dokončí 270stupňový oblouk, krátký white/cyan spark a settle. Bez confetti.
- PB duration je delší než běžný lap a přebíjí jej prioritou.

### POSITION GAINED / LOST

- Tři samostatné chevron segmenty s 45-60 ms staggerem.
- Gained jde zdola nahoru, Lost shora dolů.
- Banner se pohne maximálně 6 px v odpovídajícím směru, neodskakuje celý.

### FINAL LAP / FINISH

- FINAL LAP: dlouhý 500-650 ms accent sweep, flag reveal, potom klidný active state.
- FINISH: `finish_burst`, flag ripple maximálně 1.0-1.4 s, následně statický banner 6-10 s.

### BIO / BLE

- Heart scale podle skutečného měření přibližně 1.00 -> 1.07 -> 1.00, celkem 180-240 ms.
- Pulse trace se posouvá/reveal-maskuje podle eventu, ne jako video celé karty.
- BLE connected je pouze klidný cyan indicator. `link_drop` se spustí jednou při změně stavu.

### SYSINFO

- Normální stav: bez loop animace.
- Warn: lokální amber edge pulse 600-900 ms, nejvýše jednou za 2 s.
- Critical: krátký red edge hit a následně stabilní red hodnota; žádné blikání celé lišty.

## 12. Theme-specific motion

| Theme | Entry | Active | Glitch | Glow |
|---|---|---|---|---|
| `cyber_racing` | segment assembly + radar lock | radar blip, scan tick | `signal_lock`, `data_slice` | cyan/amber přesný lokální bloom |
| `stealth_graphite` | čistý mask reveal + edge pulse | téměř statický | pouze jemný dropout | velmi slabý a úzký |
| `night_attack` | shutter reveal + directional strike | pressure ticks | `line_tear`, `pressure_hit` | kratší, ostřejší orange/red-orange |

## 13. Manifest pro integračního agenta

Každý widget musí mít manifest, který popisuje skutečné pořadí a chování vrstev. Příklad:

```json
{
  "widget": "battle",
  "size": [420, 140],
  "text_slots": {
    "title": [148, 43, 232, 30],
    "value": [148, 74, 232, 28],
    "meta": [148, 102, 232, 20]
  },
  "layers": [
    {"id": "shadow", "file": "battle_shadow.png", "mode": "image", "z": 10},
    {"id": "base_plate", "file": "battle_base_plate.png", "mode": "image", "z": 20},
    {"id": "material", "file": "battle_material.png", "mode": "image", "z": 30},
    {"id": "tech_diagram", "file": "battle_tech_diagram.png", "mode": "image", "z": 40},
    {"id": "frame_base", "file": "battle_frame_base.png", "mode": "image", "z": 50},
    {"id": "frame_highlight", "file": "battle_frame_highlight.png", "mode": "screen", "z": 60},
    {"id": "state_accent", "file": "battle_state_accent_mask.png", "mode": "mask", "z": 70},
    {"id": "corner_left", "file": "battle_corner_left.png", "mode": "mask", "z": 80},
    {"id": "corner_right", "file": "battle_corner_right.png", "mode": "mask", "z": 81},
    {"id": "icon_well", "file": "battle_icon_well.png", "mode": "image", "z": 90},
    {"id": "radar_ticks", "file": "battle_radar_ticks.png", "mode": "mask", "z": 100},
    {"id": "radar_inner", "file": "battle_radar_ring_inner.png", "mode": "mask", "z": 101},
    {"id": "radar_outer", "file": "battle_radar_ring_outer.png", "mode": "mask", "z": 102},
    {"id": "icon", "file_by_state": {"hunting": "battle_target_icon.png", "hunted": "battle_pressure_icon.png"}, "mode": "mask", "z": 110},
    {"id": "micro_details", "file": "battle_micro_details.png", "mode": "mask", "z": 120},
    {"id": "local_glow", "file_by_color": {"cyan": "battle_glow_cyan.png", "amber": "battle_glow_amber.png", "red": "battle_glow_red.png"}, "mode": "screen", "z": 150}
  ]
}
```

Souřadnice text slotů jsou integrační kontrakt a musí se potvrdit proti skutečnému DOM. Grafik do nich nekreslí text.

## 14. Výrobní postup, který se nesmí přeskočit

### Fáze A - tři golden masters

Nejdříve se vyrábí pouze:

1. `cyber_racing` HUNTING/HUNTED 420x140,
2. `stealth_graphite` HUNTING 420x140,
3. `night_attack` HUNTED 420x140.

Ke každému se dodá:

- production layers,
- složený widget preview bez textu,
- složený widget preview s testovacím HTML textem,
- Full HD preview v reálné pozici,
- entry/active/exit video nebo frame strip,
- manifest vrstev.

Dokud tyto tři vzorky neodpovídají stranám 09-11 PDF, nevyrábí se kompletní sada.

### Fáze B - jedna kompletní rodina

Po schválení golden masters se dokončí `cyber_racing`: battle, lap/PB, position/alert, session, bio a sysinfo. Kontroluje se jednotný frame DNA, materiál a motion.

### Fáze C - další themes

Teprve potom se stejný funkční systém převypráví do `stealth_graphite` a `night_attack`. Nejde o hromadné přebarvení.

## 15. Schvalovací checklist

- [ ] Preview je sestaveno pouze z produkčních vrstev.
- [ ] Každý vizuální detail v preview má konkrétní soubor nebo implementační pravidlo.
- [ ] Battle karta při 100 % připomíná referenci z PDF siluetou, hustotou a hloubkou.
- [ ] Při zmenšení na přibližně 35-40 % zůstává title/value čitelné a dekorace nesoutěží s daty.
- [ ] Každý theme má vlastní silhouette, materiál a motion charakter.
- [ ] Widgety uvnitř theme sdílejí stejný frame DNA, icon wells, stroke váhy a mikrodetail.
- [ ] Cyan, amber a red se používají podle významu stavu.
- [ ] Night Attack nemá permanentní dominantní červenou.
- [ ] SYSINFO odpovídá modulárnímu vzhledu referenčních stran 14-16, ne pouhé textové řádce.
- [ ] Animace mají enter, active a exit a neruší driving sight.
- [ ] Žádný produkční PNG/WebM neobsahuje dynamický text ani číslo.
- [ ] Žádný flattened widget nebo Full HD screenshot není použit jako produkční asset.

## 16. Akceptační kritérium

Hotový balík se nepovažuje za správný jen proto, že má správné názvy, rozměry, alpha channel a počet souborů.

Je správný pouze tehdy, když:

1. produkční vrstvy po složení vytvoří vizuální kvalitu schválené reference,
2. themes se liší skutečným výtvarným charakterem,
3. všechny widgety v theme působí jako jeden design systém,
4. animace podporují význam eventu a nezakrývají obsah,
5. schvalovací preview je přesným výsledkem odevzdaných vrstev.

Tohle je hlavní pojistka proti opakování problému V2.
