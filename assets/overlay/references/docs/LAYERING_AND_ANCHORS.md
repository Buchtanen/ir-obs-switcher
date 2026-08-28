# Vrstvení, rozměry a anchory

| Objekt | Rozměr | Anchor | Bezpečný obsah |
|---|---:|---|---|
| Transient | 420 x 140 | podle zóny | inset 20 px; rail-left obsah od x=54 |
| Session/Major | 420 x 140 | top-center, y=64 | střed viewportu pouze nahoře |
| Bio expanded | 420 x 140 | top-right, x=48, y=120 | stejné jako transient |
| Battle stack | 420 x 140 každý | bottom-left, x=36, bottom=91 | max 2, gap 10 |
| Event | 420 x 140 | bottom-right, x=48, bottom=91 | max 1 |
| SYSINFO | 1920 x 72 | bottom-left | brand 230 px, data x=246-1902 |

Všechny SVG vrstvy transientu mají viewBox `0 0 420 140`, takže je lze absolutně překrýt na `inset:0`. SYSINFO vrstvy mají viewBox `0 0 1920 72`. Ikony mají viewBox `0 0 64 64` a doporučený display 36-44 px.

Rail je zarovnaný na fyzický levý nebo pravý okraj. Masky jsou bílé alpha matte; používejte je přes CSS `mask-image` / `-webkit-mask-image` nebo jako track matte v compositoru. Rasterová maska zůstává alpha-transparentní.
