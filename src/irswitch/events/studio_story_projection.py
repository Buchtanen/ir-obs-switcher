"""Record world-event story instances, independently of speech and its outcome."""

import json
from collections.abc import Sequence
from functools import lru_cache

from irswitch.contracts.catalog_loader import NarrativeCatalog
from irswitch.contracts.narrative import NarrativeEvent
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.episode_registry import EpisodeIntent, EpisodeRegistry, MaterialOrder


@lru_cache(maxsize=1)
def _kind_sources():
    rows = json.loads(packaged_schema_bytes("freeze-registry.json"))["eventIdentifiers"]
    result: dict[str, list[str]] = {}
    for row in rows:
        if row.get("narrativeKind"):
            result.setdefault(row["narrativeKind"], []).append(row["id"])
    return result


def routed_beats(catalog: NarrativeCatalog, event: NarrativeEvent):
    sources = set(_kind_sources().get(str(event.kind), ()))
    sources.add(str(event.kind))
    if event.source_envelope is not None:
        sources = {str(event.source_envelope.event_type)}
    lifecycle = {
        "stream.started": "STREAM_STARTED",
        "session.started": "SESSION_STARTED",
        "session.ended": "SESSION_ENDED",
        "session.restarted": "SESSION_RESTARTED",
    }
    sources.add(lifecycle.get(str(event.kind), str(event.kind)))
    targets = {
        beat
        for source in sources
        for route in (catalog.route_event(source),)
        if route
        for beat in route.beat_ids
    }
    targets.update(b.id for b in catalog.beats if any(t.id in sources for t in b.triggers))
    if any(b.id == str(event.kind) for b in catalog.beats):
        targets.add(str(event.kind))
    stage = str(event.occurrence_id).split(":")[1] if event.occurrence_id is not None else None
    return tuple(
        b
        for b in catalog.beats
        if b.id in targets and (not b.stage_any_of or stage in b.stage_any_of)
    )


def observe_story_events(
    registry: EpisodeRegistry,
    catalog: NarrativeCatalog,
    events: Sequence[NarrativeEvent],
    *,
    reducer_sequence: int,
) -> int:
    recorded = 0
    for ordinal, event in enumerate(events):
        if str(event.kind) in {"STREAM_ENDED", "stream.ended"}:
            for current in registry.current():
                if current.scope == "stream":
                    registry.resolve(
                        current.episode_id,
                        now_ms=int(event.occurred_mono_ms),
                        reason="stream_ended",
                    )
            continue
        for beat in routed_beats(catalog, event):
            # All declared memberships are independent story instances. No first-match ownership.
            for story_id in beat.story_routes:
                stream = (
                    story_id == "stream_lifecycle"
                    or story_id == "filler_single"
                    and event.occurrence_id is None
                )
                if not stream and (event.occurrence_id is None or event.lineage_id is None):
                    continue
                correlations = tuple(str(v) for v in event.correlation_key)
                semantic = (
                    correlations or (f"stream:{event.stream_epoch}",)
                    if stream
                    else correlations or (str(event.occurrence_id),)
                )
                step = registry.open(
                    EpisodeIntent(
                        definition_id=story_id,
                        scope="stream" if stream else "occurrence",
                        occurrence_id=None if stream else str(event.occurrence_id),
                        lineage_id=None if stream else str(event.lineage_id),
                        semantic_identity=semantic,
                        correlation_ids=correlations,
                        fact_ids=tuple(str(v) for v in event.fact_ids),
                        material_order=MaterialOrder(reducer_sequence, ordinal),
                        now_ms=int(event.occurred_mono_ms),
                        continuation_priority=beat.policy.base_priority,
                        source_refs=(str(event.event_id),),
                    )
                )
                if step.episode is None:
                    continue
                identifier = step.episode.episode_id
                now = int(event.occurred_mono_ms)
                if event.phase in {"ended", "result"}:
                    registry.resolve(
                        identifier,
                        now_ms=now,
                        reason="outcome_observed" if event.phase == "result" else "natural_exit",
                    )
                elif step.episode.state == "candidate":
                    registry.activate(identifier, now_ms=now, source_refs=(str(event.event_id),))
                recorded += 1
    return recorded
