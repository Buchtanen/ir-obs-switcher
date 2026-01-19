"""HTML dashboard endpoints."""
from __future__ import annotations

import json
import logging
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


async def handle_gr_status(request: web.Request) -> web.Response:
    """Handle GET /gr-status - large dashboard."""
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

    # Calculate update interval from FPS
    update_interval_ms = int(1000 / config.dashboard_update_fps)

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
                <div class="connection-status">
                    <div class="status-indicator {'disconnected' if not state.connected_iracing else ''}"></div>
                    <span class="value">{'Connected' if state.connected_iracing else 'Disconnected'}</span>
                </div>
            </div>
            
            <div class="status-card">
                <h3>OBS Connection</h3>
                <div class="connection-status">
                    <div class="status-indicator {'disconnected' if not state.connected_obs else ''}"></div>
                    <span class="value">{'Connected' if state.connected_obs else 'Disconnected'}</span>
                </div>
            </div>
            
            <div class="status-card">
                <h3>OBS Profile</h3>
                <div class="value">{obs_profile or 'N/A'}</div>
            </div>
            
            <div class="status-card">
                <h3>Current Scene</h3>
                <div class="value">{state.current_scene}</div>
            </div>
            
            <div class="status-card">
                <h3>Streaming</h3>
                <div class="streaming-indicator">
                    <div class="rec-dot"></div>
                    <span class="value">{'LIVE' if is_streaming else 'IDLE'}</span>
                </div>
            </div>
            
            <div class="status-card">
                <h3>Stream Duration</h3>
                <div class="value">{format_stream_duration(stream_duration_ms)}</div>
            </div>
            
            <div class="status-card">
                <h3>Mode</h3>
                <div class="value">{state.mode.value}</div>
            </div>
            
            <div class="status-card">
                <h3>Autoswitch</h3>
                <div class="value">{'ON' if state.autoswitch else 'OFF'}</div>
            </div>
        </div>
        
        <div class="status-card" style="margin-bottom: 30px;">
            <h3>Scene Switch Reason</h3>
            <div class="value" style="font-size: 1.2em;">{state.reason}</div>
        </div>
        
        <div class="controls">
            <button onclick="toggleAutoswitch()">Toggle Autoswitch</button>
            <button onclick="resetRestartMode()">Reset RESTART Mode</button>
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
                
                // Update stream duration
                updateValue('Stream Duration', formatStreamDuration(data.stream_duration_ms));
                
                // Update mode
                updateValue('Mode', data.mode);
                
                // Update autoswitch
                updateValue('Autoswitch', data.autoswitch ? 'ON' : 'OFF');
                
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
        
        // Initial render
        renderEvents();
        
        // Auto-update
        setInterval(updateStatus, UPDATE_INTERVAL);
        setInterval(updateEvents, UPDATE_INTERVAL);
        
        // Initial load
        updateStatus();
        updateEvents();
    </script>
</body>
</html>
"""

    response = web.Response(text=html, content_type="text/html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


async def handle_vr_status(request: web.Request) -> web.Response:
    """Handle GET /vr-status - VR widget."""
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

    # Get icon paths
    icons_path = config.dashboard_vr_icons_path if config else None

    import time
    cache_bust = int(time.time() * 1000)  # Timestamp for cache busting
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
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
        const API_BASE = window.location.origin;
        const UPDATE_INTERVAL = {update_interval_ms};
        
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
        
        async function updateStatus() {{
            try {{
                const response = await fetch(`${{API_BASE}}/status`);
                const data = await response.json();
                
                // Update connection diodes
                document.getElementById('obs-diode').classList.toggle('disconnected', !data.connected_obs);
                document.getElementById('iracing-diode').classList.toggle('disconnected', !data.connected_iracing);
                
                // Update streaming
                const recDot = document.getElementById('rec-dot');
                if (data.streaming) {{
                    recDot.style.background = '#f44336';
                    recDot.style.animation = 'pulse 2s infinite';
                }} else {{
                    recDot.style.background = '#666';
                    recDot.style.animation = 'none';
                }}
                
                // Update stream duration
                document.getElementById('stream-duration').textContent = formatStreamDuration(data.stream_duration_ms);
                
                // Update scene
                document.getElementById('scene-name').textContent = data.current_scene;
                
            }} catch (error) {{
                console.error('Failed to update status:', error);
            }}
        }}
        
        // Auto-update
        setInterval(updateStatus, UPDATE_INTERVAL);
        
        // Initial load
        updateStatus();
    </script>
</body>
</html>
"""

    response = web.Response(text=html, content_type="text/html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
