/** V4 overlay renderer (S1: timing + battle + position families). */

const ASSET_BASE = "/overlay/web/";
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

function fmtLapTime(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const total = Number(seconds);
  const mins = Math.floor(total / 60);
  const secs = total - mins * 60;
  const whole = Math.floor(secs);
  const frac = Math.round((secs - whole) * 1000);
  if (mins > 0) {
    return `${mins}:${String(whole).padStart(2, "0")}.${String(frac).padStart(3, "0")}`;
  }
  return `${whole}.${String(frac).padStart(3, "0")}`;
}

function fmtGap(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  return `${fmt(seconds, 2)} s`;
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

function resolveCopy(token) {
  if (!token) return "";
  return copyCatalog[token] || token;
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
  if (themed.startsWith("themes/")) {
    return ASSET_BASE + themed.replace(/^themes\//, "themes-v4/");
  }
  return ASSET_BASE + themed;
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
  if (familyName === "battle") return ensureLayer("v4-battle-stack");
  return ensureLayer("v4-event-layer");
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

function paintLayer(el, url, { mask = false } = {}) {
  if (!el || !url) {
    el?.classList.add("empty");
    return;
  }
  el.classList.remove("empty");
  if (mask) {
    el.style.backgroundImage = "";
    el.style.backgroundColor = "currentColor";
    const maskUrl = `url("${url}")`;
    el.style.webkitMaskImage = maskUrl;
    el.style.maskImage = maskUrl;
    el.style.webkitMaskSize = "420px 140px";
    el.style.maskSize = "420px 140px";
    el.style.webkitMaskRepeat = "no-repeat";
    el.style.maskRepeat = "no-repeat";
  } else {
    el.style.backgroundColor = "";
    el.style.backgroundImage = `url("${url}")`;
    el.style.webkitMaskImage = "";
    el.style.maskImage = "";
  }
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
    return;
  }
  node.classList.remove("fallback");
  const goldenSnapshot = isGoldenSnapshot(node);
  (family.layers || []).forEach((layer, index) => {
    if (goldenSnapshot && /^glow_/.test(layer.file)) return;
    const el = document.createElement("div");
    el.className = `layer ${layer.mode === "mask" ? "mask" : "image"}`;
    el.dataset.index = String(index);
    const url = manifestDiskPath(`${family.layer_dir}/${layer.file}`);
    paintLayer(el, url, { mask: layer.mode === "mask" });
    art.appendChild(el);
  });
  const icon = document.createElement("div");
  icon.className = "icon";
  const iconUrl = manifestDiskPath(`${family.icon_dir}/${stateKey}.png`);
  paintLayer(icon, iconUrl);
  art.appendChild(icon);
}

function fillBattleCopy(node, envelope, stateKey, sample, metrics, copy) {
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const headline = resolveCopy(copy.headlineToken) || sample.title || stateKey;
  text(title, headline);
  if (stateKey === "hunting") {
    text(subtitle, resolveCopy("battle.closing_in") || sample.subtitle || "CLOSING IN");
    text(value, fmtGap(metrics.gap));
    text(
      meta,
      metrics.targetPosition != null ? `P${metrics.targetPosition} · target` : sample.meta,
    );
  } else if (stateKey === "hunted") {
    text(subtitle, sample.subtitle || resolveCopy("battle.hunted") || "UNDER PRESSURE");
    text(value, fmtGap(metrics.gap));
    text(meta, metrics.targetPosition != null ? `P${metrics.targetPosition} behind` : sample.meta);
  } else if (stateKey === "approach") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "BATTLE BUILDING");
    text(value, metrics.closingRate != null ? fmt(metrics.closingRate, 2) : sample.value);
    text(meta, sample.meta);
  } else if (stateKey === "attack_range") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "MOVE POSSIBLE");
    text(value, fmtGap(metrics.gap));
    text(meta, metrics.closingRate != null ? `rate ${fmt(metrics.closingRate, 2)}` : sample.meta);
  } else if (stateKey === "side_by_side") {
    text(subtitle, resolveCopy(copy.statusToken) || sample.subtitle || "WHEEL TO WHEEL");
    text(value, fmtGap(metrics.gap));
    text(meta, metrics.targetCarIdx != null ? `vs #${metrics.targetCarIdx}` : sample.meta);
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
  const headline = resolveCopy(copy.headlineToken) || sample.title || stateKey;
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
  const headline = resolveCopy(copy.headlineToken) || sample.title || stateKey;
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
  const headline = resolveCopy(copy.headlineToken) || sample.title || stateKey;
  text(title, headline);
  if (stateKey === "hr_pressure") {
    text(subtitle, resolveCopy("bio.hr_pressure") || sample.subtitle || "HR PRESSURE");
    text(value, metrics.bpm != null ? `${metrics.bpm} BPM` : sample.value);
    text(
      meta,
      metrics.deltaBpm != null
        ? `${metrics.deltaBpm >= 0 ? "+" : ""}${metrics.deltaBpm} vs baseline`
        : sample.meta,
    );
  } else if (stateKey === "ble_reconnecting") {
    text(subtitle, resolveCopy("ble.lost") || sample.subtitle || "DATA STALE");
    text(value, sample.value || "--");
    text(meta, sample.meta || "reconnecting");
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, metrics.bpm != null ? `${metrics.bpm} BPM` : sample.value || "");
    text(meta, sample.meta || "");
  }
}

function fillSessionCopy(node, envelope, stateKey, sample, metrics, copy) {
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const phase = String(envelope.phase || "RESULT").toUpperCase();
  const headline = resolveCopy(copy.headlineToken) || sample.title || stateKey;
  text(title, headline);
  if (stateKey === "final_lap") {
    text(subtitle, resolveCopy("session.final_lap") || sample.subtitle || "ONE MORE PUSH");
    text(
      value,
      metrics.lap != null && metrics.totalLaps != null
        ? `LAP ${metrics.lap}/${metrics.totalLaps}`
        : sample.value,
    );
    text(meta, phase === "RESULT" ? resolveCopy("session.finish") || sample.meta : sample.meta || "major event");
  } else if (stateKey === "finish") {
    text(subtitle, resolveCopy("session.finish") || sample.subtitle || "RACE COMPLETE");
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
  const headline = resolveCopy(copy.headlineToken) || sample.title || stateKey;
  text(title, headline);
  if (stateKey === "incident") {
    text(subtitle, resolveCopy("incident") || sample.subtitle || "COALESCED UPDATE");
    text(value, metrics.value != null ? `+${metrics.value} INC` : sample.value);
    text(meta, metrics.total != null ? `total ${metrics.total}` : sample.meta);
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
  const title = node.querySelector(".title");
  const subtitle = node.querySelector(".subtitle");
  const value = node.querySelector(".value");
  const meta = node.querySelector(".meta");
  const headline = resolveCopy(copy.headlineToken) || sample.title || stateKey;
  text(title, headline);
  if (stateKey === "lap_complete") {
    text(subtitle, metrics.personalBest ? "PERSONAL BEST" : "CLEAN LAP");
    text(value, fmtLapTime(metrics.lapTime));
    text(meta, metrics.lap != null ? `lap ${metrics.lap}` : sample.meta);
  } else if (stateKey === "personal_best") {
    text(subtitle, sample.subtitle || "NEW REFERENCE");
    text(value, fmtLapTime(metrics.lapTime));
    text(meta, fmt(metrics.deltaToBest, 3));
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, sample.value || "");
    text(meta, sample.meta || "");
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

export async function initV4(options = {}) {
  theme = options.theme || theme;
  language = options.language || language;
  copyCatalog = options.copyCatalog || copyCatalog;
  resolvedMotions = options.resolvedMotions || resolvedMotions;
  resolvedStates = options.resolvedStates || resolvedStates;
  motionDisabled = Boolean(options.motionDisabled);
  const manifestUrl = options.manifestUrl || `${ASSET_BASE}themes-v4/manifest.json`;
  const catalogUrl = options.catalogUrl || `${ASSET_BASE}themes-v4/event_catalog.json`;
  const tasks = [fetch(manifestUrl), fetch(catalogUrl)];
  if (!Object.keys(copyCatalog).length) {
    tasks.push(fetch("/api/overlay/i18n"));
  }
  const results = await Promise.all(tasks);
  const [manifestRes, catalogRes, i18nRes] = results;
  if (manifestRes.ok) manifest = await manifestRes.json();
  if (catalogRes.ok) catalog = await catalogRes.json();
  if (i18nRes?.ok) {
    const i18n = await i18nRes.json();
    copyCatalog = i18n.copyCatalog || copyCatalog;
    language = i18n.language || language;
  }
}

export const DisplayV4 = {
  active: new Map(),

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
      if (!golden) enforceFamilyCap(familyName);
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
    node.classList.remove("tone-primary", "tone-warning");
    node.classList.add(`tone-${accent}`);
    fillCopySlots(node, envelope, stateKey);
    syncWidgetMotion(node, envelope, familyName, created);
    node.classList.remove("exit");
    if (created && golden) node.classList.add("visible");
    else if (created) requestAnimationFrame(() => node.classList.add("visible"));
    else node.classList.add("visible");
    if (phase === "RESULT" && !golden && !isGoldenLayout()) {
      const hold = envelope.presentation?.minHoldMs || DEFAULT_HOLD_MS;
      clearTimeout(node._exitTimer);
      node._exitTimer = setTimeout(() => this.hide(key), hold);
    } else {
      clearTimeout(node._exitTimer);
    }
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
    copy: { headlineToken: "incident", statusToken: "" },
    widget: "exception",
    variant: "incident",
    accent: "warning",
    preferredState: "ACTIVE",
  });
}

/** Ordered golden catalog: fixture id → frozen demo envelope factory. */
export const V4_GOLDEN_CATALOG = [
  { id: "lap_complete", eventType: "LAP_COMPLETE", family: "timing", phase: "RESULT", factory: () => v4FixtureLapComplete() },
  { id: "personal_best", eventType: "PERSONAL_BEST", family: "timing", phase: "RESULT", factory: () => v4FixturePersonalBest() },
  { id: "hunting", eventType: "HUNTING", family: "battle", phase: "ACTIVE", factory: () => v4FixtureHunting(1, "ACTIVE") },
  { id: "hunted", eventType: "HUNTED", family: "battle", phase: "ACTIVE", factory: () => v4FixtureHunted(1, "ACTIVE") },
  { id: "approach", eventType: "APPROACH", family: "battle", phase: "ACTIVE", factory: () => v4FixtureApproach(1, "ACTIVE") },
  { id: "attack_range", eventType: "ATTACK_RANGE", family: "battle", phase: "ACTIVE", factory: () => v4FixtureAttackRange(1, "ACTIVE") },
  { id: "side_by_side", eventType: "SIDE_BY_SIDE", family: "battle", phase: "ACTIVE", factory: () => v4FixtureSideBySide(1, "ACTIVE") },
  { id: "position_gained", eventType: "POSITION_GAINED", family: "position", phase: "RESULT", factory: () => v4FixturePositionGained() },
  { id: "position_lost", eventType: "POSITION_LOST", family: "position", phase: "RESULT", factory: () => v4FixturePositionLost() },
  { id: "overtake", eventType: "OVERTAKE", family: "position", phase: "RESULT", factory: () => v4FixtureOvertake() },
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
