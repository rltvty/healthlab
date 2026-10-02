"""Lifted authentication, logs, and completed-activity reconciliation."""

import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer

from garmin_workouts.auth import connect
from garmin_workouts.lifted import LiftedClient, LiftedError, private_json
from garmin_workouts.reconcile import (
    BERLIN,
    ActivityPlan,
    ReconcileError,
    apply_plan,
    backup_root,
    load_mappings,
    match_classes,
    propose,
    restore_backup,
)

app = typer.Typer(help="Sign in to Lifted and download exercise logs.", no_args_is_help=True)


@contextmanager
def errors():
    try:
        yield
    except (LiftedError, ReconcileError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    except (OSError, ValueError, KeyError, TypeError):
        typer.echo("Could not read/save Lifted data or its format was unexpected.", err=True)
        raise typer.Exit(1) from None


@app.command()
def login():
    """Sign in with Lifted email/password; save refreshable tokens, never the password."""
    email = typer.prompt("Lifted email").strip()
    password = typer.prompt("Lifted password", hide_input=True)
    with errors():
        client = LiftedClient()
        client.login(email, password)
        password = None
        client.customer()
        typer.echo(f"Login and customer lookup successful. Session saved to {client.path}")


@app.command("logs")
def logs(
    source: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    day: Annotated[str | None, typer.Option("--date", help="Class date in Europe/Berlin.")] = None,
    output: Annotated[
        Path | None, typer.Option(help="Save raw logs to a private JSON file.")
    ] = None,
):
    """Read logs online, or inspect a copied JSON response offline."""
    with errors():
        selected_day = date.fromisoformat(day) if day else None
        if source:
            data = json.loads(source.read_text())
        else:
            client = LiftedClient()
            client.restore()
            data = client.logs()
        if selected_day:
            data = [
                w
                for w in data
                if datetime.fromisoformat(w["start_datetime"])
                .astimezone(ZoneInfo("Europe/Berlin"))
                .date()
                == selected_day
            ]
        if output:
            private_json(output, data)
            typer.echo(f"Saved {len(data)} workouts to {output}")
        else:
            # Deliberately exclude Lifted reps: Garmin's recorded reps are authoritative.
            summary = [
                {
                    "workoutId": w["workout_id"],
                    "start": w["start_datetime"],
                    "attended": w["has_attended"],
                    "sets": [
                        {
                            k: s.get(k)
                            for k in (
                                "exercise_number",
                                "set_number",
                                "set_type",
                                "exercise_name",
                                "weight",
                            )
                        }
                        for s in w["exercise_logs"]
                    ],
                }
                for w in data
            ]
            typer.echo(json.dumps(summary, indent=2))


@app.command("sync")
def sync_activities(
    days: Annotated[
        int, typer.Option(min=1, max=90, help="Recent calendar days, including today.")
    ] = 7,
    day: Annotated[
        str | None, typer.Option("--date", help="One class date instead of --days.")
    ] = None,
    mappings: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "config/lifted-exercises.toml"
    ),
    backups: Annotated[
        Path | None, typer.Option(help="Override the private activity backup directory.")
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply")] = True,
):
    """Update recorded Lifted activities from class logs; preview by default."""
    # Reuse Garmin's sanitized errors without coupling its login to Lifted login.
    from garmin_workouts.cli import account_errors

    with account_errors(), errors():
        mapping = load_mappings(mappings)
        end = date.fromisoformat(day) if day else datetime.now(BERLIN).date()
        start = end if day else end - timedelta(days=days - 1)
        lifted = LiftedClient()
        lifted.restore()
        classes = lifted.logs()
        api = connect()
        activities = api.get_activities_by_date(start.isoformat(), end.isoformat())
        plans = []
        report = []
        for activity, matched, error in match_classes(activities, classes):
            item = {"activityId": activity["activityId"], "name": activity["activityName"]}
            report.append(item)
            if error:
                item.update(status="needs review", reason=error)
                continue
            try:
                before = api.get_activity_exercise_sets(activity["activityId"])
                after, changes = propose(activity, before, matched, mapping)
            except (ReconcileError, KeyError, TypeError, ValueError) as error:
                item.update(
                    status="needs review",
                    reason=str(error)
                    if isinstance(error, ReconcileError)
                    else "Unexpected activity or class data.",
                )
                continue
            plans.append(ActivityPlan(activity, matched, before, after, changes))
            item.update(status="update" if changes else "unchanged", changes=changes)
        typer.echo(json.dumps({"dryRun": dry_run, "activities": report}, indent=2))
        if any(item["status"] == "needs review" for item in report):
            raise ReconcileError(
                "Review the flagged activities/mappings; no activity writes were made. "
                "Use --date to narrow the selection."
            )
        if not dry_run:
            for plan in plans:
                folder = apply_plan(api, plan, backups or backup_root())
                if folder:
                    typer.echo(
                        f"Updated and verified {plan.activity['activityId']}. Backup: {folder}"
                    )


@app.command("restore")
def restore_activity(
    backup: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    dry_run: Annotated[bool, typer.Option("--dry-run/--apply")] = True,
):
    """Restore an activity backup if no subsequent changes would be overwritten."""
    from garmin_workouts.cli import account_errors

    with account_errors(), errors():
        result = restore_backup(connect(), backup, apply=not dry_run)
        typer.echo(json.dumps(result, indent=2))
