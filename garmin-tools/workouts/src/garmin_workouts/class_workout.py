"""Offline, declarative class generation; watch behavior remains unverified."""

import tomllib
from pathlib import Path
from typing import Annotated, Literal, Self

from garminconnect import exercises
from garminconnect.workout import (
    WEIGHT_UNIT_KILOGRAM,
    ExecutableStep,
    StrengthWorkout,
    WorkoutSegment,
    create_repeat_group,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

PositiveInt = Annotated[int, Field(gt=0)]
Name = Annotated[str, Field(min_length=1, pattern=r"\S")]


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Timing(ConfigModel):
    mode: Literal["time", "lap"] = "time"
    seconds: PositiveInt | None = None

    @model_validator(mode="after")
    def check_seconds(self) -> Self:
        if self.mode == "time" and self.seconds is None:
            raise ValueError("time mode requires seconds")
        if self.mode == "lap" and self.seconds is not None:
            raise ValueError("lap mode must omit seconds")
        return self


class Block(Timing):
    name: Name
    kind: Literal["warmup", "interval", "rest", "cooldown"]
    enabled: bool = True
    category: str | None = None
    weight: Literal["body"] | None = None

    @model_validator(mode="after")
    def known_category(self) -> Self:
        if self.category is not None and self.category not in exercises.CATEGORIES:
            raise ValueError(f"Unknown exercise category: {self.category}")
        if self.weight is not None and self.category is None:
            raise ValueError("Block weight requires an exercise category")
        return self


class Defaults(ConfigModel):
    sets: PositiveInt = 3
    reps: PositiveInt = 8
    work_mode: Literal["reps", "lap"] = "reps"


class Station(ConfigModel):
    number: Annotated[int, Field(ge=1, le=6)]
    name: Name
    exercise: Name | None = None
    sets: PositiveInt | None = None
    reps: PositiveInt | None = None
    work_mode: Literal["reps", "lap", "time"] | None = None
    work_seconds: PositiveInt | None = None

    @model_validator(mode="after")
    def known_exercise(self) -> Self:
        if self.work_mode == "time" and self.work_seconds is None:
            raise ValueError("time work mode requires work_seconds")
        if self.work_mode != "time" and self.work_seconds is not None:
            raise ValueError("work_seconds requires time work mode")
        if self.exercise is not None and exercises.resolve(self.exercise) is None:
            raise ValueError(f"Unknown catalog exercise: {self.exercise}; use exercises search")
        return self


class ClassConfig(ConfigModel):
    name: Name
    defaults: Defaults = Field(default_factory=Defaults)
    rest: Timing
    transition: Timing
    stations: list[Station]
    before: list[Block] = Field(default_factory=list)
    after: list[Block] = Field(default_factory=list)

    @model_validator(mode="after")
    def six_stations(self) -> Self:
        if sorted(station.number for station in self.stations) != list(range(1, 7)):
            raise ValueError("Define each station number 1 through 6 exactly once")
        return self


def load_config(path: Path) -> ClassConfig:
    with path.open("rb") as config_file:
        return ClassConfig.model_validate(tomllib.load(config_file))


def rotate_stations(config: ClassConfig, start: int) -> list[Station]:
    if start not in range(1, 7):
        raise ValueError("Starting station must be 1 through 6")
    stations = sorted(config.stations, key=lambda station: station.number)
    return stations[start - 1 :] + stations[: start - 1]


def make_step(
    order: int,
    kind: str,
    mode: str,
    value: int | None,
    description: str,
    exercise: str | None = None,
) -> ExecutableStep:
    step_ids = {"warmup": 1, "cooldown": 2, "interval": 3, "rest": 5}
    condition_ids = {"lap": 1, "time": 2, "reps": 10}
    condition_id = condition_ids[mode]
    extra = {}
    if exercise is not None:
        entry = exercises.resolve(exercise)
        if entry is None:
            raise ValueError(f"Unknown catalog exercise: {exercise}")
        extra = {"category": entry["category"], "exerciseName": entry["exercise"]}
    return ExecutableStep(
        stepOrder=order,
        stepType={"stepTypeId": step_ids[kind], "stepTypeKey": kind},
        endCondition={
            "conditionTypeId": condition_id,
            "conditionTypeKey": "lap.button" if mode == "lap" else mode,
            "displayOrder": condition_id,
            "displayable": True,
        },
        endConditionValue=None if mode == "lap" else value,
        targetType={"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
        description=description,
        **extra,
    )


def build_rotation(config: ClassConfig, start: int) -> StrengthWorkout:
    steps = []
    order = 1

    def append_blocks(blocks: list[Block]) -> None:
        nonlocal order
        for block in blocks:
            if block.enabled:
                step = make_step(order, block.kind, block.mode, block.seconds, block.name)
                if block.category is not None:
                    step = step.model_copy(update={"category": block.category})
                if block.weight == "body":
                    step = step.model_copy(
                        update={"weightValue": 0.0, "weightUnit": dict(WEIGHT_UNIT_KILOGRAM)}
                    )
                steps.append(step)
                order += 1

    append_blocks(config.before)
    stations = rotate_stations(config, start)
    for position, station in enumerate(stations):
        sets = station.sets if station.sets is not None else config.defaults.sets
        reps = station.reps if station.reps is not None else config.defaults.reps
        mode = station.work_mode or config.defaults.work_mode
        label = f"{station.number} - {station.name}"
        steps.append(
            create_repeat_group(
                sets,
                [
                    make_step(
                        order + 1,
                        "interval",
                        mode,
                        station.work_seconds if mode == "time" else reps,
                        f"{label}: target {reps} reps",
                        station.exercise,
                    ),
                    make_step(
                        order + 2,
                        "rest",
                        config.rest.mode,
                        config.rest.seconds,
                        f"Rest - {label}",
                    ),
                ],
                order,
            )
        )
        order += 3
        if position < len(stations) - 1:
            next_station = stations[position + 1]
            steps.append(
                make_step(
                    order,
                    "rest",
                    config.transition.mode,
                    config.transition.seconds,
                    f"Transition to {next_station.number} - {next_station.name}",
                )
            )
            order += 1
    append_blocks(config.after)
    sport = {"sportTypeId": 5, "sportTypeKey": "strength_training"}
    return StrengthWorkout(
        workoutName=f"{config.name} {start}",
        description="Station order: " + " → ".join(str(s.number) for s in stations),
        estimatedDurationInSecs=0,
        workoutSegments=[WorkoutSegment(segmentOrder=1, sportType=sport, workoutSteps=steps)],
    )


def summarize(config: ClassConfig, start: int, workout: StrengthWorkout) -> dict:
    return {
        "name": workout.workoutName,
        "before": [block.model_dump(exclude_none=True) for block in config.before if block.enabled],
        "rest": config.rest.model_dump(exclude_none=True),
        "transition": config.transition.model_dump(exclude_none=True),
        "after": [block.model_dump(exclude_none=True) for block in config.after if block.enabled],
        "stations": [
            {
                "number": station.number,
                "name": station.name,
                "exercise": station.exercise,
                "sets": station.sets or config.defaults.sets,
                "reps": station.reps or config.defaults.reps,
                "workMode": station.work_mode or config.defaults.work_mode,
                "workSeconds": station.work_seconds,
            }
            for station in rotate_stations(config, start)
        ],
        "steps": len(workout.workoutSegments[0].workoutSteps),
        "unmappedStations": [
            s.number for s in rotate_stations(config, start) if s.exercise is None
        ],
    }
