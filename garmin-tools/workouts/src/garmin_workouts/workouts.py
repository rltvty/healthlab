"""Minimal strength-workout proof of concept using upstream typed models."""

from garminconnect import Garmin, exercises
from garminconnect.workout import StrengthWorkout, WorkoutSegment, create_strength_set

TEST_WORKOUT_NAME = "TEST - Berlin Strength - RDL 3x8"


def build_test_workout(rest_seconds: int = 30) -> StrengthWorkout:
    if rest_seconds <= 0:
        raise ValueError("Rest duration must be positive")
    exercise = exercises.resolve("Romanian Deadlift")
    if exercise is None:
        raise ValueError("Romanian Deadlift is missing from the installed exercise catalog")
    return StrengthWorkout(
        workoutName=TEST_WORKOUT_NAME,
        description="Proof of concept: 3 x 8 Romanian Deadlift; timed rest after every set.",
        estimatedDurationInSecs=0,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 5, "sportTypeKey": "strength_training"},
                workoutSteps=[
                    create_strength_set(
                        exercise["category"],
                        step_order=1,
                        sets=3,
                        reps=8,
                        rest_seconds=rest_seconds,
                        exercise_name=exercise["exercise"],
                    )
                ],
            )
        ],
    )


def plan_test_workout(api: Garmin, workout: StrengthWorkout) -> dict:
    """Check every page for name collisions; never mutate an existing workout."""
    matches = []
    start = 0
    while True:
        page = api.get_workouts(start=start, limit=100)
        matches.extend(
            item["workoutId"] for item in page if item.get("workoutName") == workout.workoutName
        )
        if len(page) < 100:
            break
        start += len(page)
    return {
        "action": "exists" if matches else "create",
        "existingWorkoutIds": matches,
        "pushToDevice": False,
        "payload": workout.to_dict(),
    }
