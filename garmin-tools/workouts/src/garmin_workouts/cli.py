"""Garmin account discovery and a minimal strength-workout experiment."""

import json
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal

import typer
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    exercises,
)

from garmin_workouts.auth import connect, session_directory
from garmin_workouts.class_workout import build_rotation, load_config, summarize
from garmin_workouts.lifted_cli import app as lifted_app
from garmin_workouts.sync import SyncError, apply_sync, plan_sync
from garmin_workouts.workouts import build_test_workout, plan_test_workout

app = typer.Typer(help="Garmin Connect account tools.", no_args_is_help=True)
auth_app = typer.Typer(help="Sign in and save a local session.", no_args_is_help=True)
device_app = typer.Typer(help="Read devices registered with Garmin Connect.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(device_app, name="devices")
exercise_app = typer.Typer(help="Search the bundled exercise catalog.", no_args_is_help=True)
workout_app = typer.Typer(help="Inspect workouts and create a strength test.", no_args_is_help=True)
app.add_typer(exercise_app, name="exercises")
app.add_typer(workout_app, name="workouts")
app.add_typer(lifted_app, name="lifted")


@workout_app.command("sync")
def sync_class(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/berlin-strength.toml"
    ),
    start: Annotated[int | None, typer.Option(min=1, max=6)] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply")] = True,
    device: Annotated[
        int | None, typer.Option(min=1, help="Queue workouts for this device ID.")
    ] = None,
) -> None:
    """Create/update class workouts by name; default is a read-only plan."""
    try:
        definition = load_config(config)
        payloads = [
            build_rotation(definition, first).to_dict()
            for first in ([start] if start is not None else range(1, 7))
        ]
    except (ValueError, OSError) as error:
        typer.echo(f"Invalid workout configuration: {error}", err=True)
        raise typer.Exit(2) from None
    with account_errors():
        api = connect()
        try:
            plan = plan_sync(api, payloads, device)
            if dry_run:
                result = {"dryRun": True, "workouts": [item.summary(device) for item in plan]}
            else:
                result = {
                    "dryRun": False,
                    "workouts": apply_sync(
                        api, plan, device, report=lambda message: typer.echo(message, err=True)
                    ),
                }
        except SyncError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(1) from None
    typer.echo(json.dumps(result, indent=2))


@workout_app.command("generate")
def generate_class(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/berlin-strength.toml"
    ),
    start: Annotated[int | None, typer.Option(min=1, max=6)] = None,
    output_format: Annotated[Literal["summary", "json"], typer.Option("--format")] = "summary",
) -> None:
    """Generate one or all six class rotations offline; no Garmin writes."""
    try:
        definition = load_config(config)
        rotations = [start] if start is not None else range(1, 7)
        result = []
        for first in rotations:
            workout = build_rotation(definition, first)
            result.append(
                workout.to_dict()
                if output_format == "json"
                else summarize(definition, first, workout)
            )
    except (ValueError, OSError) as error:
        typer.echo(f"Invalid workout configuration: {error}", err=True)
        raise typer.Exit(2) from None
    typer.echo(json.dumps(result, indent=2))


@exercise_app.command("search")
def search_exercises(term: str) -> None:
    """Print matching exercise names and identifiers as JSON; no login needed."""
    typer.echo(json.dumps(exercises.find(term), indent=2))


@workout_app.command("list")
def list_workouts(
    start: Annotated[int, typer.Option(min=0)] = 0,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 100,
) -> None:
    """Read one page of account workouts as JSON."""
    with account_errors():
        result = connect().get_workouts(start=start, limit=limit)
    typer.echo(json.dumps(result, indent=2))


@workout_app.command("show")
def show_workout(workout_id: Annotated[int, typer.Argument(min=1)]) -> None:
    """Read a workout's full Garmin representation."""
    with account_errors():
        result = connect().get_workout_by_id(workout_id)
    typer.echo(json.dumps(result, indent=2))


@workout_app.command("preview")
def preview_workout(rest_seconds: Annotated[int, typer.Option(min=1)] = 30) -> None:
    """Print the 3 x 8 deadlift payload offline."""
    typer.echo(json.dumps(build_test_workout(rest_seconds).to_dict(), indent=2))


@workout_app.command("create-test")
def create_test_workout(
    rest_seconds: Annotated[int, typer.Option(min=1)] = 30,
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply")] = True,
) -> None:
    """Plan the test workout; --apply creates it if no same-named workout exists."""
    workout = build_test_workout(rest_seconds)
    with account_errors():
        api = connect()
        plan = plan_test_workout(api, workout)
        if dry_run:
            typer.echo(json.dumps({"dryRun": True, **plan}, indent=2))
            return
        if plan["action"] == "exists":
            typer.echo(
                json.dumps(
                    {
                        "created": False,
                        "reason": "Name already exists; no changes made",
                        "workoutIds": plan["existingWorkoutIds"],
                    },
                    indent=2,
                )
            )
            return
        result = api.upload_strength_workout(workout)
        typer.echo(
            json.dumps(
                {
                    "created": True,
                    "workoutId": result["workoutId"],
                    "workoutName": workout.workoutName,
                    "pushedToDevice": False,
                },
                indent=2,
            )
        )


@contextmanager
def account_errors():
    """Show actionable errors without exposing raw account or token data."""
    try:
        yield
    except (typer.Abort, typer.Exit):
        raise
    except GarminConnectAuthenticationError:
        typer.echo("No valid session. Run `garmin-tools auth login` to sign in.", err=True)
        raise typer.Exit(1) from None
    except GarminConnectTooManyRequestsError:
        typer.echo("Garmin returned HTTP 429. Stop retrying for now and try later.", err=True)
        raise typer.Exit(1) from None
    except GarminConnectConnectionError:
        typer.echo("Could not connect to Garmin. Check connectivity and try later.", err=True)
        raise typer.Exit(1) from None
    except OSError:
        typer.echo(
            "Could not access the local session files. Check directory permissions.", err=True
        )
        raise typer.Exit(1) from None
    except Exception as error:
        typer.echo(f"Garmin operation failed ({type(error).__name__}).", err=True)
        raise typer.Exit(1) from None


@auth_app.command("login")
def login() -> None:
    """Restore a session or prompt for email, password, and MFA."""
    with account_errors():
        connect(interactive=True)
    typer.echo(f"Connected. Session saved in {session_directory()}")


@device_app.command("list")
def list_devices() -> None:
    """Print registered devices as JSON using the saved session."""
    with account_errors():
        devices = connect().get_devices()
    typer.echo(json.dumps(devices, indent=2))


@app.command("version")
def show_version() -> None:
    """Show installed project and Garmin client versions."""
    typer.echo(f"garmin-workouts {version('garmin-workouts')}")
    typer.echo(f"garminconnect {version('garminconnect')}")
