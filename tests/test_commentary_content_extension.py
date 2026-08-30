"""Dense commentary content, append patch, proposals, and viewer-voice contract."""

from __future__ import annotations

import json
import random
import re
from difflib import SequenceMatcher
from pathlib import Path

from irswitch.commentary.graph import GraphNode, SlotSpec, TtsLimits, load_sequence_graph
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


def test_every_active_cell_meets_density_and_all_lines_validate() -> None:
    graph = load_sequence_graph()
    assert len(graph.nodes) == 27
    assert len(graph.edges) == 12
    assert graph.unfilled_cells() == []

    total = 0
    for node in graph.nodes.values():
        expected = 16 if node.id in PRIORITY_NODES else 12
        emotions = {"neutral" if state == "unknown" else state for state in node.hr_states}
        examples = {slot.name: slot.example for slot in node.slots}
        for locale, buckets in node.variants.items():
            for emotion in emotions:
                lines = buckets[emotion]
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
    assert total == 2832


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


def test_deterministic_sixty_line_self_check_against_current_validator() -> None:
    rows = _active_rows()
    sample = random.Random(20260830).sample(rows, 60)
    assert len(sample) >= 30
    for node, locale, emotion, line in sample:
        assert validate_utterance(line, node) == [], (node.id, locale, emotion, line)


def test_proposed_nodes_are_explicit_unwired_and_fully_valid() -> None:
    document = _json(PROPOSALS_PATH)
    assert document["status"] == "needs-engineering"
    assert document["topology_changed"] is False
    assert document["runtime_wiring_changed"] is False
    proposed = document["proposed_nodes"]
    assert isinstance(proposed, dict)
    assert set(proposed) == {
        "session_intro_practice",
        "session_intro_qualify",
        "session_intro_race",
        "sof_brief",
        "weather_brief",
    }

    line_count = 0
    for node_id, raw in proposed.items():
        assert isinstance(raw, dict)
        assert raw["status"] == "needs-engineering"
        slots = tuple(
            SlotSpec(str(item["name"]), str(item["type"]), str(item["example"]))
            for item in raw["slots"]
        )
        node = GraphNode(
            id=node_id,
            family=str(raw["family"]),
            event_types=tuple(str(value) for value in raw["event_types"]),
            phases=tuple(str(value) for value in raw["phases"]),
            speak_priority=int(raw["speak_priority"]),
            cooldown_s=float(raw["cooldown_s"]),
            slots=slots,
            hr_states=tuple(str(value) for value in raw["hr_states"]),
            tts=TtsLimits(max_chars=90, max_seconds=5.5),
        )
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
                for line in lines:
                    assert validate_utterance(line, node) == [], (
                        node_id,
                        locale,
                        emotion,
                        line,
                    )
                    bound = fill_slots(line, examples)
                    assert validate_utterance(bound, node) == [], (
                        node_id,
                        locale,
                        emotion,
                        bound,
                    )
                    line_count += 1
    assert line_count == 500


def test_proposed_slot_sources_are_exact_and_marked_unimplemented() -> None:
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
        assert "not implemented" in item["notes"].lower()
