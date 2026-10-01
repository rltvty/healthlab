# Garmin workouts

Personal Garmin Connect tooling for a Forerunner 970, built with
[python-garminconnect](https://github.com/cyberjunky/python-garminconnect).
Currently supports account login and read-only device listing.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13. From this directory:

```sh
uv sync --locked
uv run garmin-tools --help
```

## Login

```sh
uv run garmin-tools auth login
```

Login reuses a saved session when available. Otherwise, enter your email,
password, and MFA code when prompted. Password and MFA input are hidden.
Login can take several minutes while the library tries its authentication methods.

Session tokens are saved locally; passwords are not stored. On macOS, the token
file is `~/Library/Application Support/garmin-workouts/session/garmin_tokens.json`.
Keep this file private and out of Git.

The login flow follows the library's
[upstream example](https://github.com/cyberjunky/python-garminconnect/blob/master/example.py).
No separate example script is required.

## List devices

```sh
uv run garmin-tools devices list
```

Prints registered devices and their capabilities as JSON, using the saved session.
Run `auth login` again if the session expires. This reads your Garmin Connect
account; it does not pair directly with the watch or change account data.

## Development

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Tests use mocked Garmin responses and require no account credentials.
