"""Bounded, process-owned diagnostic journal alongside the versioned narrative tape.

This companion format records model input and reducer outcomes, not SDK replay.
Disk work runs off the event loop. Failures and loss remain visible in status.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from irswitch.build_identity import BUILD_IDENTITY

logger = logging.getLogger(__name__)


class LiveCommentaryTrace:
    def __init__(
        self,
        directory: Path,
        *,
        secrets: Callable[[], list[str]] = lambda: [],
        capacity: int = 2048,
        max_bytes: int = 128 * 1024 * 1024,
    ) -> None:
        self.path = directory / f"commentary-trace-{uuid4().hex}.ndjson"
        self._secrets = secrets
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=capacity)
        self._task: asyncio.Task[None] | None = None
        self._closing = False
        self._sequence = 0
        self._drops = 0
        self._written = 0
        self._bytes = 0
        self._max_bytes = max_bytes
        self._error: str | None = None

    def submit(self, kind: str, payload: dict[str, Any]) -> None:
        if self._closing:
            self._drops += 1
            return
        self._sequence += 1
        try:
            line = json.dumps(
                {
                    "schemaVersion": "commentary-trace/1",
                    "sequence": self._sequence,
                    "recordType": kind,
                    "monoMs": round(time.monotonic() * 1000),
                    "payload": payload,
                },
                ensure_ascii=False,
                allow_nan=False,
            )
            for secret in self._secrets():
                if secret:
                    # Also redact JSON-escaped secrets, without persisting credentials.
                    line = line.replace(json.dumps(secret, ensure_ascii=False)[1:-1], "[REDACTED]")
            if len(line.encode("utf-8")) > 262144:
                self._drops += 1
                return
            self._queue.put_nowait(line + "\n")
        except Exception:
            # Diagnostic serialization or redaction must never break the producer.
            self._drops += 1

    def status(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "queued": self._queue.qsize(),
            "written": self._written,
            "drops": self._drops,
            "bytes": self._bytes,
            "error": self._error,
            "complete": self._error is None and self._drops == 0,
        }

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        if self._task is not None:
            # Each supervised restart owns a fresh journal, never append after a trailer.
            self.path = self.path.parent / f"commentary-trace-{uuid4().hex}.ndjson"
            self._sequence = self._drops = self._written = self._bytes = 0
            self._error = None
            self._queue = asyncio.Queue(maxsize=self._queue.maxsize)
        self._closing = False
        self.submit(
            "manifest",
            {
                "build": dict(BUILD_IDENTITY),
                "maxBytes": self._max_bytes,
                "inputPolicy": "structured input and request messages; no headers or endpoint",
                "responsePolicy": "bounded candidate and outcome; no raw provider response",
            },
        )
        self._task = asyncio.create_task(self._run(), name="commentary-live-trace")

    def _append(self, lines: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            for line in lines:
                data = line.encode("utf-8")
                if self._bytes + len(data) > self._max_bytes:
                    self._error = "size_limit"
                    self._drops += 1
                    continue
                handle.write(data)
                self._bytes += len(data)
                self._written += 1
            handle.flush()

    async def _run(self) -> None:
        while not self._closing or not self._queue.empty():
            lines: list[str] = []
            try:
                lines.append(await asyncio.wait_for(self._queue.get(), timeout=0.25))
            except TimeoutError:
                continue
            while len(lines) < 64 and not self._queue.empty():
                lines.append(self._queue.get_nowait())
            try:
                await asyncio.to_thread(self._append, lines)
            except OSError:
                self._error = "write_failed"
                self._drops += len(lines)
                logger.error("Commentary trace write failed")
        # Reserved final marker even after the data size limit is reached.
        trailer = (
            json.dumps(
                {
                    "schemaVersion": "commentary-trace/1",
                    "recordType": "trailer",
                    "payload": self.status(),
                }
            )
            + "\n"
        )
        try:
            await asyncio.to_thread(self._append_trailer, trailer)
        except OSError:
            self._error = "write_failed"

    def _append_trailer(self, trailer: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(trailer)

    async def close(self) -> None:
        self._closing = True
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=2.0)
            except TimeoutError:
                self._error = "flush_timeout"
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
