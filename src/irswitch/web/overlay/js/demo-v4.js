/**
 * V4 cyclic dry-test demo — DisplayV4 envelopes on a ~28s loop.
 * Mirrors demo.js beat order; parent page reads overlay-demo-cue postMessages.
 */
import { applySysinfo } from "./display.js?v=1.2.16";
import {
  DisplayV4,
  syncSysinfoGlow,
  v4FixtureFinish,
  v4FixtureFinalLap,
  v4FixtureHrPressure,
  v4FixtureHunted,
  v4FixtureHunting,
  v4FixtureIncident,
  v4FixtureLapComplete,
  v4FixturePersonalBest,
  v4FixturePositionGained,
} from "./display-v4.js?v=1.2.16";

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

function withHold(envelope, holdMs) {
  return {
    ...envelope,
    presentation: {
      ...(envelope.presentation || {}),
      minHoldMs: holdMs,
    },
  };
}

function huntingTick(sequence, gap) {
  const base = v4FixtureHunting(sequence, "ACTIVE");
  return {
    ...base,
    metrics: { ...base.metrics, gap },
  };
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

let timers = [];
let vitalsTimer = 0;
let loopTimer = 0;
let huntingTimer = 0;
let startedAt = 0;
let seq = 1;

function nextSeq() {
  seq += 1;
  return seq;
}

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
  syncSysinfoGlow();
}

function show(envelope) {
  DisplayV4.show(envelope);
}

function showThenExit(factory, holdMs, phase = "ACTIVE") {
  const enterSeq = nextSeq();
  show(withHold(factory(enterSeq, phase), holdMs));
  later(
    holdMs,
    () => {
      show({ ...factory(nextSeq(), "EXIT"), phase: "EXIT" });
    },
    timers,
  );
}

function exitStory(factory) {
  show({ ...factory(nextSeq(), "EXIT"), phase: "EXIT" });
}

function playOnce() {
  cue("HUNTING");
  show(v4FixtureHunting(nextSeq(), "ENTER"));
  show(v4FixtureHunting(nextSeq(), "ACTIVE"));
  huntingTimer = setInterval(() => {
    const elapsed = (performance.now() - startedAt) / 1000;
    const gap = Math.max(0.86, 2.81 - elapsed * 0.12);
    show(huntingTick(nextSeq(), Number(gap.toFixed(2))));
  }, 250);

  later(
    700,
    () => {
      cue("HUNTED");
      show(v4FixtureHunted(nextSeq(), "ENTER"));
      show(v4FixtureHunted(nextSeq(), "ACTIVE"));
    },
    timers,
  );

  later(
    2400,
    () => {
      cue("LAP COMPLETE");
      show(withHold(v4FixtureLapComplete(nextSeq()), 4000));
    },
    timers,
  );

  later(
    6800,
    () => {
      cue("PERSONAL BEST");
      show(withHold(v4FixturePersonalBest(nextSeq()), 4000));
    },
    timers,
  );

  later(
    11200,
    () => {
      cue("POSITION +1");
      show(withHold(v4FixturePositionGained(nextSeq()), 3500));
      exitStory(v4FixtureHunting);
      exitStory(v4FixtureHunted);
      if (huntingTimer) {
        clearInterval(huntingTimer);
        huntingTimer = 0;
      }
    },
    timers,
  );

  later(
    15000,
    () => {
      cue("INCIDENT");
      showThenExit(v4FixtureIncident, 3500, "ACTIVE");
    },
    timers,
  );

  later(
    16800,
    () => {
      cue("HEART RATE");
      show(v4FixtureHrPressure(nextSeq(), "ENTER"));
      showThenExit(v4FixtureHrPressure, 4000, "ACTIVE");
    },
    timers,
  );

  later(
    19000,
    () => {
      cue("FINAL LAP");
      showThenExit(v4FixtureFinalLap, 4000, "ACTIVE");
    },
    timers,
  );

  later(
    23500,
    () => {
      cue("FINISH");
      show(withHold(v4FixtureFinish(nextSeq()), 4000));
    },
    timers,
  );
}

export function stopV4Demo() {
  stopTimers();
  DisplayV4.clear();
  cue("");
}

/**
 * Start the V4 cyclic dry-test loop.
 * @param {{ loop?: boolean }} [options]
 */
export function startV4DemoLoop(options = {}) {
  stopV4Demo();
  startedAt = performance.now();
  seq = 1;
  tickVitals();
  vitalsTimer = setInterval(tickVitals, 400);
  playOnce();
  const params = new URLSearchParams(location.search);
  const loop = options.loop !== false && params.get("loop") !== "0";
  if (loop) {
    loopTimer = setTimeout(() => startV4DemoLoop(options), LOOP_MS);
  }
}
