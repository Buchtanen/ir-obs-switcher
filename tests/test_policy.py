from irswitch.logic.policy import Policy
from irswitch.models import DrivingMode


def test_policy_maps_modes_to_scenes() -> None:
    policy = Policy(
        {
            DrivingMode.IDLE: "Idle",
            DrivingMode.GARAGE: "Pits",
        },
        safe_scene="Safe",
    )

    assert policy.target_for_mode(DrivingMode.IDLE) == "Idle"
    assert policy.target_for_mode(DrivingMode.GARAGE) == "Pits"
    assert policy.target_for_mode(DrivingMode.REPLAY) == "Safe"
