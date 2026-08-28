# Integration notes

## Layer order

Use `composition_manifest.json`; all production layers use the same 420x140 canvas, so no per-layer scaling or offset is needed.

1. shadow
2. base plate
3. material
4. technical diagram
5. structural frame
6. specular frame highlight
7. state accent mask
8. corner caps
9. icon well
10. radar ticks and rings
11. state icon
12. micro details
13. dynamic HTML text
14. motion effects
15. local pre-colored glow

Mask layers are white RGBA PNGs. Tint them with CSS mask-image or the overlay's existing mask renderer. Use cyan for HUNTING and amber for HUNTED. Keep red for explicit critical states.

## Motion files

- `battle_scan_enter.webm`: one-shot during ENTER.
- `battle_signal_lock.webm`: one-shot radar acquisition.
- cyber_racing `battle_data_slice.webm`: short technical slice glitch.
- stealth_graphite `battle_edge_pulse.webm`: restrained highlight pulse.
- night_attack `battle_line_tear.webm`: controlled pressure/alert tear.

Do not loop scan, data slice or line tear. Radar may repeat only while a battle is active and should be rate-limited by the integration.

## Text slots

- title: x 119-384, baseline around y 42-68
- state/subtitle: x 120-384, y 74-89
- meta: x 120-384, y 94-110

Dynamic text remains HTML. The preview font is illustrative only.
