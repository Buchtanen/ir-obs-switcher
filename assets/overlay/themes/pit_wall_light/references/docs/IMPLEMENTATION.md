# Implementace PITWALL LIGHT

## Vrstvení transientu

1. base plate (`z=10`);
2. data surface a technical grid (`z=20-30`);
3. icon well (`z=40`);
4. border a edge-light (`z=50-60`);
5. stavový rail, ticks, corner cap a divider (`z=70-100`);
6. radar/wireframe/pulse fragment (`z=110-120`);
7. jednobarevná SVG ikona (`z=200`);
8. dynamický HTML obsah (`z=300`).

Všechny vrstvy jedné transient template mají stejné `viewBox="0 0 420 140"`. Překrývejte je absolutně na `inset:0`; nikdy je nenatahujte podle délky textu. Barevný stav mění jen rail, ikonu, krátký accent a případně konkrétní hodnotu.

## Formáty a škálování

Preferujte SVG pro Browser Source. PNG/WebP použijte jen pokud cílová pipeline externí SVG neumí. 2x bitmapy zobrazujte stále v logickém rozměru 420 x 140, 180 x 72 nebo 1920 x 72. Nikdy nemixujte 1x a 2x vrstvy v jedné kompozici.

## Text a safe area

Pro běžnou kartu začíná text na `x=118`, končí na `x=400`, horní baseline je `y=18` a spodní safe edge `y=122`. Hlavní title držte na jednom řádku; dlouhé copy ukončete ellipsis. Čísla používejte s `font-variant-numeric: tabular-nums`.

## Event adapter

Frontend přečte `accents/event-visual-map.json`, vybere template, variantu, rail, ikonu a zónu. Payload smí změnit textové uzly a CSS custom properties, ale nesmí změnit geometrii. `POSITION_GAINED` a `POSITION_LOST` sdílí stejnou template; mění se jen tokeny, ikona a motion direction.

## BLE/HR

Compact vrstvu skládejte do posledního SYSINFO segmentu: base, pulse, state accent, heart/BLE icon a HTML BPM. Expanded používá template `bio`; ACTIVE a SURGE trace jsou samostatné. BLE connection indikátor vyberte z `icons/ble-hr/connection-states/`.

## SYSINFO

Full strip skládejte z base, edge light, bus line, ticks, dividers, brand surface a footer accent. Pokud aplikace používá modulární DOM, lze místo full backgroundu použít `sysinfo/segments/`. Stavová barva se mění per segment, nikdy na celém stripu.


## V4 art-pack completion (1.1.0)

- The authoritative 35-state map is `accents/event-visual-map.json`; the readable table is `references/docs/STATE_VISUAL_MAP.md`.
- `pit` and `exception` are real family templates with independent SVG layers and 1x/2x alpha raster exports in packages 03-05.
- Native transient geometry is 420 x 140. Individual cards must not be enlarged with CSS scale.
- Event glyph masters are 64 x 64 SVG. The exact icon box is `[39, 46, 48, 48]` (`[x,y,w,h]`).
- SYSINFO uses the runtime grid `brand 230 + 11 x 150`; x=1880..1920 stays as a trailing safe area.
- No repeatable WebM authoring pipeline exists in this pack. `motion/manifest.json` is authoritative and selects CSS fallback intent; no placeholder video is shipped.
