"""Reconcile completed Lifted activities, independently of workout generation."""

import math
import re
import tomllib
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from garminconnect import exercises
from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict, Field

from garmin_workouts.lifted import private_json

BERLIN = ZoneInfo("Europe/Berlin")


class ReconcileError(Exception):
    """An activity needs review before editing."""


class ExerciseMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    lifted: str
    station: int = Field(ge=1, le=6)
    garmin: str
    weight_multiplier: int = Field(ge=1, le=2)


def load_mappings(path: Path) -> dict[tuple[int, str], ExerciseMapping]:
    data = tomllib.loads(path.read_text())
    if set(data) != {"exercises"}:
        raise ReconcileError("Mapping file must contain only [[exercises]] entries.")
    result = {}
    for value in data["exercises"]:
        mapping = ExerciseMapping.model_validate(value)
        key = (mapping.station, mapping.lifted)
        if key in result or exercises.resolve(mapping.garmin) is None:
            raise ReconcileError(f"Duplicate mapping or unknown Garmin exercise: {mapping.lifted}")
        result[key] = mapping
    return result


def utc_time(value: str, naive_zone=UTC) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        parsed.replace(tzinfo=naive_zone).astimezone(UTC)
        if parsed.tzinfo is None
        else parsed.astimezone(UTC)
    )


def activity_start(activity: dict) -> datetime:
    if activity.get("startTimeGMT"):
        return utc_time(activity["startTimeGMT"])
    return utc_time(activity["startTimeLocal"], BERLIN)


def match_classes(
    activities: list[dict], classes: list[dict]
) -> list[tuple[dict, dict | None, str | None]]:
    """Require one-to-one attended class matches within 45 minutes on the same local date."""
    result = []
    for activity in activities:
        if not re.fullmatch(r"Lifted [1-6]", activity.get("activityName", "")):
            continue
        if activity.get("activityType", {}).get("typeKey") != "strength_training":
            result.append((activity, None, "Not a strength activity."))
            continue
        start = activity_start(activity)
        candidates = [
            c
            for c in classes
            if c.get("has_attended") is True
            and utc_time(c["start_datetime"]).astimezone(BERLIN).date()
            == start.astimezone(BERLIN).date()
            and abs(utc_time(c["start_datetime"]) - start) <= timedelta(minutes=45)
        ]
        result.append(
            (
                activity,
                candidates[0] if len(candidates) == 1 else None,
                None
                if len(candidates) == 1
                else f"Expected one attended Lifted class; found {len(candidates)}.",
            )
        )
    counts = Counter(c["workout_id"] for _, c, _ in result if c)
    return [
        (
            a,
            c,
            "Multiple Garmin activities match the same class."
            if c and counts[c["workout_id"]] > 1
            else error,
        )
        for a, c, error in result
    ]


def validate_layout(sets: list[dict]) -> None:
    """Recognize the recorded repeat-group layout, without consulting mutable templates."""
    expected = [(0, None)]
    for position in range(6):
        step = 1 + position * 4
        expected.extend([(step, "ACTIVE"), (step + 1, "REST")] * 3)
        if position < 5:
            expected.append((step + 3, "REST"))
    expected.extend([(24, "REST"), (25, "ACTIVE"), (26, None), (27, None)])
    # A final watch stop/rest may follow the last workout step.
    if (
        len(sets) == len(expected) + 1
        and sets[-1].get("wktStepIndex") is None
        and sets[-1].get("setType") == "REST"
    ):
        expected.append((None, "REST"))
    if len(sets) != len(expected):
        raise ReconcileError(
            "Unrecognized set count; expected six stations with three exercise/rest pairs."
        )
    seen = set()
    for item, (index, kind) in zip(sets, expected, strict=True):
        message = item.get("messageIndex")
        if (
            message is None
            or message in seen
            or item.get("wktStepIndex") != index
            or (kind and item.get("setType") != kind)
        ):
            raise ReconcileError("Unrecognized workout-step layout; station mapping needs review.")
        seen.add(message)


def propose(
    activity: dict, recorded: dict, lifted: dict, mappings: dict
) -> tuple[dict, list[dict]]:
    if str(recorded["activityId"]) != str(activity["activityId"]):
        raise ReconcileError("Activity ID mismatch.")
    validate_layout(recorded["exerciseSets"])
    if lifted.get("has_groups") or lifted.get("max_set_number") != 3:
        raise ReconcileError("Lifted class grouping or set count needs review.")
    logs = lifted["exercise_logs"]
    if len(logs) != 18 or any(s.get("set_type") != "main" for s in logs):
        raise ReconcileError("Expected exactly 18 main Lifted sets.")
    indexed = {(s["exercise_number"], s["set_number"]): s for s in logs}
    if len(indexed) != 18 or set(indexed) != {
        (station, n) for station in range(1, 7) for n in range(1, 4)
    }:
        raise ReconcileError("Missing or duplicate Lifted station/set numbers.")
    if any(s.get("spot_group") != lifted.get("spot_group") for s in logs):
        raise ReconcileError("Lifted spot groups disagree.")
    start = int(activity["activityName"].split()[-1])
    updated = deepcopy(recorded)
    changes = []
    for position in range(6):
        station = (start - 1 + position) % 6 + 1
        targets = [s for s in updated["exerciseSets"] if s.get("wktStepIndex") == 1 + 4 * position]
        for number, target in enumerate(targets, 1):
            source = indexed[station, number]
            mapping = mappings.get((station, source["exercise_name"]))
            if mapping is None:
                raise ReconcileError(
                    f"Add a reviewed mapping for station {station}: {source['exercise_name']}"
                )
            weight = source.get("weight")
            if (
                isinstance(weight, bool)
                or not isinstance(weight, (int, float))
                or not math.isfinite(weight)
                or weight < 0
            ):
                raise ReconcileError(
                    f"Missing or invalid weight for station {station}, set {number}."
                )
            exercise = exercises.resolve(mapping.garmin)
            before = deepcopy(target)
            target["exercises"] = [
                {
                    "category": exercise["category"],
                    "name": exercise["exercise"],
                    "probability": 100.0,
                }
            ]
            target["weight"] = weight * mapping.weight_multiplier * 1000
            if target != before:
                changes.append(
                    {
                        "station": station,
                        "set": number,
                        "exercise": mapping.garmin,
                        "beforeExercises": before.get("exercises"),
                        "beforeWeightGrams": before.get("weight"),
                        "weightKg": target["weight"] / 1000,
                        "watchReps": target.get("repetitionCount"),
                    }
                )
    return updated, changes


@dataclass
class ActivityPlan:
    activity: dict
    lifted: dict
    before: dict
    after: dict
    changes: list[dict]


def backup_root() -> Path:
    return user_data_path("garmin-workouts", appauthor=False) / "activity-backups"


def apply_plan(api, plan: ActivityPlan, root: Path) -> Path | None:
    if not plan.changes:
        return None
    activity_id = plan.activity["activityId"]
    if api.get_activity_exercise_sets(activity_id) != plan.before:
        raise ReconcileError(
            f"Activity {activity_id} changed since preview; stopped before writing."
        )
    folder = (
        root / str(activity_id) / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex)
    )
    # All backups must succeed before the Garmin mutation.
    private_json(folder / "before.json", plan.before)
    private_json(folder / "proposed.json", plan.after)
    private_json(folder / "lifted.json", plan.lifted)
    private_json(folder / "activity.json", plan.activity)
    private_json(folder / "changes.json", plan.changes)
    try:
        api.set_activity_exercise_sets(activity_id, plan.after)
        saved = api.get_activity_exercise_sets(activity_id)
        private_json(folder / "after.json", saved)
    except Exception as error:
        raise ReconcileError(
            f"Update or verification failed ({type(error).__name__}); "
            f"inspect backup {folder} before retrying."
        ) from None
    if saved != plan.after:
        raise ReconcileError(f"Garmin readback differs; stopped. Backup: {folder}")
    return folder


def restore_backup(api, folder: Path, *, apply: bool = False) -> dict:
    import json

    before = json.loads((folder / "before.json").read_text())
    # If a request succeeded but its response/readback was lost, only restore
    # when Garmin exactly matches the proposed update. Never guess its state.
    after_path = folder / "after.json"
    if not after_path.exists():
        after_path = folder / "proposed.json"
    after = json.loads(after_path.read_text())
    activity_id = before["activityId"]
    if after["activityId"] != activity_id:
        raise ReconcileError("Backup activity IDs disagree.")
    current = api.get_activity_exercise_sets(activity_id)
    if current == before:
        return {"activityId": activity_id, "status": "already restored"}
    if current != after:
        raise ReconcileError(
            "Activity changed after this backup; refusing to overwrite newer edits."
        )
    if apply:
        private_json(folder / ("before-restore-" + uuid4().hex + ".json"), current)
        try:
            api.set_activity_exercise_sets(activity_id, before)
            saved = api.get_activity_exercise_sets(activity_id)
            private_json(folder / ("restored-" + uuid4().hex + ".json"), saved)
        except Exception as error:
            raise ReconcileError(
                f"Restore or verification failed ({type(error).__name__}). Backup: {folder}"
            ) from None
        if saved != before:
            raise ReconcileError(f"Restore readback differs. Inspect {folder}.")
    return {"activityId": activity_id, "status": "restored" if apply else "would restore"}
