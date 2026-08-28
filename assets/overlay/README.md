# Pitwall Light / Minimal overlay theme

Implementacni graficka sada svetleho minimalistickeho theme pro OBS Browser
Source v projektu `ir-obs-switcher`. Vsechny podklady teto theme sady jsou
zamerne soustredene pod `assets/overlay/`, aby slo branch pouzit nebo porovnat
bez zasahu do runtime kodu aplikace.

## Struktura

- `backgrounds/` - poznamka k pruhlednemu 1920 x 1080 canvasu;
- `frames/` - master SVG ramecky, masky, plates a eventove sablony;
- `icons/` - eventove, SYSINFO a BLE/HR SVG vrstvy;
- `accents/` - svetelne a technicke akcenty a mapovani eventu;
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
