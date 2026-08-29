/** HUD time formatters. Keep in sync with irswitch.iracing.sdk_units. */

export const HUD_PLACEHOLDER = "—";

function finiteNumber(value) {
  if (value == null || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n;
}

/** iRacing F3 / SimHub ``m:ss.fff``. Rejects SDK sentinels such as -1. */
export function fmtLapTime(seconds) {
  const n = finiteNumber(seconds);
  if (n == null || n < 0) return HUD_PLACEHOLDER;
  const totalMs = Math.round(n * 1000);
  if (totalMs < 0) return HUD_PLACEHOLDER;
  const minutes = Math.floor(totalMs / 60000);
  const rest = totalMs % 60000;
  const secs = Math.floor(rest / 1000);
  const millis = rest % 1000;
  return `${minutes}:${String(secs).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

/** Signed delta: ``+0.318`` / ``-0.418``. */
export function fmtDelta(seconds, digits = 3) {
  const n = finiteNumber(seconds);
  if (n == null) return HUD_PLACEHOLDER;
  const body = Math.abs(n).toFixed(digits);
  if (n < 0) return `-${body}`;
  return `+${body}`;
}

/** Battle interval: ``1.91 s``. */
export function fmtGap(seconds, digits = 2) {
  const n = finiteNumber(seconds);
  if (n == null) return HUD_PLACEHOLDER;
  return `${Math.abs(n).toFixed(digits)} s`;
}

/** SessionTime / remain as ``m:ss`` or ``h:mm:ss``. */
export function fmtSessionClock(seconds) {
  const n = finiteNumber(seconds);
  if (n == null || n < 0) return HUD_PLACEHOLDER;
  const total = Math.round(n);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}
