# Review specky `overlay_v4_layout_sizing_motion_spec.md`

Kritický review implementačního kontraktu (FullHD canvas, canvases vs. display scale, zones/placement,
transitions, motion WebM, hard gates) a jeho návaznosti na `V4_RENDERER_SIZING_SPEC_REVIEW.md`.

**Rozsah:** *sada velikostí a rodin se neřeší* (grafik). Řeší se rozpory v kontraktu,
implementovatelnost v dnešním kódu a to, které gates jsou v tomhle repu reálně levné a spolehlivé.

**Stav kódu při review:** commit `686470c`; `src/irswitch/web/overlay/js/display-v4.js`,
`js/overlay.js`, `css/display-v4.css`, `css/overlay.css`, `src/irswitch/overlay/display_v4.py`,
`src/irswitch/web/themes-v4/manifest.json`.

Měření níže jsou z headless Chrome (CDP) nad reálným aiohttp serverem, ne z čtení kódu.

---

## 0. Verdikt

Specka je proti původnímu plánu velký posun (canvas ≠ display scale, zones, transitions, robustnost
bootu). Jako *implementační kontrakt* ale zatím neprojde ze čtyř důvodů:

1. **Vnitřní rozpory.** §2.6 (`video: 100%`) proti §3.2 (`video: var(--v4-canvas-*)`);
   §1.2 (`display_scale` = globální) proti §2.3 (`display_scale` = per-zone);
   §5 fáze 2 mluví o „text overflow pravidlech“, která §2 vůbec nedefinuje.
2. **Příklady neodpovídají realitě.** `layer_dir`, `mode: "screen"`, `icon_box` + `icon_mode`
   současně, `families/` segment v cestě — validace podle specky by dnešní manifest zamítla,
   renderer by dostal 404.
3. **Do „fáze mechanismus bez vizuální změny“ propašuje vizuální změnu.** `zones.EVENT.max = 1`
   proti dnešnímu stavu, kde v EVENT zóně **měřeně koexistuje 6 widgetů**.
4. **Hard gates jsou napsané pro CI, které tu neexistuje.** Pipeline je `windows-latest`,
   Python 3.11/3.12/3.13, **žádný browser, žádný Node, žádný Pillow**, a `.cursorrules` zakazuje
   nové dependency bez review. Navíc: golden gallery **scrolluje** (1761 px proti 993 px viewportu),
   takže „screenshot → hash“ pokrývá 20 z 33 fixtures, a font ze stacku
   (`Nimbus Sans Narrow` / `Arial Narrow`) není na runnerech dostupný.

Doporučení: přepsat §2 podle A1–A12 (většina je oprava textu, ne návrhu), §4 zredukovat na
Python invarianty + jeden CDP soubor a pixel hash degradovat z gate na PR artefakt.

---

## 1. Naměřená fakta (podklad pro připomínky)

Golden gallery `/overlay?demo=1&renderer=v4&layout=golden&fixture=all&theme=cyber_racing&motion=off`:

```json
{
  "cells": 33, "widgets": 33, "videos": 0,
  "galleryScrollHeight": 1761, "galleryClientHeight": 993, "viewport": [1920, 993],
  "widgetBox": ["420px", "140px"], "layerBackgroundSize": "420px 140px",
  "iconBox": ["64px", "64px", "28px", "38px"],
  "iconBackgroundSize": "420px 140px", "iconBackgroundPosition": "0px 0px",
  "copyScrollHeight": 141, "copyClientHeight": 140,
  "zoneContainersDisplay": [null, null]
}
```

Live layout `/overlay?demo=1&renderer=v4&fixture=battle_stack` + injektované event fixtures:

```json
{
  "battle": { "left": "36px", "bottom": "91px", "width": "420px", "gap": "10px", "children": 2 },
  "event": null,
  "sysinfoHeight": "72px",
  "widgetTransition": "opacity 0.28s, transform 0.28s",
  "eventLayerChildren": 6, "eventLayerScrollHeight": 891,
  "zonesInEnvelope": "EVENT"
}
```

Boot s vadným manifestem (HTTP 200, nevalidní JSON, cache vypnutá):

```json
{
  "healthy_manifest": { "wsAttempted": ["ws://…/ws/overlay"], "sysinfoClass": "has-art v4-sysinfo", "sysinfoLayers": 13 },
  "broken_manifest":  { "wsAttempted": [], "errors": ["unhandled: SyntaxError: Failed to execute 'json' on 'Response'…"],
                        "sysinfoClass": "has-art", "sysinfoLayers": 2 }
}
```

Fonty v kontejneru: `fc-match "Nimbus Sans Narrow"` → `Noto Sans`, `fc-match "Arial Narrow"` → `Noto Sans`.
Ani jeden font ze stacku v `overlay.css` není k dispozici.

---

## 2. Připomínky po sekcích + konkrétní edity

### §1.1 Overlay canvas

- **Chybí kontrakt na OBS.** `overlay.css` fixuje `html, body { width: 1920px; height: 1080px }`,
  žádné škálování. Specka říká „canvas je FullHD“, ale neříká, že **Browser Source musí být
  nakonfigurovaný na 1920×1080**, jinak se overlay ořízne / obklopí prázdnem. To je user-facing
  a patří do `README.md` (per `04-docs-policy.mdc`).
- **Chybí z-order.** Zone kontejnery vznikají runtime (`ensureLayer()` → `document.body.appendChild`)
  **až při prvním widgetu** (měřeno: `#v4-event-layer` je `null`, dokud nepřijde event). Skládání
  nad SYSINFO tedy dnes drží jen DOM order. Doplnit: „zone kontejnery se vytvářejí eagerly při
  initu, mají deklarovaný `z-index` nad `#sysinfo-widget`“. Bez toho nelze zóny ani testovat
  computed-style, protože element neexistuje.

**Edit:** přidat odstavec „Stage kontrakt“: fixní 1920×1080, požadovaná konfigurace Browser Source,
eager vytvoření zón, z-index řád (sysinfo < zones < golden gallery).

### §1.2 Asset canvas vs. display scale

- **Rozpor s §2.3.** Tady je `display_scale` „CSS transform pro celé zobrazení“, v §2.3 je to
  per-zone pole. Dva různé koncepty se stejným jménem.
- **Zmizelo rozhodnutí `zoom` vs. `transform`** (review §2.7). V CEF to nejsou zaměnitelné věci:
  `zoom` mění layout (a tedy i offsety zón), `transform` ne.
- **Chybí `transform-origin`.** U `bottom-right` zóny s `transform: scale()` bez `transform-origin:
  right bottom` se offsety rozjedou.

**Edit:** přejmenovat na dva klíče a doplnit pravidla:

```jsonc
{
  "render": { "display_scale": 1.0 },   // globální; transform na jednom stage wrapperu, origin "top left"
  "zones": { "BATTLE": { "scale": 1.0 } } // per-zone; origin se odvodí z anchor (bottom-left → "left bottom")
}
```

Plus jedna zakazovací věta: „`zoom` se nepoužívá (mění layout a chová se jinak v CEF než v Chrome).“

### §2.1 Verzování

- **Chybí čtecí pravidla.** `manifest_schema` bez odpovědi na „co dělá renderer při neznámém
  major/minor“ je jen číslo. Doplnit: neznámý **minor** → renderer čte, co zná, ignoruje zbytek;
  neznámý **major** → renderer loguje a jede na built-in defaulty; **striktní stranou je CI
  validátor**, ne runtime.
- **Chybí back-compat tabulka.** Review §5.5 měl pořadí čtení
  `canvases.<id>.size` → deprecated alias (`transient_canvas` / `sysinfo_canvas`) → `DEFAULT_CANVAS`.
  Ve specce to není vůbec, přitom oba aliasy v manifestu **jsou** a `test_v4_manifest_version_and_canvas`
  je tvrdě asertuje.
- **Chybí payload strana.** `V4AssetResolver.to_dict()` publikuje `transient_canvas` a nepublikuje
  `sysinfo_canvas`/`canvases`/`zones`. Specka musí říct, jestli je payload zdrojem pravdy pro JS
  (pak doplnit) nebo ne (pak označit `transient_canvas` v payloadu jako deprecated). Jinak se
  derivovaná konstanta vrátí přes API.

### §2.2 Canvases

- **`icon_box` a `icon_mode` jsou v příkladu obojí a bez precedence.** Ta pole nejsou alternativy,
  jsou ortogonální: `icon_mode` říká, jak se asset kreslí, `icon_box` je geometrie. Pravidlo v textu
  („`icon_box` v px *nebo* lze vyjádřit přes `icon_mode = full_canvas`“) je zmatené.
- **Default musí být `full_canvas`,** protože takové assety dnes jsou. Měřeno: ikona se renderuje
  jako 64×64 box na (28, 38) s `background-size: 420px 140px; background-position: 0 0`, tj.
  **výřez levého horního rohu** — na 3× zoomu je vidět odseknutá šachovnicová vlaječka mimo střed
  wellu.
- **Dvě různé konvence pozičních polí v jednom objektu** (`size` = `[w,h]`,
  `safe_box` = `[l,t,r,b]`, `icon_box` = `[x,y,w,h]`). `safe_box` navíc nemá CSS pořadí
  (CSS je `t,r,b,l`) → záměna je otázka času.
- **Chybí `modules` u `sysinfo`** (review §5.2). Bez něj zůstane v `overlay.css`
  `grid-template-columns: 230px repeat(11, 150px)`, `.sys-mod { width: 150px }` a
  `.sys-mod .layer.segment { background-size: 150px 72px }` — a §3.3 („rozměry se nesmí
  duplikovat“) je pro sysinfo nesplnitelná.

**Edit:** pojmenované klíče + explicitní exkluzivita:

```jsonc
{
  "canvases": {
    "transient": {
      "size": [420, 140],
      "safe_box": { "left": 119, "top": 14, "right": 16, "bottom": 10 },
      "icon_mode": "full_canvas"                       // "glyph" ⇒ icon_box je povinný
      // "icon_box": { "x": 28, "y": 36, "w": 68, "h": 68 }  // zakázané při full_canvas
    },
    "sysinfo": {
      "size": [1920, 72],
      "modules": { "brand_w": 230, "module_w": 150, "count": 11 }
    }
  }
}
```

Validace: `icon_mode = full_canvas` ⇒ `icon_box` **nesmí** být přítomen; `glyph` ⇒ musí být a musí
ležet uvnitř `size`.

### §2.3 Zones

- **`max` mění chování, ne mechanismus.** Dnes cap drží `FAMILY_CAPS` **per family**, a
  `layerRootForFamily()` posílá všech 6 ne-battle families do `#v4-event-layer`. Měřeno:
  `eventLayerChildren = 6`, `scrollHeight = 891 px`. `zones.EVENT.max = 1` je tedy redukce 6 → 1,
  tj. vizuální/behaviorální změna, která podle §5 patří do fáze 2+, ne do fáze 1.
- **Chybí per-family cap.** Zone cap sám neumí vyjádřit „battle 2, timing 1, position 1…“.
- **Chybí pořadí a overflow.** Není řečeno, kde vstupuje nový widget (dnes `appendChild`, tj.
  nejnovější dole u sysinfo) ani co se stane, když stack přeteče výšku. A cap se dnes vynucuje
  na počtu, ne na layoutu: `enforceFamilyCap()` → `hide()` odstraní node až po 320 ms, takže po
  dobu exit animace je ve stacku `cap+1` (review §3.6, ve specce zmizelo).
- **`anchor` má 9 hodnot, ale znaménko offsetu je definované jen pro rohy.** Pro `top`, `bottom`,
  `left`, `right`, `center` je „znaménko se odvodí z anchor“ nedefinované na centrované ose.
- **`align` a `direction` jsou pro dnešní dvě zóny YAGNI** a v kombinaci s `width: 420px` na
  kontejneru ani nefungují — zone kontejner musí přejít na `fit-content`, jinak `align` nic nedělá.

**Edit:**

```jsonc
{
  "zones": {
    "EVENT": {
      "anchor": "bottom-right",        // v1: pouze 4 rohy
      "offset_from": "sysinfo",
      "offset": [48, 19],
      "gap": 10,
      "max": 6,                        // = dnešní chování (6 non-battle families × cap 1)
      "order": "newest_last",          // NOVÉ: kde vstupuje nový widget
      "overflow": "drop_oldest",       // NOVÉ: co při přetečení výšky
      "transition": "fade"
    }
  },
  "families": { "timing": { "max": 1 } } // per-family cap zůstává; efektivní cap = min(family, zone)
}
```

Plus věta: „`max` se vynucuje na layoutu (rezervované sloty), ne jen na počtu aktivních; widget
v exit animaci už slot neblokuje.“ A: „redukce `max` proti dnešnímu stavu je vizuální změna
(fáze 2), ne mechanismus.“ `direction`, `align`, `scale` označit `(fáze 3)` nebo z §2.3 vyndat.

### §2.4 Family binding

- **Cesty v příkladu jsou špatné.** Reálný manifest má `"layer_dir": "themes/cyber_racing/battle/layers"`.
  Prefix `themes/` je nosný: `manifestDiskPath()` v JS, `manifest_rel_to_web()` v Pythonu
  i `test_golden_manifest_states_present_in_all_themes` (`assert icon_path.startswith("themes/")`)
  na něm stojí. Segment `families/` na disku není. Cesta ze specky by dala 404 a rozbila theme
  switching (JS přepisuje `^themes/<x>` na aktuální téma).
- **`"mode": "screen"` renderer nezná.** `rebuildArt()` dělá `layer.mode === "mask" ? mask : image`,
  takže `screen` se tiše vykreslí jako `image`. Buď doplnit enum + CSS (`mix-blend-mode: screen`)
  + validaci, nebo z příkladu vyhodit.
- **„Každá family musí deklarovat `canvas` a `zone`“ zamítne dnešní manifest.** `families.sysinfo`
  existuje a do zóny se nesměruje (JS ji drží mimo přes `TRANSIENT_FAMILIES`). Doplnit výjimku
  nebo rezervovanou zónu `SYSINFO` s fixním anchorem.
- **`presentation.zone` se nesmí použít jako fallback.** Všech 7 Python adaptérů (`battle.py`,
  `timing.py`, `position.py`, `pit.py`, `bio.py`, `exception_extra.py`, `lap.py`) posílá
  `zone="EVENT"` a `EventPresentation.zone` má default `"EVENT"`. Měřeno i na fixture:
  `zonesInEnvelope = "EVENT"` pro `hunting`. Jakmile renderer začne `presentation.zone` respektovat,
  battle skončí v EVENT zóně.

**Edit:** příklad přepsat na reálné cesty (`themes/<theme>/<family>/layers|icons`), enum `mode`
omezit na `image|mask`, doplnit pravidlo precedence:
„`family.zone` má přednost; `presentation.zone` se respektuje teprve poté, co producenti přestanou
posílat konstantní `EVENT` (samostatný work item + test, že battle eventy nesou `zone="BATTLE"`).“

### §2.5 Transitions

- **Chybí mechanismus, jen data.** Bez věty „transition preset se promítá do CSS custom properties
  na zone kontejneru a přepíná se class-ou“ sáhne implementace po Web Animations API a golden
  determinismus je pryč. Dnes je transition jediné CSS pravidlo
  (`transition: opacity 0.28s, transform 0.28s`, měřeno) a `.visible`/`.exit` classy.
- **Chybí vazba na `hide()`.** `DisplayV4.hide()` odstraňuje node po **hardcoded 320 ms**, exit
  ve specce má 240 ms. Manifest s `duration_ms: 600` se tedy uřízne v půlce a widget mezitím drží
  slot ve stacku. Doplnit: removal timer = `delay_ms + duration_ms + 50` a **clamp**
  (`duration_ms ≤ 1000`, `delay_ms ≤ 500`), aby vadný manifest nemohl zaseknout stack.
- **`easing` whitelist s volným `cubic-bezier(...)`** znamená parser a vkládání cizího stringu do
  CSS hodnoty. Omezit na pojmenované easings + malou tabulku pojmenovaných kubik
  (`"snap"`, `"soft"`), definovaných ve specce.
- **Golden režim.** §2.5 správně chce `motion=off`/`layout=golden`, ale nepíše, že v tomto režimu
  musí být **všechny** durations 0 (dnes to řeší `html.preview-layout`/`html.golden-layout` v CSS
  a `isGoldenSnapshot()` v JS — tři různé cesty, které se musí sjednotit).
- **Chybí sysinfo.** Řekněte explicitně, že transitions se na `#sysinfo-widget` nevztahují.

### §2.6 Motion WebM

- **Rozpor s §3.2.** Tady `video` má `width/height: 100%`, v §3.2 má být `var(--v4-canvas-*)`.
  Vyberte jedno: `100%` je lepší (rozměr drží widget root, video ho jen zdědí) — pak z §3.2
  seznamu `video` vyndejte.
- **`object-fit: cover` je špatná rada z vlastního zdůvodnění specky.** `fill` chybu poměru stran
  skryje protažením, `cover` ji skryje **ořezem**. Když je box == nativní rozměr reelu, jsou
  `fill`/`cover`/`none` vizuálně totožné a rozdíl se projeví jen při chybě. Chcete, aby chyba byla
  **vidět** → `object-fit: contain` (mismatch = letterbox) nebo `none`. Skutečný gate je ale CI
  kontrola rozměrů, ne `object-fit`.
- **`fps` nemá konzumenta ani levnou validaci.** Renderer fps neřídí (video jde vlastním tempem)
  a z EBML se levně čte `PixelWidth`/`PixelHeight`; framerate vyžaduje `TrackEntry`/`DefaultDuration`.
  Buď označit jako dokumentační/advisory, nebo vypustit.
- **Chybí back-compat.** Dnes je `motions` **list** 15 jmen. Migrace list → mapa je pro Python
  nerozbíjející (`resolve_motion()` testuje členství, `to_dict()` iteruje, test staví jména
  iterací) — to je nejlevnější výhra v celé specce a má tam být explicitně jako věta, ne implicitně
  v příkladu.
- **Chybí phase → reel routing.** `ENTER_MOTIONS`, `FAMILY_RESULT_MOTION`, `REDUCED_MOTION_SKIP`
  zůstávají hardcoded v JS. Deklarativní `motions` mapa, která tohle neřeší, je poloviční —
  napište alespoň „mimo rozsah schématu 2.0“.
- **Chybí akumulace `<video>`.** `ensureFxVideo()` element odstraní jen při falsy URL, takže na
  jedné kartě může přes fáze zůstat až 6 alpha-VP9 videí. Canvas-vázané reely = tohle je součást
  sizing kontraktu (fill rate, GPU paměť), ne samostatné téma.

### §3.1 Robustnost bootu

- **Hard-fail platí dál.** Měřeno s vadným manifestem: `wsAttempted: []`, unhandled
  `SyntaxError` z `initV4`. WS se nikdy neotevře, a protože backoff žije uvnitř `connectOverlay()`,
  overlay zůstane mrtvý.
- **Degradace na `.fallback` se neděje.** Ve stejném běhu skončil `#sysinfo-widget` s classou
  `has-art` a 2 statickými layery — **ani `v4-sysinfo`, ani `fallback`**. Specka předpokládá,
  že „`.fallback` styling už existuje“; existuje, ale nikdo ho v této cestě nenasadí.
- **„`connectOverlay()` musí vždy běžet“ je nepravda pro demo/golden.** `startV4Demo()` se vrací
  před `connectOverlay()` **záměrně**. Zúžit pravidlo na live cestu.
- **`initV4()` se v demo režimu volá dvakrát** (`bootstrap()` i `startV4Demo()`) → dvojí fetch
  manifestu. Doplnit požadavek „init je idempotentní“.
- **Chybí built-in defaulty** (review §5.5). Bez `DEFAULT_CANVAS` v JS bude fallback „absence
  hodnoty“, a golden render přestane být deterministický (jiný výsledek podle toho, zda fetch stihl).

**Edit:** `try { await initV4(...) } catch { logujeme } finally { if (!demo) connectOverlay(); }`
+ `const DEFAULT_CANVAS = { transient: [420, 140], sysinfo: [1920, 72] }` + „při vadném manifestu
renderer aktivně nasadí `.fallback` na widgety **i na sysinfo**“.

### §3.2 CSS custom properties

- Správný směr, ale **seznam míst je nekompletní.** Chybí: `#v4-golden-gallery
  { grid-template-columns: repeat(auto-fill, 420px) }`, `.golden-cell { width: 420px }`,
  `.v4-copy { left: 119px; right: 16px }` (to je `safe_box`!) a celý sysinfo blok
  (`background-size: 1920px 72px` **ve dvou souborech**, grid v `overlay.css`).
- **Chybí pravidlo o maskách** (review §2.4): masky se neškálují, `mask-size` == canvas, jinak
  vzniknou nekonzistentní hrany mezi `mask` a `image` vrstvami téže karty.
- **Chybí, kam se var píše.** Musí to být root widgetu (ne `:root`), aby mohly různé zóny/rodiny
  mít různý canvas současně — to je právě ta „stack flexibilita“. A musí to být **zápis varu**,
  ne `rebuildArt()`, protože ten dělá `art.replaceChildren()` a restartuje všechny reely.

### §3.3 Pozice se nesmí duplikovat

- **Chybí rozhodnutí o V3.** `overlay.css` (načítá se pro **oba** renderery) má vlastní
  `bottom: 91px`, `width/height: 420/140`, `.layer.native { 420px 140px }` a
  `left: calc(15.24% - …)` pro icon well. Review §2.1 žádal explicitní verdikt; specka ho nemá.
  Doplnit jednu větu: „V3 zůstává zamčené na 420×140 a vlastních literálech; canvas vars a zones
  platí jen pro `#v4-*` / `.v4-*`; duplikát v `overlay.css` je akceptovaný dluh do odstranění V3.“
- **Zóny „bez rebuildu widgetů“ vyžadují eager kontejnery** (viz §1.1) — dnes vznikají lazy.

### §4 CI / QA — hlavní problém specky

Kontext, který ve specce chybí a mění všechno: `.github/workflows/tests.yml` běží na
**`windows-latest`**, matice 3.11/3.12/3.13, instaluje `pytest pytest-asyncio pytest-cov freezegun`.
**Žádný browser, žádný Node, žádný Pillow.** `.cursorrules`: nové dependency jen s review.

#### §4.1 Computed-style (CDP) — dobrý gate, ale ne na golden URL

- **Zone asserty na golden URL nejdou.** Měřeno: v gallery režimu `#v4-battle-stack`
  i `#v4-event-layer` **neexistují** (`null`), gallery je skrývá a widgety jdou do `.golden-stage`.
  Zone geometrii je nutné měřit na live URL (`/overlay?demo=1&renderer=v4&fixture=battle_stack`).
- **Asertujte jen font-nezávislé věci:** box widgetu, `background-size`, `mask-size`, icon box,
  rect zone kontejneru vs. `sysinfo.size[1] + offset[1]`, počet `<video>` v golden = 0.
- **Bez nové dependency to jde:** aiohttp (core dep) umí ws klienta, takže raw CDP nad
  `--headless=new` je pár desítek řádků; tenhle review je tak celý naměřený. To je argument, který
  ve specce má být, jinak diskuse skončí na „playwright ne“.
- **Doplnit provozní detaily:** který runner (ubuntu-latest, Chrome je preinstalovaný), server na
  **ephemeral portu** (per `tests-policy.mdc` je fixní port zdroj falešných failů), skip na Windows
  dev stroji, a jestli je job `required` nebo `continue-on-error` v prvním PR.

#### §4.2 Pixel golden snapshots — nejdražší a nejméně spolehlivý gate v tomhle repu

- **Naivní screenshot pokryje 20 z 33 fixtures.** Měřeno: `galleryScrollHeight = 1761`,
  `clientHeight = 993`. Bez `captureBeyondViewport` + explicitního `clip` je zbytek galerie
  neviditelný pro hash — a hash bude přesto „zelený“.
- **Fonty.** Stack je `"Nimbus Sans Narrow", "Arial Narrow", "Eurostile", "Rajdhani", "Segoe UI"`.
  V CI kontejneru `fc-match` vrací pro první dva `Noto Sans`; na `windows-latest` to bude
  `Arial Narrow`; v OBS CEF cokoliv, co má uživatel. **Pixel hash bez zabaleného woff2 měří runner,
  ne kód.**
- **Verdikt:** pixel hash používat jako **self-comparison ve stejném jobu** (před/po v jednom běhu,
  stejný Chrome, stejné fonty) pro fázi „mechanismus“, a **necommitovat baseline**. Pokud se baseline
  chce, je předpokladem: bundled woff2 + pinned Chrome + `text=off` (hash jen artu) + full-page clip.

#### §4.3 Manifest + asset invarianty — tady je ta reálná hodnota

Nejlevnější, deterministické, běží v dnešním jobu bez čehokoli nového. Doplnit do výčtu:

- reference resolve: `family.canvas` ∈ `canvases`, `family.zone` ∈ `zones`,
  `zone.transition` ∈ `transitions`, `motion.canvas` ∈ `canvases`;
- enumy a rozsahy: `mode ∈ {image, mask}`, `anchor`, `easing`, `duration_ms/delay_ms` int ≥ 0 + clamp;
- `icon_mode` × `icon_box` exkluzivita, `safe_box`/`icon_box` uvnitř `size`;
- WebM rozměry z EBML (`PixelWidth 0xB0`, `PixelHeight 0xBA`) — bez ffmpeg;
- **negativní literálový gate:** v `display-v4.css` se nesmí objevit `420px|140px|1920px|72px|91px`
  mimo deklarovaný allowlist. 20 řádků Pythonu, vynucuje §3.2 i §3.3 mechanicky a nahrazuje dnešní
  brittle „`assert "isolation: isolate" in css`“ pozitivním invariantem obráceně — negativní
  invariant nepadá na formátování.

#### Co ve §4 chybí úplně

- **Font determinismus** jako předpoklad jakéhokoli textového nebo pixelového gate.
- **Text overflow / safe box test.** §5 fáze 2 ho slibuje, §2 ho nedefinuje, §4 ho nemá.
  Měřeno: `.v4-copy` má `scrollHeight = 141` proti `clientHeight = 140` už teď — safe area
  neexistuje jako pojem, jen jako komentář.
- **De-brittle existujících testů** (review §2.6). Refaktor CSS na vars rozbije
  `test_golden_gallery_clips_glow_overflow` a `test_golden_reduced_motion_paths` z důvodů
  nesouvisejících s chováním. Bez tohoto úkolu se práce zablokuje na falešných failech.
- **Seznam testů, které refaktor rozbije:** `test_v4_manifest_version_and_canvas`
  (`transient_canvas == [420, 140]`), `test_v4_theme_file_parity` (přesně 185 souborů),
  `test_v4_pack_size_budget` (8 MiB strop při ~5,8 MiB).
- **Boot resilience test** (review §7.2e) — ve specce §3.1 je požadavek, ale ve §4 pro něj není gate.
  Přitom je to nejcennější browser test, jaký tu může být: jeden assert `wsAttempted.length > 0`
  nad vadným manifestem.

**Minimální subset, který má §4 požadovat pro fázi 1** (a nic víc):

| Gate | Kde | Cena | Status |
|---|---|---|---|
| Manifest schema + reference + enumy | pytest, dnešní job | triviální | required |
| Canvas ↔ PNG/WebM rozměry | pytest, dnešní job | nízká | required |
| Negativní literálový gate v CSS | pytest, dnešní job | triviální | required |
| CDP: geometrie + zóny (live URL) + 0× `<video>` v golden + boot resilience | nový job, ubuntu, raw CDP nad aiohttp | střední | advisory v 1. PR, pak required |
| Pixel hash před/po | lokálně / PR artefakt | vysoká | **ne gate** |

### §5 Rollout

- **Fáze 1 nesmí obsahovat `zones.*.max`, které mění dnešní chování** (viz §2.3).
- **Chybí definice acceptance kritéria „nulová vizuální změna“** — a s ohledem na §4.2 musí být
  definované jako self-comparison ve stejném běhu, ne „hash se rovná uloženému baseline“.
- **Chybí fáze 0: de-brittle testů** a doplnění `sysinfo_canvas`/`canvases` do resolver payloadu.
- **Chybí „Docs impact“** — `04-docs-policy.mdc` to vyžaduje. Dotčené: `API.md`
  (`snapshot.v4.resolved`), `README.md` (konfigurace Browser Source 1920×1080),
  `src/irswitch/web/overlay/GOLDEN_V4.md` (pokud se změní golden URL, např. `text=off`),
  `CONFIG.md` (pokud vznikne konfigurovatelný `render.display_scale`),
  `BUILD_AND_DEPLOY.md` + `test_v4_pack_size_budget` (pokud sady velikostí koexistují).

---

## 3. Co ze `V4_RENDERER_SIZING_SPEC_REVIEW.md` do specky nedoteklo

Tohle není duplikace — jsou to body, které review vyžadoval a specka je nemá:

- rozhodnutí o V3 (`overlay.css` sdílí oba renderery) — §2.1 review
- masky se neškálují — §2.4 review
- `<video>` akumulace + `rebuildArt()` restartuje reely — §3.5 review
- cap+1 během exit animace, cap se musí vynutit na layoutu — §3.6 review
- `lastSequence` roste bez omezení — §3.6 review
- built-in defaulty a „fallback je konstanta, ne absence hodnoty“ — §3.2, §5.5 review
- `text_rules` (max_lines / overflow / min_font_px) — §4, §3.4 review
- SYSINFO slot mapping (10 ikon na disku vs. 7 v `SYSINFO_ICON_SLOTS`) — §4 review
- deprecated aliasy a pořadí čtení — §5.5 review
- `sysinfo_canvas` do `to_dict()` — §6 review
- de-brittle golden testů — §2.6 review
- `zoom` vs. `transform` v CEF — §2.7 review
- dopad na distribuci (pack budget) — §2.5, §8 review

---

## 4. Kde je specka přehnaná (škrtnout nebo odložit)

- 9 hodnot `anchor` + `align` + `direction` pro dnešní 2 zóny → v1 jen 4 rohy.
- `zones.*.display_scale` v §2.3, když §5 ho dává do fáze 3 → označit `(fáze 3)`.
- volný `cubic-bezier(...)` v `easing` → pojmenovaná tabulka.
- `motions.*.fps` → advisory nebo pryč (nemá konzumenta ani levnou validaci).
- per-family/per-state transition override → až bude use case.
- pixel hash jako hard gate → PR artefakt (viz §4.2).

## 5. Prioritně

1. **§4 přepsat podle reality CI** (windows-latest, žádný browser) + doplnit font determinismus
   a boot resilience gate; pixel hash degradovat.
2. **§2.3 `max` a §2.4 `presentation.zone`** — dvě tikající vizuální regrese schované v „mechanismu“.
3. **Odstranit vnitřní rozpory** §2.6 ↔ §3.2 a §1.2 ↔ §2.3.
4. **Opravit příklady** (`layer_dir`, `mode: "screen"`, `icon_box` + `icon_mode`, pojmenované klíče).
5. **§3.1 doplnit** built-in defaulty, `finally connectOverlay()`, aktivní `.fallback`, idempotentní init.
6. **§3.2/§3.3 dotáhnout na sysinfo, gallery grid a V3** — jinak zůstane polovina literálů na místě.
7. **Doplnit chybějící kusy kontraktu** (`text_rules`, back-compat aliasy, docs impact, seznam
   testů, které refaktor rozbije).
