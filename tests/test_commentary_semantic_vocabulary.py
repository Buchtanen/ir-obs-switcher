"""Semantic word-policy tests independent of graph/composer integration."""

from __future__ import annotations

import pytest

from irswitch.commentary.semantic_vocabulary import (
    SemanticCategory,
    VocabularyPolicyError,
    require_semantic_vocabulary,
    validate_semantic_vocabulary,
)


@pytest.mark.parametrize(
    "text",
    [
        "Po incidentu je auto mimo trať.",
        "Jezdec se vrací po incidentech.",
        "Dva incidenty během jednoho kola.",
        "The incident sent the car off track.",
        "Two incidents in this race.",
        "<speak>Po INCIDENTU pokračuje.</speak>",
    ],
)
def test_physical_driving_categories_reject_incident_word_family(text: str) -> None:
    violations = validate_semantic_vocabulary(text, SemanticCategory.TRACK_EXCURSION)

    assert [item.code for item in violations] == ["incident_vocabulary_forbidden"]
    assert violations[0].token.lower().startswith("incident")


@pytest.mark.parametrize(
    "text",
    [
        "This was incidental to the main result.",
        "The data coincidentally arrived together.",
        "Auto vyjelo mimo trať a znovu se rozjíždí.",
        "Kontakt přišel až po výjezdu z trati.",
    ],
)
def test_unrelated_words_and_specific_physical_vocabulary_are_allowed(text: str) -> None:
    assert validate_semantic_vocabulary(text, SemanticCategory.TRACK_EXCURSION) == ()


@pytest.mark.parametrize(
    "text",
    [
        "Incident count rises to four.",
        "Počet incidentů stoupá na čtyři.",
    ],
)
def test_numeric_incident_points_category_is_the_only_allow_list(text: str) -> None:
    assert validate_semantic_vocabulary(text, SemanticCategory.INCIDENT_POINTS_UPDATE) == ()


def test_policy_error_exposes_stable_reason_and_category() -> None:
    with pytest.raises(VocabularyPolicyError) as caught:
        require_semantic_vocabulary(
            "Po incidentu vůz stojí.",
            SemanticCategory.STOPPED_AFTER_EXCURSION,
        )

    assert caught.value.violations[0].code == "incident_vocabulary_forbidden"
    assert caught.value.category is SemanticCategory.STOPPED_AFTER_EXCURSION
