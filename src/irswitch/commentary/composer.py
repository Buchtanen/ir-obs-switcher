"""Grounded commentary plans: authored anchor plus explicit factual propositions."""

from __future__ import annotations

import math
import random
import re
import zlib
from dataclasses import dataclass
from typing import Any

from irswitch.commentary.anti_repeat import RecentUtteranceHistory, prefer_fresh_candidates
from irswitch.commentary.graph import GraphEdge, GraphNode, SequenceGraph, scenario_selectors
from irswitch.commentary.microplan import CommentaryMicroplan
from irswitch.commentary.story_identity import edge_identity_matches
from irswitch.commentary.style_cards import select_style_card
from irswitch.commentary.validator import fill_slots, leftover_slots
from irswitch.events.envelope import EventEnvelope, make_envelope

FACT_PACK_VERSION = "commentary-facts/3"
MAX_FACTS = 2
MAX_GRAPH_NODES = 3
_SLOT = re.compile(r"\{([a-z0-9_]+)\}", re.IGNORECASE)


@dataclass(frozen=True)
class CompositionResult:
    text: str
    fact_count: int
    graph_path: tuple[str, ...]
    tree_path: tuple[str, ...]
    fact_pack: dict[str, Any]


@dataclass(frozen=True)
class _Clause:
    kind: str
    text: str
    fact_keys: tuple[str, ...]


@dataclass(frozen=True)
class _BeatRef:
    node_id: str
    event_type: str
    phase: str
    mode: str
    correlation_id: str
    monotonic_ms: int
    target_name: str | None = None
    envelope: EventEnvelope | None = None


def build_skeleton(
    envelope: EventEnvelope,
    node: GraphNode | None,
    *,
    graph: SequenceGraph,
    story: dict[str, Any] | None,
    bindings: dict[str, object],
    emotion: str,
    language: str,
    recent: RecentUtteranceHistory | None = None,
    rng: random.Random | None = None,
) -> CompositionResult | None:
    """Build a grounded plan around one safe, fully-bound authored anchor.

    ``text`` is a complete canonical fallback. Only selected propositions, not
    unrelated position/laps/phase telemetry, are available for realization.
    """
    if node is None:
        return None
    context = story if isinstance(story, dict) else {}
    cs = language.lower().startswith("cs")
    graph_path = _graph_path(envelope, node, graph, context)
    anchor = _authored_anchor_clause(
        node,
        bindings,
        language=language,
        emotion=emotion,
        recent=recent,
        rng=rng,
    )
    if anchor is None:
        return None

    primary, details = _current_clauses(
        envelope,
        node,
        bindings,
        cs=cs,
        language=language,
        emotion=emotion,
        recent=recent,
    )
    # For events without a structured relation clause, the authored anchor is
    # itself the required proposition. It is also the universal safe fallback.
    if primary is None or any(key.startswith("authored:") for key in primary.fact_keys):
        primary = _Clause("beat", _strip_terminal(anchor.text), ("beat:event",))
    required = [primary]
    optional_candidates = details
    optional: list[_Clause] = []
    selected_ids = {_fact_id(primary)}
    for clause in optional_candidates:
        fact_id = _fact_id(clause)
        if fact_id in selected_ids:
            continue
        optional.append(clause)
        selected_ids.add(fact_id)
        if len(required) + len(optional) >= MAX_FACTS:
            break

    text = _join_clauses(required)
    selected_facts = [_fact_id(clause) for clause in [*required, *optional]]
    fact_pack = _fact_pack(
        envelope,
        node,
        graph,
        context,
        bindings,
        emotion,
        graph_path,
        selected_facts,
        anchor=_ensure_terminal(anchor.text),
        required=required,
        optional=optional,
    )
    relation = _relation(envelope.event_type)
    # Wire RESULT is also used for ongoing observations; it is not itself an outcome.
    resolved = envelope.event_type.upper() in {
        "OVERTAKE",
        "BATTLE_WON",
        "POSITION_GAINED",
        "POSITION_LOST",
        "FINISH",
        "SESSION_WRAP",
    }
    state = "resolved" if resolved else "live"
    card = select_style_card(
        node.style_cards,
        relation,
        state,
        len(required),
        index=zlib.crc32(envelope.event_id.encode()),
    )
    roles = tuple(
        (role, value)
        for role, key in (
            ("hero", "hero_name"),
            ("target", "target_name"),
            ("front", "front_target_name"),
            ("rear", "rear_target_name"),
        )
        if (value := _bound(bindings, key))
    )
    microplan = CommentaryMicroplan(
        family=node.family,
        relation=relation,
        story_state=state,
        density="multi_role" if relation == "hero_between_two_fronts" else "single",
        actor_roles=roles,
        required_ids=tuple(_fact_id(c) for c in required),
        optional_ids=tuple(_fact_id(c) for c in optional),
        style_card_id=card.id,
        canonical=text,
        source_correlation=envelope.correlation_id,
        run_epoch=_int(envelope.metrics.get("runEpoch")) or 0,
        source_revision=int(envelope.monotonic_ms or 0),
    )
    fact_pack["microplan"] = microplan.to_dict()
    example_values = {**dict(roles), "position": _bound(bindings, "position")}
    example = card.example(language)
    placeholders = _SLOT.findall(example)
    if any(not example_values.get(key) for key in placeholders):
        example = ""
    else:
        example = example.format_map(example_values)
    fact_pack["style_card"] = {"id": card.id, "guidance": card.guidance, "example": example}
    fact_pack["canonical"] = text
    return CompositionResult(
        text=text,
        fact_count=len(required) + len(optional),
        graph_path=graph_path,
        tree_path=("anchor", "required", *(clause.kind for clause in optional)),
        fact_pack=fact_pack,
    )


def _graph_path(
    envelope: EventEnvelope,
    node: GraphNode,
    graph: SequenceGraph,
    context: dict[str, Any],
) -> tuple[str, ...]:
    current = _BeatRef(
        node_id=node.id,
        event_type=envelope.event_type,
        phase=envelope.phase,
        mode=envelope.mode,
        correlation_id=envelope.correlation_id,
        monotonic_ms=int(envelope.monotonic_ms or 0),
        target_name=(envelope.target.display_name if envelope.target is not None else None),
        envelope=envelope,
    )
    refs = _history_refs(graph, context)
    chain: list[_BeatRef] = [current]
    cursor = current
    cursor_index = len(refs)
    while len(chain) < MAX_GRAPH_NODES:
        found: tuple[int, _BeatRef] | None = None
        for index in range(cursor_index - 1, -1, -1):
            prior = refs[index]
            edge = _matching_edge(graph, prior, cursor)
            if edge is not None:
                found = (index, prior)
                break
        if found is None:
            break
        cursor_index, cursor = found
        chain.insert(0, cursor)
    return tuple(ref.node_id for ref in chain)


def _history_refs(graph: SequenceGraph, context: dict[str, Any]) -> list[_BeatRef]:
    story = context.get("story")
    story = story if isinstance(story, dict) else {}
    raw_beats = story.get("recent_beats")
    if not isinstance(raw_beats, list):
        raw_beats = list(raw_beats) if isinstance(raw_beats, tuple) else []
    refs: list[_BeatRef] = []
    for raw in raw_beats:
        if not isinstance(raw, dict):
            continue
        event_type = str(raw.get("event_type") or "").upper()
        phase = str(raw.get("phase") or "").upper()
        mode = str(raw.get("mode") or "")
        branch = raw.get("branch")
        candidates = graph.nodes_for(
            event_type,
            phase,
            mode=mode,
            branch=str(branch) if branch not in (None, "") else None,
            **scenario_selectors(raw, raw.get("confidence", 1.0)),
        )
        if not candidates:
            continue
        refs.append(
            _BeatRef(
                node_id=candidates[0].id,
                event_type=event_type,
                phase=phase,
                mode=mode,
                correlation_id=str(raw.get("correlation_id") or ""),
                monotonic_ms=_int(raw.get("monotonic_ms")) or 0,
                target_name=_text(raw.get("target_name")),
                envelope=make_envelope(
                    event_type=event_type,
                    phase=phase,
                    mode=mode,
                    session_id=str(raw.get("session_id") or ""),
                    correlation_id=str(raw.get("correlation_id") or ""),
                    subject={"car_id": str(raw.get("hero_id") or "player")},
                    metrics={
                        "runEpoch": raw.get("run_epoch"),
                        "scenarioId": raw.get("scenario_id"),
                        "parentStoryId": raw.get("parent_story_id"),
                    },
                ),
            )
        )
    return refs


def _matching_edge(
    graph: SequenceGraph,
    prior: _BeatRef,
    current: _BeatRef,
) -> GraphEdge | None:
    gap_s = max(0.0, (current.monotonic_ms - prior.monotonic_ms) / 1000.0)
    for edge in graph.outgoing(prior.node_id):
        if not edge.legacy_identity_compatible:
            if (
                prior.envelope is None
                or current.envelope is None
                or not edge_identity_matches(edge, prior.envelope, current.envelope)
            ):
                continue
        if edge.target != current.node_id:
            continue
        if gap_s < edge.min_gap_s or gap_s > edge.max_gap_s:
            continue
        if (
            edge.same_correlation
            and prior.correlation_id
            and current.correlation_id
            and prior.correlation_id != current.correlation_id
        ):
            continue
        return edge
    return None


def _history_clause(
    graph_path: tuple[str, ...],
    graph: SequenceGraph,
    context: dict[str, Any],
    *,
    cs: bool,
) -> _Clause | None:
    if len(graph_path) < 2:
        return None
    refs = _history_refs(graph, context)
    labels: list[str] = []
    keys: list[str] = []
    for node_id in graph_path[:-1]:
        beat = next((item for item in reversed(refs) if item.node_id == node_id), None)
        target = beat.target_name if beat is not None else None
        label = _history_label(node_id, target, cs=cs)
        if label:
            labels.append(label)
            keys.append(f"history:{node_id}")
    if not labels:
        return None
    if cs:
        text = "Příběh vedl " + _join_labels(labels, cs=True)
    else:
        text = "The story moved " + _join_labels(labels, cs=False)
    return _Clause("history", text, tuple(keys))


def _history_label(node_id: str, target: str | None, *, cs: bool) -> str:
    if cs:
        labels = {
            "hunting": f"od stíhání {target}" if target else "od stíhání",
            "attack_range": "přes přípravu útoku",
            "side_by_side": f"k jízdě vedle {target}" if target else "k jízdě vedle sebe",
            "hunted": f"od tlaku jezdce {target}" if target else "od tlaku zezadu",
            "pit_entry": "od nájezdu do boxů",
            "pit_stopped": "přes zastávku v boxech",
            "overtake": "přes dokončené předjetí",
            "rival_threat": "od rostoucí hrozby soupeře",
            "gain_found": "od nalezeného tempa",
            "hot_lap": "od rychlého kola",
            "final_lap": "od posledního kola",
            "incident": "od změny bodového součtu",
            "incident_aftermath": "přes jeho následky",
            "session_checkered": "od šachovnicové vlajky",
            "session_wrap": "přes shrnutí jízdy",
            "leader_change": (f"od změny lídra na {target}" if target else "od změny lídra"),
        }
    else:
        labels = {
            "hunting": f"from the chase of {target}" if target else "from the chase",
            "attack_range": "through attack range",
            "side_by_side": f"to side by side with {target}" if target else "to side by side",
            "hunted": f"from pressure by {target}" if target else "from pressure behind",
            "pit_entry": "from pit entry",
            "pit_stopped": "through the pit stop",
            "overtake": "through the completed pass",
            "rival_threat": "from the growing rival threat",
            "gain_found": "from the pace he found",
            "hot_lap": "from the quick lap",
            "final_lap": "from the final lap",
            "incident": "from the point-count update",
            "incident_aftermath": "through its aftermath",
            "session_checkered": "from the checkered flag",
            "session_wrap": "through the session wrap",
            "leader_change": (
                f"from the lead change to {target}" if target else "from the lead change"
            ),
        }
    return labels.get(node_id, "")


def _current_clauses(
    envelope: EventEnvelope,
    node: GraphNode,
    bindings: dict[str, object],
    *,
    cs: bool,
    language: str,
    emotion: str,
    recent: RecentUtteranceHistory | None,
) -> tuple[_Clause | None, list[_Clause]]:
    event = envelope.event_type.upper()
    name = _bound(bindings, "target_name")
    position = _positive_position(_bound(bindings, "position"))
    gap = _positive_metric(_bound(bindings, "gap"))
    lap = _positive_position(_bound(bindings, "lap") or _bound(bindings, "current_lap"))
    lap_time = _positive_metric(_bound(bindings, "lap_time"))
    delta = _nonzero_metric(_bound(bindings, "delta"))
    streak = _bound(bindings, "streak")
    front = _bound(bindings, "front_target_name")
    rear = _bound(bindings, "rear_target_name")
    front_gap = _positive_metric(_bound(bindings, "front_gap"))
    rear_gap = _positive_metric(_bound(bindings, "rear_gap"))
    details: list[_Clause] = []
    primary: _Clause | None

    if event in {"HUNTING", "APPROACH", "ATTACK_RANGE"}:
        if name:
            primary = _Clause(
                "beat",
                (
                    (f"Z {position}. místa stahuje {name}" if position else f"Stahuje {name}")
                    if cs
                    else (
                        f"He is closing on {name} from P{position}"
                        if position
                        else f"He is closing on {name}"
                    )
                ),
                (
                    ("target:name", "hero:position", "beat:relation")
                    if position
                    else ("target:name", "beat:relation")
                ),
            )
        else:
            primary = _Clause(
                "beat",
                "Stahuje vůz před sebou" if cs else "He is closing on the car ahead",
                ("beat:relation",),
            )
        if gap:
            details.append(
                _Clause(
                    "detail",
                    f"odstup je {gap}" if cs else f"the gap is {gap}",
                    ("target:gap",),
                )
            )
        return primary, details

    if event == "HUNTED":
        primary = _Clause(
            "beat",
            (
                (f"Zezadu tlačí {name}" if name else "Tlak přichází zezadu")
                if cs
                else (
                    f"{name} is applying pressure from behind"
                    if name
                    else "Pressure is arriving from behind"
                )
            ),
            ("target:name", "beat:relation") if name else ("beat:relation",),
        )
        if gap:
            details.append(
                _Clause(
                    "detail", f"odstup je {gap}" if cs else f"the gap is {gap}", ("target:gap",)
                )
            )
        return primary, details

    if event == "BATTLE_FOR_POSITION":
        if front and rear:
            primary = _Clause(
                "beat",
                (
                    f"Vpředu útočí na {front}, zatímco zezadu tlačí {rear}"
                    if cs
                    else f"He attacks {front} ahead while {rear} applies pressure behind"
                ),
                ("front:name", "rear:name"),
            )
        else:
            primary = _Clause(
                "beat",
                (
                    "Současně útočí vpředu a brání zezadu"
                    if cs
                    else "He is attacking ahead while defending from behind"
                ),
                ("beat:two_front",),
            )
        if front_gap and rear_gap:
            details.append(
                _Clause(
                    "detail",
                    (
                        f"vpředu je {front_gap} a vzadu {rear_gap}"
                        if cs
                        else f"the margins are {front_gap} ahead and {rear_gap} behind"
                    ),
                    ("front:gap", "rear:gap"),
                )
            )
        return primary, details

    if event in {"OVERTAKE", "POSITION_GAINED", "BATTLE_WON"}:
        if position and name and event != "POSITION_GAINED":
            return (
                _Clause(
                    "beat",
                    (
                        f"Předjíždí {name} a bere {position}. místo"
                        if cs
                        else f"He passes {name} and takes P{position}"
                    ),
                    ("target:name", "hero:position"),
                ),
                details,
            )
        if position:
            return (
                _Clause(
                    "beat",
                    f"Posouvá se na {position}. místo" if cs else f"He moves up to P{position}",
                    ("hero:position", "beat:gain"),
                ),
                details,
            )
        if event == "POSITION_GAINED":
            return (
                _Clause("beat", "Získává pozici" if cs else "He gains a position", ("beat:gain",)),
                details,
            )

    if event == "LEADER_CHANGE":
        old_leader = _bound(bindings, "leader_name") or _bound(bindings, "old_leader_name")
        if name and old_leader:
            return (
                _Clause(
                    "beat",
                    (
                        f"{name} přebírá vedení po {old_leader}"
                        if cs
                        else f"{name} takes the lead from {old_leader}"
                    ),
                    ("target:name", "leader:name"),
                ),
                details,
            )
        if name:
            return (
                _Clause(
                    "beat",
                    f"{name} jde do čela" if cs else f"{name} takes the lead",
                    ("target:name", "beat:lead"),
                ),
                details,
            )

    if event == "SESSION_WRAP":
        p1 = _bound(bindings, "p1_name")
        p2 = _bound(bindings, "p2_name")
        p3 = _bound(bindings, "p3_name")
        extra: list[_Clause] = []
        if p1 and p2 and p3:
            extra.append(
                _Clause(
                    "detail",
                    (
                        f"první tři: {p1}, {p2}, {p3}"
                        if cs
                        else f"the top three are {p1}, {p2}, and {p3}"
                    ),
                    ("field:podium",),
                )
            )
        if position:
            return (
                _Clause(
                    "beat",
                    (
                        f"končí na {position}. místě"
                        if cs
                        else f"He finishes the session in P{position}"
                    ),
                    ("hero:position", "beat:wrap"),
                ),
                extra,
            )
        if extra:
            return extra[0], extra[1:]

    if event == "POSITION_LOST":
        if position and name:
            return (
                _Clause(
                    "beat",
                    (
                        f"Za {name} klesá na {position}. místo"
                        if cs
                        else f"He drops behind {name} to P{position}"
                    ),
                    ("target:name", "hero:position"),
                ),
                details,
            )
        if position:
            return (
                _Clause(
                    "beat",
                    f"Klesá na {position}. místo" if cs else f"He drops to P{position}",
                    ("hero:position", "beat:loss"),
                ),
                details,
            )
        return (
            _Clause("beat", "Ztrácí pozici" if cs else "He loses a position", ("beat:loss",)),
            details,
        )

    if event == "FINISH":
        # A FINISH event does not guarantee a confirmed final classification.
        return (
            _Clause(
                "beat", "Jeho závod skončil" if cs else "His race is complete", ("beat:finish",)
            ),
            details,
        )

    if event in {"LAP_COMPLETE", "PERSONAL_BEST", "HOT_LAP"}:
        if lap and lap_time:
            primary = _Clause(
                "beat",
                (
                    f"Dokončuje {lap}. kolo v čase {lap_time}"
                    if cs
                    else f"He completes lap {lap} in {lap_time}"
                ),
                ("session:lap", "hero:lap_time"),
            )
        elif lap_time:
            primary = _Clause(
                "beat",
                f"Zapisuje čas {lap_time}" if cs else f"He records a lap of {lap_time}",
                ("hero:lap_time", "beat:lap"),
            )
        else:
            primary = None
        if delta:
            details.append(
                _Clause(
                    "detail",
                    f"zlepšení je {delta}" if cs else f"the gain is {delta}",
                    ("hero:delta",),
                )
            )
        if streak:
            details.append(
                _Clause(
                    "detail",
                    (
                        f"je to {streak}. osobní zlepšení v řadě"
                        if cs
                        else f"it is personal best number {streak} in a row"
                    ),
                    ("hero:streak",),
                )
            )
        if primary is not None:
            return primary, details

    authored = _richest_authored_clause(
        node,
        bindings,
        language=language,
        emotion=emotion,
        recent=recent,
    )
    return authored, details


def _authored_anchor_clause(
    node: GraphNode,
    bindings: dict[str, object],
    *,
    language: str,
    emotion: str,
    recent: RecentUtteranceHistory | None,
    rng: random.Random | None = None,
) -> _Clause | None:
    candidates: list[tuple[str, tuple[str, ...]]] = []
    authored = node.variant_bucket(language, emotion)
    if not authored:
        locale_map = node.variants.get(language) or node.variants.get("en") or {}
        for state in node.hr_states:
            authored = locale_map.get(state) or locale_map.get("neutral") or ()
            if authored:
                break
    for raw in authored:
        names = tuple(dict.fromkeys(_SLOT.findall(raw)))
        bound = tuple(name for name in names if _bound(bindings, name) is not None)
        text = fill_slots(raw, bindings).strip()
        if not text or leftover_slots(text):
            continue
        candidates.append((text, bound))
    if not candidates:
        return None
    ordered = [item[0] for item in candidates]
    fresh = prefer_fresh_candidates(ordered, recent)
    text = rng.choice(fresh) if rng is not None else fresh[0]
    selected = next(item for item in candidates if item[0] == text)
    keys = tuple(f"authored:{name}" for name in selected[1]) or ("beat:event",)
    return _Clause("beat", _strip_terminal(text), keys)


def _richest_authored_clause(
    node: GraphNode,
    bindings: dict[str, object],
    *,
    language: str,
    emotion: str,
    recent: RecentUtteranceHistory | None,
) -> _Clause | None:
    """Compatibility fallback for unstructured events; selection is no longer richest-first."""
    return _authored_anchor_clause(
        node,
        bindings,
        language=language,
        emotion=emotion,
        recent=recent,
    )


def _context_clauses(
    context: dict[str, Any],
    *,
    used: set[str],
    cs: bool,
) -> list[_Clause]:
    race = context.get("race")
    race = race if isinstance(race, dict) else {}
    situation = context.get("situation")
    situation = situation if isinstance(situation, dict) else {}
    out: list[_Clause] = []
    position = _int(race.get("class_position") or race.get("position"))
    if position and "hero:position" not in used:
        out.append(
            _Clause(
                "context",
                f"drží {position}. místo" if cs else f"he is running P{position}",
                ("hero:position",),
            )
        )
    remaining = _int(situation.get("laps_remaining"))
    if remaining is not None and remaining >= 0 and "session:remaining" not in used:
        out.append(
            _Clause(
                "session",
                f"zbývá {remaining} kol" if cs else f"there are {remaining} laps remaining",
                ("session:remaining",),
            )
        )
    phase = _text(situation.get("race_phase"))
    if phase and phase != "unknown" and "session:phase" not in used:
        if cs:
            labels = {"opening": "úvodní", "middle": "střední", "closing": "závěrečná"}
            text = f"závod je v {labels.get(phase, phase)} fázi"
        else:
            text = f"the race is in its {phase} phase"
        out.append(_Clause("session", text, ("session:phase",)))
    return out


def _fact_pack(
    envelope: EventEnvelope,
    node: GraphNode,
    graph: SequenceGraph,
    context: dict[str, Any],
    bindings: dict[str, object],
    emotion: str,
    graph_path: tuple[str, ...],
    selected_facts: list[str],
    *,
    anchor: str,
    required: list[_Clause],
    optional: list[_Clause],
) -> dict[str, Any]:
    race = context.get("race")
    race = race if isinstance(race, dict) else {}
    situation = context.get("situation")
    situation = situation if isinstance(situation, dict) else {}
    story = context.get("story")
    story = story if isinstance(story, dict) else {}
    target = {
        key: value
        for key, value in {
            "name": _bound(bindings, "target_name"),
            "gap": _positive_metric(_bound(bindings, "gap")),
        }.items()
        if value is not None
    }
    front_target = _compact(
        {
            "name": _bound(bindings, "front_target_name"),
            "gap": _positive_metric(_bound(bindings, "front_gap")),
            "position": _positive_position(_bound(bindings, "front_position")),
        }
    )
    rear_target = _compact(
        {
            "name": _bound(bindings, "rear_target_name"),
            "gap": _positive_metric(_bound(bindings, "rear_gap")),
        }
    )
    ahead_raw = story.get("ahead")
    behind_raw = story.get("behind")
    ahead: list[Any] = ahead_raw if isinstance(ahead_raw, list) else []
    behind: list[Any] = behind_raw if isinstance(behind_raw, list) else []
    allowed_names = _allowed_names(bindings, ahead, behind)
    selected_text = " ".join(clause.text for clause in [*required, *optional])
    allowed_numbers = _allowed_numbers(selected_text)
    allowed_names = [name for name in allowed_names if name.casefold() in selected_text.casefold()]
    return {
        "version": FACT_PACK_VERSION,
        "anchor": anchor,
        "required_facts": [
            _proposition(
                clause,
                allowed_names=allowed_names,
                provenance="event",
                relation=_relation(envelope.event_type),
            )
            for clause in required
        ],
        "optional_facts": [
            _proposition(clause, allowed_names=allowed_names, provenance=clause.kind)
            for clause in optional
        ],
        "forbidden_claims": _forbidden_claims(envelope.event_type),
        "allowed_names": allowed_names,
        "allowed_numbers": allowed_numbers,
        "beat": {
            "node": node.id,
            "event": envelope.event_type,
            "phase": envelope.phase,
            "family": node.family,
            "relation": _relation(envelope.event_type),
            "next_possible": [edge.target for edge in graph.outgoing(node.id)],
            "emotion": emotion,
            "graph_path": list(graph_path),
            "selected_facts": list(selected_facts),
        },
        "session": _compact(
            {
                "mode": envelope.mode,
                "lap": situation.get("current_lap") or _bound(bindings, "lap"),
                "laps_remain": situation.get("laps_remaining"),
                "is_final_lap": situation.get("is_final_lap"),
                "race_phase": situation.get("race_phase"),
            }
        ),
        "hero": _compact(
            {
                "class_position": (
                    _positive_position(_bound(bindings, "position"))
                    or race.get("class_position")
                    or race.get("position")
                ),
                "lap_time": _bound(bindings, "lap_time"),
                "delta": _bound(bindings, "delta"),
                "streak": _bound(bindings, "streak"),
            }
        ),
        "target": target,
        "front_target": front_target,
        "rear_target": rear_target,
        "field": {"ahead": ahead[:2], "behind": behind[:2]},
        "bio": {"hr_band": emotion},
    }


def _relation(event_type: str) -> str:
    return {
        "HUNTING": "hero_closing_on_target",
        "APPROACH": "hero_closing_on_target",
        "ATTACK_RANGE": "hero_closing_on_target",
        "HUNTED": "target_closing_on_hero",
        "OVERTAKE": "hero_passed_target",
        "POSITION_GAINED": "hero_gained_position",
        "POSITION_LOST": "hero_lost_position",
        "BATTLE_FOR_POSITION": "hero_between_two_fronts",
        "LEADER_CHANGE": "class_leader_changed",
        "SESSION_WRAP": "session_result",
        "FINISH": "session_result",
    }.get(event_type.upper(), "factual_beat")


def _fact_id(clause: _Clause) -> str:
    return next((key for key in clause.fact_keys if key.startswith("beat:")), clause.fact_keys[0])


def _proposition(
    clause: _Clause,
    *,
    allowed_names: list[str],
    provenance: str,
    relation: str | None = None,
) -> dict[str, Any]:
    folded = clause.text.casefold()
    required_terms = [
        name.split()[-1] for name in allowed_names if name.casefold() in folded and name.split()
    ]
    proposition = {
        "id": _fact_id(clause),
        "text": _ensure_terminal(clause.text),
        "provenance": provenance,
        "required_terms": required_terms,
        "required_numbers": [match.group(0) for match in _NUMBER_LITERAL.finditer(clause.text)],
    }
    if relation:
        proposition["relation"] = relation
    return proposition


def _forbidden_claims(event_type: str) -> list[str]:
    event = event_type.upper()
    claims: list[str] = []
    if event in {
        "HUNTING",
        "APPROACH",
        "ATTACK_RANGE",
        "HUNTED",
        "LEADER_CHANGE",
        "POSITION_GAINED",
    }:
        claims.append("on_track_pass")
    if event in {"HUNTING", "APPROACH", "ATTACK_RANGE", "HUNTED"}:
        claims.append("hero_leads")
    if event == "POSITION_LOST":
        claims.append("position_gain")
    return claims


def _allowed_names(
    bindings: dict[str, object],
    ahead: list[Any],
    behind: list[Any],
) -> list[str]:
    names: list[str] = []
    entity_keys = {"track", "mode", "hero_car", "target_car", "target_nationality"}
    for key, value in bindings.items():
        if ("name" in key or key in entity_keys) and (text := _text(value)):
            names.append(text)
    for item in [*ahead, *behind]:
        if isinstance(item, dict):
            text = _text(item.get("name") or item.get("display_name"))
            if text:
                names.append(text)
    return list(dict.fromkeys(names))


_NUMBER_LITERAL = re.compile(r"-?\d+(?:(?:[.:])\d+)*")


def _allowed_numbers(*sources: object) -> list[str]:
    found: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                visit(nested)
            return
        if isinstance(value, (list, tuple)):
            for nested in value:
                visit(nested)
            return
        if isinstance(value, bool) or value is None:
            return
        for match in _NUMBER_LITERAL.finditer(str(value)):
            found.append(match.group(0))

    for source in sources:
        visit(source)
    return list(dict.fromkeys(found))


def _join_labels(labels: list[str], *, cs: bool) -> str:
    if len(labels) == 1:
        return labels[0]
    return " a ".join(labels) if cs else " and ".join(labels)


def _join_clauses(clauses: list[_Clause]) -> str:
    parts = [_strip_terminal(clause.text) for clause in clauses if clause.text.strip()]
    if not parts:
        return ""
    return ". ".join(part[:1].upper() + part[1:] for part in parts) + "."


def _strip_terminal(text: str) -> str:
    return text.strip().rstrip(".!?…").strip()


def _ensure_terminal(text: str) -> str:
    clean = text.strip()
    if not clean:
        return clean
    return clean if clean[-1] in ".!?…" else clean + "."


def _fact_keys(clauses: list[_Clause]) -> set[str]:
    return {key for clause in clauses for key in clause.fact_keys}


def _bound(bindings: dict[str, object], name: str) -> str | None:
    value = bindings.get(name)
    return _text(value)


def _text(value: object) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _int(value: object) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _numeric(value: str | None) -> float | None:
    if not value:
        return None
    match = _NUMBER_LITERAL.search(value.replace(",", "."))
    if match is None:
        return None
    raw = match.group(0)
    try:
        if ":" in raw:
            parts = [float(part) for part in raw.split(":")]
            parsed = sum(
                part * (60 ** (len(parts) - index - 1)) for index, part in enumerate(parts)
            )
        else:
            parsed = float(raw)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _positive_metric(value: str | None) -> str | None:
    parsed = _numeric(value)
    return value if parsed is not None and parsed > 0 else None


def _nonzero_metric(value: str | None) -> str | None:
    parsed = _numeric(value)
    return value if parsed is not None and parsed != 0 else None


def _positive_position(value: str | None) -> str | None:
    parsed = _numeric(value)
    return str(int(parsed)) if parsed is not None and parsed > 0 and parsed.is_integer() else None


def _compact(values: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value not in (None, "")}
