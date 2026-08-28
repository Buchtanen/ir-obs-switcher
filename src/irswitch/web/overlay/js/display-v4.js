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

function syncWidgetMotion(node, envelope, familyName, created) {
  if (prefersReducedMotion()) return;
  const art = node.querySelector(".v4-art");
  if (!art) return;
  const preview =
    document.documentElement.classList.contains("preview-layout") ||
    document.documentElement.classList.contains("golden-layout");
  if (preview) return;

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
  (family.layers || []).forEach((layer, index) => {
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
    text(subtitle, "CLOSING IN");
    text(value, fmtGap(metrics.gap));
    text(
      meta,
      metrics.targetPosition != null ? `P${metrics.targetPosition} · target` : sample.meta,
    );
  } else if (stateKey === "hunted") {
    text(subtitle, "UNDER PRESSURE");
    text(value, fmtGap(metrics.gap));
    text(meta, metrics.targetPosition != null ? `P${metrics.targetPosition} behind` : sample.meta);
  } else if (stateKey === "approach") {
    text(subtitle, sample.subtitle || "BATTLE BUILDING");
    text(value, metrics.closingRate != null ? fmt(metrics.closingRate, 2) : sample.value);
    text(meta, sample.meta);
  } else if (stateKey === "attack_range") {
    text(subtitle, sample.subtitle || "MOVE POSSIBLE");
    text(value, fmtGap(metrics.gap));
    text(meta, metrics.closingRate != null ? `rate ${fmt(metrics.closingRate, 2)}` : sample.meta);
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
  if (stateKey === "pit_entry") {
    text(subtitle, resolveCopy("pit.entry") || sample.subtitle || "STORY START");
    text(
      value,
      metrics.position != null ? `P${metrics.position}` : metrics.lapTime ?? sample.value,
    );
    text(meta, sample.meta || "lane detected");
  } else if (stateKey === "pit_exit") {
    text(subtitle, resolveCopy("pit.exit") || sample.subtitle || "BACK ON TRACK");
    text(value, metrics.position != null ? `P${metrics.position}` : sample.value);
    text(meta, sample.meta || "");
  } else {
    text(subtitle, sample.subtitle || "");
    text(value, metrics.duration != null ? fmt(metrics.duration, 1) + " s" : sample.value || "");
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
    text(subtitle, resolveCopy("bio.hr_high") || sample.subtitle || "HR PRESSURE");
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

function widgetKey(envelope, stateKey) {
  const cid = envelope.correlationId || envelope.storyKey || envelope.eventId || stateKey;
  return `v4:${cid}`;
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

  show(envelope) {
    if (!envelope || envelope.format !== "v4") return null;
    if (isStale(envelope)) return null;
    const phase = String(envelope.phase || "RESULT").toUpperCase();
    if (phase === "EXIT") {
      this.hide(widgetKey(envelope, resolveStateKey(envelope)));
      return null;
    }
    const stateKey = resolveStateKey(envelope);
    const familyName = familyForState(stateKey);
    if (!TRANSIENT_FAMILIES.has(familyName)) return null;
    const key = widgetKey(envelope, stateKey);
    let node = this.active.get(key);
    const created = !node;
    if (!node) {
      enforceFamilyCap(familyName);
      node = this._create(stateKey, familyName);
      this.active.set(key, node);
    } else if (node.dataset.state !== stateKey) {
      node.dataset.state = stateKey;
      rebuildArt(node, stateKey, familyName);
      const meta = manifest?.states?.[stateKey] || {};
      node.className = `v4-widget tone-${meta.tone || "primary"}`;
      node.classList.add("visible");
    }
    node.dataset.state = stateKey;
    node.dataset.phase = phase;
    node.classList.toggle("phase-compact", phase === "COMPACT");
    fillCopySlots(node, envelope, stateKey);
    syncWidgetMotion(node, envelope, familyName, created);
    node.classList.remove("exit");
    if (created) requestAnimationFrame(() => node.classList.add("visible"));
    else node.classList.add("visible");
    if (phase === "RESULT") {
      const hold = envelope.presentation?.minHoldMs || DEFAULT_HOLD_MS;
      clearTimeout(node._exitTimer);
      node._exitTimer = setTimeout(() => this.hide(key), hold);
    } else {
      clearTimeout(node._exitTimer);
    }
    return node;
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

  _create(stateKey, familyName) {
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
    layerRootForFamily(familyName).appendChild(node);
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

export function v4FixtureLapComplete(sequence = 1) {
  return {
    type: "event",
    format: "v4",
    schemaVersion: "1.0",
    eventId: "demo:lap:1",
    sequence,
    sessionId: "session:demo",
    eventType: "LAP_COMPLETE",
    mode: "RACE",
    phase: "RESULT",
    priority: 40,
    dedupeKey: "RACE:LAP_COMPLETE:12",
    correlationId: "lap:12",
    metrics: { lap: 12, lapTime: 112.084, bestLap: 112.402, deltaToBest: -0.318 },
    copy: { headlineToken: "lap.complete", statusToken: "" },
    presentation: {
      widget: "timing",
      zone: "EVENT",
      variant: "lap_complete",
      accent: "primary",
      preferredState: "RESULT",
      minHoldMs: 6000,
    },
  };
}

export function v4FixtureHunting(sequence = 1, phase = "ACTIVE") {
  return {
    type: "event",
    format: "v4",
    schemaVersion: "1.0",
    eventId: "demo:battle:hunting",
    sequence,
    sessionId: "session:demo",
    eventType: "HUNTING",
    mode: "RACE",
    phase,
    priority: 20,
    dedupeKey: "RACE:battle:hunting",
    correlationId: "battle:hunting",
    metrics: { gap: 0.84, closingRate: 0.34, targetPosition: 7, targetCarIdx: 17 },
    copy: { headlineToken: "battle.hunting", statusToken: "" },
    presentation: {
      widget: "battle",
      zone: "EVENT",
      variant: "hunting",
      accent: "primary",
      preferredState: "ACTIVE",
    },
  };
}

export function v4FixtureHunted(sequence = 2, phase = "ACTIVE") {
  return {
    type: "event",
    format: "v4",
    schemaVersion: "1.0",
    eventId: "demo:battle:hunted",
    sequence,
    sessionId: "session:demo",
    eventType: "HUNTED",
    mode: "RACE",
    phase,
    priority: 20,
    dedupeKey: "RACE:battle:hunted",
    correlationId: "battle:hunted",
    metrics: { gap: 0.62, closingRate: 0.21, targetPosition: 8, targetCarIdx: 23 },
    copy: { headlineToken: "battle.hunted", statusToken: "" },
    presentation: {
      widget: "battle",
      zone: "EVENT",
      variant: "hunted",
      accent: "warning",
      preferredState: "ACTIVE",
    },
  };
}

export function v4FixturePositionGained(sequence = 1) {
  return {
    type: "event",
    format: "v4",
    schemaVersion: "1.0",
    eventId: "demo:position:gained",
    sequence,
    sessionId: "session:demo",
    eventType: "POSITION_GAINED",
    mode: "RACE",
    phase: "RESULT",
    priority: 70,
    dedupeKey: "RACE:POSITION_GAINED:7",
    correlationId: "position:gain:7",
    metrics: { direction: "gain", oldPosition: 8, newPosition: 7, delta: 1 },
    copy: { headlineToken: "position.gained", statusToken: "" },
    presentation: {
      widget: "position",
      zone: "EVENT",
      variant: "position_gained",
      accent: "primary",
      preferredState: "RESULT",
      minHoldMs: 4000,
    },
  };
}

export function v4FixturePositionLost(sequence = 1) {
  return {
    type: "event",
    format: "v4",
    schemaVersion: "1.0",
    eventId: "demo:position:lost",
    sequence,
    sessionId: "session:demo",
    eventType: "POSITION_LOST",
    mode: "RACE",
    phase: "RESULT",
    priority: 70,
    dedupeKey: "RACE:POSITION_LOST:8",
    correlationId: "position:loss:8",
    metrics: { direction: "loss", oldPosition: 7, newPosition: 8, delta: -1 },
    copy: { headlineToken: "position.lost", statusToken: "" },
    presentation: {
      widget: "position",
      zone: "EVENT",
      variant: "position_lost",
      accent: "warning",
      preferredState: "RESULT",
      minHoldMs: 4000,
    },
  };
}

export function v4FixtureOvertake(sequence = 1) {
  return {
    type: "event",
    format: "v4",
    schemaVersion: "1.0",
    eventId: "demo:position:overtake",
    sequence,
    sessionId: "session:demo",
    eventType: "OVERTAKE",
    mode: "RACE",
    phase: "RESULT",
    priority: 80,
    dedupeKey: "RACE:OVERTAKE:6",
    correlationId: "overtake:6",
    metrics: { oldPosition: 7, newPosition: 6, targetCarIdx: 17 },
    copy: { headlineToken: "position.overtake", statusToken: "" },
    presentation: {
      widget: "position",
      zone: "EVENT",
      variant: "overtake",
      accent: "primary",
      preferredState: "RESULT",
      minHoldMs: 5000,
    },
  };
}

export function v4FixturePitEntry(sequence = 1, phase = "ENTER") {
  return {
    type: "event",
    format: "v4",
    schemaVersion: "1.0",
    eventId: "demo:pit:entry",
    sequence,
    sessionId: "session:demo",
    eventType: "PIT_ENTRY",
    mode: "RACE",
    phase,
    priority: 50,
    dedupeKey: "RACE:PIT_ENTRY:7",
    correlationId: "pit:7",
    metrics: { position: 7 },
    copy: { headlineToken: "pit.entry", statusToken: "" },
    presentation: {
      widget: "pit",
      zone: "EVENT",
      variant: "pit_entry",
      accent: "warning",
      preferredState: "ENTER",
      minHoldMs: 5000,
    },
  };
}

export function v4FixtureHrPressure(sequence = 1, phase = "ACTIVE") {
  return {
    type: "event",
    format: "v4",
    schemaVersion: "1.0",
    eventId: "demo:bio:hr",
    sequence,
    sessionId: "session:demo",
    eventType: "HR_PRESSURE_RISING",
    mode: "RACE",
    phase,
    priority: 35,
    dedupeKey: "RACE:HR_PRESSURE",
    correlationId: "bio:hr",
    metrics: { bpm: 164, deltaBpm: 14, intensity: 72 },
    copy: { headlineToken: "bio.hr_high", statusToken: "" },
    presentation: {
      widget: "bio",
      zone: "EVENT",
      variant: "hr_pressure",
      accent: "warning",
      preferredState: "ACTIVE",
    },
  };
}
