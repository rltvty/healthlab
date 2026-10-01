"""Session login following python-garminconnect's example.py init_api flow."""

import logging
from contextlib import contextmanager
from pathlib import Path

import typer
from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError
from platformdirs import user_data_path


def session_directory() -> Path:
    return user_data_path("garmin-workouts", appauthor=False) / "session"


@contextmanager
def quiet_login():
    """Match upstream's suppressed fallback warnings without changing global logging permanently."""
    logger = logging.getLogger("garminconnect")
    previous = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        logger.setLevel(previous)


def connect(*, interactive: bool = False) -> Garmin:
    """Restore tokens; only interactive login may request credentials."""
    directory = str(session_directory())
    with quiet_login():
        api = Garmin()
        try:
            api.login(directory)
        except (GarminConnectAuthenticationError, GarminConnectConnectionError):
            if not interactive:
                raise GarminConnectAuthenticationError("Run auth login to sign in") from None
        else:
            api.client.dump(directory)
            return api

        typer.echo("No valid session found. Please log in.")
        while True:
            email = typer.prompt("Garmin email").strip()
            password = typer.prompt("Garmin password", hide_input=True)
            api = Garmin(
                email=email,
                password=password,
                prompt_mfa=lambda: typer.prompt("Garmin MFA code", hide_input=True).strip(),
            )
            password = None
            typer.echo("Signing in. The library's fallback methods can take several minutes.")
            try:
                api.login(directory)
            except GarminConnectAuthenticationError:
                typer.echo(
                    "Authentication failed. Check your credentials and MFA, or Ctrl-C to cancel."
                )
                continue
            # Unlike upstream's login(), explicitly surface persistence errors.
            api.client.dump(directory)
            return api
