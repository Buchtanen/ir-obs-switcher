#!/usr/bin/env python3
"""Repeatable no-retry Qwen latency probe for the v2 release corpus.

This branch-only utility prints JSON evidence to stdout. It never writes runtime
configuration and deliberately disables environment proxies and redirects.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import ssl
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

GOLDENS = Path(__file__).with_name("qwen-transport-goldens.json")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def endpoint(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("endpoint must be a plain local/LAN HTTP(S) URL")
    host = parsed.hostname
    if host != "localhost":
        try:
            address = ipaddress.ip_address(host or "")
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "DNS hostnames other than localhost are forbidden"
            ) from exc
        if not (address.is_loopback or address.is_private or address.is_link_local):
            raise argparse.ArgumentTypeError("endpoint must be loopback or private/link-local")
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        return value.rstrip("/")
    if path and not path.endswith("/v1"):
        raise argparse.ArgumentTypeError("endpoint path must be empty, /v1 or /chat/completions")
    return value.rstrip("/") + "/chat/completions"


def opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )


def post(
    client: urllib.request.OpenerDirector,
    url: str,
    body: dict[str, Any],
    timeout: float,
    stream: bool,
) -> dict[str, Any]:
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    request = urllib.request.Request(
        url,
        data=encoded,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        },
    )
    started = time.monotonic_ns()
    with client.open(request, timeout=timeout) as response:
        headers_at = time.monotonic_ns()
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP status {response.status}")
        if not stream:
            payload = response.read(65537)
            if len(payload) > 65536:
                raise RuntimeError("warm-up response exceeds 65536 bytes")
            json.loads(payload)
            completed = time.monotonic_ns()
            return {
                "ttfbMs": (headers_at - started) / 1_000_000,
                "ttftMs": None,
                "totalMs": (completed - started) / 1_000_000,
                "outputBytes": len(payload),
            }
        total = 0
        visible = bytearray()
        first_content: int | None = None
        finish: str | None = None
        done = False
        for raw_line in response:
            total += len(raw_line)
            if total > 65536 or len(raw_line) > 16384:
                raise RuntimeError("SSE size limit exceeded")
            line = raw_line.decode("utf-8").rstrip("\r\n")
            if not line:
                continue
            if not line.startswith("data: "):
                raise RuntimeError("invalid SSE field")
            data = line[6:]
            if done:
                raise RuntimeError("semantic data after DONE")
            if data == "[DONE]":
                done = True
                continue
            frame = json.loads(data)
            choices = frame.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise RuntimeError("expected one SSE choice")
            choice = choices[0]
            if choice.get("index") != 0:
                raise RuntimeError("unexpected SSE choice index")
            delta = choice.get("delta")
            if not isinstance(delta, dict) or "tool_calls" in delta or "function_call" in delta:
                raise RuntimeError("invalid SSE delta")
            content = delta.get("content")
            if content is not None:
                if not isinstance(content, str):
                    raise RuntimeError("non-string SSE content")
                chunk = content.encode()
                if chunk and first_content is None:
                    first_content = time.monotonic_ns()
                visible.extend(chunk)
                if len(visible) > 2048:
                    raise RuntimeError("visible output exceeds 2048 bytes")
            if "finish_reason" in choice:
                finish = choice["finish_reason"]
        completed = time.monotonic_ns()
        if not done or finish != "stop" or not visible:
            raise RuntimeError("incomplete or non-stop SSE result")
        return {
            "ttfbMs": (headers_at - started) / 1_000_000,
            "ttftMs": (None if first_content is None else (first_content - started) / 1_000_000),
            "totalMs": (completed - started) / 1_000_000,
            "outputBytes": len(visible),
        }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def summarize(samples: list[dict[str, Any]], key: str) -> dict[str, float] | None:
    values = [row[key] for row in samples if row[key] is not None]
    if not values:
        return None
    return {
        "median": statistics.median(values),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "maximum": max(values),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True, type=endpoint)
    parser.add_argument("--model", required=True)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=float, default=1.5)
    parser.add_argument("--residency", choices=("warm", "cold"), required=True)
    parser.add_argument("--warmup", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.iterations <= 1000:
        parser.error("--iterations must be in 1..1000")
    if args.residency == "warm" and not args.warmup:
        parser.error("warm residency evidence requires --warmup")
    goldens = json.loads(GOLDENS.read_text(encoding="utf-8"))
    client = opener()
    warmup_result = None
    if args.warmup:
        body = goldens["warmup"]["body"]
        body["model"] = args.model
        warmup_result = post(client, args.endpoint, body, 10.0, False)
    body = goldens["canonicalBackendRequest"]
    body["model"] = args.model
    samples = []
    failures = []
    for ordinal in range(1, args.iterations + 1):
        try:
            samples.append(
                {
                    "ordinal": ordinal,
                    **post(
                        client,
                        args.endpoint,
                        body,
                        args.timeout_seconds,
                        True,
                    ),
                }
            )
        except (OSError, ValueError, RuntimeError, urllib.error.HTTPError) as exc:
            failures.append(
                {
                    "ordinal": ordinal,
                    "type": type(exc).__name__,
                    "message": str(exc)[:128],
                }
            )
    report = {
        "schemaVersion": "qwen-latency-report/2",
        "residency": args.residency,
        "model": args.model,
        "endpointHost": urllib.parse.urlsplit(args.endpoint).hostname,
        "iterations": args.iterations,
        "successful": len(samples),
        "failed": len(failures),
        "warmup": warmup_result,
        "metrics": {key: summarize(samples, key) for key in ("ttfbMs", "ttftMs", "totalMs")},
        "samples": samples,
        "failures": failures,
        "retries": 0,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if samples and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
