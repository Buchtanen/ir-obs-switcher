"""Spoken vocabulary policy keyed by the fact being narrated."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class SemanticCategory(StrEnum):
    INCIDENT_POINTS_UPDATE = "incident_points_update"
    TRACK_EXCURSION = "track_excursion"
    LOSS_OF_CONTROL = "loss_of_control"
    SLIDE = "slide"
    SPIN = "spin"
    CONTACT_VEHICLE = "contact_vehicle"
    CONTACT_BARRIER = "contact_barrier"
    BRAKING_OVERSHOOT = "braking_overshoot"
    AVOIDANCE_MANEUVER = "avoidance_maneuver"
    STOPPED_AFTER_EXCURSION = "stopped_after_excursion"
    TRACK_REJOINED = "track_rejoined"
    CONTROL_REGAINED = "control_regained"
    NORMAL_RUNNING_RESUMED = "normal_running_resumed"
    PACE_LOSS_SUSTAINED = "pace_loss_sustained"
    LIMPING_TO_PITS = "limping_to_pits"
    PIT_FOR_REPAIRS = "pit_for_repairs"
    TOW_STARTED_RACE = "tow_started_race"
    RESET_TO_PITS = "reset_to_pits"
    RUN_CONTINUATION_LOST = "run_continuation_lost"
    OTHER = "other"


@dataclass(frozen=True)
class VocabularyViolation:
    code: str
    message: str
    token: str
    start: int
    end: int


class VocabularyPolicyError(ValueError):
    def __init__(
        self,
        category: SemanticCategory,
        violations: tuple[VocabularyViolation, ...],
    ) -> None:
        self.category = category
        self.violations = violations
        super().__init__(
            f"semantic vocabulary rejected for {category.value}: "
            + ", ".join(item.token for item in violations)
        )


# Exact English word/plural plus Czech inflections used for the same noun.
# Deliberately does not match unrelated words such as "incidental".
_INCIDENT_WORD = re.compile(
    r"(?<!\w)incident(?:ech|ům|em|ů|u|y|e|s|ní\w*)?(?!\w)",
    re.IGNORECASE | re.UNICODE,
)


def validate_semantic_vocabulary(
    text: str,
    category: SemanticCategory,
) -> tuple[VocabularyViolation, ...]:
    """Return deterministic violations for one semantic commentary category."""
    if not isinstance(category, SemanticCategory):
        raise ValueError("category must be a SemanticCategory")
    if category is SemanticCategory.INCIDENT_POINTS_UPDATE:
        return ()
    raw = text if isinstance(text, str) else ""
    return tuple(
        VocabularyViolation(
            code="incident_vocabulary_forbidden",
            message=(
                "physical driving facts must use their specific off-track, contact, "
                "control, or outcome vocabulary"
            ),
            token=match.group(0),
            start=match.start(),
            end=match.end(),
        )
        for match in _INCIDENT_WORD.finditer(raw)
    )


def require_semantic_vocabulary(text: str, category: SemanticCategory) -> None:
    """Raise a typed error when semantic vocabulary is not speakable."""
    violations = validate_semantic_vocabulary(text, category)
    if violations:
        raise VocabularyPolicyError(category, violations)


CURRENT_SIGNAL_NODES = frozenset(
    {
        "track_excursion",
        "stopped_after_excursion",
        "track_rejoined",
        "motion_restored",
        "tow_started_race",
        "pit_return_observed",
    }
)
_OFFTRACK = re.compile(
    r"off[ -]?(?:the[ -]?)?track|left the track|track limits|mimo trať|opustil\w* trať|limit\w* trati",
    re.I,
)
_UNPROVEN = re.compile(
    r"\b(?:contact\w*|collis\w*|crash\w*|spun|spin\w*|slid\w*|skid\w*|damag\w*|repair\w*|"
    r"kontakt\w*|koliz\w*|náraz\w*|smyk\w*|hodiny|poškoz\w*|oprav\w*|ovlád\w*)\b|"
    r"(?:lost|regain\w*) control|normal (?:pace|speed)|pod kontrolou|běžn\w* tempo",
    re.I,
)


def validate_node_vocabulary(text: str, node_id: str) -> tuple[VocabularyViolation, ...]:
    """Same policy for authored, composed, polished and final synthesized text."""
    category = (
        SemanticCategory.INCIDENT_POINTS_UPDATE
        if node_id in {"incident", "incident_unknown"}
        else SemanticCategory.OTHER
    )
    out = list(validate_semantic_vocabulary(text, category))
    if node_id in {"track_excursion", "incident_off_track"} and not _OFFTRACK.search(text):
        out.append(
            VocabularyViolation(
                "offtrack_wording_required", "Name the confirmed off-track", "", 0, 0
            )
        )
    if node_id in CURRENT_SIGNAL_NODES:
        for match in _UNPROVEN.finditer(text):
            out.append(
                VocabularyViolation(
                    "unproven_excursion_claim",
                    "Cause, control and damage remain unknown",
                    match.group(),
                    match.start(),
                    match.end(),
                )
            )
    return tuple(out)
