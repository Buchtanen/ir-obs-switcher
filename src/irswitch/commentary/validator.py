"""TTS intonation / SSML validator for authored commentary lines."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from irswitch.commentary.graph import GraphNode, TtsLimits
from irswitch.commentary.semantic_vocabulary import validate_node_vocabulary

_TERMINAL = re.compile(r"[.!?…][\"')\]]*$")
_MULTI_PUNCT = re.compile(r"[!?]{2,}|\.{3,}|…{2,}")
_ALL_CAPS = re.compile(r"\b[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{4,}\b")
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_LONG_DIGIT = re.compile(r"\d{4,}")
_SLOT = re.compile(r"\{([a-z0-9_]+)\}")
_BREAK_TIME = re.compile(r'time="(\d{1,6})ms"')
_ALLOWED_TAGS = frozenset({"speak", "break", "emphasis", "prosody"})
_CHARS_PER_SECOND = 13.0
# Same contract as sequence_graph viewer-voice tests. Not pit radio to the driver.
_ADDRESS_EN = re.compile(
    r"\b(you|your|yours|you're|you've|you'll)\b",
    re.IGNORECASE,
)
_ADDRESS_CS = re.compile(
    r"\b(ty|tvoje|tvůj|tvá|jsi|jedeš|máš|musíš|můžeš|vezmi|drž)\b",
    re.IGNORECASE,
)
# "{target_name}, that's a lap." talks TO the named driver. Subject "{target_name} is" is OK.
_VOCATIVE_SLOT = re.compile(r"^\s*\{([a-z0-9_]+)\}\s*,")
_MAX_BREAK_MS = 500
_MAX_TAG_CHARS = 80
_ALLOWED_EMPHASIS = frozenset({"reduced", "moderate", "strong"})
_ALLOWED_RATE = frozenset({"slow", "medium", "fast", "x-slow", "x-fast"})


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

    if _has_emoji(stripped):
        issues.append(ValidationIssue("emoji", "emoji is not speakable"))
    if _URL.search(stripped):
        issues.append(ValidationIssue("url", "URLs are not speakable"))

    spoken = _plain_text(stripped)
    issues.extend(
        ValidationIssue(item.code, item.message)
        for item in validate_node_vocabulary(spoken, node.id)
    )
    if _MULTI_PUNCT.search(spoken):
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
    elif "&" in spoken and "&amp;" not in raw and "&lt;" not in raw:
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

    if _ADDRESS_EN.search(spoken) or _ADDRESS_CS.search(spoken):
        issues.append(
            ValidationIssue(
                "address_driver",
                "viewer third person only; do not address the featured driver as you/your",
            )
        )

    vocative = _VOCATIVE_SLOT.match(stripped)
    if vocative:
        slot_types = {slot.name: slot.type for slot in node.slots}
        if slot_types.get(vocative.group(1)) == "name":
            issues.append(
                ValidationIssue(
                    "vocative_opener",
                    "do not start with a name slot and a comma; talk about the driver, not to them",
                )
            )

    return issues


def estimate_seconds(spoken: str, *, ssml: str | None = None) -> float:
    """Rough spoken duration. Used for speak-lock, not a DSP measurement."""
    base = max(0.4, len(spoken) / _CHARS_PER_SECOND)
    extra = 0.0
    if ssml:
        for match in _BREAK_TIME.finditer(ssml):
            extra += int(match.group(1)) / 1000.0
        extra += 0.12 * ssml.lower().count("<break")
    return base + extra


def fill_slots(text: str, values: dict[str, object]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values or values[key] is None:
            return match.group(0)
        return str(values[key])

    return _SLOT.sub(repl, text)


def leftover_slots(text: str) -> list[str]:
    return _SLOT.findall(text)


def _is_ssml(text: str) -> bool:
    return "<" in text and ">" in text


def _has_emoji(text: str) -> bool:
    for char in text:
        code = ord(char)
        if 0x1F300 <= code <= 0x1FAFF or 0x2700 <= code <= 0x27BF or 0x1F000 <= code <= 0x1F0FF:
            return True
    return False


def _plain_text(text: str) -> str:
    if not _is_ssml(text):
        return text
    return " ".join(_strip_tags(text).split())


def _strip_tags(text: str) -> str:
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char != "<":
            out.append(char)
            index += 1
            continue
        end = text.find(">", index + 1)
        if end == -1 or (end - index) > _MAX_TAG_CHARS:
            out.append(char)
            index += 1
            continue
        if out and out[-1] != " ":
            out.append(" ")
        index = end + 1
    return "".join(out)


def _validate_ssml(text: str, tts: TtsLimits) -> list[ValidationIssue]:
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered or "<?xml" in lowered:
        return [ValidationIssue("ssml_parse", "SSML declarations are not allowed")]
    allowed = set(tts.ssml_allowed) | {"speak"}
    issues: list[ValidationIssue] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "<":
            index += 1
            continue
        end = text.find(">", index + 1)
        if end == -1 or (end - index) > _MAX_TAG_CHARS:
            issues.append(ValidationIssue("ssml_parse", "unclosed or oversized SSML tag"))
            break
        raw = text[index + 1 : end].strip()
        index = end + 1
        if raw.startswith("/"):
            name = raw[1:].split(None, 1)[0].lower() if raw[1:] else ""
            if name not in _ALLOWED_TAGS:
                issues.append(ValidationIssue("ssml_tag", f"unsupported SSML tag <{name}>"))
            continue
        name, attrs = _split_tag(raw)
        if name not in _ALLOWED_TAGS:
            issues.append(ValidationIssue("ssml_tag", f"unsupported SSML tag <{name}>"))
            continue
        if name not in allowed and name != "speak":
            issues.append(ValidationIssue("ssml_tag", f"tag <{name}> is not allowed on this node"))
        if name == "break":
            issues.extend(_check_break_attrs(attrs))
        if name == "emphasis":
            level = _attr(attrs, "level") or "moderate"
            if level.lower() not in _ALLOWED_EMPHASIS:
                issues.append(
                    ValidationIssue("ssml_emphasis", f"emphasis level {level!r} is not allowed")
                )
        if name == "prosody":
            issues.extend(_check_prosody_attrs(attrs, allowed))
    return issues


def _split_tag(raw: str) -> tuple[str, str]:
    body = raw[:-1].strip() if raw.endswith("/") else raw
    parts = body.split(None, 1)
    name = parts[0].lower() if parts else ""
    attrs = parts[1] if len(parts) > 1 else ""
    return name, attrs


def _attr(attrs: str, key: str) -> str | None:
    token = f'{key}="'
    start = attrs.lower().find(token)
    if start < 0:
        return None
    begin = start + len(token)
    end = attrs.find('"', begin)
    if end < 0:
        return None
    return attrs[begin:end]


def _check_break_attrs(attrs: str) -> list[ValidationIssue]:
    time_raw = _attr(attrs, "time")
    if not time_raw:
        return []
    value = time_raw.strip()
    # Linear check — avoid unbounded \d+ (CodeQL py/polynomial-redos).
    if not (value.endswith("ms") and value[:-2].isdigit()):
        return [ValidationIssue("ssml_break", "break time must look like 200ms")]
    if int(value[:-2]) > _MAX_BREAK_MS:
        return [
            ValidationIssue(
                "ssml_break",
                f"break {time_raw} exceeds {_MAX_BREAK_MS}ms (intonation stall)",
            )
        ]
    return []


def _check_prosody_attrs(attrs: str, allowed: Iterable[str]) -> list[ValidationIssue]:
    if "prosody" not in set(allowed):
        return [ValidationIssue("ssml_tag", "tag <prosody> is not allowed on this node")]
    issues: list[ValidationIssue] = []
    rate = _attr(attrs, "rate")
    if rate and rate.lower() not in _ALLOWED_RATE:
        issues.append(ValidationIssue("ssml_prosody", f"prosody rate {rate!r} is not allowed"))
    pitch = _attr(attrs, "pitch")
    if pitch and not re.fullmatch(r"[+-]?\d{1,2}%", pitch.strip()):
        issues.append(ValidationIssue("ssml_prosody", "prosody pitch must be like +5% or -8%"))
    return issues


def issues_as_codes(issues: list[ValidationIssue]) -> list[str]:
    return [item.code for item in issues]
