"""Optional remote LLM style polish over authored skeleton lines. Fail-soft.

Live inference stays the LAN Ollama 3B (RTX A1000). A 4090 is for optional
later fine-tuning, not a different runtime model.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from irswitch.commentary.graph import GraphNode, TtsLimits
from irswitch.commentary.validator import validate_utterance
from irswitch.overlay.settings import CommentarySettings

logger = logging.getLogger(__name__)

# High-precision junk only. Do not NLP-match names/leads — that rejects good paraphrases.
_BANNED_PHRASE = re.compile(
    r"\b(welcome back|stay tuned|ladies and gentlemen)\b",
    re.IGNORECASE,
)
_EXPAND_PAD = 40
_EXPAND_RATIO = 1.35
_MIN_ATTEMPT_S = 0.05

_LEAD_CLAIM = re.compile(
    r"\b(unchallenged lead|narrow lead|the lead|leads?|leading|leader)\b",
    re.IGNORECASE,
)
_LEAD_OK = re.compile(
    r"\b(unchallenged lead|narrow lead|the lead|leads?|leading|leader|"
    r"pole|p\s*one|p\s*1|position\s*one)\b",
    re.IGNORECASE,
)
_POLE = re.compile(r"\bpole\b", re.IGNORECASE)
_RIVAL_AHEAD = re.compile(r"\bis ahead\b", re.IGNORECASE)
_TRAIL = re.compile(r"\b(trails?|trailing|behind|closing on|hunting)\b", re.IGNORECASE)
_PASS = re.compile(r"\b(inches past|overtakes?|overtook|passes?|passed|edges)\b", re.IGNORECASE)
_WESTWARD = re.compile(r"\b(westward|eastward|northward|southward)\b", re.IGNORECASE)
_CM = re.compile(r"\b(centimet(?:er|re)s?|centimeters?)\b", re.IGNORECASE)
_SECONDS = re.compile(r"\bseconds?\b", re.IGNORECASE)
_LIVE_CALL = re.compile(r"^\s*Live Call\s*:", re.IGNORECASE)
_HERO_PREFIX = re.compile(r"^([A-Z][a-z]{2,})\.\s+([A-Z][a-z]{2,})\b")
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

_FACT_LOCK = (
    "Keep EVERY fact from SKELETON. Do not add new numbers, names, or events.\n"
    "Keep numbers written as words (as in the skeleton); do not reintroduce digits.\n"
    "Keep units as words (meters per second, degrees Celsius, seconds); "
    "do not reintroduce abbreviations (m/s, °C, km/h).\n"
    "Never invent yellows, overtakes, final lap, Stay tuned, leads, or BPM.\n"
    "Do not turn a chase into a lead, or a position loss into a gain.\n"
    "P two / P two / second is a race position, not pole.\n"
    "ahead / trails / closing on / P two are not a lead. Do not say the featured "
    "driver leads unless SKELETON already says lead, P one, or pole.\n"
    "Surnames (West, Leep, and similar) are people, never compass directions.\n"
    "Do not prefix the line with Live Call:.\n"
    "Do not glue the featured driver name onto another driver's surname "
    "(not Richard Ohanian).\n"
    "Never you/your/jsi/tvůj to the featured driver. Viewers hear about the protagonist; "
    "rivals are the other named drivers.\n"
    "Never open with the featured driver's name and a comma (not 'Richard, ...'). "
    "Never open with Name. then the rest of the call. Talk about the driver; do not address them.\n"
)

_FACT_LOCK_CS = (
    "Zachovej KAŽDÝ fakt ze SKELETONU. Nepřidávej nová čísla, jména ani události.\n"
    "Čísla ponech slovně a nevracej číslice ani zkratky jednotek.\n"
    "Nikdy nevymýšlej žlutou vlajku, předjetí, poslední kolo, vedení ani BPM.\n"
    "Nezaměň stíhání za vedení a ztrátu pozice za zisk.\n"
    "Mluv o hlavním jezdci ve třetí osobě; nikdy ho neoslovuj jako ty nebo vy.\n"
    "Nevkládej úvod typu Živě ani meta komentář.\n"
)


def _hero_lock(driver_names: Sequence[str]) -> str:
    shown = " / ".join(n.strip() for n in driver_names if n and str(n).strip())
    if not shown:
        return ""
    return (
        f"The featured driver is {shown}, the protagonist of the call. "
        "Speak about that driver in third person (name mixed with he/him/his). "
        "Other named people are rivals, not the featured driver. "
        "Never address the featured driver as you/your; this is for stream viewers, not pit radio. "
        "Do not open with their name plus a comma or a lone Name. sentence.\n"
    )


def _tts_for(node: GraphNode | None) -> TtsLimits:
    return node.tts if node is not None else TtsLimits()


def polish_char_limit(skeleton: str, tts: TtsLimits) -> int:
    """Polish may restyle, not grow into a second invented sentence."""
    n = len((skeleton or "").strip())
    grown = max(n + _EXPAND_PAD, int(n * _EXPAND_RATIO) if n else 64)
    return min(int(tts.max_chars), grown)


def _length_rule(tts: TtsLimits, skeleton: str) -> str:
    cap = polish_char_limit(skeleton, tts)
    return (
        "Stream-viewer commentary only, third person about the featured driver. "
        "Same sentence count as the skeleton; "
        "do not add a sentence. Richer wording of the same facts only. "
        f"Hard cap {cap} characters for this skeleton and {tts.max_seconds:g} seconds spoken. "
        "Do not welcome, recap unused history, or invent action."
    )


def _completion_tokens(settings: CommentarySettings, tts: TtsLimits, skeleton: str) -> int:
    # Bound to this skeleton so the model cannot dump into the node TTS ceiling.
    budget = polish_char_limit(skeleton, tts) + 16
    return max(32, min(int(settings.llm_max_tokens), budget))


def _expansion_code(skeleton: str, content: str, tts: TtsLimits) -> str | None:
    if _BANNED_PHRASE.search(content or ""):
        return "banned_phrase"
    if len((content or "").strip()) > polish_char_limit(skeleton, tts):
        return "expanded"
    return None


def fact_violation_codes(
    skeleton: str,
    polished: str,
    driver_names: Sequence[str] = (),
    *,
    fact_pack: dict[str, Any] | None = None,
) -> list[str]:
    """Reject VOD-style inversions the 3B model repeats. Empty = fact-ok."""
    sk = skeleton or ""
    po = polished or ""
    codes: list[str] = []
    if _LIVE_CALL.search(po):
        codes.append("live_call_prefix")
    if _LEAD_CLAIM.search(po) and not _LEAD_OK.search(sk):
        codes.append("invented_lead")
    if _POLE.search(po) and not _POLE.search(sk) and not _LEAD_OK.search(sk):
        codes.append("invented_pole")
    if (_TRAIL.search(sk) or _RIVAL_AHEAD.search(sk)) and _LEAD_CLAIM.search(po):
        codes.append("polarity_flip")
    if _TRAIL.search(sk) and _PASS.search(po) and not _PASS.search(sk):
        codes.append("invented_pass")
    if re.search(r"\bWest\b", sk) and _WESTWARD.search(po):
        codes.append("surname_as_direction")
    if _SECONDS.search(sk) and _CM.search(po):
        codes.append("unit_distortion")
    fused = _HERO_PREFIX.match(sk.strip())
    if fused is not None:
        glued = f"{fused.group(1)} {fused.group(2)}"
        if re.search(rf"\b{re.escape(glued)}\b", po) and glued not in sk:
            codes.append("hero_name_fusion")
    if _hero_vocative(po, driver_names):
        codes.append("hero_vocative")
    if _two_front_polarity_conflict(po, fact_pack):
        codes.append("two_front_polarity_conflict")
    return codes


def _two_front_polarity_conflict(
    polished: str,
    fact_pack: dict[str, Any] | None,
) -> bool:
    if not isinstance(fact_pack, dict):
        return False
    front = fact_pack.get("front_target")
    rear = fact_pack.get("rear_target")
    if not isinstance(front, dict) or not isinstance(rear, dict):
        return False
    front_name = str(front.get("name") or "").strip()
    rear_name = str(rear.get("name") or "").strip()
    if not front_name or not rear_name or front_name.casefold() == rear_name.casefold():
        return bool(front_name and rear_name)
    text = polished or ""
    front_behind = re.search(
        rf"\b{re.escape(front_name)}\b[^.!?]{{0,48}}\b(behind|from behind|rear|zezadu|vzadu)\b",
        text,
        re.IGNORECASE,
    )
    rear_ahead = re.search(
        rf"\b{re.escape(rear_name)}\b[^.!?]{{0,48}}\b(ahead|in front|vpředu|před ním)\b",
        text,
        re.IGNORECASE,
    )
    return front_behind is not None or rear_ahead is not None


def _hero_vocative(text: str, names: Sequence[str]) -> bool:
    """True when the line opens by addressing the featured driver."""
    raw = (text or "").lstrip()
    if not raw:
        return False
    for name in names:
        token = str(name).strip()
        if not token:
            continue
        # Richard, that's a lap.
        if re.match(rf"^{re.escape(token)}\s*,", raw, flags=re.IGNORECASE):
            return True
        # Richard. That's a lap.
        if re.match(rf"^{re.escape(token)}\.\s+\S", raw, flags=re.IGNORECASE):
            return True
    return False


def _reject_codes(
    skeleton: str,
    content: str,
    node: GraphNode,
    driver_names: Sequence[str] = (),
    fact_pack: dict[str, Any] | None = None,
) -> list[str]:
    codes: list[str] = []
    expand = _expansion_code(skeleton, content, node.tts)
    if expand:
        codes.append(expand)
    issues = validate_utterance(content, node)
    codes.extend(item.code for item in issues)
    for code in fact_violation_codes(skeleton, content, driver_names, fact_pack=fact_pack):
        if code not in codes:
            codes.append(code)
    return codes


def _system_prompt(
    *,
    past: bool,
    tts: TtsLimits,
    skeleton: str,
    driver_names: Sequence[str] = (),
    locale: str = "en",
) -> str:
    if locale.lower().startswith("cs"):
        cap = polish_char_limit(skeleton, tts)
        timing = "opožděný televizní komentář" if past else "živý televizní komentář"
        return (
            f"Uprav {timing} pro diváky streamu, ne rádio do kokpitu.\n"
            f"{_FACT_LOCK_CS}"
            "Zachovej stejný počet vět; nepřidávej další větu. "
            f"Limit je {cap} znaků a {tts.max_seconds:g} sekundy mluveného projevu. "
            "Pouze výsledný komentář, bez vysvětlování."
        )
    hero = _hero_lock(driver_names)
    if past:
        lead = (
            "Polish a TV race call that already happened moments ago.\n"
            f"{_FACT_LOCK}{hero}"
            "Keep the same facts; do not invent that a pass, lead, or finish already happened.\n"
        )
    else:
        lead = "Polish a TV race call for stream viewers.\n" f"{_FACT_LOCK}{hero}"
    return (
        f"{lead}{_length_rule(tts, skeleton)}\n"
        "Commentary only — no meta commentary about being an AI."
    )


def _user_content(
    skeleton: str,
    *,
    past: bool,
    rejected: Sequence[str] = (),
    previous: str | None = None,
    fact_pack: dict[str, Any] | None = None,
    composition_path: Sequence[str] = (),
) -> str:
    instruction = (
        "Rewrite this delayed call. Same facts, same length, richer wording only."
        if past
        else "Rewrite the live call. Same facts, same length, richer wording only."
    )
    parts = [f"SKELETON:\n{skeleton}\n{instruction}"]
    if fact_pack:
        parts.append(
            "FACTS:\n"
            + json.dumps(fact_pack, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )
    if composition_path:
        parts.append("COMPOSITION_PATH: " + " -> ".join(str(item) for item in composition_path))
    if rejected:
        parts.append(
            "PREVIOUS REWRITE REJECTED: "
            + ", ".join(rejected)
            + ". Do not repeat those mistakes. Output only the rewrite."
        )
        if previous:
            parts.append(f"REJECTED TEXT:\n{previous}")
    return "\n".join(parts)


@dataclass(frozen=True)
class PolishOutcome:
    """Result of one polish attempt (for TTS + optional debug tape)."""

    text: str
    outcome: str  # ok | fallback_disabled | fallback_timeout | fallback_error | retry_exhausted
    latency_ms: float
    skeleton: str
    request: dict[str, Any]
    response: dict[str, Any] | None = None
    attempts: int = 0
    fact_pack: dict[str, Any] | None = None
    composition_path: tuple[str, ...] = ()

    def debug_record(self, *, node_id: str, event_type: str) -> dict[str, Any]:
        last = None
        if isinstance(self.response, dict):
            last = self.response.get("content")
        return {
            "nodeId": node_id,
            "eventType": event_type,
            "outcome": self.outcome,
            "latencyMs": round(self.latency_ms, 1),
            "attempts": self.attempts,
            "skeleton": self.skeleton,
            "polished": self.text if self.outcome == "ok" else last,
            "spoken": self.text,
            "request": self.request,
            "response": self.response,
            "factPack": self.fact_pack,
            "compositionPath": list(self.composition_path),
        }


def _max_attempts(settings: CommentarySettings) -> int:
    try:
        raw = int(getattr(settings, "llm_max_attempts", 5) or 5)
    except (TypeError, ValueError):
        raw = 5
    return max(1, min(8, raw))


def build_polish_request(
    skeleton: str,
    settings: CommentarySettings,
    *,
    past: bool = False,
    node: GraphNode | None = None,
    driver_names: Sequence[str] = (),
    rejected: Sequence[str] = (),
    previous: str | None = None,
    locale: str = "en",
    fact_pack: dict[str, Any] | None = None,
    composition_path: Sequence[str] = (),
) -> dict[str, Any]:
    tts = _tts_for(node)
    text = skeleton.strip()
    return {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": _completion_tokens(settings, tts, text),
        # Native Ollama + OpenAI-compat: keep Qwen3 from spending the token
        # budget on a thinking trace (empty content / timeout).
        "think": False,
        "reasoning_effort": "none",
        "messages": [
            {
                "role": "system",
                "content": _system_prompt(
                    past=past,
                    tts=tts,
                    skeleton=text,
                    driver_names=driver_names,
                    locale=locale,
                ),
            },
            {
                "role": "user",
                "content": _user_content(
                    text,
                    past=past,
                    rejected=rejected,
                    previous=previous,
                    fact_pack=fact_pack,
                    composition_path=composition_path,
                ),
            },
        ],
    }


def _failed(
    *,
    outcome: str,
    latency_ms: float,
    skeleton: str,
    request: dict[str, Any],
    response: dict[str, Any] | None = None,
    attempts: int,
    fact_pack: dict[str, Any] | None = None,
    composition_path: Sequence[str] = (),
) -> PolishOutcome:
    return PolishOutcome(
        text="",
        outcome=outcome,
        latency_ms=latency_ms,
        skeleton=skeleton,
        request=request,
        response=response,
        attempts=attempts,
        fact_pack=fact_pack,
        composition_path=tuple(composition_path),
    )


def polish_skeleton(
    skeleton: str,
    node: GraphNode,
    settings: CommentarySettings,
    *,
    opener: Any | None = None,
    past: bool = False,
    driver_names: Sequence[str] = (),
    locale: str = "en",
    fact_pack: dict[str, Any] | None = None,
    composition_path: Sequence[str] = (),
) -> PolishOutcome:
    """Blocking HTTP polish. Never raises. Empty text when polish is on and fails."""
    text = (skeleton or "").strip()
    if not text:
        return PolishOutcome(
            text="",
            outcome="fallback_validate",
            latency_ms=0.0,
            skeleton=skeleton,
            request={},
            attempts=0,
            fact_pack=fact_pack,
            composition_path=tuple(composition_path),
        )
    if not settings.llm_polish:
        return PolishOutcome(
            text=text,
            outcome="fallback_disabled",
            latency_ms=0.0,
            skeleton=text,
            request={},
            attempts=0,
            fact_pack=fact_pack,
            composition_path=tuple(composition_path),
        )

    url = _chat_completions_url(settings.llm_base_url)
    if urlparse(url).scheme not in {"http", "https"}:
        return _failed(
            outcome="fallback_error",
            latency_ms=0.0,
            skeleton=text,
            request=build_polish_request(
                text,
                settings,
                past=past,
                node=node,
                driver_names=driver_names,
                locale=locale,
                fact_pack=fact_pack,
                composition_path=composition_path,
            ),
            response={"error": "llm_base_url must be http(s)"},
            attempts=0,
            fact_pack=fact_pack,
            composition_path=composition_path,
        )

    max_attempts = _max_attempts(settings)
    deadline = time.monotonic() + max(0.5, float(settings.llm_timeout_s))
    started = time.monotonic()
    payload: dict[str, Any] = {}
    last_response: dict[str, Any] | None = None
    timed_out = 0
    http_ok = 0

    for attempt in range(1, max_attempts + 1):
        remaining = deadline - time.monotonic()
        if remaining <= _MIN_ATTEMPT_S:
            break
        rejected: Sequence[str] = ()
        previous: str | None = None
        if isinstance(last_response, dict):
            codes = last_response.get("validatorCodes")
            if isinstance(codes, list) and codes:
                rejected = [str(code) for code in codes]
            previous = str(last_response.get("content") or "") or None
        payload = build_polish_request(
            text,
            settings,
            past=past,
            node=node,
            driver_names=driver_names,
            rejected=rejected,
            previous=previous,
            locale=locale,
            fact_pack=fact_pack,
            composition_path=composition_path,
        )
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            if opener is not None:
                raw = opener(req, timeout=remaining)
            else:
                with urllib.request.urlopen(req, timeout=remaining) as resp:  # nosec B310
                    raw = resp.read()
        except TimeoutError:
            timed_out += 1
            last_response = {"error": "timeout"}
            continue
        except urllib.error.URLError as exc:
            last_response = {"error": str(exc.reason)}
            logger.warning("commentary llm polish unreachable: %s", exc.reason)
            continue
        except Exception as exc:
            last_response = {"error": str(exc)}
            logger.warning("commentary llm polish failed", exc_info=True)
            continue

        http_ok += 1
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_response = {"error": f"bad json: {exc}"}
            continue

        if not isinstance(parsed, dict):
            last_response = {"error": "not an object"}
            continue
        content = _extract_content(parsed)
        compact = _compact_response(parsed)
        if not content:
            last_response = compact
            continue

        codes = _reject_codes(text, content, node, driver_names, fact_pack)
        last_response = {**compact, "validatorCodes": codes}
        if codes:
            continue

        latency = (time.monotonic() - started) * 1000.0
        return PolishOutcome(
            text=content,
            outcome="ok",
            latency_ms=latency,
            skeleton=text,
            request=payload,
            response=compact,
            attempts=attempt,
            fact_pack=fact_pack,
            composition_path=tuple(composition_path),
        )

    latency = (time.monotonic() - started) * 1000.0
    attempts_done = max(timed_out + http_ok, 1)
    if http_ok == 0 and timed_out > 0:
        kind = "fallback_timeout"
    elif http_ok == 0:
        kind = "fallback_error"
    else:
        kind = "retry_exhausted"
    return _failed(
        outcome=kind,
        latency_ms=latency,
        skeleton=text,
        request=payload,
        response=last_response,
        attempts=attempts_done,
        fact_pack=fact_pack,
        composition_path=composition_path,
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
    raw = str(content).strip() if content else ""
    if raw:
        return _THINK_BLOCK.sub("", raw).strip()
    return ""


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
