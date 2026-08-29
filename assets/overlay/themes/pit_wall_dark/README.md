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

Pro implementaci zacnete v
`references/docs/IMPLEMENTATION.md` a
`references/examples/html/widget-composition.html`.
