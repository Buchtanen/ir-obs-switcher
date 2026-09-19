"""#274 slice 4: race-outcome verifier minimal pairs."""

from __future__ import annotations

from irswitch.contracts.race_outcome_family_map import RACE_OUTCOME_WIRE_IDS, row_for_wire_id
from irswitch.contracts.race_outcome_verifier_pairs import (
    pairs_for_wire_id,
    positive_pair_for_wire_id,
    race_outcome_verifier_pairs,
)
from irswitch.events.semantic_verifier import SemanticVerifier, VerifyIntent


def _intent_from_pair(pair) -> VerifyIntent:
    return VerifyIntent(
        text=pair.text,
        family=pair.family,
        subject_surface=pair.subject_surface,
        required_claim_surface=pair.required_claim_surface,
        actor_bindings=(("hero", (pair.subject_surface,)),),
        required_actors=frozenset({"hero"}),
        now_ms=10_000,
        deadline_mono_ms=20_000,
    )


def test_every_creatable_family_has_positive_and_reject_pair() -> None:
    by_wire: dict[str, list] = {}
    for pair in race_outcome_verifier_pairs():
        by_wire.setdefault(pair.wire_id, []).append(pair)

    for wire_id in RACE_OUTCOME_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        if not row.can_create:
            assert pairs_for_wire_id(wire_id) == ()
            assert wire_id not in by_wire
            continue
        pairs = by_wire[wire_id]
        assert any(p.expect_accepted for p in pairs)
        assert any(not p.expect_accepted for p in pairs)
        assert all(p.family == row.realization_family for p in pairs)


def test_semantic_verifier_matches_race_outcome_minimal_pairs() -> None:
    verifier = SemanticVerifier()
    for pair in race_outcome_verifier_pairs():
        step = verifier.verify(_intent_from_pair(pair))
        assert step.outcome == "succeeded", pair.pair_id
        assert step.result is not None
        assert step.result.accepted is pair.expect_accepted, (pair.pair_id, step.result.reasons)
        assert tuple(step.result.reasons) == pair.expect_reasons, (
            pair.pair_id,
            step.result.reasons,
        )


def test_gain_and_loss_positive_pairs_cannot_both_pass_swapped() -> None:
    verifier = SemanticVerifier()
    gained = positive_pair_for_wire_id("POSITION_GAINED")
    lost = positive_pair_for_wire_id("POSITION_LOST")

    gain_as_loss = VerifyIntent(
        text=gained.text,
        family=lost.family,
        subject_surface=lost.subject_surface,
        required_claim_surface=lost.required_claim_surface,
        actor_bindings=(("hero", (lost.subject_surface,)),),
        required_actors=frozenset({"hero"}),
        now_ms=10_000,
        deadline_mono_ms=20_000,
    )
    loss_as_gain = VerifyIntent(
        text=lost.text,
        family=gained.family,
        subject_surface=gained.subject_surface,
        required_claim_surface=gained.required_claim_surface,
        actor_bindings=(("hero", (gained.subject_surface,)),),
        required_actors=frozenset({"hero"}),
        now_ms=10_000,
        deadline_mono_ms=20_000,
    )
    gain_ok = verifier.verify(_intent_from_pair(gained))
    loss_ok = verifier.verify(_intent_from_pair(lost))
    swapped_a = verifier.verify(gain_as_loss)
    swapped_b = verifier.verify(loss_as_gain)

    assert gain_ok.result and gain_ok.result.accepted
    assert loss_ok.result and loss_ok.result.accepted
    assert swapped_a.result and swapped_a.result.accepted is False
    assert swapped_b.result and swapped_b.result.accepted is False
    assert not (swapped_a.result.accepted and swapped_b.result.accepted)


def test_pass_forward_and_reverse_cannot_both_accept() -> None:
    verifier = SemanticVerifier()
    pairs = {p.pair_id: p for p in pairs_for_wire_id("OVERTAKE")}
    forward = verifier.verify(_intent_from_pair(pairs["OVERTAKE:positive"]))
    reverse = verifier.verify(_intent_from_pair(pairs["OVERTAKE:actor_reversed"]))
    assert forward.result and forward.result.accepted
    assert reverse.result and reverse.result.accepted is False
    assert "actor_reversed" in reverse.result.reasons
