# State Machine Redesign - Plán implementace

## Nové stavy

1. **CONNECTING** - čekání na připojení OBS a iRacing současně
   - Neprepina se nic
   - Nastavi se safe_scene
   - Pouziva se i pri lost connection

2. **LOADING** - po connecting do zobrazení iRacing lobby
   - Nic se neprepina
   - Detekce: iracing_mode is None (SessionTime empty)

3. **LOBBY** - po zobrazení lobby (místo IDLE)
   - Prepina se
   - Detekce: iracing_mode == IDLE a není loading

4. **GARAGE, RACE, REPLAY** - v pořádku, prepina se

5. **QUIT** - v pořádku
   - Po skončení streamu se nahodi safe scene
   - Padne do stavu CONNECTING

6. **RESTART** - v pořádku
   - Blokuje prepinani
   - Drzi svoji scenu
   - Ceka jako connecting pres LOADING a grace period na LOBBY
   - Kdy obnovi prepinani

## Flow

```
START → CONNECTING (safe_scene, no switch)
  ↓ (both connected)
LOADING (no switch)
  ↓ (iRacing lobby detected)
LOBBY (switch to lobby scene)
  ↓
GARAGE/RACE/REPLAY (switch)
  ↓
QUIT (switch to quit scene, then safe_scene after stream stop) → CONNECTING

RESTART: QUIT + hotkey → RESTART (no switch, keep scene)
  ↓ (through LOADING)
  ↓ (grace period)
LOBBY (resume switching)
```

## Implementace

1. Přidat stavy do DrivingMode enum ✅
2. Upravit state machine tick() pro novou logiku
3. Upravit main loop pro správné přechody
4. Přidat reset endpoint
5. Opravit zobrazení session info v GR dashboard
