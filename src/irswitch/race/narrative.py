"""Stream-level SESSION_WRAP / SESSION_PREVIEW at session boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.overlay.models import RaceState
from irswitch.race.watcher_log import WatcherLog, note

_WRAP_PRIORITY = 58
_PREVIEW_PRIORITY = 52


def _mode_label(mode: str) -> str:
    return {
        "PRACTICE": "Practice",
        "QUALIFYING": "Qualifying",
        "RACE": "Race",
        "GENERIC": "Session",
    }.get(mode, "Session")


def _mode_label_cs(mode: str) -> str:
    return {
        "PRACTICE": "trénink",
        "QUALIFYING": "kvalifikace",
        "RACE": "závod",
        "GENERIC": "session",
    }.get(mode, "session")


@dataclass
class StreamNarrativeFsm:
    """Emit wrap/preview once per session boundary for stream commentary.

    Sequencing intent (with ``session_briefs`` sidecars):
    * key change → ``SESSION_WRAP`` (previous) then ``SESSION_PREVIEW`` (new)
      when the stream already had a prior session
    * ``player_finished`` / ``session_finished`` rising edge → ``SESSION_WRAP`` if not yet wrapped
    * first session of a stream gets neither wrap nor preview (intros own the opener)
    """

    _key: str | None = None
    _mode: str = "GENERIC"
    _position: int | None = None
    _p1: str | None = None
    _p2: str | None = None
    _p3: str | None = None
    _finished: bool = False
    _wrapped_keys: set[str] = field(default_factory=set)
    _previewed_keys: set[str] = field(default_factory=set)
    _had_prior_session: bool = False
    _pending: list[EventEnvelope] = field(default_factory=list)

    def reset_session(self) -> None:
        """Drop active key tracking; keep wrap/preview history for the stream."""
        self._key = None
        self._mode = "GENERIC"
        self._position = None
        self._p1 = None
        self._p2 = None
        self._p3 = None
        self._finished = False

    def reset_stream(self) -> None:
        self.reset_session()
        self._wrapped_keys.clear()
        self._previewed_keys.clear()
        self._had_prior_session = False
        self._pending.clear()

    def take_pending(self) -> list[EventEnvelope]:
        out = list(self._pending)
        self._pending.clear()
        return out

    def tick(
        self,
        state: RaceState,
        now: float,
        *,
        session_key: str | None,
        log: WatcherLog | None = None,
    ) -> list[EventEnvelope]:
        produced: list[EventEnvelope] = []
        if not state.connected:
            # Disconnect is not a clean wrap; keep history for reconnect same key.
            return produced

        mode = state.overlay_mode or "GENERIC"
        position = state.class_position or state.position
        finished = bool(state.player_finished or state.session_finished)

        if session_key and session_key != self._key:
            if self._key is not None and self._key not in self._wrapped_keys:
                produced.append(
                    self._wrap_envelope(
                        now,
                        key=self._key,
                        mode=self._mode,
                        position=self._position,
                        reason="session_change",
                        p1=self._p1,
                        p2=self._p2,
                        p3=self._p3,
                    )
                )
                self._wrapped_keys.add(self._key)
                self._had_prior_session = True
            prev_had = self._had_prior_session or bool(self._wrapped_keys)
            self._key = session_key
            self._mode = mode
            self._position = position
            self._p1 = state.p1_name
            self._p2 = state.p2_name
            self._p3 = state.p3_name
            self._finished = finished
            if prev_had and session_key not in self._previewed_keys:
                produced.append(
                    self._preview_envelope(
                        now,
                        key=session_key,
                        mode=mode,
                        position=position,
                    )
                )
                self._previewed_keys.add(session_key)
                self._had_prior_session = True
            if produced:
                self._pending.extend(produced)
                self._note_emits(produced, log, now)
            self._bound_history()
            return produced

        if session_key is None:
            return produced

        self._mode = mode
        self._position = position
        self._p1 = state.p1_name
        self._p2 = state.p2_name
        self._p3 = state.p3_name

        if finished and not self._finished and session_key not in self._wrapped_keys:
            produced.append(
                self._wrap_envelope(
                    now,
                    key=session_key,
                    mode=mode,
                    position=position,
                    reason="session_finished",
                    p1=state.p1_name,
                    p2=state.p2_name,
                    p3=state.p3_name,
                )
            )
            self._wrapped_keys.add(session_key)
            self._had_prior_session = True
        self._finished = finished

        if produced:
            self._pending.extend(produced)
            self._note_emits(produced, log, now)
        self._bound_history()
        return produced

    def _note_emits(
        self,
        produced: list[EventEnvelope],
        log: WatcherLog | None,
        now: float,
    ) -> None:
        for env in produced:
            metrics = env.metrics or {}
            reason = str(metrics.get("reason") or metrics.get("kind") or "emit")
            note(
                log,
                watch="briefs",
                kind=env.event_type,
                emitted=True,
                reason=reason,
                confidence=1.0,
                now=now,
            )

    def _bound_history(self) -> None:
        for bag in (self._wrapped_keys, self._previewed_keys):
            while len(bag) > 16:
                bag.pop()

    def _wrap_envelope(
        self,
        now: float,
        *,
        key: str,
        mode: str,
        position: int | None,
        reason: str,
        p1: str | None = None,
        p2: str | None = None,
        p3: str | None = None,
    ) -> EventEnvelope:
        metrics: dict[str, object] = {
            "kind": "session_wrap",
            "mode": mode,
            "modeLabel": _mode_label(mode),
            "modeLabelCs": _mode_label_cs(mode),
            "reason": reason,
            "sessionCount": len(self._wrapped_keys) + 1,
        }
        if position is not None:
            metrics["position"] = position
        if p1:
            metrics["p1Name"] = p1
        if p2:
            metrics["p2Name"] = p2
        if p3:
            metrics["p3Name"] = p3
        return make_envelope(
            event_type="SESSION_WRAP",
            phase="RESULT",
            mode=mode,
            priority=_WRAP_PRIORITY,
            monotonic_ms=int(now * 1000),
            metrics=metrics,
            correlation_id=f"stream_wrap:{key}",
            dedupe_key=f"SESSION_WRAP:{key}",
        )

    def _preview_envelope(
        self,
        now: float,
        *,
        key: str,
        mode: str,
        position: int | None,
    ) -> EventEnvelope:
        metrics: dict[str, object] = {
            "kind": "session_preview",
            "mode": mode,
            "modeLabel": _mode_label(mode),
            "modeLabelCs": _mode_label_cs(mode),
        }
        if position is not None:
            metrics["position"] = position
        return make_envelope(
            event_type="SESSION_PREVIEW",
            phase="RESULT",
            mode=mode,
            priority=_PREVIEW_PRIORITY,
            monotonic_ms=int(now * 1000),
            metrics=metrics,
            correlation_id=f"stream_preview:{key}",
            dedupe_key=f"SESSION_PREVIEW:{key}",
        )
