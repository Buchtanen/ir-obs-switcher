# Pit Wall Dark overlay theme

Implementacni graficka sada pro OBS Browser Source v projektu `ir-obs-switcher`
(drive „Pitwall / Race Control“). Vsechny podklady teto theme sady jsou
soustredene pod `assets/overlay/themes/pit_wall_dark/`, aby slo pack pouzit
nebo porovnat bez zasahu do runtime kodu aplikace a bez kolize s jinymi
theme packy.

## Struktura

- `backgrounds/` - poznamka k pruhlednemu 1920 x 1080 canvasu;
- `frames/` - master SVG ramecky, masky, plates a eventove sablony;
- `icons/` - eventove a SYSINFO SVG vrstvy;
- `accents/` - technicke akcenty a mapovani eventu na vizualni tokeny;
- `motion/` - motion kontrakt a doporucene prechody;
- `textures/` - master SVG datove plochy;
- `references/` - implementacni dokumentace a HTML/CSS kompozice;
- `packages/` - kompletni rozdelene ZIP exporty vcetne PNG a WebP variant;
- `manifest.json` - strojove citelny katalog vsech zdrojovych assetu;
- `theme-tokens.json` - design tokeny theme.

Sada nepouziva plny bitmapovy background. Widgety a SYSINFO jsou pruhledne
vrstvy skladane nad OBS scenou; zive hodnoty a text renderuje HTML.

## V4 completion 1.1.0

- full 35-state map and all 35 event routes: `accents/event-visual-map.json`;
- readable decision table: `references/docs/STATE_VISUAL_MAP.md`;
- new `pit` and `exception` family templates in `frames/templates/`;
- state-specific 64 x 64 glyphs in `icons/event/`;
- exact Dark `iconBox`: `[54, 50, 40, 40]`;
- SYSINFO grid: brand 230 + 11 modules x 150, with a 40 px trailing safe area;
- motion is CSS fallback by design until an alpha-WebM pipeline is established.

Pro implementaci zacnete v
`references/docs/IMPLEMENTATION.md` a
`references/examples/html/widget-composition.html`.
