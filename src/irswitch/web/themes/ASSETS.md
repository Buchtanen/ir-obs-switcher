# Buchtanen iRacer - overlay assets

1920 x 1080 target, transparent PNG layers at exact widget pixels. No production asset contains text or numbers. Icons, dividers, corners, radar rings, pulse traces and accent fragments are white alpha masks for CSS `mask-image` / `currentColor`. Background and frame PNGs are normal images, never masks. Exception: `final_lap_flag.png` is a painted solid white flag (not a mask) so last-lap stays white; `finish_flag.png` is the checkered mask used only after the race ends.

Do not load `previews/` in the overlay.

| File | pixels |
|---|---|
| `battle_background.png` | `420 x 140` |
| `battle_frame.png` | `420 x 140` |
| `battle_glow.png` | `420 x 140` |
| `battle_target_icon.png` | `72 x 72` |
| `battle_pressure_icon.png` | `72 x 72` |
| `battle_corner_caps.png` | `420 x 140` |
| `battle_radar_rings.png` | `116 x 116` |
| `lap_background.png` | `380 x 112` |
| `lap_frame.png` | `380 x 112` |
| `lap_flag_icon.png` | `64 x 64` |
| `lap_stopwatch_icon.png` | `64 x 64` |
| `alert_banner.png` | `380 x 84` |
| `position_banner.png` | `380 x 96` |
| `chevron_up.png` | `64 x 64` |
| `chevron_down.png` | `64 x 64` |
| `session_background.png` | `520 x 126` |
| `final_lap_flag.png` | `80 x 80` | solid white cloth; painted, not masked |
| `finish_flag.png` | `96 x 80` | checkered mask; FINISH only |
| `bio_compact_plate.png` | `240 x 64` |
| `bio_expanded_plate.png` | `280 x 118` |
| `heart_icon.png` | `56 x 56` |
| `ble_icon.png` | `48 x 48` |
| `bio_pulse_trace.png` | `220 x 52` |
| `bio_accent.png` | `280 x 118` |
| `sysinfo_background.png` | `1920 x 72` |
| `sysinfo_module_segment.png` | `150 x 72` |
| `sysinfo_dividers.png` | `1920 x 72` |
| `cpu_icon.png` | `48 x 48` |
| `gpu_icon.png` | `48 x 48` |
| `ram_icon.png` | `48 x 48` |
| `temp_icon.png` | `48 x 48` |
| `power_icon.png` | `48 x 48` |
| `fps_icon.png` | `48 x 48` |
| `accent_slash.png` | `128 x 64` |
| `scan_line.png` | `320 x 48` |
| `thin_divider.png` | `320 x 32` |
| `wireframe_fragment.png` | `220 x 88` |

## Animations (optional VP9 alpha WebM)

| File | pixels | playback |
|---|---|---|
| `battle_radar_loop.webm` | `116 x 116` | loop while HUNTING is active |
| `battle_scan_enter.webm` | `420 x 140` | once on battle ENTER |
| `finish_accent_sweep.webm` | `520 x 126` | once on FINISH ENTER |

WebM does not replace the 320 ms / 280 ms widget enter/exit transitions. Missing file = CSS/PNG fallback.

Layering: background -> frame -> accent -> icon -> micro detail -> glow -> HTML. SYSINFO grid is unchanged: `230px + 11×150px`.

The pack ships one glow PNG (`battle_glow.png`). Overlay stretches it onto lap / PB / session / bio / alert / position plates and adds a CSS `drop-shadow` so those widgets still read a local halo. Compact BPM reuses the same glow slot.

QA: 3 themes × 37 PNG + 3 WebM; names, alpha, geometry parity verified.
