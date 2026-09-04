"""Dense commentary content, append patch, proposals, and viewer-voice contract."""

from __future__ import annotations

import json
import random
import re
from difflib import SequenceMatcher
from pathlib import Path

from irswitch.commentary.graph import GRAPH_VERSION, GraphNode, load_sequence_graph
from irswitch.commentary.validator import fill_slots, validate_utterance

ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "docs" / "commentary_extension_texts_patch.json"
PROPOSALS_PATH = ROOT / "docs" / "commentary_extension_proposals.json"

PRIORITY_NODES = {
    "lap_complete",
    "personal_best",
    "hunting",
    "hunted",
    "side_by_side",
    "overtake",
    "position_gained",
    "position_lost",
    "rival_threat",
    "battle_won",
    "final_lap",
    "finish",
    "pit_entry",
    "back_on_track",
    "in_car",
    "pit_outcome",
}
# W4/H4 session briefs landed from proposals at 10 lines/cell (not densified to 12).
SESSION_BRIEF_NODES = {
    "session_intro_practice",
    "session_intro_qualify",
    "session_intro_race",
    "sof_brief",
    "weather_brief",
}
TARGET_NAME_NODES = {"hunting", "hunted", "side_by_side", "overtake", "rival_threat"}


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized(text: str) -> str:
    without_slots = re.sub(r"\{[^}]+\}", "{slot}", text.lower())
    return re.sub(r"[^a-zá-ž0-9{} ]+", "", without_slots)


def _active_rows() -> list[tuple[GraphNode, str, str, str]]:
    rows: list[tuple[GraphNode, str, str, str]] = []
    for node in load_sequence_graph().nodes.values():
        for locale, buckets in node.variants.items():
            for emotion, lines in buckets.items():
                rows.extend((node, locale, emotion, line) for line in lines)
    return rows


WAVE_A_NODES = {
    "stream_start",
    "in_car_practice",
    "in_car_qualify",
    "in_car_race",
}
WAVE_A_DENSITY = 4
WAVE_B_NODES = {"incident_off_track", "incident_unknown"}
WAVE_C_NODES = {"session_flag_yellow", "session_flag_green", "session_flag_checkered"}
WAVE_D_NODES = {"quali_recap", "parade_pad"}
WAVE_LEADER_NODES = {"leader_change"}
WAVE_BCD_SPARSE = 1
WAVE_BD_DENSITY = 4
WAVE_LEADER_DENSITY = 3


def _expected_density(node_id: str) -> int:
    if node_id == "prepared_filler":
        # Schema-only fallback; audible text always comes from the validated buffer.
        return 4
    if node_id in {"incident", "track_excursion"}:
        return 4
    if node_id in {
        "stopped_after_excursion",
        "track_rejoined",
        "motion_restored",
        "tow_started_race",
        "pit_return_observed",
    }:
        return 2
    if node_id in PRIORITY_NODES:
        return 16
    if node_id in SESSION_BRIEF_NODES:
        return 10
    if node_id == "field_fact":
        return 16
    if node_id == "weather_change":
        return 13
    if node_id in WAVE_A_NODES:
        return WAVE_A_DENSITY
    if node_id in WAVE_C_NODES:
        return WAVE_BCD_SPARSE
    if node_id in WAVE_B_NODES or node_id in WAVE_D_NODES:
        return WAVE_BD_DENSITY
    if node_id in WAVE_LEADER_NODES:
        return WAVE_LEADER_DENSITY
    return 12


def test_every_active_cell_meets_density_and_all_lines_validate() -> None:
    graph = load_sequence_graph()
    assert graph.version == GRAPH_VERSION
    assert graph.unfilled_cells() == []
    assert SESSION_BRIEF_NODES <= set(graph.nodes)
    assert WAVE_A_NODES <= set(graph.nodes)
    assert WAVE_B_NODES <= set(graph.nodes)
    assert WAVE_C_NODES <= set(graph.nodes)
    assert WAVE_D_NODES <= set(graph.nodes)

    total = 0
    for node in graph.nodes.values():
        if node.prepared is not None:
            # Prepared anchors are generation/review guidance, not audible
            # legacy variants and therefore use their own contract tests.
            continue
        expected = _expected_density(node.id)
        emotions = {"neutral" if state == "unknown" else state for state in node.hr_states}
        examples = {slot.name: slot.example for slot in node.slots}
        for locale, buckets in node.variants.items():
            for emotion in emotions:
                lines = buckets[emotion]
                if node.id == "incident_aftermath":
                    assert lines  # Legacy-only copy with forbidden noun removed.
                else:
                    assert len(lines) == expected, (node.id, locale, emotion)
                assert len(set(lines)) == len(lines), (node.id, locale, emotion)
                for line in lines:
                    assert validate_utterance(line, node) == [], (
                        node.id,
                        locale,
                        emotion,
                        line,
                    )
                    bound = fill_slots(line, examples)
                    assert validate_utterance(bound, node) == [], (
                        node.id,
                        locale,
                        emotion,
                        bound,
                    )
                total += len(lines)
    # Densified graph + W4/H4 briefs + observer fillers + session_checkered + N11A (72) + N11 B/C/D (38) + leader_change (18).
    assert total > 4000


def test_append_patch_exactly_matches_graph_tails() -> None:
    graph = load_sequence_graph()
    patch = _json(PATCH_PATH)
    assert patch["graph_version"] == 1
    assert patch["merge_mode"] == "append"
    assert patch["baseline"]["line_count"] == 752  # type: ignore[index]
    patches = patch["patches"]
    assert isinstance(patches, list)
    assert len(patches) == 188

    appended = 0
    for item in patches:
        assert isinstance(item, dict)
        node = graph.nodes[str(item["node_id"])]
        lines = node.variants[str(item["locale"])][str(item["emotion"])]
        additions = item["append_lines"]
        assert isinstance(additions, list)
        assert item["baseline_line_count"] == 4
        assert lines[:4]
        if node.id not in {"incident", "incident_aftermath"}:
            assert lines[4:] == tuple(additions)
        appended += len(additions)
    assert appended == 2008


def test_target_name_nodes_have_slot_light_fallback_ratio() -> None:
    graph = load_sequence_graph()
    lines: list[str] = []
    for node_id in TARGET_NAME_NODES:
        node = graph.nodes[node_id]
        emotions = {"neutral" if state == "unknown" else state for state in node.hr_states}
        for buckets in node.variants.values():
            for emotion in emotions:
                cell = buckets[emotion]
                assert sum("{target_name}" not in line for line in cell) == 6
                lines.extend(cell)
    light = sum("{target_name}" not in line for line in lines)
    assert len(lines) == 576
    assert light == 216
    assert light / len(lines) == 0.375


def test_no_near_duplicates_within_active_cells() -> None:
    graph = load_sequence_graph()
    findings: list[tuple[str, str, str, str, str, float]] = []
    for node in graph.nodes.values():
        for locale, buckets in node.variants.items():
            for emotion, lines in buckets.items():
                normalized = [_normalized(line) for line in lines]
                for left in range(len(lines)):
                    for right in range(left + 1, len(lines)):
                        score = SequenceMatcher(None, normalized[left], normalized[right]).ratio()
                        if score >= 0.88:
                            findings.append(
                                (node.id, locale, emotion, lines[left], lines[right], score)
                            )
    assert findings == []


def test_viewer_voice_has_no_direct_second_person_address() -> None:
    forbidden_en = re.compile(r"\b(you|your|yours|you're|you've|you'll)\b", re.IGNORECASE)
    forbidden_cs = re.compile(
        r"\b(ty|tvoje|tvůj|tvá|jsi|jedeš|máš|musíš|můžeš|vezmi|drž)\b",
        re.IGNORECASE,
    )
    findings: list[tuple[str, str, str]] = []
    for node, locale, _emotion, line in _active_rows():
        pattern = forbidden_en if locale == "en" else forbidden_cs
        if pattern.search(line):
            findings.append((node.id, locale, line))
    assert findings == []


def test_viewer_voice_name_slots_are_not_vocative_openers() -> None:
    vocative = re.compile(r"^\s*\{([a-z0-9_]+)\}\s*,")
    findings: list[tuple[str, str, str]] = []
    for node, locale, _emotion, line in _active_rows():
        match = vocative.match(line)
        if not match:
            continue
        types = {slot.name: slot.type for slot in node.slots}
        if types.get(match.group(1)) == "name":
            findings.append((node.id, locale, line))
    assert findings == []


def test_deterministic_sixty_line_self_check_against_current_validator() -> None:
    rows = _active_rows()
    sample = random.Random(20260830).sample(rows, 60)
    assert len(sample) >= 30
    for node, locale, emotion, line in sample:
        assert validate_utterance(line, node) == [], (node.id, locale, emotion, line)


def test_proposed_nodes_are_wired_into_graph_and_fully_valid() -> None:
    document = _json(PROPOSALS_PATH)
    assert document["status"] == "wired"
    assert document["topology_changed"] is False
    assert document["runtime_wiring_changed"] is True
    proposed = document["proposed_nodes"]
    assert isinstance(proposed, dict)
    assert set(proposed) == SESSION_BRIEF_NODES

    graph = load_sequence_graph()
    line_count = 0
    for node_id, raw in proposed.items():
        assert isinstance(raw, dict)
        assert raw["status"] == "wired"
        assert node_id in graph.nodes
        graph_node = graph.nodes[node_id]
        assert graph_node.event_types == tuple(str(value) for value in raw["event_types"])
        variants = raw["variants"]
        assert set(variants) == {"en", "cs"}
        for locale, buckets in variants.items():
            examples = {
                str(item["name"]): (item.get("examples_by_locale") or {}).get(
                    locale, item["example"]
                )
                for item in raw["slots"]
            }
            assert set(buckets) == {"neutral", "calm", "focused", "pushing", "high"}
            for emotion, lines in buckets.items():
                assert len(lines) == 10, (node_id, locale, emotion)
                assert graph_node.variants[locale][emotion] == tuple(lines)
                for line in lines:
                    assert validate_utterance(line, graph_node) == [], (
                        node_id,
                        locale,
                        emotion,
                        line,
                    )
                    bound = fill_slots(line, examples)
                    assert validate_utterance(bound, graph_node) == [], (
                        node_id,
                        locale,
                        emotion,
                        bound,
                    )
                    line_count += 1
    assert line_count == 500


def test_proposed_slot_sources_are_exact_and_marked_wired() -> None:
    slots = _json(PROPOSALS_PATH)["proposed_slots"]
    assert isinstance(slots, list)
    assert {item["slot"] for item in slots} == {
        "track",
        "field_size",
        "sof",
        "sof_class",
        "skies",
        "air_temp",
        "track_temp",
        "wind_speed",
        "precipitation",
    }
    for item in slots:
        assert item["irsdk_session_source"]
        assert "wired" in item["notes"].lower()
        assert "not implemented" not in item["notes"].lower()
