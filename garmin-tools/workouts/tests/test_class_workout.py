import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from garmin_workouts import cli
from garmin_workouts.class_workout import ClassConfig, build_rotation, load_config, rotate_stations

CONFIG = Path(__file__).parents[1] / "config" / "berlin-strength.toml"


def flatten(steps):
    for step in steps:
        yield step
        yield from flatten(step.get("workoutSteps", []))


def expand(steps):
    for step in steps:
        if step["type"] == "RepeatGroupDTO":
            for _ in range(step["numberOfIterations"]):
                yield from expand(step["workoutSteps"])
        else:
            yield step


def test_all_six_rotations_have_same_stations_and_unique_step_orders():
    config = load_config(CONFIG)
    names = ["Deadlift", "Arms", "Lunge", "Machine Pull", "Leg Press", "Chest Press"]
    for start in range(1, 7):
        expected = list(range(start, 7)) + list(range(1, start))
        assert [s.number for s in rotate_stations(config, start)] == expected
        assert [s.name for s in sorted(config.stations, key=lambda s: s.number)] == names
        workout = build_rotation(config, start)
        assert workout.workoutName == f"Lifted {start}"
        steps = workout.to_dict()["workoutSegments"][0]["workoutSteps"]
        assert [s["stepOrder"] for s in flatten(steps)] == list(range(1, 29))
        groups = [s for s in steps if s["type"] == "RepeatGroupDTO"]
        assert len(groups) == 6
        assert all(s["numberOfIterations"] == 3 for s in groups)
        steps = list(expand(steps))
        work = [s for s in steps if ": target " in s["description"]]
        assert len(work) == 18
        assert [int(s["description"].split(" - ")[0]) for s in work] == [
            n for n in expected for _ in range(3)
        ]
        for step in work:
            timed = step["description"].startswith("5 - Leg Press:")
            assert step["endConditionValue"] == (30 if timed else 8)
            assert step["endCondition"]["conditionTypeKey"] == ("time" if timed else "reps")
        rests = [s for s in steps if s["description"].startswith("Rest - ")]
        assert len(rests) == 18
        assert all(s["endConditionValue"] == 30 for s in rests)
        assert len([s for s in steps if s["description"].startswith("Transition to ")]) == 5
        for index, step in enumerate(steps):
            if step["description"].startswith("Transition to "):
                assert step["endConditionValue"] == 15
                assert steps[index - 1]["description"].startswith("Rest - ")
        assert steps[-5]["description"].startswith("Rest - ")
        assert [s["description"] for s in steps[-4:]] == [
            "Break",
            "Core",
            "Stretching",
            "Breathing",
        ]


def test_timing_changes_only_leg_press_end_condition():
    config = load_config(CONFIG)
    previous = config.model_copy(deep=True)
    previous.stations[4].work_mode = None
    previous.stations[4].work_seconds = None
    for start in range(1, 7):
        current = build_rotation(config, start).to_dict()
        old = build_rotation(previous, start).to_dict()
        for step in flatten(current["workoutSegments"][0]["workoutSteps"]):
            if step.get("description", "").startswith("5 - Leg Press:"):
                step["endCondition"].update(
                    conditionTypeId=10, conditionTypeKey="reps", displayOrder=10
                )
                step["endConditionValue"] = 8
        assert current == old


def test_warmup_category_and_bodyweight_only_change_warmup():
    config = load_config(CONFIG)
    previous = config.model_copy(deep=True)
    previous.before[0].category = None
    previous.before[0].weight = None
    for start in range(1, 7):
        current = build_rotation(config, start).to_dict()
        old = build_rotation(previous, start).to_dict()
        warmup = current["workoutSegments"][0]["workoutSteps"][0]
        assert warmup.pop("category") == "WARM_UP"
        assert "exerciseName" not in warmup
        assert warmup.pop("weightValue") == 0
        assert warmup.pop("weightUnit")["unitKey"] == "kilogram"
        assert warmup["stepType"]["stepTypeKey"] == "warmup"
        assert warmup["endConditionValue"] == 360
        assert current == old


@pytest.mark.parametrize(
    "category,weight", [("INVALID", None), (None, "body"), ("WARM_UP", "heavy")]
)
def test_invalid_block_exercise_settings_rejected(category, weight):
    data = load_config(CONFIG).model_dump(exclude_none=True)
    data["before"][0].update(category=category, weight=weight)
    with pytest.raises(ValidationError):
        ClassConfig.model_validate(data)


@pytest.mark.parametrize(
    "mode,seconds", [("time", None), ("time", 0), ("reps", 30), ("lap", 30), (None, 30)]
)
def test_invalid_work_timing_rejected(mode, seconds):
    data = load_config(CONFIG).model_dump(exclude_none=True)
    data["stations"][4].update(work_mode=mode, work_seconds=seconds)
    with pytest.raises(ValidationError):
        ClassConfig.model_validate(data)


def test_unknown_station_exercises_are_not_fabricated():
    steps = build_rotation(load_config(CONFIG), 1).to_dict()["workoutSegments"][0]["workoutSteps"]
    steps = list(expand(steps))
    for step in steps:
        if step["description"].startswith(("2 - Arms:", "4 - Machine Pull:")):
            assert "category" not in step
            assert "exerciseName" not in step
    deadlift = next(s for s in steps if s["description"].startswith("1 - Deadlift:"))
    assert deadlift["exerciseName"] == "ROMANIAN_DEADLIFT"


def test_defaults_overrides_and_manual_modes_apply_to_every_rotation():
    data = load_config(CONFIG).model_dump(exclude_none=True)
    data["defaults"] = {"sets": 2, "reps": 10, "work_mode": "lap"}
    data["stations"][0].update(sets=1, reps=6, work_mode="reps")
    data["stations"][4].pop("work_mode")
    data["stations"][4].pop("work_seconds")
    data["rest"] = {"mode": "lap"}
    data["transition"] = {"mode": "lap"}
    data["before"][0]["enabled"] = False
    data["after"] = []
    config = ClassConfig.model_validate(data)
    for start in range(1, 7):
        steps = build_rotation(config, start).to_dict()["workoutSegments"][0]["workoutSteps"]
        groups = [s for s in steps if s["type"] == "RepeatGroupDTO"]
        assert sorted(s["numberOfIterations"] for s in groups) == [1, 2, 2, 2, 2, 2]
        steps = list(expand(steps))
        assert len(steps) == 27  # 11 sets + 11 rests + 5 transitions
        deadlift = next(s for s in steps if s["description"].startswith("1 - Deadlift:"))
        assert deadlift["endConditionValue"] == 6
        for step in steps:
            if step is not deadlift:
                assert step["endCondition"]["conditionTypeKey"] == "lap.button"
                assert "endConditionValue" not in step


@pytest.mark.parametrize(
    "problem", ["duplicate", "missing", "exercise", "typo", "zero", "lap_seconds"]
)
def test_bad_config_rejected(problem):
    data = load_config(CONFIG).model_dump(exclude_none=True)
    if problem == "duplicate":
        data["stations"][0]["number"] = 2
    elif problem == "missing":
        data["stations"].pop()
    elif problem == "exercise":
        data["stations"][0]["exercise"] = "Imaginary Exercise"
    elif problem == "typo":
        data["defaults"]["rep"] = 8
    elif problem == "zero":
        data["defaults"]["reps"] = 0
    else:
        data["rest"]["mode"] = "lap"
    with pytest.raises(ValidationError):
        ClassConfig.model_validate(data)


def test_generation_cli_is_offline(monkeypatch):
    connect = Mock(side_effect=AssertionError("Must not connect"))
    monkeypatch.setattr(cli, "connect", connect)
    runner = CliRunner()
    result = runner.invoke(cli.app, ["workouts", "generate", "--config", str(CONFIG)])
    assert result.exit_code == 0, result.output
    summaries = json.loads(result.stdout)
    assert len(summaries) == 6
    assert summaries[0]["unmappedStations"] == [2, 4]
    assert summaries[0]["stations"][4]["workMode"] == "time"
    assert summaries[0]["stations"][4]["workSeconds"] == 30
    result = runner.invoke(
        cli.app,
        ["workouts", "generate", "--config", str(CONFIG), "--start", "3", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)) == 1
    assert json.loads(result.stdout)[0]["workoutName"] == "Lifted 3"
    connect.assert_not_called()


def test_invalid_config_cli_returns_useful_error(tmp_path):
    path = tmp_path / "invalid.toml"
    path.write_text("name = [broken")
    result = CliRunner().invoke(cli.app, ["workouts", "generate", "--config", str(path)])
    assert result.exit_code == 2
    assert "Invalid workout configuration" in result.output
