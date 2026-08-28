/** V4 overlay renderer (S1: timing + battle families). */

const ASSET_BASE = "/overlay/web/";
const DEFAULT_HOLD_MS = 4000;
const FAMILY_CAPS = { battle: 2, timing: 1, position: 1, exception: 1, pit: 1, bio: 1, session: 1 };

const COPY_EN = {
  "lap.complete": "LAP COMPLETE",
  "lap.personal_best": "PERSONAL BEST",
  "battle.hunting": "HUNTING",
  "battle.hunted": "UNDER ATTACK",
  "battle.closing_in": "CLOSING IN",
  "battle.approach": "APPROACH",
  "battle.attack_range": "ATTACK RANGE",
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

function resolveCopy(token) {
  if (!token) return "";
  return COPY_EN[token] || token;
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

function fillCopySlots(node, envelope, stateKey) {
  const sample = manifest?.states?.[stateKey]?.sample || {};
  const metrics = envelope.metrics || {};
  const copy = envelope.copy || {};
  const familyName = familyForState(stateKey);
  if (familyName === "battle") {
    fillBattleCopy(node, envelope, stateKey, sample, metrics, copy);
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
  const manifestUrl = options.manifestUrl || `${ASSET_BASE}themes-v4/manifest.json`;
  const catalogUrl = options.catalogUrl || `${ASSET_BASE}themes-v4/event_catalog.json`;
  const [manifestRes, catalogRes] = await Promise.all([fetch(manifestUrl), fetch(catalogUrl)]);
  if (manifestRes.ok) manifest = await manifestRes.json();
  if (catalogRes.ok) catalog = await catalogRes.json();
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
