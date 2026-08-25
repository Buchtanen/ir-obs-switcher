import { DisplayManager, applySysinfo } from "./display.js";

const LOOP_MS = 28000;

function cue(label) {
  if (window.parent && window.parent !== window) {
    window.parent.postMessage({ type: "overlay-demo-cue", label }, "*");
  }
}

function later(ms, fn, bag) {
  const id = setTimeout(fn, ms);
  bag.push(id);
  return id;
}

function keyOf(event) {
  const channel = event.channel || "alert";
  const token = event.data && event.data.state ? event.data.state : event.name;
  return `${channel}:${token}`;
}

function show(event) {
  DisplayManager.show({ type: "event", phase: "enter", ...event });
}

function hide(event, bag, afterMs) {
  later(afterMs, () => DisplayManager.hide(keyOf(event)), bag);
}

function mockSystem(elapsed) {
  const load = 42 + 12 * Math.sin(elapsed / 4);
  return {
    cpu: { load, temperature: 64, power: 95, frequency: 5.12 },
    gpu: {
      load: 71 + 6 * Math.sin(elapsed / 5),
      temperature: 67,
      power: 248,
      clock: 2110,
      vram_used: 10.4,
      vram_total: 24,
    },
    memory: { used: 18.2, total: 32, percent: 57 },
    performance: { fps: 91, frametime: 11.0 },
  };
}

function mockBio(elapsed) {
  const bpm = Math.round(122 + 22 * (0.5 + 0.5 * Math.sin(elapsed / 6)));
  const delta = bpm - 118;
  return {
    connected: true,
    status: "connected",
    bpm,
    baseline_bpm: 118,
    delta_bpm: delta,
    state: delta >= 25 ? "high" : delta >= 15 ? "pushing" : "focused",
  };
}

const HUNTING = {
  name: "battle",
  channel: "battle",
  data: { state: "hunting", targetPosition: 6, gap: 2.81, closingRate: 0.34 },
};
const HUNTED = {
  name: "battle",
  channel: "battle",
  data: { state: "hunted", targetPosition: 8, gap: 1.42, closingRate: 0.21 },
};
const LAP = {
  name: "lap_complete",
  channel: "lap",
  data: { lap: 12, lapTime: 94.372, deltaToBest: -0.318 },
};
const PB = {
  name: "personal_best",
  channel: "lap",
  data: { lap: 12, lapTime: 94.372 },
};
const GAIN = {
  name: "position_change",
  channel: "alert",
  data: { direction: "gain", oldPosition: 8, newPosition: 7, delta: 1 },
};
const INCIDENT = {
  name: "incident",
  channel: "alert",
  data: { value: 2, total: 5 },
};
const HR = {
  name: "heart_rate",
  channel: "bio",
  data: { bpm: 147, delta: 28, state: "high" },
};
const FINAL = { name: "final_lap", channel: "session", data: { lap: 20 } };
const FINISH = {
  name: "finish",
  channel: "session",
  data: { position: 5, classPosition: 3 },
};

let timers = [];
let vitalsTimer = 0;
let loopTimer = 0;
let huntingTimer = 0;
let startedAt = 0;

function stopTimers() {
  timers.forEach(clearTimeout);
  timers = [];
  if (vitalsTimer) clearInterval(vitalsTimer);
  if (loopTimer) clearTimeout(loopTimer);
  if (huntingTimer) clearInterval(huntingTimer);
  vitalsTimer = 0;
  loopTimer = 0;
  huntingTimer = 0;
}

function tickVitals() {
  const elapsed = (performance.now() - startedAt) / 1000;
  applySysinfo(mockSystem(elapsed), mockBio(elapsed));
}

function playOnce() {
  cue("HUNTING");
  show(HUNTING);
  huntingTimer = setInterval(() => {
    const elapsed = (performance.now() - startedAt) / 1000;
    const gap = Math.max(0.86, 2.81 - elapsed * 0.12);
    show({
      ...HUNTING,
      data: { ...HUNTING.data, gap },
    });
  }, 250);

  later(700, () => {
    cue("HUNTED");
    show(HUNTED);
  }, timers);

  later(2400, () => {
    cue("LAP COMPLETE");
    show(LAP);
    hide(LAP, timers, 4000);
  }, timers);

  later(6800, () => {
    cue("PERSONAL BEST");
    show(PB);
    hide(PB, timers, 4000);
  }, timers);

  later(11200, () => {
    cue("POSITION +1");
    show(GAIN);
    hide(GAIN, timers, 3500);
  }, timers);

  later(15000, () => {
    cue("INCIDENT");
    show(INCIDENT);
    hide(INCIDENT, timers, 3500);
  }, timers);

  later(16800, () => {
    cue("HEART RATE");
    show(HR);
    hide(HR, timers, 4000);
  }, timers);

  later(19000, () => {
    cue("FINAL LAP");
    show(FINAL);
    hide(FINAL, timers, 4000);
  }, timers);

  later(23500, () => {
    cue("FINISH");
    show(FINISH);
    hide(FINISH, timers, 4000);
  }, timers);
}

export function stopDemo() {
  stopTimers();
  DisplayManager.clear();
  cue("");
}

export function startDemo() {
  stopDemo();
  startedAt = performance.now();
  tickVitals();
  vitalsTimer = setInterval(tickVitals, 400);
  playOnce();
  const params = new URLSearchParams(location.search);
  const loop = params.get("loop") !== "0";
  if (loop) {
    loopTimer = setTimeout(() => startDemo(), LOOP_MS);
  }
}
