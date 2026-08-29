"""TTS intonation / SSML validator for authored commentary lines."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable

from irswitch.commentary.graph import GraphNode, TtsLimits

_TERMINAL = re.compile(r"[.!?…][\"')\]]*$")
_MULTI_PUNCT = re.compile(r"[!?]{2,}|\.{3,}|…{2,}")
_ALL_CAPS = re.compile(r"\b[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{4,}\b")
_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002700-\U000027bf"
    "\U0001f000-\U0001f0ff"
    "]+"
)
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_LONG_DIGIT = re.compile(r"\d{4,}")
_SLOT = re.compile(r"\{([a-z0-9_]+)\}")
_CHARS_PER_SECOND = 13.0
_MAX_BREAK_MS = 500
_ALLOWED_EMPHASIS = frozenset({"reduced", "moderate", "strong"})
_ALLOWED_RATE = frozenset({"slow", "medium", "fast", "x-slow", "x-fast"})

# Tags we may wrap around authored text. Author-visible allow-list is narrower.
_TREE_TAGS = frozenset({"speak", "break", "emphasis", "prosody"})


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"


def validate_utterance(
    text: str,
    node: GraphNode,
    *,
    limits: TtsLimits | None = None,
) -> list[ValidationIssue]:
    """Return issues for one authored line. Empty list = speakable."""
    tts = limits or node.tts
    issues: list[ValidationIssue] = []
    raw = text if isinstance(text, str) else ""
    stripped = raw.strip()
    if not stripped:
        issues.append(ValidationIssue("empty", "utterance is empty"))
        return issues

    if _EMOJI.search(stripped):
        issues.append(ValidationIssue("emoji", "emoji is not speakable"))
    if _URL.search(stripped):
        issues.append(ValidationIssue("url", "URLs are not speakable"))
    if _MULTI_PUNCT.search(_plain_text(stripped)):
        issues.append(
            ValidationIssue(
                "multi_punct",
                "stacked punctuation (!!, ??, ...) breaks TTS intonation; use one mark or <break/>",
            )
        )

    slots = _SLOT.findall(stripped)
    known = {slot.name for slot in node.slots}
    for name in slots:
        if name not in known:
            issues.append(ValidationIssue("unknown_slot", f"unknown slot {{{name}}}"))
    if "{" in stripped and "}" not in stripped:
        issues.append(ValidationIssue("unbalanced_slot", "unbalanced '{' in utterance"))
    if "}" in stripped and "{" not in stripped:
        issues.append(ValidationIssue("unbalanced_slot", "unbalanced '}' in utterance"))

    if _is_ssml(stripped):
        issues.extend(_validate_ssml(stripped, tts))
        spoken = _plain_text(stripped)
    else:
        spoken = stripped
        if "&" in spoken and "&amp;" not in raw and "&lt;" not in raw:
            issues.append(
                ValidationIssue(
                    "ampersand",
                    "raw '&' is unsafe for TTS/SSML; write 'and' / 'a' or an entity",
                )
            )

    if tts.require_terminal_punct and spoken and not _TERMINAL.search(spoken):
        issues.append(
            ValidationIssue(
                "terminal_punct",
                "end with . ! or ? so TTS can fall (statement) or rise (question)",
            )
        )

    if _ALL_CAPS.search(spoken):
        issues.append(
            ValidationIssue(
                "all_caps",
                "ALL-CAPS words make most TTS engines shout; use emphasis SSML instead",
            )
        )

    if _LONG_DIGIT.search(spoken):
        issues.append(
            ValidationIssue(
                "long_number",
                "digit runs of 4+ are read digit-by-digit; use a slot or spoken form",
            )
        )

    if len(spoken) > tts.max_chars:
        issues.append(
            ValidationIssue(
                "max_chars",
                f"{len(spoken)} chars exceeds max {tts.max_chars}",
            )
        )

    estimated = estimate_seconds(spoken, ssml=stripped if _is_ssml(stripped) else None)
    if estimated > tts.max_seconds:
        issues.append(
            ValidationIssue(
                "max_seconds",
                f"estimated {estimated:.1f}s exceeds max {tts.max_seconds:.1f}s",
            )
        )

    return issues


def estimate_seconds(spoken: str, *, ssml: str | None = None) -> float:
    """Rough spoken duration. Used for speak-lock, not a DSP measurement."""
    base = max(0.4, len(spoken) / _CHARS_PER_SECOND)
    extra = 0.0
    if ssml:
        for match in re.finditer(r'time="(\d+)ms"', ssml):
            extra += int(match.group(1)) / 1000.0
        extra += 0.12 * len(re.findall(r"<break\b", ssml))
    return base + extra


def fill_slots(text: str, values: dict[str, object]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values or values[key] is None:
            return match.group(0)
        return str(values[key])

    return _SLOT.sub(repl, text)


def _is_ssml(text: str) -> bool:
    return "<" in text and ">" in text


def _plain_text(text: str) -> str:
    if not _is_ssml(text):
        return text
    try:
        root = ET.fromstring(_wrap_speak(text))
    except ET.ParseError:
        return re.sub(r"<[^>]+>", " ", text)
    chunks = ["".join(root.itertext())]
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()


def _wrap_speak(text: str) -> str:
    trimmed = text.strip()
    if trimmed.startswith("<speak"):
        return trimmed
    return f"<speak>{trimmed}</speak>"


def _validate_ssml(text: str, tts: TtsLimits) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    allowed = set(tts.ssml_allowed) | {"speak"}
    try:
        root = ET.fromstring(_wrap_speak(text))
    except ET.ParseError as exc:
        issues.append(ValidationIssue("ssml_parse", f"SSML is not well-formed: {exc}"))
        return issues

    for element in root.iter():
        tag = _local(element.tag)
        if tag not in _TREE_TAGS:
            issues.append(ValidationIssue("ssml_tag", f"unsupported SSML tag <{tag}>"))
            continue
        if tag not in allowed and tag != "speak":
            issues.append(ValidationIssue("ssml_tag", f"tag <{tag}> is not allowed on this node"))
        if tag == "break":
            issues.extend(_check_break(element))
        if tag == "emphasis":
            level = (element.get("level") or "moderate").lower()
            if level not in _ALLOWED_EMPHASIS:
                issues.append(
                    ValidationIssue("ssml_emphasis", f"emphasis level {level!r} is not allowed")
                )
        if tag == "prosody":
            issues.extend(_check_prosody(element, allowed))
    return issues


def _check_break(element: ET.Element) -> list[ValidationIssue]:
    time_raw = element.get("time")
    if not time_raw:
        return []
    match = re.fullmatch(r"(\d+)ms", time_raw.strip())
    if match is None:
        return [ValidationIssue("ssml_break", "break time must look like 200ms")]
    if int(match.group(1)) > _MAX_BREAK_MS:
        return [
            ValidationIssue(
                "ssml_break",
                f"break {time_raw} exceeds {_MAX_BREAK_MS}ms (intonation stall)",
            )
        ]
    return []


def _check_prosody(element: ET.Element, allowed: Iterable[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if "prosody" not in set(allowed):
        issues.append(ValidationIssue("ssml_tag", "tag <prosody> is not allowed on this node"))
        return issues
    rate = element.get("rate")
    if rate and rate.lower() not in _ALLOWED_RATE:
        issues.append(ValidationIssue("ssml_prosody", f"prosody rate {rate!r} is not allowed"))
    pitch = element.get("pitch")
    if pitch and not re.fullmatch(r"[+-]?\d{1,2}%", pitch.strip()):
        issues.append(ValidationIssue("ssml_prosody", "prosody pitch must be like +5% or -8%"))
    return issues


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def issues_as_codes(issues: list[ValidationIssue]) -> list[str]:
    return [item.code for item in issues]
