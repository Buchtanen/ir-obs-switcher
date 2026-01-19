"""HTML dashboard endpoints."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from aiohttp import web

from irswitch.config import AppConfig
from irswitch.server.event_log import get_event_log

# Import these lazily to avoid circular import
def _get_current_state():
    from irswitch.server.api import _current_state
    return _current_state

def _get_obs_client():
    from irswitch.server.api import _obs_client
    return _obs_client

logger = logging.getLogger(__name__)


def format_stream_duration(ms: Optional[int]) -> str:
    """Format stream duration in MM:SS or HH:MM:SS format."""
    if ms is None:
        return "00:00"
    
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"


def format_duration(seconds: Optional[float]) -> str:
    """Format duration in seconds to HH:MM:SS or MM:SS format."""
    if seconds is None:
        return "N/A"
    
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


async def handle_gr_status(request: web.Request) -> web.Response:
    """Handle GET /gr-status - large dashboard."""
    try:
        config: Optional[AppConfig] = request.app.get("config")
        if config is None:
            return web.Response(text="Configuration not available", status=500)

        # Get current state
        state = _get_current_state()
        if state is None:
            return web.Response(text="Service not initialized", status=503)

        # Get streaming status
        is_streaming = False
        stream_duration_ms: Optional[int] = None
        obs_client = _get_obs_client()
        if obs_client is not None and state.connected_obs:
            try:
                is_streaming, stream_duration_ms = await obs_client.get_stream_status()
            except Exception:
                pass

        # Get OBS profile
        obs_profile: Optional[str] = None
        if obs_client is not None and state.connected_obs:
            try:
                obs_profile = await obs_client.get_current_profile()
                if obs_profile is None:
                    logger.debug("OBS profile is None - profile may not be available via WebSocket API")
            except Exception as e:
                logger.debug(f"Failed to get OBS profile: {e}")
                obs_profile = None

        # Get recent events
        events = []
        try:
            event_log = get_event_log()
            events_data = await event_log.get_recent_events(config.dashboard_event_log_size)
            events = [
                {
                    "timestamp": e.timestamp,
                    "type": e.type,
                    "message": e.message,
                    "data": e.data,
                }
                for e in events_data
            ]
        except Exception as e:
            logger.debug(f"Failed to get events: {e}")

        # Get metrics
        from irswitch.server.metrics import get_metrics
        metrics = get_metrics()
        metrics_dict = metrics.to_dict(state)

        # Calculate update interval from FPS
        update_interval_ms = int(1000 / config.dashboard_update_fps)
        
        # Cache busting timestamp
        cache_bust = int(time.time() * 1000)

        # Build image paths
        bg_image = config.dashboard_gr_background_image or ""
        logo_obs = config.dashboard_gr_logo_obs or ""
        logo_iracing = config.dashboard_gr_logo_iracing or ""
        logo_app = config.dashboard_gr_logo_app or ""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>iRacing OBS Switcher - Status</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: {'url(' + bg_image + ')' if bg_image else '#1a1a1a'};
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            color: #fff;
            min-height: 100vh;
            padding: 20px;
            overflow-x: hidden;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(0, 0, 0, 0.7);
            border-radius: 12px;
            padding: 30px;
            backdrop-filter: blur(10px);
        }}
        
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid rgba(255, 255, 255, 0.1);
        }}
        
        .header h1 {{
            font-size: 2em;
            font-weight: 600;
        }}
        
        .logo-container {{
            display: flex;
            gap: 15px;
            align-items: center;
        }}
        
        .logo {{
            height: 40px;
            width: auto;
            opacity: 0.9;
        }}
        
        .status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .status-card {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .status-card h3 {{
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #aaa;
            margin-bottom: 10px;
        }}
        
        .status-card .sublabel {{
            font-size: 0.7em;
            color: #666;
            margin-bottom: 5px;
            min-height: 1.2em;
        }}
        
        .status-card .value {{
            font-size: 1.5em;
            font-weight: 600;
            color: #fff;
        }}
        
        .connection-status {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .status-indicator {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #4caf50;
        }}
        
        .status-indicator.disconnected {{
            background: #f44336;
        }}
        
        .streaming-indicator {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
        }}
        
        .rec-dot {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: {'#f44336' if is_streaming else '#666'};
            animation: {'pulse 2s infinite' if is_streaming else 'none'};
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        
        .controls {{
            display: flex;
            gap: 15px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }}
        
        button {{
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: #fff;
            padding: 12px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.2s;
        }}
        
        button:hover {{
            background: rgba(255, 255, 255, 0.2);
            border-color: rgba(255, 255, 255, 0.3);
        }}
        
        button:active {{
            transform: scale(0.98);
        }}
        
        .event-log {{
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            padding: 20px;
            max-height: 400px;
            overflow-y: auto;
        }}
        
        .event-log h3 {{
            margin-bottom: 15px;
            font-size: 1.1em;
        }}
        
        .event-item {{
            padding: 10px;
            margin-bottom: 8px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
            border-left: 3px solid #4caf50;
            font-size: 0.9em;
        }}
        
        .event-item.connection_lost {{
            border-left-color: #f44336;
        }}
        
        .event-item.scene_switch {{
            border-left-color: #2196f3;
        }}
        
        .event-item.override_applied {{
            border-left-color: #ff9800;
        }}
        
        .event-time {{
            color: #aaa;
            font-size: 0.85em;
            margin-right: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>iRacing OBS Switcher</h1>
            <div class="logo-container">
                {'<img src="' + logo_app + '" alt="App" class="logo">' if logo_app else ''}
            </div>
        </div>
        
        <div class="status-grid">
            <div class="status-card">
                <h3>iRacing Connection</h3>
                <div class="sublabel"></div>
                <div class="connection-status">
                    <div class="status-indicator {'disconnected' if not state.connected_iracing else ''}"></div>
                    <span class="value">{'Connected' if state.connected_iracing else 'Disconnected'}</span>
                </div>
            </div>
            
            <div class="status-card">
                <h3>OBS Connection</h3>
                <div class="sublabel"></div>
                <div class="connection-status">
                    <div class="status-indicator {'disconnected' if not state.connected_obs else ''}"></div>
                    <span class="value">{'Connected' if state.connected_obs else 'Disconnected'}</span>
                </div>
            </div>
            
            <div class="status-card">
                <h3>OBS Profile</h3>
                <div class="sublabel"></div>
                <div class="value">{obs_profile or 'N/A'}</div>
            </div>
            
            <div class="status-card">
                <h3>Current Scene</h3>
                <div class="sublabel"></div>
                <div class="value">{state.current_scene}</div>
            </div>
            
            <div class="status-card">
                <h3>Streaming</h3>
                <div class="sublabel"></div>
                <div class="streaming-indicator">
                    <div class="rec-dot"></div>
                    <span class="value">{'LIVE' if is_streaming else 'IDLE'}</span>
                </div>
            </div>
            
            <div class="status-card">
                <h3>Stream Duration</h3>
                <div class="sublabel">
                    <span id="stream-duration-label">Cumulative</span>
                    {f' | <span>Current</span>' if stream_duration_ms is not None else ''}
                </div>
                <div class="value" id="stream-duration-display">
                    <span>{format_duration(metrics_dict.get("stream_duration_seconds")) if metrics_dict.get("stream_duration_seconds") is not None else 'N/A'}</span>
                    {f' <span style="font-size: 0.75em; color: #aaa;">| {format_stream_duration(stream_duration_ms)}</span>' if stream_duration_ms is not None else ''}
                </div>
            </div>
            
            <div class="status-card">
                <h3>Mode</h3>
                <div class="sublabel"></div>
                <div class="value">{state.mode.value}</div>
            </div>
            
            <div class="status-card">
                <h3>Autoswitch</h3>
                <div class="sublabel"></div>
                <div class="value">{'ON' if state.autoswitch else 'OFF'}</div>
            </div>
        </div>
        
        <div class="status-grid" style="margin-top: 20px;">
            <div class="status-card">
                <h3>Session Type</h3>
                <div class="sublabel"></div>
                <div class="value" id="session-type">{'N/A' if state.session_type == 'Test' or state.session_type is None else state.session_type}</div>
            </div>
            
            <div class="status-card">
                <h3>Session Name</h3>
                <div class="sublabel"></div>
                <div class="value" style="font-size: 1.2em;" id="session-name">{'N/A' if state.session_type == 'Test' or state.session_name is None else state.session_name}</div>
            </div>
            
            <div class="status-card">
                <h3>Session Num</h3>
                <div class="sublabel"></div>
                <div class="value" id="session-num">{'N/A' if state.session_type == 'Test' or state.session_num is None else state.session_num}</div>
            </div>
        </div>
        
        <div class="status-grid" style="margin-top: 20px;">
            <div class="status-card">
                <h3>Scene Switches</h3>
                <div class="sublabel"></div>
                <div class="value" id="metrics-switches">{metrics_dict.get('scene_switches_total', 0)}</div>
            </div>
            
            <div class="status-card">
                <h3>Avg Latency</h3>
                <div class="sublabel"></div>
                <div class="value" id="metrics-latency">
                    {f"{metrics_dict.get('scene_switch_latency_avg_ms', 0):.4f} ms" if metrics_dict.get('scene_switch_latency_avg_ms') is not None else 'N/A'}
                </div>
            </div>
            
            <div class="status-card">
                <h3>Uptime</h3>
                <div class="sublabel"></div>
                <div class="value" id="metrics-uptime">{format_duration(metrics_dict.get('uptime_seconds', 0))}</div>
            </div>
            
            <div class="status-card">
                <h3>iRacing Connected</h3>
                <div class="sublabel">
                    <span id="metrics-iracing-label">Cumulative</span>
                    {f' | <span>Current</span>' if metrics_dict.get('iracing_connected_duration_current_session_seconds') is not None and metrics_dict.get('iracing_connected_duration_current_session_seconds') > 0 else ''}
                </div>
                <div class="value" id="metrics-iracing-time">
                    <span>{format_duration(metrics_dict.get('iracing_connected_duration_seconds')) if metrics_dict.get('iracing_connected_duration_seconds') is not None else 'N/A'}</span>
                    {f' <span style="font-size: 0.75em; color: #aaa;">| {format_duration(metrics_dict.get("iracing_connected_duration_current_session_seconds"))}</span>' if metrics_dict.get('iracing_connected_duration_current_session_seconds') is not None and metrics_dict.get('iracing_connected_duration_current_session_seconds') > 0 else ''}
                </div>
            </div>
            
            <div class="status-card">
                <h3>OBS Connected</h3>
                <div class="sublabel">
                    <span id="metrics-obs-label">Cumulative</span>
                    {f' | <span>Current</span>' if metrics_dict.get('obs_connected_duration_current_session_seconds') is not None and metrics_dict.get('obs_connected_duration_current_session_seconds') > 0 else ''}
                </div>
                <div class="value" id="metrics-obs-time">
                    <span>{format_duration(metrics_dict.get('obs_connected_duration_seconds')) if metrics_dict.get('obs_connected_duration_seconds') is not None else 'N/A'}</span>
                    {f' <span style="font-size: 0.75em; color: #aaa;">| {format_duration(metrics_dict.get("obs_connected_duration_current_session_seconds"))}</span>' if metrics_dict.get('obs_connected_duration_current_session_seconds') is not None and metrics_dict.get('obs_connected_duration_current_session_seconds') > 0 else ''}
                </div>
            </div>
        </div>
        
        <div class="status-card" style="margin-bottom: 30px;">
            <h3>Scene Switch Reason</h3>
            <div class="value" style="font-size: 1.2em;">{state.reason}</div>
        </div>
        
        <div class="controls">
            <button onclick="toggleAutoswitch()">Toggle Autoswitch</button>
            <button onclick="resetRestartMode()">Reset RESTART Mode</button>
            <button onclick="reloadConfig()">Reload Config</button>
            <button onclick="shutdownService()" style="background: rgba(244, 67, 54, 0.2); border-color: rgba(244, 67, 54, 0.4);">Shutdown Service</button>
        </div>
        
        <div class="event-log">
            <h3>Event Log</h3>
            <div id="events-container"></div>
        </div>
    </div>
    
    <script>
        const API_BASE = window.location.origin;
        const UPDATE_INTERVAL = {update_interval_ms};
        
        let events = {json.dumps(events)};
        
        function formatTime(timestamp) {{
            const date = new Date(timestamp);
            return date.toLocaleTimeString();
        }}
        
        function renderEvents() {{
            const container = document.getElementById('events-container');
            container.innerHTML = events.map(e => `
                <div class="event-item ${{e.type}}">
                    <span class="event-time">${{formatTime(e.timestamp)}}</span>
                    <strong>${{e.type}}</strong>: ${{e.message}}
                </div>
            `).join('');
        }}
        
        async function updateStatus() {{
            try {{
                const response = await fetch(`${{API_BASE}}/status`);
                const data = await response.json();
                
                // Update connection statuses
                updateConnectionStatus('iracing', data.connected_iracing);
                updateConnectionStatus('obs', data.connected_obs);
                
                // Update scene
                updateValue('Current Scene', data.current_scene);
                
                // Update streaming
                const streamingEl = document.querySelector('.streaming-indicator .value');
                const recDot = document.querySelector('.rec-dot');
                if (streamingEl && recDot) {{
                    if (data.streaming) {{
                        streamingEl.textContent = 'LIVE';
                        recDot.style.background = '#f44336';
                        recDot.style.animation = 'pulse 2s infinite';
                    }} else {{
                        streamingEl.textContent = 'IDLE';
                        recDot.style.background = '#666';
                        recDot.style.animation = 'none';
                    }}
                }}
                
                // Update stream duration - show cumulative | current
                const streamDurationEl = document.getElementById('stream-duration-display');
                const streamLabelEl = document.getElementById('stream-duration-label');
                if (streamDurationEl) {{
                    let html = '<span>' + (formatDuration(data.stream_duration_seconds) || 'N/A') + '</span>';
                    if (data.stream_duration_ms !== null && data.stream_duration_ms !== undefined) {{
                        html += ' <span style="font-size: 0.75em; color: #aaa;">| ' + formatStreamDuration(data.stream_duration_ms) + '</span>';
                    }}
                    streamDurationEl.innerHTML = html;
                }}
                if (streamLabelEl) {{
                    streamLabelEl.parentElement.innerHTML = 'Cumulative' + (data.stream_duration_ms !== null && data.stream_duration_ms !== undefined ? ' | <span>Current</span>' : '');
                }}
                
                // Update mode
                updateValue('Mode', data.mode);
                
                // Update autoswitch
                updateValue('Autoswitch', data.autoswitch ? 'ON' : 'OFF');
                
                // Update session info - hide Test sessions
                const sessionType = data.session_type === 'Test' || data.session_type === null || data.session_type === undefined ? 'N/A' : data.session_type;
                const sessionName = data.session_type === 'Test' || data.session_name === null || data.session_name === undefined ? 'N/A' : data.session_name;
                const sessionNum = data.session_type === 'Test' || data.session_num === null || data.session_num === undefined ? 'N/A' : data.session_num;
                updateValue('Session Type', sessionType);
                updateValue('Session Name', sessionName);
                updateValue('Session Num', sessionNum);
                
                // Update reason - find the reason card specifically
                const reasonCard = Array.from(document.querySelectorAll('.status-card')).find(card => {{
                    const h3 = card.querySelector('h3');
                    return h3 && h3.textContent.trim() === 'Scene Switch Reason';
                }});
                if (reasonCard) {{
                    const valueEl = reasonCard.querySelector('.value');
                    if (valueEl) {{
                        valueEl.textContent = data.reason;
                    }}
                }}
                
            }} catch (error) {{
                console.error('Failed to update status:', error);
            }}
        }}
        
        async function updateEvents() {{
            try {{
                const response = await fetch(`${{API_BASE}}/api/events?count=${{config.dashboard_event_log_size}}`);
                const data = await response.json();
                events = data.events;
                renderEvents();
            }} catch (error) {{
                console.error('Failed to update events:', error);
            }}
        }}
        
        function updateConnectionStatus(type, connected) {{
            // Update iRacing connection (first indicator)
            const iracingIndicator = document.querySelectorAll('.status-indicator')[0];
            if (type === 'iracing') {{
                if (connected) {{
                    iracingIndicator.classList.remove('disconnected');
                }} else {{
                    iracingIndicator.classList.add('disconnected');
                }}
            }}
            
            // Update OBS connection (second indicator)
            const obsIndicator = document.querySelectorAll('.status-indicator')[1];
            if (type === 'obs') {{
                if (connected) {{
                    obsIndicator.classList.remove('disconnected');
                }} else {{
                    obsIndicator.classList.add('disconnected');
                }}
            }}
        }}
        
        function updateValue(label, value) {{
            // Find card by label and update value
            const cards = document.querySelectorAll('.status-card');
            cards.forEach(card => {{
                const h3 = card.querySelector('h3');
                if (h3 && h3.textContent.trim() === label) {{
                    const valueEl = card.querySelector('.value');
                    if (valueEl) {{
                        valueEl.textContent = value;
                    }}
                }}
            }});
        }}
        
        function formatStreamDuration(ms) {{
            if (!ms) return '00:00';
            const totalSeconds = Math.floor(ms / 1000);
            const hours = Math.floor(totalSeconds / 3600);
            const minutes = Math.floor((totalSeconds % 3600) / 60);
            const seconds = totalSeconds % 60;
            if (hours > 0) {{
                return `${{hours.toString().padStart(2, '0')}}:${{minutes.toString().padStart(2, '0')}}:${{seconds.toString().padStart(2, '0')}}`;
            }}
            return `${{minutes.toString().padStart(2, '0')}}:${{seconds.toString().padStart(2, '0')}}`;
        }}
        
        function formatDuration(seconds) {{
            if (seconds === null || seconds === undefined) return 'N/A';
            const totalSeconds = Math.floor(seconds);
            const hours = Math.floor(totalSeconds / 3600);
            const minutes = Math.floor((totalSeconds % 3600) / 60);
            const secs = totalSeconds % 60;
            if (hours > 0) {{
                return `${{hours.toString().padStart(2, '0')}}:${{minutes.toString().padStart(2, '0')}}:${{secs.toString().padStart(2, '0')}}`;
            }}
            return `${{minutes.toString().padStart(2, '0')}}:${{secs.toString().padStart(2, '0')}}`;
        }}
        
        async function toggleAutoswitch() {{
            try {{
                await fetch(`${{API_BASE}}/autoswitch/toggle`, {{ method: 'POST' }});
                await updateStatus();
                await updateEvents();
            }} catch (error) {{
                console.error('Failed to toggle autoswitch:', error);
            }}
        }}
        
        async function resetRestartMode() {{
            try {{
                await fetch(`${{API_BASE}}/restart-mode/reset`, {{ method: 'POST' }});
                await updateStatus();
            }} catch (error) {{
                console.error('Failed to reset restart mode:', error);
            }}
        }}
        
        async function reloadConfig() {{
            try {{
                const response = await fetch(`${{API_BASE}}/config/reload`, {{ method: 'POST' }});
                const data = await response.json();
                
                if (response.ok) {{
                    // Show success notification
                    alert('Config reloaded successfully');
                }} else {{
                    // Show error notification
                    alert('Failed to reload config: ' + (data.error || 'Unknown error'));
                }}
            }} catch (error) {{
                console.error('Failed to reload config:', error);
                alert('Failed to reload config: ' + error.message);
            }}
        }}
        
        async function shutdownService() {{
            if (!confirm('Are you sure you want to shutdown the service? This will stop the iRacing OBS Switcher.')) {{
                return;
            }}
            try {{
                const response = await fetch(`${{API_BASE}}/shutdown`, {{ method: 'POST' }});
                const data = await response.json();
                
                if (response.ok) {{
                    alert('Service shutdown initiated. The service will stop shortly.');
                }} else {{
                    alert('Failed to shutdown service: ' + (data.error || 'Unknown error'));
                }}
            }} catch (error) {{
                console.error('Failed to shutdown service:', error);
                alert('Failed to shutdown service: ' + error.message);
            }}
        }}
        
        async function updateMetrics() {{
            try {{
                const response = await fetch(`${{API_BASE}}/metrics`);
                const data = await response.json();
                
                // Update metrics
                updateValue('Scene Switches', data.scene_switches_total || 0);
                const latency = data.scene_switch_latency_avg_ms;
                updateValue('Avg Latency', latency !== null && latency !== undefined ? latency.toFixed(4) + ' ms' : 'N/A');
                updateValue('Uptime', formatDuration(data.uptime_seconds));
                
                // iRacing Connected - show cumulative | current
                const iracingCumulative = data.iracing_connected_duration_seconds;
                const iracingCurrent = data.iracing_connected_duration_current_session_seconds;
                const iracingEl = document.getElementById('metrics-iracing-time');
                const iracingLabelEl = document.getElementById('metrics-iracing-label');
                if (iracingEl) {{
                    let html = '<span>' + (formatDuration(iracingCumulative) || 'N/A') + '</span>';
                    if (iracingCurrent !== null && iracingCurrent !== undefined && iracingCurrent > 0) {{
                        html += ' <span style="font-size: 0.75em; color: #aaa;">| ' + formatDuration(iracingCurrent) + '</span>';
                    }}
                    iracingEl.innerHTML = html;
                }}
                if (iracingLabelEl) {{
                    iracingLabelEl.parentElement.innerHTML = 'Cumulative' + (iracingCurrent !== null && iracingCurrent !== undefined && iracingCurrent > 0 ? ' | <span>Current</span>' : '');
                }}
                
                // OBS Connected - show cumulative | current
                const obsCumulative = data.obs_connected_duration_seconds;
                const obsCurrent = data.obs_connected_duration_current_session_seconds;
                const obsEl = document.getElementById('metrics-obs-time');
                const obsLabelEl = document.getElementById('metrics-obs-label');
                if (obsEl) {{
                    let html = '<span>' + (formatDuration(obsCumulative) || 'N/A') + '</span>';
                    if (obsCurrent !== null && obsCurrent !== undefined && obsCurrent > 0) {{
                        html += ' <span style="font-size: 0.75em; color: #aaa;">| ' + formatDuration(obsCurrent) + '</span>';
                    }}
                    obsEl.innerHTML = html;
                }}
                if (obsLabelEl) {{
                    obsLabelEl.parentElement.innerHTML = 'Cumulative' + (obsCurrent !== null && obsCurrent !== undefined && obsCurrent > 0 ? ' | <span>Current</span>' : '');
                }}
            }} catch (error) {{
                console.error('Failed to update metrics:', error);
            }}
        }}
        
        // Initial render
        renderEvents();
        
        // Auto-update
        setInterval(updateStatus, UPDATE_INTERVAL);
        setInterval(updateEvents, UPDATE_INTERVAL);
        setInterval(updateMetrics, UPDATE_INTERVAL);
        
        // Initial load
        updateStatus();
        updateEvents();
        updateMetrics();
    </script>
</body>
</html>
"""

        response = web.Response(text=html, content_type="text/html")
        # Strong cache control headers
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Accel-Expires"] = "0"  # For nginx proxy
        response.headers["Last-Modified"] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
        response.headers["ETag"] = f'"{cache_bust}"'  # Unique ETag for each request
        return response
    except Exception as e:
        logger.error(f"Error in handle_gr_status: {e}", exc_info=True)
        return web.Response(text=f"Internal server error: {e}", status=500)


async def handle_vr_status_wrapper(request: web.Request) -> web.Response:
    """
    Handle GET /vr-status-wrapper - Wrapper for RaceLab VR with iframe and meta refresh.
    
    RaceLab VR widgety se načítají jen při startu a nepodporují JS ani meta refresh.
    Tento wrapper vrací HTML s iframe, který se refreshuje pomocí meta refresh.
    """
    config: Optional[AppConfig] = request.app.get("config")
    update_interval_ms = int(1000 / (config.dashboard_update_fps if config else 2))
    refresh_seconds = max(1, update_interval_ms // 1000)
    
    import time
    cache_bust = int(time.time() * 1000)
    
    # Get base URL from request
    base_url = f"{request.scheme}://{request.host}"
    iframe_url = f"{base_url}/vr-status?t={cache_bust}"
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="{refresh_seconds}">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <title>VR Status Wrapper</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        html, body {{
            width: 100%;
            height: 100%;
            overflow: hidden;
        }}
        iframe {{
            width: 100%;
            height: 100%;
            border: none;
        }}
    </style>
</head>
<body>
    <iframe src="{iframe_url}" frameborder="0"></iframe>
</body>
</html>
"""
    
    response = web.Response(text=html, content_type="text/html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


async def handle_vr_status(request: web.Request) -> web.Response:
    """
    Handle GET /vr-status - VR widget.
    
    Note: RaceLab VR widgety se načítají jen při startu a neaktualizují se automaticky.
    Pokud RaceLab VR nepodporuje refresh interval, widget se neaktualizuje.
    
    Možná řešení:
    1. Zkus použít /vr-status-wrapper (s iframe a meta refresh)
    2. Nastav refresh interval v RaceLab VR widget nastavení
    3. Použij externí nástroj pro periodický refresh
    """
    # Check if this is a redirect request (for cache busting)
    redirect_param = request.query.get("redirect")
    if redirect_param == "1":
        # Redirect to URL with timestamp to force refresh
        import time
        timestamp = int(time.time() * 1000)
        redirect_url = f"{request.scheme}://{request.host}/vr-status?t={timestamp}"
        return web.Response(status=302, headers={"Location": redirect_url})
    
    # Get current state
    state = _get_current_state()
    if state is None:
        return web.Response(text="Service not initialized", status=503)

    # Get streaming status
    is_streaming = False
    stream_duration_ms: Optional[int] = None
    obs_client = _get_obs_client()
    if obs_client is not None and state.connected_obs:
        try:
            is_streaming, stream_duration_ms = await obs_client.get_stream_status()
        except Exception:
            pass

    config: Optional[AppConfig] = request.app.get("config")
    update_interval_ms = int(1000 / (config.dashboard_update_fps if config else 2))
    refresh_seconds = max(1, update_interval_ms // 1000)  # Convert to seconds, minimum 1 second

    # Get icon paths
    icons_path = config.dashboard_vr_icons_path if config else None

    import time
    cache_bust = int(time.time() * 1000)  # Timestamp for cache busting
    
    # Note: RaceLab VR may not support meta refresh or JS
    # The widget should be configured in RaceLab VR with a refresh interval
    # URL should include timestamp parameter for cache busting: /vr-status?t=1234567890
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate, max-age=0">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <!-- Note: RaceLab VR may not support meta refresh - configure refresh interval in RaceLab VR widget settings -->
    <!-- <meta http-equiv="refresh" content="{refresh_seconds}"> -->
    <title>iRacing OBS Switcher - VR Status</title>
    <!-- Cache bust: {cache_bust} -->
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: transparent;
            min-width: 420px;
            width: fit-content;
            height: 75px;
            overflow: hidden;
            color: #fff;
        }}
        
        .vr-bar {{
            width: 100%;
            height: 100%;
            min-width: 420px;
            background: rgba(0, 0, 0, 0.5);
            border-left: 8px solid #ff9800;
            border-radius: 0 10px 10px 0;
            display: flex;
            align-items: center;
            padding: 0 15px;
            gap: 20px;
            color: #fff;
        }}
        
        .status-diodes {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        
        .diode {{
            width: 24px;
            height: 24px;
            border-radius: 50%;
            background: #4caf50;
        }}
        
        .diode.disconnected {{
            background: #f44336;
        }}
        
        .streaming-indicator {{
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 0 20px;
        }}
        
        .rec-dot {{
            width: 42px;
            height: 42px;
            border-radius: 50%;
            background: {'#f44336' if is_streaming else '#666'};
            animation: {'pulse 2s infinite' if is_streaming else 'none'};
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        
        .info {{
            display: flex;
            align-items: center;
            gap: 15px;
            flex: 1;
            font-weight: 600;
            font-size: 18px;
            color: #fff;
        }}
        
        .scene-name {{
            font-size: 22px;
            font-weight: 700;
            color: #fff;
        }}
        
        .stream-duration {{
            font-size: 18px;
            font-weight: 600;
            color: #fff;
        }}
    </style>
</head>
<body>
    <div class="vr-bar">
        <div class="status-diodes">
            <div class="diode {'disconnected' if not state.connected_obs else ''}" id="obs-diode"></div>
            <div class="diode {'disconnected' if not state.connected_iracing else ''}" id="iracing-diode"></div>
        </div>
        
        <div class="streaming-indicator">
            <div class="rec-dot" id="rec-dot"></div>
            <span class="stream-duration" id="stream-duration">{format_stream_duration(stream_duration_ms)}</span>
        </div>
        
        <div class="info">
            <span class="scene-name" id="scene-name">{state.current_scene}</span>
        </div>
    </div>
    
    <script>
        // Test JavaScript availability immediately
        (function() {{
            const testResults = [];
            
            // Test window.location
            const hasWindowLocation = typeof window !== 'undefined' && typeof window.location !== 'undefined';
            testResults.push('window.location: ' + (hasWindowLocation ? 'EXISTS' : 'NOT FOUND'));
            
            // Test XMLHttpRequest
            const hasXHR = typeof XMLHttpRequest !== 'undefined';
            testResults.push('XMLHttpRequest: ' + (hasXHR ? 'EXISTS' : 'NOT FOUND'));
            
            // Test fetch
            const hasFetch = typeof fetch !== 'undefined';
            testResults.push('fetch: ' + (hasFetch ? 'EXISTS' : 'NOT FOUND'));
            
            // Test window object
            const hasWindow = typeof window !== 'undefined';
            testResults.push('window: ' + (hasWindow ? 'EXISTS' : 'NOT FOUND'));
            
            // Display results in the scene name element
            const sceneNameEl = document.getElementById('scene-name');
            if (sceneNameEl) {{
                const originalText = sceneNameEl.textContent;
                sceneNameEl.textContent = originalText + ' | JS: ' + testResults.join(', ');
                sceneNameEl.style.color = '#ffff00'; // Yellow to make it visible
            }}
            
            // Also log to console if available
            if (typeof console !== 'undefined' && typeof console.log !== 'undefined') {{
                console.log('VR Dashboard JS Test Results:', testResults);
            }}
        }})();
    </script>
</body>
</html>
"""

    response = web.Response(text=html, content_type="text/html")
    # Strong cache control headers for RaceLab VR
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Accel-Expires"] = "0"  # For nginx proxy
    response.headers["Last-Modified"] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    response.headers["ETag"] = f'"{cache_bust}"'  # Unique ETag for each request
    return response


async def handle_test_widget(request: web.Request) -> web.Response:
    """Handle GET /test - simple test widget to verify JS works."""
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>JS Test</title>
</head>
<body>
    <div id="content">STARTED</div>
    <script>
        document.getElementById('content').textContent = 'JS JEDE';
    </script>
</body>
</html>
"""
    response = web.Response(text=html, content_type="text/html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
