"""#263 ExposureStore: spoken-only fatigue, base-2 half-life, channel pressure."""

from __future__ import annotations

import json
import math
from pathlib import Path

from irswitch.events import __all__ as events_exports
from irswitch.events.exposure_store import (
    EXPOSURE_CAP,
    LONG_SILENCE_MS,
    PATTERN_HALF_LIFE_MS,
    SEMANTIC_HALF_LIFE_MS,
    EmbeddingAdapter,
    ExposureIntent,
    ExposureStore,
    content_tokens,
    half_life_decay,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "exposure_store.py"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "exposure_store"
MACHINE = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "v2.0.0"
    / "machine"
    / "vertical-slice-fixtures.json"
)


def _intent(**overrides: object) -> ExposureIntent:
    values: dict[str, object] = {
        "phase": "speaking",
        "utterance_id": "utt:1",
        "semantic_identity": ("hero", "car.22", "lap"),
        "family": "timing_attempt",
        "pattern": "timing.lap.completed:tight:1",
        "text": "The hero completes lap twelve.",
        "tape_channel": "race.timing.lap",
        "policy_id": "result",
        "episode_id": "episode:lap-1",
        "beat_role": "outcome",
        "now_ms": 10_000,
        "source_kind": "narrative",
    }
    values.update(overrides)
    return ExposureIntent(**values)  # type: ignore[arg-type]


def test_rejected_and_stale_add_no_fatigue() -> None:
    store = ExposureStore()
    for phase in ("planned", "rejected", "stale", "building", "committed"):
        step = store.record(_intent(phase=phase, utterance_id=f"utt:{phase}"))
        assert step.reason == "ignored_not_spoken"
        assert step.record is None
    view = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="The hero completes lap twelve.",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=10_000,
    )
    assert view.semantic_fatigue == 0.0
    assert view.pattern_fatigue == 0.0
    assert view.channel_pressure == 0.0
    assert view.event_penalty == 0.0


def test_manual_never_records() -> None:
    store = ExposureStore()
    step = store.record(_intent(source_kind="manual"))
    assert step.reason == "ignored_manual"
    assert (
        store.query(
            semantic_identity=("hero", "car.22", "lap"),
            pattern="timing.lap.completed:tight:1",
            text="The hero completes lap twelve.",
            tape_channel="race.timing.lap",
            policy_id="result",
            now_ms=10_000,
        ).semantic_fatigue
        == 0.0
    )


def test_speaking_starts_penalty_not_planning() -> None:
    store = ExposureStore()
    planned = store.record(_intent(phase="planned"))
    spoken = store.record(_intent(phase="speaking"))
    assert planned.reason == "ignored_not_spoken"
    assert spoken.reason == "recorded"
    assert spoken.record is not None
    assert spoken.record.exposure_weight == 1.0
    view = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="The hero completes lap twelve.",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=10_000,
    )
    assert view.semantic_fatigue == 1.0
    assert view.pattern_fatigue == 1.0


def test_half_life_is_base2_not_natural_exp() -> None:
    assert half_life_decay(90_000, SEMANTIC_HALF_LIFE_MS) == 0.5
    assert half_life_decay(180_000, PATTERN_HALF_LIFE_MS) == 0.5
    natural = math.exp(-1.0)
    assert abs(0.5 - natural) > 0.1
    payload = json.loads(MACHINE.read_text(encoding="utf-8"))
    calcs = next(
        row["calculations"]
        for row in payload["fixtures"]
        if "fatigue_half_each" in row.get("expectations", [])
    )
    for item in calcs:
        if item.get("op") != "half_life":
            continue
        age_ms = int(item["age"]) * 1000
        half_ms = int(item["halfLife"]) * 1000
        assert half_life_decay(age_ms, half_ms) == float(item["expected"])


def test_decay_uses_monotonic_time() -> None:
    store = ExposureStore()
    store.record(_intent(now_ms=10_000))
    later = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="The hero completes lap twelve.",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=10_000 + SEMANTIC_HALF_LIFE_MS,
    )
    assert later.semantic_fatigue == 0.5
    earlier = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="The hero completes lap twelve.",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=10_000,
    )
    assert earlier.semantic_fatigue == 1.0


def test_channel_pressure_uses_accepted_and_event_coefficient() -> None:
    store = ExposureStore()
    store.record(_intent(phase="rejected", utterance_id="utt:rej"))
    store.record(_intent(phase="speaking", utterance_id="utt:ok"))
    view = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="The hero completes lap twelve.",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=10_000,
    )
    assert view.channel_pressure == 6.0
    assert view.event_penalty == 0.5 * 6.0
    pressure = store.channel_pressure_view(now_ms=10_000)
    assert pressure.by_channel == (("race.timing.lap", 6.0),)


def test_filler_cadence_uses_long_silence_not_ttl() -> None:
    store = ExposureStore()
    store.record(
        _intent(
            utterance_id="utt:fill",
            semantic_identity=("stream", "lobby"),
            family="filler_single",
            pattern="filler.lobby:tight:1",
            text="Still in the lobby.",
            tape_channel="filler.track_state",
            policy_id="filler",
            episode_id="episode:fill",
            beat_role="filler",
        )
    )
    half = store.query(
        semantic_identity=("stream", "lobby"),
        pattern="filler.lobby:tight:1",
        text="Still in the lobby.",
        tape_channel="filler.track_state",
        policy_id="filler",
        now_ms=10_000 + LONG_SILENCE_MS,
    )
    assert half.channel_pressure == 6.0 * 0.5


def test_lexical_jaccard_and_tail_are_deterministic() -> None:
    store = ExposureStore()
    store.record(_intent(text="The hero completes lap twelve."))
    same = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="Hero completes lap twelve",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=10_000,
    )
    other = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="Rain is falling harder now",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=10_000,
    )
    assert same.lexical_jaccard > 0.0
    assert same.lexical_tail_similar is True
    assert other.lexical_jaccard == 0.0
    assert other.lexical_tail_similar is False
    assert content_tokens("The hero completes lap twelve.") == frozenset(
        {"hero", "completes", "lap", "twelve"}
    )


def test_embedding_cannot_gate_facts_or_successors() -> None:
    class LoudAdapter:
        def similarity(self, left: str, right: str) -> float:
            return 0.99

    store = ExposureStore(embedding=LoudAdapter())
    step = store.record(_intent())
    assert step.reason == "recorded"
    view = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="unrelated wording",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=10_000,
    )
    assert view.embedding_similarity == 0.99
    assert view.embedding_is_gate is False
    assert view.semantic_fatigue == 1.0
    assert view.channel_pressure == 6.0
    assert isinstance(LoudAdapter(), EmbeddingAdapter)


def test_family_role_histories_are_not_score_terms() -> None:
    store = ExposureStore()
    store.record(_intent())
    view = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="The hero completes lap twelve.",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=10_000,
    )
    audit = store.cadence_audit()
    assert "timing_attempt" in audit.families
    assert "outcome" in audit.roles
    assert not hasattr(view, "family_penalty")
    assert view.semantic_fatigue == 1.0


def test_capacity_evicts_oldest_and_stream_reset_clears() -> None:
    store = ExposureStore(capacity=2)
    store.record(_intent(utterance_id="utt:a", now_ms=1_000, semantic_identity=("a",)))
    store.record(_intent(utterance_id="utt:b", now_ms=2_000, semantic_identity=("b",)))
    evicted = store.record(_intent(utterance_id="utt:c", now_ms=3_000, semantic_identity=("c",)))
    assert evicted.reason == "recorded"
    assert store.size == 2
    assert (
        store.query(
            semantic_identity=("a",),
            pattern="timing.lap.completed:tight:1",
            text="x",
            tape_channel="race.timing.lap",
            policy_id="result",
            now_ms=3_000,
        ).semantic_fatigue
        == 0.0
    )
    reset = store.reset_stream(now_ms=4_000)
    assert reset.reason == "reset"
    assert store.size == 0
    assert EXPOSURE_CAP == 128


def test_replay_fixtures_cover_transition_identity_and_expiry() -> None:
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))

    store = ExposureStore()
    store.record(_intent(now_ms=transition["spokenAtMs"]))
    aged = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="The hero completes lap twelve.",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=transition["queryAtMs"],
    )
    assert aged.semantic_fatigue == transition["expectedSemantic"]
    pattern_at = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="The hero completes lap twelve.",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=transition["spokenAtMs"] + transition["patternHalfLifeMs"],
    )
    assert pattern_at.pattern_fatigue == transition["expectedPatternAtSpokenPlus180s"]

    other = store.query(
        semantic_identity=tuple(identity["otherIdentity"]),
        pattern=identity["otherPattern"],
        text="Pressure from behind.",
        tape_channel="race.battle.pressure",
        policy_id="live_story",
        now_ms=transition["spokenAtMs"],
    )
    assert other.semantic_fatigue == 0.0
    assert other.pattern_fatigue == 0.0

    store.reset_stream(now_ms=expiry["resetAtMs"])
    cleared = store.query(
        semantic_identity=("hero", "car.22", "lap"),
        pattern="timing.lap.completed:tight:1",
        text="The hero completes lap twelve.",
        tape_channel="race.timing.lap",
        policy_id="result",
        now_ms=expiry["queryAtMs"],
    )
    assert cleared.semantic_fatigue == 0.0


def test_exports_and_banned_imports_stay_out() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "exposure_store" not in events_exports
    for banned in (
        "NarrativeRuntime",
        "eval(",
        "exec(",
        "compile(",
        "irswitch.commentary",
        "irswitch.overlay",
        "StoryDirector",
        "math.exp",
    ):
        assert banned not in source
