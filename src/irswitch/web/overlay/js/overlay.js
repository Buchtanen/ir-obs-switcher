import { DisplayManager, applySysinfo, applyPersistentArt } from "./display.js";

/** Bump with index.html ?v= so OBS CEF does not keep stale JS/CSS. */
const OVERLAY_ASSET_VER = "1.2.17";

const BACKOFF = [1000, 2000, 5000, 10000];

function fixtureHud() {
  return (
    Boolean(window.__demoMode) ||
    document.documentElement.classList.contains("golden-layout") ||
    document.documentElement.classList.contains("preview-layout")
  );
}

function hudIdle() {
  return document.documentElement.classList.contains("overlay-idle");
}

function armHud(live) {
  if (fixtureHud()) {
    document.documentElement.classList.remove("overlay-idle");
    return;
  }
  const nextIdle = !live;
  document.documentElement.classList.toggle("overlay-idle", nextIdle);
  if (nextIdle) {
    window.__v4Display?.clear?.();
    DisplayManager.clear();
  }
}

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/overlay`;
}

function applyTheme(theme) {
  const id = theme || "cyber_racing";
  const link = document.getElementById("theme-css");
  if (link) link.href = `/overlay/static/css/themes/${id}.css?v=${OVERLAY_ASSET_VER}`;
  document.documentElement.dataset.theme = id;
}

function applyPresentation(msg) {
  if (msg.theme) {
    applyTheme(msg.theme);
    window.__overlayTheme = msg.theme;
  }
  if (msg.assets) {
    window.__assets = msg.assets;
    if (window.__renderer === "v4") {
      window.__v4Display?.refresh?.({ theme: msg.theme || window.__overlayTheme });
    } else {
      applyPersistentArt();
      DisplayManager.refreshArt();
    }
  }
}

function updateSysinfo(system, bio) {
  applySysinfo(system, bio);
  window.__v4SyncSysinfoGlow?.();
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
      if (useV4 && !hudIdle()) window.__v4Display?.applyStateSnapshot?.(msg.activeStories || []);
      return;
    }
    if (msg.type === "state") {
      if (msg.domain === "race") {
        window.__race = msg.data;
        armHud(Boolean(msg.data && msg.data.connected));
      }
      if (msg.domain === "bio") {
        window.__bio = msg.data;
        updateSysinfo(window.__system || {}, msg.data);
      }
      if (msg.domain === "system") {
        window.__system = msg.data;
        updateSysinfo(msg.data, window.__bio);
      }
      return;
    }
    if (msg.type === "event") {
      if (hudIdle()) return;
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
  armHud(Boolean(msg.race && msg.race.connected));
  if (msg.bio) window.__bio = msg.bio;
  if (msg.system) {
    window.__system = msg.system;
    updateSysinfo(msg.system, window.__bio);
  }
  if (msg.bio) updateSysinfo(window.__system || {}, msg.bio);
  if (!events || hudIdle()) return;
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
      armHud(false);
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

async function startV4Golden(params, v4) {
  const {
    DisplayV4,
    getV4GoldenFixture,
    renderV4GoldenGallery,
    v4FixtureHunted,
    v4FixtureHunting,
  } = v4;
  const fixture = params.get("fixture");
  const showGallery = !fixture || fixture === "all";
  if (showGallery) {
    renderV4GoldenGallery(DisplayV4);
    return;
  }
  if (fixture === "battle_stack") {
    DisplayV4.show(v4FixtureHunting(1, "ACTIVE"));
    DisplayV4.show(v4FixtureHunted(1, "ACTIVE"));
    return;
  }
  const envelope = getV4GoldenFixture(fixture);
  if (envelope) {
    DisplayV4.show(envelope);
    return;
  }
  DisplayV4.show(getV4GoldenFixture("lap_complete"));
}

async function startV4Demo(params) {
  const v4 = await import(`./display-v4.js?v=${OVERLAY_ASSET_VER}`);
  const {
    DisplayV4,
    initV4,
    getV4GoldenFixture,
    v4FixtureHunted,
    v4FixtureHunting,
    v4FixturePitEntry,
    v4FixtureHrPressure,
  } = v4;
  window.__v4Display = DisplayV4;
  window.__v4SyncSysinfoGlow = v4.syncSysinfoGlow;
  const theme = params.get("theme") || window.__overlayTheme || "cyber_racing";
  try {
    await initV4({
      theme,
      language: window.__overlayLanguage || "en",
      manifestUrl: window.__v4ManifestUrl,
      catalogUrl: window.__v4CatalogUrl,
      copyCatalog: window.__v4CopyCatalog,
      resolvedMotions: window.__v4ResolvedMotions,
      resolvedStates: window.__v4ResolvedStates,
      motionDisabled: params.get("motion") === "off",
    });
  } catch (err) {
    console.error("v4 demo init failed", err);
    document.documentElement.dataset.v4Manifest = "fallback";
  }
  const layout = params.get("layout");
  if (layout === "golden") {
    await startV4Golden(params, v4);
    return;
  }
  // Explicit fixture → frozen snapshot. No fixture → cyclic V4 dry-test loop.
  const fixture = params.get("fixture");
  if (!fixture) {
    if (layout === "preview") {
      DisplayV4.show(getV4GoldenFixture("lap_complete"));
      return;
    }
    const mod = await import(`./demo-v4.js?v=${OVERLAY_ASSET_VER}`);
    mod.startV4DemoLoop();
    return;
  }
  if (fixture === "hunting") {
    DisplayV4.show(v4FixtureHunting(1, "ENTER"));
    DisplayV4.show(v4FixtureHunting(2, "ACTIVE"));
    return;
  }
  if (fixture === "hunted") {
    DisplayV4.show(v4FixtureHunted(1, "ENTER"));
    DisplayV4.show(v4FixtureHunted(2, "ACTIVE"));
    return;
  }
  if (fixture === "battle_stack") {
    DisplayV4.show(v4FixtureHunting(1, "ACTIVE"));
    DisplayV4.show(v4FixtureHunted(1, "ACTIVE"));
    return;
  }
  if (fixture === "pit_entry") {
    DisplayV4.show(v4FixturePitEntry(1, "ENTER"));
    DisplayV4.show(v4FixturePitEntry(2, "ACTIVE"));
    return;
  }
  if (fixture === "hr_pressure") {
    DisplayV4.show(v4FixtureHrPressure(1, "ENTER"));
    DisplayV4.show(v4FixtureHrPressure(2, "ACTIVE"));
    return;
  }
  const envelope = getV4GoldenFixture(fixture);
  if (envelope) {
    DisplayV4.show(envelope);
    return;
  }
  const mod = await import(`./demo-v4.js?v=${OVERLAY_ASSET_VER}`);
  mod.startV4DemoLoop();
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
        window.__v4CopyCatalog = snap.v4.copyCatalog;
        window.__v4ResolvedMotions = snap.v4.resolved?.motions;
        window.__v4ResolvedStates = snap.v4.resolved?.states;
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
    const { DisplayV4, initV4, syncSysinfoGlow } = await import(
      `./display-v4.js?v=${OVERLAY_ASSET_VER}`
    );
    window.__v4Display = DisplayV4;
    window.__v4SyncSysinfoGlow = syncSysinfoGlow;
    try {
      await initV4({
        theme: theme || window.__overlayTheme || "cyber_racing",
        language: window.__overlayLanguage || "en",
        manifestUrl: window.__v4ManifestUrl,
        catalogUrl: window.__v4CatalogUrl,
        copyCatalog: window.__v4CopyCatalog,
        resolvedMotions: window.__v4ResolvedMotions,
        resolvedStates: window.__v4ResolvedStates,
        motionDisabled: params.get("motion") === "off",
      });
    } catch (err) {
      console.error("v4 init failed", err);
      document.documentElement.dataset.v4Manifest = "fallback";
      document.getElementById("sysinfo-widget")?.classList.add("fallback");
    } finally {
      if (demo) {
        // Demo path: startV4Demo may re-init; do not open live WS.
      } else {
        connectOverlay();
      }
    }
    if (demo) {
      try {
        await startV4Demo(params);
      } catch (err) {
        console.error("v4 demo failed", err);
      }
      return;
    }
    return;
  }
  if (demo) {
    const layout = params.get("layout");
    const mod = await import(`./demo.js?v=${OVERLAY_ASSET_VER}`);
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
