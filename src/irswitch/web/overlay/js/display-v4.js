/** V4 overlay renderer (S1: timing + battle + position families). */

import { fmtBpmDelta, fmtDelta, fmtGap, fmtLapTime, fmtRate } from "./timing-format.js";

const ASSET_BASE = "/overlay/web/";
/** Bust browser cache for theme PNGs when wells/icons change. */
const ASSET_CACHE = "1.2.17";
const DEFAULT_HOLD_MS = 4000;
const FAMILY_CAPS = { battle: 2, timing: 1, position: 1, exception: 1, pit: 1, bio: 1, session: 1 };

const ENTER_MOTIONS = ["enter_reveal", "theme_glitch"];
const REDUCED_MOTION_SKIP = new Set([
  "theme_glitch",
  "result_burst",
  "exception_link_drop",
  "session_finish_burst",
]);
const FAMILY_RESULT_MOTION = {
  timing: "timing_projection_sweep",
  position: "position_chevron_hit",
  pit: "pit_stop_ring",
  bio: "bio_pulse",
  session: "session_finish_burst",
  exception: "exception_link_drop",
};

const TRANSIENT_FAMILIES = new Set([
  "battle",
  "timing",
  "position",
  "exception",
  "pit",
  "bio",
  "session",
]);

/** Last-resort canvas sizes when manifest/aliases are missing or invalid. */
const DEFAULT_CANVAS = {
  transient: [420, 140],
  sysinfo: [1920, 72],
};

let manifest = null;
let catalog = null;
let theme = "cyber_racing";
let language = "en";
let copyCatalog = {};
let resolvedMotions = {};
let resolvedStates = {};
let motionDisabled = false;
let lastSequence = new Map();

function text(el, value) {
  if (!el) return;
  el.textContent = value == null ? "—" : String(value);
}

function fmt(n, digits) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

/** Whole-number BPM for HUD (never show sensor floats). */
function fmtBpm(bpm) {
  if (bpm == null || bpm === "") return "";
  const n = Number(bpm);
  if (!Number.isFinite(n)) return "";
  return String(Math.round(n));
}

function fmtPositionDelta(delta) {
  if (delta == null || Number.isNaN(delta)) return "—";
  const n = Number(delta);
  if (n > 0) return `+${n} POS`;
  if (n < 0) return `${n} POS`;
  return "0 POS";
}

function fmtPositionRange(oldPos, newPos) {
  if (oldPos == null || newPos == null) return "—";
  return `P${oldPos} → P${newPos}`;
}

/** Last-resort labels when snapshot/i18n catalog is stale (OBS CEF cache). */
const FALLBACK_COPY = {
  "exception.incident": "INCIDENT",
  "exception.invalid_lap": "INVALID LAP",
  "exception.link_drop": "LINK DROP",
  incident: "INCIDENT",
  invalid_lap: "INVALID LAP",
  "battle.battle_for_position": "BATTLE FOR POSITION",
  "position.rival_threat": "RIVAL THREAT",
};

function labelForToken(token) {
  if (!token) return "";
  return copyCatalog[token] || FALLBACK_COPY[token] || "";
}

function resolveCopy(token) {
  if (!token) return "";
  return labelForToken(token);
}

/** Prefer catalog label; never show unknown token when sample title exists. */
function resolveHeadline(token, sampleTitle, stateKey) {
  const labeled = labelForToken(token);
  if (labeled) return labeled;
  return sampleTitle || stateKey || token || "";
}

function prefersReducedMotion() {
  return (
    motionDisabled ||
    (typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches)
  );
}

function motionUrl(name) {
  const rel = resolvedMotions[name];
  if (rel) return ASSET_BASE + rel;
  return manifestDiskPath(`themes/${theme}/motion/${name}.webm`);
}

function ensureFxVideo(art, className, url, loop) {
  if (!url) {
    const existing = art.querySelector(`video.${className}`);
    if (existing) {
      existing.pause();
      existing.remove();
    }
    return null;
  }
  let video = art.querySelector(`video.${className}`);
  if (!video) {
    video = document.createElement("video");
    video.className = `layer fx ${className}`;
    video.muted = true;
    video.defaultMuted = true;
    video.playsInline = true;
    video.setAttribute("muted", "");
    video.setAttribute("playsinline", "");
    art.appendChild(video);
  }
  if (video.dataset.src !== url) {
    video.dataset.src = url;
    video.src = url;
  }
  video.loop = Boolean(loop);
  return video;
}

function playOnceFromStart(video) {
  if (!video) return;
  video.currentTime = 0;
  const playPromise = video.play();
  if (playPromise?.catch) playPromise.catch(() => {});
}

function isGoldenSnapshot(node) {
  return (
    document.documentElement.classList.contains("golden-layout") ||
    document.documentElement.classList.contains("golden-gallery") ||
    Boolean(node?.closest?.(".golden-stage"))
  );
}

function syncWidgetMotion(node, envelope, familyName, created) {
  if (prefersReducedMotion() || isGoldenSnapshot(node)) return;
  const art = node.querySelector(".v4-art");
  if (!art) return;
  if (document.documentElement.classList.contains("preview-layout")) return;

  const phase = String(envelope.phase || "RESULT").toUpperCase();
  const isEnter = created || phase === "ENTER";

  if (isEnter) {
    for (const name of ENTER_MOTIONS) {
      if (REDUCED_MOTION_SKIP.has(name) && prefersReducedMotion()) continue;
      playOnceFromStart(ensureFxVideo(art, `motion-${name}`, motionUrl(name), false));
    }
  }

  if (phase === "ACTIVE" && familyName === "battle") {
    playOnceFromStart(
      ensureFxVideo(art, "motion-battle_signal_lock", motionUrl("battle_signal_lock"), false),
    );
  }

  if (phase === "RESULT") {
    if (!REDUCED_MOTION_SKIP.has("result_burst") || !prefersReducedMotion()) {
      playOnceFromStart(
        ensureFxVideo(art, "motion-result_burst", motionUrl("result_burst"), false),
      );
    }
    const familyMotion = FAMILY_RESULT_MOTION[familyName];
    if (familyMotion && !(REDUCED_MOTION_SKIP.has(familyMotion) && prefersReducedMotion())) {
      playOnceFromStart(
        ensureFxVideo(art, `motion-${familyMotion}`, motionUrl(familyMotion), false),
      );
    }
  }

  if (phase === "EXIT") {
    playOnceFromStart(ensureFxVideo(art, "motion-exit_trace", motionUrl("exit_trace"), false));
  }
}

function manifestDiskPath(rel) {
  const themed = rel.replace(/^themes\/[^/]+/, `themes-v4/${theme}`);
  let path;
  if (themed.startsWith("themes/")) {
    path = ASSET_BASE + themed.replace(/^themes\//, "themes-v4/");
  } else {
    path = ASSET_BASE + themed;
  }
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}v=${ASSET_CACHE}`;
}

function familyForState(stateKey) {
  const meta = manifest?.states?.[stateKey];
  if (meta?.family) return meta.family;
  const entry = Object.values(catalog?.entries || {}).find((row) => row.state === stateKey);
  return entry?.family || "timing";
}

function resolveStateKey(envelope) {
  const variant = envelope.presentation?.variant;
  if (variant && manifest?.states?.[variant]) return variant;
  const eventType = String(envelope.eventType || "").toUpperCase();
  const entry = catalog?.entries?.[eventType];
  if (entry?.state) return entry.state;
  const fallback = catalog?.fallbacks?.[eventType];
  if (fallback) return fallback;
  return variant || eventType.toLowerCase();
}

function layerRootForFamily(familyName) {
  const family = manifest?.themes?.[theme]?.families?.[familyName];
  const zone = String(family?.zone || (familyName === "battle" ? "battle" : "event")).toLowerCase();
  if (zone === "battle") return ensureLayer("v4-battle-stack");
  return ensureLayer("v4-event-layer");
}

function isPositiveIntPair(value) {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    Number.isInteger(value[0]) &&
    Number.isInteger(value[1]) &&
    value[0] > 0 &&
    value[1] > 0
  );
}

/** Read order: theme canvases override → root canvases → legacy alias → DEFAULT. */
function resolveThemeCanvas(canvasId) {
  const root = manifest?.canvases?.[canvasId] || {};
  const override = manifest?.themes?.[theme]?.canvases?.[canvasId] || {};
  return { ...root, ...override };
}

function canvasSize(canvasId) {
  const cfg = resolveThemeCanvas(canvasId);
  if (isPositiveIntPair(cfg.size)) return [cfg.size[0], cfg.size[1]];
  if (canvasId === "transient" && isPositiveIntPair(manifest?.transient_canvas)) {
    return [manifest.transient_canvas[0], manifest.transient_canvas[1]];
  }
  if (canvasId === "sysinfo" && isPositiveIntPair(manifest?.sysinfo_canvas)) {
    return [manifest.sysinfo_canvas[0], manifest.sysinfo_canvas[1]];
  }
  return DEFAULT_CANVAS[canvasId] || DEFAULT_CANVAS.transient;
}

function setPxVar(root, name, value, fallback) {
  const n = Number(value);
  const px = Number.isFinite(n) ? n : fallback;
  root.style.setProperty(name, `${px}px`);
}

function applyThemeTextAndIconVars(root, cfg) {
  const safe = cfg.safe_box || {};
  setPxVar(root, "--v4-safe-l", safe.left, 119);
  setPxVar(root, "--v4-safe-t", safe.top, 14);
  setPxVar(root, "--v4-safe-r", safe.right, 16);
  setPxVar(root, "--v4-safe-b", safe.bottom, 10);

  const slots = cfg.text_slots || {};
  const title = slots.title || {};
  const subtitle = slots.subtitle || {};
  const value = slots.value || {};
  const meta = slots.meta || {};
  setPxVar(root, "--v4-title-x", title.left, 119);
  setPxVar(root, "--v4-title-y", title.top, 38);
  setPxVar(root, "--v4-subtitle-x", subtitle.left, 120);
  setPxVar(root, "--v4-subtitle-y", subtitle.top, 62);
  setPxVar(root, "--v4-value-x", value.left, 120);
  setPxVar(root, "--v4-value-y", value.top, 80);
  setPxVar(root, "--v4-meta-x", meta.left, 120);
  setPxVar(root, "--v4-meta-y", meta.top, 112);

  if (cfg.icon_mode === "glyph" && Array.isArray(cfg.icon_box) && cfg.icon_box.length === 4) {
    const [x, y, w, h] = cfg.icon_box;
    setPxVar(root, "--v4-icon-x", x, 0);
    setPxVar(root, "--v4-icon-y", y, 0);
    setPxVar(root, "--v4-icon-w", w, 64);
    setPxVar(root, "--v4-icon-h", h, 64);
    root.dataset.v4IconMode = "glyph";
  } else {
    root.dataset.v4IconMode = "full_canvas";
  }
}

function applyManifestGeometry(target) {
  if (typeof document === "undefined") return;
  const root = target || document.documentElement;
  const [tw, th] = canvasSize("transient");
  const [sw, sh] = canvasSize("sysinfo");
  root.style.setProperty("--v4-canvas-w", `${tw}px`);
  root.style.setProperty("--v4-canvas-h", `${th}px`);
  root.style.setProperty("--v4-sysinfo-w", `${sw}px`);
  root.style.setProperty("--v4-sysinfo-h", `${sh}px`);
  root.style.setProperty("--v4-gallery-col", `${tw}px`);

  applyThemeTextAndIconVars(root, resolveThemeCanvas("transient"));

  const battle = manifest?.zones?.battle || {};
  const event = manifest?.zones?.event || {};
  const battleOffset = Array.isArray(battle.offset) ? battle.offset : [36, 19];
  const eventOffset = Array.isArray(event.offset) ? event.offset : [48, 19];
  const sysH = sh;
  const battleY = sysH + (Number(battleOffset[1]) || 19);
  const eventY = sysH + (Number(eventOffset[1]) || 19);
  root.style.setProperty("--v4-zone-battle-x", `${Number(battleOffset[0]) || 36}px`);
  root.style.setProperty("--v4-zone-battle-y", `${battleY}px`);
  root.style.setProperty("--v4-zone-battle-gap", `${Number(battle.gap) || 10}px`);
  root.style.setProperty("--v4-zone-event-x", `${Number(eventOffset[0]) || 48}px`);
  root.style.setProperty("--v4-zone-event-y", `${eventY}px`);
  root.style.setProperty("--v4-zone-event-gap", `${Number(event.gap) || 10}px`);

  // Eager zone containers (existing ids) so geometry vars apply before first event.
  ensureLayer("v4-battle-stack");
  ensureLayer("v4-event-layer");
}

function applyIconMode(iconEl) {
  if (!iconEl) return;
  const mode = resolveThemeCanvas("transient").icon_mode || "full_canvas";
  iconEl.classList.toggle("mode-glyph", mode === "glyph");
  iconEl.classList.toggle("mode-full-canvas", mode !== "glyph");
}

function isStale(envelope) {
  const cid = envelope.correlationId || envelope.storyKey || envelope.eventId;
  if (!cid) return false;
  const seq = Number(envelope.sequence || 0);
  const prev = lastSequence.get(cid) || 0;
  if (seq <= prev && envelope.phase !== "EXIT") return true;
  lastSequence.set(cid, Math.max(prev, seq));
  return false;
}

function paintLayer(el, url, { mask = false, canvas = null } = {}) {
  if (!el || !url) {
    el?.classList.add("empty");
    return;
  }
  el.classList.remove("empty");
  // Prefer CSS vars on the widget/zone. Only pin inline size for explicit canvases
  // (e.g. SYSINFO) that differ from the transient defaults.
  const explicit = isPositiveIntPair(canvas);
  const size = explicit ? `${canvas[0]}px ${canvas[1]}px` : "";
  if (mask) {
    el.style.backgroundImage = "";
    el.style.backgroundColor = "currentColor";
    const maskUrl = `url("${url}")`;
    el.style.webkitMaskImage = maskUrl;
    el.style.maskImage = maskUrl;
    if (explicit) {
      el.style.webkitMaskSize = size;
      el.style.maskSize = size;
      el.style.webkitMaskRepeat = "no-repeat";
      el.style.maskRepeat = "no-repeat";
      el.style.webkitMaskPosition = "0 0";
      el.style.maskPosition = "0 0";
    } else {
      el.style.webkitMaskSize = "";
      el.style.maskSize = "";
      el.style.webkitMaskRepeat = "";
      el.style.maskRepeat = "";
      el.style.webkitMaskPosition = "";
      el.style.maskPosition = "";
    }
  } else {
    el.style.backgroundColor = "";
    el.style.backgroundImage = `url("${url}")`;
    el.style.backgroundSize = size;
    el.style.backgroundPosition = size ? "0 0" : "";
    el.style.webkitMaskImage = "";
    el.style.maskImage = "";
  }
}

/** Resolve plate layer_dir, honoring per-state pack template overrides. */
function familyLayerDir(family, stateKey) {
  if (!family) return "";
  const overrides = family.state_layer_dirs || {};
  const override = stateKey && overrides[stateKey];
  return override || family.layer_dir || "";
}

function clearPlateMask(el) {
  if (!el) return;
  el.style.removeProperty("-webkit-mask-image");
  el.style.removeProperty("mask-image");
  el.style.removeProperty("-webkit-mask-size");
  el.style.removeProperty("mask-size");
  el.style.removeProperty("mask-mode");
  el.style.removeProperty("mask-composite");
  el.style.removeProperty("-webkit-mask-composite");
  el.classList.remove("has-plate-mask");
}

/** Clip .v4-art to the chamfered plate. Union base_plate + material: Light packs
 *  ship base_plate as a hollow rim, so masking with it alone clips the glass fill. */
function paintPlateMask(el, family, stateKey) {
  const layerDir = familyLayerDir(family, stateKey);
  if (!el || !layerDir) {
    clearPlateMask(el);
    return;
  }
  const files = ["base_plate.png"];
  if ((family.layers || []).some((layer) => layer.file === "material.png")) {
    files.push("material.png");
  }
  const urls = files.map((file) => manifestDiskPath(`${layerDir}/${file}`)).filter(Boolean);
  if (!urls.length) {
    clearPlateMask(el);
    return;
  }
  const mask = urls.map((url) => `url("${url}")`).join(", ");
  // Prefer setProperty — plain style.maskImage was computing to none in Chromium.
  el.style.setProperty("-webkit-mask-image", mask);
  el.style.setProperty("mask-image", mask);
  el.style.setProperty("mask-mode", "alpha");
  el.style.setProperty("mask-composite", "add");
  el.style.setProperty("-webkit-mask-composite", "source-over");
  el.style.removeProperty("-webkit-mask-size");
  el.style.removeProperty("mask-size");
  el.style.setProperty("-webkit-mask-repeat", "no-repeat");
  el.style.setProperty("mask-repeat", "no-repeat");
  el.style.setProperty("-webkit-mask-position", "0 0");
  el.style.setProperty("mask-position", "0 0");
  el.classList.add("has-plate-mask");
}

const SYSINFO_ICON_SLOTS = {
  cpu_icon: "cpu.png",
  gpu_icon: "gpu.png",
  temp_icon: "temp.png",
  power_icon: "power.png",
  ram_icon: "ram.png",
  fps_icon: "fps.png",
  heart_icon: "heart.png",
};

function sysinfoCanvas() {
  return canvasSize("sysinfo");
}

function sysinfoFamily() {
  return manifest?.themes?.[theme]?.families?.sysinfo;
}

function paintSysinfoIcon(el, url) {
  if (!el || !url) {
    el?.classList.add("empty");
    el.style.webkitMaskImage = "";
    el.style.maskImage = "";
    return;
  }
  el.classList.remove("empty");
  el.style.backgroundImage = "";
  el.style.backgroundColor = "currentColor";
  const maskUrl = `url("${url}")`;
  el.style.webkitMaskImage = maskUrl;
  el.style.maskImage = maskUrl;
  el.style.webkitMaskSize = "contain";
  el.style.maskSize = "contain";
  el.style.webkitMaskRepeat = "no-repeat";
  el.style.maskRepeat = "no-repeat";
  el.style.webkitMaskPosition = "center";
  el.style.maskPosition = "center";
}

export function syncSysinfoGlow(widget = document.getElementById("sysinfo-widget")) {
  if (!widget?.classList.contains("v4-sysinfo")) return;
  let tone = "normal";
  if (widget.querySelector(".sys-mod.crit")) tone = "critical";
  else if (widget.querySelector(".sys-mod.warn")) tone = "warn";
  widget.dataset.glow = tone;
}

function renderSysinfoIcons(family) {
  document.querySelectorAll("#sysinfo-widget .sys-icon[data-slot]").forEach((el) => {
    const iconFile = SYSINFO_ICON_SLOTS[el.dataset.slot];
    if (!iconFile) return;
    const url = manifestDiskPath(`${family.icon_dir}/${iconFile}`);
    paintSysinfoIcon(el, url);
  });
}

export function renderSysinfo() {
  const widget = document.getElementById("sysinfo-widget");
  if (!widget) return;
  const family = sysinfoFamily();
  const art = widget.querySelector(".sysinfo-art");
  if (!art || !family?.layers?.length) {
    widget.classList.remove("v4-sysinfo", "has-art");
    widget.classList.add("fallback");
    return;
  }
  widget.classList.remove("fallback");
  widget.classList.add("v4-sysinfo", "has-art");
  const canvas = sysinfoCanvas();
  art.replaceChildren();
  (family.layers || []).forEach((layer, index) => {
    const el = document.createElement("div");
    el.className = `layer ${layer.mode === "mask" ? "mask" : "image"}`;
    if (layer.file.includes("dividers")) el.classList.add("dividers");
    const glowMatch = /^sysinfo_glow_(.+)\.png$/.exec(layer.file);
    if (glowMatch) {
      el.classList.add("glow");
      el.dataset.glow = glowMatch[1];
    }
    el.dataset.index = String(index);
    const url = manifestDiskPath(`${family.layer_dir}/${layer.file}`);
    paintLayer(el, url, { mask: layer.mode === "mask", canvas });
    art.appendChild(el);
  });
  renderSysinfoIcons(family);
  syncSysinfoGlow(widget);
}

export function initV4Sysinfo() {
  renderSysinfo();
}

function ensureLayer(id) {
  let layer = document.getElementById(id);
  if (!layer) {
    layer = document.createElement("div");
    layer.id = id;
    document.body.appendChild(layer);
  }
  return layer;
}

function rebuildArt(node, stateKey, familyName) {
  const art = node.querySelector(".v4-art");
  if (!art) return;
  art.replaceChildren();
  const family = manifest?.themes?.[theme]?.families?.[familyName];
  if (!family) {
    node.classList.add("fallback");
    art.style.webkitMaskImage = "";
    art.style.maskImage = "";
    return;
  }
  node.classList.remove("fallback");
  const layerDir = familyLayerDir(family, stateKey);
  (family.layers || []).forEach((layer, index) => {
    const glowMatch = /^glow_(cyan|amber|red)\.png$/.exec(layer.file);
    // Soft bloom PNGs bleed past the chamfer unless perfectly plate-masked.
    // Skip them (golden + live); enter WebM stays, clipped by art plate mask.
    if (glowMatch) return;
    const url = manifestDiskPath(`${layerDir}/${layer.file}`);
    if (!url) return;
    const el = document.createElement("div");
    el.className = `layer ${layer.mode === "mask" ? "mask" : "image"}`;
    el.dataset.index = String(index);
    paintLayer(el, url, { mask: layer.mode === "mask" });
    art.appendChild(el);
  });
  const icon = document.createElement("div");
  icon.className = "icon";
  applyIconMode(icon);
  const iconUrl = manifestDiskPath(`${family.icon_dir}/${stateKey}.png`);
  paintLayer(icon, iconUrl);
  art.appendChild(icon);
  // Clip enter WebM / residual bloom to the chamfered plate (not the CSS box).
  paintPlateMask(art, family, stateKey);
}

function resolveTargetName(metrics, envelope) {
  const fromMetrics = metrics && metrics.targetName;
  if (fromMetrics) return String(fromMetrics);
  const fromTarget = envelope && envelope.target && (envelope.target.displayName || envelope.target.display_name);
  if (fromTarget) return String(fromTarget);
  return "";
}

function fillBattleCopy(node, envelope, stateKey, sample, metrics, copy) {
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const headline = resolveHeadline(copy.headlineToken, sample.title, stateKey);
  text(title, headline);
  if (stateKey === "hunting") {
    text(subtitle, resolveCopy("battle.closing_in") || sample.subtitle || "CLOSING IN");
    text(value, fmtGap(metrics.gap));
    const huntName = resolveTargetName(metrics, envelope);
    text(
      meta,
      huntName
        ? huntName
        : metrics.targetPosition != null
          ? `P${metrics.targetPosition} · target`
          : sample.meta,
    );
  } else if (stateKey === "hunted") {
    text(subtitle, sample.subtitle || resolveCopy("battle.hunted") || "UNDER PRESSURE");
    text(value, fmtGap(metrics.gap));
    const huntedName = resolveTargetName(metrics, envelope);
    text(
      meta,
      huntedName
        ? huntedName
        : metrics.targetPosition != null
          ? `P${metrics.targetPosition} behind`
          : sample.meta,
    );
  } else if (stateKey === "approach") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "BATTLE BUILDING");
    text(value, metrics.gap != null ? fmtGap(metrics.gap) : sample.value);
    const approachName = resolveTargetName(metrics, envelope);
    text(
      meta,
      approachName
        ? approachName
        : metrics.closingRate != null
          ? fmtRate(metrics.closingRate)
          : sample.meta,
    );
  } else if (stateKey === "attack_range") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "MOVE POSSIBLE");
    text(value, fmtGap(metrics.gap));
    const attackName = resolveTargetName(metrics, envelope);
    text(
      meta,
      attackName
        ? attackName
        : metrics.closingRate != null
          ? fmtRate(metrics.closingRate)
          : sample.meta,
    );
  } else if (stateKey === "side_by_side") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "WHEEL TO WHEEL");
    text(value, fmtGap(metrics.gap));
    const vsName = resolveTargetName(metrics, envelope);
    text(meta, vsName ? `vs ${vsName}` : metrics.targetCarIdx != null ? `vs #${metrics.targetCarIdx}` : sample.meta);
  } else if (stateKey === "battle_for_position") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "AHEAD + BEHIND");
    text(value, metrics.position != null ? `P${metrics.position}` : sample.value);
    const frontLabel = metrics.frontTargetName
      ? `ahead ${metrics.frontTargetName}`
      : metrics.frontTargetPosition != null
        ? `ahead P${metrics.frontTargetPosition}`
        : "";
    const rearLabel = metrics.rearTargetName
      ? `behind ${metrics.rearTargetName}`
      : metrics.rearTargetPosition != null
        ? `behind P${metrics.rearTargetPosition}`
        : "";
    text(meta, [frontLabel, rearLabel].filter(Boolean).join(" · "));
  } else if (stateKey === "battle_won") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "GAP STABILISED");
    text(
      value,
      metrics.delta != null
        ? fmtPositionDelta(Math.abs(Number(metrics.delta)))
        : sample.value,
    );
    text(meta, sample.meta || "story result");
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, sample.value || fmtGap(metrics.gap));
    text(meta, sample.meta || "");
  }
}

function fillPositionCopy(node, envelope, stateKey, sample, metrics, copy) {
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const headline = resolveHeadline(copy.headlineToken, sample.title, stateKey);
  text(title, headline);
  const delta =
    metrics.delta ??
    (metrics.oldPosition != null && metrics.newPosition != null
      ? metrics.oldPosition - metrics.newPosition
      : null);
  if (stateKey === "position_gained") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "ORDER UPDATE");
    text(value, delta != null ? fmtPositionDelta(Math.abs(delta)) : sample.value);
    text(
      meta,
      metrics.oldPosition != null && metrics.newPosition != null
        ? fmtPositionRange(metrics.oldPosition, metrics.newPosition)
        : sample.meta,
    );
  } else if (stateKey === "position_lost") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "STAY FOCUSED");
    text(value, delta != null ? fmtPositionDelta(delta) : sample.value);
    text(
      meta,
      metrics.oldPosition != null && metrics.newPosition != null
        ? fmtPositionRange(metrics.oldPosition, metrics.newPosition)
        : sample.meta,
    );
  } else if (stateKey === "overtake") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "BATTLE COMPLETE");
    text(
      value,
      metrics.oldPosition != null && metrics.newPosition != null
        ? fmtPositionRange(metrics.oldPosition, metrics.newPosition)
        : sample.value,
    );
    text(meta, metrics.targetCarIdx != null ? `vs #${metrics.targetCarIdx}` : sample.meta);
  } else if (stateKey === "rival_threat") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "FAST LAP");
    // Live adapter sends rivalPosition/gap/targetName, not metrics.position.
    // Sample fallback is hardcoded P8 — never use it when live identity exists.
    const rivalPos = metrics.position ?? metrics.rivalPosition;
    text(value, rivalPos != null ? `P${rivalPos}` : sample.value);
    const rivalName = resolveTargetName(metrics, envelope);
    const gapLabel = metrics.gap != null ? fmtGap(metrics.gap) : null;
    if (rivalName && gapLabel) {
      text(meta, `${rivalName} · ${gapLabel}`);
    } else if (rivalName) {
      text(meta, rivalName);
    } else if (gapLabel) {
      text(meta, gapLabel);
    } else {
      text(meta, sample.meta || "projected ahead");
    }
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, sample.value || fmtPositionDelta(delta));
    text(meta, sample.meta || fmtPositionRange(metrics.oldPosition, metrics.newPosition));
  }
}

function fillPitCopy(node, envelope, stateKey, sample, metrics, copy) {
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const headline = resolveHeadline(copy.headlineToken, sample.title, stateKey);
  text(title, headline);
  const duration =
    metrics.pitDurationProxy ?? metrics.duration ?? metrics.lapTime ?? sample.value ?? null;
  if (stateKey === "pit_entry") {
    text(subtitle, resolveCopy("pit.entry") || sample.subtitle || "STORY START");
    text(
      value,
      metrics.entryPosition != null
        ? `P${metrics.entryPosition}`
        : metrics.position != null
          ? `P${metrics.position}`
          : sample.value,
    );
    text(meta, sample.meta || "");
  } else if (stateKey === "pit_lane") {
    text(subtitle, resolveCopy("pit.lane") || sample.subtitle || "LIMITER ACTIVE");
    text(value, duration != null ? `${fmt(duration, 1)} s` : sample.value);
    text(meta, metrics.onPitRoad ? "on pit road" : sample.meta || "");
  } else if (stateKey === "pit_stopped") {
    text(subtitle, resolveCopy("pit.stopped") || sample.subtitle || "SERVICE");
    text(value, duration != null ? `${fmt(duration, 1)} s` : sample.value);
    text(meta, sample.meta || "");
  } else if (stateKey === "pit_released") {
    text(subtitle, resolveCopy("pit.released") || sample.subtitle || "GO GO GO");
    text(value, duration != null ? `${fmt(duration, 1)} s` : sample.value);
    text(meta, sample.meta || "");
  } else if (stateKey === "pit_exit") {
    text(subtitle, resolveCopy("pit.exit") || sample.subtitle || "BACK ON TRACK");
    text(
      value,
      metrics.exitPosition != null
        ? `P${metrics.exitPosition}`
        : metrics.position != null
          ? `P${metrics.position}`
          : sample.value,
    );
    text(meta, sample.meta || "");
  } else if (stateKey === "pit_outcome") {
    text(subtitle, resolveCopy("pit.outcome") || sample.subtitle || "STORY COMPLETE");
    const delta = metrics.positionDelta;
    text(
      value,
      delta != null
        ? fmtPositionDelta(Number(delta))
        : metrics.position != null
          ? `P${metrics.position}`
          : sample.value,
    );
    text(
      meta,
      metrics.entryPosition != null && metrics.exitPosition != null
        ? fmtPositionRange(metrics.entryPosition, metrics.exitPosition)
        : sample.meta || "",
    );
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, duration != null ? `${fmt(duration, 1)} s` : sample.value || "");
    text(meta, sample.meta || "");
  }
}

function fillBioCopy(node, envelope, stateKey, sample, metrics, copy) {
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const headline = resolveHeadline(copy.headlineToken, sample.title, stateKey);
  text(title, headline);
  const bpmLabel = fmtBpm(metrics.bpm);
  if (stateKey === "hr_pressure") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "BATTLE INTENSITY");
    text(value, bpmLabel ? `${bpmLabel} BPM` : sample.value);
    text(meta, metrics.deltaBpm != null ? fmtBpmDelta(metrics.deltaBpm, 0) : sample.meta || "");
  } else if (stateKey === "ble_reconnecting") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "SENSOR DATA PAUSED");
    text(value, sample.value || "--");
    text(meta, sample.meta || "reconnecting");
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, bpmLabel ? `${bpmLabel} BPM` : sample.value || "");
    text(meta, sample.meta || "");
  }
}

function fillSessionCopy(node, envelope, stateKey, sample, metrics, copy) {
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const phase = String(envelope.phase || "RESULT").toUpperCase();
  const headline = resolveHeadline(copy.headlineToken, sample.title, stateKey);
  text(title, headline);
  if (stateKey === "final_lap") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "ONE MORE PUSH");
    text(
      value,
      metrics.lap != null && metrics.totalLaps != null
        ? `LAP ${metrics.lap}/${metrics.totalLaps}`
        : sample.value,
    );
    text(meta, phase === "RESULT" ? resolveCopy("session.finish") || sample.meta : sample.meta || "major event");
  } else if (stateKey === "finish") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "RACE COMPLETE");
    text(value, metrics.position != null ? `P${metrics.position}` : sample.value);
    text(meta, metrics.classPosition != null ? `P${metrics.classPosition} in class` : sample.meta);
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, sample.value || "");
    text(meta, sample.meta || "");
  }
}

function fillExceptionCopy(node, envelope, stateKey, sample, metrics, copy) {
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const headline = resolveHeadline(copy.headlineToken, sample.title, stateKey);
  text(title, headline);
  if (stateKey === "incident") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "COALESCED UPDATE");
    text(value, metrics.value != null ? `+${metrics.value} INC` : sample.value);
    text(meta, metrics.total != null ? `total ${metrics.total}` : sample.meta);
  } else if (stateKey === "invalid_lap") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "PROJECTION CANCELLED");
    text(value, metrics.lap != null ? `LAP ${metrics.lap}` : sample.value);
    text(meta, sample.meta || "");
  } else if (stateKey === "link_drop") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "DATA STALE");
    text(value, sample.value || "--");
    text(meta, sample.meta || "reconnecting");
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, sample.value || "");
    text(meta, sample.meta || "");
  }
}

function fillTimingCopy(node, envelope, stateKey, sample, metrics, copy) {
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const headline = resolveHeadline(copy.headlineToken, sample.title, stateKey);
  text(title, headline);
  if (stateKey === "target") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "ME VS TARGET");
    text(value, metrics.targetTime != null ? fmtLapTime(metrics.targetTime) : sample.value);
    text(meta, metrics.referenceType ? `${metrics.referenceType} reference` : sample.meta);
  } else if (stateKey === "projected_lap") {
    text(
      subtitle,
      metrics.confidence != null ? `CONFIDENCE ${fmt(metrics.confidence, 2)}` : sample.subtitle,
    );
    text(value, metrics.projectedTime != null ? fmtLapTime(metrics.projectedTime) : sample.value);
    text(meta, metrics.range != null ? `range ±${fmt(metrics.range, 3)}` : sample.meta);
  } else if (stateKey === "pb_attack") {
    const sectorLabel = metrics.sector || metrics.timingPointId || "S1";
    const delta = metrics.delta ?? metrics.deltaToBest;
    text(subtitle, delta != null ? `${sectorLabel} · ${fmtDelta(delta)}` : sample.subtitle);
    text(value, metrics.projectedTime != null ? fmtLapTime(metrics.projectedTime) : sample.value);
    text(meta, sample.meta || "personal best");
  } else if (stateKey === "hot_lap") {
    const idx = metrics.hotLapIndex ?? 1;
    const total = metrics.hotLapTotal ?? 2;
    if (idx != null && total != null) text(title, `HOT LAP ${idx}/${total}`);
    text(subtitle, metrics.position != null ? `CURRENT P${metrics.position}` : sample.subtitle);
    text(
      value,
      metrics.sectorDelta != null ? `S1 ${fmtDelta(metrics.sectorDelta)}` : sample.value,
    );
    const hotName = resolveTargetName(metrics, envelope);
    text(
      meta,
      hotName
        ? `target ${hotName}`
        : metrics.targetPosition != null
          ? `target P${metrics.targetPosition}`
          : sample.meta,
    );
  } else if (stateKey === "position_attack") {
    const attackName = resolveTargetName(metrics, envelope);
    if (attackName) text(title, `${attackName} IN RANGE`);
    else if (metrics.targetPosition != null) text(title, `P${metrics.targetPosition} IN RANGE`);
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "ME VS GRID");
    text(value, metrics.projectedTime != null ? fmtLapTime(metrics.projectedTime) : sample.value);
    text(meta, metrics.confidence != null ? `confidence ${fmt(metrics.confidence, 2)}` : sample.meta);
  } else if (stateKey === "gain_found") {
    const sectorLabel = metrics.sector || metrics.timingPointId;
    const isSplit = typeof sectorLabel === "string" && /^S\d+$/.test(sectorLabel);
    text(
      subtitle,
      isSplit ? sectorLabel : metrics.timingPointId ? `${metrics.timingPointId} EXIT` : sample.subtitle,
    );
    if (isSplit && metrics.segmentTime != null) {
      text(value, fmtLapTime(metrics.segmentTime));
      text(meta, metrics.delta != null ? fmtDelta(metrics.delta) : sample.meta || "");
    } else {
      text(value, metrics.delta != null ? fmtDelta(metrics.delta) : sample.value);
      text(meta, sample.meta || "clean minisector");
    }
  } else if (stateKey === "clean_streak") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "CONSISTENT PACE");
    text(value, metrics.streak != null ? `${metrics.streak} LAPS` : sample.value);
    text(meta, metrics.spread != null ? `spread ${fmt(metrics.spread, 2)}` : sample.meta);
  } else if (stateKey === "lap_complete") {
    text(subtitle, metrics.personalBest ? "PERSONAL BEST" : "CLEAN LAP");
    text(value, fmtLapTime(metrics.lapTime));
    text(meta, metrics.lap != null ? `lap ${metrics.lap}` : sample.meta);
  } else if (stateKey === "personal_best") {
    text(subtitle, sample.subtitle || "NEW REFERENCE");
    text(value, fmtLapTime(metrics.lapTime));
    text(meta, fmtDelta(metrics.deltaToBest));
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, sample.value || "");
    text(meta, sample.meta || "");
  }
}

function fillCopySlots(node, envelope, stateKey) {
  const sample = manifest?.states?.[stateKey]?.sample || {};
  const metrics = envelope.metrics || {};
  const copy = envelope.copy || {};
  const familyName = familyForState(stateKey);
  if (familyName === "battle") {
    fillBattleCopy(node, envelope, stateKey, sample, metrics, copy);
    return;
  }
  if (familyName === "position") {
    fillPositionCopy(node, envelope, stateKey, sample, metrics, copy);
    return;
  }
  if (familyName === "pit") {
    fillPitCopy(node, envelope, stateKey, sample, metrics, copy);
    return;
  }
  if (familyName === "bio") {
    fillBioCopy(node, envelope, stateKey, sample, metrics, copy);
    return;
  }
  if (familyName === "session") {
    fillSessionCopy(node, envelope, stateKey, sample, metrics, copy);
    return;
  }
  if (familyName === "exception") {
    fillExceptionCopy(node, envelope, stateKey, sample, metrics, copy);
    return;
  }
  if (familyName === "timing") {
    fillTimingCopy(node, envelope, stateKey, sample, metrics, copy);
  }
}

function widgetKey(envelope, stateKey, { golden = false } = {}) {
  const familyName = familyForState(stateKey);
  const persistent = !golden && (familyName === "pit" || familyName === "bio");
  const cid =
    (persistent ? envelope.storyKey || envelope.correlationId : envelope.correlationId) ||
    envelope.storyKey ||
    envelope.eventId ||
    stateKey;
  return golden ? `golden:${cid}` : `v4:${cid}`;
}

function isGoldenLayout() {
  return document.documentElement.classList.contains("golden-layout");
}

function enforceFamilyCap(familyName) {
  const cap = FAMILY_CAPS[familyName];
  if (!cap) return;
  const entries = [...DisplayV4.active.entries()].filter(([, node]) => node.dataset.family === familyName);
  while (entries.length >= cap) {
    const [oldestKey] = entries.shift();
    DisplayV4.hide(oldestKey);
  }
}

/** RESULT position plates must clear sticky rival_threat ACTIVE peers. */
function preemptStickyFamilyPeers(familyName, keepKey, phase) {
  if (familyName !== "position" || phase !== "RESULT") return;
  for (const [key, node] of [...DisplayV4.active.entries()]) {
    if (key === keepKey) continue;
    if (node.dataset.family !== familyName) continue;
    const peerPhase = String(node.dataset.phase || "").toUpperCase();
    if (peerPhase === "ACTIVE" || peerPhase === "ENTER") {
      DisplayV4.hide(key);
    }
  }
}

function scheduleHoldTimer(node, key, envelope, phase, golden) {
  clearTimeout(node._exitTimer);
  if (golden || isGoldenLayout()) return;
  if (phase === "RESULT") {
    const hold = envelope.presentation?.minHoldMs || DEFAULT_HOLD_MS;
    node._exitTimer = setTimeout(() => DisplayV4.hide(key), hold);
    return;
  }
  if (phase === "ACTIVE" || phase === "ENTER") {
    const maxHold = Number(envelope.presentation?.maxHoldMs || 0);
    if (maxHold > 0) {
      node._exitTimer = setTimeout(() => DisplayV4.hide(key), maxHold);
    }
  }
}

export async function initV4(options = {}) {
  theme = options.theme || theme;
  language = options.language || language;
  copyCatalog = options.copyCatalog || copyCatalog;
  resolvedMotions = options.resolvedMotions || resolvedMotions;
  resolvedStates = options.resolvedStates || resolvedStates;
  motionDisabled = Boolean(options.motionDisabled);
  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = theme;
  }
  let manifestOk = false;
  try {
    const manifestUrl = options.manifestUrl || `${ASSET_BASE}themes-v4/manifest.json`;
    const catalogUrl = options.catalogUrl || `${ASSET_BASE}themes-v4/event_catalog.json`;
    const tasks = [fetch(manifestUrl), fetch(catalogUrl), fetch("/api/overlay/i18n")];
    const results = await Promise.all(tasks);
    const [manifestRes, catalogRes, i18nRes] = results;
    if (manifestRes.ok) {
      try {
        manifest = await manifestRes.json();
        manifestOk = Boolean(manifest && typeof manifest === "object");
      } catch (err) {
        console.error("v4 manifest parse failed", err);
        manifest = null;
        manifestOk = false;
      }
    }
    if (catalogRes.ok) {
      try {
        catalog = await catalogRes.json();
      } catch (err) {
        console.error("v4 catalog parse failed", err);
        catalog = null;
      }
    }
    if (i18nRes?.ok) {
      try {
        const i18n = await i18nRes.json();
        // Merge so a stale/partial snapshot catalog cannot hide new tokens.
        copyCatalog = { ...copyCatalog, ...(i18n.copyCatalog || {}) };
        language = i18n.language || language;
      } catch (err) {
        console.error("v4 i18n parse failed", err);
      }
    }
  } catch (err) {
    console.error("initV4 failed", err);
    manifest = null;
    manifestOk = false;
  } finally {
    if (typeof document !== "undefined") {
      document.documentElement.dataset.v4Manifest = manifestOk ? "ok" : "fallback";
      if (!manifestOk) {
        document.getElementById("sysinfo-widget")?.classList.add("fallback");
      } else {
        applyManifestGeometry();
      }
    }
  }
  if (options.sysinfo !== false) {
    try {
      renderSysinfo();
    } catch (err) {
      console.error("renderSysinfo failed", err);
    }
  }
}

export function refreshV4Presentation(options = {}) {
  if (options.theme) theme = options.theme;
  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = theme;
    if (manifest) applyManifestGeometry();
  }
  renderSysinfo();
}

export const DisplayV4 = {
  active: new Map(),

  refresh(options = {}) {
    refreshV4Presentation(options);
  },

  show(envelope, options = {}) {
    if (!envelope || envelope.format !== "v4") return null;
    const golden = Boolean(options.golden || options.container);
    if (!golden && isStale(envelope)) return null;
    const phase = String(envelope.phase || "RESULT").toUpperCase();
    if (phase === "EXIT") {
      this.hide(widgetKey(envelope, resolveStateKey(envelope), { golden }));
      return null;
    }
    const stateKey = resolveStateKey(envelope);
    const familyName = familyForState(stateKey);
    if (!TRANSIENT_FAMILIES.has(familyName)) return null;
    const key = widgetKey(envelope, stateKey, { golden });
    let node = this.active.get(key);
    const created = !node;
    if (!node) {
      if (!golden) {
        preemptStickyFamilyPeers(familyName, key, phase);
        enforceFamilyCap(familyName);
      }
      node = this._create(stateKey, familyName, options.container);
      this.active.set(key, node);
    } else if (node.dataset.state !== stateKey) {
      node.dataset.state = stateKey;
      rebuildArt(node, stateKey, familyName);
      const meta = manifest?.states?.[stateKey] || {};
      const accent = envelope.presentation?.accent || meta.tone || "primary";
      node.className = `v4-widget tone-${accent}`;
      node.classList.add("visible");
    }
    node.dataset.state = stateKey;
    node.dataset.phase = phase;
    node.classList.toggle("phase-compact", phase === "COMPACT");
    const accent = envelope.presentation?.accent || manifest?.states?.[stateKey]?.tone || "primary";
    node.classList.remove("tone-primary", "tone-warning", "tone-alert");
    node.classList.add(`tone-${accent}`);
    fillCopySlots(node, envelope, stateKey);
    syncWidgetMotion(node, envelope, familyName, created);
    node.classList.remove("exit");
    if (created && golden) node.classList.add("visible");
    else if (created) requestAnimationFrame(() => node.classList.add("visible"));
    else node.classList.add("visible");
    scheduleHoldTimer(node, key, envelope, phase, golden);
    return node;
  },

  showInContainer(envelope, container) {
    if (!container) return null;
    return this.show(envelope, { golden: true, container });
  },

  hide(key) {
    const node = this.active.get(key);
    if (!node) return;
    clearTimeout(node._exitTimer);
    node.classList.add("exit");
    node.classList.remove("visible");
    setTimeout(() => {
      if (this.active.get(key) !== node) return;
      node.remove();
      this.active.delete(key);
    }, 320);
  },

  clear() {
    for (const key of [...this.active.keys()]) this.hide(key);
    lastSequence.clear();
  },

  applyStateSnapshot(stories) {
    this.clear();
    (stories || []).forEach((story) => this.show({ ...story, format: "v4" }));
  },

  _create(stateKey, familyName, parent) {
    const meta = manifest?.states?.[stateKey] || {};
    const node = document.createElement("div");
    node.className = `v4-widget tone-${meta.tone || "primary"}`;
    node.dataset.family = familyName;
    node.dataset.state = stateKey;
    const copy = document.createElement("div");
    copy.className = "v4-copy";
    copy.innerHTML =
      '<div class="title"></div><div class="subtitle"></div><div class="value"></div><div class="meta"></div>';
    const art = document.createElement("div");
    art.className = "v4-art";
    node.append(art, copy);
    (parent || layerRootForFamily(familyName)).appendChild(node);
    rebuildArt(node, stateKey, familyName);
    return node;
  },
};

export function showV4(envelope) {
  return DisplayV4.show(envelope);
}

export function applyV4StateSnapshot(stories) {
  DisplayV4.applyStateSnapshot(stories);
}

export function clearV4() {
  DisplayV4.clear();
}

function v4FixtureEnvelope({
  eventType,
  phase = "RESULT",
  correlationId,
  eventId,
  metrics = {},
  copy = {},
  presentation = {},
  priority = 50,
  sequence = 1,
  dedupeKey,
  accent,
  widget,
  variant,
  preferredState,
}) {
  return {
    type: "event",
    format: "v4",
    schemaVersion: "1.0",
    eventId: eventId || `demo:${correlationId}`,
    sequence,
    sessionId: "session:demo",
    eventType,
    mode: "RACE",
    phase,
    priority,
    dedupeKey: dedupeKey || `RACE:${eventType}:${correlationId}`,
    correlationId,
    metrics,
    copy,
    presentation: {
      zone: "EVENT",
      accent: accent || "primary",
      preferredState: preferredState || phase,
      minHoldMs: 6000,
      widget,
      variant,
      ...presentation,
    },
  };
}

export function v4FixtureLapComplete(sequence = 1) {
  return v4FixtureEnvelope({
    eventType: "LAP_COMPLETE",
    phase: "RESULT",
    correlationId: "golden:lap_complete",
    sequence,
    priority: 40,
    metrics: { lap: 12, lapTime: 112.084, bestLap: 112.402, deltaToBest: -0.318 },
    copy: { headlineToken: "lap.complete", statusToken: "" },
    widget: "timing",
    variant: "lap_complete",
    accent: "primary",
    preferredState: "RESULT",
  });
}

export function v4FixturePersonalBest(sequence = 1) {
  return v4FixtureEnvelope({
    eventType: "PERSONAL_BEST",
    phase: "RESULT",
    correlationId: "golden:personal_best",
    sequence,
    priority: 60,
    metrics: { lap: 14, lapTime: 111.682, bestLap: 111.682, deltaToBest: -0.418 },
    copy: { headlineToken: "lap.personal_best", statusToken: "" },
    widget: "timing",
    variant: "personal_best",
    accent: "primary",
    preferredState: "RESULT",
  });
}

export function v4FixtureTarget(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "TARGET_LOCKED",
    phase,
    correlationId: "golden:target",
    sequence,
    priority: 45,
    metrics: { targetTime: 111.9, referenceType: "session" },
    copy: { headlineToken: "", statusToken: "" },
    widget: "timing",
    variant: "target",
    accent: "primary",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureProjectedLap(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "PROJECTED_LAP",
    phase,
    correlationId: "golden:projected_lap",
    sequence,
    priority: 42,
    metrics: { projectedTime: 111.774, confidence: 0.78, range: 0.11, bestLap: 112.402 },
    copy: { headlineToken: "", statusToken: "" },
    widget: "timing",
    variant: "projected_lap",
    accent: "primary",
    preferredState: "ACTIVE",
  });
}

export function v4FixturePbAttack(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "SECTOR_BEST",
    phase,
    correlationId: "golden:pb_attack",
    sequence,
    priority: 55,
    metrics: { sector: "S1", delta: -0.238, projectedTime: 111.64, bestLap: 111.682 },
    copy: { headlineToken: "", statusToken: "" },
    widget: "timing",
    variant: "pb_attack",
    accent: "primary",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureHotLap(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "HOT_LAP",
    phase,
    correlationId: "golden:hot_lap",
    sequence,
    priority: 50,
    metrics: {
      hotLapIndex: 1,
      hotLapTotal: 2,
      position: 7,
      targetPosition: 6,
      sectorDelta: -0.117,
    },
    copy: { headlineToken: "", statusToken: "" },
    widget: "timing",
    variant: "hot_lap",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixturePositionAttack(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "POSITION_ATTACK",
    phase,
    correlationId: "golden:position_attack",
    sequence,
    priority: 48,
    metrics: { targetPosition: 5, projectedTime: 111.774, confidence: 0.78, bestLap: 112.402 },
    copy: { headlineToken: "", statusToken: "" },
    widget: "timing",
    variant: "position_attack",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureGainFound(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "GAIN_FOUND",
    phase,
    correlationId: "golden:gain_found",
    sequence,
    priority: 44,
    metrics: { timingPointId: "T5", delta: -0.11, lap: 12, segmentTime: 18.42 },
    copy: { headlineToken: "", statusToken: "" },
    widget: "timing",
    variant: "gain_found",
    accent: "primary",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureCleanStreak(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "CLEAN_STREAK",
    phase,
    correlationId: "golden:clean_streak",
    sequence,
    priority: 38,
    metrics: { streak: 5, spread: 0.31 },
    copy: { headlineToken: "", statusToken: "" },
    widget: "timing",
    variant: "clean_streak",
    accent: "primary",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureHunting(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "HUNTING",
    phase,
    correlationId: "golden:hunting",
    sequence,
    priority: 20,
    metrics: { gap: 0.84, closingRate: 0.34, targetPosition: 7, targetCarIdx: 17 },
    copy: { headlineToken: "battle.hunting", statusToken: "" },
    widget: "battle",
    variant: "hunting",
    accent: "primary",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureHunted(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "HUNTED",
    phase,
    correlationId: "golden:hunted",
    sequence,
    priority: 20,
    metrics: { gap: 0.62, closingRate: 0.21, targetPosition: 8, targetCarIdx: 23 },
    copy: { headlineToken: "battle.hunted", statusToken: "" },
    widget: "battle",
    variant: "hunted",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureApproach(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "APPROACH",
    phase,
    correlationId: "golden:approach",
    sequence,
    priority: 20,
    metrics: { gap: 1.12, closingRate: 0.28, targetPosition: 6, targetCarIdx: 14 },
    copy: { headlineToken: "battle.approach", statusToken: "" },
    widget: "battle",
    variant: "approach",
    accent: "primary",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureAttackRange(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "ATTACK_RANGE",
    phase,
    correlationId: "golden:attack_range",
    sequence,
    priority: 20,
    metrics: { gap: 0.38, closingRate: 0.41, targetPosition: 6, targetCarIdx: 14 },
    copy: { headlineToken: "battle.attack_range", statusToken: "" },
    widget: "battle",
    variant: "attack_range",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureSideBySide(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "SIDE_BY_SIDE",
    phase,
    correlationId: "golden:side_by_side",
    sequence,
    priority: 20,
    metrics: { gap: 0.04, closingRate: 0.0, targetPosition: 6, targetCarIdx: 14 },
    copy: { headlineToken: "battle.side_by_side", statusToken: "" },
    widget: "battle",
    variant: "side_by_side",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureBattleForPosition(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "BATTLE_FOR_POSITION",
    phase,
    correlationId: "golden:battle_for_position",
    sequence,
    priority: 25,
    metrics: { position: 7, gapAhead: 0.42, gapBehind: 0.38 },
    copy: { headlineToken: "battle.battle_for_position", statusToken: "" },
    widget: "battle",
    variant: "battle_for_position",
    accent: "warning",
    preferredState: "ACTIVE",
    presentation: { maxHoldMs: 8000 },
  });
}

export function v4FixtureBattleWon(sequence = 1) {
  return v4FixtureEnvelope({
    eventType: "BATTLE_WON",
    phase: "RESULT",
    correlationId: "golden:battle_won",
    sequence,
    priority: 85,
    metrics: { delta: 1, oldPosition: 8, newPosition: 7 },
    copy: { headlineToken: "", statusToken: "" },
    widget: "battle",
    variant: "battle_won",
    accent: "primary",
    preferredState: "RESULT",
    presentation: { minHoldMs: 5000 },
  });
}

export function v4FixturePositionGained(sequence = 1) {
  return v4FixtureEnvelope({
    eventType: "POSITION_GAINED",
    phase: "RESULT",
    correlationId: "golden:position_gained",
    sequence,
    priority: 70,
    metrics: { direction: "gain", oldPosition: 8, newPosition: 7, delta: 1 },
    copy: { headlineToken: "position.gained", statusToken: "" },
    widget: "position",
    variant: "position_gained",
    accent: "primary",
    preferredState: "RESULT",
    presentation: { minHoldMs: 4000 },
  });
}

export function v4FixturePositionLost(sequence = 1) {
  return v4FixtureEnvelope({
    eventType: "POSITION_LOST",
    phase: "RESULT",
    correlationId: "golden:position_lost",
    sequence,
    priority: 70,
    metrics: { direction: "loss", oldPosition: 7, newPosition: 8, delta: -1 },
    copy: { headlineToken: "position.lost", statusToken: "" },
    widget: "position",
    variant: "position_lost",
    accent: "warning",
    preferredState: "RESULT",
    presentation: { minHoldMs: 4000 },
  });
}

export function v4FixtureOvertake(sequence = 1) {
  return v4FixtureEnvelope({
    eventType: "OVERTAKE",
    phase: "RESULT",
    correlationId: "golden:overtake",
    sequence,
    priority: 80,
    metrics: { oldPosition: 7, newPosition: 6, targetCarIdx: 17 },
    copy: { headlineToken: "position.overtake", statusToken: "" },
    widget: "position",
    variant: "overtake",
    accent: "primary",
    preferredState: "RESULT",
    presentation: { minHoldMs: 5000 },
  });
}

export function v4FixtureRivalThreat(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "RIVAL_THREAT",
    phase,
    correlationId: "golden:rival_threat",
    sequence,
    priority: 65,
    metrics: { position: 8, rivalPosition: 7, projectedGap: 0.24 },
    copy: { headlineToken: "position.rival_threat", statusToken: "" },
    widget: "position",
    variant: "rival_threat",
    accent: "warning",
    preferredState: "ACTIVE",
    presentation: { maxHoldMs: 8000 },
  });
}

export function v4FixturePitEntry(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "PIT_ENTRY",
    phase,
    correlationId: "golden:pit_entry",
    sequence,
    priority: 50,
    metrics: { position: 7, onPitRoad: true },
    copy: { headlineToken: "pit.entry", statusToken: "" },
    widget: "pit",
    variant: "pit_entry",
    accent: "warning",
    preferredState: "ENTER",
  });
}

export function v4FixturePitLane(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "PIT_LANE",
    phase,
    correlationId: "golden:pit_lane",
    sequence,
    priority: 50,
    metrics: { position: 7, duration: 41.2, onPitRoad: true },
    copy: { headlineToken: "pit.lane", statusToken: "" },
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixturePitStopped(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "PIT_STOPPED",
    phase,
    correlationId: "golden:pit_stopped",
    sequence,
    priority: 50,
    metrics: { position: 7, duration: 8.4, onPitRoad: true },
    copy: { headlineToken: "pit.stopped", statusToken: "" },
    widget: "pit",
    variant: "pit_stopped",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixturePitReleased(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "PIT_RELEASED",
    phase,
    correlationId: "golden:pit_released",
    sequence,
    priority: 50,
    metrics: { position: 7, duration: 12.7, onPitRoad: true },
    copy: { headlineToken: "pit.released", statusToken: "" },
    widget: "pit",
    variant: "pit_released",
    accent: "primary",
    preferredState: "ACTIVE",
  });
}

export function v4FixturePitExit(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "PIT_EXIT",
    phase,
    correlationId: "golden:pit_exit",
    sequence,
    priority: 50,
    metrics: { position: 12, onPitRoad: false },
    copy: { headlineToken: "pit.exit", statusToken: "" },
    widget: "pit",
    variant: "pit_exit",
    accent: "primary",
    preferredState: "ACTIVE",
  });
}

export function v4FixturePitOutcome(sequence = 1) {
  return v4FixtureEnvelope({
    eventType: "PIT_OUTCOME",
    phase: "RESULT",
    correlationId: "golden:pit_outcome",
    sequence,
    priority: 50,
    metrics: { position: 10, positionDelta: 2, duration: 24.3 },
    copy: { headlineToken: "pit.outcome", statusToken: "" },
    widget: "pit",
    variant: "pit_outcome",
    accent: "primary",
    preferredState: "RESULT",
  });
}

export function v4FixtureHrPressure(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "HR_PRESSURE_RISING",
    phase,
    correlationId: "golden:hr_pressure",
    sequence,
    priority: 35,
    metrics: { bpm: 164, deltaBpm: 14, baselineBpm: 150, intensity: 72 },
    copy: { headlineToken: "bio.hr_pressure", statusToken: "" },
    widget: "bio",
    variant: "hr_pressure",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureBleReconnecting(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "BLE_LOST",
    phase,
    correlationId: "golden:ble_reconnecting",
    sequence,
    priority: 35,
    metrics: {},
    copy: { headlineToken: "ble.lost", statusToken: "" },
    widget: "bio",
    variant: "ble_reconnecting",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureFinalLap(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "FINAL_LAP",
    phase,
    correlationId: "golden:final_lap",
    sequence,
    priority: 95,
    metrics: { lap: 24, totalLaps: 24 },
    copy: { headlineToken: "session.final_lap", statusToken: "" },
    widget: "session",
    variant: "final_lap",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureFinish(sequence = 1) {
  return v4FixtureEnvelope({
    eventType: "FINISH",
    phase: "RESULT",
    correlationId: "golden:finish",
    sequence,
    priority: 100,
    metrics: { position: 6, classPosition: 4 },
    copy: { headlineToken: "session.finish", statusToken: "" },
    widget: "session",
    variant: "finish",
    accent: "primary",
    preferredState: "RESULT",
  });
}

export function v4FixtureIncident(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "INCIDENT",
    phase,
    correlationId: "golden:incident",
    sequence,
    priority: 90,
    metrics: { value: 2, total: 5 },
    copy: { headlineToken: "exception.incident", statusToken: "" },
    widget: "exception",
    variant: "incident",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

export function v4FixtureInvalidLap(sequence = 1) {
  return v4FixtureEnvelope({
    eventType: "INVALID_LAP",
    phase: "RESULT",
    correlationId: "golden:invalid_lap",
    sequence,
    priority: 88,
    metrics: { lap: 4 },
    copy: { headlineToken: "exception.invalid_lap", statusToken: "" },
    widget: "exception",
    variant: "invalid_lap",
    accent: "alert",
    preferredState: "RESULT",
  });
}

export function v4FixtureLinkDrop(sequence = 1, phase = "ACTIVE") {
  return v4FixtureEnvelope({
    eventType: "LINK_DROP",
    phase,
    correlationId: "golden:link_drop",
    sequence,
    priority: 92,
    metrics: {},
    copy: { headlineToken: "exception.link_drop", statusToken: "" },
    widget: "exception",
    variant: "link_drop",
    accent: "alert",
    preferredState: "ACTIVE",
  });
}

/** Ordered golden catalog: fixture id → frozen demo envelope factory. */
export const V4_GOLDEN_CATALOG = [
  { id: "lap_complete", eventType: "LAP_COMPLETE", family: "timing", phase: "RESULT", factory: () => v4FixtureLapComplete() },
  { id: "personal_best", eventType: "PERSONAL_BEST", family: "timing", phase: "RESULT", factory: () => v4FixturePersonalBest() },
  { id: "target", eventType: "TARGET_LOCKED", family: "timing", phase: "ACTIVE", factory: () => v4FixtureTarget(1, "ACTIVE") },
  { id: "projected_lap", eventType: "PROJECTED_LAP", family: "timing", phase: "ACTIVE", factory: () => v4FixtureProjectedLap(1, "ACTIVE") },
  { id: "pb_attack", eventType: "SECTOR_BEST", family: "timing", phase: "ACTIVE", factory: () => v4FixturePbAttack(1, "ACTIVE") },
  { id: "hot_lap", eventType: "HOT_LAP", family: "timing", phase: "ACTIVE", factory: () => v4FixtureHotLap(1, "ACTIVE") },
  { id: "position_attack", eventType: "POSITION_ATTACK", family: "timing", phase: "ACTIVE", factory: () => v4FixturePositionAttack(1, "ACTIVE") },
  { id: "gain_found", eventType: "GAIN_FOUND", family: "timing", phase: "ACTIVE", factory: () => v4FixtureGainFound(1, "ACTIVE") },
  { id: "clean_streak", eventType: "CLEAN_STREAK", family: "timing", phase: "ACTIVE", factory: () => v4FixtureCleanStreak(1, "ACTIVE") },
  { id: "hunting", eventType: "HUNTING", family: "battle", phase: "ACTIVE", factory: () => v4FixtureHunting(1, "ACTIVE") },
  { id: "hunted", eventType: "HUNTED", family: "battle", phase: "ACTIVE", factory: () => v4FixtureHunted(1, "ACTIVE") },
  { id: "approach", eventType: "APPROACH", family: "battle", phase: "ACTIVE", factory: () => v4FixtureApproach(1, "ACTIVE") },
  { id: "attack_range", eventType: "ATTACK_RANGE", family: "battle", phase: "ACTIVE", factory: () => v4FixtureAttackRange(1, "ACTIVE") },
  { id: "side_by_side", eventType: "SIDE_BY_SIDE", family: "battle", phase: "ACTIVE", factory: () => v4FixtureSideBySide(1, "ACTIVE") },
  { id: "battle_for_position", eventType: "BATTLE_FOR_POSITION", family: "battle", phase: "ACTIVE", factory: () => v4FixtureBattleForPosition(1, "ACTIVE") },
  { id: "battle_won", eventType: "BATTLE_WON", family: "battle", phase: "RESULT", factory: () => v4FixtureBattleWon() },
  { id: "position_gained", eventType: "POSITION_GAINED", family: "position", phase: "RESULT", factory: () => v4FixturePositionGained() },
  { id: "position_lost", eventType: "POSITION_LOST", family: "position", phase: "RESULT", factory: () => v4FixturePositionLost() },
  { id: "overtake", eventType: "OVERTAKE", family: "position", phase: "RESULT", factory: () => v4FixtureOvertake() },
  { id: "rival_threat", eventType: "RIVAL_THREAT", family: "position", phase: "ACTIVE", factory: () => v4FixtureRivalThreat(1, "ACTIVE") },
  { id: "pit_entry", eventType: "PIT_ENTRY", family: "pit", phase: "ACTIVE", factory: () => v4FixturePitEntry(1, "ACTIVE") },
  { id: "pit_lane", eventType: "PIT_LANE", family: "pit", phase: "ACTIVE", factory: () => v4FixturePitLane(1, "ACTIVE") },
  { id: "pit_stopped", eventType: "PIT_STOPPED", family: "pit", phase: "ACTIVE", factory: () => v4FixturePitStopped(1, "ACTIVE") },
  { id: "pit_released", eventType: "PIT_RELEASED", family: "pit", phase: "ACTIVE", factory: () => v4FixturePitReleased(1, "ACTIVE") },
  { id: "pit_exit", eventType: "PIT_EXIT", family: "pit", phase: "ACTIVE", factory: () => v4FixturePitExit(1, "ACTIVE") },
  { id: "pit_outcome", eventType: "PIT_OUTCOME", family: "pit", phase: "RESULT", factory: () => v4FixturePitOutcome() },
  { id: "hr_pressure", eventType: "HR_PRESSURE_RISING", family: "bio", phase: "ACTIVE", factory: () => v4FixtureHrPressure(1, "ACTIVE") },
  { id: "ble_reconnecting", eventType: "BLE_LOST", family: "bio", phase: "ACTIVE", factory: () => v4FixtureBleReconnecting(1, "ACTIVE") },
  { id: "final_lap", eventType: "FINAL_LAP", family: "session", phase: "ACTIVE", factory: () => v4FixtureFinalLap(1, "ACTIVE") },
  { id: "finish", eventType: "FINISH", family: "session", phase: "RESULT", factory: () => v4FixtureFinish() },
  { id: "incident", eventType: "INCIDENT", family: "exception", phase: "ACTIVE", factory: () => v4FixtureIncident(1, "ACTIVE") },
  { id: "invalid_lap", eventType: "INVALID_LAP", family: "exception", phase: "RESULT", factory: () => v4FixtureInvalidLap() },
  { id: "link_drop", eventType: "LINK_DROP", family: "exception", phase: "ACTIVE", factory: () => v4FixtureLinkDrop(1, "ACTIVE") },
];

const V4_GOLDEN_BY_ID = Object.fromEntries(V4_GOLDEN_CATALOG.map((entry) => [entry.id, entry]));

export function getV4GoldenFixture(fixtureId) {
  const entry = V4_GOLDEN_BY_ID[fixtureId];
  if (!entry) return null;
  return entry.factory();
}

export function renderV4GoldenGallery(DisplayV4) {
  document.documentElement.classList.add("golden-gallery");
  let gallery = document.getElementById("v4-golden-gallery");
  if (!gallery) {
    gallery = document.createElement("div");
    gallery.id = "v4-golden-gallery";
    document.body.appendChild(gallery);
  }
  gallery.replaceChildren();
  V4_GOLDEN_CATALOG.forEach((entry) => {
    const cell = document.createElement("div");
    cell.className = "golden-cell";
    const label = document.createElement("div");
    label.className = "golden-label";
    label.textContent = `${entry.id} · ${entry.eventType} · ${entry.phase}`;
    const stage = document.createElement("div");
    stage.className = "golden-stage";
    cell.append(label, stage);
    gallery.appendChild(cell);
    DisplayV4.showInContainer(entry.factory(), stage);
  });
}
