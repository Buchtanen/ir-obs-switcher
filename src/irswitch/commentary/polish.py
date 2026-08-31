"""Optional remote LLM style polish over authored skeleton lines. Fail-soft."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from irswitch.commentary.graph import GraphNode
from irswitch.commentary.validator import validate_utterance
from irswitch.overlay.settings import CommentarySettings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are polishing a TV race call for stream viewers.\n"
    "Keep EVERY fact from SKELETON. Do not add new numbers, names, or events.\n"
    "Never invent yellows, overtakes, final lap, Stay tuned, or BPM.\n"
    "Viewers only, third person. Write exactly 3 sentences unless SKELETON "
    "clearly needs a longer welcome (up to 7 sentences).\n"
    "Commentary only — no meta commentary about being an AI."
)

_SYSTEM_PROMPT_PAST = (
    "You are polishing a TV race call that already happened moments ago.\n"
    "Keep EVERY fact from SKELETON. Do not add new numbers, names, or events.\n"
    "Rewrite in past tense / 'already happened' framing for viewers catching up.\n"
    "Never invent yellows, overtakes, final lap, Stay tuned, or BPM.\n"
    "Viewers only, third person. One or two short sentences.\n"
    "Commentary only — no meta commentary about being an AI."
)


@dataclass(frozen=True)
class PolishOutcome:
    """Result of one polish attempt (for TTS + optional debug tape)."""

    text: str
    outcome: str  # ok | fallback_disabled | fallback_timeout | fallback_validate | fallback_error
    latency_ms: float
    skeleton: str
    request: dict[str, Any]
    response: dict[str, Any] | None = None

    def debug_record(self, *, node_id: str, event_type: str) -> dict[str, Any]:
        return {
            "nodeId": node_id,
            "eventType": event_type,
            "outcome": self.outcome,
            "latencyMs": round(self.latency_ms, 1),
            "skeleton": self.skeleton,
            "polished": self.text if self.outcome == "ok" else None,
            "spoken": self.text,
            "request": self.request,
            "response": self.response,
        }


def build_polish_request(
    skeleton: str, settings: CommentarySettings, *, past: bool = False
) -> dict[str, Any]:
    system = _SYSTEM_PROMPT_PAST if past else _SYSTEM_PROMPT
    user = (
        f"SKELETON:\n{skeleton.strip()}\nRewrite as a brief past call now."
        if past
        else f"SKELETON:\n{skeleton.strip()}\nWrite the live call now."
    )
    return {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }


def polish_skeleton(
    skeleton: str,
    node: GraphNode,
    settings: CommentarySettings,
    *,
    opener: Any | None = None,
    past: bool = False,
) -> PolishOutcome:
    """Blocking HTTP polish. Never raises; returns skeleton on failure."""
    text = (skeleton or "").strip()
    if not text:
        return PolishOutcome(
            text="",
            outcome="fallback_validate",
            latency_ms=0.0,
            skeleton=skeleton,
            request={},
        )
    if not settings.llm_polish:
        return PolishOutcome(
            text=text,
            outcome="fallback_disabled",
            latency_ms=0.0,
            skeleton=text,
            request={},
        )

    payload = build_polish_request(text, settings, past=past)
    url = _chat_completions_url(settings.llm_base_url)
    if urlparse(url).scheme not in {"http", "https"}:
        return PolishOutcome(
            text=text,
            outcome="fallback_error",
            latency_ms=0.0,
            skeleton=text,
            request=payload,
            response={"error": "llm_base_url must be http(s)"},
        )
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        if opener is not None:
            raw = opener(req, timeout=settings.llm_timeout_s)
        else:
            # Scheme validated above (http/https only).
            with urllib.request.urlopen(req, timeout=settings.llm_timeout_s) as resp:  # nosec B310
                raw = resp.read()
    except TimeoutError:
        latency = (time.monotonic() - started) * 1000.0
        return PolishOutcome(
            text=text,
            outcome="fallback_timeout",
            latency_ms=latency,
            skeleton=text,
            request=payload,
        )
    except urllib.error.URLError as exc:
        latency = (time.monotonic() - started) * 1000.0
        logger.warning("commentary llm polish unreachable: %s", exc.reason)
        return PolishOutcome(
            text=text,
            outcome="fallback_error",
            latency_ms=latency,
            skeleton=text,
            request=payload,
            response={"error": str(exc.reason)},
        )
    except Exception as exc:
        latency = (time.monotonic() - started) * 1000.0
        logger.warning("commentary llm polish failed", exc_info=True)
        return PolishOutcome(
            text=text,
            outcome="fallback_error",
            latency_ms=latency,
            skeleton=text,
            request=payload,
            response={"error": str(exc)},
        )

    latency = (time.monotonic() - started) * 1000.0
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return PolishOutcome(
            text=text,
            outcome="fallback_error",
            latency_ms=latency,
            skeleton=text,
            request=payload,
            response={"error": f"bad json: {exc}"},
        )

    content = _extract_content(parsed)
    if not content:
        return PolishOutcome(
            text=text,
            outcome="fallback_error",
            latency_ms=latency,
            skeleton=text,
            request=payload,
            response=_compact_response(parsed),
        )

    issues = validate_utterance(content, node)
    if issues:
        return PolishOutcome(
            text=text,
            outcome="fallback_validate",
            latency_ms=latency,
            skeleton=text,
            request=payload,
            response={
                **_compact_response(parsed),
                "validatorCodes": [item.code for item in issues],
            },
        )

    return PolishOutcome(
        text=content,
        outcome="ok",
        latency_ms=latency,
        skeleton=text,
        request=payload,
        response=_compact_response(parsed),
    )


def _chat_completions_url(base_url: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    if not root:
        root = "http://127.0.0.1:11434/v1"
    if root.endswith("/chat/completions"):
        return root
    return f"{root}/chat/completions"


def _extract_content(parsed: dict[str, Any]) -> str:
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content).strip() if content else ""


def _compact_response(parsed: dict[str, Any]) -> dict[str, Any]:
    usage = parsed.get("usage")
    compact: dict[str, Any] = {
        "id": parsed.get("id"),
        "model": parsed.get("model"),
        "content": _extract_content(parsed),
    }
    if isinstance(usage, dict):
        compact["usage"] = usage
    return compact
