# OBS Browser Source

1. Browser Source nastavte na `1920 x 1080`.
2. Dokument musí mít `html, body { margin:0; width:1920px; height:1080px; background:transparent; overflow:hidden; }`.
3. Assety servírujte přes lokální HTTP server nebo absolutní cestu, ne přes náhodné `file://` relativní odkazy.
4. Zapněte `Shutdown source when not visible` jen pokud event engine po obnovení bezpečně načte current state.
5. Pro čitelnost v OBS nepoužívejte browser zoom. Canvas škálujte jedním wrapper transformem podle cílového výstupu.
6. Ověřte alpha v transparentní scéně a současně nad světlým i tmavým onboard záběrem.

Referenční markup je v `examples/html/widget-composition.html` a `examples/html/sysinfo-composition.html`. Zobrazené texty jsou pouze HTML placeholdery; žádný text není součástí assetu.
