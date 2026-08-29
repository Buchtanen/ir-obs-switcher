# Motion language

## Lifecycle

- ENTER 360 ms: horizontální timing wipe + rail reveal; opacity může doběhnout v první polovině.
- ACTIVE: karta je klidná; povolený je jen datový micro-pulse nebo změna jednotlivých ticks.
- COMPACT 180-240 ms: snížit detail opacity, neměnit 420 x 140.
- SUSPENDED: opacity 0.40-0.48, bez aktivních sweepů.
- EXIT 300 ms: opačný timing wipe; žádné scale-out.

## Event-specific

- HUNTING: rail 220 ms zdola nahoru; closing-rate ticks po 18 ms.
- HUNTED: pressure segments postupně; red přepnutí pouze na critical payload.
- PB: LCD flash 300 ms, peak opacity max 0.18.
- POSITION: mask reveal ve směru šipky, 280 ms.
- FINAL LAP: jeden horizontal bus sweep, 420 ms.
- FINISH: scanner projede jednou, pak se zastaví; žádné nekonečné blikání.
- BIO: trace posun pouze při novém BLE sample; nepředstírat EKG frekvenci.

Při `prefers-reduced-motion` vypněte tick build, trace scrolling a flash; zkraťte opacity transition na max 160 ms.
