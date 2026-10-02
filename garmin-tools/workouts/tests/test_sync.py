from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from garmin_workouts import cli
from garmin_workouts.class_workout import build_rotation, load_config
from garmin_workouts.sync import PlanItem, SyncError, apply_sync, canonical, plan_sync


@pytest.fixture
def payload():
    config = load_config(Path(__file__).parents[1] / "config/berlin-strength.toml")
    return build_rotation(config, 1).to_dict()


def test_server_metadata_does_not_trigger_update(payload):
    stored = deepcopy(payload)
    stored.update(workoutId=123, author={"name": "private"})
    stored["sportType"]["displayOrder"] = 3
    for step in stored["workoutSegments"][0]["workoutSteps"]:
        step.update(stepId=456, childStepId=1)
        step.setdefault("weightValue", None)
        step["stepType"]["displayOrder"] = 99
    assert canonical(stored) == canonical(payload)
    stored["workoutSegments"][0]["workoutSteps"][1]["endConditionValue"] = 9
    assert canonical(stored) != canonical(payload)


def test_plan_detects_create_update_and_unchanged(payload):
    api = Mock(spec=["get_workouts", "get_workout_by_id"])
    api.get_workouts.return_value = [{"workoutName": "Lifted 1", "workoutId": 123}]
    api.get_workout_by_id.return_value = deepcopy(payload)
    assert plan_sync(api, [payload])[0].action == "unchanged"
    api.get_workout_by_id.return_value["description"] = "Changed"
    assert plan_sync(api, [payload])[0].action == "update"
    api.get_workouts.return_value = []
    assert plan_sync(api, [payload])[0].action == "create"


def test_duplicate_names_block_entire_plan(payload):
    api = Mock(spec=["get_workouts"])
    api.get_workouts.return_value = [{"workoutName": "Lifted 1", "workoutId": n} for n in [1, 2]]
    with pytest.raises(SyncError, match="Multiple workouts"):
        plan_sync(api, [payload])


def test_wrong_sport_and_device_rejected(payload):
    api = Mock()
    api.get_devices.return_value = []
    with pytest.raises(SyncError, match="Selected device"):
        plan_sync(api, [payload], 42)
    api.get_workouts.assert_not_called()
    api.get_workouts.return_value = [{"workoutName": "Lifted 1", "workoutId": 123}]
    api.get_workout_by_id.return_value = {"sportType": {"sportTypeId": 1}}
    with pytest.raises(SyncError, match="not a strength"):
        plan_sync(api, [payload])


def test_updates_preserve_id_and_queue_explicit_device(payload):
    api = Mock(spec=["update_workout", "get_workout_by_id", "push_workout_to_device"])
    api.get_workout_by_id.return_value = payload
    result = apply_sync(api, [PlanItem(payload, "update", 123)], 42)
    api.update_workout.assert_called_once_with(123, payload)
    api.push_workout_to_device.assert_called_once_with(123, 42)
    assert result[0]["verified"] and result[0]["sendQueued"]


def test_unchanged_does_not_upload_or_update(payload):
    api = Mock(spec=["get_workout_by_id"])
    api.get_workout_by_id.return_value = payload
    result = apply_sync(api, [PlanItem(payload, "unchanged", 123)])
    assert result[0]["action"] == "unchanged"
    assert result[0]["sendQueued"] is False


def test_readback_mismatch_stops_remaining_writes_and_pushes(payload):
    api = Mock()
    api.upload_workout.return_value = {"workoutId": 123}
    api.get_workout_by_id.return_value = {}
    with pytest.raises(SyncError, match="differs"):
        apply_sync(api, [PlanItem(payload, "create"), PlanItem(payload, "create")], 42)
    api.upload_workout.assert_called_once()
    api.push_workout_to_device.assert_not_called()


def test_cli_defaults_to_dry_run(monkeypatch):
    api = Mock(spec=["get_workouts"])
    api.get_workouts.return_value = []
    monkeypatch.setattr(cli, "connect", lambda: api)
    config = Path(__file__).parents[1] / "config/berlin-strength.toml"
    result = CliRunner().invoke(cli.app, ["workouts", "sync", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert '"dryRun": true' in result.stdout
    assert result.stdout.count('"action": "create"') == 6
