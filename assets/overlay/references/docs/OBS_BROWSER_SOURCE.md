# OBS Browser Source guide

1. Browser Source nastavte na `1920 x 1080`; HTML i body musí mít nulový margin, transparentní background a hidden overflow.
2. Assety servírujte přes lokální HTTP server nebo stabilní absolutní cestu.
3. Root overlay škálujte jako jeden celek. Jednotlivé karty nesmí mít odlišný transform scale.
4. Pro animovaný radar/trace použijte 60 FPS; pro statickou scénu postačí 30 FPS.
5. V transparentním production režimu nesmí zůstat žádný full-canvas tint, pseudo-element ani demo background.
6. Ověřte čitelnost nad světlou oblohou, tmavým asfaltem a detailním kokpitem; otestujte i fallback bez backdrop blur.
7. Po reconnectu Browser Source musí event engine znovu dodat current state, jinak nevypínejte zdroj při skrytí.

Referenční CSS je v `examples/css/pitwall-light.css`. Ukázkové texty v HTML jsou pouze dynamické DOM placeholdery.
