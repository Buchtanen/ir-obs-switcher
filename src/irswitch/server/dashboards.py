"""HTML dashboard endpoints."""

from __future__ import annotations

import json
import logging
import time

from aiohttp import web

from irswitch import __version__
from irswitch.config import AppConfig
from irswitch.i18n import get_translator
from irswitch.server.app_keys import APP_CONFIG
from irswitch.server.event_log import get_event_log
from irswitch.server.metrics_display import summarize_errors_total


# Import these lazily to avoid circular import
def _get_current_state():
    from irswitch.server.api import _current_state

    return _current_state


def _get_obs_client():
    from irswitch.server.api import _obs_client

    return _obs_client


logger = logging.getLogger(__name__)


def format_stream_duration(ms: int | None) -> str:
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


def format_duration(seconds: float | None) -> str:
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
        config: AppConfig | None = request.app.get(APP_CONFIG)
        if config is None:
            return web.Response(text="Configuration not available", status=500)

        # Get translator for current language
        translator = get_translator()

        # Get current state
        state = _get_current_state()
        if state is None:
            return web.Response(text="Service not initialized", status=503)

        # Get streaming status
        is_streaming = False
        stream_duration_ms: int | None = None
        stream_title: str | None = None
        stream_description: str | None = None
        is_selected = False
        is_ready_selected = False
        obs_client = _get_obs_client()
        if obs_client is not None and state.connected_obs:
            try:
                is_streaming, stream_duration_ms = await obs_client.get_stream_status()
            except Exception:
                pass

            # Check if stream is selected (not just defined)
            is_selected = False
            is_ready_selected = False
            try:
                is_selected, is_ready_selected = await obs_client.is_stream_selected()
            except Exception:
                pass

            # Get cached stream title (don't make API calls from dashboard)
            stream_title, stream_description, quota_exceeded, api_key_missing = (
                obs_client.get_cached_stream_info()
            )
            if quota_exceeded:
                logger.debug("YouTube API quota exceeded - using cached stream title")

            # Check if stream is "planned" (defined but not selected) vs "current" (selected/ready)
            # Only show stream row if:
            # 1. Streaming is active (definitely current)
            # 2. Stream is selected AND has stream info (key/broadcast_id) - actually selected in Broadcast Manager
            # 3. Stream has title (may be from previous selection or defined stream)
            # If stream is selected/ready but title is not available, show "Ready" instead
            # Only if stream is actually selected (has key/broadcast_id), not just configured
            if not stream_title and (is_streaming or (is_selected and is_ready_selected)):
                stream_title = "Stream Ready (Title Not Available)"

        # Get OBS profile
        obs_profile: str | None = None
        if obs_client is not None and state.connected_obs:
            try:
                obs_profile = await obs_client.get_current_profile()
                if obs_profile is None:
                    logger.debug(
                        "OBS profile is None - profile may not be available via WebSocket API"
                    )
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
        errors_total_count, errors_breakdown = summarize_errors_total(
            metrics_dict.get("errors_total")
        )

        # Calculate update interval from FPS
        update_interval_ms = int(1000 / config.dashboard_update_fps)

        # Cache busting timestamp
        cache_bust = int(time.time() * 1000)

        # Build image paths
        bg_image = config.dashboard_gr_background_image or ""
        logo_app = config.dashboard_gr_logo_app or "/assets/favicon/favicon-96x96.png"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <link rel="icon" type="image/png" href="/assets/favicon/favicon-96x96.png">
    <link rel="icon" type="image/x-icon" href="/assets/favicon/favicon.ico">
    <link rel="apple-touch-icon" href="/assets/favicon/apple-touch-icon.png">
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
            padding: 12px;
            overflow-x: hidden;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(0, 0, 0, 0.7);
            border-radius: 8px;
            padding: 15px;
            backdrop-filter: blur(10px);
        }}

        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}

        .header h1 {{
            font-size: 1.3em;
            font-weight: 600;
        }}

        .logo-container {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}

        .logo {{
            height: 28px;
            width: auto;
            opacity: 0.9;
        }}

        .status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 10px;
            margin-bottom: 12px;
        }}

        .status-grid.compact-row {{
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        }}

        .status-card {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 10px 12px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}

        .status-card h3 {{
            font-size: 0.7em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #888;
            margin-bottom: 4px;
        }}

        .status-card .sublabel {{
            font-size: 0.65em;
            color: #555;
            margin-bottom: 3px;
            min-height: 1em;
        }}

        .status-card .value {{
            font-size: 1.1em;
            font-weight: 600;
            color: #fff;
        }}
        
        .connection-status {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .status-indicator {{
            width: 17px;
            height: 17px;
            border-radius: 50%;
            background: #4caf50;
            box-shadow: 0 0 8px rgba(76, 175, 80, 0.6);
            margin-top: 3px;
            flex-shrink: 0;
        }}
        
        .status-indicator.disconnected {{
            background: #f44336;
            box-shadow: 0 0 8px rgba(244, 67, 54, 0.6);
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
            gap: 8px;
            margin-bottom: 12px;
            flex-wrap: wrap;
        }}

        .config-reload-panel {{
            display: none;
            margin-bottom: 12px;
            padding: 12px 14px;
            border-radius: 4px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            background: rgba(255, 255, 255, 0.06);
            font-size: 0.85em;
            line-height: 1.45;
        }}

        .config-reload-panel.visible {{
            display: block;
        }}

        .config-reload-panel.needs-restart {{
            border-color: rgba(255, 152, 0, 0.5);
            background: rgba(255, 152, 0, 0.12);
        }}

        .config-reload-panel h4 {{
            margin: 0 0 8px 0;
            font-size: 0.95em;
            font-weight: 600;
        }}

        .config-reload-panel .reload-keys {{
            font-family: ui-monospace, Consolas, monospace;
            word-break: break-word;
        }}

        .config-reload-panel .reload-section + .reload-section {{
            margin-top: 8px;
        }}

        button {{
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: #fff;
            padding: 8px 14px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85em;
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
            border-radius: 6px;
            padding: 12px;
            max-height: 300px;
            overflow-y: auto;
        }}

        .event-log h3 {{
            margin-bottom: 10px;
            font-size: 0.9em;
        }}
        
        .event-item {{
            padding: 10px;
            margin-bottom: 8px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
            border-left: 3px solid #4caf50;
            font-size: 0.9em;
            transition: background-color 0.3s ease-out, box-shadow 0.3s ease-out;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 0 20px rgba(76, 175, 80, 0.05);
            position: relative;
        }}
        
        .event-item:hover {{
            background: rgba(255, 255, 255, 0.12);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3), inset 0 0 30px rgba(76, 175, 80, 0.08);
        }}
        
        .event-item::before {{
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 3px;
            background: linear-gradient(to bottom, rgba(76, 175, 80, 0.8), rgba(76, 175, 80, 0.4));
            border-radius: 4px 0 0 4px;
        }}
        
        .event-item.new-event {{
            background: rgba(76, 175, 80, 0.15);
            box-shadow: 0 0 15px rgba(76, 175, 80, 0.4), inset 0 0 40px rgba(76, 175, 80, 0.1);
            animation: highlightFade 3s ease-out forwards;
        }}
        
        @keyframes highlightFade {{
            0% {{
                background: rgba(76, 175, 80, 0.25);
                box-shadow: 0 0 20px rgba(76, 175, 80, 0.6), inset 0 0 50px rgba(76, 175, 80, 0.15);
            }}
            100% {{
                background: rgba(255, 255, 255, 0.08);
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 0 20px rgba(76, 175, 80, 0.05);
            }}
        }}
        
        .event-item.connection_lost {{
            border-left-color: #f44336;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 0 20px rgba(244, 67, 54, 0.05);
        }}
        
        .event-item.connection_lost::before {{
            background: linear-gradient(to bottom, rgba(244, 67, 54, 0.8), rgba(244, 67, 54, 0.4));
        }}
        
        .event-item.connection_lost:hover {{
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3), inset 0 0 30px rgba(244, 67, 54, 0.08);
        }}
        
        .event-item.connection_lost.new-event {{
            background: rgba(244, 67, 54, 0.15);
            box-shadow: 0 0 15px rgba(244, 67, 54, 0.4), inset 0 0 40px rgba(244, 67, 54, 0.1);
            animation: highlightFadeError 3s ease-out forwards;
        }}
        
        @keyframes highlightFadeError {{
            0% {{
                background: rgba(244, 67, 54, 0.25);
                box-shadow: 0 0 20px rgba(244, 67, 54, 0.6), inset 0 0 50px rgba(244, 67, 54, 0.15);
            }}
            100% {{
                background: rgba(255, 255, 255, 0.08);
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 0 20px rgba(244, 67, 54, 0.05);
            }}
        }}
        
        .event-item.scene_switch {{
            border-left-color: #2196f3;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 0 20px rgba(33, 150, 243, 0.05);
        }}
        
        .event-item.scene_switch::before {{
            background: linear-gradient(to bottom, rgba(33, 150, 243, 0.8), rgba(33, 150, 243, 0.4));
        }}
        
        .event-item.scene_switch:hover {{
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3), inset 0 0 30px rgba(33, 150, 243, 0.08);
        }}
        
        .event-item.scene_switch.new-event {{
            background: rgba(33, 150, 243, 0.15);
            box-shadow: 0 0 15px rgba(33, 150, 243, 0.4), inset 0 0 40px rgba(33, 150, 243, 0.1);
            animation: highlightFadeInfo 3s ease-out forwards;
        }}
        
        @keyframes highlightFadeInfo {{
            0% {{
                background: rgba(33, 150, 243, 0.25);
                box-shadow: 0 0 20px rgba(33, 150, 243, 0.6), inset 0 0 50px rgba(33, 150, 243, 0.15);
            }}
            100% {{
                background: rgba(255, 255, 255, 0.08);
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 0 20px rgba(33, 150, 243, 0.05);
            }}
        }}
        
        .event-item.override_applied {{
            border-left-color: #ff9800;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 0 20px rgba(255, 152, 0, 0.05);
        }}
        
        .event-item.override_applied::before {{
            background: linear-gradient(to bottom, rgba(255, 152, 0, 0.8), rgba(255, 152, 0, 0.4));
        }}
        
        .event-item.override_applied:hover {{
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3), inset 0 0 30px rgba(255, 152, 0, 0.08);
        }}
        
        .event-item.override_applied.new-event {{
            background: rgba(255, 152, 0, 0.15);
            box-shadow: 0 0 15px rgba(255, 152, 0, 0.4), inset 0 0 40px rgba(255, 152, 0, 0.1);
            animation: highlightFadeWarning 3s ease-out forwards;
        }}
        
        .event-item.youtube_quota_exceeded {{
            border-left: 3px solid #ff9800;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 0 20px rgba(255, 152, 0, 0.05);
        }}
        
        .event-item.youtube_quota_exceeded::before {{
            background: linear-gradient(to bottom, rgba(255, 152, 0, 0.8), rgba(255, 152, 0, 0.4));
        }}
        
        .event-item.youtube_quota_exceeded:hover {{
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3), inset 0 0 30px rgba(255, 152, 0, 0.08);
        }}
        
        .event-item.youtube_quota_exceeded.new-event {{
            background: rgba(255, 152, 0, 0.15);
            box-shadow: 0 0 15px rgba(255, 152, 0, 0.4), inset 0 0 40px rgba(255, 152, 0, 0.1);
            animation: highlightFadeWarning 3s ease-out forwards;
        }}

        @keyframes highlightFadeWarning {{
            0% {{
                background: rgba(255, 152, 0, 0.25);
                box-shadow: 0 0 20px rgba(255, 152, 0, 0.6), inset 0 0 50px rgba(255, 152, 0, 0.15);
            }}
            100% {{
                background: rgba(255, 255, 255, 0.08);
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 0 20px rgba(255, 152, 0, 0.05);
            }}
        }}
        
        .event-time {{
            color: #888;
            font-size: 0.85em;
            margin-right: 12px;
            font-weight: 500;
            opacity: 0.9;
        }}
        
        /* Toast notifications */
        .toast-container {{
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 12px;
            pointer-events: none;
        }}
        
        .toast {{
            background: linear-gradient(135deg, rgba(30, 30, 30, 0.98) 0%, rgba(20, 20, 20, 0.98) 100%);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 18px 24px;
            min-width: 320px;
            max-width: 500px;
            color: #fff;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), 0 2px 8px rgba(0, 0, 0, 0.3);
            animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            backdrop-filter: blur(20px) saturate(180%);
            position: relative;
            overflow: hidden;
            pointer-events: auto;
        }}
        
        .toast::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, transparent, currentColor, transparent);
            opacity: 0.3;
        }}
        
        .toast.success {{
            border-left: 4px solid #4caf50;
            box-shadow: 0 8px 32px rgba(76, 175, 80, 0.2), 0 2px 8px rgba(0, 0, 0, 0.3);
        }}
        
        .toast.success::before {{
            background: linear-gradient(90deg, transparent, #4caf50, transparent);
        }}
        
        .toast.error {{
            border-left: 4px solid #f44336;
            box-shadow: 0 8px 32px rgba(244, 67, 54, 0.2), 0 2px 8px rgba(0, 0, 0, 0.3);
        }}
        
        .toast.error::before {{
            background: linear-gradient(90deg, transparent, #f44336, transparent);
        }}
        
        .toast.warning {{
            border-left: 4px solid #ff9800;
            box-shadow: 0 8px 32px rgba(255, 152, 0, 0.2), 0 2px 8px rgba(0, 0, 0, 0.3);
        }}
        
        .toast.warning::before {{
            background: linear-gradient(90deg, transparent, #ff9800, transparent);
        }}
        
        .toast.info {{
            border-left: 4px solid #2196f3;
            box-shadow: 0 8px 32px rgba(33, 150, 243, 0.2), 0 2px 8px rgba(0, 0, 0, 0.3);
        }}
        
        .toast.info::before {{
            background: linear-gradient(90deg, transparent, #2196f3, transparent);
        }}
        
        .toast-title {{
            font-weight: 600;
            margin-bottom: 6px;
            font-size: 1em;
            color: #fff;
            letter-spacing: 0.3px;
        }}
        
        .toast-message {{
            font-size: 0.9em;
            color: #e0e0e0;
            line-height: 1.5;
        }}
        
        @keyframes slideIn {{
            from {{
                transform: translateX(120%);
                opacity: 0;
            }}
            to {{
                transform: translateX(0);
                opacity: 1;
            }}
        }}
        
        @keyframes slideOut {{
            from {{
                transform: translateX(0);
                opacity: 1;
            }}
            to {{
                transform: translateX(120%);
                opacity: 0;
            }}
        }}
        
        .toast.hiding {{
            animation: slideOut 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }}
        
        /* Confirm dialog overlay */
        #confirm-overlay-container {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            z-index: 20000;
            pointer-events: none;
        }}
        
        .confirm-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(8px);
            z-index: 20000;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.2s ease-out;
            pointer-events: auto;
        }}
        
        .confirm-dialog {{
            background: linear-gradient(135deg, rgba(30, 30, 30, 0.98) 0%, rgba(20, 20, 20, 0.98) 100%);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            padding: 32px;
            min-width: 400px;
            max-width: 600px;
            color: #fff;
            box-shadow: 0 16px 48px rgba(0, 0, 0, 0.6), 0 4px 16px rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(20px) saturate(180%);
            animation: scaleIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
            pointer-events: auto;
        }}
        
        .confirm-dialog h3 {{
            font-size: 1.4em;
            font-weight: 600;
            margin-bottom: 12px;
            color: #fff;
            letter-spacing: 0.3px;
        }}
        
        .confirm-dialog p {{
            font-size: 1em;
            color: #e0e0e0;
            line-height: 1.6;
            margin-bottom: 24px;
        }}
        
        .confirm-buttons {{
            display: flex;
            gap: 12px;
            justify-content: flex-end;
        }}
        
        .confirm-button {{
            padding: 12px 24px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            font-size: 0.95em;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            min-width: 100px;
        }}
        
        .confirm-button:hover {{
            background: rgba(255, 255, 255, 0.2);
            border-color: rgba(255, 255, 255, 0.3);
            transform: translateY(-1px);
        }}
        
        .confirm-button:active {{
            transform: translateY(0);
        }}
        
        .confirm-button.primary {{
            background: linear-gradient(135deg, #4caf50 0%, #45a049 100%);
            border-color: #4caf50;
        }}
        
        .confirm-button.primary:hover {{
            background: linear-gradient(135deg, #45a049 0%, #3d8b40 100%);
            box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);
        }}
        
        .confirm-button.danger {{
            background: linear-gradient(135deg, #f44336 0%, #d32f2f 100%);
            border-color: #f44336;
        }}
        
        .confirm-button.danger:hover {{
            background: linear-gradient(135deg, #d32f2f 0%, #c62828 100%);
            box-shadow: 0 4px 12px rgba(244, 67, 54, 0.3);
        }}
        
        @keyframes fadeIn {{
            from {{
                opacity: 0;
            }}
            to {{
                opacity: 1;
            }}
        }}
        
        @keyframes scaleIn {{
            from {{
                transform: scale(0.9);
                opacity: 0;
            }}
            to {{
                transform: scale(1);
                opacity: 1;
            }}
        }}
        
        .confirm-overlay.hiding {{
            animation: fadeOut 0.2s ease-out forwards;
        }}
        
        .confirm-overlay.hiding .confirm-dialog {{
            animation: scaleOut 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }}
        
        @keyframes fadeOut {{
            from {{
                opacity: 1;
            }}
            to {{
                opacity: 0;
            }}
        }}
        
        @keyframes scaleOut {{
            from {{
                transform: scale(1);
                opacity: 1;
            }}
            to {{
                transform: scale(0.9);
                opacity: 0;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>iRacing OBS Switcher <span style="font-size: 0.5em; color: #888; font-weight: normal;">v{__version__}</span></h1>
            <div class="logo-container">
                {'<img src="' + logo_app + '" alt="App" class="logo">' if logo_app else ''}
            </div>
        </div>
        
        <div class="status-grid compact-row">
            <div class="status-card">
                <h3>{translator.t('iracing_connection')} / {translator.t('obs_connection')}</h3>
                <div class="connection-status">
                    <div class="status-indicator {'disconnected' if not state.connected_iracing else ''}" title="iRacing"></div>
                    <div class="status-indicator {'disconnected' if not state.connected_obs else ''}" title="OBS"></div>
                </div>
            </div>

            <div class="status-card">
                <h3>{translator.t('mode')}</h3>
                <div class="value">{state.mode}</div>
            </div>

            <div class="status-card">
                <h3>{translator.t('current_scene')}</h3>
                <div class="value">{state.current_scene}</div>
            </div>

            <div class="status-card">
                <h3>{translator.t('obs_profile')}</h3>
                <div class="value">{obs_profile or translator.t('n_a')}</div>
            </div>
        </div>
        
        <div class="status-grid" style="margin-bottom: 12px;" id="stream-row-container">
            <div class="status-card" style="grid-column: 1 / -1;">
                <h3 id="stream-row-header">Stream</h3>
                <div id="stream-row-content">
                    <div class="value" style="font-size: 0.9em; color: #888;">No stream information available</div>
                </div>
            </div>
        </div>

        <div class="status-grid" style="margin-bottom: 12px;">
            <div class="status-card">
                <h3>{translator.t('streaming')}</h3>
                <div class="streaming-indicator">
                    <div class="rec-dot"></div>
                    <span class="value">{'LIVE' if is_streaming else 'IDLE'}</span>
                </div>
            </div>

            <div class="status-card">
                <h3>{translator.t('autoswitch')}</h3>
                <div class="value">{translator.t('on') if state.autoswitch else translator.t('off')}</div>
            </div>

            <div class="status-card" style="grid-column: span 2;">
                <h3>{translator.t('session_type')} / {translator.t('session_name')}</h3>
                <div class="value" id="session-info">
                    {{
                        ''.join([
                            state.session_type if state.session_type != 'Test' and state.session_type is not None else translator.t('n_a'),
                            '' if state.session_type == 'Test' or state.session_name is None else ' | ' + state.session_name,
                            '' if state.session_type == 'Test' or state.session_num_display is None else ' (' + state.session_num_display + ')'
                        ])
                    }}
                </div>
            </div>
        </div>

        <div class="status-grid" style="margin-bottom: 12px;">
            <div class="status-card">
                <h3>{translator.t('scene_switches')}</h3>
                <div class="value" id="metrics-switches">{metrics_dict.get('scene_switches_total', 0)}</div>
            </div>

            <div class="status-card">
                <h3>{translator.t('avg_latency')}</h3>
                <div class="value" id="metrics-latency">
                    {f"{metrics_dict.get('scene_switch_latency_avg_ms', 0):.4f} ms" if metrics_dict.get('scene_switch_latency_avg_ms') is not None else translator.t('n_a')}
                </div>
            </div>

            <div class="status-card">
                <h3>{translator.t('uptime')}</h3>
                <div class="value" id="metrics-uptime">{format_duration(metrics_dict.get('uptime_seconds', 0))}</div>
            </div>

            <div class="status-card">
                <h3>{translator.t('iracing_connected')}</h3>
                <div class="value" id="metrics-iracing-time">
                    {format_duration(metrics_dict.get('iracing_connected_duration_seconds')) if metrics_dict.get('iracing_connected_duration_seconds') is not None else translator.t('n_a')}
                </div>
            </div>

            <div class="status-card">
                <h3>{translator.t('obs_connected')}</h3>
                <div class="value" id="metrics-obs-time">
                    {format_duration(metrics_dict.get('obs_connected_duration_seconds')) if metrics_dict.get('obs_connected_duration_seconds') is not None else translator.t('n_a')}
                </div>
            </div>

            <div class="status-card">
                <h3>{translator.t('errors_total')}</h3>
                <div class="value" id="metrics-errors">{errors_total_count}</div>
                <div class="sublabel" id="metrics-errors-breakdown">
                    {errors_breakdown if errors_breakdown else translator.t('n_a')}
                </div>
            </div>
        </div>

        <div class="status-card" style="margin-bottom: 12px;">
            <h3>{translator.t('scene_switch_reason')}</h3>
            <div class="value">{state.reason}</div>
        </div>
        
        <div class="controls">
            <button onclick="toggleAutoswitch()">{translator.t('toggle_autoswitch')}</button>
            <button onclick="resetRestartMode()">Reset RESTART Mode</button>
            <button onclick="reinitStream()">{translator.t('reinit_stream')}</button>
            <button onclick="reloadConfig()">Reload Config</button>
            <button onclick="resetService()" style="background: rgba(255, 152, 0, 0.2); border-color: rgba(255, 152, 0, 0.4);">Reset Service</button>
            <button onclick="restartService()" style="background: rgba(255, 152, 0, 0.25); border-color: rgba(255, 152, 0, 0.5);">{translator.t('restart_service')}</button>
            <button onclick="shutdownService()" style="background: rgba(244, 67, 54, 0.2); border-color: rgba(244, 67, 54, 0.4);">Shutdown Service</button>
        </div>

        <div id="config-reload-panel" class="config-reload-panel" aria-live="polite"></div>
        
        <div class="event-log">
            <h3>Event Log</h3>
            <div id="events-container"></div>
        </div>
    </div>
    
    <div class="toast-container" id="toast-container"></div>
    <div id="confirm-overlay-container"></div>
    
    <script>
        const API_BASE = window.location.origin;
        const UPDATE_INTERVAL = {update_interval_ms};
        const config = {{
            dashboard_event_log_size: {config.dashboard_event_log_size}
        }};
        
        // Translations
        const translations = {json.dumps(translator.translations)};
        function t(key, params = {{}}) {{
            let text = translations[key] || key;
            if (Object.keys(params).length > 0) {{
                for (const [k, v] of Object.entries(params)) {{
                    const placeholder = '{{' + k + '}}';
                    text = text.replace(placeholder, v);
                }}
            }}
            return text;
        }}
        
        let events = {json.dumps(events)};
        
        function formatTime(timestamp) {{
            const date = new Date(timestamp);
            return date.toLocaleTimeString();
        }}
        
        function getQuotaResetTimeLocal() {{
            // YouTube API quota resets at midnight Pacific Time (PT)
            // Calculate next midnight PT and convert to local time
            
            const now = new Date();
            
            // Get current time in PT
            const ptFormatter = new Intl.DateTimeFormat('en-US', {{
                timeZone: 'America/Los_Angeles',
                year: 'numeric',
                month: 'numeric',
                day: 'numeric',
                hour: 'numeric',
                minute: 'numeric',
                hour12: false
            }});
            
            const ptParts = ptFormatter.formatToParts(now);
            const ptYear = parseInt(ptParts.find(p => p.type === 'year').value);
            const ptMonth = parseInt(ptParts.find(p => p.type === 'month').value) - 1;
            const ptDay = parseInt(ptParts.find(p => p.type === 'day').value);
            const ptHour = parseInt(ptParts.find(p => p.type === 'hour').value);
            const ptMinute = parseInt(ptParts.find(p => p.type === 'minute').value);
            
            // Calculate next midnight PT (add 1 day if not already midnight)
            const nextDay = ptHour > 0 || ptMinute > 0 ? ptDay + 1 : ptDay;
            
            // Find UTC time that corresponds to PT midnight
            // Try different UTC times until we find one that is midnight PT
            let utcMidnight = null;
            // PT midnight is typically UTC 08:00 (PST) or 07:00 (PDT) next day
            for (let utcHour = 7; utcHour <= 8; utcHour++) {{
                const candidate = new Date(Date.UTC(ptYear, ptMonth, nextDay, utcHour, 0, 0));
                const ptCheck = new Intl.DateTimeFormat('en-US', {{
                    timeZone: 'America/Los_Angeles',
                    hour: 'numeric',
                    minute: 'numeric',
                    hour12: false
                }}).formatToParts(candidate);
                const checkHour = parseInt(ptCheck.find(p => p.type === 'hour').value);
                const checkMinute = parseInt(ptCheck.find(p => p.type === 'minute').value);
                if (checkHour === 0 && checkMinute === 0) {{
                    utcMidnight = candidate;
                    break;
                }}
            }}
            
            // Fallback: use UTC 08:00 (PST)
            if (!utcMidnight) {{
                utcMidnight = new Date(Date.UTC(ptYear, ptMonth, nextDay, 8, 0, 0));
            }}
            
            // Format in local time (Czech locale)
            const options = {{}};
            options.hour = '2-digit';
            options.minute = '2-digit';
            return utcMidnight.toLocaleTimeString('cs-CZ', options);
        }}
        
        function formatEventMessage(eventType, message, data) {{
            // Format message in format: "XXX Detected | Action AAAA Activated | Scene SSSS"
            const toastInfo = getToastInfo(eventType, message, data);
            return toastInfo.message;
        }}
        
        function renderEvents(newEventTimestamps = new Set()) {{
            const container = document.getElementById('events-container');
            container.innerHTML = events.map(e => {{
                const isNew = newEventTimestamps.has(e.timestamp);
                const formattedMessage = formatEventMessage(e.type, e.message, e.data);
                return `
                    <div class="event-item ${{e.type}}${{isNew ? ' new-event' : ''}}" data-timestamp="${{e.timestamp}}">
                        <span class="event-time">${{formatTime(e.timestamp)}}</span>
                        ${{formattedMessage}}
                    </div>
                `;
            }}).join('');
            
            // Remove 'new-event' class after animation completes (3 seconds)
            setTimeout(() => {{
                container.querySelectorAll('.new-event').forEach(el => {{
                    el.classList.remove('new-event');
                }});
            }}, 3000);
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
                updateValue(t('autoswitch'), data.autoswitch ? t('on') : t('off'));

                // Update session info - combined in one element
                const sessionInfoEl = document.getElementById('session-info');
                if (sessionInfoEl) {{
                    if (data.session_type === 'Test' || data.session_type === null || data.session_type === undefined) {{
                        sessionInfoEl.textContent = 'N/A';
                    }} else {{
                        let text = data.session_type;
                        if (data.session_name) {{
                            text += ' | ' + data.session_name;
                        }}
                        if (data.session_num_display) {{
                            text += ' (' + data.session_num_display + ')';
                        }}
                        sessionInfoEl.textContent = text;
                    }}
                }}

                // Update OBS Profile if available
                if (data.obs_profile !== undefined) {{
                    updateValue('OBS Profile', data.obs_profile || 'N/A');
                }}

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
                
                // Update stream row visibility and content
                updateStreamRow(data);
                
            }} catch (error) {{
                console.error('Failed to update status:', error);
            }}
        }}
        
        function formatDateTime(isoString) {{
            if (!isoString) return null;
            try {{
                const date = new Date(isoString);
                return date.toLocaleString('cs-CZ', {{ 
                    day: '2-digit', 
                    month: '2-digit', 
                    year: 'numeric',
                    hour: '2-digit', 
                    minute: '2-digit' 
                }});
            }} catch (e) {{
                return null;
            }}
        }}
        
        function formatStreamStatus(status) {{
            const statusMap = {{
                'created': 'Vytvořen',
                'ready': 'Připraven',
                'testing': 'Testování',
                'live': 'ŽIVĚ',
                'complete': 'Dokončen',
                'revoked': 'Zrušen'
            }};
            return statusMap[status] || status || 'Neznámý';
        }}
        
        function formatPrivacyStatus(privacy) {{
            const privacyMap = {{
                'private': 'Soukromé',
                'unlisted': 'Neveřejné',
                'public': 'Veřejné'
            }};
            return privacyMap[privacy] || privacy || 'Neznámé';
        }}
        
        function updateStreamRow(data) {{
            // Stream row is always visible - find container by ID
            const streamRowContainer = document.getElementById('stream-row-container');
            if (!streamRowContainer) return;
            
            const headerEl = document.getElementById('stream-row-header');
            const contentEl = document.getElementById('stream-row-content');
            if (!headerEl || !contentEl) return;
            
            // Determine OAuth status for header
            let oauthStatus = '';
            let oauthColor = '#888';
            let oauthIcon = '🔒';
            if (data.oauth_configured) {{
                if (data.oauth_authenticated) {{
                    oauthStatus = data.oauth_has_refresh_token ? 'Active' : 'Expired';
                    oauthColor = data.oauth_has_refresh_token ? '#4caf50' : '#ffc107';
                    oauthIcon = data.oauth_has_refresh_token ? '✅' : '⚠️';
                }} else {{
                    oauthStatus = 'Pending';
                    oauthColor = '#ff9800';
                    oauthIcon = '⏳';
                }}
            }} else {{
                oauthStatus = 'Not Configured';
                oauthColor = '#888';
                oauthIcon = '⚪';
            }}
            
            // Determine stream readiness
            const isStreamReady = data.connected_obs && (
                data.streaming ||
                (data.stream_selected && data.stream_ready_selected) ||
                (data.stream_title && data.stream_title !== '')
            );
            
            // Build header with OAuth status and icon
            let oauthButton = '';
            if (data.oauth_configured && !data.oauth_authenticated) {{
                oauthButton = '<button onclick="initiateOAuth()" style="margin-left: 8px; padding: 4px 12px; font-size: 0.8em; background: rgba(255, 152, 0, 0.2); border: 1px solid rgba(255, 152, 0, 0.4); border-radius: 4px; cursor: pointer;">Authorize</button>';
            }}
            headerEl.innerHTML = `<span style="display: inline-flex; align-items: center; gap: 6px;"><span>📺</span> Stream</span> <span style="font-size: 0.7em; font-weight: normal; color: ${{oauthColor}}; margin-left: 12px; display: inline-flex; align-items: center; gap: 4px;"><span>${{oauthIcon}}</span> YouTube OAuth: ${{oauthStatus}}</span>${{oauthButton}}`;
            
            // Build content based on stream readiness
            if (!data.connected_obs) {{
                contentEl.innerHTML = `
                    <div class="value" style="font-size: 0.9em; color: #888;">OBS not connected</div>
                `;
            }} else if (!isStreamReady) {{
                contentEl.innerHTML = `
                    <div class="value" style="font-size: 0.9em; color: #888;">Stream not ready</div>
                `;
            }} else {{
                // Stream is ready - show compact info with all details
                const streamTitle = data.stream_title || 'No title available';
                const streamDescription = data.stream_description || null;
                const quotaExceeded = data.youtube_quota_exceeded || false;
                
                // Format times
                const scheduledTime = formatDateTime(data.stream_scheduled_start_time);
                const actualTime = formatDateTime(data.stream_actual_start_time);
                
                // Format status and privacy
                const streamStatus = formatStreamStatus(data.stream_status);
                const privacyStatus = formatPrivacyStatus(data.stream_privacy_status);
                
                // Format viewers
                const viewers = data.stream_concurrent_viewers !== null && data.stream_concurrent_viewers !== undefined 
                    ? data.stream_concurrent_viewers.toLocaleString('cs-CZ') 
                    : null;
                
                // Build info rows
                let infoRows = [];
                
                if (scheduledTime) {{
                    infoRows.push(`<span style="display: inline-flex; align-items: center; gap: 4px;"><span>📅</span> Scheduled: ${{scheduledTime}}</span>`);
                }}
                if (actualTime) {{
                    infoRows.push(`<span style="display: inline-flex; align-items: center; gap: 4px;"><span>▶️</span> Started: ${{actualTime}}</span>`);
                }}
                if (viewers !== null) {{
                    infoRows.push(`<span style="display: inline-flex; align-items: center; gap: 4px;"><span>👁️</span> Viewers: ${{viewers}}</span>`);
                }}
                if (streamStatus) {{
                    const statusColor = data.stream_status === 'live' ? '#f44336' : '#888';
                    infoRows.push(`<span style="display: inline-flex; align-items: center; gap: 4px;"><span>🔴</span> Status: <span style="color: ${{statusColor}}; font-weight: 600;">${{streamStatus}}</span></span>`);
                }}
                if (privacyStatus) {{
                    const privacyIcon = data.stream_privacy_status === 'public' ? '🌐' : data.stream_privacy_status === 'unlisted' ? '🔗' : '🔒';
                    infoRows.push(`<span style="display: inline-flex; align-items: center; gap: 4px;"><span>${{privacyIcon}}</span> Privacy: ${{privacyStatus}}</span>`);
                }}
                
                let infoHtml = '';
                if (infoRows.length > 0) {{
                    infoHtml = `
                        <div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 16px; font-size: 0.8em; color: #aaa;">
                            ${{infoRows.join('')}}
                        </div>
                    `;
                }}
                
                let descriptionHtml = '';
                if (streamDescription && streamDescription !== t('not_available') && streamDescription.trim() !== '') {{
                    // Truncate description if too long
                    const maxDescLength = 120;
                    const truncatedDesc = streamDescription.length > maxDescLength 
                        ? streamDescription.substring(0, maxDescLength) + '...' 
                        : streamDescription;
                    descriptionHtml = `
                        <div style="margin-top: 8px; font-size: 0.85em; color: #aaa; line-height: 1.4;">${{truncatedDesc}}</div>
                    `;
                }}
                
                let warningHtml = '';
                if (quotaExceeded) {{
                    const resetTime = getQuotaResetTimeLocal();
                    const params = {{}};
                    params.time = resetTime;
                    const quotaMsg = t('youtube_quota_message', params);
                    warningHtml = `
                        <div style="margin-top: 8px; font-size: 0.8em; color: #ff9800; display: inline-flex; align-items: center; gap: 4px;"><span>⚠️</span> ${{t('youtube_api_quota_exceeded')}} - ${{quotaMsg}}</div>
                    `;
                }}
                
                // Layout: title on top, then info rows, then description
                contentEl.innerHTML = `
                    <div class="value" style="font-size: 0.95em; font-weight: 600; line-height: 1.3;">${{streamTitle}}</div>
                    ${{infoHtml}}
                    ${{descriptionHtml}}
                    ${{warningHtml}}
                `;
            }}
        }}
        
        // Track last event timestamp to detect new events
        let lastEventTimestamp = events.length > 0 ? Math.max(...events.map(e => e.timestamp)) : 0;
        
        // Map event types to toast types and titles
        function getToastInfo(eventType, message, data) {{
            const typeMap = {{
                'application_started': {{ type: 'info', title: t('application_started') }},
                'connection_lost': {{ type: 'error', title: t('connection_lost') }},
                'connection_restored': {{ type: 'success', title: t('connection_restored') }},
                'loading_started': {{ type: 'info', title: t('loading_started') }},
                'loading_ended': {{ type: 'info', title: t('loading_completed') }},
                'game_started': {{ type: 'success', title: t('game_started') }},
                'scene_switch': {{ type: 'info', title: t('scene_switched') }},
                'stream_started': {{ type: 'success', title: t('stream_started') }},
                'stream_stopped': {{ type: 'warning', title: t('stream_stopped') }},
                'stream_start_failed': {{ type: 'error', title: t('stream_start_failed') }},
                'stream_stop_failed': {{ type: 'error', title: t('stream_stop_failed') }},
                'stream_start_skipped': {{ type: 'warning', title: t('stream_start_skipped') }},
                'stream_stop_skipped': {{ type: 'warning', title: t('stream_stop_skipped') }},
                'override_applied': {{ type: 'info', title: t('override_applied') }},
                'autoswitch_toggled': {{ type: 'info', title: t('autoswitch_toggled') }},
                'stream_title_detected': {{ type: 'success', title: t('stream_title_detected') }},
                'stream_info_refreshed': {{ type: 'success', title: t('stream_info_refreshed') }},
                'stream_selected': {{ type: 'success', title: t('stream_selected') }},
                'stream_deselected': {{ type: 'warning', title: t('stream_deselected') }},
                'youtube_quota_exceeded': {{ type: 'warning', title: t('youtube_quota_exceeded') }}
            }};
            
            const info = typeMap[eventType] || {{ type: 'info', title: eventType.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase()) }};
            
            // Format message for toast in format: "XXX Detected | Action AAAA Activated | Scene SSSS"
            let parts = [];
            
            // Detected part
            let detected = '';
            if (eventType === 'connection_lost' || eventType === 'connection_restored') {{
                const component = message.toLowerCase().includes('iracing') ? 'iRacing' : 
                                 message.toLowerCase().includes('obs') ? 'OBS' : 'Connection';
                detected = eventType === 'connection_lost' ? `${{component}} Disconnected` : `${{component}} Connected`;
            }} else if (eventType === 'game_started') {{
                detected = `${{(data && data.mode ? data.mode.toUpperCase() : 'GAME')}} Detected`;
            }} else {{
                detected = info.title.replace(' Started', ' Detected').replace(' Stopped', ' Detected').replace(' Switched', ' Change Detected');
            }}
            if (detected) parts.push(detected);
            
            // Action part
            let action = '';
            if (eventType === 'connection_lost' || eventType === 'connection_restored') {{
                const component = message.toLowerCase().includes('iracing') ? 'iRacing' : 
                                 message.toLowerCase().includes('obs') ? 'OBS' : 'Connection';
                action = eventType === 'connection_lost' ? `${{component}} Connection Lost` : `${{component}} Connection Restored`;
            }} else if (eventType === 'game_started') {{
                action = `Game Mode ${{(data && data.mode ? data.mode : 'Unknown')}} Activated`;
            }} else if (eventType === 'scene_switch') {{
                action = 'Scene Switch Activated';
            }} else if (eventType === 'override_applied') {{
                action = `Override Activated (${{(data && data.seconds ? data.seconds : '?')}}s)`;
            }} else if (eventType === 'autoswitch_toggled') {{
                action = `Autoswitch ${{(data && data.autoswitch ? 'Enabled' : 'Disabled')}}`;
            }} else if (eventType === 'stream_title_detected') {{
                action = `Stream Title: ${{(data && data.stream_title ? data.stream_title : 'Unknown')}}`;
            }} else if (eventType === 'stream_selected') {{
                action = 'Stream Selected Activated';
            }} else if (eventType === 'stream_deselected') {{
                action = 'Stream Deselected Activated';
            }} else {{
                action = info.title + (eventType.includes('started') ? ' Activated' : eventType.includes('stopped') ? ' Activated' : '');
            }}
            if (action) parts.push(action);
            
            // Scene part
            if (data && data.scene) {{
                parts.push(`Scene ${{data.scene}}`);
            }}
            
            const toastMessage = parts.join(' | ') || message;
            
            return {{ type: info.type, title: info.title, message: toastMessage }};
        }}
        
        async function updateEvents() {{
            try {{
                const response = await fetch(`${{API_BASE}}/api/events?count=${{config.dashboard_event_log_size}}`);
                if (!response.ok) {{
                    console.error('Failed to fetch events:', response.status);
                    return;
                }}
                const data = await response.json();
                if (data && data.events && Array.isArray(data.events)) {{
                    // Detect new events
                    const newEvents = data.events.filter(e => e.timestamp > lastEventTimestamp);
                    
                    // Collect timestamps of new events for highlighting
                    const newEventTimestamps = new Set(newEvents.map(e => e.timestamp));
                    
                    // Show toast alerts for new events
                    newEvents.forEach(event => {{
                        const toastInfo = getToastInfo(event.type, event.message, event.data);
                        showToast(toastInfo.title, toastInfo.message, toastInfo.type);
                    }});
                    
                    // Update last event timestamp
                    if (data.events.length > 0) {{
                        lastEventTimestamp = Math.max(...data.events.map(e => e.timestamp));
                    }}
                    
                    // Only update if events actually changed
                    const eventsJson = JSON.stringify(events);
                    const newEventsJson = JSON.stringify(data.events);
                    if (eventsJson !== newEventsJson) {{
                        events = data.events;
                        // Render with highlighting for new events
                        renderEvents(newEventTimestamps);
                    }}
                }}
            }} catch (error) {{
                console.error('Failed to update events:', error);
            }}
        }}
        
        function updateConnectionStatus(type, connected) {{
            // Update connection status indicators
            const indicators = document.querySelectorAll('.status-indicator');
            indicators.forEach(indicator => {{
                const title = indicator.getAttribute('title');
                if ((type === 'iracing' && title === 'iRacing') || (type === 'obs' && title === 'OBS')) {{
                    if (connected) {{
                        indicator.classList.remove('disconnected');
                    }} else {{
                        indicator.classList.add('disconnected');
                    }}
                }}
            }});
            
            // Also update VR dashboard diodes if present
            const iracingDiode = document.getElementById('iracing-diode');
            const obsDiode = document.getElementById('obs-diode');
            if (type === 'iracing' && iracingDiode) {{
                if (connected) {{
                    iracingDiode.classList.remove('disconnected');
                }} else {{
                    iracingDiode.classList.add('disconnected');
                }}
            }}
            if (type === 'obs' && obsDiode) {{
                if (connected) {{
                    obsDiode.classList.remove('disconnected');
                }} else {{
                    obsDiode.classList.add('disconnected');
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
        
        // Toast notification functions
        function showToast(title, message, type = 'info') {{
            const container = document.getElementById('toast-container');
            if (!container) return;
            
            const toast = document.createElement('div');
            toast.className = `toast ${{type}}`;
            toast.innerHTML = `
                <div class="toast-title">${{title}}</div>
                <div class="toast-message">${{message}}</div>
            `;
            
            container.appendChild(toast);
            
            // Highlight toast for 3 seconds, then fade out
            setTimeout(() => {{
                toast.style.opacity = '0.7';
                toast.style.transition = 'opacity 0.5s ease-out';
            }}, 3000);
            
            // Auto-remove after 5 seconds
            setTimeout(() => {{
                toast.classList.add('hiding');
                setTimeout(() => {{
                    if (toast.parentNode) {{
                        toast.parentNode.removeChild(toast);
                    }}
                }}, 300);
            }}, 5000);
        }}
        
        function showConfirm(title, message, confirmText = 'Confirm', cancelText = 'Cancel', danger = false) {{
            return new Promise((resolve) => {{
                const container = document.getElementById('confirm-overlay-container');
                if (!container) {{
                    resolve(false);
                    return;
                }}
                
                const overlay = document.createElement('div');
                overlay.className = 'confirm-overlay';
                overlay.innerHTML = `
                    <div class="confirm-dialog">
                        <h3>${{title}}</h3>
                        <p>${{message}}</p>
                        <div class="confirm-buttons">
                            <button class="confirm-button" data-action="cancel">${{cancelText}}</button>
                            <button class="confirm-button ${{danger ? 'danger' : 'primary'}}" data-action="confirm">${{confirmText}}</button>
                        </div>
                    </div>
                `;
                
                container.appendChild(overlay);
                
                const closeDialog = (confirmed) => {{
                    overlay.classList.add('hiding');
                    setTimeout(() => {{
                        if (overlay.parentNode) {{
                            overlay.parentNode.removeChild(overlay);
                        }}
                        resolve(confirmed);
                    }}, 200);
                }};
                
                // Handle button clicks
                overlay.querySelectorAll('.confirm-button').forEach(btn => {{
                    btn.addEventListener('click', (e) => {{
                        e.stopPropagation();
                        const action = btn.getAttribute('data-action');
                        if (action === 'confirm') {{
                            closeDialog(true);
                        }} else if (action === 'cancel') {{
                            closeDialog(false);
                        }}
                    }});
                }});
                
                // Handle overlay click (outside dialog)
                overlay.addEventListener('click', (e) => {{
                    if (e.target === overlay) {{
                        closeDialog(false);
                    }}
                }});
                
                // Handle Escape key
                const handleEscape = (e) => {{
                    if (e.key === 'Escape') {{
                        closeDialog(false);
                        document.removeEventListener('keydown', handleEscape);
                    }}
                }};
                document.addEventListener('keydown', handleEscape);
            }});
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
        
        function formatReloadKeys(keys) {{
            if (!keys || keys.length === 0) {{
                return '(none)';
            }}
            return keys.join(', ');
        }}

        function updateConfigReloadPanel(appliedLive, needsRestart) {{
            const panel = document.getElementById('config-reload-panel');
            if (!panel) return;

            const live = Array.isArray(appliedLive) ? appliedLive : [];
            const restart = Array.isArray(needsRestart) ? needsRestart : [];
            panel.classList.add('visible');
            panel.classList.toggle('needs-restart', restart.length > 0);
            panel.innerHTML = `
                <h4>Config reload result</h4>
                <div class="reload-section">
                    <strong>Applied live:</strong>
                    <div class="reload-keys">${{formatReloadKeys(live)}}</div>
                </div>
                <div class="reload-section">
                    <strong>Needs restart:</strong>
                    <div class="reload-keys">${{formatReloadKeys(restart)}}</div>
                </div>
            `;
        }}

        async function reloadConfig() {{
            try {{
                const response = await fetch(`${{API_BASE}}/config/reload`, {{ method: 'POST' }});
                const data = await response.json();
                
                if (response.ok) {{
                    const live = data.applied_live || [];
                    const restart = data.needs_restart || [];
                    updateConfigReloadPanel(live, restart);
                    if (restart.length > 0) {{
                        showToast(
                            'Config Reloaded — Restart Needed',
                            `Restart for: ${{formatReloadKeys(restart)}}`,
                            'warning'
                        );
                    }} else if (live.length > 0) {{
                        showToast(
                            'Config Reloaded',
                            `Applied live: ${{formatReloadKeys(live)}}`,
                            'success'
                        );
                    }} else {{
                        showToast('Config Reloaded', 'No tracked keys changed', 'success');
                    }}
                }} else {{
                    showToast('Config Reload Failed', data.error || 'Unknown error', 'error');
                }}
            }} catch (error) {{
                console.error('Failed to reload config:', error);
                showToast('Config Reload Failed', error.message || 'Network error', 'error');
            }}
        }}
        
        async function reinitStream() {{
            try {{
                const response = await fetch(`${{API_BASE}}/stream/reinit`, {{ method: 'POST' }});
                const data = await response.json();
                
                if (response.ok) {{
                    const title = data.stream_title || t('not_available');
                    showToast(t('reinit_stream'), `${{t('stream_title')}}: ${{title}}`, 'success');
                    await updateStatus();
                    await updateEvents();
                }} else {{
                    showToast(t('reinit_stream'), data.error || data.message || 'Unknown error', 'error');
                }}
            }} catch (error) {{
                console.error('Failed to reinit stream:', error);
                showToast(t('reinit_stream'), error.message || 'Network error', 'error');
            }}
        }}
        
        async function initiateOAuth() {{
            try {{
                const response = await fetch(`${{API_BASE}}/oauth/initiate`);
                const data = await response.json();
                
                if (response.ok && data.authorization_url) {{
                    // Open authorization URL in new window
                    window.open(data.authorization_url, '_blank');
                    showToast('OAuth Authorization', 'Authorization page opened in new window. Complete the authorization and the page will redirect automatically.', 'info');
                    
                    // Poll for OAuth status update after authorization
                    let pollCount = 0;
                    const maxPolls = 60; // 60 polls = 30 seconds (poll every 500ms)
                    const pollInterval = setInterval(async () => {{
                        pollCount++;
                        
                        try {{
                            // Force status update to check OAuth status
                            await updateStatus();
                            
                            // Check if OAuth is now authenticated
                            const statusResponse = await fetch(`${{API_BASE}}/oauth/status`);
                            const statusData = await statusResponse.json();
                            
                            if (statusData.authenticated) {{
                                clearInterval(pollInterval);
                                showToast('OAuth Authorized', 'YouTube API authorization completed successfully!', 'success');
                                // Force full status refresh
                                await updateStatus();
                            }} else if (pollCount >= maxPolls) {{
                                clearInterval(pollInterval);
                                showToast('OAuth Timeout', 'Authorization check timed out. Please refresh the page if authorization completed.', 'warning');
                            }}
                        }} catch (error) {{
                            console.error('OAuth poll error:', error);
                            if (pollCount >= maxPolls) {{
                                clearInterval(pollInterval);
                            }}
                        }}
                    }}, 500); // Poll every 500ms
                }} else {{
                    showToast('OAuth Initiation Failed', data.error || data.message || 'Unknown error', 'error');
                }}
            }} catch (error) {{
                console.error('Failed to initiate OAuth:', error);
                showToast('OAuth Initiation Failed', error.message || 'Network error', 'error');
            }}
        }}
        
        async function resetService() {{
            try {{
                const confirmed = await showConfirm(
                    'Reset Service',
                    'This will reset state to CONNECTING, clear metrics, and set safe scene. Continue?',
                    'Reset',
                    'Cancel',
                    false
                );
                if (!confirmed) {{
                    return;
                }}
                
                const response = await fetch(`${{API_BASE}}/reset`, {{ method: 'POST' }});
                const data = await response.json();
                
                if (response.ok) {{
                    showToast('Service Reset', 'State and metrics reset to CONNECTING', 'success');
                    await updateStatus();
                    await updateMetrics();
                    await updateEvents();
                }} else {{
                    showToast('Reset Failed', data.error || 'Unknown error', 'error');
                }}
            }} catch (error) {{
                console.error('Failed to reset service:', error);
                showToast('Reset Failed', error.message || 'Network error', 'error');
            }}
        }}
        
        async function restartService() {{
            const confirmed = await showConfirm(
                t('restart_service'),
                t('restart_service_confirm'),
                t('restart'),
                t('cancel'),
                true
            );
            if (!confirmed) {{
                return;
            }}
            try {{
                const response = await fetch(`${{API_BASE}}/restart`, {{ method: 'POST' }});
                const data = await response.json();
                
                if (response.ok) {{
                    showToast(t('restart_initiated'), t('restart_initiated_detail'), 'warning');
                }} else {{
                    showToast(t('restart_failed'), data.error || 'Unknown error', 'error');
                }}
            }} catch (error) {{
                console.error('Failed to restart service:', error);
                showToast(t('restart_failed'), error.message || 'Network error', 'error');
            }}
        }}
        
        async function shutdownService() {{
            const confirmed = await showConfirm(
                'Shutdown Service',
                'Are you sure you want to shutdown the service? This will stop the iRacing OBS Switcher.',
                'Shutdown',
                'Cancel',
                true
            );
            if (!confirmed) {{
                return;
            }}
            try {{
                const response = await fetch(`${{API_BASE}}/shutdown`, {{ method: 'POST' }});
                const data = await response.json();
                
                if (response.ok) {{
                    showToast('Shutdown Initiated', 'The service will stop shortly', 'warning');
                }} else {{
                    showToast('Shutdown Failed', data.error || 'Unknown error', 'error');
                }}
            }} catch (error) {{
                console.error('Failed to shutdown service:', error);
                showToast('Shutdown Failed', error.message || 'Network error', 'error');
            }}
        }}
        
        async function updateMetrics() {{
            try {{
                const response = await fetch(`${{API_BASE}}/metrics`);
                const data = await response.json();
                
                // Update metrics
                updateValue(t('scene_switches'), data.scene_switches_total || 0);
                const latency = data.scene_switch_latency_avg_ms;
                updateValue(t('avg_latency'), latency !== null && latency !== undefined ? latency.toFixed(4) + ' ms' : t('n_a'));
                updateValue(t('uptime'), formatDuration(data.uptime_seconds));
                
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

                const errors = data.errors_total || {{}};
                const errorsEl = document.getElementById('metrics-errors');
                const errorsBreakdownEl = document.getElementById('metrics-errors-breakdown');
                if (errorsEl) {{
                    const total = Object.values(errors).reduce((sum, n) => sum + (Number(n) || 0), 0);
                    errorsEl.textContent = total;
                }}
                if (errorsBreakdownEl) {{
                    const parts = Object.entries(errors)
                        .filter(([, n]) => (Number(n) || 0) > 0)
                        .sort((a, b) => (Number(b[1]) - Number(a[1])) || a[0].localeCompare(b[0]))
                        .map(([key, n]) => key + ': ' + n);
                    errorsBreakdownEl.textContent = parts.length ? parts.join(' · ') : t('n_a');
                }}
            }} catch (error) {{
                console.error('Failed to update metrics:', error);
            }}
        }}
        
        // Initial render (no new events on initial load)
        renderEvents(new Set());
        
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
        response.headers["Cache-Control"] = (
            "no-cache, no-store, must-revalidate, max-age=0, private"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Accel-Expires"] = "0"  # For nginx proxy
        response.headers["Last-Modified"] = time.strftime(
            "%a, %d %b %Y %H:%M:%S GMT", time.gmtime()
        )
        response.headers["ETag"] = f'"{cache_bust}"'  # Unique ETag for each request
        return response
    except Exception as e:
        logger.error(f"Error in handle_gr_status: {e}", exc_info=True)
        return web.Response(text=f"Internal server error: {e}", status=500)


async def handle_vr_status(request: web.Request) -> web.Response:
    """
    Handle GET /vr-status - VR widget.

    Note: RaceLab VR widgety se načítají jen při startu a neaktualizují se automaticky.
    Pokud RaceLab VR nepodporuje refresh interval, widget se neaktualizuje.

    Možná řešení:
    1. Nastav refresh interval v RaceLab VR widget nastavení
    2. Použij externí nástroj pro periodický refresh
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
    stream_duration_ms: int | None = None
    obs_client = _get_obs_client()
    if obs_client is not None and state.connected_obs:
        try:
            is_streaming, stream_duration_ms = await obs_client.get_stream_status()
        except Exception:
            pass

    config: AppConfig | None = request.app.get(APP_CONFIG)
    update_interval_ms = int(1000 / (config.dashboard_update_fps if config else 2))
    refresh_seconds = max(1, update_interval_ms // 1000)  # Convert to seconds, minimum 1 second

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
        const API_BASE = window.location.origin;
        const UPDATE_INTERVAL = {update_interval_ms};
        
        async function updateStatus() {{
            try {{
                const response = await fetch(`${{API_BASE}}/status`);
                if (!response.ok) return;
                const data = await response.json();
                
                // Update connection statuses
                const obsDiode = document.getElementById('obs-diode');
                const iracingDiode = document.getElementById('iracing-diode');
                if (obsDiode) {{
                    if (data.connected_obs) {{
                        obsDiode.classList.remove('disconnected');
                    }} else {{
                        obsDiode.classList.add('disconnected');
                    }}
                }}
                if (iracingDiode) {{
                    if (data.connected_iracing) {{
                        iracingDiode.classList.remove('disconnected');
                    }} else {{
                        iracingDiode.classList.add('disconnected');
                    }}
                }}
                
                // Update scene
                const sceneName = document.getElementById('scene-name');
                if (sceneName && data.current_scene) {{
                    sceneName.textContent = data.current_scene;
                }}
                
                // Update streaming
                const recDot = document.getElementById('rec-dot');
                const streamDuration = document.getElementById('stream-duration');
                if (recDot) {{
                    if (data.streaming) {{
                        recDot.style.background = '#f44336';
                        recDot.style.animation = 'pulse 2s infinite';
                    }} else {{
                        recDot.style.background = '#666';
                        recDot.style.animation = 'none';
                    }}
                }}
                if (streamDuration && data.stream_duration_ms !== null && data.stream_duration_ms !== undefined) {{
                    const totalSeconds = Math.floor(data.stream_duration_ms / 1000);
                    const hours = Math.floor(totalSeconds / 3600);
                    const minutes = Math.floor((totalSeconds % 3600) / 60);
                    const seconds = totalSeconds % 60;
                    if (hours > 0) {{
                        streamDuration.textContent = `${{hours.toString().padStart(2, '0')}}:${{minutes.toString().padStart(2, '0')}}:${{seconds.toString().padStart(2, '0')}}`;
                    }} else {{
                        streamDuration.textContent = `${{minutes.toString().padStart(2, '0')}}:${{seconds.toString().padStart(2, '0')}}`;
                    }}
                }}
            }} catch (error) {{
                console.error('Failed to update VR status:', error);
            }}
        }}
        
        // Initial update
        updateStatus();
        
        // Auto-update
        setInterval(updateStatus, UPDATE_INTERVAL);
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
