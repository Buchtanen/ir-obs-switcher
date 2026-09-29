"""Conservative, input-owned checks for experimental remote wording.

This is a bounded guard for known unsupported claims, not a general semantic
proof. Rejected candidates use the current bundle's authored fallback.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from irswitch.events.commentary_microplan import Microplan

_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
}
_ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
}
_CAUSAL_OR_UNSUPPORTED = re.compile(
    r"\b(?:because|due to|contact|collision|crash|spin|spun|running wide|ran wide|"
    r"damage|damaged|tyres?|tires?|fuel|penalty|penalties|strategy|retired|"
    r"briefly|momentarily|safely|leader|leading|leads|track record|world record|"
    r"overtak(?:e|es|ing|en)|passes|passed|moved up|moving up|gained places?|"
    r"lost places?|dropp(?:ed|ing) (?:to|back)|hunts? for (?:a |the )?(?:move|pass))\b",
    re.IGNORECASE,
)
_SECONDS = re.compile(r"\b(\d+(?:\.\d+)?|[a-z]+)(?:\s+|-)(?:seconds?|secs?)\b", re.I)
_POSITIONS = re.compile(r"\bP(\d{1,3})\b|\b(\d{1,3})(?:st|nd|rd|th)\b", re.I)
_ORDINALS = re.compile(r"\b(?:" + "|".join(_ORDINAL_WORDS) + r")\b", re.I)
_INCIDENT_POINTS = re.compile(
    r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r")\s+(?:more |additional )?incident points\b",
    re.I,
)
_INCIDENT_TOTAL = re.compile(
    r"\b(?:total|tally)\s+(?:is|to|of|now at|stands at)\s+(\d+|" + "|".join(_NUMBER_WORDS) + r")\b",
    re.I,
)
_LAP_TIMES = re.compile(r"\b\d{1,2}:\d{2}\.\d{3}\b")
_DIGITS = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
_COUNTED_INCIDENTS = re.compile(
    r"\b(?:\d+|"
    + "|".join(_NUMBER_WORDS)
    + r")\s+(?:new |separate |distinct )?incidents?\b(?!\s+points\b)",
    re.IGNORECASE,
)


def _number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        word = value.casefold()
        return float(_NUMBER_WORDS[word]) if word in _NUMBER_WORDS else None


def free_grounding_reasons(text: str, plan: Microplan) -> list[str]:
    """Check units, entities and known invented claim families against one plan."""
    fields = dict(plan.input_fields)
    reasons: list[str] = []
    if _CAUSAL_OR_UNSUPPORTED.search(text):
        reasons.append("unsupported_claim")
    state = fields.get("aftermath_state")
    if re.search(r"\b(?:stopped|stationary|stalled)\b", text, re.I) and state != "stopped":
        reasons.append("stop_unprovided")
    if (
        re.search(
            r"\b(?:back under\s?way|resumes? (?:driving|racing)|gets? going again)\b", text, re.I
        )
        and fields.get("previously_stopped") != 1
    ):
        reasons.append("recovery_unprovided")
    if re.search(r"\btow(?:ed|ing)?\b", text, re.I) and state != "towing":
        reasons.append("tow_unprovided")
    if (
        re.search(r"\bmandatory repairs?\b", text, re.I)
        and fields.get("mandatory_repair_required") != 1
    ):
        reasons.append("repair_unprovided")
    if (
        re.search(r"\boptional repairs?\b", text, re.I)
        and fields.get("optional_repair_required") != 1
    ):
        reasons.append("repair_unprovided")
    if re.search(r"\brepairs? (?:completed|finished)|\bfully repaired\b", text, re.I):
        reasons.append("repair_completion_unprovided")
    if _COUNTED_INCIDENTS.search(text):
        reasons.append("incident_points_as_events")

    seconds = [float(value) for key, value in fields.items() if key.endswith("_seconds")]
    for match in _SECONDS.finditer(text):
        number = _number(match.group(1))
        if number is None:
            continue
        tolerance = 0.51 if math.isclose(number, round(number)) else 0.051
        before = text[max(0, match.start() - 38) : match.start()].casefold()
        after = text[match.end() : match.end() + 20].casefold()
        if re.match(r"\s+(?:behind|ahead|back from)\b", after) or re.search(
            r"\bgap\s+(?:is|at|of|stands at|now)\s*$", before
        ):
            valid = [float(fields["gap_seconds"])] if "gap_seconds" in fields else []
        elif re.search(r"\b(?:decreased|reduced|closed|improved|widened|grew)\s+by\s*$", before):
            valid = [
                float(fields[key])
                for key in ("gap_reduction_seconds", "delta_to_best_seconds")
                if key in fields
            ]
        else:
            valid = seconds
        if not any(abs(number - float(allowed)) <= tolerance for allowed in valid):
            reasons.append("seconds_mismatch")
            break

    positions = {int(value) for key, value in fields.items() if key.endswith("_position")}
    for match in _POSITIONS.finditer(text):
        if int(match.group(1) or match.group(2)) not in positions:
            reasons.append("position_mismatch")
            break
    for match in _ORDINALS.finditer(text):
        before = text[max(0, match.start() - 18) : match.start()].casefold()
        after = text[match.end() : match.end() + 14].casefold()
        if re.match(r"\s+(?:lap|sector|time|race)\b", after):
            continue
        if re.match(r"\s+(?:place|position)\b", after) or re.search(
            r"\b(?:in|to|is|runs|sits|finishes|takes)\s*$", before
        ):
            if _ORDINAL_WORDS[match.group().casefold()] not in positions:
                reasons.append("position_mismatch")
                break

    for pattern, field in (
        (_INCIDENT_POINTS, "incident_points_added"),
        (_INCIDENT_TOTAL, "incident_points_total"),
    ):
        for match in pattern.finditer(text):
            number = _number(match.group(1))
            if number is not None and number != fields.get(field):
                reasons.append("incident_points_mismatch")
                break

    lap_times = {str(value) for key, value in fields.items() if key == "lap_time"}
    if any(time not in lap_times for time in _LAP_TIMES.findall(text)):
        reasons.append("lap_time_mismatch")

    # Unlabelled digits cannot introduce a new lap count, gap or incident count.
    without_times = _LAP_TIMES.sub("", text)
    allowed_numbers = [float(value) for value in fields.values() if isinstance(value, (int, float))]
    for match in _DIGITS.finditer(without_times):
        if not any(abs(float(match.group()) - value) <= 0.001 for value in allowed_numbers):
            reasons.append("number_unprovided")
            break

    subject_match = re.search(r"(?<!\w)" + re.escape(plan.subject) + r"(?!\w)", text, re.I)
    if subject_match is None:
        reasons.append("subject_missing")
    if plan.beat_id in {"HUNTING", "HUNTED", "APPROACH", "ATTACK_RANGE", "SIDE_BY_SIDE"}:
        target_match = None
        if len(plan.actors) < 2:
            reasons.append("actor_bindings")
        else:
            target = plan.actors[1][1]
            target_match = re.search(r"(?<!\w)" + re.escape(target) + r"(?!\w)", text, re.I)
            if target_match is None:
                reasons.append("target_missing")
            elif (
                subject_match is not None
                and plan.beat_id in {"HUNTING", "APPROACH", "ATTACK_RANGE"}
                and target_match.start() < subject_match.start()
            ):
                reasons.append("actor_order")
        if plan.beat_id in {"HUNTING", "APPROACH", "ATTACK_RANGE"} and re.search(
            r"\b(?:under pressure from|being chased by|pulling away from)\b", text, re.I
        ):
            reasons.append("trend_reversed")
        if (
            plan.beat_id == "HUNTED"
            and re.search(r"\b(?:closing on|catching|chasing|approaching)\b", text, re.I)
            and subject_match is not None
            and target_match is not None
            and subject_match.start() < target_match.start()
        ):
            reasons.append("trend_reversed")
    return list(dict.fromkeys(reasons))
