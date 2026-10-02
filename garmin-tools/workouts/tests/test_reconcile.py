import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from garmin_workouts.cli import app
from garmin_workouts.reconcile import (
    ActivityPlan,
    ReconcileError,
    apply_plan,
    load_mappings,
    match_classes,
    propose,
    restore_backup,
)

MAPPINGS = Path(__file__).parents[1] / "config" / "lifted-exercises.toml"


@pytest.fixture
def sample():
    mapping = load_mappings(MAPPINGS)
    activity = {
        "activityId": 123,
        "activityName": "Lifted 3",
        "startTimeGMT": "2026-10-02 05:21:12",
        "activityType": {"typeKey": "strength_training"},
    }
    sets = []

    def add(index, kind):
        sets.append(
            {
                "messageIndex": len(sets),
                "wktStepIndex": index,
                "setType": kind,
                "exercises": [{"category": "UNKNOWN", "name": None, "probability": 90}],
                "weight": None,
                "repetitionCount": 7,
                "duration": 32.1,
                "startTime": "recorded",
                "extraWatchField": {"keep": True},
            }
        )

    add(0, "ACTIVE")
    for position in range(6):
        step = 1 + position * 4
        for _ in range(3):
            add(step, "ACTIVE")
            add(step + 1, "REST")
        if position < 5:
            add(step + 3, "REST")
    for step, kind in [(24, "REST"), (25, "ACTIVE"), (26, "REST"), (27, "REST"), (None, "REST")]:
        add(step, kind)
    recorded = {"activityId": 123, "exerciseSets": sets}
    weights = [40, 10, 10, 52.5, 73, 15]
    selected = [
        (1, "BB Romanian Deadlift"),
        (2, "DB Standing Triceps Extension"),
        (3, "DB Reverse Lunge On The Spot"),
        (4, "Lat Pull V Bar"),
        (5, "Leg Press Normal Stance"),
        (6, "DB Chest Press Incline"),
    ]
    logs = [
        {
            "exercise_number": m.station,
            "set_number": n,
            "set_type": "main",
            "exercise_name": m.lifted,
            "weight": weights[m.station - 1],
            "reps": 8,
            "spot_group": 1,
        }
        for m in (mapping[key] for key in selected)
        for n in (1, 2, 3)
    ]
    lifted = {
        "workout_id": "class",
        "start_datetime": "2026-10-02T05:15:00Z",
        "has_attended": True,
        "has_groups": False,
        "spot_group": 1,
        "max_set_number": 3,
        "exercise_logs": logs,
    }
    return activity, recorded, lifted, mapping


@pytest.mark.parametrize("key", list(load_mappings(MAPPINGS)))
def test_each_historical_exercise_maps_with_correct_weight_and_watch_reps(sample, key):
    activity, recorded, lifted, mappings = sample
    station, name = key
    for item in lifted["exercise_logs"]:
        if item["exercise_number"] == station:
            item.update(exercise_name=name, weight=10)
    _, changes = propose(activity, recorded, lifted, mappings)
    selected = [c for c in changes if c["station"] == station]
    doubled = station in (3, 6) or (station == 2 and name != "DB Standing Triceps Extension")
    assert len(selected) == 3
    assert all(c["weightKg"] == (20 if doubled else 10) for c in selected)
    assert all(c["watchReps"] == 7 for c in selected)


def test_all_rotations_preserve_watch_fields_and_use_confirmed_weights(sample):
    activity, recorded, lifted, mapping = sample
    untouched = deepcopy(recorded)
    expected_kg = {1: 40, 2: 10, 3: 20, 4: 52.5, 5: 73, 6: 30}
    for start in range(1, 7):
        activity["activityName"] = f"Lifted {start}"
        after, changes = propose(activity, recorded, lifted, mapping)
        assert len(changes) == 18
        for change in changes:
            assert change["weightKg"] == expected_kg[change["station"]]
            assert change["watchReps"] == 7
        for before_set, after_set in zip(
            recorded["exerciseSets"], after["exerciseSets"], strict=True
        ):
            assert {k: v for k, v in before_set.items() if k not in ("weight", "exercises")} == {
                k: v for k, v in after_set.items() if k not in ("weight", "exercises")
            }
            if before_set["wktStepIndex"] not in (1, 5, 9, 13, 17, 21):
                assert before_set == after_set
        assert propose(activity, after, lifted, mapping)[1] == []
    assert recorded == untouched


@pytest.mark.parametrize(
    "problem",
    ["unknown", "weight", "nan", "duplicate", "missing", "group", "layout", "extra_active"],
)
def test_ambiguous_payloads_fail_before_mutation(sample, problem):
    activity, recorded, lifted, mapping = sample
    if problem == "unknown":
        lifted["exercise_logs"][0]["exercise_name"] = "New exercise"
    elif problem in ("weight", "nan"):
        lifted["exercise_logs"][0]["weight"] = None if problem == "weight" else float("nan")
    elif problem == "duplicate":
        lifted["exercise_logs"][0] = lifted["exercise_logs"][1]
    elif problem == "missing":
        lifted["exercise_logs"].pop()
    elif problem == "group":
        lifted["has_groups"] = True
    elif problem == "layout":
        recorded["exerciseSets"][1]["wktStepIndex"] = 2
    else:
        recorded["exerciseSets"].append(deepcopy(recorded["exerciseSets"][1]))
    with pytest.raises(ReconcileError):
        propose(activity, recorded, lifted, mapping)


def test_matching_uses_dates_and_unique_attended_classes(sample):
    activity, _, lifted, _ = sample
    assert match_classes([activity], [lifted])[0][2] is None
    assert match_classes([activity], [lifted, dict(lifted, workout_id="second")])[0][2]
    assert match_classes([activity, dict(activity, activityId=456)], [lifted])[0][2]
    assert match_classes([activity], [dict(lifted, has_attended=False)])[0][2]
    assert match_classes([activity], [dict(lifted, start_datetime="2026-10-01T05:15:00Z")])[0][2]
    assert match_classes([dict(activity, activityName="Morning Run")], [lifted]) == []


def test_berlin_midnight_match(sample):
    activity, _, lifted, _ = sample
    activity.pop("startTimeGMT")
    activity["startTimeLocal"] = "2026-10-02 00:21:00"
    lifted["start_datetime"] = "2026-10-01T22:15:00Z"
    assert match_classes([activity], [lifted])[0][2] is None


def plan_for(sample):
    activity, before, lifted, mappings = sample
    after, changes = propose(activity, before, lifted, mappings)
    return ActivityPlan(activity, lifted, before, after, changes)


def test_backups_exist_before_write_and_roundtrip_restore(sample, tmp_path):
    plan = plan_for(sample)
    api = Mock()
    api.get_activity_exercise_sets.side_effect = [plan.before, plan.after]

    def write(activity_id, data):
        before_file = next(tmp_path.rglob("before.json"))
        assert json.loads(before_file.read_text()) == plan.before
        assert before_file.stat().st_mode & 0o777 == 0o600
        assert json.loads(before_file.with_name("proposed.json").read_text()) == data

    api.set_activity_exercise_sets.side_effect = write
    folder = apply_plan(api, plan, tmp_path)
    assert json.loads((folder / "after.json").read_text()) == plan.after
    api.reset_mock(side_effect=True)
    api.get_activity_exercise_sets.return_value = plan.after
    assert restore_backup(api, folder)["status"] == "would restore"
    api.set_activity_exercise_sets.assert_not_called()
    api.get_activity_exercise_sets.side_effect = [plan.after, plan.before]
    assert restore_backup(api, folder, apply=True)["status"] == "restored"
    api.set_activity_exercise_sets.assert_called_once_with(123, plan.before)


def test_no_writes_on_conflict_backup_failure_or_unchanged(sample, tmp_path, monkeypatch):
    plan = plan_for(sample)
    api = Mock()
    api.get_activity_exercise_sets.return_value = {}
    with pytest.raises(ReconcileError, match="changed"):
        apply_plan(api, plan, tmp_path)
    api.set_activity_exercise_sets.assert_not_called()
    api.get_activity_exercise_sets.return_value = plan.before
    monkeypatch.setattr("garmin_workouts.reconcile.private_json", Mock(side_effect=OSError))
    with pytest.raises(OSError):
        apply_plan(api, plan, tmp_path)
    api.set_activity_exercise_sets.assert_not_called()
    plan.changes = []
    assert apply_plan(api, plan, tmp_path) is None


def test_readback_failure_keeps_backup_and_restore_rejects_new_edits(sample, tmp_path):
    plan = plan_for(sample)
    api = Mock()
    api.get_activity_exercise_sets.side_effect = [
        plan.before,
        {"activityId": 123, "exerciseSets": []},
    ]
    with pytest.raises(ReconcileError, match="readback differs"):
        apply_plan(api, plan, tmp_path)
    folder = next(tmp_path.rglob("before.json")).parent
    assert (folder / "after.json").exists()
    api.get_activity_exercise_sets.side_effect = None
    api.get_activity_exercise_sets.return_value = {"activityId": 123, "newerEdit": True}
    with pytest.raises(ReconcileError, match="newer edits"):
        restore_backup(api, folder, apply=True)


def test_restore_can_recover_lost_readback_without_overwriting_unknown_state(sample, tmp_path):
    plan = plan_for(sample)
    (tmp_path / "before.json").write_text(json.dumps(plan.before))
    (tmp_path / "proposed.json").write_text(json.dumps(plan.after))
    api = Mock()
    api.get_activity_exercise_sets.return_value = plan.after
    assert restore_backup(api, tmp_path)["status"] == "would restore"
    api.get_activity_exercise_sets.return_value = {"activityId": 123, "exerciseSets": []}
    with pytest.raises(ReconcileError, match="newer edits"):
        restore_backup(api, tmp_path, apply=True)
    api.set_activity_exercise_sets.assert_not_called()


def test_cli_dryrun_then_apply_and_all_plans_checked_first(sample, tmp_path, monkeypatch):
    activity, before, lifted, _ = sample
    api = Mock()
    api.get_activities_by_date.return_value = [activity]
    api.get_activity_exercise_sets.return_value = before
    monkeypatch.setattr("garmin_workouts.lifted_cli.connect", lambda: api)
    client = Mock()
    client.logs.return_value = [lifted]
    monkeypatch.setattr("garmin_workouts.lifted_cli.LiftedClient", lambda: client)
    args = [
        "lifted",
        "sync",
        "--date",
        "2026-10-02",
        "--mappings",
        str(MAPPINGS),
        "--backups",
        str(tmp_path),
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["activities"][0]["status"] == "update"
    api.set_activity_exercise_sets.assert_not_called()
    assert not list(tmp_path.iterdir())
    client.logs.return_value = [lifted, dict(lifted, workout_id="ambiguous")]
    result = CliRunner().invoke(app, args + ["--apply"])
    assert result.exit_code == 1
    api.set_activity_exercise_sets.assert_not_called()
    client.logs.return_value = [lifted]
    plan = plan_for(sample)
    api.get_activity_exercise_sets.side_effect = [before, before, plan.after]
    result = CliRunner().invoke(app, args + ["--apply"])
    assert result.exit_code == 0, result.output
    api.set_activity_exercise_sets.assert_called_once()
