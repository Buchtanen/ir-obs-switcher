# Motion guide

- ENTER 340 ms: jemný 24px slide + blur-to-sharp; rail reveal 220 ms.
- ACTIVE: karta zůstává klidná; povolen je jednorázový radar sweep nebo sample-driven pulse update.
- UPDATE 220 ms: mění se pouze data a malé accent fragmenty, bez opakovaného ENTER.
- COMPACT 180-240 ms: sekundární detail ztlumit, box zůstává 420 x 140.
- SUSPENDED: opacity přibližně 0.46, bez sweepů.
- EXIT 300 ms: opačný slide, žádné dramatické scale-out.
- HUNTING/HUNTED/BATTLE: radar sweep maximálně jednou při vstupu, rings mohou krátce pulznout.
- PB: jeden soft surface flash, peak opacity nejvýše 0.16.
- POSITION: reveal ve směru chevronu.
- FINAL LAP/FINISH: jeden edge-light sweep; potom statický stav.
- BLE/HR: trace se aktualizuje jen při novém sample; nesimuluje EKG.

Při `prefers-reduced-motion` vypněte sweep, scrolling trace a flash; opacity transition nejvýše 160 ms.

## WebM delivery status

The 15 theme-specific reels in this directory are authoritative alpha-VP9 motion assets. They are generated reproducibly by `scripts/build_pit_wall_theme_additions.py`, use the native 420 x 140 canvas, contain no baked text or numbers, and end transparent so the static plate remains authoritative. CSS is retained only as a missing-file and reduced-motion fallback. See `references/docs/MOTION_QA.md` for the ffprobe matrix.
