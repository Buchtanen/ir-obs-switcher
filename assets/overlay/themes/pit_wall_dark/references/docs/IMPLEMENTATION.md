# Implementace Theme 4

## 1. Výběr assetu

Frontend přečte `tokens/event-visual-map.json`, vybere semantic template a stavovou barvu. Každá template složka obsahuje samostatné vrstvy ve správném pořadí. Společné vrstvy jsou navíc v `assets/vector/common/` pro deduplikovanou implementaci.

## 2. SVG, PNG a WebP

Preferujte SVG pro rámy, ticks, grid, rail, masky, chevrons a ikony. PNG/WebP použijte, pokud pipeline neumí bezpečně načíst externí SVG. WebP je lossless a zachovává alpha. 2x exporty jsou určeny pro škálování na 1440p/4K; v CSS je stále zobrazujte v logické velikosti 420 x 140 nebo 1920 x 72.

## 3. Textový layout

Pro rail vlevo začíná safe content na `x=54`; pro rail vpravo může začít na `x=22` a končí nejpozději na `x=362`. Primární hodnota má tabular numerals. Doporučený font stack je Barlow Condensed / Roboto Condensed / Arial Narrow. Důležité hodnoty 30-36 px, titul 22-24 px, label 10-12 px, jednotky 11-13 px.

## 4. Stavové tokeny

- `active`: cyan `#35D7FF`
- `pressure`: amber `#F4A62A`
- `critical`: red `#FF4E5B`
- `positive`: green `#36D28A`
- `neutral`: muted `#8DA2AD`

Barva se mění lokálně na railu, ikoně, krátké value underline nebo konkrétním SYSINFO kanálu. Celou plate nepřebarvujte.

## 5. Eventové skládání

- HUNTING: cyan left rail, target/radar, right-side technical grid, closing-rate ticks.
- HUNTED: amber right rail; red jen při explicitním critical stavu; pressure icon/bars.
- BATTLE: horní a dolní datová větev kolem centrálního timing pivotu.
- LAP: stopwatch/flag v rail zóně, čas jako dominantní HTML hodnota.
- PB: green rail a krátký LCD surface flash do světlé šedé, bez změny plate.
- POSITION: stejná geometrie pro gain/loss; mění se icon, rail token a motion direction.
- FINAL LAP / FINISH: major surface, stále 420 x 140; delší active display, ne větší footprint.
- BIO: heart/BLE ikona a pulse trace jako oddělená vrstva; BPM je HTML.
- SYSINFO: base + bus line + ticks + dividers + kanály; stav se mění per channel.

## 6. CSS/OBS

Použijte pevný 1920 x 1080 overlay root a `transform: scale(...)` až na celé kořenové vrstvě, ne na jednotlivých kartách. V OBS nastavte Browser Source na 1920 x 1080, transparentní background a 60 FPS jen pokud jsou animované trace/ticks; pro statickou scénu postačuje 30 FPS.
