# Buchtanen iRacer - overlay assets

1920 x 1080 target, transparent. No visible text, numbers or units are embedded. State-sensitive SVG layers use `currentColor`.

| File | viewBox / pixels |
|---|---|
| `battle_background.svg` | `420 x 140` |
| `battle_frame.svg` | `420 x 140` |
| `battle_glow.png` | `840 x 280` |
| `battle_target_icon.svg` | `72 x 72` |
| `battle_pressure_icon.svg` | `72 x 72` |
| `battle_corner_caps.svg` | `420 x 140` |
| `battle_radar_rings.svg` | `116 x 116` |
| `lap_background.svg` | `380 x 112` |
| `lap_frame.svg` | `380 x 112` |
| `lap_flag_icon.svg` | `64 x 64` |
| `lap_stopwatch_icon.svg` | `64 x 64` |
| `alert_banner.svg` | `380 x 84` |
| `position_banner.svg` | `380 x 96` |
| `chevron_up.svg` | `64 x 64` |
| `chevron_down.svg` | `64 x 64` |
| `session_background.svg` | `520 x 126` |
| `final_lap_flag.svg` | `80 x 80` |
| `finish_flag.svg` | `96 x 80` |
| `bio_compact_plate.svg` | `240 x 64` |
| `bio_expanded_plate.svg` | `280 x 118` |
| `heart_icon.svg` | `56 x 56` |
| `ble_icon.svg` | `48 x 48` |
| `bio_pulse_trace.svg` | `220 x 52` |
| `bio_accent.svg` | `280 x 118` |
| `sysinfo_background.svg` | `1920 x 72` |
| `sysinfo_module_segment.svg` | `150 x 72` |
| `sysinfo_dividers.svg` | `1920 x 72` |
| `cpu_icon.svg` | `48 x 48` |
| `gpu_icon.svg` | `48 x 48` |
| `ram_icon.svg` | `48 x 48` |
| `temp_icon.svg` | `48 x 48` |
| `power_icon.svg` | `48 x 48` |
| `fps_icon.svg` | `48 x 48` |
| `accent_slash.svg` | `128 x 64` |
| `scan_line.svg` | `320 x 48` |
| `thin_divider.svg` | `320 x 32` |
| `wireframe_fragment.svg` | `220 x 88` |

Layering: background -> frame -> accent -> icon -> micro detail -> glow -> reveal/mask -> HTML.

SYSINFO is 72 px high; its first 230 px (12%) are an empty branding zone.

QA: 3 themes x 37 files; names, alpha, SVG text ban and geometry parity verified.
