"""Garmin account login and read-only device discovery."""

import json
from contextlib import contextmanager
from importlib.metadata import version

import typer
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from garmin_workouts.auth import connect, session_directory

app = typer.Typer(help="Garmin Connect account tools.", no_args_is_help=True)
auth_app = typer.Typer(help="Sign in and save a local session.", no_args_is_help=True)
device_app = typer.Typer(help="Read devices registered with Garmin Connect.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(device_app, name="devices")


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
