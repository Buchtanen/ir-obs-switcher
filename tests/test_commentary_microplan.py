"""Selected-fact contracts; no Ollama required for these regressions."""

import json

import pytest

from irswitch.commentary.composer import build_skeleton
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.polish import (
    _tested_live_data,
    build_polish_request,
    fact_violation_codes,
    polish_skeleton,
)
from irswitch.commentary.style_cards import load_node_moods
from irswitch.events.envelope import make_envelope
from irswitch.overlay.settings import CommentarySettings


def plan(event="POSITION_LOST", node_id="position_lost", **bindings):
    graph = load_sequence_graph()
    mode = str(bindings.pop("mode", "GENERIC"))
    result = build_skeleton(
        make_envelope(event_type=event, phase="RESULT", correlation_id="relation:12", mode=mode),
        graph.nodes[node_id],
        graph=graph,
        story={"race": {"class_position": 13}, "situation": {"current_lap": 99}},
        bindings=bindings,
        emotion="unknown",
        language="en",
    )
    assert result is not None
    return result


def test_selected_facts_replace_skeleton_as_validator_authority():
    result = plan(position=13, target_name="Rossi")
    assert result.fact_pack["version"] == "commentary-facts/3"
    assert result.fact_count == 1
    assert "P13" in result.text and "Rossi" in result.text
    assert not fact_violation_codes(
        "Position lost.", "He drops behind Rossi to P13.", fact_pack=result.fact_pack
    )
    assert "invented_number" in fact_violation_codes(
        result.text, "He drops behind Rossi to P13 on lap 99.", fact_pack=result.fact_pack
    )


def test_position_gain_is_not_evidence_of_an_on_track_pass():
    result = plan("POSITION_GAINED", "position_gained", position=8, target_name="Rossi")
    assert "passes" not in result.text
    assert "forbidden_pass" in fact_violation_codes(
        result.text, "He passes Rossi to take P8.", fact_pack=result.fact_pack
    )


def test_two_front_does_not_match_direction_across_other_actor():
    result = plan(
        "BATTLE_FOR_POSITION",
        "two_front_battle",
        front_target_name="Rossi",
        rear_target_name="Meyer",
    )
    assert not fact_violation_codes(
        result.text,
        "He attacks Rossi ahead while Meyer applies pressure behind.",
        fact_pack=result.fact_pack,
    )
    for bad in (
        "He attacks Meyer ahead while Rossi applies pressure behind.",
        "He follows Rossi and Meyer.",
        "Rossi attacks ahead while Meyer applies pressure behind.",
        "Rossi accelerates forward and he attacks; Meyer pressures from behind.",
    ):
        assert fact_violation_codes(result.text, bad, fact_pack=result.fact_pack)


def test_numeric_precision_is_not_changed_by_normalization():
    result = plan("HUNTING", "hunting", target_name="Rossi", gap="0.05 seconds")
    assert "invented_number" in fact_violation_codes(
        result.text, "He closes on Rossi, 0.5 seconds ahead.", fact_pack=result.fact_pack
    )
    assert not fact_violation_codes(
        result.text, "He closes on Rossi, 0.050 seconds ahead.", fact_pack=result.fact_pack
    )


def test_invalid_source_metrics_are_not_selected_for_realization():
    for invalid in ("nan", "inf", "-0.5 seconds", "0 seconds"):
        result = plan("HUNTING", "hunting", target_name="Rossi", gap=invalid)
        selected = " ".join(
            fact["text"]
            for key in ("required_facts", "optional_facts")
            for fact in result.fact_pack[key]
        )
        assert invalid not in selected
        assert result.fact_pack["target"].get("gap") is None


def test_position_event_retains_outcome_but_omits_invalid_position():
    result = plan("POSITION_GAINED", "position_gained", position=0)
    assert result.text == "He gains a position."
    assert not result.fact_pack["allowed_numbers"]


def test_compact_request_omits_anchor_telemetry_and_changes_retry():
    result = plan(position=13, target_name="Rossi")
    settings = CommentarySettings()
    first = build_polish_request("Do not copy this anchor.", settings, fact_pack=result.fact_pack)
    strict = build_polish_request(
        result.text, settings, fact_pack=result.fact_pack, rejected=["invented_number"]
    )
    prompt = " ".join(message["content"] for message in first["messages"])
    assert "Do not copy" not in prompt and "99" not in prompt
    assert "allowed_numbers" not in prompt and "provenance" not in prompt
    retry = " ".join(message["content"] for message in strict["messages"])
    assert "invented_number" not in retry
    assert "Correct only" not in retry
    assert len(prompt) < 1400


def _live_user(event: str, node_id: str, **bindings: object) -> str:
    result = plan(event, node_id, **bindings)
    return build_polish_request(
        result.text,
        CommentarySettings(),
        node=load_sequence_graph().nodes[node_id],
        fact_pack=result.fact_pack,
    )["messages"][1]["content"]


def test_g1_request_is_role_labeled_data_without_example_or_mood():
    result = plan("HUNTED", "hunted", hero_name="Buchtanen", target_name="Flint", gap="1.44 s")
    request = build_polish_request(
        result.text,
        CommentarySettings(),
        node=load_sequence_graph().nodes["hunted"],
        fact_pack=result.fact_pack,
    )

    system = request["messages"][0]["content"]
    user = request["messages"][1]["content"]
    assert system.startswith("You are a professional TV race commentator.")
    assert "Never predict the future." in system
    assert "Do not invent a pass" in system
    assert "Color, energy and a bit of showmanship are OK" in system
    assert "Write in Czech" not in system
    assert "STYLE" not in system

    cs_system = build_polish_request(
        result.text,
        CommentarySettings(),
        node=load_sequence_graph().nodes["hunted"],
        fact_pack=result.fact_pack,
        locale="cs",
    )["messages"][0]["content"]
    assert cs_system == system
    assert user.startswith("DATA:")
    assert 'chaser: "Flint"' in user
    assert 'gap: "1.44 s"' in user
    assert 'target: "Buchtanen"' in user
    assert "relation:" not in user
    assert 'situation: "applying pressure from behind"' in user
    assert "hero:" not in user
    assert "STYLE mood" not in user
    assert "Write a NEW broadcast line." not in user
    assert result.text not in user
    assert "Example:" not in user
    assert request["temperature"] == 0.4
    assert request["max_tokens"] == 45
    assert request["options"] == {
        "num_ctx": 512,
        "num_thread": 4,
        "num_predict": 45,
        "top_k": 30,
        "top_p": 0.85,
    }


def test_tested_live_data_schemas_match_4b_probe():
    hunting = _live_user(
        "HUNTING", "hunting", hero_name="Buchtanen", target_name="Hudson", gap="2.03 s"
    )
    assert 'chaser: "Buchtanen"' in hunting
    assert 'target: "Hudson"' in hunting
    assert 'gap: "2.03 s"' in hunting
    assert 'relation: "hero_closing_on_target"' in hunting
    assert 'situation: "closing gap on Hudson"' in hunting
    assert "closing_on:" not in hunting
    assert "hero:" not in hunting
    assert "STYLE mood" not in hunting

    overtake = _live_user(
        "OVERTAKE",
        "overtake",
        hero_name="Buchtanen",
        target_name="Hudson",
        position=29,
    )
    assert 'hero: "Buchtanen"' in overtake
    assert 'passed: "Hudson"' in overtake
    assert 'new_position: "P29"' in overtake
    assert 'situation: "completed a pass"' in overtake

    two_front = _live_user(
        "BATTLE_FOR_POSITION",
        "two_front_battle",
        hero_name="Buchtanen",
        front_target_name="LoVecchio",
        rear_target_name="Rubin",
    )
    assert 'hero: "Buchtanen"' in two_front
    assert 'car_ahead: "LoVecchio"' in two_front
    assert 'car_behind: "Rubin"' in two_front
    assert 'situation: "attacking LoVecchio, Rubin applying pressure behind"' in two_front

    field = _live_user(
        "FIELD_FACT",
        "field_fact",
        hero_name="Buchtanen",
        target_name="Hudson",
        gap="6.11 s",
    )
    assert 'chaser: "Buchtanen"' in field
    assert 'target: "Hudson"' in field
    assert 'gap: "6.11 s"' in field
    assert "hero:" not in field
    assert "situation:" not in field


def test_hunting_uses_verified_chaser_not_closing_on_subject():
    hunting = _live_user("HUNTING", "hunting", hero_name="Buchtanen", target_name="Nash")
    assert 'chaser: "Buchtanen"' in hunting
    assert 'target: "Nash"' in hunting
    assert 'relation: "hero_closing_on_target"' in hunting
    assert 'situation: "closing gap on Nash"' in hunting
    assert "closing_on:" not in hunting
    assert "closing on the target" not in hunting


def test_practice_and_qualify_facts_name_the_session():
    practice = _live_user(
        "HUNTING",
        "hunting",
        hero_name="Buchtanen",
        target_name="Nash",
        mode="PRACTICE",
    )
    assert 'session: "practice"' in practice
    assert "in practice" in practice

    qualify = _live_user(
        "PERSONAL_BEST",
        "personal_best",
        hero_name="Buchtanen",
        position=18,
        mode="QUALIFYING",
    )
    assert 'session: "qualifying"' in qualify
    assert "in qualifying" in qualify


def test_locked_en_probe_schemas():
    lost = _live_user(
        "POSITION_LOST",
        "position_lost",
        hero_name="Buchtanen",
        target_name="Rossi",
        position=13,
    )
    assert 'hero: "Buchtanen"' in lost
    assert 'lost_to: "Rossi"' in lost
    assert 'new_position: "P13"' in lost
    assert 'situation: "lost a position"' in lost

    leader = _live_user(
        "LEADER_CHANGE",
        "leader_change",
        target_name="Hudson",
        leader_name="Brown",
    )
    assert 'new_leader: "Hudson"' in leader
    assert 'old_leader: "Brown"' in leader
    assert 'situation: "lead changed"' in leader

    rival = _live_user(
        "RIVAL_THREAT",
        "rival_threat",
        target_name="Kovalainen",
        gap="2.4 s",
    )
    assert 'threat: "Kovalainen"' in rival
    assert 'gap: "2.4 s"' in rival
    assert 'situation: "distant rival, not yet applying pressure"' in rival

    incident = _live_user("INCIDENT", "incident_off_track", hero_name="Buchtanen")
    assert 'hero: "Buchtanen"' in incident
    assert 'situation: "ran off the track"' in incident

    quali = _live_user("QUALI_RECAP", "quali_recap", hero_name="Buchtanen", position=18)
    assert 'hero: "Buchtanen"' in quali
    assert 'situation: "qualified"' in quali

    wrap = _live_user("SESSION_WRAP", "session_wrap", hero_name="Buchtanen", position=12)
    assert 'hero: "Buchtanen"' in wrap
    assert 'situation: "session finished"' in wrap
    assert 'position: "P12"' in wrap

    two_front = _live_user(
        "BATTLE_FOR_POSITION",
        "two_front_battle",
        hero_name="Buchtanen",
        front_target_name="LoVecchio",
        rear_target_name="Rubin",
        front_gap="0.7 s",
        rear_gap="0.5 s",
    )
    assert 'gap_ahead: "0.7 s"' in two_front
    assert 'gap_behind: "0.5 s"' in two_front

    field_pos = _live_user(
        "FIELD_FACT",
        "field_fact",
        hero_name="Buchtanen",
        position=30,
    )
    assert 'chaser: "Buchtanen"' in field_pos
    assert 'position: "P30"' in field_pos
    assert 'situation: "holds P30"' in field_pos
    assert "hero:" not in field_pos

    gained = _live_user("POSITION_GAINED", "position_gained", hero_name="Buchtanen", position=8)
    assert 'hero: "Buchtanen"' in gained
    assert 'new_position: "P8"' in gained
    assert 'situation: "gained a position to P8"' in gained

    swing = _live_user(
        "POSITION_LOST",
        "position_lost",
        hero_name="Buchtanen",
        position=8,
        old_position=2,
        places=6,
    )
    assert 'hero: "Buchtanen"' in swing
    assert 'from: "P2"' in swing
    assert 'to: "P8"' in swing
    assert "places: 6" in swing
    assert 'situation: "lost 6 positions to P8"' in swing
    assert 'situation: "lost a position"' not in swing

    field_leader = _live_user("FIELD_FACT", "field_fact", leader_name="Rossi")
    assert 'leader: "Rossi"' in field_leader
    assert 'situation: "Rossi sets the pace out front"' in field_leader

    weather = _live_user(
        "WEATHER_CHANGE",
        "weather_change",
        skies="partly cloudy",
        air_temp="23 C",
        wind_speed="4 m/s",
    )
    assert 'skies: "partly cloudy"' in weather
    assert 'air_temp: "23 C"' in weather
    assert 'wind_speed: "4 m/s"' in weather
    assert 'situation: "current conditions"' in weather

    lap = _live_user(
        "LAP_COMPLETE",
        "lap_complete",
        hero_name="Buchtanen",
        lap=12,
        lap_time="1:32.4",
    )
    assert 'hero: "Buchtanen"' in lap
    assert 'lap: "12"' in lap
    assert 'lap_time: "1:32.4"' in lap
    assert 'situation: "completed lap 12 in 1:32.4"' in lap

    personal_best = _live_user(
        "PERSONAL_BEST",
        "personal_best",
        hero_name="Buchtanen",
        position=18,
        lap=8,
        lap_time="1:31.1",
        delta="-0.4",
    )
    assert 'hero: "Buchtanen"' in personal_best
    assert 'position: "P18"' in personal_best
    assert 'lap: "8"' in personal_best
    assert 'lap_time: "1:31.1"' in personal_best
    assert 'situation: "set a personal best on lap 8 in 1:31.1"' in personal_best
    assert 'delta: "-0.4"' in personal_best
    assert "vs own" not in personal_best

    excursion = _live_user("TRACK_EXCURSION", "track_excursion", hero_name="Buchtanen")
    assert 'hero: "Buchtanen"' in excursion
    assert 'situation: "ran off the track"' in excursion
    assert "action:" not in excursion

    restored = _live_user("TRACK_EXCURSION", "motion_restored", hero_name="Buchtanen")
    assert 'hero: "Buchtanen"' in restored
    assert 'situation: "moving again after going off"' in restored
    assert "every driver" not in restored
    assert "action:" not in restored

    points = _live_user("INCIDENT", "incident", hero_name="Buchtanen", value=2)
    assert 'hero: "Buchtanen"' in points
    assert "incident_points: 2" in points
    assert 'situation: "incident points"' in points
    assert "action:" not in points

    finish_plan = plan("FINISH", "finish", hero_name="Buchtanen", position=11)
    assert finish_plan.text == "He finishes in P11."
    assert finish_plan.fact_pack["required_facts"][0]["relation"] == "hero_placement"
    finish = _live_user("FINISH", "finish", hero_name="Buchtanen", position=11)
    assert 'hero: "Buchtanen"' in finish
    assert 'situation: "hero placement"' in finish
    assert 'position: "P11"' in finish

    checkered = _live_user("SESSION_CHECKERED", "session_checkered", hero_name="Buchtanen")
    assert 'situation: "checkered flag"' in checkered
    assert "hero:" not in checkered
    assert "action:" not in checkered


def test_two_front_and_overtake_keep_typed_data_without_hero_role():
    two = plan(
        "BATTLE_FOR_POSITION",
        "two_front_battle",
        hero_name="Buchtanen",
        front_target_name="LoVecchio",
        rear_target_name="Rubin",
        front_gap="0.17 s",
        rear_gap="0.33 s",
    )
    two.fact_pack["microplan"]["actor_roles"] = [
        item for item in two.fact_pack["microplan"]["actor_roles"] if item[0] != "hero"
    ]
    data = _tested_live_data(two.fact_pack)
    assert data is not None
    assert data["hero"] == "Buchtanen"
    assert data["car_ahead"] == "LoVecchio"
    assert data["car_behind"] == "Rubin"
    assert data["gap_ahead"] == "0.17 s"
    assert data["gap_behind"] == "0.33 s"
    assert "target_ahead" not in data

    overtake = plan(
        "OVERTAKE",
        "overtake",
        hero_name="Buchtanen",
        target_name="Bergh",
        position=8,
    )
    overtake.fact_pack["microplan"]["actor_roles"] = [
        item for item in overtake.fact_pack["microplan"]["actor_roles"] if item[0] != "hero"
    ]
    passed = _tested_live_data(overtake.fact_pack)
    assert passed is not None
    assert passed["hero"] == "Buchtanen"
    assert passed["passed"] == "Bergh"
    assert passed["new_position"] == "P8"
    assert "P8 Bergh completed a pass" not in str(passed)


def test_hunted_rejects_role_lexicon_and_schema_leaks():
    result = plan("HUNTED", "hunted", hero_name="Buchtanen", target_name="Flint")
    assert "role_as_name" in fact_violation_codes(
        result.text, "Target's on the move behind Buchtanen.", fact_pack=result.fact_pack
    )
    assert "schema_leak" in fact_violation_codes(
        result.text,
        "target_closing_on_hero — Flint is applying pressure.",
        fact_pack=result.fact_pack,
    )


def test_hunting_rejects_possessive_target_as_subject():
    result = plan("HUNTING", "hunting", hero_name="Buchtanen", target_name="Gosselin")
    for bad in (
        "Gosselin's closing on the target.",
        "Gosselin's closing on Buchtanen.",
        "Gosselin is closing on the target.",
    ):
        assert "reversed_relation" in fact_violation_codes(
            result.text, bad, fact_pack=result.fact_pack
        )
    assert not fact_violation_codes(
        result.text,
        "Buchtanen is closing the gap on Gosselin.",
        fact_pack=result.fact_pack,
    )


def test_weather_brief_sends_typed_facts_and_rejects_polarity():
    brief = _live_user(
        "WEATHER_BRIEF",
        "weather_brief",
        skies="overcast",
        air_temp="27 C",
        track_temp="30 C",
        wind_speed="1 m/s",
    )
    assert 'skies: "overcast"' in brief
    assert 'wind_speed: "1 m/s"' in brief
    assert "weather brief" not in brief
    result = plan(
        "WEATHER_BRIEF",
        "weather_brief",
        skies="overcast",
        air_temp="27 C",
        wind_speed="1 m/s",
    )
    assert "weather_polarity" in fact_violation_codes(
        result.text,
        "Moments ago, the weather was clear and calm—no rain, no wind.",
        fact_pack=result.fact_pack,
    )


def test_final_lap_is_typed_not_literal_canonical():
    user = _live_user("FINAL_LAP", "final_lap", hero_name="Buchtanen", position=5)
    assert 'situation: "final lap"' in user
    result = plan("FINAL_LAP", "final_lap", hero_name="Buchtanen", position=5)
    assert not fact_violation_codes(
        result.text,
        "Final lap. Buchtanen starts it in P5.",
        fact_pack=result.fact_pack,
    )


def test_no_one_is_not_an_invented_number():
    result = plan("HUNTED", "hunted", hero_name="Buchtanen", target_name="Flint")
    assert "invented_number" not in fact_violation_codes(
        result.text,
        "Buchtanen holds station. No one is out there ahead.",
        fact_pack=result.fact_pack,
    )


def test_natural_validator_talk_is_meta_output():
    result = plan("HUNTED", "hunted", hero_name="Buchtanen", target_name="Flint")
    assert "meta_output" in fact_violation_codes(
        result.text,
        "No invented numbers, just real-time data behind Flint.",
        fact_pack=result.fact_pack,
    )
    assert "meta_output" in fact_violation_codes(
        result.text,
        "No weather polarity shift in this call on Flint.",
        fact_pack=result.fact_pack,
    )


def test_untested_live_relation_stays_on_legacy_data_keys():
    user = _live_user("HOT_LAP", "hot_lap", hero_name="Buchtanen", lap_time="1:31.8")
    assert user.startswith("DATA:")
    assert "STYLE mood" not in user
    assert "Write a NEW broadcast line." not in user
    assert 'action: "hot lap"' in user or "action:" in user


def test_node_mood_catalog_is_short_and_references_real_nodes():
    default, moods = load_node_moods()
    graph = load_sequence_graph()
    assert set(moods) <= set(graph.nodes)
    assert moods["incident_off_track"] == "urgent, startled, clipped"
    assert moods["overtake"] == "decisive, punchy, celebratory"
    for mood in (default, *moods.values()):
        assert 2 <= len(mood.split(",")) <= 4
        assert "." not in mood


def test_microplan_accepts_atmosphere_but_rejects_new_outcome():
    result = plan("HUNTED", "hunted", hero_name="Buchtanen", target_name="Flint")
    vivid = "Buchtanen’s mirrors flash—Flint’s pressure bites, tight and cold, right behind."
    assert not fact_violation_codes(result.text, vivid, fact_pack=result.fact_pack)

    predicted = "Buchtanen feels Flint closing from behind and will win this fight."
    codes = fact_violation_codes(result.text, predicted, fact_pack=result.fact_pack)
    assert "unsupported_prediction" in codes
    assert "unsupported_event" in codes

    incident = plan("INCIDENT", "incident_off_track", hero_name="Buchtanen")
    atmospheric = "Buchtanen hits the track’s edge—no warning. That’s a real one."
    assert "invented_number" not in fact_violation_codes(
        incident.text, atmospheric, fact_pack=incident.fact_pack
    )
    unsupported_state = "Buchtanen is off track—no signal, no response."
    assert "unsupported_event" in fact_violation_codes(
        incident.text, unsupported_state, fact_pack=incident.fact_pack
    )


def test_style_warning_does_not_retry_and_attempts_are_recorded():
    result = plan(position=13, target_name="Rossi")
    calls = []

    def opener(req, timeout):
        calls.append(req)
        return json.dumps(
            {"choices": [{"message": {"content": "He drops behind Rossi to P13"}}]}
        ).encode()

    outcome = polish_skeleton(
        result.text,
        load_sequence_graph().nodes["position_lost"],
        CommentarySettings(llm_polish=True),
        fact_pack=result.fact_pack,
        opener=opener,
    )
    assert outcome.outcome == "ok" and len(calls) == 1
    assert outcome.text.endswith(".")
    assert outcome.debug_record(node_id="position_lost", event_type="POSITION_LOST")["attemptLog"]


def test_only_one_semantic_retry_then_complete_canonical_fallback():
    result = plan(position=13, target_name="Rossi")
    calls = []

    def opener(req, timeout):
        calls.append(json.loads(req.data))
        return json.dumps(
            {"choices": [{"message": {"content": "Hamilton wins on lap 99."}}]}
        ).encode()

    outcome = polish_skeleton(
        result.text,
        load_sequence_graph().nodes["position_lost"],
        CommentarySettings(llm_polish=True, llm_max_attempts=8),
        fact_pack=result.fact_pack,
        opener=opener,
    )
    assert outcome.attempts == len(calls) == 2
    retry = " ".join(message["content"] for message in calls[1]["messages"])
    assert "invented_number" not in retry
    assert "Correct only" not in retry
    assert outcome.text == result.text


@pytest.mark.parametrize("error", [TimeoutError(), OSError("offline")])
def test_outage_does_not_retry_identical_request(error):
    result = plan(position=13, target_name="Rossi")

    def opener(req, timeout):
        raise error

    outcome = polish_skeleton(
        result.text,
        load_sequence_graph().nodes["position_lost"],
        CommentarySettings(llm_polish=True),
        fact_pack=result.fact_pack,
        opener=opener,
    )
    assert outcome.attempts == 1
    assert outcome.text == result.text
