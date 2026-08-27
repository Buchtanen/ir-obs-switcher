const CHANNELS = {
  battle: { cap: 2, layer: "battle-stack" },
  lap: { cap: 1, layer: "event-layer" },
  alert: { cap: 1, layer: "event-layer" },
  session: { cap: 1, layer: "session-layer" },
  bio: { cap: 1, layer: "bio-expanded" },
  system: { cap: 1, layer: "event-layer" },
};

const ASSET_BASE = "/overlay/web/";

const FALLBACK_LAYERS = ["bg", "frame", "glow", "accent", "corners", "deco", "icon"];

function makeLayerEl(layer) {
  const el = document.createElement("div");
  el.className = `layer ${layer.id}`;
  el.dataset.layer = layer.id;
  if (layer.blend === "screen") el.classList.add("blend-screen");
  if (layer.mask || layer.id === "frame" || layer.id === "accent") el.classList.add("cover");
  return el;
}

function text(el, value) {
  if (!el) return;
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

export function assetUrl(slot) {
  const rel = window.__assets && window.__assets[slot];
  if (!rel) return null;
  return ASSET_BASE + rel;
}

function paintLayer(el, slot, asMask) {
  if (!el) return;
  const url = slot ? assetUrl(slot) : null;
  if (!url) {
    el.classList.add("empty");
    el.style.backgroundImage = "";
    el.style.webkitMaskImage = "";
    el.style.maskImage = "";
    return;
  }
  el.classList.remove("empty");
  if (asMask) {
    el.style.backgroundImage = "";
    el.style.backgroundColor = "currentColor";
    const mask = `url("${url}")`;
    const cover = el.classList.contains("cover");
    const size = cover ? "100% 100%" : "contain";
    const pos = cover ? "0 0" : "center";
    el.style.webkitMaskImage = mask;
    el.style.maskImage = mask;
    el.style.webkitMaskSize = size;
    el.style.maskSize = size;
    el.style.webkitMaskRepeat = "no-repeat";
    el.style.maskRepeat = "no-repeat";
    el.style.webkitMaskPosition = pos;
    el.style.maskPosition = pos;
  } else {
    el.style.backgroundColor = "";
    el.style.backgroundImage = `url("${url}")`;
    el.style.webkitMaskImage = "";
    el.style.maskImage = "";
  }
}

function playMuted(video) {
  if (!video) return;
  const run = video.play();
  if (run && typeof run.catch === "function") run.catch(() => {});
}

function ensureFxVideo(art, className, slot, loop) {
  let video = art.querySelector(`video.${className}`);
  const url = assetUrl(slot);
  if (!url) {
    if (video) {
      video.pause();
      video.remove();
    }
    return null;
  }
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

function removeFxVideo(art, className) {
  const video = art.querySelector(`video.${className}`);
  if (!video) return;
  video.pause();
  video.remove();
}

function syncWidgetFx(node, event, isEnter) {
  const art = node.querySelector(".widget-art");
  if (!art) return;
  const hunting = event.name === "battle" && event.data && event.data.state === "hunting";
  if (hunting) {
    const lock = ensureFxVideo(art, "signal-lock", "battle_signal_lock", false);
    node.classList.toggle("has-radar-fx", Boolean(lock));
    if (isEnter) playMuted(lock);
  } else {
    removeFxVideo(art, "signal-lock");
    node.classList.remove("has-radar-fx");
  }
  if (isEnter && event.name === "battle") {
    const scan = ensureFxVideo(art, "scan-enter", "battle_scan_enter", false);
    if (scan) {
      try {
        scan.currentTime = 0;
      } catch (_err) {
        /* metadata not ready yet */
      }
      playMuted(scan);
    }
    const themeFx = ensureFxVideo(art, "theme-motion", "battle_theme_motion", false);
    if (themeFx) {
      try {
        themeFx.currentTime = 0;
      } catch (_err) {
        /* metadata not ready yet */
      }
      playMuted(themeFx);
    }
  }
  if (isEnter && event.name === "finish") {
    const sweep = ensureFxVideo(art, "finish-sweep", "finish_accent_sweep", false);
    if (sweep) {
      try {
        sweep.currentTime = 0;
      } catch (_err) {
        /* metadata not ready yet */
      }
      playMuted(sweep);
    }
  }
}

function sizeClass(event) {
  if (event.channel === "battle") return "battle";
  if (event.name === "position_change") return "position";
  if (event.channel === "lap") return "lap";
  if (event.channel === "session") return "session";
  if (event.channel === "bio") return "bio";
  return "alert";
}

function toneClass(event) {
  const name = event.name;
  const data = event.data || {};
  if (name === "battle") return data.state === "hunted" ? "hunted" : "hunting";
  if (name === "incident" || name === "ble_lost") return "alert";
  if (name === "personal_best") return "pb";
  return name;
}

function battleLayerPlan(hunted) {
  const icon = hunted ? "battle_pressure_icon" : "battle_target_icon";
  const glow = hunted ? "battle_glow_amber" : "battle_glow_cyan";
  return [
    { id: "shadow", slot: "battle_shadow" },
    { id: "base", slot: "battle_base_plate" },
    { id: "material", slot: "battle_material" },
    { id: "tech", slot: "battle_tech_diagram" },
    { id: "frame", slot: "battle_frame_base" },
    { id: "highlight", slot: "battle_frame_highlight", blend: "screen" },
    { id: "accent", slot: "battle_state_accent_mask", mask: true },
    { id: "corner-left", slot: "battle_corner_left", mask: true },
    { id: "corner-right", slot: "battle_corner_right", mask: true },
    { id: "well", slot: "battle_icon_well" },
    { id: "ticks", slot: "battle_radar_ticks", mask: true },
    { id: "ring-inner", slot: "battle_radar_ring_inner", mask: true },
    { id: "ring-outer", slot: "battle_radar_ring_outer", mask: true },
    { id: "icon", slot: icon, mask: true },
    { id: "micro", slot: "battle_micro_details", mask: true },
    { id: "glow", slot: glow, blend: "screen" },
  ];
}

function fallbackLayerPlan(slots) {
  return FALLBACK_LAYERS.filter((name) => slots[name]).map((name) => {
    const maskKey = `${name}Mask`;
    const explicit = Object.prototype.hasOwnProperty.call(slots, maskKey);
    const mask = explicit ? Boolean(slots[maskKey]) : name === "icon";
    return {
      id: name,
      slot: slots[name],
      mask,
      blend: name === "glow" ? "screen" : undefined,
    };
  });
}

function layersFor(event) {
  if (event.name === "battle") {
    return battleLayerPlan(event.data && event.data.state === "hunted");
  }
  return fallbackLayerPlan(artSlots(event));
}

function artSlots(event) {
  const name = event.name;
  const data = event.data || {};
  if (name === "lap_complete") {
    return {
      bg: "lap_background",
      frame: "lap_frame",
      glow: "battle_glow_cyan",
      icon: "lap_flag_icon",
      iconMask: true,
    };
  }
  if (name === "personal_best") {
    return {
      bg: "lap_background",
      frame: "lap_frame",
      glow: "battle_glow_amber",
      icon: "lap_stopwatch_icon",
      iconMask: true,
    };
  }
  if (name === "position_change") {
    return {
      bg: "position_banner",
      glow: "battle_glow_cyan",
      icon: data.direction === "gain" ? "chevron_up" : "chevron_down",
      iconMask: true,
    };
  }
  if (name === "final_lap") {
    return {
      bg: "session_background",
      glow: "battle_glow_cyan",
      icon: "final_lap_flag",
      iconMask: false,
    };
  }
  if (name === "finish") {
    return {
      bg: "session_background",
      glow: "battle_glow_amber",
      icon: "finish_flag",
      iconMask: true,
    };
  }
  if (name === "heart_rate") {
    return {
      bg: "bio_expanded_plate",
      glow: "battle_glow_cyan",
      accent: "bio_accent",
      deco: "bio_pulse_trace",
      icon: "heart_icon",
      accentMask: true,
      decoMask: true,
      iconMask: true,
    };
  }
  if (name === "ble_lost") {
    return {
      bg: "bio_expanded_plate",
      glow: "battle_glow_red",
      icon: "ble_icon",
      iconMask: true,
    };
  }
  return { bg: "alert_banner", glow: "battle_glow_amber" };
}

export function applyPersistentArt() {
  document.querySelectorAll("[data-slot]").forEach((el) => {
    const asMask = el.classList.contains("icon") || el.classList.contains("mask");
    paintLayer(el, el.dataset.slot, asMask);
  });
  const sys = document.getElementById("sysinfo-widget");
  if (sys) {
    const plate = Boolean(assetUrl("sysinfo_background"));
    sys.classList.toggle("has-art", plate);
    sys.classList.toggle("fallback", !plate);
  }
  const bio = document.getElementById("bio-compact");
  if (bio) {
    const plate = Boolean(assetUrl("bio_compact_plate"));
    bio.classList.toggle("has-art", plate);
    bio.classList.toggle("fallback", !plate);
  }
}

export const DisplayManager = {
  active: new Map(),

  show(event) {
    const channel = event.channel || "alert";
    const key = `${channel}:${event.data && event.data.state ? event.data.state : event.name}`;
    let node = this.active.get(key);
    const created = !node;
    if (!node) {
      node = this._create(event, channel);
      this.active.set(key, node);
    }
    this._fill(node, event);
    node.classList.remove("exit");
    requestAnimationFrame(() => node.classList.add("visible"));
    if (!document.documentElement.classList.contains("preview-layout")) {
      syncWidgetFx(node, event, created);
    }
    if (event.phase === "exit") this.hide(key);
    return node;
  },

  hide(key) {
    const node = this.active.get(key);
    if (!node) return;
    node.querySelectorAll("video").forEach((video) => video.pause());
    node.classList.add("exit");
    node.classList.remove("visible");
    setTimeout(() => {
      if (this.active.get(key) !== node) return;
      node.remove();
      this.active.delete(key);
    }, 400);
  },

  clear() {
    for (const [key, node] of [...this.active.entries()]) {
      node.remove();
      this.active.delete(key);
    }
  },

  refreshArt() {
    for (const node of this.active.values()) {
      if (node._event) {
        this._applyArt(node, node._event);
        if (!document.documentElement.classList.contains("preview-layout")) {
          syncWidgetFx(node, node._event, false);
        }
      }
    }
    applyPersistentArt();
  },

  _create(event, channel) {
    const spec = CHANNELS[channel] || CHANNELS.alert;
    const layer = document.getElementById(spec.layer);
    const node = document.createElement("div");
    node.className = `widget ${sizeClass(event)} ${toneClass(event)}`;
    node.dataset.key = `${channel}:${event.name}`;
    const art = document.createElement("div");
    art.className = "widget-art";
    const copy = document.createElement("div");
    copy.className = "widget-copy";
    copy.innerHTML = '<div class="kicker"></div><div class="title"></div><div class="meta"></div>';
    node.append(art, copy);
    layer.appendChild(node);
    return node;
  },

  _applyArt(node, event) {
    const plan = layersFor(event);
    const art = node.querySelector(".widget-art");
    const hasPlate = plan.some((layer) => {
      const id = layer.id;
      return (id === "base" || id === "bg") && Boolean(assetUrl(layer.slot));
    });
    node.classList.toggle("has-art", hasPlate);
    node.classList.toggle("fallback", !hasPlate);
    node.classList.remove("battle", "lap", "alert", "position", "session", "bio");
    node.classList.add(sizeClass(event));
    const videos = [...art.querySelectorAll("video")];
    [...art.querySelectorAll(".layer:not(video)")].forEach((el) => el.remove());
    const firstVideo = videos[0] || null;
    plan.forEach((layer) => {
      const el = makeLayerEl(layer);
      art.insertBefore(el, firstVideo);
      paintLayer(el, layer.slot, Boolean(layer.mask) && Boolean(layer.slot));
    });
  },

  _fill(node, event) {
    node._event = event;
    const data = event.data || {};
    const keep = ["visible", "exit", "has-art", "has-radar-fx", "fallback"].filter((name) =>
      node.classList.contains(name),
    );
    node.className = ["widget", sizeClass(event), toneClass(event), ...keep].join(" ");
    const kicker = node.querySelector(".kicker");
    const title = node.querySelector(".title");
    const meta = node.querySelector(".meta");
    const name = event.name;
    const state = data.state;
    if (name === "battle" && state === "hunting") {
      text(kicker, "CLOSING IN");
      text(title, "HUNTING");
      text(meta, `P${data.targetPosition ?? "—"}  +${fmt(data.gap, 3)}`);
    } else if (name === "battle" && state === "hunted") {
      text(kicker, "UNDER PRESSURE");
      text(title, "HUNTED");
      text(meta, `P${data.targetPosition ?? "—"}  -${fmt(data.gap, 3)}`);
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
      text(kicker, "");
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
    this._applyArt(node, event);
  },
};

function fmtUnit(n, digits, suffix) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits) + suffix;
}

function joinParts(parts) {
  const present = parts.filter((part) => part != null && part !== "—");
  return present.length ? present.join(" ") : "—";
}

export function applySysinfo(system, bio) {
  const cpu = (system && system.cpu) || {};
  const gpu = (system && system.gpu) || {};
  const mem = (system && system.memory) || {};
  const perf = (system && system.performance) || {};
  setMod(
    "cpu-load",
    joinParts([fmtUnit(cpu.load, 0, "%"), fmtUnit(cpu.frequency, 2, "G")]),
    cpu.load,
    85,
    95,
  );
  setMod("cpu-temp", fmtUnit(cpu.temperature, 0, "°C"), cpu.temperature, 80, 95);
  setMod("cpu-pwr", fmtUnit(cpu.power, 0, "W"), cpu.power, 140, 200);
  hintEmpty(
    "cpu-temp",
    cpu.temperature,
    "Windows has no CPU package sensors. LHM 0.9.5+: Remote Web Server → Run, File → Hardware → CPU.",
  );
  hintEmpty(
    "cpu-pwr",
    cpu.power,
    "LHM 0.9.5+ dropped WMI. Keep Remote Web Server running (data.json on 8085 or the bound NIC).",
  );
  setMod("gpu-load", fmtUnit(gpu.load, 0, "%"), gpu.load, 90, 98);
  setMod("gpu-temp", fmtUnit(gpu.temperature, 0, "°C"), gpu.temperature, 80, 90);
  setMod("gpu-pwr", fmtUnit(gpu.power, 0, "W"), gpu.power, 350, 450);
  setMod("gpu-clk", fmtUnit(gpu.clock, 0, "M"), null, 99, 99);
  const vram =
    gpu.vram_used != null && gpu.vram_total != null
      ? `${fmt(gpu.vram_used, 1)}/${fmt(gpu.vram_total, 0)}`
      : "—";
  setMod(
    "vram",
    vram,
    gpu.vram_used != null && gpu.vram_total ? (gpu.vram_used / gpu.vram_total) * 100 : null,
    85,
    95,
  );
  const ram = mem.used != null && mem.total != null ? `${fmt(mem.used, 1)}/${fmt(mem.total, 0)}` : "—";
  setMod("ram", ram, mem.percent, 85, 95);
  setMod(
    "fps",
    joinParts([fmt(perf.fps, 0), fmtUnit(perf.frametime, 1, "ms")]),
    perf.frametime,
    20,
    33,
  );
  const bpm = bio && bio.bpm != null ? String(bio.bpm) : "—";
  setMod("hr", bpm, bio && bio.state === "high" ? 90 : bio && bio.bpm != null ? 0 : null, 80, 90);
  const ble = document.getElementById("ble-dot");
  if (ble) {
    ble.className =
      "icon mask ble-icon" +
      (bio && bio.connected ? " on" : bio && bio.status === "reconnecting" ? " warn" : "");
    if (ble.dataset.slot) paintLayer(ble, ble.dataset.slot, true);
  }
  const compact = document.getElementById("bio-bpm");
  if (compact) text(compact, bpm);
}

function setMod(id, label, metric, warn, crit) {
  const el = document.getElementById(id);
  if (!el) return;
  const value = el.querySelector(".value");
  if (value) text(value, label);
  el.classList.toggle("empty-metric", label == null || label === "—");
  el.classList.remove("warn", "crit");
  if (metric != null && metric >= crit) el.classList.add("crit");
  else if (metric != null && metric >= warn) el.classList.add("warn");
}

function hintEmpty(id, metric, message) {
  const el = document.getElementById(id);
  if (!el) return;
  el.title = metric == null ? message : "";
}

export { lerp };
