import json
from unittest.mock import Mock

from typer.testing import CliRunner

from garmin_workouts import cli
from garmin_workouts.workouts import TEST_WORKOUT_NAME, build_test_workout, plan_test_workout

runner = CliRunner()


def test_preview_is_offline_and_has_three_rep_sets_with_timed_rests(monkeypatch):
    connect = Mock(side_effect=AssertionError("Preview must be offline"))
    monkeypatch.setattr(cli, "connect", connect)
    result = runner.invoke(cli.app, ["workouts", "preview", "--rest-seconds", "45"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["sportType"]["sportTypeKey"] == "strength_training"
    group = data["workoutSegments"][0]["workoutSteps"][0]
    assert group["numberOfIterations"] == 3
    work, rest = group["workoutSteps"]
    assert work["category"] == "DEADLIFT"
    assert work["exerciseName"] == "ROMANIAN_DEADLIFT"
    assert work["endCondition"]["conditionTypeKey"] == "reps"
    assert work["endConditionValue"] == 8
    assert rest["endCondition"]["conditionTypeKey"] == "time"
    assert rest["endConditionValue"] == 45
    assert len({group["stepOrder"], work["stepOrder"], rest["stepOrder"]}) == 3
    assert "weightValue" not in work
    connect.assert_not_called()


def test_create_defaults_to_read_only_plan(monkeypatch):
    api = Mock(spec=["get_workouts"])
    api.get_workouts.return_value = []
    monkeypatch.setattr(cli, "connect", lambda: api)
    result = runner.invoke(cli.app, ["workouts", "create-test"])
    assert result.exit_code == 0
    plan = json.loads(result.stdout)
    assert plan["dryRun"] is True
    assert plan["action"] == "create"
    assert plan["pushToDevice"] is False


def test_name_collision_on_later_page_blocks_creation(monkeypatch):
    api = Mock(spec=["get_workouts"])
    api.get_workouts.side_effect = [
        [{"workoutId": n, "workoutName": "Other"} for n in range(100)],
        [{"workoutId": 123, "workoutName": TEST_WORKOUT_NAME}],
    ]
    monkeypatch.setattr(cli, "connect", lambda: api)
    result = runner.invoke(cli.app, ["workouts", "create-test", "--apply"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["created"] is False
    assert json.loads(result.stdout)["workoutIds"] == [123]
    api.get_workouts.assert_called_with(start=100, limit=100)


def test_apply_uploads_one_typed_workout(monkeypatch):
    api = Mock(spec=["get_workouts", "upload_strength_workout"])
    api.get_workouts.return_value = []
    api.upload_strength_workout.return_value = {"workoutId": 123}
    monkeypatch.setattr(cli, "connect", lambda: api)
    result = runner.invoke(cli.app, ["workouts", "create-test", "--apply"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["workoutId"] == 123
    api.upload_strength_workout.assert_called_once()
    assert api.upload_strength_workout.call_args.args[0].to_dict() == build_test_workout().to_dict()


def test_duplicate_name_plan_lists_all_matches():
    api = Mock()
    api.get_workouts.return_value = [
        {"workoutId": n, "workoutName": TEST_WORKOUT_NAME} for n in [1, 2]
    ]
    assert plan_test_workout(api, build_test_workout())["existingWorkoutIds"] == [1, 2]


def test_invalid_rest_rejected_before_login(monkeypatch):
    connect = Mock(side_effect=AssertionError("Must not log in"))
    monkeypatch.setattr(cli, "connect", connect)
    result = runner.invoke(cli.app, ["workouts", "create-test", "--rest-seconds", "0"])
    assert result.exit_code == 2
    connect.assert_not_called()
