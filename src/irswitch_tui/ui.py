"""Textual UI layout."""
from __future__ import annotations

import asyncio
from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Label, Static

from irswitch_tui.client import AsyncClient


class StatusPanel(Static):
    """Panel displaying current status."""

    def __init__(self, client: AsyncClient) -> None:
        super().__init__()
        self.client = client

    def compose(self) -> ComposeResult:
        """Compose status panel."""
        with Vertical():
            yield Label("Status", classes="section-title")
            yield Label("iRacing: --", id="iracing-status")
            yield Label("OBS: --", id="obs-status")
            yield Label("Mode: --", id="mode")
            yield Label("Current Scene: --", id="current-scene")
            yield Label("Target Scene: --", id="target-scene")
            yield Label("Autoswitch: --", id="autoswitch")
            yield Label("Reason: --", id="reason")
            yield Label("Streaming: --", id="streaming")

    def update_status(self, status: dict) -> None:
        """Update status display."""
        iracing_connected = status.get('connected_iracing', False)
        obs_connected = status.get('connected_obs', False)
        
        iracing_label = self.query_one("#iracing-status")
        iracing_label.update(
            f"iRacing: {'Connected' if iracing_connected else 'Disconnected'}"
        )
        iracing_label.set_class(iracing_connected, "connected")
        iracing_label.set_class(not iracing_connected, "disconnected")
        
        obs_label = self.query_one("#obs-status")
        obs_label.update(
            f"OBS: {'Connected' if obs_connected else 'Disconnected'}"
        )
        obs_label.set_class(obs_connected, "connected")
        obs_label.set_class(not obs_connected, "disconnected")
        self.query_one("#mode").update(f"Mode: {status.get('mode', '--')}")
        self.query_one("#current-scene").update(
            f"Current Scene: {status.get('current_scene', '--')}"
        )
        self.query_one("#target-scene").update(
            f"Target Scene: {status.get('target_scene', '--')}"
        )
        self.query_one("#autoswitch").update(
            f"Autoswitch: {'ON' if status.get('autoswitch') else 'OFF'}"
        )
        self.query_one("#reason").update(f"Reason: {status.get('reason', '--')}")
        
        # Streaming status
        streaming = status.get('streaming', False)
        stream_duration_ms = status.get('stream_duration_ms')
        if streaming and stream_duration_ms:
            duration_sec = stream_duration_ms // 1000
            duration_min = duration_sec // 60
            duration_sec = duration_sec % 60
            stream_text = f"Streaming: Yes ({duration_min:02d}:{duration_sec:02d})"
        elif streaming:
            stream_text = "Streaming: Yes"
        else:
            stream_text = "Streaming: No"
        self.query_one("#streaming").update(stream_text)


class ControlPanel(Static):
    """Panel with control buttons."""

    def __init__(self, client: AsyncClient) -> None:
        super().__init__()
        self.client = client
        self._current_status: Optional[dict] = None

    def compose(self) -> ComposeResult:
        """Compose control panel."""
        with Vertical():
            yield Label("Controls", classes="section-title")
            yield Button("Toggle Autoswitch", id="toggle-autoswitch")
            yield Button("Override: Race", id="override-race")
            yield Button("Override: Pits", id="override-pits")
            yield Button("Override: Safe", id="override-safe")

    def update_status(self, status: dict) -> None:
        """Update status to use for scene overrides."""
        self._current_status = status

    @on(Button.Pressed, "#toggle-autoswitch")
    async def on_toggle_autoswitch(self) -> None:
        """Handle toggle autoswitch button."""
        try:
            await self.client.toggle_autoswitch()
        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")

    @on(Button.Pressed, "#override-race")
    async def on_override_race(self) -> None:
        """Handle override race button."""
        try:
            await self.client.override_scene("Race", 120)
        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")

    @on(Button.Pressed, "#override-pits")
    async def on_override_pits(self) -> None:
        """Handle override pits button."""
        try:
            await self.client.override_scene("Pits", 120)
        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")

    @on(Button.Pressed, "#override-safe")
    async def on_override_safe(self) -> None:
        """Handle override safe scene button (uses target_scene from status)."""
        try:
            # Use target_scene from status, which should be the safe scene when in IDLE mode
            # Fallback to current_scene if target_scene is not available
            if self._current_status:
                scene = self._current_status.get("target_scene") or self._current_status.get("current_scene")
                if scene:
                    await self.client.override_scene(scene, 120)
                else:
                    self.app.notify("No scene available from status", severity="error")
            else:
                self.app.notify("Status not available", severity="error")
        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")


class SwitcherTUI(App):
    """Main TUI application."""

    CSS = """
    .section-title {
        text-style: bold;
        margin: 1;
    }
    StatusPanel, ControlPanel {
        border: solid $primary;
        padding: 1;
        margin: 1;
    }
    #iracing-status.connected {
        color: $success;
    }
    #iracing-status.disconnected {
        color: $error;
    }
    #obs-status.connected {
        color: $success;
    }
    #obs-status.disconnected {
        color: $error;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "toggle_autoswitch", "Toggle Autoswitch"),
    ]

    def __init__(self, client: AsyncClient) -> None:
        super().__init__()
        self.client = client
        self._update_task: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()
        with Container():
            with Horizontal():
                yield StatusPanel(self.client)
                yield ControlPanel(self.client)
        yield Footer()

    async def on_mount(self) -> None:
        """Called when app is mounted."""
        # Set up status callback
        self.client.set_status_callback(self.on_status_update)

        # Connect to service
        try:
            await self.client.connect()
            # Initial status fetch
            status = await self.client.get_status()
            self.on_status_update(status)
        except Exception as e:
            self.notify(f"Failed to connect: {e}", severity="error")
            self.exit(1)

    def on_status_update(self, status: dict) -> None:
        """Handle status update from WebSocket."""
        status_panel = self.query_one(StatusPanel)
        status_panel.update_status(status)
        
        # Update control panel with status for scene overrides
        control_panel = self.query_one(ControlPanel)
        control_panel.update_status(status)
        
        # Show notification for connection changes
        iracing_connected = status.get('connected_iracing', False)
        obs_connected = status.get('connected_obs', False)
        
        # Store previous state to detect changes
        if not hasattr(self, '_prev_iracing'):
            self._prev_iracing = iracing_connected
            self._prev_obs = obs_connected
            return
        
        # Notify on connection changes
        if iracing_connected != self._prev_iracing:
            if iracing_connected:
                self.notify("iRacing connected", severity="success")
            else:
                self.notify("iRacing disconnected", severity="error")
            self._prev_iracing = iracing_connected
        
        if obs_connected != self._prev_obs:
            if obs_connected:
                self.notify("OBS connected", severity="success")
            else:
                self.notify("OBS disconnected", severity="error")
            self._prev_obs = obs_connected

    async def action_toggle_autoswitch(self) -> None:
        """Action to toggle autoswitch."""
        try:
            await self.client.toggle_autoswitch()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    async def on_unmount(self) -> None:
        """Called when app is unmounted."""
        await self.client.disconnect()
