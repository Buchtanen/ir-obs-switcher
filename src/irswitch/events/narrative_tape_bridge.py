"""#284 NarrativeRuntime owned tape flush effect bridge.

Wraps ``commentary.tape_writer.NarrativeTapeWriter.aclose`` as an EffectWorker
so shutdown can flush/close the writer under actor ownership. Not exported from
``events/__init__.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from irswitch.commentary.tape_writer import CLOSE_REASONS, NarrativeTapeWriter
from irswitch.contracts.command import NarrativeCommand

EffectWorker = Callable[
    [dict[str, Any]],
    Awaitable[NarrativeCommand | Sequence[NarrativeCommand] | None],
]

_HASH = "sha256:" + ("1" * 64)


def default_narrative_tape_manifest(
    *,
    process_instance_id: str = "process:race",
    broadcast_epoch: int = 0,
    stream_epoch: int = 0,
    file_ordinal: int = 0,
    app_version: str = "0.0.0",
) -> dict[str, Any]:
    """Minimal valid narrative-tape-manifest/2 for race-owned writers."""

    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schemaVersion": "narrative-tape-manifest/2",
        "recordType": "manifest",
        "processInstanceId": process_instance_id,
        "processStartedAtUtc": now,
        "processMonotonicOriginMs": 0,
        "appVersion": str(app_version),
        "gitRevision": "unknown",
        "platform": "linux",
        "broadcastEpoch": int(broadcast_epoch),
        "streamEpoch": int(stream_epoch),
        "fileOrdinal": int(file_ordinal),
        "openedAtUtc": now,
        "catalogVersion": "narrative-catalog:2",
        "catalogHash": _HASH,
        "desiredConfigGeneration": 0,
        "desiredConfigHash": _HASH,
        "effectiveConfigHash": _HASH,
        "configApplySequence": 0,
        "effectiveConfigProjection": [],
        "enabledPurposeChannels": ["flow"],
        "redactionPolicy": {
            "sensitiveValues": "marker_only",
            "prompt": "hash",
            "completion": True,
        },
        "historyComplete": True,
        "detectorParameterSnapshots": [],
        "previousFileHash": None,
    }


def open_narrative_tape_writer(
    output_dir: Path | str,
    *,
    manifest: dict[str, Any] | None = None,
    shutdown_flush_timeout_s: float = 2.0,
    flush_interval_ms: int = 500,
    app_version: str = "0.0.0",
) -> NarrativeTapeWriter:
    """Create a race-owned NarrativeTapeWriter (not started; call ``start()`` under a loop)."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    payload = (
        dict(manifest)
        if manifest is not None
        else default_narrative_tape_manifest(app_version=app_version)
    )
    return NarrativeTapeWriter(
        directory,
        payload,
        flush_interval_ms=int(flush_interval_ms),
        shutdown_flush_timeout_s=float(shutdown_flush_timeout_s),
    )


def build_tape_flush_effect(writer: NarrativeTapeWriter) -> EffectWorker:
    """Return an effect that fail-soft closes ``writer`` on shutdown flush."""

    async def tape_flush(token: dict[str, Any]) -> NarrativeCommand | None:
        reason = str(token.get("reason") or "shutdown")
        try:
            await writer.aclose(reason if reason in CLOSE_REASONS else "shutdown")
        except Exception:
            # Fail-soft: runtime timeout path reports degraded health separately.
            return None
        return None

    return tape_flush
