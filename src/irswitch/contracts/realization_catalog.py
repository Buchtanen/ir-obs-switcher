"""EN-only RealizationCatalog and offline legacy-variant classifier (v2 #266).

Implementation-time tooling. Not live-wired. Composes the #256 coverage matrix
and #257 narrative catalog; does not import commentary or overlay packages.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .catalog_loader import NarrativeCatalog, load_narrative_catalog
from .coverage_matrix import audit_coverage_matrix
from .primitives import ContractViolation, canonical_sha256
from .resources import packaged_schema_bytes

SCHEMA_VERSION = "realization-catalog/2"
DISPOSITIONS = frozenset(
    {"audited_pattern", "authored_line", "style_fragment", "reject", "cs_excluded"}
)
ROUTABLE = frozenset({"audited_pattern", "authored_line"})
VARIANT_KEYS = ("neutral", "calm", "focused", "pushing", "high")
STYLE_FRAGMENTS = frozenset({"now", "and", "then", "still", "again", "next", "and then"})
FIRST_PERSON = frozenset(
    {
        "i",
        "i'm",
        "i've",
        "i'd",
        "i'll",
        "me",
        "my",
        "we",
        "we're",
        "we've",
        "we'd",
        "our",
        "ours",
        "us",
    }
)
QUESTION_START = frozenset(
    {"how", "what", "why", "who", "when", "did", "does", "is", "are", "can", "could"}
)
IMPERATIVE_START = frozenset({"look", "watch", "don't", "listen", "remember"})
EMOTION = frozenset(
    {
        "controlled",
        "effortless",
        "nervous",
        "frustrated",
        "angry",
        "scared",
        "terrified",
        "panic",
        "delighted",
        "excited",
        "emotional",
        "stressed",
        "calm",
    }
)
INTENT = frozenset({"trying", "intends", "hoping", "wants"})
CAUSAL = frozenset({"because", "caused", "blame", "fault"})
CERTAINTY = frozenset({"definitely", "certainly", "inevitably", "guaranteed"})
MEDICAL = frozenset({"injured", "injury", "pain", "medical", "heartbeat"})
NON_EN_CHARS = frozenset("ěščřžýáíéúůďťňóĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ")
PUNCT = ".,;:!?\"'"


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    return value


def _load(name: str, override: dict[str, Any] | None) -> dict[str, Any]:
    if override is not None:
        return _object(override, name)
    return _object(json.loads(packaged_schema_bytes(name)), name)


def _unique(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def _source_hash(node_id: str, locale: str, bucket: str, ordinal: int, text: str) -> str:
    return str(
        canonical_sha256(
            {
                "nodeId": node_id,
                "locale": locale,
                "emotionBucket": bucket,
                "ordinal": ordinal,
                "text": text,
            }
        )
    )


@dataclass(frozen=True, slots=True)
class PatternCard:
    id: str
    beat_id: str
    family: str
    freedom: str
    enabled: bool
    audited_language: str
    pattern: str
    placeholders: tuple[str, ...]
    required_claims: tuple[str, ...]
    forbidden_addition: str
    forbidden_claim_types: tuple[str, ...]
    source_provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RealizationCatalog:
    schema_version: str
    catalog_hash: str
    language: str
    beat_count: int
    pattern_count: int
    family_count: int
    cards: tuple[PatternCard, ...]

    def routable_cards(self) -> tuple[PatternCard, ...]:
        return tuple(
            card
            for card in self.cards
            if card.enabled and card.audited_language == "en" and card.freedom == "tight"
        )

    def routable_card_ids(self) -> tuple[str, ...]:
        return tuple(card.id for card in self.routable_cards())

    def card(self, card_id: str) -> PatternCard:
        for item in self.cards:
            if item.id == card_id:
                return item
        raise ContractViolation(f"unknown pattern card {card_id}")


@dataclass(frozen=True, slots=True)
class LegacyVariant:
    node_id: str
    locale: str
    emotion_bucket: str
    ordinal: int
    text: str
    event_types: tuple[str, ...]
    legacy_family: str
    source_hash: str


@dataclass(frozen=True, slots=True)
class Classification:
    source_hash: str
    locale: str
    disposition: str
    proposed: bool
    accepted: bool
    beat_ids: tuple[str, ...]
    family: str
    required_claims: tuple[str, ...]
    forbidden_addition: str
    forbidden_claim_types: tuple[str, ...]
    safe_transforms: tuple[str, ...]
    reject_reasons: tuple[str, ...]
    source_provenance: tuple[str, ...]
    text: str

    @property
    def v2_reachable(self) -> bool:
        return (
            self.accepted
            and self.locale == "en"
            and self.disposition in ROUTABLE
            and bool(self.beat_ids)
        )


@dataclass(frozen=True, slots=True)
class MigrationReport:
    schema_version: str
    catalog_hash: str
    beat_count: int
    pattern_count: int
    en_count: int
    cs_count: int
    proposed_count: int
    accepted_count: int
    routable_count: int
    disposition_counts: tuple[tuple[str, int], ...]
    classifications: tuple[Classification, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "catalogHash": self.catalog_hash,
            "beatCount": self.beat_count,
            "patternCount": self.pattern_count,
            "enCount": self.en_count,
            "csCount": self.cs_count,
            "proposedCount": self.proposed_count,
            "acceptedCount": self.accepted_count,
            "routableCount": self.routable_count,
            "dispositionCounts": dict(self.disposition_counts),
            "classifications": [
                {
                    "sourceHash": item.source_hash,
                    "locale": item.locale,
                    "disposition": item.disposition,
                    "proposed": item.proposed,
                    "accepted": item.accepted,
                    "v2Reachable": item.v2_reachable,
                    "beatIds": list(item.beat_ids),
                    "family": item.family,
                    "requiredClaims": list(item.required_claims),
                    "forbiddenAddition": item.forbidden_addition,
                    "forbiddenClaimTypes": list(item.forbidden_claim_types),
                    "safeTransforms": list(item.safe_transforms),
                    "rejectReasons": list(item.reject_reasons),
                    "sourceProvenance": list(item.source_provenance),
                    "text": item.text,
                }
                for item in self.classifications
            ],
        }


@dataclass(frozen=True, slots=True)
class _BeatNotes:
    family: str
    required_claims: tuple[str, ...]
    forbidden_addition: str
    forbidden_claim_types: tuple[str, ...]


def _beat_notes(beat_doc: dict[str, Any], narrative: NarrativeCatalog) -> dict[str, _BeatNotes]:
    notes: dict[str, _BeatNotes] = {}
    for row in beat_doc["beats"]:
        beat_id = str(row["id"])
        claims = row["claims"]
        typed = narrative.beat(beat_id)
        notes[beat_id] = _BeatNotes(
            family=typed.realization.family,
            required_claims=tuple(claim.id for claim in typed.claims),
            forbidden_addition=str(claims.get("forbiddenAddition") or ""),
            forbidden_claim_types=tuple(
                str(item) for item in claims.get("globalForbiddenClaimTypes") or ()
            ),
        )
    return notes


def load_realization_catalog(
    *,
    registry: dict[str, Any] | None = None,
    beats: dict[str, Any] | None = None,
    graph: dict[str, Any] | None = None,
    cards: dict[str, Any] | None = None,
    detectors: dict[str, Any] | None = None,
    replay_refs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> RealizationCatalog:
    """Load the frozen EN tight catalog. Pattern and beat counts stay separate."""

    matrix = audit_coverage_matrix(
        registry=registry,
        beats=beats,
        graph=graph,
        cards=cards,
        detectors=detectors,
        replay_refs=replay_refs,
    )
    loaded = load_narrative_catalog(
        registry=registry,
        beats=beats,
        graph=graph,
        detectors=detectors,
        config=config,
    )
    if loaded.catalog is None:
        error = loaded.failure.error if loaded.failure is not None else "catalog_invalid"
        raise ContractViolation(error)
    narrative = loaded.catalog
    card_doc = _load("realization-pattern-cards.json", cards)
    beat_doc = _load("beat-catalog.json", beats)
    notes = _beat_notes(beat_doc, narrative)
    built: list[PatternCard] = []
    for row in card_doc["cards"]:
        beat_id = str(row["beatId"])
        note = notes[beat_id]
        card_id = str(row["id"])
        built.append(
            PatternCard(
                id=card_id,
                beat_id=beat_id,
                family=str(row["family"]),
                freedom=str(row["freedom"]),
                enabled=bool(row["enabled"]),
                audited_language=str(row["auditedLanguage"]),
                pattern=str(row["pattern"]),
                placeholders=tuple(str(item) for item in row.get("placeholders") or ()),
                required_claims=note.required_claims,
                forbidden_addition=note.forbidden_addition,
                forbidden_claim_types=note.forbidden_claim_types,
                source_provenance=("packaged:realization-pattern-cards.json", card_id),
            )
        )
    if matrix.pattern_card_count != len(built) or matrix.beat_count != len(notes):
        raise ContractViolation("realization catalog counts drifted from coverage matrix")
    return RealizationCatalog(
        schema_version=SCHEMA_VERSION,
        catalog_hash=str(canonical_sha256(card_doc)),
        language="en",
        beat_count=matrix.beat_count,
        pattern_count=matrix.pattern_card_count,
        family_count=matrix.family_count,
        cards=tuple(built),
    )


def inventory_legacy_variants(graph: dict[str, Any]) -> tuple[LegacyVariant, ...]:
    """Read raw sequence-graph JSON. Does not import the commentary package."""

    payload = _object(graph, "legacy graph")
    nodes = _object(payload.get("nodes") or {}, "nodes")
    variants: list[LegacyVariant] = []
    for node_id, raw in nodes.items():
        node = _object(raw, f"nodes.{node_id}")
        event_types = tuple(str(item).upper() for item in node.get("event_types") or [])
        legacy_family = str(node.get("family") or "")
        locale_map = node.get("variants") or {}
        if not isinstance(locale_map, dict):
            raise ContractViolation(f"nodes.{node_id}.variants must be an object")
        for locale, buckets in locale_map.items():
            if not isinstance(buckets, dict):
                continue
            for bucket in VARIANT_KEYS:
                texts = buckets.get(bucket) or []
                if not isinstance(texts, list):
                    continue
                for ordinal, item in enumerate(texts):
                    text = str(item)
                    if not text.strip():
                        continue
                    variants.append(
                        LegacyVariant(
                            node_id=str(node_id),
                            locale=str(locale),
                            emotion_bucket=bucket,
                            ordinal=ordinal,
                            text=text,
                            event_types=event_types,
                            legacy_family=legacy_family,
                            source_hash=_source_hash(
                                str(node_id), str(locale), bucket, ordinal, text
                            ),
                        )
                    )
    return tuple(variants)


def _mapped_beats(event_types: tuple[str, ...], narrative: NarrativeCatalog) -> tuple[str, ...]:
    beat_ids: list[str] = []
    for event_id in event_types:
        route = narrative.route_event(event_id)
        if route is not None:
            beat_ids.extend(route.beat_ids)
    return _unique(beat_ids)


def _notes_for(beat_ids: tuple[str, ...], notes: dict[str, _BeatNotes]) -> _BeatNotes:
    families: list[str] = []
    required: list[str] = []
    forbidden: list[str] = []
    types: list[str] = []
    for beat_id in beat_ids:
        note = notes[beat_id]
        families.append(note.family)
        required.extend(note.required_claims)
        if note.forbidden_addition:
            forbidden.append(note.forbidden_addition)
        types.extend(note.forbidden_claim_types)
    unique_families = _unique(families)
    return _BeatNotes(
        family=unique_families[0] if len(unique_families) == 1 else "",
        required_claims=_unique(required),
        forbidden_addition="; ".join(_unique(forbidden)),
        forbidden_claim_types=_unique(types),
    )


def _tokens(text: str) -> list[str]:
    return [item for item in text.split() if item]


def _bare_token(token: str) -> str:
    return token.strip(PUNCT).casefold()


def _has_word(text: str, words: frozenset[str]) -> bool:
    return any(_bare_token(token) in words for token in _tokens(text))


def _mask_slots_and_numbers(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "{":
            end = text.find("}", i)
            if end != -1:
                out.append("slot")
                i = end + 1
                continue
        if char.isdigit():
            j = i
            while j < len(text) and (text[j].isdigit() or text[j] in {":", "."}):
                j += 1
            out.append("num")
            i = j
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _sentence_count(text: str) -> int:
    masked = _mask_slots_and_numbers(text)
    parts = [item.strip() for item in masked.replace("!", ".").replace("?", ".").split(".")]
    parts = [item for item in parts if item]
    return max(1, len(parts)) if text.strip() else 0


def _safe_transforms(text: str) -> tuple[str, ...]:
    if text != " ".join(text.split()):
        return ("normalize_whitespace",)
    return ()


def _reject_reasons(text: str) -> list[str]:
    reasons: list[str] = []
    stripped = text.strip()
    if not stripped:
        return ["empty"]
    if len(stripped) > 240:
        reasons.append("too_long")
    if _sentence_count(stripped) > 1:
        reasons.append("sentence_count")
    if len(_tokens(stripped)) > 32:
        reasons.append("token_count")
    if any(char in NON_EN_CHARS for char in stripped):
        reasons.append("non_en_contract")
    lowered = stripped.casefold()
    if (
        "<think>" in lowered
        or "```" in stripped
        or lowered.startswith("# ")
        or lowered.startswith("commentator:")
    ):
        reasons.append("meta_output")
    first = _bare_token(_tokens(stripped)[0]) if _tokens(stripped) else ""
    if "?" in stripped or first in QUESTION_START:
        reasons.append("question")
    if _has_word(stripped, FIRST_PERSON):
        reasons.append("first_person")
    if first in IMPERATIVE_START:
        reasons.append("imperative")
    if _has_word(stripped, EMOTION):
        reasons.append("emotion_inference")
    if _has_word(stripped, INTENT):
        reasons.append("intent_inference")
    if _has_word(stripped, CAUSAL):
        reasons.append("causal_inference")
    if _has_word(stripped, CERTAINTY):
        reasons.append("unsupported_certainty")
    if _has_word(stripped, MEDICAL) or "heart rate" in lowered:
        reasons.append("medical_inference")
    return reasons


def _is_style_fragment(text: str) -> bool:
    without_slots = text.replace("{", "").replace("}", "")
    normalized = without_slots.strip().rstrip(".,;:").casefold()
    tokens = _tokens(normalized)
    return normalized in STYLE_FRAGMENTS or (len(tokens) <= 2 and "{" not in text)


class MigrationClassifier:
    """Proposes proposition-level dispositions; acceptance is explicit."""

    def __init__(
        self,
        catalog: RealizationCatalog | None = None,
        *,
        accepted_hashes: frozenset[str] | set[str] = frozenset(),
        narrative: NarrativeCatalog | None = None,
        beat_notes: dict[str, _BeatNotes] | None = None,
    ) -> None:
        self.catalog = catalog or load_realization_catalog()
        loaded = load_narrative_catalog() if narrative is None else None
        if narrative is None:
            assert loaded is not None
            if loaded.catalog is None:
                error = loaded.failure.error if loaded.failure is not None else "catalog_invalid"
                raise ContractViolation(error)
            narrative = loaded.catalog
        self._narrative = narrative
        self._notes = beat_notes or _beat_notes(_load("beat-catalog.json", None), narrative)
        self._accepted = set(accepted_hashes)
        self._patterns = {card.pattern: card for card in self.catalog.routable_cards()}

    def classify(self, variant: LegacyVariant) -> Classification:
        beat_ids = _mapped_beats(variant.event_types, self._narrative)
        notes = _notes_for(beat_ids, self._notes)
        provenance = (
            f"legacy:{variant.node_id}:{variant.locale}:{variant.emotion_bucket}:{variant.ordinal}",
        )
        accepted = variant.source_hash in self._accepted
        if variant.locale == "cs":
            return Classification(
                source_hash=variant.source_hash,
                locale=variant.locale,
                disposition="cs_excluded",
                proposed=True,
                accepted=False,
                beat_ids=beat_ids,
                family=notes.family,
                required_claims=notes.required_claims,
                forbidden_addition=notes.forbidden_addition,
                forbidden_claim_types=notes.forbidden_claim_types,
                safe_transforms=_safe_transforms(variant.text),
                reject_reasons=("cs_excluded",),
                source_provenance=provenance,
                text=variant.text,
            )
        matched = self._patterns.get(variant.text.strip())
        if matched is not None:
            if not notes.family:
                notes = _BeatNotes(
                    family=matched.family,
                    required_claims=matched.required_claims,
                    forbidden_addition=matched.forbidden_addition,
                    forbidden_claim_types=matched.forbidden_claim_types,
                )
                if not beat_ids:
                    beat_ids = (matched.beat_id,)
            return Classification(
                source_hash=variant.source_hash,
                locale=variant.locale,
                disposition="audited_pattern",
                proposed=True,
                accepted=accepted,
                beat_ids=beat_ids,
                family=notes.family or matched.family,
                required_claims=notes.required_claims or matched.required_claims,
                forbidden_addition=notes.forbidden_addition or matched.forbidden_addition,
                forbidden_claim_types=notes.forbidden_claim_types or matched.forbidden_claim_types,
                safe_transforms=_safe_transforms(variant.text),
                reject_reasons=(),
                source_provenance=provenance,
                text=variant.text,
            )
        reasons = tuple(_reject_reasons(variant.text))
        if reasons:
            disposition = "reject"
        elif _is_style_fragment(variant.text):
            disposition = "style_fragment"
        else:
            disposition = "authored_line"
        return Classification(
            source_hash=variant.source_hash,
            locale=variant.locale,
            disposition=disposition,
            proposed=True,
            accepted=accepted,
            beat_ids=beat_ids,
            family=notes.family,
            required_claims=notes.required_claims,
            forbidden_addition=notes.forbidden_addition,
            forbidden_claim_types=notes.forbidden_claim_types,
            safe_transforms=_safe_transforms(variant.text),
            reject_reasons=reasons,
            source_provenance=provenance,
            text=variant.text,
        )

    def accept(self, classification: Classification) -> Classification:
        if classification.disposition == "cs_excluded" or classification.locale == "cs":
            raise ContractViolation("CS cannot enter v2 routing")
        self._accepted.add(classification.source_hash)
        return Classification(
            source_hash=classification.source_hash,
            locale=classification.locale,
            disposition=classification.disposition,
            proposed=True,
            accepted=True,
            beat_ids=classification.beat_ids,
            family=classification.family,
            required_claims=classification.required_claims,
            forbidden_addition=classification.forbidden_addition,
            forbidden_claim_types=classification.forbidden_claim_types,
            safe_transforms=classification.safe_transforms,
            reject_reasons=classification.reject_reasons,
            source_provenance=classification.source_provenance,
            text=classification.text,
        )


def migrate_legacy_graph(
    graph: dict[str, Any],
    *,
    accepted_hashes: frozenset[str] | set[str] = frozenset(),
    catalog: RealizationCatalog | None = None,
) -> MigrationReport:
    """Offline export report. Classifications stay proposed unless accepted."""

    catalog = catalog or load_realization_catalog()
    classifier = MigrationClassifier(catalog, accepted_hashes=accepted_hashes)
    classifications = tuple(classifier.classify(item) for item in inventory_legacy_variants(graph))
    counts = Counter(item.disposition for item in classifications)
    return MigrationReport(
        schema_version=SCHEMA_VERSION,
        catalog_hash=catalog.catalog_hash,
        beat_count=catalog.beat_count,
        pattern_count=catalog.pattern_count,
        en_count=sum(1 for item in classifications if item.locale == "en"),
        cs_count=sum(1 for item in classifications if item.locale == "cs"),
        proposed_count=len(classifications),
        accepted_count=sum(1 for item in classifications if item.accepted),
        routable_count=sum(1 for item in classifications if item.v2_reachable),
        disposition_counts=tuple(sorted(counts.items())),
        classifications=classifications,
    )
