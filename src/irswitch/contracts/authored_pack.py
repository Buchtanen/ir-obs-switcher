"""Authored critical/lifecycle pack and bundle-only realizer (v2 #267).

Implementation-time tooling. Not live-wired. Composes #257 catalog load and
#266 realization cards. Consumes only ``realization-bundle/2`` surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog_loader import load_narrative_catalog
from .primitives import ContractViolation, canonical_sha256
from .realization_catalog import load_realization_catalog

SCHEMA_VERSION = "authored-pack/2"
BUNDLE_SCHEMA = "realization-bundle/2"
TENTH_WORDS = {
    1: "one tenth",
    2: "two tenths",
    3: "three tenths",
    4: "four tenths",
    5: "five tenths",
    6: "six tenths",
    7: "seven tenths",
    8: "eight tenths",
    9: "nine tenths",
}
UNSAFE_COLOR = frozenset(
    {"because", "caused", "stunning", "brilliant", "probably", "will win", "looking"}
)


def render_surface_forms(
    value: float | int, value_type: str, unit: str | None = None
) -> tuple[str, ...]:
    """Finite EN number/unit/ordinal/band forms. No live telemetry."""

    if value_type == "duration_s":
        forms = [f"{value:g} seconds" if unit in {None, "s"} else f"{value:g} {unit}"]
        tenths = int(round(float(value) * 10))
        word = TENTH_WORDS.get(tenths)
        if word is not None:
            forms.append(word)
        return tuple(forms)
    if value_type == "ordinal":
        return (f"P{int(value)}",)
    if value_type == "band":
        return (str(value),)
    return (str(value),)


@dataclass(frozen=True, slots=True)
class AuthoredLine:
    id: str
    beat_id: str
    pattern_id: str
    pattern: str
    placeholders: tuple[str, ...]
    required_claims: tuple[str, ...]
    family: str
    policy_id: str


@dataclass(frozen=True, slots=True)
class AuthoredPack:
    schema_version: str
    catalog_hash: str
    beat_count: int
    line_count: int
    beat_ids: tuple[str, ...]
    lines: tuple[AuthoredLine, ...]

    def lines_for(self, beat_id: str) -> tuple[AuthoredLine, ...]:
        return tuple(line for line in self.lines if line.beat_id == beat_id)

    def line(self, line_id: str) -> AuthoredLine:
        for item in self.lines:
            if item.id == line_id:
                return item
        raise ContractViolation(f"unknown authored line {line_id}")


@dataclass(frozen=True, slots=True)
class SurfaceValueSet:
    surface_value_set_id: str
    fact_id: str
    attribute_id: str
    value_type: str
    unit: str | None
    forms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RelationLexeme:
    claim_id: str
    polarity: str
    temporal_frame: str
    forms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SurfaceLexicon:
    surface_value_sets: tuple[SurfaceValueSet, ...]
    relation_lexemes: tuple[RelationLexeme, ...]
    connectives: tuple[str, ...]
    forbidden_lexemes: tuple[str, ...]
    subject_surface: str
    subject_actor_id: str

    def value_forms(self, fact_id: str, attribute_id: str) -> tuple[str, ...]:
        for item in self.surface_value_sets:
            if item.fact_id == fact_id and item.attribute_id == attribute_id:
                return item.forms
        return ()

    def claim_surface(self, claim_id: str) -> str:
        for item in self.relation_lexemes:
            if item.claim_id == claim_id and item.forms:
                return item.forms[0]
        return ""

    def canonical(self) -> dict[str, object]:
        return {
            "connectives": list(self.connectives),
            "forbiddenLexemes": list(self.forbidden_lexemes),
            "relationLexemes": [
                {
                    "claimId": item.claim_id,
                    "forms": list(item.forms),
                    "polarity": item.polarity,
                    "temporalFrame": item.temporal_frame,
                }
                for item in self.relation_lexemes
            ],
            "subjectActorId": self.subject_actor_id,
            "subjectSurface": self.subject_surface,
            "surfaceValueSets": [
                {
                    "attributeId": item.attribute_id,
                    "factId": item.fact_id,
                    "forms": list(item.forms),
                    "surfaceValueSetId": item.surface_value_set_id,
                    "unit": item.unit,
                    "valueType": item.value_type,
                }
                for item in self.surface_value_sets
            ],
        }


@dataclass(frozen=True, slots=True)
class RealizationBundle:
    schema_version: str
    bundle_id: str
    beat_id: str
    backend: str
    pattern_id: str
    max_chars: int
    max_seconds: float
    required_claim_ids: tuple[str, ...]
    selected_fact_ids: tuple[str, ...]
    planned_mono_ms: int
    expires_mono_ms: int
    language: str
    actor_bindings: tuple[tuple[str, tuple[str, ...]], ...]
    fact_bindings: tuple[tuple[str, str], ...]
    surface_lexicon: SurfaceLexicon
    fact_binding_hash: str
    surface_lexicon_hash: str
    bundle_hash: str


@dataclass(frozen=True, slots=True)
class AuthoredStep:
    schema_version: str
    outcome: str
    reason: str
    backend: str
    text: str | None
    text_hash: str | None
    line_id: str | None
    used_live_view: bool
    used_roster: bool
    used_config: bool
    latency_ms: dict[str, int] | None


def load_authored_pack() -> AuthoredPack:
    """Select catalog cards for every beat whose backend is authored."""

    cards = load_realization_catalog()
    loaded = load_narrative_catalog()
    if loaded.catalog is None:
        error = loaded.failure.error if loaded.failure is not None else "catalog_invalid"
        raise ContractViolation(error)
    narrative = loaded.catalog
    lines: list[AuthoredLine] = []
    beat_ids: list[str] = []
    for beat in narrative.beats:
        if beat.realization.backend != "authored":
            continue
        beat_ids.append(beat.id)
        matched = [card for card in cards.cards if card.beat_id == beat.id]
        if len(matched) != 4:
            raise ContractViolation(f"authored beat {beat.id} missing four cards")
        required = tuple(claim.id for claim in beat.claims)
        for card in matched:
            lines.append(
                AuthoredLine(
                    id=card.id,
                    beat_id=beat.id,
                    pattern_id=card.id,
                    pattern=card.pattern,
                    placeholders=card.placeholders,
                    required_claims=required,
                    family=beat.realization.family,
                    policy_id=beat.policy.id,
                )
            )
    return AuthoredPack(
        schema_version=SCHEMA_VERSION,
        catalog_hash=cards.catalog_hash,
        beat_count=len(beat_ids),
        line_count=len(lines),
        beat_ids=tuple(beat_ids),
        lines=tuple(lines),
    )


def _lexicon_from_dict(raw: dict[str, Any]) -> SurfaceLexicon:
    sets = tuple(
        SurfaceValueSet(
            surface_value_set_id=str(item["surfaceValueSetId"]),
            fact_id=str(item["factId"]),
            attribute_id=str(item["attributeId"]),
            value_type=str(item["valueType"]),
            unit=item.get("unit"),
            forms=tuple(str(form) for form in item.get("forms") or ()),
        )
        for item in raw.get("surfaceValueSets") or ()
    )
    relations = tuple(
        RelationLexeme(
            claim_id=str(item["claimId"]),
            polarity=str(item.get("polarity") or "positive"),
            temporal_frame=str(item.get("temporalFrame") or "current"),
            forms=tuple(str(form) for form in item.get("forms") or () if str(form).strip()),
        )
        for item in raw.get("relationLexemes") or ()
    )
    return SurfaceLexicon(
        surface_value_sets=sets,
        relation_lexemes=relations,
        connectives=tuple(str(item) for item in raw.get("connectives") or ()),
        forbidden_lexemes=tuple(str(item) for item in raw.get("forbiddenLexemes") or ()),
        subject_surface=str(raw.get("subjectSurface") or ""),
        subject_actor_id=str(raw.get("subjectActorId") or ""),
    )


def authored_bundle(
    *,
    beat_id: str,
    backend: str,
    pattern_id: str,
    max_chars: int,
    max_seconds: float,
    required_claim_ids: tuple[str, ...],
    selected_fact_ids: tuple[str, ...],
    planned_mono_ms: int,
    expires_mono_ms: int,
    language: str,
    actor_bindings: tuple[tuple[str, tuple[str, ...]], ...],
    fact_bindings: tuple[tuple[str, str], ...],
    lexicon: dict[str, Any],
) -> RealizationBundle:
    """Pure bundle constructor. Does not read a live ledger, roster or config."""

    surface = _lexicon_from_dict(lexicon)
    fact_payload = [
        {"factId": fact_id, "predicate": predicate} for fact_id, predicate in fact_bindings
    ]
    actor_payload = [
        {"actorId": actor_id, "aliases": list(aliases)} for actor_id, aliases in actor_bindings
    ]
    plan_payload = {
        "backend": backend,
        "beatId": beat_id,
        "expiresMonoMs": expires_mono_ms,
        "language": language,
        "maxChars": max_chars,
        "maxSeconds": max_seconds,
        "patternId": pattern_id,
        "plannedMonoMs": planned_mono_ms,
        "requiredClaimIds": list(required_claim_ids),
        "selectedFactIds": list(selected_fact_ids),
    }
    fact_hash = str(canonical_sha256(fact_payload))
    lexicon_hash = str(canonical_sha256(surface.canonical()))
    bundle_hash = str(
        canonical_sha256(
            {
                "actorBindings": actor_payload,
                "beatPlan": plan_payload,
                "factBindings": fact_payload,
                "surfaceLexicon": surface.canonical(),
            }
        )
    )
    digest = bundle_hash.removeprefix("sha256:")
    return RealizationBundle(
        schema_version=BUNDLE_SCHEMA,
        bundle_id=f"rb:{digest[:32]}",
        beat_id=beat_id,
        backend=backend,
        pattern_id=pattern_id,
        max_chars=max_chars,
        max_seconds=max_seconds,
        required_claim_ids=required_claim_ids,
        selected_fact_ids=selected_fact_ids,
        planned_mono_ms=planned_mono_ms,
        expires_mono_ms=expires_mono_ms,
        language=language,
        actor_bindings=actor_bindings,
        fact_bindings=fact_bindings,
        surface_lexicon=surface,
        fact_binding_hash=fact_hash,
        surface_lexicon_hash=lexicon_hash,
        bundle_hash=bundle_hash,
    )


def _failed(reason: str, *, backend: str, latency: dict[str, int] | None) -> AuthoredStep:
    return AuthoredStep(
        schema_version=SCHEMA_VERSION,
        outcome="failed",
        reason=reason,
        backend=backend,
        text=None,
        text_hash=None,
        line_id=None,
        used_live_view=False,
        used_roster=False,
        used_config=False,
        latency_ms=latency,
    )


def _select_line(
    pack: AuthoredPack,
    beat_id: str,
    pattern_id: str,
    spoken_line_ids: tuple[str, ...],
) -> AuthoredLine | None:
    lines = pack.lines_for(beat_id)
    if not lines:
        return None
    unused = tuple(line for line in lines if line.id not in spoken_line_ids)
    pool = unused or lines
    for line in pool:
        if line.pattern_id == pattern_id:
            return line
    return pool[0]


def _fill(pattern: str, subject: str, claim: str) -> str:
    return (
        pattern.replace("{subjectSurface}", subject)
        .replace("{requiredClaimSurface}", claim)
        .replace("{subject_surface}", subject)
        .replace("{required_claim_surface}", claim)
    )


class AuthoredRealizer:
    """Render one authored EN line from a frozen bundle. Never a Qwen fallback."""

    def __init__(self, pack: AuthoredPack | None = None) -> None:
        self.pack = pack or load_authored_pack()

    def realize(
        self,
        bundle: RealizationBundle,
        *,
        now_ms: int,
        deadline_mono_ms: int | None = None,
        cancelled: bool = False,
        fallback: bool = False,
        spoken_line_ids: tuple[str, ...] = (),
        expected_bundle_hash: str | None = None,
    ) -> AuthoredStep:
        latency = {"plan_to_realize": int(now_ms) - bundle.planned_mono_ms}
        if fallback:
            return _failed("authored_fallback_forbidden", backend=bundle.backend, latency=latency)
        if bundle.backend != "authored":
            return _failed("authored_backend_required", backend=bundle.backend, latency=latency)
        if cancelled:
            return _failed("realization_cancelled", backend=bundle.backend, latency=latency)
        expired = int(now_ms) >= bundle.expires_mono_ms
        timed_out = deadline_mono_ms is not None and int(now_ms) >= int(deadline_mono_ms)
        if expired or timed_out:
            return _failed("realization_timeout", backend=bundle.backend, latency=latency)
        if expected_bundle_hash is not None and expected_bundle_hash != bundle.bundle_hash:
            return _failed("realization_input_invalid", backend=bundle.backend, latency=latency)
        if bundle.language != "en":
            return _failed("realization_input_invalid", backend=bundle.backend, latency=latency)
        line = _select_line(self.pack, bundle.beat_id, bundle.pattern_id, spoken_line_ids)
        if line is None:
            return _failed("unknown_authored_beat", backend=bundle.backend, latency=latency)
        subject = bundle.surface_lexicon.subject_surface.strip()
        if not subject and bundle.actor_bindings:
            subject = bundle.actor_bindings[0][1][0]
        claim_id = bundle.required_claim_ids[0] if bundle.required_claim_ids else ""
        claim = bundle.surface_lexicon.claim_surface(claim_id).strip()
        if not subject or not claim:
            return _failed("realization_input_invalid", backend=bundle.backend, latency=latency)
        text = _fill(line.pattern, subject, claim).strip()
        if "{" in text or "}" in text:
            return _failed("realization_input_invalid", backend=bundle.backend, latency=latency)
        lowered = text.casefold()
        forbidden = tuple(bundle.surface_lexicon.forbidden_lexemes) + tuple(UNSAFE_COLOR)
        if any(token in lowered for token in forbidden):
            return _failed("forbidden_claim", backend=bundle.backend, latency=latency)
        if len(text) > bundle.max_chars:
            return _failed("realization_output_oversize", backend=bundle.backend, latency=latency)
        if not text.endswith("."):
            return _failed("realization_input_invalid", backend=bundle.backend, latency=latency)
        return AuthoredStep(
            schema_version=SCHEMA_VERSION,
            outcome="succeeded",
            reason="succeeded",
            backend="authored",
            text=text,
            text_hash=str(canonical_sha256({"text": text})),
            line_id=line.id,
            used_live_view=False,
            used_roster=False,
            used_config=False,
            latency_ms=latency,
        )
