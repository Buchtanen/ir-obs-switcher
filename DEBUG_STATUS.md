# Shrnutí stavu ladění - Co zbývá odladit

## Přehled dokončených úkolů

### ✅ Dokončené podle STATUS.md a tests.md

#### OBS funkcionalita
- ✅ **debug_obs_connection_states** - Rozlišení stavů připojení, notifikace
- ✅ **debug_obs_scene_validation** - Validace scén při připojení
- ✅ **debug_notifications** - Windows notifikace pro změny připojení

#### iRacing funkcionalita
- ✅ **debug_iracing_connection** - Detekce připojení/odpojení
- ✅ **debug_iracing_mode_detection** - Detekce všech módů (IDLE, GARAGE, RACE, REPLAY, QUIT)
- ✅ **debug_quit_detection** - Detekce ukončení hry
- ✅ **debug_restart_hotkey** - Globální hotkey pro RESTART mód
- ✅ **debug_loading_screen_handling** - Grace period pro loading screen

#### TUI a UI
- ✅ **debug_tui_dynamic_scenes** - Dynamické scény v TUI
- ✅ **debug_logging** - Debug logování do `.cursor/debug.log`

---

## Co zbývá odladit (podle plánu ladění)

### 🔧 Task 12: Test state machine s reálnými daty

**Status**: Částečně dokončeno

**Co funguje**:
- ✅ Základní flow funguje
- ✅ Debounce a cooldown jsou implementovány
- ✅ Override funkcionalita funguje

**Co zbývá otestovat**:
- ⏳ **Edge case: Rychlé změny módů** - Ověřit, že debounce správně funguje při velmi rychlých změnách
- ⏳ **Edge case: Override během debounce** - Ověřit, že override má prioritu i během debounce
- ⏳ **Edge case: Vypnutí autoswitch během běhu** - Ověřit graceful handling
- ⏳ **Edge case: iRacing disconnect během přepínání** - Ověřit, že se stav správně aktualizuje

**Referenční test**: `debug_state_machine_with_iracing` (tests.md, řádek 609)

---

### 🔧 Task 13: Test OBS scene switching

**Status**: Částečně dokončeno

**Co funguje**:
- ✅ Základní přepínání scén funguje
- ✅ Scény se přepínají podle módu iRacing

**Co zbývá otestovat**:
- ⏳ **Edge case: Idempotentní chování** - Ověřit, že přepnutí na stejnou scénu nezpůsobí problémy
- ⏳ **Edge case: Chybějící scéna v OBS** - Ověřit error handling když scéna neexistuje
- ⏳ **Edge case: Rychlé přepínání** - Ověřit, že cooldown brání příliš rychlému přepínání
- ⏳ **Edge case: OBS disconnect během přepínání** - Ověřit graceful handling

**Referenční test**: `debug_scene_switching_with_iracing` (tests.md, řádek 573)

---

### 🔧 Task 14: Test API serveru

**Status**: Částečně dokončeno (unit testy prošly)

**Co funguje**:
- ✅ REST endpointy (`GET /status`, `POST /override`, `POST /autoswitch/toggle`)
- ✅ WebSocket endpoint (`WS /ws`)
- ✅ Unit testy prošly

**Co zbývá otestovat**:
- ⏳ **Real-world test: WebSocket reconnection** - Ověřit, že WebSocket se správně reconnectuje při ztrátě spojení
- ⏳ **Real-world test: API během různých stavů** - Ověřit response formáty při různých stavech (OBS disconnected, iRacing disconnected, override active)
- ⏳ **Edge case: Concurrent requests** - Ověřit, že API správně zpracovává souběžné requesty
- ⏳ **Edge case: Stream status v API** - Ověřit, že stream status se správně zobrazuje v `/status` endpointu

---

### 🔧 Task 15: Test TUI klienta

**Status**: Částečně dokončeno

**Co funguje**:
- ✅ Základní připojení a zobrazení stavu
- ✅ Real-time updates přes WebSocket
- ✅ Dynamické scény
- ✅ Barevné indikátory připojení
- ✅ In-app notifikace

**Co zbývá otestovat**:
- ⏳ **Edge case: TUI reconnection** - Ověřit, že TUI se správně reconnectuje při ztrátě spojení s API
- ⏳ **Edge case: TUI error handling** - Ověřit graceful handling chyb (API nedostupné, neplatné response, atd.)
- ⏳ **Edge case: TUI při různých stavech** - Ověřit zobrazení při QUIT, RESTART, override stavech
- ⏳ **Edge case: TUI keybindings** - Ověřit všechny keybindings (q, t, atd.)

**Referenční testy**: `test_tui_*` (tests.md, řádek 331-435)

---

### 🔧 Task 16: End-to-end test a finální ladění

**Status**: Nezačato

**Co zbývá otestovat**:
- ⏳ **Kompletní E2E flow**: IDLE → GARAGE → RACE → REPLAY → QUIT → RESTART
- ⏳ **Edge case: Připojení/odpojení iRacing během běhu** - Ověřit graceful handling
- ⏳ **Edge case: Připojení/odpojení OBS během běhu** - Ověřit graceful handling
- ⏳ **Edge case: Override během normálního přepínání** - Ověřit prioritu
- ⏳ **Edge case: Vypnutí autoswitch během běhu** - Ověřit graceful handling
- ⏳ **Performance test**: Ověřit latenci přepínání scén
- ⏳ **Performance test**: Ověřit CPU a memory usage
- ⏳ **Doplňování testů**: Pro každý nalezený problém vytvořit unit test

**Referenční test**: Task 16 v plánu ladění

---

## Shrnutí podle priorit (aktualizováno)

### 🔴 Kritická priorita (teď)

1. **Task 15: Test TUI klienta - KOMPLETNÍ**
   - ⚠️ **TUI ještě nebylo testováno vůbec!**
   - Základní připojení a zobrazení stavu
   - Real-time updates přes WebSocket
   - Ovládání (keybindings, tlačítka)
   - Error handling a reconnection
   - Zobrazení všech stavů (QUIT, RESTART, override, streaming)

### 🟡 Vysoká priorita (po TUI)

2. **Task 16: Připojení/odpojení a performance testy**
   - Připojení/odpojení iRacing během běhu
   - Připojení/odpojení OBS během běhu
   - Performance testy (latenci, CPU, memory)

### 🟢 Odloženo

3. **Task 12: State machine edge cases** - Odloženo
4. **Task 13: OBS scene switching edge cases** - Chybějící scéna je zachycena při connectu, rychlé přepínání nehrozí
5. **Task 14: API edge cases** - Odloženo

---

## Doporučený postup

1. **🔴 TEĎ: Task 15 - Kompletní test TUI klienta**
   - Všechny manuální testy z tests.md
   - Ověření všech funkcí TUI
   - Edge cases a error handling

2. **🟡 DÁLE: Task 16 - Připojení/odpojení a performance**
   - Test připojení/odpojení během běhu
   - Performance měření

3. **⏸️ POZDĚJI: Rozšíření funkcionality** (uživatel popíše později)

---

## Poznámky

- Většina základní funkcionality funguje správně
- Zbývá hlavně otestovat edge cases a error handling
- End-to-end test je kritický pro ověření, že vše funguje společně
- Performance testy jsou důležité pro produkční použití
