"""#266 EN-only RealizationCatalog and migration classifier."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from irswitch.contracts import (
    ContractViolation,
    canonical_sha256,
    load_realization_catalog,
)
from irswitch.contracts.realization_catalog import (
    SCHEMA_VERSION,
    LegacyVariant,
    MigrationClassifier,
    inventory_legacy_variants,
    migrate_legacy_graph,
)
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events import __all__ as events_exports

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "irswitch" / "contracts" / "realization_catalog.py"
LEGACY_GRAPH = ROOT / "src" / "irswitch" / "commentary" / "data" / "sequence_graph.json"
FIXTURE_GRAPH = ROOT / "tests" / "fixtures" / "realization_catalog" / "legacy_graph.json"


def _fixture_graph() -> dict[str, Any]:
    payload = json.loads(FIXTURE_GRAPH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _variant(**overrides: object) -> LegacyVariant:
    values: dict[str, object] = {
        "node_id": "lap_complete",
        "locale": "en",
        "emotion_bucket": "neutral",
        "ordinal": 0,
        "text": "That's a lap for him.",
        "event_types": ("LAP_COMPLETE",),
        "legacy_family": "timing",
        "source_hash": "pending",
    }
    values.update(overrides)
    if values["source_hash"] == "pending":
        values["source_hash"] = str(
            canonical_sha256(
                {
                    "nodeId": values["node_id"],
                    "locale": values["locale"],
                    "emotionBucket": values["emotion_bucket"],
                    "ordinal": values["ordinal"],
                    "text": values["text"],
                }
            )
        )
    return LegacyVariant(**values)  # type: ignore[arg-type]


def test_frozen_catalog_keeps_pattern_and_beat_counts_separate() -> None:
    catalog = load_realization_catalog()
    cards = json.loads(packaged_schema_bytes("realization-pattern-cards.json"))

    assert catalog.schema_version == SCHEMA_VERSION == "realization-catalog/2"
    assert catalog.pattern_count == 256
    assert catalog.beat_count == 64
    assert catalog.family_count == 37
    assert catalog.pattern_count != catalog.beat_count
    assert catalog.language == "en"
    assert catalog.catalog_hash == str(canonical_sha256(cards))
    assert len(catalog.cards) == 256
    assert {card.beat_id for card in catalog.cards} and len(
        {card.beat_id for card in catalog.cards}
    ) == 64
    for card in catalog.cards:
        assert card.audited_language == "en"
        assert card.enabled is True
        assert card.freedom == "tight"
        assert card.pattern
        assert card.placeholders


def test_cards_annotate_required_and_forbidden_claims() -> None:
    catalog = load_realization_catalog()
    cards = [card for card in catalog.cards if card.beat_id == "timing.lap.completed"]

    assert len(cards) == 4
    assert {card.family for card in cards} == {"timing.lap_result"}
    for card in cards:
        assert "timing.lap_completed" in card.required_claims
        assert card.forbidden_addition == "PB or pace judgement without comparison fact"
        assert "unbound.emotion" in card.forbidden_claim_types
        assert card.source_provenance == ("packaged:realization-pattern-cards.json", card.id)


def test_no_cs_card_is_v2_reachable() -> None:
    catalog = load_realization_catalog()

    assert catalog.routable_card_ids()
    assert all(card.audited_language == "en" for card in catalog.routable_cards())
    cards = json.loads(packaged_schema_bytes("realization-pattern-cards.json"))
    mutated = copy.deepcopy(cards)
    mutated["cards"][0]["auditedLanguage"] = "cs"
    with pytest.raises(ContractViolation, match="pattern card language is not EN"):
        load_realization_catalog(cards=mutated)


def test_inventory_covers_all_legacy_en_variants() -> None:
    graph = json.loads(LEGACY_GRAPH.read_text(encoding="utf-8"))
    variants = inventory_legacy_variants(graph)

    assert sum(1 for item in variants if item.locale == "en") == 2128
    assert sum(1 for item in variants if item.locale == "cs") == 2128
    assert len({item.source_hash for item in variants}) == len(variants)


def test_every_migrated_text_has_proposition_disposition() -> None:
    report = migrate_legacy_graph(json.loads(LEGACY_GRAPH.read_text(encoding="utf-8")))

    assert report.en_count == 2128
    assert report.cs_count == 2128
    assert report.beat_count == 64
    assert report.pattern_count == 256
    assert report.beat_count != report.pattern_count
    assert report.proposed_count == 4256
    assert report.accepted_count == 0
    assert report.routable_count == 0
    assert {item.disposition for item in report.classifications} <= {
        "audited_pattern",
        "authored_line",
        "style_fragment",
        "reject",
        "cs_excluded",
    }
    assert all(item.disposition for item in report.classifications)
    assert all(item.accepted is False for item in report.classifications)


def test_cs_variants_are_excluded_and_cannot_be_accepted() -> None:
    classifier = MigrationClassifier()
    variant = inventory_legacy_variants(_fixture_graph())[-1]
    step = classifier.classify(variant)

    assert variant.locale == "cs"
    assert variant.text == "To je kolo."
    assert step.disposition == "cs_excluded"
    assert step.v2_reachable is False
    assert "cs_excluded" in step.reject_reasons
    with pytest.raises(ContractViolation, match="CS cannot enter v2 routing"):
        classifier.accept(step)


def test_classifier_proposes_until_explicit_acceptance() -> None:
    classifier = MigrationClassifier()
    variant = _variant()
    proposed = classifier.classify(variant)

    assert proposed.disposition == "authored_line"
    assert proposed.proposed is True
    assert proposed.accepted is False
    assert proposed.v2_reachable is False
    assert proposed.beat_ids == ("timing.lap.completed",)
    assert "timing.lap_completed" in proposed.required_claims
    accepted = classifier.accept(proposed)
    assert accepted.accepted is True
    assert accepted.v2_reachable is True
    assert classifier.classify(variant).accepted is True


def test_unsafe_legacy_text_is_rejected() -> None:
    classifier = MigrationClassifier()
    question = classifier.classify(_variant(text="How did he do that?", ordinal=1))
    first_person = classifier.classify(_variant(text="I think he is pushing.", ordinal=2))
    emotion = classifier.classify(_variant(text="He looks nervous and frustrated.", ordinal=3))
    multi = classifier.classify(
        _variant(
            text="He crosses the line. The lap is banked and the picture is clear.",
            ordinal=4,
        )
    )

    assert question.disposition == "reject"
    assert "question" in question.reject_reasons
    assert first_person.disposition == "reject"
    assert "first_person" in first_person.reject_reasons
    assert emotion.disposition == "reject"
    assert "emotion_inference" in emotion.reject_reasons
    assert multi.disposition == "reject"
    assert "sentence_count" in multi.reject_reasons
    assert all(item.v2_reachable is False for item in (question, first_person, emotion, multi))


def test_card_pattern_classifies_as_audited_pattern() -> None:
    classifier = MigrationClassifier()
    step = classifier.classify(_variant(text="{subjectSurface} {requiredClaimSurface}."))

    assert step.disposition == "audited_pattern"
    assert step.accepted is False
    assert step.family == "timing.lap_result"
    accepted = classifier.accept(step)
    assert accepted.v2_reachable is True


def test_style_fragment_is_not_routable() -> None:
    classifier = MigrationClassifier()
    step = classifier.classify(_variant(text="now.", ordinal=8))
    accepted = classifier.accept(step)

    assert step.disposition == "style_fragment"
    assert accepted.accepted is True
    assert accepted.v2_reachable is False


def test_accept_set_makes_only_en_authored_or_pattern_routable() -> None:
    graph = _fixture_graph()
    variants = inventory_legacy_variants(graph)
    classifier = MigrationClassifier()
    proposed = [classifier.classify(item) for item in variants]
    accepted_hashes = frozenset(
        item.source_hash
        for item in proposed
        if item.disposition in {"audited_pattern", "authored_line", "style_fragment"}
    )
    report = migrate_legacy_graph(graph, accepted_hashes=accepted_hashes)

    assert report.accepted_count == 3
    assert report.routable_count == 2
    assert {item.text for item in variants if item.locale == "cs"} == {"To je kolo."}
    assert all(
        item.disposition != "cs_excluded" or item.accepted is False
        for item in report.classifications
    )


def test_classifier_is_not_exported_from_events_and_never_uses_eval() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "realization_catalog" not in events_exports
    assert "NarrativeRuntime" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    for banned in ("irswitch.commentary", "irswitch.overlay", "irswitch.events"):
        assert banned not in source
    assert "RealizationBundle" not in source


def test_classification_export_preserves_source_provenance() -> None:
    report = migrate_legacy_graph(_fixture_graph())
    row = next(item for item in report.classifications if item.locale == "en")
    exported = report.as_dict()

    assert exported["schemaVersion"] == SCHEMA_VERSION
    assert exported["patternCount"] == 256
    assert exported["beatCount"] == 64
    assert row.source_provenance[0].startswith("legacy:lap_complete:")
    rows = exported["classifications"]
    assert isinstance(rows, list)
    first = rows[0]
    assert isinstance(first, dict)
    assert isinstance(first["sourceHash"], str)
    assert first["sourceHash"] == row.source_hash
