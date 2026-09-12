# VR perf collector (standalone)

Offline sampler for **Windows + iRacing VR** tuning (Pico / Virtual Desktop / OpenXR).

**Not part of irswitch.** No HTTP API, no `/vr-status`, no overlay wiring.
Copy this folder to the racing PC (or keep it beside the repo) and run it while you drive.

## What it collects

| Source | Metrics |
| --- | --- |
| LibreHardwareMonitor HTTP (`/data.json`) | GPU/CPU load, temp, power, clocks, VRAM |
| NVIDIA NVML (optional `nvidia-ml-py`) | GPU util/temp/power/VRAM if LHM GPU is sparse |
| iRacing SDK (optional `irsdk`) | `FrameRate`, frametime, rough active-car count |
| Manual `--note` / `--note-file` | Tag segments (`solo`, `field`, `pits`) |

Virtual Desktop overlay stats are **not** scraped. Log them by hand in `--note` if needed.

## Prerequisites (Win11)

1. LibreHardwareMonitor running  
2. Options → **Remote Web Server** enabled (default `http://127.0.0.1:8085/data.json`)  
3. Sensors for **CPU** + **GPU** enabled  
4. Optional: `pip install nvidia-ml-py irsdk`  

## Usage

```powershell
cd tools\vr-perf

# record (Ctrl+C to stop)
python collect.py --out recordings\stint.jsonl --hz 90 --interval 0.5 --note solo

# live note flips without restart (other terminal / hotkey):
#   set --note-file recordings\note.txt
#   then: echo field > recordings\note.txt

# after the stint
python collect.py summarize recordings\stint.jsonl --hz 90
```

Optional: `--renderer-ini "C:\Users\<you>\Documents\iRacing\renderer.ini"` snapshots key graphics lines once at start.

## How to read the summary

- **headroom** — FPS on target and GPU &lt; ~80% → room for SS / quality  
- **ok** — holding target, GPU working  
- **fps_low** — under ~92% of target Hz  
- **gpu_bound** — GPU ≥ ~95% while FPS soft → cut shadows / cars / particles before MSAA 8×  

Typical workflow (4090, 3120², MSAA 4×, shadows high, cars 30/20):

1. Lap alone (`note=solo`)  
2. Pack traffic (`note=field`)  
3. Compare `gpu_load.p95` + `fps.p05` between notes  
4. Change **one** graphics knob, repeat  

## Tests

```powershell
cd tools\vr-perf
python -m unittest test_headroom.py -v
```

(Headroom helpers are pure stdlib — safe to run on Linux CI too; live LHM/iRacing sampling is Windows-oriented.)

## Output

JSONL lines (`type=meta` once, then `type=sample`). No secrets; renderer paths only if you pass `--renderer-ini`.
