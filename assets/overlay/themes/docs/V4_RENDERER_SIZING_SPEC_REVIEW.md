# Review návrhu specky „V4 renderer sizing capabilities“

Kritické zhodnocení plánu (manifest-driven canvas + slots, odstranění hardcode 420×140,
CSS vars / inline sizing, stack layer flexibility, migrace / back-compat, acceptance kritéria).

**Rozsah:** *sada konkrétních velikostí se zde neřeší* — to je rozhodnutí grafika. Řeší se
kontrakt, mechanismus, rizika a průkaznost.

**Stav kódu při review:** commit `fd3b7cb`, V4 renderer `src/irswitch/web/overlay/js/display-v4.js`,
CSS `src/irswitch/web/overlay/css/display-v4.css`, manifest `src/irswitch/web/themes-v4/manifest.json`,
Python resolver `src/irswitch/overlay/display_v4.py`.

---

## 0. Verdikt

Směr je správný, ale specka v podobě „odstraníme hardcode 420×140 a přesuneme rozměr do manifestu“
je **neprůchodná** ze čtyř důvodů, které plán nepokrývá:

- **Problém není chybějící pole v manifestu.** `manifest.transient_canvas` (= `[420, 140]`) už
  existuje a Python resolver ho už publikuje do presentation payloadu. Chybí jeho *konzumace*
  v JS a jeho *validace*. Specka řeší symptom (konstanta v kódu), ne příčinu (žádná vazba
  manifest → render, žádná validace, žádný fallback).
- **420×140 není konstanta, ale derivovaná konstanta v pěti vrstvách** včetně V3 rendereru
  a včetně anchorů odvozených od výšky SYSINFO. Odstranění na jednom místě rozbije jiná.
- **Golden gallery neposkytuje proti sizing regresi žádnou ochranu.** Ověřeno experimentálně
  (viz §7): úmyslně rozbitý sizing prošel 27/27 testy.
- **V renderu je latentní bug v icon slotu**, který by refaktor „420×140 → `var(--canvas-w)`“
  mechanicky zabetonoval. Ověřeno experimentálně (viz §3).

Doporučení: rozdělit na **fázi „mechanismus bez vizuální změny“** (hard gate: pixel-identický
render) a **fázi „oprava geometrie“** (vyžaduje re-approval grafika). Dnešní specka to míchá.

Součástí tohoto review je i doporučený kontrakt pro:

- řízení pozic widgetů na FullHD canvasu (zónování, anchor/offset, stack capy),
- řízení vstupních/výstupních animací widgetů (fade/swipe/swipe+fade…),

viz `assets/overlay/themes/docs/overlay_v4_layout_sizing_motion_spec.md` (revize po obou Opus reviewích).
CDP review: `assets/overlay/themes/docs/overlay_v4_layout_sizing_motion_spec_review.md`.

---

## 1. Faktické korekce vůči specce

- **`overlay.html` neexistuje.** Shelly jsou `src/irswitch/web/overlay/index.html` (produkční,
  načítá `overlay.css` + `display-v4.css` + theme CSS) a `golden.html` (pouze redirect na
  `/overlay?demo=1&renderer=v4&layout=golden&...`). Specka musí jmenovat správné soubory,
  jinak bude checklist neproveditelný.
- **`transient_canvas` už v manifestu je** a `V4AssetResolver.to_dict()` ho vrací v
  `snapshot.v4.resolved.transient_canvas`. Renderer ho ignoruje: `paintLayer()` má
  `canvas = [420, 140]` jako *default parametru* a `rebuildArt()` ho nikdy nepředá.
- **SYSINFO není hotový precedent, na který lze navázat.** `sysinfoCanvas()` čte
  `manifest.sysinfo_canvas`, ale rozměr je *zároveň* zadrátovaný na třech dalších místech:
  `overlay.css` (`#sysinfo-widget { width: 1920px; height: 72px }`,
  `grid-template-columns: 230px repeat(11, 150px)`, `.sysinfo-art .layer { background-size: 1920px 72px }`)
  a `display-v4.css` (`background-size: 1920px 72px`). Kopírovat „sysinfo pattern“ znamená
  zdědit polovičatost.
- **Asymetrie v resolver payloadu:** `to_dict()` publikuje `transient_canvas`, ale **ne**
  `sysinfo_canvas`. Ověřeno na běžícím serveru:

  ```
  lang cs
  transient_canvas [420, 140]
  has sysinfo_canvas key: False
  ```

- **`presentation.zone` se dnes nepoužívá.** Envelope ho má (`EventPresentation.zone`, default
  `"EVENT"`), ale `layerRootForFamily()` routuje **výhradně podle family** (`battle` →
  `#v4-battle-stack`, vše ostatní → `#v4-event-layer`). „Slots“ tedy jako kontrakt neexistují —
  specka nemůže tvrdit, že je „jen zparametrizuje“.

---

## 2. Slabá místa a nezmíněné závislosti

### 2.1 V3 renderer sdílí stejné CSS

`index.html` načítá `overlay.css` pro **oba** renderery. V `overlay.css` žije vlastní kopie
420×140 pro V3 plates a — což je horší — komentář dokumentující geometrii icon wellu:

```
/* V3 well centre is (64, 71) on the 420x140 canvas. */
/* V3 plates are authored 420x140. Keep native size on every card so the ... */
```

Sizing refaktor, který sáhne do `overlay.css`, mění chování V3. Specka to nezmiňuje a
neurčuje, zda V3 zůstává na fixních 420×140 (doporučeno) nebo se migruje také.

### 2.2 Anchor transientů je odvozen z výšky SYSINFO

`bottom: 91px` = 72 px (SYSINFO) + 19 px (gap). Tato derivace je **duplikovaná** v
`overlay.css` i `display-v4.css`, a je zdokumentovaná jen komentářem:

```
/* Preview: hunted bottom at y=989, sysinfo 72px → 19px gap. */
```

Změna `sysinfo_canvas[1]` tedy tiše rozbije pozici transientů. Manifest-driven sizing musí
tuto vazbu vyjádřit explicitně (offset relativní k SYSINFO), jinak vznikne třída chyb, kterou
nikdo nezachytí.

### 2.3 Motion WebM jsou canvas-vázané assety bez záznamu v manifestu

Ověřeno (`ffprobe`, 3 témata × 15 reelů):

```
enter_reveal.webm    vp9, 420x140, yuv420p, 30/1, ALPHA_MODE=1
result_burst.webm    vp9, 420x140, yuv420p, 30/1
exit_trace.webm      vp9, 420x140, yuv420p, 30/1
theme_glitch.webm    vp9, 420x140, yuv420p, 30/1
compact_mask.webm    vp9, 420x140, yuv420p, 30/1
```

- CSS je fixuje: `.v4-art video.fx { width: 420px; height: 140px; object-fit: fill }`.
- `manifest.motions` je **plochý seznam jmen** — žádná dimenze, žádný fps, žádná vazba na canvas.
- Změna canvasu ⇒ re-render 45 alpha-VP9 reelů. Bez záznamu v manifestu na to nic neupozorní
  a `object-fit: fill` chybu *skryje* (protáhne obraz místo selhání).

### 2.4 Masking

`paintLayer()` sází `mask-size` inline v pixelech z canvasu; masky se plní `currentColor`.
Při nenativní velikosti se maska resampluje → jiný antialias hran než u `image` layerů ve
stejné kartě. Specka musí říct, že masky se **neškálují** (canvas = nativní rozměr assetu),
jinak vzniknou nekonzistentní hrany mezi `mask` a `image` vrstvami téhož plate.

### 2.5 Asset resolver a testy assetů

- `test_v4_layer_and_icon_files_exist` už rozměr **bere z manifestu** — tato část je připravená.
- `test_v4_manifest_version_and_canvas` ale tvrdě asertuje `manifest["transient_canvas"] == [420, 140]`.
- `test_v4_theme_file_parity` asertuje **přesně 185 souborů** a bit-identickou sadu jmen napříč
  třemi tématy. Jakékoli per-size varianty assetů to rozbijí.
- `test_v4_pack_size_budget` má strop 8 MiB při produkčních ~5,8 MiB — druhá sada velikostí
  se do stropu nevejde. Specka musí říct, jestli se velikosti *přepínají* (jedna sada aktivní)
  nebo *koexistují* (nutný nový strop a revize distribuce v `BUILD_AND_DEPLOY.md`).

### 2.6 Golden gallery je zafixovaná stringovými testy

`test_golden_gallery_clips_glow_overflow` a `test_golden_reduced_motion_paths` asertují
**literální podstringy** ve zdrojáku, mj.:

```python
assert "isolation: isolate" in css
assert "contain: paint" in css
assert "overflow: hidden" in css
assert ".golden-stage .v4-widget" in css
assert "goldenSnapshot && /^glow_/.test(layer.file)" in js
assert "prefersReducedMotion() || isGoldenSnapshot(node)" in js
assert "let resolvedStates" in js
```

Refaktor CSS na custom properties tyto testy rozbije z důvodů **nesouvisejících s chováním**,
a naopak sizing regresi nezachytí (§7). Specka musí obsahovat úkol „de-brittle existujících
golden testů“, jinak se práce zablokuje na falešných failech.

### 2.7 OBS Browser Source

`overlay.css` fixuje `html, body { width: 1920px; height: 1080px; overflow: hidden }`.
Pokud specka zavede zvětšování karet přes `transform: scale()` nebo `zoom`, je třeba počítat s tím, že:

- OBS CEF rendruje na rozměr nakonfigurovaný v Browser Source; `zoom` mění layout, `transform`
  ne — jsou to dva různé výsledky a specka musí zvolit jeden.
- `transform: scale()` na 8 kartách × 17 vrstev vytvoří nové kompozitní vrstvy → GPU paměť.
- Škálování nad 1.0 rozmaže 420×140 PNG. **Zvětšení karet nelze udělat CSS scale** — vyžaduje
  nové assety. To je nejdůležitější věta, která ve specce chybí (viz §5.3).

---

## 3. Architektonická rizika

### 3.1 Hard-fail bootu při vadném manifestu (ověřeno)

`initV4()` dělá `await Promise.all([fetch(manifestUrl), fetch(catalogUrl)])` a následně
`await manifestRes.json()`. V `bootstrap()` je volání **bez `try`/`catch`**. Vadný manifest
tedy shodí celý boot ještě před `connectOverlay()`.

Ověřeno na serveru, který vrací HTTP 200 s nevalidním JSON tělem:

```json
{
  "jsExceptions": [
    "SyntaxError: Failed to execute 'json' on 'Response': Unexpected end of JSON input\n    at initV4 (…/display-v4.js:777:52)\n    at async bootstrap (…/overlay.js:287:5)"
  ],
  "webSocketsAttempted": [],
  "pageState": { "renderer": "v4", "hasDisplay": true, "widgets": 0 }
}
```

Zdravý manifest pro kontrast: `"webSocketsAttempted": ["ws://127.0.0.1:8099/ws/overlay"]`.

**Důsledek:** WebSocket se nikdy neotevře, a protože reconnect backoff žije *uvnitř*
`connectOverlay()`, overlay zůstane trvale mrtvý — bez zotavení, bez viditelné chyby v OBS.
To je přímý rozpor s pravidlem „never crash the main loop“ aplikovaným na render vrstvu.

Přesun sizingu do manifestu **zvětšuje blast radius této chyby**. Specka musí obsahovat:

- `try`/`catch` kolem `initV4()` v `bootstrap()`, `connectOverlay()` se zavolá vždy;
- built-in default canvas v JS jako poslední fallback;
- degradaci na `.fallback` render (existuje) místo prázdné stránky.

### 3.2 Determinismus goldenů se naváže na fetch

Dnes při nedostupném manifestu zůstane `manifest = null` a `fillCopySlots()` ztratí
`manifest.states[state].sample` → texty spadnou na `"—"`. To je tichá degradace *obsahu*.
Se sizingem v manifestu bude stejný fallback měnit i **geometrii** → golden snapshot přestane
být deterministický (dva různé výsledky podle toho, zda fetch stihl). Fallback proto musí být
**konstanta v kódu, ne absence hodnoty**, a golden běh musí umět selhat hlasitě, když manifest
nedojde.

### 3.3 Latentní bug icon slotu (ověřeno) — refaktor by ho zabetonoval

Ikony **nejsou** malé glyfy, jsou to full-canvas assety 420×140 s glyfem umístěným na finální
pozici. Ověřeno výpočtem alpha bounding boxu:

```
cyber_racing/battle/icons/hunting.png : 420x140, opaque bbox (28, 36)–(96, 104), glyph 69x69
```

Střed glyfu ≈ (62, 70), což odpovídá V3 komentáři „well centre is (64, 71)“.

Renderer ale ikonu kreslí jako **64×64 box** na `left: 28px; top: 38px`, a `paintLayer(icon, iconUrl)`
inline **přepíše** CSS `background-size: contain; background-position: center` na canvas rozměr.
Ověřeno computed style v běžícím prohlížeči:

```json
{
  "icon_box": { "w": 64, "h": 64 },
  "icon_backgroundSize": "420px 140px",
  "icon_backgroundPosition": "0px 0px",
  "icon_offsetLeftTop": [28, 38],
  "icon_inline": "background-image: url(\"…/timing/icons/lap_complete.png\"); background-size: 420px 140px; background-position: 0px 0px;"
}
```

Element tedy zobrazuje výřez obrázku **(0,0)–(64,64)** — tj. odseknutý levý horní roh glyfu —
a posune ho o (28,38). Výsledek je vidět na screenshotu: neúplná šachovnicová vlaječka mimo
střed icon wellu.

**Dopad na specku:** mechanická náhrada `420×140 → var(--v4-canvas-w)` tento bug *zachová*
(jen ho zparametrizuje) a udělá ho nezjistitelným, protože „ikona se kreslí špatně“ se pak bude
tvářit jako „ikona respektuje canvas“. Fix musí být součástí specky:

- ikona je **full-inset layer** (`inset: 0`, `background-size: <canvas>`) — konzistentní
  s tím, jak jsou assety authorované; **nebo**
- manifest deklaruje `icon_box` a assety se re-authorují jako skutečné sprity.

Rozhodnutí patří grafikovi, ale specka musí explicitně říct, které z toho platí.

### 3.4 Text slots kolidují s artem — chybí safe area

`.v4-copy` je `left: 119px; right: 16px; top: 0; bottom: 0` s `grid-template-rows: auto auto 1fr auto`
a **bez** `overflow`, `text-overflow`, `white-space` i `max-lines`. Ověřeno:

- `copy.scrollHeight = 141` proti `140` výšce karty už v **angličtině** → 1 px přetečení,
  `overflow-y: visible`;
- `title` sedí na `top: 0`, takže překrývá horní rám plate; `meta` je odseknutá dole
  (viditelné na 3× zoomu);
- `BATTLE FOR POSITION` (EN) i `KOLO DOKONČENO` / `ZTRÁTA POZICE` (CS) kříží pravý chamfer rámu.

Čeština sama o sobě zalomení nezpůsobí (nejdelší token `ZTRÁTA SENZORU TEPU`, 19 znaků, se do
285 px vejde — měřeno `lines: 1` u všech 33 fixtures), ale rezerva je nulová a **safe area
neexistuje jako pojem**. Škálovat rozbitý layout nemá smysl; `safe_box` musí být v manifestu
součástí definice canvasu.

Vedlejší zjištění ze stejného měření: subtitle/meta zůstávají v češtině anglické
(`CLEAN LAP`, `MOVE POSSIBLE`, `STAY FOCUSED`), protože fallbacky jsou anglické literály přímo
v `fill*Copy()`. Není to sizing, ale délka textu je vstup do sizingu, takže to do kontraktu slotů patří.

### 3.5 Render performance

- **17 elementů na kartu** (16 layer divů u `battle` + icon), každý s vlastním full-canvas
  `background-image`. `FAMILY_CAPS` = battle 2 + timing/position/exception/pit/bio/session 1
  ⇒ až **8 karet ≈ 136 full-canvas paintů**. Fill-rate roste lineárně s plochou canvasu.
- **`<video>` se akumulují.** `ensureFxVideo()` odstraňuje element jen když je URL falsy.
  Přes fáze ENTER (2 reely) → ACTIVE (1) → RESULT (2) → EXIT (1) tak na jedné kartě může
  zůstat až 6 alpha-VP9 videí; při 8 kartách řádově desítky. Alpha VP9 dekóduje dvě vrstvy.
- **`rebuildArt()` dělá `art.replaceChildren()`**, což při změně state zahodí i fx videa;
  `syncWidgetMotion()` je pak znovu vytvoří a znovu nastaví `src` → re-fetch a re-decode.
- **Důsledek pro specku:** změna canvasu **nesmí** procházet přes `rebuildArt()`. Musí to být
  zápis jedné CSS custom property, jinak každá změna velikosti = rebuild 17 elementů a
  restart všech motion reelů.

### 3.6 Menší stabilitní nálezy (nejsou sizing, ale sizing je zhorší)

- `lastSequence` (Map correlationId → sequence) se čistí jen v `DisplayV4.clear()`. Za dlouhou
  session roste bez omezení.
- `enforceFamilyCap()` volá `hide()`, které node odstraní až po 320 ms timeoutu. Po dobu exit
  animace je ve stacku **cap+1** karet. U vyšších karet to přeteče výšku stacku — přímý dopad
  na „stack layer flexibility“ z plánu. Cap musí být vynucen na *layoutu*, ne jen na počtu.

---

## 4. Co chybí v kontraktu manifestu

| Oblast | Stav dnes | Chybí |
|---|---|---|
| Verzování schématu | `"version": 4` = verze **art packu** | Verze **schématu** manifestu + pravidlo major/minor |
| Validace | `load_v4_manifest()` kontroluje jen „je to dict“; JS nevaliduje nic | Rozměry > 0 a integer, canvas ↔ PNG rozměr, `mode` enum, existence layer souborů, `states[*].family` existuje v tématu |
| Fallbacks | Implicitní `undefined` → tichá degradace | Deklarovaný built-in default + hlasité hlášení |
| Per-state overrides | `states[*]` má `family`/`icon`/`tone`/`lifecycle`/`sample` — žádnou geometrii | Možnost per-state text boxu / canvasu |
| Zone / layout | Neexistuje; routing je `if (family === "battle")` v JS | `zones` sekce (anchor, offset, direction, gap, cap) |
| Anchor / alignment | Implicitní přes `bottom: 91px` ve dvou CSS souborech | Explicitní anchor + offset relativní k SYSINFO |
| Text overflow | Neexistuje | Per-slot `max_lines`, `overflow`, `min_font_px`, safe box |
| Caps | `FAMILY_CAPS` konstanta v JS | Do manifestu (nebo do configu), aby šly ladit bez buildu |
| Motion | Plochý seznam jmen | Canvas + fps u reelu |
| SYSINFO slots | `SYSINFO_ICON_SLOTS` v JS má **7** položek, na disku je **10** ikon (`ble`, `frametime`, `vram` nemapované; `vram` používá `ram_icon`) | Slot mapping do manifestu |
| Canvas ↔ display scale | Nerozlišeno | Dvě oddělená pole (viz §5.3) |

---

## 5. Konkrétní návrhy změn specky

### 5.1 Naming

Manifest je konzistentně **snake_case** (`transient_canvas`, `layer_dir`, `icon_dir`,
`functional_component`, `sysinfo_canvas`); wire/envelope je **camelCase** (`minHoldMs`,
`headlineToken`, `preferredState`). Specka musí toto rozdělení zachovat — tj. **nová manifest
pole snake_case**, nezavádět camelCase kvůli JS. Jinak vznikne třetí konvence.

### 5.2 Navrhovaná struktura

```jsonc
{
  "manifest_schema": "2.0",          // NOVÉ: verze schématu (ne packu)
  "version": 4,                      // ponechat: verze art packu

  "canvases": {                      // NOVÉ: pojmenované canvasy
    "transient": {
      "size": [420, 140],
      "safe_box": [119, 14, 16, 10], // left, top, right, bottom — text nesmí ven
      "icon_box": [28, 36, 68, 68]   // x, y, w, h; nebo "full" = ikona je full-canvas layer
    },
    "sysinfo": {
      "size": [1920, 72],
      "modules": { "brand_w": 230, "module_w": 150, "count": 11 }
    }
  },

  "transient_canvas": [420, 140],    // DEPRECATED alias, čte se když "canvases" chybí
  "sysinfo_canvas": [1920, 72],      // DEPRECATED alias

  "zones": {                         // NOVÉ: nahrazuje layerRootForFamily() + FAMILY_CAPS
    "BATTLE": { "anchor": "bottom-left",  "offset": [36, 19], "offset_from": "sysinfo",
                "direction": "up", "gap": 10, "max": 2 },
    "EVENT":  { "anchor": "bottom-right", "offset": [48, 19], "offset_from": "sysinfo",
                "direction": "up", "gap": 10, "max": 1 }
  },

  "text_rules": {                    // NOVÉ
    "title":    { "max_lines": 1, "overflow": "shrink",   "min_font_px": 16 },
    "subtitle": { "max_lines": 1, "overflow": "ellipsis" },
    "value":    { "max_lines": 1, "overflow": "shrink",   "min_font_px": 20 },
    "meta":     { "max_lines": 1, "overflow": "ellipsis" }
  },

  "themes": {
    "cyber_racing": {
      "families": {
        "battle": {
          "canvas": "transient",     // NOVÉ: reference do "canvases"
          "zone": "BATTLE",          // NOVÉ: nahrazuje hardcoded routing
          "layer_dir": "…", "icon_dir": "…", "layers": [ … ], "states": [ … ]
        }
      }
    }
  },

  "motions": {                       // list → mapa, přidává canvas + fps
    "enter_reveal": { "canvas": "transient", "fps": 30 }
  }
}
```

`offset_from: "sysinfo"` odstraňuje derivovanou konstantu `91 = 72 + 19` z §2.2 — renderer si
druhou složku offsetu spočítá z `canvases.sysinfo.size[1]`.

### 5.3 Nejdůležitější doplnění: canvas ≠ display scale

Specka musí zavést **dva oddělené koncepty** a explicitně zakázat jejich záměnu:

- **`canvases.<id>.size`** — nativní rozměr assetů. Musí se rovnat rozměru PNG i WebM.
  Změna ⇒ **re-render celého art packu** (45 reelů + 185 souborů × 3 témata).
- **`render.scale`** (globální) nebo **`zones.<id>.scale`** (per-zone) — pouze CSS transform
  při kompozici. Žádné nové assety, ale nad 1.0 ztráta ostrosti.

Věta, která ve specce chybí a musí v ní být:
**„Větší karty nelze získat CSS scale existujících 420×140 assetů; vyžadují nový art pack.“**
Bez ní se `scale` použije jako zkratka a výsledkem bude rozmazaný overlay, který projde všemi
testy.

### 5.4 Mechanismus: CSS custom properties, ne inline styly

Dnes je rozměr nastaven **dvakrát**: v CSS (`.v4-art .layer { background-size: 420px 140px }`)
a inline z `paintLayer()` (`el.style.backgroundSize`). Inline vyhrává, takže CSS pravidlo je
mrtvý kód, který jen mate.

Doporučení:

- `paintLayer()` **přestane** sázet `backgroundSize` / `backgroundPosition` / `maskSize` inline;
  nastavuje pouze `background-image` / `mask-image`.
- JS zapíše canvas jedním zápisem na root widgetu:
  `node.style.setProperty("--v4-canvas-w", `${w}px`)` (a `-h`).
- CSS použije `var()` všude: `background-size: var(--v4-canvas-w) var(--v4-canvas-h)`,
  `mask-size: …`, `.v4-widget { width: var(--v4-canvas-w); height: var(--v4-canvas-h) }`,
  `video.fx { width: …; height: … }`, `.golden-stage { … }`.

Přínosy: (a) proměnná na `.v4-widget` (nikoli `:root`) umožní **různé canvasy pro různé
zones/families současně** — to je přesně ta „stack layer flexibility“, kterou plán chce;
(b) změna velikosti je jeden zápis, ne rebuild 17 elementů (§3.5); (c) je to testovatelné
přes `getComputedStyle` (§7).

### 5.5 Defaulty

- Built-in default v JS: `const DEFAULT_CANVAS = { transient: [420, 140], sysinfo: [1920, 72] }`
  — musí přežít úplnou absenci manifestu.
- Pořadí čtení: `canvases.<id>.size` → deprecated alias → `DEFAULT_CANVAS`.
- Neplatná hodnota (0, negativní, ne-integer, ne-pár) se **nesmí** propagovat; loguje se a
  padá na default.

---

## 6. Migrace / back-compat

Návrh fázování, které chybí v plánu:

- **Fáze 1 — mechanismus, nulová vizuální změna.** Zavést `canvases` + CSS vars + validaci +
  fallback; defaulty = dnešní hodnoty. **Hard gate: render je pixel-identický** (dokazatelné
  hashem screenshotu golden gallery před/po). Sem patří i de-brittle existujících golden testů (§2.6).
- **Fáze 2 — oprava geometrie.** Icon slot (§3.3), safe box a text rules (§3.4). Tohle
  **vizuálně mění** výstup ⇒ vyžaduje re-approval grafika a nesmí se schovat do „sizing“ PR.
- **Fáze 3 — zones a caps do manifestu.** Odstranit `layerRootForFamily()` a `FAMILY_CAPS` z JS;
  začít respektovat `presentation.zone` (§1). Vynutit cap na layoutu, ne jen počtem (§3.6).
- **Fáze 4 — úklid.** Odstranit deprecated aliasy `transient_canvas` / `sysinfo_canvas`,
  major bump `manifest_schema`.

Back-compat pravidla:

- Renderer musí po celé přechodné období číst **starý i nový** manifest.
- `sysinfo_canvas` doplnit do `V4AssetResolver.to_dict()` (§1) — jinak zůstane asymetrie.
- **Šťastná náhoda, kterou lze využít:** převod `motions` z listu na mapu je pro dnešní Python
  kód nerozbíjející. `resolve_motion()` používá `if motion not in motions` (u dictu testuje
  klíče), `to_dict()` iteruje `for motion in …` (u dictu iteruje klíče),
  `test_v4_motion_reels_per_theme` staví `f"{name}.webm" for name in manifest["motions"]` a
  `len(manifest["motions"]) == 15` platí pro obojí. Migrace `motions` je tedy levná — stojí za
  to ji udělat hned ve fázi 1.

---

## 7. Testy / QA — a proč to dnešní nestačí

### 7.1 Důkaz, že golden gallery sizing regresi nezachytí

Dnešní „golden“ testy jsou **grep nad zdrojovým textem** (`display_v4_js()`, `display_v4_css()`
+ `assert "…" in js`) plus kontrola rozměrů z **PNG hlaviček**. Žádný pixel snapshot,
žádný computed style, žádný browser (v `pyproject.toml` není playwright ani Pillow).

Experiment: do CSS jsem vložil `width: 520px` / `height: 190px` a v JS
`canvas = [520, 190]`, tj. sizing rozporný s assety:

```
=== injected sizing regression ===
 src/irswitch/web/overlay/css/display-v4.css | 22 +++++++++++-----------
 src/irswitch/web/overlay/js/display-v4.js   |  2 +-
=== run V4 golden + asset tests ===
...........................                                              [100%]
27 passed in 0.28s
```

**27/27 zelených** při vizuálně rozbitém renderu (odseknuté rámy, přesahující cely galerie).
Změna byla následně revertována; baseline je zpět zelený.

Závěr: acceptance kritérium „golden gallery projde“ je pro tuto specku **bezcenné**. Specka
musí přinést nový typ důkazu.

### 7.2 Navrhované testy

- **(a) Computed-style testy (nejvyšší přínos / cena).** Headless Chrome přes CDP
  (`Runtime.evaluate`), bez nové runtime dependency. Asserty:
  `getComputedStyle(layer).backgroundSize` == canvas z manifestu; box `.v4-widget` == canvas;
  icon box == `icon_box`; `mask-size` == canvas. Přesně tohle chytí regresi z §7.1.
- **(b) Pixel golden snapshots.** Screenshot `/overlay?...layout=golden&fixture=all&motion=off`
  → hash, per téma. Jediný test, který ochrání *vzhled*, a jediný způsob, jak dokázat
  „fáze 1 je pixel-identická“. Navázat na už otevřené rozhodnutí v
  `EVENT_ENGINE_V4_PARALLEL_PLAN.md` („QA tool: either approve dev-only Pillow extra, or
  rewrite geometry/alpha checks on the existing zlib PNG reader“) — pro hash stačí `hashlib`,
  Pillow není potřeba.
- **(c) Validace manifestu — pure Python, bez browseru.** Unit testy nad nevalidními manifesty:
  canvas `0` / chybí / string místo intu / nepár; `mode` mimo enum; layer soubor neexistuje;
  `states[*].family` chybí v tématu. Nejlevnější a nejrychlejší návratnost.
- **(d) Invariant canvas ↔ assety.** Rozšířit existující `test_v4_layer_and_icon_files_exist`
  na **motion WebM** (rozměr lze číst z EBML bez ffmpeg — `PixelWidth` `0xB0`, `PixelHeight` `0xBA`)
  a na celou mapu `canvases`. Tím se zabrání „canvas změněn, reely ne“.
- **(e) Boot resilience.** Malformovaný manifest ⇒ overlay **musí** otevřít WebSocket a
  vyrenderovat `.fallback`. Dnes selže (§3.1). Test lze postavit na CDP probe, který jsem
  použil — asserce `webSocketsAttempted.length > 0`.
- **(f) Text overflow / safe box.** Pro každý fixture × jazyk (`en`, `cs`): `title.scrollWidth
  <= clientWidth`, `copy.scrollHeight <= canvas_h`, a že žádný text slot nepřekročí `safe_box`.
  Dnes by tento test **failoval** (`scrollHeight = 141 > 140`) — což je správně, je to reálná chyba.
- **(g) De-brittle.** Nahradit stringové asserty z §2.6 computed-style ekvivalenty. Bez toho
  bude každý CSS refaktor blokovaný falešnými faily.
- **Reduced motion.** Zachovat `motion=off` v golden URL (už je) a přidat asserci, že se
  nevytvoří žádný `<video>` element.

### 7.3 Jak to dokazovat v PR

- Fáze 1: **hash rovnost** screenshotů gallery před/po, per téma — jedno číslo, nula diskuse.
- Fáze 2+: před/po screenshoty + explicitní approval grafika v PR.
- Vždy: výstup computed-style testu (canvas z manifestu vs. skutečný render) jako log artifact.
- Pro každou behaviorální změnu bez testu: `TDD-exception` blok podle
  `.cursor/rules/03-tdd-test-drive-policy.mdc`.

---

## 8. Procesní mezery ve specce

- **Není určen zdroj pravdy pro geometrii.** Grafik (assety) vs. manifest vs. CSS. Doporučení:
  **manifest je zdroj pravdy a CI ho validuje proti assetům** (§7.2d). Bez tohoto rozhodnutí
  se hardcode vrátí jinou cestou.
- **Chybí acceptance kritérium „nulová vizuální změna“** pro mechanickou fázi. Bez něj nelze
  refaktor odreviewovat.
- **Chybí dopad na distribuci.** Změna art packu se dotkne `test_v4_pack_size_budget` a
  `BUILD_AND_DEPLOY.md` (§2.5).
- **Chybí SYSINFO slot mapping** (10 ikon na disku vs. 7 v `SYSINFO_ICON_SLOTS`) — souvisí,
  protože SYSINFO je druhý canvas ve hře.
- **Docs impact.** Sizing kontrakt se dotkne `API.md` (payload `snapshot.v4.resolved`),
  `src/irswitch/web/overlay/GOLDEN_V4.md` (pokud se změní golden URL) a `CONFIG.md`
  (pokud vznikne konfigurovatelný `render.scale`). Plán to nezmiňuje.

---

## 9. Shrnutí prioritizovaně

1. **Opravit boot resilience** (§3.1) — dnes to je hard-fail bez zotavení; se sizingem
   v manifestu je to blokující riziko.
2. **Zavést pixel + computed-style testy** (§7.2 a, b) — bez nich je celá specka nemeřitelná.
3. **Rozdělit canvas vs. display scale** (§5.3) — jinak vznikne rozmazaný overlay.
4. **Opravit icon slot a zavést safe box** (§3.3, §3.4) — jinak zparametrizujeme rozbitou geometrii.
5. **Doplnit `manifest_schema` + validaci + fallbacky** (§4, §5.5).
6. **Zones/caps do manifestu a začít respektovat `presentation.zone`** (§1, §5.2).
7. **De-brittle existující golden testy** (§2.6) — jinak práci zablokují falešné faily.
8. **Vyčistit derivované konstanty** (`bottom: 91px`, V3 kopie 420×140) (§2.1, §2.2).
