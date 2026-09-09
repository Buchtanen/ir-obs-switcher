"""#267 authored critical/lifecycle pack and bundle-only realizer."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.contracts import load_authored_pack, load_narrative_catalog
from irswitch.contracts.authored_pack import (
    SCHEMA_VERSION,
    AuthoredRealizer,
    authored_bundle,
    render_surface_forms,
)
from irswitch.events import __all__ as events_exports

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "irswitch" / "contracts" / "authored_pack.py"
FIXTURES = ROOT / "tests" / "fixtures" / "authored_pack"
UNSAFE = (
    "because",
    "caused",
    "stunning",
    "brilliant",
    "probably",
    "will win",
    "looking",
)


def _lexicon(
    *,
    subject: str = "The stream",
    claim: str = "is live",
    fact_id: str = "fact:stream-1",
    claim_id: str = "stream.started",
    number: tuple[str, ...] = (),
) -> dict[str, object]:
    sets = []
    if number:
        sets.append(
            {
                "surfaceValueSetId": "svs:1",
                "factId": fact_id,
                "attributeId": "lap",
                "valueType": "int",
                "unit": None,
                "forms": list(number),
            }
        )
    return {
        "surfaceValueSets": sets,
        "relationLexemes": [
            {
                "claimId": claim_id,
                "polarity": "positive",
                "temporalFrame": "current",
                "forms": [claim],
            }
        ],
        "connectives": ["now"],
        "forbiddenLexemes": ["because", "probably", "stunning"],
        "subjectSurface": subject,
        "subjectActorId": "stream",
    }


def _bundle(**overrides: object):
    values: dict[str, object] = {
        "beat_id": "stream.started",
        "backend": "authored",
        "pattern_id": "stream.started:tight:1",
        "max_chars": 160,
        "max_seconds": 13.0,
        "required_claim_ids": ("stream.started",),
        "selected_fact_ids": ("fact:stream-1",),
        "planned_mono_ms": 10_000,
        "expires_mono_ms": 20_000,
        "language": "en",
        "actor_bindings": (("stream", ("The stream", "the broadcast")),),
        "fact_bindings": (("fact:stream-1", "stream.started"),),
        "lexicon": _lexicon(),
    }
    values.update(overrides)
    return authored_bundle(**values)  # type: ignore[arg-type]


def test_pack_selects_all_authored_critical_and_lifecycle_beats() -> None:
    pack = load_authored_pack()
    catalog = load_narrative_catalog().require_catalog()
    authored_ids = tuple(
        beat.id for beat in catalog.beats if beat.realization.backend == "authored"
    )

    assert pack.schema_version == SCHEMA_VERSION == "authored-pack/2"
    assert pack.beat_count == 33
    assert pack.line_count == 132
    assert pack.beat_ids == authored_ids
    assert all(
        beat.id not in pack.beat_ids
        for beat in catalog.beats
        if beat.realization.backend != "authored"
    )
    for beat_id in authored_ids:
        lines = pack.lines_for(beat_id)
        assert len(lines) == 4
        assert {line.pattern_id for line in lines} == {
            f"{beat_id}:tight:{index}" for index in (1, 2, 3, 4)
        }


def test_each_authored_line_is_fact_complete_and_self_contained() -> None:
    pack = load_authored_pack()
    catalog = load_narrative_catalog().require_catalog()
    for line in pack.lines:
        beat = catalog.beat(line.beat_id)
        assert line.required_claims == tuple(claim.id for claim in beat.claims)
        assert "subjectSurface" in line.placeholders
        assert "requiredClaimSurface" in line.placeholders
        assert line.pattern.endswith(".")
        lowered = line.pattern.casefold()
        assert all(token not in lowered for token in UNSAFE)


def test_authored_mode_is_chosen_before_generation_never_as_fallback() -> None:
    realizer = AuthoredRealizer()
    qwen = realizer.realize(_bundle(backend="qwen_compiled"), now_ms=10_000)
    fallback = realizer.realize(
        _bundle(backend="qwen_compiled"),
        now_ms=10_000,
        fallback=True,
    )
    authored = realizer.realize(_bundle(), now_ms=10_000)

    assert qwen.outcome == "failed"
    assert qwen.reason == "authored_backend_required"
    assert qwen.text is None
    assert fallback.reason == "authored_fallback_forbidden"
    assert authored.outcome == "succeeded"
    assert authored.backend == "authored"


def test_realizer_consumes_only_the_bundle_surfaces() -> None:
    step = AuthoredRealizer().realize(_bundle(), now_ms=10_400)
    missing = AuthoredRealizer().realize(
        _bundle(lexicon=_lexicon(claim="")),
        now_ms=10_000,
    )

    assert step.text == "The stream is live."
    assert step.used_live_view is False
    assert step.used_roster is False
    assert step.used_config is False
    assert step.latency_ms is not None
    assert step.latency_ms["plan_to_realize"] == 400
    assert missing.reason == "realization_input_invalid"


def test_numeric_forms_come_from_shared_surface_lexicon() -> None:
    forms = render_surface_forms(0.8, "duration_s", "s")
    bundle = _bundle(
        beat_id="timing.lap.completed",
        pattern_id="timing.lap.completed:tight:1",
        required_claim_ids=("timing.lap_completed",),
        selected_fact_ids=("fact:lap-1",),
        actor_bindings=(("hero", ("Alex", "the driver")),),
        fact_bindings=(("fact:lap-1", "timing.lap_completed"),),
        lexicon=_lexicon(
            subject="Alex",
            claim="completes lap 12",
            fact_id="fact:lap-1",
            claim_id="timing.lap_completed",
            number=forms,
        ),
    )
    step = AuthoredRealizer().realize(bundle, now_ms=10_000)

    assert forms == ("0.8 seconds", "eight tenths")
    assert step.text == "Alex completes lap 12."
    assert "0.8 seconds" in bundle.surface_lexicon.value_forms("fact:lap-1", "lap")
    assert "1.1 seconds" not in step.text


def test_timeout_and_cancel_fail_closed() -> None:
    realizer = AuthoredRealizer()
    timeout = realizer.realize(_bundle(), now_ms=20_000, deadline_mono_ms=15_000)
    cancelled = realizer.realize(_bundle(), now_ms=10_000, cancelled=True)

    assert timeout.outcome == "failed"
    assert timeout.reason == "realization_timeout"
    assert timeout.text is None
    assert cancelled.reason == "realization_cancelled"
    assert cancelled.text is None


def test_stale_bundle_hash_and_tts_limit_reject() -> None:
    realizer = AuthoredRealizer()
    stale = realizer.realize(_bundle(), now_ms=10_000, expected_bundle_hash="sha256:" + ("0" * 64))
    oversized = realizer.realize(_bundle(max_chars=8), now_ms=10_000)

    assert stale.reason == "realization_input_invalid"
    assert oversized.reason == "realization_output_oversize"


def test_anti_repeat_uses_only_safe_card_variants() -> None:
    realizer = AuthoredRealizer()
    first = realizer.realize(_bundle(), now_ms=10_000)
    second = realizer.realize(
        _bundle(pattern_id="stream.started:tight:2"),
        now_ms=10_000,
        spoken_line_ids=(first.line_id,),
    )
    third = realizer.realize(
        _bundle(pattern_id="stream.started:tight:1"),
        now_ms=10_000,
        spoken_line_ids=(first.line_id, second.line_id),
    )

    assert first.text == "The stream is live."
    assert second.text == "The stream now is live."
    assert third.text == "Now The stream is live."
    assert first.line_id != second.line_id != third.line_id


def test_unknown_qwen_beat_is_not_in_the_pack() -> None:
    pack = load_authored_pack()
    step = AuthoredRealizer(pack).realize(
        _bundle(beat_id="battle.approach", pattern_id="battle.approach:tight:1"),
        now_ms=10_000,
    )

    assert "battle.approach" not in pack.beat_ids
    assert step.reason == "unknown_authored_beat"


def test_listening_fixtures_cover_transition_identity_and_expiry() -> None:
    realizer = AuthoredRealizer()
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))

    ok = realizer.realize(
        _bundle(pattern_id=transition["patternId"]),
        now_ms=transition["nowMs"],
        deadline_mono_ms=transition["deadlineMonoMs"],
    )
    assert ok.outcome == transition["expectOutcome"]
    assert ok.text == transition["expectText"]
    denied = realizer.realize(
        _bundle(backend=identity["backend"]),
        now_ms=identity["nowMs"],
        fallback=identity["fallback"],
    )
    assert denied.reason == identity["expectReason"]
    late = realizer.realize(
        _bundle(expires_mono_ms=expiry["expiresMonoMs"]),
        now_ms=expiry["nowMs"],
        deadline_mono_ms=expiry["deadlineMonoMs"],
    )
    assert late.reason == expiry["expectReason"]


def test_realizer_is_not_exported_from_events_and_never_uses_eval() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "authored_pack" not in events_exports
    assert "NarrativeRuntime" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    for banned in ("irswitch.commentary", "irswitch.overlay", "irswitch.events"):
        assert banned not in source
    assert "FactView" not in source
