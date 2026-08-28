## V4 Overlay Layout / Sizing / Motion Spec (FullHD canvas)

Tento dokument je implementační kontrakt pro V4 overlay renderer (browser source) a art pack. Neřeší konkrétní sadu velikostí a rodin (to dodá grafik a následně se z toho nastaví parametry v manifestu).

### Cíle

- Overlay canvas je fixně **FullHD 1920×1080** (OBS Browser Source).
- Widgety mohou mít **různé nativní rozměry** (asset canvas), bez hardcodů v CSS/JS.
- Pozice widgetů na obrazovce jsou řízené deklarativně (anchor/offset/stack).
- Vstupní/výstupní animace widgetů (fade/swipe/swipe+fade…) jsou řízené deklarativně a jsou deterministické pro golden QA.
- Overlay je robustní: vadný/nenačtený manifest nikdy “nezabije” overlay (musí degradovat na fallback render a dál se připojit na WS).

### Non-cíle (zatím)

- Škálování overlay podle velikosti OBS browser source (kromě explicitního `display_scale`).
- “Chytré” typografické přepočty bez kontraktu safe area / pravidel overflow.
- Runtime dekódování PNG/WebM pro validaci rozměrů (to je úloha CI, ne live render).

---

## 1) Základní pojmy (musí se držet)

### 1.1 Overlay canvas (kompozice)

- **Overlay canvas**: 1920×1080 (layout souřadnice, anchor a offsety).
- Overlay samotný je “stage”, do které se skládají widgety v několika “zones” (stacky).

### 1.2 Asset canvas vs display scale (kriticky důležité)

Oddělit dva koncepty:

- **Asset canvas**: nativní rozměr widgetů (PNG/WebM vrstvy). Změna = **re-render art packu**.
- **Display scale**: CSS transform pro celé zobrazení (např. zmenšení na streamu). To nemění assety.

Kontrakt: **větší widget nelze získat CSS scale existujících assetů** bez ztráty ostrosti. Pokud se chce větší plate, musí vzniknout nový pack v odpovídající velikosti.

---

## 2) Manifest kontrakt (V4)

Manifest je jediný zdroj pravdy. CI validuje manifest proti assetům.

### 2.1 Verzování

- `manifest_schema`: verze schématu (major/minor). Je to verze *kontraktu*, ne “pack verze”.
- `version`: verze art packu (stávající, může zůstat).

### 2.2 Canvases (pojmenované)

`canvases` definuje nativní rozměry a layout metainformace. Musí existovat minimálně:

- `transient` (default widget canvas)
- `sysinfo` (spodní bar)

Příklad:

```json
{
  "manifest_schema": "2.0",
  "version": 4,
  "canvases": {
    "transient": {
      "size": [420, 140],
      "safe_box": [119, 14, 16, 10],
      "icon_box": [28, 36, 68, 68],
      "icon_mode": "full_canvas"
    },
    "sysinfo": {
      "size": [1920, 72]
    }
  }
}
```

Pravidla:

- `size`: `[w,h]` kladné integer.
- `safe_box`: `[left,top,right,bottom]` insets v px (safe area pro text).
- `icon_box`: `[x,y,w,h]` v px *nebo* lze vyjádřit přes `icon_mode = "full_canvas"`.
- `icon_mode`:
  - `full_canvas`: state ikony jsou full-canvas PNG (glyf už je na finální pozici v rámci canvasu).
  - `glyph`: state ikony jsou “sprite” (glyf) a renderer je skládá do `icon_box` s `contain/center`.

Poznámka: `icon_mode` je explicitní, aby se nezavedl hybrid export, který bude vypadat “náhodně”.

### 2.3 Zones (pozice widgetů na FullHD canvasu)

`zones` deklaruje, kde se widgety skládají na overlay (stacky).

Příklad:

```json
{
  "zones": {
    "BATTLE": {
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
    "EVENT": {
      "anchor": "bottom-right",
      "offset_from": "sysinfo",
      "offset": [48, 19],
      "direction": "up",
      "gap": 10,
      "max": 1,
      "align": "end",
      "display_scale": 1.0,
      "transition": "fade"
    }
  }
}
```

Pravidla:

- `anchor`: `top-left|top|top-right|left|center|right|bottom-left|bottom|bottom-right`.
- `offset_from`:
  - `canvas`: offset se počítá od okraje 1920×1080.
  - `sysinfo`: Y offset se počítá nad sysinfo barem (`canvases.sysinfo.size[1]`), aby se odstranila duplikovaná derivace typu “72 + 19”.
- `offset`: `[x,y]` v px (vždy kladné nebo nulové; znaménko se odvodí z `anchor`).
- `direction`: `up|down` (stack roste).
- `gap`: mezera mezi widgety v stacku (px).
- `max`: cap (počet widgetů v zóně).
- `align`: `start|center|end` (zarovnání widgetů v rámci zóny, když mají různé šířky).
- `display_scale`: volitelný scale pro celou zónu. Změna > 1.0 nezvětšuje ostrost (viz §1.2).
- `transition`: default transition preset pro widgety v této zóně (viz §2.5).

### 2.4 Family binding (routing do zón)

Každá family musí deklarovat:

- `canvas`: reference na `canvases.<id>` (např. `transient`).
- `zone`: reference na `zones.<id>`.

Příklad:

```json
{
  "themes": {
    "cyber_racing": {
      "families": {
        "battle": {
          "canvas": "transient",
          "zone": "BATTLE",
          "layer_dir": "themes-v4/cyber_racing/families/battle/layers",
          "icon_dir": "themes-v4/cyber_racing/families/battle/icons",
          "layers": [
            { "file": "base_plate.png", "mode": "image" },
            { "file": "frame_highlight.png", "mode": "screen" },
            { "file": "state_accent_mask.png", "mode": "mask" }
          ]
        }
      }
    }
  }
}
```

Kontrakt: renderer nesmí routovat “podle if (family===battle)”. Routing je přes `family.zone` nebo `presentation.zone` (když je k dispozici).

### 2.5 Transitions (animace enter/exit)

V4 musí mít deklarativní definici “widget enter/exit” přechodů. WebM motion reely (glitch/reveal) jsou separátní a nesmí být jediný mechanismus “entry”.

Příklad:

```json
{
  "transitions": {
    "fade": {
      "enter": { "opacity": [0, 1], "duration_ms": 280, "easing": "ease-out", "delay_ms": 0 },
      "exit":  { "opacity": [1, 0], "duration_ms": 240, "easing": "ease-in", "delay_ms": 0 }
    },
    "swipe": {
      "enter": { "opacity": [1, 1], "translate_x": [16, 0], "duration_ms": 280, "easing": "ease-out" },
      "exit":  { "opacity": [1, 1], "translate_x": [0, 16], "duration_ms": 240, "easing": "ease-in" }
    },
    "swipe_fade": {
      "enter": { "opacity": [0, 1], "translate_x": [16, 0], "duration_ms": 280, "easing": "ease-out" },
      "exit":  { "opacity": [1, 0], "translate_x": [0, 16], "duration_ms": 240, "easing": "ease-in" }
    }
  }
}
```

Pravidla:

- `duration_ms`, `delay_ms` jsou integer >= 0.
- `translate_x|translate_y` jsou px v prostoru zóny (před aplikací `display_scale`).
- `easing` je whitelist (`linear`, `ease`, `ease-in`, `ease-out`, `ease-in-out`, `cubic-bezier(...)`).
- `transition` se aplikuje primárně per-zone; per-family/per-state override je volitelný (ale musí být explicitní a validovaný).
- Golden gallery musí umět přepnout režim bez animací (`layout=golden`/`motion=off`), aby snapshoty byly deterministické.

### 2.6 Motion WebM (reely)

Motion reely jsou asset-canvas vázané (nativní size). Manifest musí obsahovat:

- mapu `motions` (name → metadata), minimálně `canvas` reference + fps.

Příklad:

```json
{
  "motions": {
    "enter_reveal": { "canvas": "transient", "fps": 30 },
    "result_burst": { "canvas": "transient", "fps": 30 }
  }
}
```

Kontrakt:

- Motion reely se renderují do `.v4-art` s `width/height: 100%`.
- `object-fit` nesmí být `fill` (skrývá chyby poměru stran); použít `cover` a ořez je očekávaný jen pokud je to explicitně schválené.

---

## 3) Implementační pravidla (renderer)

### 3.1 Robustnost bootu

- `initV4()` a parse JSON musí být chráněné `try/catch`.
- I při vadném manifestu se overlay musí připojit na WS (`connectOverlay()` musí vždy běžet).
- Při vadném manifestu se widgety rendrují jako `.fallback` (už existuje styling), nikoli prázdná stránka.

### 3.2 Jediný zdroj pravdy pro rozměry: CSS custom properties

- Renderer nesmí nastavovat `background-size`/`mask-size` inline per layer.
- Rozměry canvasu se aplikují 1× na widget root jako CSS custom properties:
  - `--v4-canvas-w`, `--v4-canvas-h`
- CSS používá `var(--v4-canvas-*)` pro:
  - `.v4-widget` `width/height`
  - `.v4-art .layer` `background-size` / `mask-size`
  - `.v4-art video.fx` `width/height`
  - golden stage rozměry

### 3.3 Pozice (zones) se nesmí duplikovat

- `bottom: 91px` nesmí existovat ve dvou CSS souborech. Y offset musí být odvozen z `canvases.sysinfo.size[1]` + `zones.*.offset[1]` při `offset_from="sysinfo"`.
- Zóny se musí dát přepočítat bez rebuildu widgetů (jen update CSS vars na zone containeru).

---

## 4) CI / QA (hard gates)

Kontrakt sizing+pozice+animace je “neviditelný”, takže musí být tvrdě měřený.

### 4.1 Computed-style testy (CDP)

Headless Chrome přes CDP:

- assert `getComputedStyle(widget).width/height` odpovídá `canvas.size`
- assert `background-size` / `mask-size` odpovídá `canvas.size`
- assert zone container (anchor/offset) odpovídá `zones.*`
- assert v golden režimu nejsou `<video>` elementy (motion off)

### 4.2 Pixel golden snapshots

- `/overlay?demo=1&renderer=v4&layout=golden&fixture=all&theme=<t>&motion=off` → screenshot hash.
- Fáze “mechanismus” musí být pixel-identická (hash equality) před/po.

### 4.3 Manifest + asset invariants

Pure Python testy:

- `canvases.*.size` valid
- `safe_box` / `icon_box` uvnitř canvasu
- PNG vrstvy a state ikony mají rozměr podle deklarovaného canvasu
- WebM reely mají rozměr podle deklarovaného canvasu (bez ffmpeg dependency)

---

## 5) Rollout (bez míchání vizuálních změn)

1) **Mechanismus (bez vizuální změny)**
- čtení canvas/zones/transitions z manifestu + fallbacky
- CSS vars místo literálů
- computed-style + pixel gates

2) **Geometrie (vizuální změna, vyžaduje re-approval grafika)**
- oprava icon režimu (full_canvas vs glyph)
- safe_box + text overflow pravidla

3) **Rozšíření (až pak)**
- per-zone display_scale
- per-family/per-state transition override (pokud je potřeba)

