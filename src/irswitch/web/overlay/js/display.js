const CHANNELS = {
  battle: { cap: 2, layer: "battle-stack" },
  lap: { cap: 1, layer: "event-layer" },
  alert: { cap: 1, layer: "event-layer" },
  session: { cap: 1, layer: "session-layer" },
  bio: { cap: 1, layer: "bio-expanded" },
  system: { cap: 1, layer: "event-layer" },
};

function text(el, value) {
  el.textContent = value == null ? "—" : String(value);
}

function fmt(n, digits) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

function lerp(a, b, t) {
  if (a == null || b == null) return b;
  return a + (b - a) * t;
}

export const DisplayManager = {
  active: new Map(),

  show(event) {
    const channel = event.channel || "alert";
    const key = `${channel}:${event.data && event.data.state ? event.data.state : event.name}`;
    let node = this.active.get(key);
    if (!node) {
      node = this._create(event, channel);
      this.active.set(key, node);
    }
    this._fill(node, event);
    node.classList.remove("exit");
    requestAnimationFrame(() => node.classList.add("visible"));
    if (event.phase === "exit") this.hide(key);
    return node;
  },

  hide(key) {
    const node = this.active.get(key);
    if (!node) return;
    node.classList.add("exit");
    node.classList.remove("visible");
    setTimeout(() => {
      node.remove();
      this.active.delete(key);
    }, 400);
  },

  _create(event, channel) {
    const spec = CHANNELS[channel] || CHANNELS.alert;
    const layer = document.getElementById(spec.layer);
    const node = document.createElement("div");
    node.className = `widget ${event.data && event.data.state ? event.data.state : event.name}`;
    node.dataset.key = `${channel}:${event.name}`;
    layer.appendChild(node);
    return node;
  },

  _fill(node, event) {
    const data = event.data || {};
    const kicker = document.createElement("div");
    kicker.className = "kicker";
    const title = document.createElement("div");
    title.className = "title";
    const meta = document.createElement("div");
    meta.className = "meta";
    const name = event.name;
    const state = data.state;
    if (name === "battle" && state === "hunting") {
      text(kicker, "CLOSING IN");
      text(title, "HUNTING");
      text(meta, `P${data.targetPosition ?? "—"}  +${fmt(data.gap, 2)}`);
    } else if (name === "battle" && state === "hunted") {
      text(kicker, "UNDER PRESSURE");
      text(title, "HUNTED");
      text(meta, `P${data.targetPosition ?? "—"}  -${fmt(data.gap, 2)}`);
    } else if (name === "lap_complete") {
      text(kicker, `LAP ${data.lap ?? ""}`);
      text(title, "LAP COMPLETE");
      text(meta, `${fmt(data.lapTime, 3)}  ${fmt(data.deltaToBest, 3)}`);
    } else if (name === "personal_best") {
      text(kicker, "STOPWATCH");
      text(title, "PERSONAL BEST");
      text(meta, `${fmt(data.lapTime, 3)}`);
    } else if (name === "position_change") {
      text(kicker, data.direction === "gain" ? "POSITION GAINED" : "POSITION LOST");
      text(title, data.direction === "gain" ? `+${Math.abs(data.delta || 1)} POS` : `${data.delta} POS`);
      text(meta, `P${data.oldPosition} → P${data.newPosition}`);
    } else if (name === "incident") {
      text(kicker, "INCIDENT");
      text(title, `+${data.value}`);
      text(meta, `TOTAL ${data.total}`);
    } else if (name === "pit_entry") {
      text(kicker, "PITS");
      text(title, "PIT ENTRY");
      text(meta, "");
    } else if (name === "pit_exit") {
      text(kicker, "TRACK");
      text(title, "BACK ON TRACK");
      text(meta, data.position != null ? `P${data.position}` : "");
    } else if (name === "final_lap") {
      text(kicker, "FLAG");
      text(title, "FINAL LAP");
      text(meta, "ONE MORE PUSH");
    } else if (name === "finish") {
      text(kicker, "CHECKERED");
      text(title, "FINISH");
      text(meta, `P${data.position ?? "—"}  P${data.classPosition ?? "—"} IN CLASS`);
    } else if (name === "heart_rate") {
      text(kicker, "HEART RATE");
      text(title, `${data.bpm ?? "—"} BPM`);
      text(meta, data.delta != null ? `+${data.delta}` : "");
    } else if (name === "ble_lost") {
      text(kicker, "SENSOR");
      text(title, "HEART SENSOR LOST");
      text(meta, "RECONNECTING");
    } else {
      text(kicker, (event.channel || "").toUpperCase());
      text(title, String(name || "").replaceAll("_", " ").toUpperCase());
      text(meta, "");
    }
    node.replaceChildren(kicker, title, meta);
  },
};

export function applySysinfo(system, bio) {
  const cpu = (system && system.cpu) || {};
  const gpu = (system && system.gpu) || {};
  const mem = (system && system.memory) || {};
  const perf = (system && system.performance) || {};
  setMod("cpu-load", fmt(cpu.load, 0) + "%", cpu.load, 85, 95);
  setMod("cpu-temp", fmt(cpu.temperature, 0) + "°C", cpu.temperature, 80, 95);
  setMod("cpu-pwr", fmt(cpu.power, 0) + "W", cpu.power, 140, 200);
  setMod("cpu-freq", fmt(cpu.frequency, 2) + "G", null, 99, 99);
  setMod("gpu-load", fmt(gpu.load, 0) + "%", gpu.load, 90, 98);
  setMod("gpu-temp", fmt(gpu.temperature, 0) + "°C", gpu.temperature, 80, 90);
  setMod("gpu-pwr", fmt(gpu.power, 0) + "W", gpu.power, 350, 450);
  setMod("gpu-clk", fmt(gpu.clock, 0) + "M", null, 99, 99);
  const vram = gpu.vram_used != null ? `${fmt(gpu.vram_used, 1)}/${fmt(gpu.vram_total, 0)}` : "—";
  setMod("vram", vram, gpu.vram_used && gpu.vram_total ? (gpu.vram_used / gpu.vram_total) * 100 : null, 85, 95);
  const ram = mem.used != null ? `${fmt(mem.used, 1)}/${fmt(mem.total, 0)}` : "—";
  setMod("ram", ram, mem.percent, 85, 95);
  setMod("fps", fmt(perf.fps, 0), perf.fps != null ? 200 - perf.fps : null, 40, 80);
  setMod("ft", perf.frametime != null ? fmt(perf.frametime, 1) + "ms" : "—", perf.frametime, 20, 33);
  const bpm = bio && bio.bpm != null ? String(bio.bpm) : "—";
  setMod("hr", "♥ " + bpm, bio && bio.state === "high" ? 90 : 0, 80, 90);
  const ble = document.getElementById("ble-dot");
  if (ble) {
    ble.className = "ble-dot" + (bio && bio.connected ? " on" : bio && bio.status === "reconnecting" ? " warn" : "");
  }
  const compact = document.getElementById("bio-bpm");
  if (compact) text(compact, bpm);
}

function setMod(id, label, metric, warn, crit) {
  const el = document.getElementById(id);
  if (!el) return;
  const value = el.querySelector(".value");
  if (value) text(value, label);
  el.classList.remove("warn", "crit");
  if (metric != null && metric >= crit) el.classList.add("crit");
  else if (metric != null && metric >= warn) el.classList.add("warn");
}

export { lerp };
