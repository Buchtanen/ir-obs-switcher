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

No repeatable WebM authoring pipeline is established in this pack. `motion/manifest.json` therefore declares CSS fallback as authoritative. Reels may be added later only when alpha-VP9 export and deterministic verification are available; no placeholder WebM is included.
