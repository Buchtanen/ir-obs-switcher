## V4 Overlay Layout / Sizing / Motion Spec (FullHD canvas)

Implementační kontrakt pro V4 overlay renderer (OBS Browser Source) a art pack. **Sadu velikostí a rodin nedefinuje** — tu dodá grafik; tady jsou jen parametry, které se z ní zapisují do manifestu.

Kritické review tohoto textu:

- `assets/overlay/themes/docs/overlay_v4_layout_sizing_motion_spec_review.md` (měření CDP)
- `assets/overlay/themes/docs/V4_RENDERER_SIZING_SPEC_REVIEW.md` (příčina: manifest canvas už existuje, JS ho nečte)

Tato verze zapracovává shodu obou Opus reviewů (rozpory, fallbacky, routing zón, ikony, golden stage, CI gates).

### Cíle

- Overlay canvas je fixně **FullHD 1920×1080**.
- Widgety mohou mít **různé nativní rozměry** (asset canvas), bez pixelových literálů v V4 CSS/JS.
- Pozice widgetů na obrazovce jsou deklarativní (`zones`: anchor / offset / stack).
- Enter/exit animace widgetů (`fade` / `swipe` / `swipe_fade` …) jsou deklarativní a v golden režimu vypnuté.
- Vadný manifest **nesmí** zabít overlay: fallback render + WebSocket se musí otevřít.

### Non-cíle

- Globální scale overlay podle velikosti OBS Browser Source. `zoom` je zakázaný (v OBS CEF mění layout; `transform` ne).
- Runtime dekódování PNG/WebM pro validaci rozměrů (CI, ne live loop).
- Migrace V3 rendereru. `overlay.css` (`#battle-stack`, `#event-layer`, `.widget`) zůstává na 420×140.

---

## 1) Pojmy

### 1.1 Overlay canvas

- Kompoziční souřadnice: **1920×1080**.
- Stage, do které se skládají zóny (stacky) a SYSINFO bar.

### 1.2 Asset canvas vs display scale

Dva oddělené koncepty. **Záměna je zakázaná.**

| | Asset canvas | Display scale |
|---|---|---|
| Co | Nativní px PNG/WebM | CSS `transform: scale()` na **zóně** |
| Změna | Re-render art packu | Jen kompozice |
| Nad 1.0 | Ostřejší jen s novými assety | Rozmazání |

`display_scale` je **per-zone**, ne globální. `transform-origin` je kotvicí hrana zóny (z `anchor`). Anchor a offsety se počítají v overlay px **před** scale.

Věta kontraktu: **větší kartu nelze získat CSS scale existujících assetů.**

---

## 2) Manifest kontrakt

Manifest je jediný zdroj geometrie. CI ho validuje proti assetům.

Renderer čte `canvases` / `zones` / `transitions` **jen z fetchnutého manifestu**. `snapshot.v4.resolved` nese resolvované *cesty*, ne druhou kopii geometrie. Payload se doplní o `sysinfo_canvas` kvůli symetrii s `transient_canvas`, ne jako druhý kanál layoutu.

### 2.1 Verzování

- `manifest_schema`: semver-like **dvojice integerů** `[major, minor]`, ne string (`"2.10"` vs `"2.9"`). Neznámý major → fallback + log, overlay žije.
- `version`: verze art packu (stávající klíč).

### 2.2 Canvases

Povinné klíče: `transient`, `sysinfo`.

Pořadí čtení velikosti: `canvases.<id>.size` → deprecated alias (`transient_canvas` / `sysinfo_canvas`) → JS `DEFAULT_CANVAS`. Neplatná hodnota se nepropaguje.

```json
{
  "manifest_schema": [2, 0],
  "version": 4,
  "transient_canvas": [420, 140],
  "sysinfo_canvas": [1920, 72],
  "canvases": {
    "transient": {
      "size": [420, 140],
      "safe_box": [119, 14, 16, 10],
      "icon_mode": "full_canvas"
    },
    "sysinfo": {
      "size": [1920, 72],
      "icon_mode": "glyph",
      "icon_box": [0, 0, 32, 32]
    }
  }
}
```

Pravidla:

- `size`: `[w, h]`, kladné integer.
- `icon_mode` je **autoritativní**:
  - `full_canvas`: `icon_box` **nesmí** být přítomen (CI reject). State ikony mají přesně `size`. Vrstva ikony je `inset: 0`, `background-size` = canvas.
  - `glyph`: `icon_box` `[x, y, w, h]` je povinný a leží uvnitř canvasu. Ikona se skládá `contain` + `center` do boxu.
- `safe_box`: `[left, top, right, bottom]` insets pro `.v4-copy`. Bez `text_rules` je nevymahatelný — viz §2.7. Ve **fázi 1** se `safe_box` smí deklarovat, ale renderer ho **neaplikuje** (dnešní copy insety zůstanou, pixel-identita).
- SYSINFO ikony jsou glyph sprity (dnes 64×72 do 32×32 mask boxu), ne transient full-canvas.

Family `sysinfo` **nemusí** mít `zone` (není transientní karta). Má `canvas: "sysinfo"`.

### 2.3 Zones (pozice na FullHD)

Zone id: **lowercase snake_case** (`battle`, `event`). Lookup je case-insensitive kvůli uppercase defaultu v envelope.

Kontejner: `div.v4-zone[data-zone]` s `width: max-content`, vytváří se **eager** při `initV4()` (ne lazy při prvním eventu). Anchor/offset jako CSS vars na kontejneru (`--v4-zone-x`, `--v4-zone-y`), ne per-id literály v CSS.

```json
{
  "zones": {
    "battle": {
      "anchor": "bottom-left",
      "offset_from": "sysinfo",
      "offset": [36, 19],
      "direction": "up",
      "gap": 10,
      "max": 2,
      "align": "start",
      "display_scale": 1.0,
      "transition": "swipe_fade"
    },
    "event": {
      "anchor": "bottom-right",
      "offset_from": "sysinfo",
      "offset": [48, 19],
      "direction": "up",
      "gap": 10,
      "max": 6,
      "align": "end",
      "display_scale": 1.0,
      "transition": "fade"
    }
  }
}
```

`max` ve fázi 1 **kopíruje dnešní chování**, ne ideál. Dnes `FAMILY_CAPS` drží cap **per family** a 6 ne-battle rodin sdílí jeden layer → v event stacku může koexistovat až 6 karet. `event.max: 1` by byla **vizuální změna** a patří do fáze 3 (až se cap opravdu přesune na zónu).

Pravidla:

- `anchor`: `top-left | top | top-right | left | center | right | bottom-left | bottom | bottom-right`.
- `offset_from`: `canvas` (od okraje 1920×1080) nebo `sysinfo` (Y nad `canvases.sysinfo.size[1]`). `anchor: top-*` + `offset_from: sysinfo` je nevalidní.
- Když se sysinfo nerenderuje (golden layout, `sysinfo: false`), Y se pořád počítá z manifest `canvases.sysinfo.size[1]`.
- `offset`: `[x, y]` ≥ 0; znaménko odvodí `anchor`.
- `direction`: růst stacku. **Nová karta se vkládá na kotvicí hranu** (`up` + `bottom-*` + `appendChild` + `flex-direction: column` = dnešní chování: nejnovější dole, stack roste nahoru).
- `align` → `align-items` kontejneru (`start | center | end`).
- `max`: layout cap. Karta v EXIT se z toku **okamžitě** vyjme (`position: absolute` během exit), aby stack nedržel cap+1.
- Z-order: zóny kreslí **nad** SYSINFO (`z-index` v CSS, ne pořadí v DOM).
- Přetečení zóny mimo 1920×1080 při daném `max` + `gap` + výškách canvasů je **CI chyba**, ne runtime ořez.
- Golden gallery je z placementu vyjmutá: cell je parent, který dědí canvas, ale ignoruje anchor/offset/stack/`display_scale`.

### 2.4 Family binding

Transientní family deklaruje `canvas` + `zone`. Prefix cest **`themes/` je povinný** (`manifestDiskPath()` / `manifest_rel_to_web()`). Segment `families/` na disku není.

```json
{
  "themes": {
    "cyber_racing": {
      "families": {
        "battle": {
          "canvas": "transient",
          "zone": "battle",
          "layer_dir": "themes/cyber_racing/battle/layers",
          "icon_dir": "themes/cyber_racing/battle/icons",
          "layers": [
            { "file": "base_plate.png", "mode": "image" },
            { "file": "frame_highlight.png", "mode": "image" },
            { "file": "state_accent_mask.png", "mode": "mask" }
          ]
        }
      }
    }
  }
}
```

`mode` enum rendereru: `image` | `mask`. Hodnota `"screen"` **neexistuje** — blend se řeší CSS třídou, ne novým modem v MVP.

**Routing (fáze 1–2):** `family.zone` je autoritativní. `presentation.zone` se **ignoruje**. Dnes všech 8 Python adaptérů posílá `zone="EVENT"` natvrdo; zapojení envelope zóny je samostatný úkol (fáze 3) spolu s úpravou emitérů.

### 2.5 Transitions

CSS enter/exit je oddělené od WebM reelů. Parametry jdou jako CSS vars na widget (`--v4-enter-dur`, `--v4-enter-ease`, `--v4-enter-dx`, `--v4-exit-*`, …). Hodnoty z manifestu **nahrazují** dnešní defaulty `.v4-widget`, nesčítají se.

```json
{
  "transitions": {
    "fade": {
      "enter": { "opacity": [0, 1], "duration_ms": 280, "easing": "ease-out", "delay_ms": 0 },
      "exit":  { "opacity": [1, 0], "duration_ms": 280, "easing": "ease-in", "delay_ms": 0 }
    },
    "swipe": {
      "enter": { "opacity": [1, 1], "translate_x": [16, 0], "duration_ms": 280, "easing": "ease-out" },
      "exit":  { "opacity": [1, 1], "translate_x": [0, 16], "duration_ms": 280, "easing": "ease-in" }
    },
    "swipe_fade": {
      "enter": { "opacity": [0, 1], "translate_x": [16, 0], "duration_ms": 280, "easing": "ease-out" },
      "exit":  { "opacity": [1, 0], "translate_x": [0, 16], "duration_ms": 280, "easing": "ease-in" }
    }
  }
}
```

Pravidla:

- `duration_ms`, `delay_ms`: integer ≥ 0.
- `easing` whitelist: `linear | ease | ease-in | ease-out | ease-in-out`. **Bez** volného `cubic-bezier(...)` v MVP.
- Znaménko `translate_*`: „ven od kotvicí hrany zóny“; renderer zrcadlí podle `anchor`.
- `hide()` removal timeout = `exit.delay_ms + exit.duration_ms` (dnes natvrdo 320 ms). Pojistka: `transitionend` + tento timeout.
- Fáze 1: preset hodnoty = dnešní 280/280 ms, aby pixel/computed gate prošel. Změna tempo/easing = fáze 2+.
- Golden: `layout=golden` / `motion=off` → žádný CSS transition, žádný `<video>`.
- Per-family/per-state override **není** v MVP.

### 2.6 Motion WebM

Mapa jméno → metadata. Migrace list→mapa je nerozbíjející pro dnešní Python (`in` / iterace klíčů) a patří do fáze 1.

```json
{
  "motions": {
    "enter_reveal": { "canvas": "transient", "fps": 30 },
    "result_burst": { "canvas": "transient", "fps": 30 }
  }
}
```

- Reel size musí = referenced canvas (CI, EBML `PixelWidth`/`PixelHeight`).
- Render: `width/height: 100%` na `.v4-art video.fx` (box je canvas přes inherited vars).
- `object-fit: contain`. `fill` i `cover` zakázané — obojí skrývají mismatch (protažení / ořez). Při shodě size je `contain` vizuálně identický s `fill`.
- `fps` je **CI-only**; renderer ho nečte, `to_dict()` ho nepublikuje.
- Úklid `<video>`: při EXIT / `hide()` / `rebuildArt()` se elementy pauznou a odstraní. `motionUrl()` nesmí být jediná cesta k remove (dnes nikdy nevrátí falsy).

### 2.7 Text rules (fáze 2, ne fáze 1)

```json
{
  "text_rules": {
    "title":    { "max_lines": 1, "overflow": "shrink", "min_font_px": 16 },
    "subtitle": { "max_lines": 1, "overflow": "ellipsis" },
    "value":    { "max_lines": 1, "overflow": "shrink", "min_font_px": 20 },
    "meta":     { "max_lines": 1, "overflow": "ellipsis" }
  }
}
```

Bez tohoto bloku se `safe_box` ve fázi 2 nesmí považovat za hotový.

### 2.8 Pack state map precedence and icon coverage

Renderer vybírá plate template z theme pack mapy. Pořadí je:

1. explicitní `events.<event>.template`, pokud existuje;
2. `states.<state>.template`;
3. deklarovaný family fallback.

Runtime `family` slouží pro routing a lifecycle; nesmí přepsat již resolved
template. Povinný kontraktní případ je `position_attack`: runtime family je
`timing`, ale pack template je `position`.

Coverage 35 stavů se počítá výhradně z `iconPolicy.stateGlyphs`. Event-specific
override glyphy a utility knihovna (`ble`, systémové metriky, telemetry a obecné
status symboly) jsou samostatné množiny. Utility naming nemusí být mezi themes
1:1; přesná parita se vyžaduje pouze pro stavové glyphy.

---

## 3) Renderer

### 3.1 Boot

- `initV4()` + `json()` v `try/catch`. `connectOverlay()` běží u **live** overlay vždy; demo/golden se připojuje jen když není `demo=1`.
- `initV4()` je **idempotentní** (dnes demo volá 2× → dvojí fetch + dvojí sysinfo).
- Vadný manifest: `.fallback` widgety, `documentElement.dataset.v4Manifest = "ok|fallback"`, WS otevřené.
- Built-in `DEFAULT_CANVAS` v JS musí přežít totální absenci manifestu.

### 3.2 CSS custom properties (dědičnost dolů)

Vars se nastavují na **nejbližší layout kontejner** (`.v4-zone` nebo `.golden-cell`). Widget je **dědí**. Widget je nesmí definovat sám — `.golden-stage` je rodič a vars z potomka nevidí.

Povinné vars: `--v4-canvas-w`, `--v4-canvas-h`. Gallery grid: `--v4-gallery-col` = max šířka canvasu v katalogu, ne literál `420px`. `renderV4GoldenGallery()` nastaví canvas na cell **před** `showInContainer()`.

`paintLayer()` **přestane** sázet `backgroundSize` / `maskSize` / `backgroundPosition` inline u vrstev. Výjimka fáze 1 pro **ikonu**: CSS musí explicitně držet dnešní (chybný) render `background-size: var(--v4-canvas-w) var(--v4-canvas-h); background-position: 0 0` v 64×64 boxu, jinak spadne na `contain` a fáze 1 není pixel-identická. Oprava ikony = fáze 2, vizuální změna, re-approval grafika.

Video: `width/height: 100%` (box z inherited canvas vars). Žádný druhý literál 420×140.

### 3.3 V3 vs V4 CSS

- `display-v4.css`: žádné pixelové literály zone geometrie (`bottom: 91px`, `width: 420px` mimo `var(..., 420px)` fallback).
- `overlay.css` V3 selektory se **nemění**.
- SYSINFO: `1920×72` je dnes na třech místech (dva CSS + inline `paintLayer`). Fáze 1 sjednotí V4 cestu na `canvases.sysinfo`; V3 grid `230px + 11×150px` v `overlay.css` zůstává, dokud SYSINFO nedostane vlastní layout kontrakt.

---

## 4) CI / QA

Pipeline dnes: `windows-latest`, Python 3.11–3.13, **bez** Chrome/Node/Pillow. Nové závislosti jen po review.

### 4.1 Blokující gate (pure Python)

- Schema: size, enumy, `family.canvas`/`family.zone` existují, `transition` odkazuje na preset, `icon_mode` ↔ `icon_box`.
- Canvas ↔ PNG: `full_canvas` ikony == `size`; `glyph` ikony ≤ `icon_box`; vrstvy == family canvas.
- Canvas ↔ WebM: EBML `0xB0`/`0xBA`, bez ffmpeg.
- Alias parity: `canvases.transient.size == transient_canvas` (dokud alias žije). **Nepřikazovat** `== [420, 140]` jako schopnost rendereru — pack freeze je oddělený test.
- Negativní literálový test: v `display-v4.css` žádné nahé `width: 420px` / `bottom: 91px` (fallback v `var(--v4-w, 420px)` povolen).
- De-brittle **před** CSS/JS refaktorem: dnešní grep asserty (`"contain: paint"`, `"let resolvedStates"`) nahradit behaviorálními ekvivalenty, jinak se práce zablokuje.

### 4.2 Volitelný browser job (není blokující PR gate, dokud není v CI Chrome)

Samostatný `ubuntu-latest` job s pinovaným Chrome, raw CDP, bez nové pip závislosti:

- Boot: vadný manifest ⇒ WS attempt > 0, widgety `.fallback`, `dataset.v4Manifest=fallback`.
- Computed style: widget box == canvas; `background-size`/`mask-size` == canvas; golden ⇒ 0 `<video>`.
- Zóny měřit na **live** URL, ne gallery (gallery zone kontejnery schovává).

### 4.3 Pixel hash — ne CI gate

Hash gallery je **PR artefakt** ze stejného stroje před/po fázi 1. V CI se neshodne (font stack, gallery scroll 1761 vs viewport, Chrome verze). Nightly s tolerancí eventualně; nikdy `hash ==` na Windows runneru.

---

## 5) Rollout

0. **De-brittle golden grep testů** (před jakýmkoli CSS/JS).

1. **Mechanismus (nulová vizuální změna)**  
   Fallback řetězec canvasu, CSS vars na zone/cell, `paintLayer` bez defaultu, eager zóny, `family.zone` routing (ekvivalent dnešního if), `motions` list→mapa, boot try/catch + idempotentní `initV4`, Python invarianty.  
   **Hard gate:** computed-style + (lokální) pixel self-comparison.  
   Ikona zůstává ve fázi 1 vizuálně stejná (špatný výřez).  
   `event.max` zůstává ekvivalent dnešních 6 karet.

2. **Geometrie (vizuální, re-approval grafika)**  
   `icon_mode` opravdu, `safe_box` + `text_rules`, úklid videí, SYSINFO icon map (10 souborů vs 7 slotů).  
   Rozhodnutí „velikosti koexistují vs. jedna aktivní sada“ je **vstup** této fáze (dopad na `test_v4_theme_file_parity` 185 souborů a 8 MiB budget).

3. **Placement + cap na zóně**  
   Emitery posílají skutečnou `presentation.zone`; renderer ji začne číst; `event.max` se smí snížit. Docs: `API.md` dnes `snapshot.v4` skoro nedokumentuje — nová sekce, ne update.

4. **Úklid aliasů** `transient_canvas` / `sysinfo_canvas`, major bump `manifest_schema`.
