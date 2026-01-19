# TUI Test Checklist

## Test 1: test_tui_connection ✅/❌

**Postup**:
1. Spusť službu: `irswitchd --config config/config.ini`
2. Spusť TUI: `irswitch-tui --url http://127.0.0.1:17321`
3. Ověř, že TUI se připojí bez chyb

**Očekávaný výsledek**: TUI se zobrazí s aktuálním stavem služby

**Status**: ⏳ Čeká na test

---

## Test 2: test_tui_status_display ✅/❌

**Postup**:
1. Spusť službu a TUI
2. Ověř zobrazení všech status polí:
   - iRacing: Connected/Disconnected
   - OBS: Connected/Disconnected
   - Mode: IDLE/GARAGE/RACE/REPLAY/QUIT/RESTART
   - Current Scene: název aktuální scény
   - Target Scene: název cílové scény
   - Autoswitch: ON/OFF
   - Reason: důvod aktuálního stavu
   - **Streaming**: true/false (pokud je v API)
   - **Stream Duration**: čas (pokud je v API)

**Očekávaný výsledek**: Všechna pole jsou zobrazena a aktualizována v real-time

**Status**: ⏳ Čeká na test

---

## Test 3: test_tui_controls ✅/❌

**Postup**:
1. Spusť službu a TUI
2. Testuj každé tlačítko:
   - **Toggle Autoswitch**: Ověř, že se přepne autoswitch on/off
   - **Override: Race**: Ověř, že se aplikuje override na Race scénu
   - **Override: Pits**: Ověř, že se aplikuje override na Pits scénu
   - **Override: Safe**: Ověř, že se aplikuje override na Safe scénu (dynamicky získáno ze statusu)

**Očekávaný výsledek**: Všechna tlačítka fungují a aktualizují stav, scény jsou dynamické

**Status**: ⏳ Čeká na test

---

## Test 4: test_tui_keybindings ✅/❌

**Postup**:
1. Spusť službu a TUI
2. Testuj klávesové zkratky:
   - `q`: Ověř, že TUI se ukončí
   - `t`: Ověř, že se přepne autoswitch on/off

**Očekávaný výsledek**: Všechny klávesové zkratky fungují

**Status**: ⏳ Čeká na test

---

## Test 5: test_tui_realtime_updates ✅/❌

**Postup**:
1. Spusť službu a TUI
2. Změň stav služby (např. připoj OBS, změň mód v iRacing)
3. Ověř, že TUI se automaticky aktualizuje

**Očekávaný výsledek**: TUI se aktualizuje automaticky při změně stavu

**Status**: ⏳ Čeká na test

---

## Test 6: test_tui_connection_status_indicators ✅/❌

**Postup**:
1. Spusť službu a TUI
2. Ověř barevné indikátory:
   - **Zelená**: Connected (iRacing/OBS připojen)
   - **Červená**: Disconnected (iRacing/OBS odpojen)
3. Změň stav připojení (vypni/zapni OBS nebo iRacing)
4. Ověř, že se barvy aktualizují

**Očekávaný výsledek**: Barevné indikátory správně zobrazují stav připojení

**Status**: ⏳ Čeká na test

---

## Test 7: test_tui_notifications ✅/❌

**Postup**:
1. Spusť službu a TUI
2. Testuj notifikace při změně připojení:
   - **iRacing disconnected**: Vypni iRacing → Ověř, že se zobrazí notifikace "iRacing disconnected" (severity: error)
   - **iRacing connected**: Zapni iRacing → Ověř, že se zobrazí notifikace "iRacing connected" (severity: success)
   - **OBS disconnected**: Vypni OBS → Ověř, že se zobrazí notifikace "OBS disconnected" (severity: error)
   - **OBS connected**: Zapni OBS → Ověř, že se zobrazí notifikace "OBS connected" (severity: success)
3. Ověř, že notifikace se zobrazují v TUI (ne jako Windows notifikace)
4. Ověř, že notifikace mají správnou barvu (error = červená, success = zelená)

**Očekávaný výsledek**: 
- Notifikace se zobrazují v TUI při každé změně připojení
- Notifikace mají správnou barvu podle severity
- Notifikace se zobrazují i když jsou Windows notifikace vypnuté

**Status**: ⏳ Čeká na test

---

## Test 8: test_tui_error_handling ✅/❌

**Postup**:
1. Spusť službu a TUI
2. Vypni službu (zastav `irswitchd`)
3. Ověř, že TUI zobrazí chybovou notifikaci
4. Zapni službu znovu
5. Ověř, že TUI se znovu připojí (nebo zobrazí chybu pokud reconnection není implementováno)

**Očekávaný výsledek**: TUI správně zpracovává chyby a zobrazuje uživatelsky přívětivé zprávy

**Status**: ⏳ Čeká na test

---

## Poznámky k testování

- Všechny testy jsou manuální (vyžadují interakci)
- Testuj postupně, jeden po druhém
- Zaznamenej všechny problémy a pozorování
- Ověř, že TUI zobrazuje i nové stavy (QUIT, RESTART, streaming)
