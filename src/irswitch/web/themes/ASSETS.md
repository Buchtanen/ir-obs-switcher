# Buchtanen iRacer - overlay assets

1920 x 1080 target, transparent PNG layers at exact widget pixels. No production asset contains text or numbers. Icons, dividers, corners, radar rings, pulse traces and accent fragments are white alpha masks for CSS `mask-image` / `currentColor`. Background and frame PNGs are normal images, never masks. Exception: `final_lap_flag.png` is a painted solid white flag (not a mask) so last-lap stays white; `finish_flag.png` is the checkered mask used only after the race ends.

Battle is golden-master V3: every battle layer is a full 420×140 canvas. Layer order and tinting: [V3_INTEGRATION.md](V3_INTEGRATION.md). Do not load `previews/` or MP4 review clips in the overlay.

| File | pixels |
|---|---|
| `battle_shadow.png` | `420 x 140` |
| `battle_base_plate.png` | `420 x 140` |
| `battle_material.png` | `420 x 140` |
| `battle_tech_diagram.png` | `420 x 140` |
| `battle_frame_base.png` | `420 x 140` |
| `battle_frame_highlight.png` | `420 x 140` |
| `battle_state_accent_mask.png` | `420 x 140` |
| `battle_corner_left.png` | `420 x 140` |
| `battle_corner_right.png` | `420 x 140` |
| `battle_icon_well.png` | `420 x 140` |
| `battle_radar_ticks.png` | `420 x 140` |
| `battle_radar_ring_inner.png` | `420 x 140` |
| `battle_radar_ring_outer.png` | `420 x 140` |
| `battle_target_icon.png` | `420 x 140` |
| `battle_pressure_icon.png` | `420 x 140` |
| `battle_micro_details.png` | `420 x 140` |
| `battle_scan_mask.png` | `420 x 140` |
| `battle_glow_cyan.png` | `420 x 140` |
| `battle_glow_amber.png` | `420 x 140` |
| `battle_glow_red.png` | `420 x 140` |
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
| `battle_scan_enter.webm` | `420 x 140` | once on battle ENTER |
| `battle_signal_lock.webm` | `420 x 140` | radar acquisition; may retrigger while HUNTING |
| `battle_theme_motion.webm` | `420 x 140` | once on ENTER; cyber `data_slice`, stealth `edge_pulse`, night `line_tear` |
| `finish_accent_sweep.webm` | `520 x 126` | once on FINISH ENTER |

WebM does not replace the 320 ms / 280 ms widget enter/exit transitions. Missing file = CSS/PNG fallback.

Layering (battle V3): shadow → base plate → material → tech diagram → frame → highlight → state accent → corners → icon well → radar → icon → micro → HTML → motion → local glow. Other widgets still use V2 plates until Phase B. SYSINFO grid is unchanged: `230px + 11×150px`.

HUNTING uses `battle_glow_cyan`; HUNTED uses `battle_glow_amber`. Battle glow is alpha-composited (not `mix-blend-mode: screen`). Lap/session/bio reuse those pre-colored glows. Never `filter: drop-shadow` on the plate PNG (it halos internal alpha).

Text slots (battle): title 26px italic at y≈42, kicker 13px at y≈76, meta 11px muted at y≈96, copy pad 119px. Radar rings stay static; `battle_signal_lock.webm` may retrigger while HUNTING (1.4s, stealth 1.8s).

QA: 3 themes × 50 PNG + 4 WebM; names, alpha, geometry parity verified. Preview MP4/PNG boards stay out of the web tree.
