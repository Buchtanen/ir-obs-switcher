"""#274 race-outcome verifier minimal pairs (Slice 4).

Branch inventory of accept/reject EN utterances for each creatable
race-outcome family. Exercises ``SemanticVerifier`` polarity/actor axes
without rewriting frozen ``docs/v2.0.0/machine/*`` corpora or flipping
``FAMILY_ROUTE``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .primitives import ContractViolation
from .race_outcome_family_map import RACE_OUTCOME_WIRE_IDS, row_for_wire_id


@dataclass(frozen=True, slots=True)
class RaceOutcomeVerifierPair:
    """One accept/reject utterance bound to a race-outcome wire id."""

    wire_id: str
    pair_id: str
    family: str
    text: str
    subject_surface: str
    required_claim_surface: str
    expect_accepted: bool
    expect_reasons: tuple[str, ...]
    notes: str = ""


# Subject/target fixtures reused across pairs (not live telemetry).
_SUBJECT = "Alex"
_TARGET = "Morgan"
_OLD_LEADER = "Morgan"
_NEW_LEADER = "Alex"


def _utter(subject: str, claim: str, *, style: str = "plain") -> str:
    if style == "plain":
        return f"{subject} {claim}."
    if style == "now_mid":
        return f"{subject} now {claim}."
    if style == "now_lead":
        return f"Now {subject} {claim}."
    if style == "now_trail":
        return f"{subject} {claim} now."
    raise ContractViolation(f"unknown utterance style: {style}")


def race_outcome_verifier_pairs() -> tuple[RaceOutcomeVerifierPair, ...]:
    """Return the closed minimal-pair inventory for creatable race-outcome wires."""

    pairs: list[RaceOutcomeVerifierPair] = []
    for wire_id in RACE_OUTCOME_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        if not row.can_create:
            continue
        assert row.realization_family is not None
        family = row.realization_family

        if wire_id == "OVERTAKE":
            claim = f"passes {_TARGET}"
            reverse_claim = f"is passed by {_TARGET}"
            pairs.extend(
                [
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:positive",
                        family=family,
                        text=_utter(_SUBJECT, claim),
                        subject_surface=_SUBJECT,
                        required_claim_surface=claim,
                        expect_accepted=True,
                        expect_reasons=(),
                        notes="Passer→passed order.",
                    ),
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:actor_reversed",
                        family=family,
                        text=_utter(_TARGET, f"passes {_SUBJECT}"),
                        subject_surface=_SUBJECT,
                        required_claim_surface=claim,
                        expect_accepted=False,
                        expect_reasons=("actor_reversed",),
                        notes="Swap passer/passed must not both accept.",
                    ),
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:polarity_inverted",
                        family=family,
                        text=_utter(_SUBJECT, reverse_claim),
                        subject_surface=_SUBJECT,
                        required_claim_surface=claim,
                        expect_accepted=False,
                        expect_reasons=("required_missing",),
                        notes="Inverted pass polarity is not the required claim.",
                    ),
                ]
            )
        elif wire_id == "POSITION_GAINED":
            claim = "gains P3"
            loss_claim = "drops to P5"
            pairs.extend(
                [
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:positive",
                        family=family,
                        text=_utter(_SUBJECT, claim),
                        subject_surface=_SUBJECT,
                        required_claim_surface=claim,
                        expect_accepted=True,
                        expect_reasons=(),
                    ),
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:loss_polarity",
                        family=family,
                        text=_utter(_SUBJECT, loss_claim),
                        subject_surface=_SUBJECT,
                        required_claim_surface=claim,
                        expect_accepted=False,
                        expect_reasons=("required_missing",),
                        notes="Loss wording must not satisfy a gain frame.",
                    ),
                ]
            )
        elif wire_id == "POSITION_LOST":
            claim = "drops to P5"
            gain_claim = "gains P3"
            pairs.extend(
                [
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:positive",
                        family=family,
                        text=_utter(_SUBJECT, claim),
                        subject_surface=_SUBJECT,
                        required_claim_surface=claim,
                        expect_accepted=True,
                        expect_reasons=(),
                    ),
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:gain_polarity",
                        family=family,
                        text=_utter(_SUBJECT, gain_claim),
                        subject_surface=_SUBJECT,
                        required_claim_surface=claim,
                        expect_accepted=False,
                        expect_reasons=("required_missing",),
                        notes="Gain wording must not satisfy a loss frame.",
                    ),
                ]
            )
        elif wire_id == "LEADER_CHANGE":
            claim = f"takes the lead from {_OLD_LEADER}"
            pairs.extend(
                [
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:positive",
                        family=family,
                        text=_utter(_NEW_LEADER, claim),
                        subject_surface=_NEW_LEADER,
                        required_claim_surface=claim,
                        expect_accepted=True,
                        expect_reasons=(),
                    ),
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:actor_reversed",
                        family=family,
                        text=_utter(_OLD_LEADER, claim),
                        subject_surface=_NEW_LEADER,
                        required_claim_surface=claim,
                        expect_accepted=False,
                        expect_reasons=("actor_reversed",),
                    ),
                ]
            )
        elif wire_id == "FINISH":
            claim = "finishes P3"
            pairs.extend(
                [
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:positive",
                        family=family,
                        text=_utter(_SUBJECT, claim),
                        subject_surface=_SUBJECT,
                        required_claim_surface=claim,
                        expect_accepted=True,
                        expect_reasons=(),
                    ),
                    RaceOutcomeVerifierPair(
                        wire_id=wire_id,
                        pair_id=f"{wire_id}:polarity_negated",
                        family=family,
                        text=f"It is not true that {_SUBJECT} {claim}.",
                        subject_surface=_SUBJECT,
                        required_claim_surface=claim,
                        expect_accepted=False,
                        expect_reasons=("unsafe_negation", "polarity_mismatch"),
                    ),
                ]
            )
        else:
            raise ContractViolation(f"missing verifier pairs for {wire_id}")

    return tuple(pairs)


def pairs_for_wire_id(wire_id: str) -> tuple[RaceOutcomeVerifierPair, ...]:
    """Return minimal pairs for one wire id (empty for the non-creatable alias)."""

    row = row_for_wire_id(wire_id)
    if not row.can_create:
        return ()
    found = tuple(pair for pair in race_outcome_verifier_pairs() if pair.wire_id == wire_id)
    if not found:
        raise ContractViolation(f"missing verifier pairs for {wire_id}")
    return found


def positive_pair_for_wire_id(wire_id: str) -> RaceOutcomeVerifierPair:
    """Return the required positive pair for a creatable wire."""

    for pair in pairs_for_wire_id(wire_id):
        if pair.expect_accepted:
            return pair
    raise ContractViolation(f"missing positive verifier pair for {wire_id}")
