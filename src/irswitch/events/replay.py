"""Deterministic JSONL capture/replay for the immutable N12 stream."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, BinaryIO

from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.stream import (
    ConfigUpdate,
    FrozenAcceptedEvent,
    FrozenAcceptedEventBatch,
    SessionReset,
    StreamContractError,
    StreamItem,
    canonical_json_bytes,
    freeze_config,
    freeze_context,
    thaw_config,
    thaw_context,
)

REPLAY_SCHEMA_VERSION = "n12-replay/1"


class N12ReplayWriter:
    """Append canonical rows; contexts precede the first referencing batch."""

    def __init__(
        self,
        path: Path,
        *,
        source_commit: str,
        config_generation: int,
        config_digest: str,
        locale: str,
        monotonic_origin_ms: int | None = None,
    ) -> None:
        self.path = path
        self.origin_ms = (
            int(time.monotonic() * 1000) if monotonic_origin_ms is None else monotonic_origin_ms
        )
        self._seen_contexts: set[tuple[str, int]] = set()
        self._file: BinaryIO = path.open("wb")
        self._write(
            {
                "row": "header",
                "schema": REPLAY_SCHEMA_VERSION,
                "source_commit": source_commit,
                "config_generation": config_generation,
                "config_digest": config_digest,
                "locale": locale,
                "monotonic_origin_ms": self.origin_ms,
            }
        )

    def record(self, item: StreamItem) -> None:
        if isinstance(item, FrozenAcceptedEventBatch):
            key = (item.session_id, item.context_version)
            if key not in self._seen_contexts:
                context = thaw_context(item.context_payload)
                self._write(
                    {
                        "row": "context",
                        "session_id": item.session_id,
                        "context_version": item.context_version,
                        "captured_monotonic_offset_ms": int(context["captured_monotonic_ms"])
                        - self.origin_ms,
                        "payload": context,
                    }
                )
                self._seen_contexts.add(key)
            self._write(
                {
                    "row": "events",
                    "stream_sequence": item.stream_sequence,
                    "session_id": item.session_id,
                    "batch_sequence": item.batch_sequence,
                    "accepted_monotonic_offset_ms": item.accepted_monotonic_ms - self.origin_ms,
                    "context_version": item.context_version,
                    "events": [_event_to_row(event) for event in item.events],
                }
            )
            return
        payload: dict[str, Any]
        if isinstance(item, SessionReset):
            payload = {
                "kind": "SessionReset",
                "old_session_id": item.old_session_id,
                "new_session_id": item.new_session_id,
                "reason": item.reason,
            }
        else:
            payload = {
                "kind": "ConfigUpdate",
                "generation": item.generation,
                "config": thaw_config(item.frozen_config),
            }
        self._write(
            {
                "row": "control",
                "stream_sequence": item.stream_sequence,
                "payload": payload,
            }
        )

    def record_expected(
        self,
        *,
        overlay_wire_ids: list[str],
        commentary_decision_ids: list[str],
        commentary_speech_ids: list[str],
    ) -> None:
        self._write(
            {
                "row": "expected",
                "overlay_wire_ids": overlay_wire_ids,
                "commentary_decision_ids": commentary_decision_ids,
                "commentary_speech_ids": commentary_speech_ids,
            }
        )

    def close(self) -> None:
        if not self._file.closed:
            self._file.flush()
            self._file.close()

    def __enter__(self) -> N12ReplayWriter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _write(self, row: dict[str, Any]) -> None:
        self._file.write(canonical_json_bytes(row) + b"\n")
        self._file.flush()


class N12ReplayBundle:
    def __init__(self, rows: tuple[dict[str, Any], ...]) -> None:
        self.rows = rows
        self.header = rows[0]
        self.expected = tuple(row for row in rows if row.get("row") == "expected")

    async def replay(self, fanout: AsyncEventFanout, *, realtime: bool = False) -> None:
        replay_origin = int(time.monotonic() * 1000)
        contexts: dict[tuple[str, int], tuple[dict[str, Any], int]] = {}
        previous_offset = 0
        for row in self.rows[1:]:
            kind = row.get("row")
            if kind == "context":
                key = (str(row["session_id"]), int(row["context_version"]))
                contexts[key] = (
                    dict(row["payload"]),
                    int(row["captured_monotonic_offset_ms"]),
                )
                continue
            if kind == "expected":
                continue
            if kind == "control":
                fanout.publish(_control_from_row(row))
                continue
            if kind != "events":
                raise StreamContractError(f"unknown replay row: {kind!r}")
            offset = int(row["accepted_monotonic_offset_ms"])
            if realtime and offset > previous_offset:
                await asyncio.sleep((offset - previous_offset) / 1000.0)
            previous_offset = max(previous_offset, offset)
            session_id = str(row["session_id"])
            context_version = int(row["context_version"])
            context, context_offset = contexts[(session_id, context_version)]
            context = dict(context)
            context["captured_monotonic_ms"] = replay_origin + context_offset
            frozen_context = freeze_context(context)
            fanout.publish_context(frozen_context)
            fanout.publish(
                FrozenAcceptedEventBatch(
                    stream_sequence=int(row["stream_sequence"]),
                    session_id=session_id,
                    batch_sequence=int(row["batch_sequence"]),
                    accepted_monotonic_ms=replay_origin + offset,
                    context_version=context_version,
                    context_payload=frozen_context,
                    events=tuple(_event_from_row(value) for value in row["events"]),
                )
            )


def load_n12_replay(path: Path) -> N12ReplayBundle:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_bytes().splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StreamContractError(f"invalid replay row {line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise StreamContractError(f"replay row {line_no} must be an object")
        rows.append(row)
    if not rows or rows[0].get("row") != "header":
        raise StreamContractError("replay header must be the first row")
    if rows[0].get("schema") != REPLAY_SCHEMA_VERSION:
        raise StreamContractError(f"unsupported replay schema: {rows[0].get('schema')!r}")
    return N12ReplayBundle(tuple(rows))


def _event_to_row(event: FrozenAcceptedEvent) -> dict[str, Any]:
    return {
        "envelope": json.loads(event.envelope),
        "audiences": list(event.audiences),
        "source": event.source,
        "source_ordinal": event.source_ordinal,
        "coalesce_key": list(event.coalesce_key) if event.coalesce_key else None,
        "event_id": event.event_id,
        "sequence": event.sequence,
        "phase": event.phase,
        "priority": event.priority,
        "overlay_payload": (
            json.loads(event.overlay_payload) if event.overlay_payload is not None else None
        ),
    }


def _event_from_row(row: dict[str, Any]) -> FrozenAcceptedEvent:
    coalesce = row.get("coalesce_key")
    return FrozenAcceptedEvent(
        envelope=canonical_json_bytes(row["envelope"]),
        audiences=tuple(row["audiences"]),
        source=str(row["source"]),
        source_ordinal=int(row["source_ordinal"]),
        coalesce_key=(tuple(str(value) for value in coalesce) if coalesce else None),
        event_id=str(row["event_id"]),
        sequence=int(row["sequence"]),
        phase=str(row["phase"]),
        priority=int(row["priority"]),
        overlay_payload=(
            canonical_json_bytes(row["overlay_payload"])
            if row.get("overlay_payload") is not None
            else None
        ),
    )


def _control_from_row(row: dict[str, Any]) -> StreamItem:
    payload = row["payload"]
    sequence = int(row["stream_sequence"])
    if payload["kind"] == "SessionReset":
        return SessionReset(
            str(payload["old_session_id"]),
            str(payload["new_session_id"]),
            str(payload["reason"]),
            sequence,
        )
    if payload["kind"] == "ConfigUpdate":
        return ConfigUpdate(
            int(payload["generation"]), freeze_config(dict(payload["config"])), sequence
        )
    raise StreamContractError(f"unknown replay control: {payload.get('kind')!r}")
