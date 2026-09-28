# Handover — VR perf agent (Win11)

Kontext pro Cursor agenta na racing PC (Windows 11). Komunikuj s uživatelem **česky**. Bez výslovného souhlasu **neměň** kód, INI ani grafiku.

Detail nástroje: [`tools/vr-perf/README.md`](README.md). PR: [#359](https://github.com/Buchtanen/ir-obs-switcher/pull/359).

## Cíl

Změřit, proč při plném poli před sebou padá FPS (~90 → ~70), a navrhnout **jednu** grafickou změnu najednou. Po schválení znovu změřit. Stabilní ~90 Hz ve field je priorita před vyšší kvalitou.

## Stav setupu

- Pico 4 + Virtual Desktop + OpenXR (**VDXR** — Runtime v overlay musí ukazovat VDXR)
- RTX 4090, render ~3120×3120, cíl **90 Hz**
- MSAA **4×** + Sharp filter (8× až když field drží ~90)
- Shadows High, cars 30/20, mirrors 3, HCI high detail
- Particles/foliage full, objects high (kromě pits)
- Foveated 40/40
- VD OK: H265+, 450 Mbit/s, latence 22–38 ms, ~10 ms/frame když hra stíhá
- Problém: full field ahead → FPS ~90 → ~70
- LibreHardwareMonitor k dispozici (+ HW overview / configs)

## Co NEdělat

- Neměnit irswitch product kód, neintegrovat collector, nepřidávat `/vr-status`
- Neměnit grafiku / config bez **explicitního** schválení uživatele
- Neskočit na MSAA 8×, dokud field nedrží ~90
- Neměnit více knoflíků najednou
- Nescrapovat VD overlay automaticky — ručně poznamenat do `--note` / reportu

## Prerekvizity

1. LibreHardwareMonitor běží; Options → **Remote Web Server** zapnutý
2. Default URL: `http://127.0.0.1:8085/data.json` (port ověř v LHM / README; jinak `--lhm-url`)
3. Sensoy CPU + GPU zapnuté
4. Volitelně: `pip install nvidia-ml-py irsdk`
5. VD performance overlay (oba sticky) — Runtime = **VDXR**
6. Repo / složka `tools\vr-perf` na tomto PC

## Postup stintu

1. Ověř LHM:
   ```powershell
   curl http://127.0.0.1:8085/data.json
   ```
   (nebo prohlížeč / Invoke-WebRequest). Pokud 404/connection refused → zapni Remote Web Server / zjisti port.
2. Spusť iRacing VR, připrav stint (solo → field).
3. Záznam (PowerShell):
   ```powershell
   cd tools\vr-perf
   python collect.py --out recordings\stint.jsonl --hz 90 --interval 0.5 --note solo --note-file recordings\note.txt
   ```
   Alternativa bez subcommandu je OK (`collect` je default). `--note` = sticky label; `--note-file` = live flip bez restartu.
4. Po pár kolech solo: `echo field > recordings\note.txt` a jeď plný pack před sebou.
5. Ctrl+C po stintu.
6. Summarize:
   ```powershell
   python collect.py summarize recordings\stint.jsonl --hz 90
   ```
7. Interpretuj výstup (níže). Doporuč **jeden** knoflík. Po schválení a změně → znovu měř.

Volitelně: `--renderer-ini "C:\Users\<you>\Documents\iRacing\renderer.ini"` snapshot klíčů na startu.

## Interpretační pravidla

| class / hint | Význam |
| --- | --- |
| `headroom` | FPS na cíli, GPU &lt; ~80 % → prostor pro SS/kvalitu |
| `ok` | Drží cíl, GPU pracuje |
| `fps_low` | Pod ~92 % target Hz |
| `gpu_bound` | GPU ≥ ~95 % při měkkém FPS → řezat stíny/auta/částice **před** MSAA 8× |

Srovnej `note=solo` vs `note=field`: `fps.p05`, `gpu_load.p95`, `bottleneck_hint`. VD latence / Runtime zapisuj ručně do reportu.

## Priorita ladění

Jedna změna → re-measure. Drž **3120** a **MSAA 4×**.

1. Shadows High → **Medium**
2. Cars detail **30/20** (snížit)
3. Mirrors **3 → 2**
4. Particles (snížit)
5. MSAA 8× / vyšší SS — **až** field drží ~90

## Kde jsou artefakty / jak odevzdat

Uživateli vždy vrať:

1. Cestu k JSONL (`recordings\….jsonl`)
2. Výstup `summarize` (JSON + `bottleneck_hint`)
3. Doporučený **jeden** další knoflík (nebo „držet, field OK“)
4. Krátké VD poznámky (Runtime, latence), pokud relevantní

Docs: no change mimo tento handover (nástroj je standalone, mimo irswitch produkt).
