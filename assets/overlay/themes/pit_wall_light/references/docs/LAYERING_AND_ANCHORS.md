# Anchory, safe areas a rozměry

| Objekt | Rozměr | Anchor | Safe area |
|---|---:|---|---|
| Transient | 420 x 140 | podle event zóny | x 118-400, y 18-122 |
| Session / major | 420 x 140 | x 750, y 64 | stejná jako transient |
| BLE/HR expanded | 420 x 140 | x 1452, y 120 | stejná jako transient |
| Battle stack | 420 x 140 každý | x 36, bottom 91, gap 10 | max 2 |
| Event | 420 x 140 | x 1452, bottom 91 | max 1 |
| BLE/HR compact | 180 x 72 | poslední SYSINFO segment | x 12-168, y 10-62 |
| SYSINFO | 1920 x 72 | x 0, y 1008 | brand 230; data x 246-1902 |

Z-index a animační role každého souboru jsou také v `manifests/asset-manifest.json` a `.csv`.
