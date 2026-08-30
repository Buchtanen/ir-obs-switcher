/* Shared admin live client — polls status/activity + optional WS hooks. */
(function (global) {
  const POLL_MS = 2000;

  function statusClass(status) {
    const s = String(status || "").toLowerCase();
    if (["connected", "sampling", "running", "speaking", "ready", "recording"].includes(s)) {
      return "status-ok";
    }
    if (["degraded", "connecting", "reconnecting", "unreachable", "busy"].includes(s)) {
      return "status-warn";
    }
    if (["error", "disconnected"].includes(s)) return "status-bad";
    return "status-idle";
  }

  function pillEnabled(enabled) {
    return `<span class="pill ${enabled ? "enabled" : "disabled"}">${enabled ? "enabled" : "disabled"}</span>`;
  }

  function pillActive(active) {
    return `<span class="pill ${active ? "active" : "inactive"}">${active ? "active" : "inactive"}</span>`;
  }

  function pillStatus(status) {
    return `<span class="pill ${statusClass(status)}">${escapeHtml(status || "—")}</span>`;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatClock(at) {
    if (at == null || at === 0) return "—";
    // Prefer wall-clock when at looks like epoch seconds; else show relative mono.
    if (at > 1e9) {
      const d = new Date(at * 1000);
      return d.toLocaleTimeString();
    }
    return `${Number(at).toFixed(1)}s`;
  }

  function renderExtensionCard(ext) {
    const d = ext.detail || {};
    let meta = "";
    if (ext.id === "ble") {
      meta = `device=${d.deviceName || "—"} · bpm=${d.bpm ?? "—"} · state=${d.hrState || "—"}`;
    } else if (ext.id === "lhm") {
      meta = `url=${d.baseUrl || "—"} · sensors=${d.sensorRows ?? 0}`;
    } else if (ext.id === "sysinfo") {
      meta = `cpu=${d.cpuTemp ?? "—"}°C / ${d.cpuPower ?? "—"}W · gpu=${d.gpuLoad ?? "—"}%`;
    }
    const tip =
      ext.id === "lhm" && !ext.active && d.tip
        ? `<div class="tip">${escapeHtml(d.tip)}</div>`
        : "";
    return `<article class="card" data-id="${escapeHtml(ext.id)}">
      <h3>${escapeHtml(ext.label)}</h3>
      <div class="row">${pillEnabled(ext.enabled)} ${pillActive(ext.active)} ${pillStatus(ext.status)}</div>
      <div class="meta">${escapeHtml(meta)}</div>
      ${tip}
    </article>`;
  }

  function renderFeatureCard(key, feat) {
    if (key === "eventEngine") {
      const flags = Object.entries(feat || {})
        .map(([k, v]) => `${k}=${v ? "on" : "off"}`)
        .join(" · ");
      return `<article class="card"><h3>Event engine</h3>
        <div class="meta">${escapeHtml(flags || "—")}</div></article>`;
    }
    const title =
      key === "overlay" ? "Overlay" : key === "commentary" ? "Commentary" : key === "tape" ? "Session tape" : key;
    const extra =
      key === "overlay"
        ? `theme=${feat.theme || "—"} · widgets=${feat.activeWidgets ?? 0}`
        : key === "commentary"
          ? `busy=${feat.busy ? "yes" : "no"} · runtime=${feat.runtime ? "yes" : "no"}`
          : "";
    return `<article class="card" data-id="${escapeHtml(key)}">
      <h3>${escapeHtml(title)}</h3>
      <div class="row">${pillEnabled(!!feat.enabled)} ${pillActive(!!feat.active)} ${pillStatus(feat.status)}</div>
      <div class="meta">${escapeHtml(extra)}</div>
    </article>`;
  }

  function renderSwitcher(sw) {
    if (!sw) {
      return `<div class="card"><h3>Switcher</h3><div class="hint">Service state not initialized.</div></div>`;
    }
    return `<div class="card"><h3>Switcher</h3>
      <div class="row">
        <span class="pill ${sw.connected_iracing ? "enabled" : "disabled"}">iRacing ${sw.connected_iracing ? "up" : "down"}</span>
        <span class="pill ${sw.connected_obs ? "enabled" : "disabled"}">OBS ${sw.connected_obs ? "up" : "down"}</span>
        <span class="pill ${sw.autoswitch ? "active" : "inactive"}">autoswitch ${sw.autoswitch ? "on" : "off"}</span>
      </div>
      <div class="meta">mode=${escapeHtml(sw.mode || "—")} · scene=${escapeHtml(sw.current_scene || "—")} → ${escapeHtml(sw.target_scene || "—")}</div>
      <div class="hint">${escapeHtml(sw.reason || "")}</div>
    </div>`;
  }

  function renderActivity(items) {
    if (!items || !items.length) {
      return `<div class="feed-row"><span class="at">—</span><span class="kind">idle</span><span></span><span class="msg">No activity yet.</span></div>`;
    }
    return items
      .map((row) => {
        const src = escapeHtml(row.source || "?");
        return `<div class="feed-row">
          <span class="at">${escapeHtml(formatClock(row.at))}</span>
          <span class="src-${src}">${src}</span>
          <span class="kind">${escapeHtml(row.kind || "")}</span>
          <span class="msg">${escapeHtml(row.message || "")}</span>
        </div>`;
      })
      .join("");
  }

  async function fetchJson(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`${url} → ${res.status}`);
    return res.json();
  }

  function setLive(on) {
    const el = document.getElementById("live-indicator");
    if (!el) return;
    el.classList.toggle("on", !!on);
    el.textContent = on ? "live" : "offline";
  }

  function setVersion(v) {
    const el = document.getElementById("admin-version");
    if (el && v) el.textContent = `v${v}`;
  }

  function startAdmin(options) {
    const opts = options || {};
    let timer = null;
    let wsOk = false;

    async function tick() {
      try {
        if (opts.onStatus) {
          const status = await fetchJson("/api/admin/status");
          setVersion(status.version);
          opts.onStatus(status);
        }
        if (opts.onActivity) {
          const act = await fetchJson(`/api/admin/activity?limit=${opts.activityLimit || 80}`);
          opts.onActivity(act);
        }
        setLive(true);
      } catch (err) {
        console.debug("admin poll failed", err);
        setLive(wsOk);
      }
    }

    function connectWs(path, label) {
      try {
        const proto = location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${proto}://${location.host}${path}`);
        ws.onopen = () => {
          wsOk = true;
          setLive(true);
        };
        ws.onclose = () => {
          wsOk = false;
        };
        ws.onmessage = () => {
          // Any traffic nudges a refresh so cards stay fresh without waiting for poll.
          if (opts.refreshOnWs) tick();
        };
        ws.onerror = () => {};
        return ws;
      } catch (e) {
        console.debug("admin ws", label, e);
        return null;
      }
    }

    const sockets = [];
    if (opts.useSwitcherWs !== false) sockets.push(connectWs("/ws", "switcher"));
    if (opts.useOverlayWs !== false) sockets.push(connectWs("/ws/overlay", "overlay"));

    tick();
    timer = setInterval(tick, opts.pollMs || POLL_MS);

    return {
      stop() {
        if (timer) clearInterval(timer);
        sockets.forEach((ws) => {
          try {
            ws && ws.close();
          } catch (_) {}
        });
      },
    };
  }

  global.IrAdmin = {
    startAdmin,
    renderExtensionCard,
    renderFeatureCard,
    renderSwitcher,
    renderActivity,
    pillEnabled,
    pillActive,
    pillStatus,
    escapeHtml,
  };
})(window);
