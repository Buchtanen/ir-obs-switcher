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
    DisplayManager.refreshArt();
  }
}

function applySnapshot(msg, { events = true } = {}) {
  applyPresentation(msg);
  if (msg.race) window.__race = msg.race;
  if (msg.bio) window.__bio = msg.bio;
  if (msg.system) {
    window.__system = msg.system;
    applySysinfo(msg.system, window.__bio);
  }
  if (msg.bio) applySysinfo(window.__system || {}, msg.bio);
  if (events) (msg.activeEvents || []).forEach((ev) => DisplayManager.show(ev));
}

function onMessage(msg) {
  if (msg.type === "snapshot") {
    applySnapshot(msg);
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
    DisplayManager.show(msg);
    return;
  }
  if (msg.type === "activeEvents") {
    return;
  }
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

async function bootstrap() {
  const params = demoParams();
  const demo = params.has("demo");
  const theme = params.get("theme");
  try {
    const res = await fetch("/api/overlay/snapshot");
    if (res.ok) {
      const snap = await res.json();
      if (theme) {
        snap.theme = theme;
        snap.assets = remapThemeAssets(snap.assets, theme);
      }
      applySnapshot(snap, { events: !demo });
    }
  } catch (err) {
    // WS snapshot is the fallback
  }
  if (theme) applyTheme(theme);
  if (demo) {
    const { startDemo } = await import("./demo.js");
    startDemo();
    return;
  }
  connectOverlay();
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", bootstrap);
} else {
  bootstrap();
}
