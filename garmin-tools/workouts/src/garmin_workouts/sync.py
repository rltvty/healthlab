"""Plan, apply, verify, and queue generated workouts without deleting IDs."""

from collections.abc import Callable
from dataclasses import dataclass

from garminconnect import Garmin


class SyncError(Exception):
    """A safe-to-display planning or verification failure."""


def canonical(payload: dict) -> dict:
    """Compare training semantics, excluding server IDs, authors and display metadata."""

    def step(value: dict) -> dict:
        result = {
            key: value.get(key)
            for key in (
                "type",
                "stepOrder",
                "description",
                "category",
                "exerciseName",
                "weightValue",
                "targetValueOne",
                "targetValueTwo",
                "zoneNumber",
                "secondaryTargetValueOne",
                "secondaryTargetValueTwo",
                "secondaryZoneNumber",
            )
        }
        for key, id_key in (
            ("stepType", "stepTypeId"),
            ("endCondition", "conditionTypeId"),
            ("targetType", "workoutTargetTypeId"),
            ("secondaryTargetType", "workoutTargetTypeId"),
            ("weightUnit", "unitId"),
        ):
            result[key] = (value.get(key) or {}).get(id_key)
        if result["endCondition"] != 1:
            result["endConditionValue"] = value.get("endConditionValue")
        if value.get("type") == "RepeatGroupDTO":
            result["numberOfIterations"] = value.get("numberOfIterations")
            result["skipLastRestStep"] = bool(value.get("skipLastRestStep"))
            result["workoutSteps"] = [step(item) for item in value.get("workoutSteps", [])]
        return result

    return {
        "workoutName": payload.get("workoutName"),
        "description": payload.get("description"),
        "sport": (payload.get("sportType") or {}).get("sportTypeId"),
        "segments": [
            {
                "order": segment.get("segmentOrder"),
                "sport": (segment.get("sportType") or {}).get("sportTypeId"),
                "steps": [step(item) for item in segment.get("workoutSteps", [])],
            }
            for segment in payload.get("workoutSegments", [])
        ],
    }


@dataclass
class PlanItem:
    payload: dict
    action: str
    workout_id: int | None = None

    def summary(self, device_id: int | None) -> dict:
        return {
            "name": self.payload["workoutName"],
            "action": self.action,
            "workoutId": self.workout_id,
            "sendToDevice": device_id,
        }


def plan_sync(api: Garmin, payloads: list[dict], device_id: int | None = None) -> list[PlanItem]:
    if device_id is not None:
        matches = [d for d in api.get_devices() if str(d.get("deviceId")) == str(device_id)]
        if len(matches) != 1 or not matches[0].get("strengthWorkoutCapable"):
            raise SyncError(
                "Selected device is missing, ambiguous, or lacks strength-workout support."
            )
    by_name: dict[str, list[int]] = {}
    offset = 0
    while True:
        page = api.get_workouts(start=offset, limit=100)
        for item in page:
            by_name.setdefault(item["workoutName"], []).append(int(item["workoutId"]))
        if len(page) < 100:
            break
        offset += len(page)
    result = []
    for payload in payloads:
        name = payload["workoutName"]
        ids = by_name.get(name, [])
        if len(ids) > 1:
            raise SyncError(f"Multiple workouts named {name}; resolve duplicates before syncing.")
        if not ids:
            result.append(PlanItem(payload, "create"))
            continue
        current = api.get_workout_by_id(ids[0])
        if (current.get("sportType") or {}).get("sportTypeId") != 5:
            raise SyncError(f"{name} exists but is not a strength workout; refusing to replace it.")
        action = "unchanged" if canonical(current) == canonical(payload) else "update"
        result.append(PlanItem(payload, action, ids[0]))
    return result


def apply_sync(
    api: Garmin,
    plan: list[PlanItem],
    device_id: int | None = None,
    report: Callable[[str], None] = lambda _: None,
) -> list[dict]:
    results = []
    for item in plan:
        workout_id = item.workout_id
        name = item.payload["workoutName"]
        if item.action == "create":
            response = api.upload_workout(item.payload)
            workout_id = int(response["workoutId"])
            report(f"Created {name} (ID {workout_id}); checking stored workout.")
        elif item.action == "update":
            api.update_workout(workout_id, item.payload)
            report(f"Updated {name} (ID {workout_id}); checking stored workout.")
        if workout_id is None:
            raise SyncError(f"No workout ID for {name}.")
        stored = api.get_workout_by_id(workout_id)
        if canonical(stored) != canonical(item.payload):
            raise SyncError(
                f"Stored {name} (ID {workout_id}) differs from the requested structure. "
                "Stopped before further writes or device sends; inspect workouts show."
            )
        results.append(
            {
                "name": name,
                "action": item.action,
                "workoutId": workout_id,
                "verified": True,
                "sendQueued": False,
            }
        )
    # Verify every selected workout before queuing any for the watch.
    if device_id is not None:
        for result in results:
            api.push_workout_to_device(result["workoutId"], device_id)
            result["sendQueued"] = True
            report(
                f"Queued {result['name']} for device {device_id}; phone/watch sync is still needed."
            )
    return results
