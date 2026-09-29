"""Current accepted facts → immutable M1 input and an independent speech grammar.

Only audited event families enter live speech. Other paraphrases can be examined
in shadow; a model's claimed fact IDs never authorize a sentence.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from irswitch.events.stream import (
    FrozenAcceptedEvent,
    FrozenAcceptedEventBatch,
    thaw_context,
    thaw_envelope,
)

M1_SYSTEM = (
    "Write a natural English motorsport commentary sentence for viewers. "
    "The application supplies exactly the current facts it wants expressed. "
    "Preserve their meaning and actor roles; you may reorder and paraphrase for clear spoken rhythm. "
    "Use specific information rather than generic drama. Include every provided fact except an optional "
    "position if it makes the line clumsy. Do not add facts or infer unprovided events. "
    "A car ahead is not necessarily the race leader. Do not turn a return to the circuit into a more "
    "specific driving state. No nationality, emotions or intentions are supplied. "
    "If speech_decision is skip, output action skip and no candidates. If speak, deliver the update. "
    "Normally 8-28 words, at most 200 characters, one sentence. "
    'Output JSON only: {"action":"speak" or "skip","used_fact_ids":[...],'
    '"candidates":[{"style_id":"natural","text":"..."}]}. '
    "used_fact_ids must refer to the supplied fact IDs. No explanations. "
    "Use only the supplied current facts. No previous commentary is needed."
)

M2_SYSTEM = (
    "You are an English motorsport commentator addressing stream viewers in the third person. "
    "Use only current supplied structured facts; previous commentary is memory, not evidence of current state. "
    "Keep actor roles, numbers, and units exact: position is a place, gap is time in seconds, "
    "incident points are not a count of separate incidents. "
    "Do not invent causes, overtakes, position changes, contact, damage, penalties, intentions, "
    "race leadership, pit service, duration, or predictions. Unknown is not false. "
    "Give one clear update that combines relevant supplied facts when useful. "
    "When a current fact supplies a measured change since the last spoken update, prefer that change "
    "over merely restating the current value. "
    "Avoid repeating already spoken meaning; if nothing material changed, choose skip. "
    "If valid_until_ms has passed, choose skip. One sentence, usually 8-28 words, at most 200 characters. "
    'Return JSON only with exactly {"action":"speak" or "skip","used_fact_ids":[...],'
    '"candidates":[{"style_id":"natural","text":"..."}]}. '
    "For skip, candidates and used_fact_ids are empty arrays. For speak, use one candidate and "
    "only IDs of supplied current facts; a cited ID is not permission to invent details."
)


def digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Microplan:
    event_id: str
    beat_id: str
    revision: int
    session_id: str
    correlation_id: str
    expires_ms: int
    subject: str
    actors: tuple[tuple[str, str], ...]
    facts: tuple[tuple[str, str], ...]
    allowed: tuple[str, ...]
    input_fields: tuple[tuple[str, str | int | float], ...] = ()

    @property
    def digest(self) -> str:
        return digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "beat_id": self.beat_id,
            "revision": self.revision,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "expires_ms": self.expires_ms,
            "subject": self.subject,
            "actors": [list(x) for x in self.actors],
            "facts": [list(x) for x in self.facts],
            "allowed": list(self.allowed),
            "input_fields": [list(x) for x in self.input_fields],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Microplan:
        return cls(
            **{
                **data,
                "actors": tuple(tuple(x) for x in data["actors"]),
                "facts": tuple(tuple(x) for x in data["facts"]),
                "allowed": tuple(data["allowed"]),
                "input_fields": tuple(tuple(x) for x in data.get("input_fields", ())),
            }
        )

    def prompt_json(
        self, *, now_ms: int | None = None, recent_commentary: tuple[dict[str, object], ...] = ()
    ) -> str:
        fields = dict(self.input_fields)
        separate = {"gap_seconds", "gap_reduction_seconds", "delta_to_best_seconds"}
        primary = {k: v for k, v in fields.items() if k not in separate}
        facts = []
        for index, (key, text) in enumerate(self.facts):
            if index == 0:
                item_fields = primary
            elif index == 1:
                item_fields = {
                    k: fields[k] for k in ("gap_seconds", "delta_to_best_seconds") if k in fields
                }
            elif index == 2 and "gap_reduction_seconds" in fields:
                item_fields = {"gap_reduction_seconds": fields["gap_reduction_seconds"]}
            else:
                item_fields = {}
            facts.append({"id": key, "claim": text, "fields": item_fields})
        return json.dumps(
            {
                "speech_decision": "speak",
                "now_ms": now_ms,
                "valid_until_ms": self.expires_ms,
                "event_type": self.beat_id,
                "featured_driver": self.subject,
                "facts": facts,
                "recent_commentary": recent_commentary,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def accepts(self, text: str) -> bool:
        # Whole-sentence membership: extra clauses, role reversal, altered numbers,
        # inferred overtakes and negations cannot sneak past substring checks.
        return " ".join(text.split()).casefold() in {x.casefold() for x in self.allowed}

    def verify_payload(self) -> dict[str, Any]:
        """Input-owned semantic authority frozen on dispatch, before model IO."""
        return {
            "verifyFamily": self.beat_id,
            "verifySubjectSurface": self.subject,
            "verifyRequiredClaimSurface": self.allowed[0][len(self.subject) + 1 :].rstrip("."),
            "verifyActorBindings": [[key, [name]] for key, name in self.actors],
            "verifyRequiredActors": [key for key, _ in self.actors],
            "verifyAllowedSentences": list(self.allowed),
        }


def _name(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    name = " ".join(raw.split())
    if not 1 <= len(name) <= 48 or not all(c.isalpha() or c in " '-" for c in name):
        return None
    return name


def _positive(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    return value if math.isfinite(value) and 0 < value < 3600 else None


def _place(raw: object) -> int | None:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and 1 <= raw <= 200 else None


def _incident_points(raw: object) -> int | None:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and 1 <= raw <= 1000 else None


def _spoken_number(value: int) -> str:
    small = (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    )
    if value < 20:
        return small[value]
    tens = ("", "", "twenty", "thirty", "forty", "fifty")
    whole, rem = divmod(value, 10)
    return tens[whole] + ("-" + small[rem] if rem else "")


def plan_from_accepted(
    accepted: FrozenAcceptedEvent, batch: FrozenAcceptedEventBatch
) -> Microplan | None:
    """Project explicitly mapped source facts, never overlay copy or raw event JSON.

    TTL is five seconds from the event's original timestamp (not receipt time).
    Missing names/timing/direction and unsupported families fail closed.
    """
    envelope = thaw_envelope(accepted.envelope)
    if envelope.phase in {"EXIT", "CANCEL"}:
        return None
    context = thaw_context(batch.context_payload)
    subject = _name(envelope.subject.display_name)
    hero = context.get("story", {}).get("hero", {})
    is_hero = envelope.subject.car_id == "player" or (
        hero.get("car_idx") is not None and envelope.subject.car_id == str(hero["car_idx"])
    )
    if subject is None and is_hero:
        names = hero.get("speakable_names", [])
        subject = next((value for raw in names if (value := _name(raw))), None)
        subject = subject or _name(hero.get("display_name"))
    if envelope.event_type == "SESSION_FLAG":
        subject = "Race control"
    if subject is None:
        # Named subject is mandatory; never substitute a fixture or guess roster.
        return None
    target = _name(envelope.target.display_name) if envelope.target else None
    target = target or _name(envelope.metrics.get("targetName"))
    kind = envelope.event_type
    metrics = envelope.metrics
    claims: tuple[str, ...]
    if kind in {"PERSONAL_BEST", "LAP_COMPLETE"}:
        lap_time = _positive(metrics.get("lapTime"))
        if lap_time is None:
            return None
        milliseconds = round(lap_time * 1000)
        minutes, rem = divmod(milliseconds, 60_000)
        lap = f"{minutes}:{rem / 1000:06.3f}"
        if kind == "PERSONAL_BEST":
            claims = (
                f"sets a personal best of {lap}",
                f"posts a personal best of {lap}",
                f"sets a new personal best of {lap}",
                f"records a personal best of {lap}",
            )
        else:
            claims = tuple(
                f"{verb} {article} lap {timing} {lap}"
                for verb in ("completes", "has completed")
                for article in ("a", "the")
                for timing in ("in", "with a time of")
            ) + (
                f"posts a lap of {lap}",
                f"clocks a lap of {lap}",
            )
    elif kind in {"HUNTING", "HUNTED", "SIDE_BY_SIDE", "ATTACK_RANGE", "APPROACH"}:
        if target is None or subject.casefold() == target.casefold():
            return None
        direction = metrics.get("direction")
        if kind == "HUNTING" and direction == "front":
            claims = (
                f"is closing on {target}",
                f"closes in on {target}",
                f"is closing the gap to {target}",
            )
        elif kind == "HUNTED" and direction == "rear":
            claims = (f"is under pressure from {target}", f"faces pressure from {target}")
        elif kind == "SIDE_BY_SIDE":
            claims = (
                f"is side by side with {target}",
                f"runs alongside {target}",
                f"is running side by side with {target}",
                f"runs side by side with {target}",
                f"is alongside {target}",
            )
        elif kind == "ATTACK_RANGE" and direction == "front":
            claims = (
                f"is within attacking range of {target}",
                f"is in attacking range of {target}",
            )
        elif kind == "APPROACH" and direction == "front":
            claims = (f"is approaching {target}", f"is getting closer to {target}")
        else:
            return None
    elif kind in {"POSITION_GAINED", "POSITION_LOST"}:
        old_position = _place(metrics.get("oldPosition"))
        new_position = _place(metrics.get("newPosition"))
        if old_position is None or new_position is None:
            return None
        if metrics.get("direction") != ("gain" if kind == "POSITION_GAINED" else "loss"):
            return None
        if kind == "POSITION_GAINED" and new_position >= old_position:
            return None
        if kind == "POSITION_LOST" and new_position <= old_position:
            return None
        claims = (f"moves from P{old_position} to P{new_position}",)
    elif kind == "FINISH":
        position = _place(metrics.get("position")) or _place(metrics.get("classPosition"))
        if position is None:
            return None
        claims = (f"finishes in P{position}",)
    elif kind == "FINAL_LAP":
        lap_number = metrics.get("lap")
        if (
            isinstance(lap_number, bool)
            or not isinstance(lap_number, int)
            or not 1 <= lap_number <= 10000
        ):
            return None
        claims = ("starts the final lap",)
    elif kind == "FIELD_FACT":
        position = _place(metrics.get("position"))
        if metrics.get("fact") != "position" or position is None:
            return None
        lap_number = metrics.get("lap")
        if (
            isinstance(lap_number, bool)
            or not isinstance(lap_number, int)
            or not 1 <= lap_number <= 10000
        ):
            lap_number = None
        claims = (
            (
                f"is running in P{position} on lap {lap_number}"
                if lap_number is not None
                else f"is running in P{position}"
            ),
        )
    elif kind == "BACK_UNDER_WAY":
        if metrics.get("kind") != "back_under_way":
            return None
        claims = ("is back under way",)
    elif kind == "INCIDENT_AFTERMATH":
        aftermath = metrics.get("kind")
        if aftermath == "rolling":
            claims = ("is moving after the incident",)
        else:
            # "stalled" can mean off-track or a pending tow; neither proves
            # that the car has stopped or been towed.
            return None
    elif kind == "SESSION_FLAG":
        flag = metrics.get("kind")
        if flag not in {"yellow", "green", "checkered"}:
            return None
        subject = "Race control"
        claims = (f"shows the {flag} flag",)
    elif kind == "INCIDENT":
        points = _incident_points(metrics.get("value"))
        total = _incident_points(metrics.get("total"))
        if points is None or total is None or points > total:
            return None
        claims = (f"has gained {points} incident points, bringing the total to {total}",)
    elif kind in {"PIT_ENTRY", "PIT_EXIT"}:
        position_key = "entryPosition" if kind == "PIT_ENTRY" else "exitPosition"
        position = _place(metrics.get(position_key))
        action = "enters" if kind == "PIT_ENTRY" else "exits"
        direction = "from" if kind == "PIT_ENTRY" else "in"
        claims = (
            (
                f"{action} the pit lane {direction} P{position}"
                if position is not None
                else f"{action} the pit lane"
            ),
        )
    else:
        return None
    allowed = tuple(f"{subject} {claim}." for claim in claims)
    fact_texts = [allowed[0]]
    input_fields: list[tuple[str, str | int | float]] = []
    if kind in {"PERSONAL_BEST", "LAP_COMPLETE"}:
        input_fields.append(("lap_time", lap))
    if kind == "LAP_COMPLETE":
        best_lap = _positive(metrics.get("bestLap"))
        raw_delta = metrics.get("deltaToBest")
        delta = (
            float(raw_delta)
            if isinstance(raw_delta, (int, float))
            and not isinstance(raw_delta, bool)
            and math.isfinite(raw_delta)
            else None
        )
        if (
            lap_time is not None
            and best_lap is not None
            and delta is not None
            and abs(delta) > 0.0005
            and abs((lap_time - best_lap) - delta) <= 0.015
        ):
            delta_ms = round(abs(delta) * 1000)
            input_fields.append(("delta_to_best_seconds", delta_ms / 1000))
            comparison = "slower" if delta > 0 else "quicker"
            fact_texts.append(
                f"That lap is {delta_ms / 1000:.3f} seconds {comparison} than {subject}'s previous best lap."
            )
    if kind in {"POSITION_GAINED", "POSITION_LOST"}:
        input_fields.extend((("old_position", old_position), ("new_position", new_position)))
    if kind == "FINISH":
        input_fields.append(("finish_position", position))
    if kind == "FINAL_LAP":
        input_fields.append(("lap_number", lap_number))
    if kind == "FIELD_FACT":
        input_fields.append(("current_position", position))
        if lap_number is not None:
            input_fields.append(("lap_number", lap_number))
    if kind == "INCIDENT":
        assert points is not None and total is not None
        input_fields.extend((("incident_points_added", points), ("incident_points_total", total)))
    if kind in {"PIT_ENTRY", "PIT_EXIT"} and position is not None:
        input_fields.append(
            ("entry_position" if kind == "PIT_ENTRY" else "exit_position", position)
        )
    if kind == "PERSONAL_BEST":
        allowed += tuple(
            f"{subject} {verb} a {new}personal best{noun} of {lap}."
            for verb in ("sets", "posts", "records")
            for new in ("", "new ")
            for noun in (" lap time", " time", " lap")
        )
        allowed += tuple(
            f"{subject} {verb} {lap} {ending}."
            for verb in ("clocks", "posts", "records")
            for ending in ("for a personal best", "for a new personal best")
        )
        allowed += (
            f"A new personal best for {subject} at {lap}.",
            f"A personal best for {subject} with a {lap} lap.",
            f"{subject}'s new personal best is {lap}.",
            f"{subject} sets a new personal best with a {lap} lap.",
            f"{subject} posts a {lap} lap for a new personal best.",
        )
    if kind in {"PERSONAL_BEST", "LAP_COMPLETE"}:
        seconds, fraction = divmod(rem, 1000)
        spoken_lap = (
            (f"{_spoken_number(minutes)} minute" + ("s" if minutes != 1 else "") + ", ")
            if minutes
            else ""
        )
        spoken_lap += (
            _spoken_number(seconds)
            + " point "
            + " ".join(_spoken_number(int(digit)) for digit in f"{fraction:03d}")
        )
        allowed += tuple(text.replace(lap, spoken_lap) for text in allowed)
    gap = _positive(metrics.get("gap"))
    if kind == "HUNTING" and gap is not None:
        gap_text = f"{gap:.3f}".rstrip("0").rstrip(".")
        input_fields.append(("gap_seconds", gap))
        fact_texts.append(f"The gap from {subject} to {target} ahead is {gap_text} seconds.")
        allowed = tuple(f"{subject} {claim}, with a gap of {gap_text} seconds." for claim in claims)
        allowed += tuple(
            f"{subject} is {qualifier}{gap_text} seconds behind {target} and closing."
            for qualifier in ("", "just ", "now ", "now just ")
        )
        allowed += (
            f"{subject} is closing on {target}, now {gap_text} seconds behind.",
            f"{subject} closes to within {gap_text} seconds of {target}.",
        )
        allowed += tuple(
            f"{subject} {claim}{ahead}, {qualifier}{gap_text} seconds behind."
            for claim in claims
            for ahead in ("", " ahead")
            for qualifier in ("", "just ", "now ", "now just ")
        )
        allowed += tuple(
            f"{subject} {claim}{ahead}, with the gap {qualifier}{gap_text} seconds."
            for claim in claims
            for ahead in ("", " ahead")
            for qualifier in ("at ", "now ", "now just ")
        )
    if len(allowed[0]) > 200:
        return None
    if kind == "SIDE_BY_SIDE":
        allowed += tuple(
            text.replace(f"{subject} is ", f"{subject} is currently ")
            for text in allowed
            if text.startswith(f"{subject} is ")
        )
    allowed = tuple(dict.fromkeys(text for text in allowed if len(text) <= 200))
    actors: tuple[tuple[str, str], ...] = (
        (("race_control", subject),)
        if kind == "SESSION_FLAG"
        else ((envelope.subject.car_id, subject),)
    )
    if target is not None and kind not in {"PERSONAL_BEST", "LAP_COMPLETE"}:
        target_id = envelope.target.car_id if envelope.target else "target"
        if target_id == envelope.subject.car_id:
            return None
        actors += ((target_id, target),)
    return Microplan(
        event_id=accepted.event_id,
        beat_id=kind,
        revision=accepted.sequence,
        session_id=batch.session_id,
        correlation_id=envelope.correlation_id or accepted.event_id,
        expires_ms=int(envelope.monotonic_ms) + 5000,
        subject=subject,
        actors=actors,
        facts=tuple(
            (f"{accepted.event_id}:claim:{index}", text) for index, text in enumerate(fact_texts)
        ),
        allowed=allowed,
        input_fields=tuple(input_fields),
    )
