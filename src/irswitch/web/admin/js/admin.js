/* Shared admin live client — poll primary, debounced WS invalidate, single-flight. */
(function (global) {
  const POLL_MS = 2000;
  const WS_DEBOUNCE_MS = 500;

  function statusClass(severity, status) {
    const sev = String(severity || "").toLowerCase();
    if (sev) {
      if (sev === "ok") return "status-ok";
      if (sev === "warn") return "status-warn";
      if (sev === "bad") return "status-bad";
      if (sev === "disabled" || sev === "idle") return "status-idle";
    }
    const s = String(status || "").toLowerCase();
    if (["connected", "sampling", "running", "speaking", "ready", "recording"].includes(s)) {
      return "status-ok";
    }
    if (["degraded", "connecting", "reconnecting", "unreachable", "reachable_empty", "stale"].includes(s)) {
      return "status-warn";
    }
    if (["error", "disconnected"].includes(s)) return "status-bad";
    return "status-idle";
  }

  function pillEnabled(enabled) {
    if (enabled == null) return "";
    return `<span class="pill ${enabled ? "enabled" : "disabled"}">${enabled ? "enabled" : "disabled"}</span>`;
  }

  function pillRequired(required, mode) {
    if (required == null) return "";
    const label = required ? `required:${mode || "yes"}` : "not required";
    return `<span class="pill ${required ? "inactive" : "disabled"}">${escapeHtml(label)}</span>`;
  }

  function pillActive(active) {
    return `<span class="pill ${active ? "active" : "inactive"}">${active ? "active" : "inactive"}</span>`;
  }

  function pillBusy(busy) {
    if (!busy) return "";
    return `<span class="pill active">busy</span>`;
  }

  function pillStatus(status, severity) {
    return `<span class="pill ${statusClass(severity, status)}">${escapeHtml(status || "—")}</span>`;
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
    if (at > 1e9) {
      return new Date(at * 1000).toLocaleTimeString();
    }
    return `${Number(at).toFixed(1)}s`;
  }

  function renderExtensionCard(ext) {
    const d = ext.detail || {};
    let meta = "";
    if (ext.id === "ble") {
      meta = `device=${d.deviceName || "—"} · bpm=${d.bpm ?? "—"} · state=${d.hrState || "—"}`;
    } else if (ext.id === "lhm") {
      const stale = d.stale ? " · stale" : "";
      const err = d.errorCode ? ` · err=${d.errorCode}` : "";
      meta = `url=${d.lastBaseUrl || d.baseUrl || "—"} · sensors=${d.sensorRows ?? 0} · ${d.connection || ""}${stale}${err} · checked=${formatClock(d.checkedAt)}`;
    } else if (ext.id === "sysinfo") {
      meta = `cpu=${d.cpuTemp ?? "—"}°C / ${d.cpuPower ?? "—"}W · gpu=${d.gpuLoad ?? "—"}% · lhmReq=${d.lhmRequired ? d.lhmRequirementMode || "yes" : "no"}`;
    }
    const tip =
      ext.id === "lhm" && d.tip && ext.required
        ? `<div class="tip">${escapeHtml(d.tip)}</div>`
        : "";
    const enableOrReq =
      ext.id === "lhm" ? pillRequired(ext.required, ext.requirementMode) : pillEnabled(ext.enabled);
    return `<article class="card" data-id="${escapeHtml(ext.id)}">
      <h3>${escapeHtml(ext.label)}</h3>
      <div class="row">${enableOrReq} ${pillActive(ext.active)} ${pillBusy(ext.busy)} ${pillStatus(ext.status, ext.severity)}</div>
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
          ? `busy=${feat.busy ? "yes" : "no"} · available=${feat.available ? "yes" : "no"}`
          : `available=${feat.available ? "yes" : "no"}`;
    return `<article class="card" data-id="${escapeHtml(key)}">
      <h3>${escapeHtml(title)}</h3>
      <div class="row">${pillEnabled(!!feat.enabled)} ${pillActive(!!feat.active)} ${pillBusy(!!feat.busy)} ${pillStatus(feat.status, feat.severity)}</div>
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

  function renderHealth(health) {
    if (!health) return "";
    const ready = !!health.ready;
    const blocking = health.blocking || [];
    const warnings = health.warnings || [];
    if (ready && !warnings.length) {
      return `<div class="health ok" role="status"><strong>ready</strong> — no blocking issues</div>`;
    }
    const cls = ready ? "health warn" : "health bad";
    const title = ready ? "ready with warnings" : "not ready";
    const lines = []
      .concat(blocking.map((b) => `block:${b.id} — ${b.reason}${b.tip ? ` (${b.tip})` : ""}`))
      .concat(warnings.map((w) => `warn:${w.id} — ${w.reason}${w.tip ? ` (${w.tip})` : ""}`));
    return `<div class="${cls}" role="status">
      <strong>${escapeHtml(title)}</strong>
      <ul>${lines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>
    </div>`;
  }

  function renderActivity(items) {
    if (!items || !items.length) {
      return `<div class="feed-row"><span class="at">—</span><span class="kind">idle</span><span></span><span class="msg">No activity yet.</span></div>`;
    }
    return items
      .map((row) => {
        const src = escapeHtml(row.source || "?");
        const at = row.occurredAt != null ? row.occurredAt : row.at;
        const eph = row.ephemeral ? " · live" : "";
        return `<div class="feed-row">
          <span class="at">${escapeHtml(formatClock(at))}</span>
          <span class="src-${src}">${src}${eph}</span>
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

  function setVersion(v, schema) {
    const el = document.getElementById("admin-version");
    if (el && v) el.textContent = schema != null ? `v${v} · schema ${schema}` : `v${v}`;
  }

  function startAdmin(options) {
    const opts = options || {};
    let timer = null;
    let wsOk = false;
    let inFlight = false;
    let debounceTimer = null;

    async function tick() {
      if (inFlight) return;
      inFlight = true;
      try {
        if (opts.onStatus) {
          const status = await fetchJson("/api/admin/status");
          setVersion(status.version, status.schemaVersion);
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
      } finally {
        inFlight = false;
      }
    }

    function scheduleTick() {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        debounceTimer = null;
        tick();
      }, opts.wsDebounceMs || WS_DEBOUNCE_MS);
    }

    function connectWs(path) {
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
          if (opts.refreshOnWs) scheduleTick();
        };
        ws.onerror = () => {};
        return ws;
      } catch (e) {
        console.debug("admin ws", path, e);
        return null;
      }
    }

    const sockets = [];
    if (opts.useSwitcherWs) sockets.push(connectWs("/ws"));
    if (opts.useOverlayWs) sockets.push(connectWs("/ws/overlay"));

    tick();
    timer = setInterval(tick, opts.pollMs || POLL_MS);

    return {
      stop() {
        if (timer) clearInterval(timer);
        if (debounceTimer) clearTimeout(debounceTimer);
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
    renderHealth,
    renderActivity,
    pillEnabled,
    pillActive,
    pillStatus,
    escapeHtml,
  };
})(window);
