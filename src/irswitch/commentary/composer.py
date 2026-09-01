"""Deterministic fact-pack and multi-node graph-path skeleton composer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from irswitch.commentary.anti_repeat import RecentUtteranceHistory, prefer_fresh_candidates
from irswitch.commentary.graph import GraphEdge, GraphNode, SequenceGraph
from irswitch.commentary.validator import fill_slots, leftover_slots
from irswitch.events.envelope import EventEnvelope

FACT_PACK_VERSION = "commentary-facts/1"
MAX_FACTS = 4
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
) -> CompositionResult | None:
    """Compose two to four facts by walking history → beat → detail → context.

    The sequence graph still decides valid temporal transitions. RaceObserver's
    frozen ``recent_beats`` supplies prior facts; no live observer reference or
    LLM inference is used here.
    """
    if node is None:
        return None
    context = story if isinstance(story, dict) else {}
    cs = language.lower().startswith("cs")
    graph_path = _graph_path(envelope, node, graph, context)
    clauses: list[_Clause] = []

    history_clause = _history_clause(graph_path, graph, context, cs=cs)
    if history_clause is not None:
        clauses.append(history_clause)

    primary, details = _current_clauses(
        envelope,
        node,
        bindings,
        cs=cs,
        language=language,
        emotion=emotion,
        recent=recent,
    )
    if primary is not None:
        clauses.append(primary)
    clauses.extend(details)
    clauses.extend(_context_clauses(context, used=_fact_keys(clauses), cs=cs))

    selected: list[_Clause] = []
    selected_facts: list[str] = []
    for clause in clauses:
        new_facts = [key for key in clause.fact_keys if key not in selected_facts]
        if not new_facts or len(selected_facts) + len(new_facts) > MAX_FACTS:
            continue
        candidate = _join_clauses([*selected, clause])
        if len(candidate) > node.tts.max_chars:
            continue
        selected.append(clause)
        selected_facts.extend(new_facts)
        if len(selected_facts) >= MAX_FACTS:
            break

    # A composer result must really be composed: at least two parts and facts.
    if len(selected) < 2 or len(selected_facts) < 2:
        return None
    text = _join_clauses(selected)
    fact_pack = _fact_pack(
        envelope,
        node,
        graph,
        context,
        bindings,
        emotion,
        graph_path,
        selected_facts,
        recent,
    )
    return CompositionResult(
        text=text,
        fact_count=len(selected_facts),
        graph_path=graph_path,
        tree_path=tuple(clause.kind for clause in selected),
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
            "incident": "od incidentu",
            "incident_aftermath": "přes jeho následky",
            "session_checkered": "od šachovnicové vlajky",
            "session_wrap": "přes shrnutí jízdy",
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
            "incident": "from the incident",
            "incident_aftermath": "through its aftermath",
            "session_checkered": "from the checkered flag",
            "session_wrap": "through the session wrap",
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
    position = _bound(bindings, "position")
    gap = _bound(bindings, "gap")
    lap = _bound(bindings, "lap") or _bound(bindings, "current_lap")
    lap_time = _bound(bindings, "lap_time")
    delta = _bound(bindings, "delta")
    streak = _bound(bindings, "streak")
    front = _bound(bindings, "front_target_name")
    rear = _bound(bindings, "rear_target_name")
    front_gap = _bound(bindings, "front_gap")
    rear_gap = _bound(bindings, "rear_gap")
    details: list[_Clause] = []

    if event in {"HUNTING", "APPROACH", "ATTACK_RANGE"}:
        if name:
            primary = _Clause(
                "beat",
                f"Stahuje {name}" if cs else f"He is closing on {name}",
                ("target:name", "beat:relation"),
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
        if position and name:
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


def _richest_authored_clause(
    node: GraphNode,
    bindings: dict[str, object],
    *,
    language: str,
    emotion: str,
    recent: RecentUtteranceHistory | None,
) -> _Clause | None:
    candidates: list[tuple[int, int, str, tuple[str, ...]]] = []
    for raw in node.variant_bucket(language, emotion):
        names = tuple(dict.fromkeys(_SLOT.findall(raw)))
        bound = tuple(name for name in names if _bound(bindings, name) is not None)
        text = fill_slots(raw, bindings).strip()
        if not text or leftover_slots(text):
            continue
        candidates.append((len(bound), len(text), text, bound))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    ordered = [item[2] for item in candidates]
    fresh = prefer_fresh_candidates(ordered, recent)
    text = fresh[0]
    selected = next(item for item in candidates if item[2] == text)
    keys = tuple(f"authored:{name}" for name in selected[3]) or ("beat:event",)
    return _Clause("beat", _strip_terminal(text), keys)


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
    recent: RecentUtteranceHistory | None,
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
            "gap": _bound(bindings, "gap"),
        }.items()
        if value is not None
    }
    front_target = _compact(
        {
            "name": _bound(bindings, "front_target_name"),
            "gap": _bound(bindings, "front_gap"),
            "position": _bound(bindings, "front_position"),
        }
    )
    rear_target = _compact(
        {
            "name": _bound(bindings, "rear_target_name"),
            "gap": _bound(bindings, "rear_gap"),
        }
    )
    ahead = story.get("ahead") if isinstance(story.get("ahead"), list) else []
    behind = story.get("behind") if isinstance(story.get("behind"), list) else []
    return {
        "version": FACT_PACK_VERSION,
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
                "class_position": race.get("class_position") or race.get("position"),
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
        "recent": list(recent.recent(4) if recent is not None else ()),
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
    }.get(event_type.upper(), "factual_beat")


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
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _compact(values: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value not in (None, "")}
