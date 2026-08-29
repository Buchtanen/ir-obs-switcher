# Naming convention

Formát: `pw-{scope}-{layer-or-element}-{variant}-{state}.{ext}`.

- prefix `pw`: Pitwall / Race Control;
- semantic scope: `hunting`, `hunted`, `battle`, `lap`, `pb`, `position`, `final-lap`, `finish`, `bio`, `sysinfo`;
- pořadí `01` až `08` ve template složkách určuje defaultní z-index;
- stavová barva se zapisuje jen u skutečně barevné vrstvy: `cyan`, `amber`, `red`, `green`;
- rozlišení je dáno adresářem `1x` / `2x`, ne suffixem souboru;
- master je vždy SVG; PNG a WebP jsou odvozené exporty se stejným stemem.

Příklady: `pw-hunting-04-status-rail-cyan.svg`, `pw-icon-stopwatch.svg`, `pw-sysinfo-bus-line.svg`, `pw-mask-wipe-left.svg`.

Added semantic scopes: `pit`, `exception`; state glyphs use the complete state stem, for example `pw-icon-pit-entry.svg` / `pl-icon-invalid-lap.svg`.
