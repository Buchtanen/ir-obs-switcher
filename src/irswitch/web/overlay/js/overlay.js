import { DisplayManager, applySysinfo, applyPersistentArt } from "./display.js";

const BACKOFF = [1000, 2000, 5000, 10000];

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/overlay`;
}

function applyTheme(theme) {
  const id = theme || "cyber_racing";
  const link = document.getElementById("theme-css");
  if (link) link.href = `/overlay/static/css/themes/${id}.css`;
}

function applyPresentation(msg) {
  if (msg.theme) applyTheme(msg.theme);
  if (msg.assets) {
    window.__assets = msg.assets;
    applyPersistentArt();
    if (window.__renderer === "v4") {
      window.__v4Display?.refresh?.();
    } else {
      DisplayManager.refreshArt();
    }
  }
}

function legacyFromV4(envelope) {
  const eventType = String(envelope.eventType || "").toLowerCase();
  let name = eventType.replace(/_/g, " ");
  if (eventType === "lap_complete") name = "lap_complete";
  if (eventType === "personal_best") name = "personal_best";
  const phaseRaw = String(envelope.phase || "RESULT").toUpperCase();
  const phase = phaseRaw === "EXIT" ? "exit" : phaseRaw === "RESULT" ? "trigger" : phaseRaw.toLowerCase();
  const metrics = envelope.metrics || {};
  const channel =
    name.includes("lap") || name === "personal_best"
      ? "lap"
      : envelope.presentation?.widget === "battle"
        ? "battle"
        : "alert";
  return {
    type: "event",
    name,
    phase,
    channel,
    priority: envelope.priority || 0,
    timestamp: (envelope.monotonicMs || 0) / 1000,
    data: { ...metrics, state: envelope.presentation?.variant },
  };
}

function createMessageHandler(useV4) {
  return function onMessage(msg) {
    if (msg.type === "snapshot") {
      applySnapshot(msg, { events: !window.__demoMode });
      return;
    }
    if (msg.type === "STATE_SNAPSHOT") {
      if (useV4) window.__v4Display?.applyStateSnapshot?.(msg.activeStories || []);
      return;
    }
    if (msg.type === "state") {
      if (msg.domain === "race") window.__race = msg.data;
      if (msg.domain === "bio") {
        window.__bio = msg.data;
        applySysinfo(window.__system || {}, msg.data);
      }
      if (msg.domain === "system") {
        window.__system = msg.data;
        applySysinfo(msg.data, window.__bio);
      }
      return;
    }
    if (msg.type === "event") {
      if (msg.format === "v4") {
        if (useV4) window.__v4Display?.show?.(msg);
        else DisplayManager.show(legacyFromV4(msg));
        return;
      }
      if (!useV4) DisplayManager.show(msg);
      return;
    }
    if (msg.type === "activeEvents") {
      return;
    }
  };
}

let onMessage = createMessageHandler(false);

function applySnapshot(msg, { events = true } = {}) {
  applyPresentation(msg);
  if (msg.race) window.__race = msg.race;
  if (msg.bio) window.__bio = msg.bio;
  if (msg.system) {
    window.__system = msg.system;
    applySysinfo(msg.system, window.__bio);
  }
  if (msg.bio) applySysinfo(window.__system || {}, msg.bio);
  if (!events) return;
  if (window.__renderer === "v4") return;
  (msg.activeEvents || []).forEach((ev) => DisplayManager.show(ev));
}

export function connectOverlay() {
  let attempt = 0;
  let socket;

  function connect() {
    socket = new WebSocket(wsUrl());
    socket.onopen = () => {
      attempt = 0;
    };
    socket.onmessage = (ev) => {
      try {
        onMessage(JSON.parse(ev.data));
      } catch (err) {
        // ignore malformed
      }
    };
    socket.onclose = () => {
      const wait = BACKOFF[Math.min(attempt, BACKOFF.length - 1)];
      attempt += 1;
      setTimeout(connect, wait);
    };
    socket.onerror = () => {
      socket.close();
    };
  }
  connect();
}

function remapThemeAssets(assets, theme) {
  const next = {};
  Object.entries(assets || {}).forEach(([slot, rel]) => {
    next[slot] = rel ? String(rel).replace(/themes\/[^/]+\//, `themes/${theme}/`) : rel;
  });
  return next;
}

function demoParams() {
  return new URLSearchParams(location.search);
}

async function startV4Demo(params) {
  const { DisplayV4, initV4, v4FixtureLapComplete } = await import("./display-v4.js");
  window.__v4Display = DisplayV4;
  const theme = params.get("theme") || window.__overlayTheme || "cyber_racing";
  await initV4({
    theme,
    language: window.__overlayLanguage || "en",
    manifestUrl: window.__v4ManifestUrl,
    catalogUrl: window.__v4CatalogUrl,
  });
  const layout = params.get("layout");
  const fixture = params.get("fixture") || "lap_complete";
  if (layout === "golden" || layout === "preview" || fixture === "lap_complete") {
    DisplayV4.show(v4FixtureLapComplete());
    return;
  }
  const mod = await import("./demo.js");
  mod.startDemo();
}

async function bootstrap() {
  const params = demoParams();
  const demo = params.has("demo");
  window.__demoMode = demo;
  const theme = params.get("theme");
  const rendererParam = params.get("renderer");
  let useV4 = rendererParam === "v4";
  try {
    const res = await fetch("/api/overlay/snapshot");
    if (res.ok) {
      const snap = await res.json();
      if (theme) {
        snap.theme = theme;
        snap.assets = remapThemeAssets(snap.assets, theme);
      }
      window.__overlayTheme = snap.theme;
      if (snap.v4) {
        window.__v4ManifestUrl = snap.v4.manifestUrl;
        window.__v4CatalogUrl = snap.v4.catalogUrl;
        window.__overlayLanguage = snap.v4.language;
        if (snap.v4.renderer) useV4 = true;
      }
      applySnapshot(snap, { events: !demo });
    }
  } catch (err) {
    // WS snapshot is the fallback
  }
  if (theme) applyTheme(theme);
  if (useV4) {
    window.__renderer = "v4";
    onMessage = createMessageHandler(true);
    const { DisplayV4, initV4 } = await import("./display-v4.js");
    window.__v4Display = DisplayV4;
    await initV4({
      theme: theme || window.__overlayTheme || "cyber_racing",
      language: window.__overlayLanguage || "en",
      manifestUrl: window.__v4ManifestUrl,
      catalogUrl: window.__v4CatalogUrl,
    });
    if (demo) {
      await startV4Demo(params);
      return;
    }
    connectOverlay();
    return;
  }
  if (demo) {
    const layout = params.get("layout");
    const mod = await import("./demo.js");
    if (layout === "golden") {
      mod.startGoldenLayout();
    } else if (layout === "preview") {
      mod.startPreviewLayout();
    } else if (layout === "qa") {
      mod.startQaLayout("lap");
    } else if (layout === "qa-finish") {
      mod.startQaLayout("finish");
    } else {
      mod.startDemo();
    }
    return;
  }
  connectOverlay();
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", bootstrap);
} else {
  bootstrap();
}
