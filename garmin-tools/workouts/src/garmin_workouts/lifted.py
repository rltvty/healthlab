"""Firebase session and read-only Lifted dashboard access."""

import json
import os
import tempfile
import time
from pathlib import Path
from uuid import UUID

import requests
from platformdirs import user_data_path

# Public Firebase web app identifier from Lifted's dashboard bundle, not a secret.
API_KEY = "AIzaSyDPK-r1RSlQbMHeLS5oSTzEuV5K7Imnt7Q"
API_URL = "https://api.lifted-studios.com"


class LiftedError(Exception):
    """Safe-to-display error without response bodies or credentials."""


def token_path() -> Path:
    return user_data_path("garmin-workouts", appauthor=False) / "lifted" / "session.json"


def private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class LiftedClient:
    def __init__(self, path: Path | None = None):
        self.path = path or token_path()
        self.session: dict = {}

    def request(self, method: str, url: str, **kwargs):
        try:
            response = requests.request(method, url, timeout=30, allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise LiftedError("Could not connect to Lifted/Firebase. Try again later.") from None
        if not 200 <= response.status_code < 300:
            if response.status_code == 401:
                raise LiftedError("Session rejected. Run lifted login again.")
            if response.status_code == 400:
                raise LiftedError(
                    "Sign-in or refresh failed. Check your Lifted email/password; Google-only, "
                    "MFA, or CAPTCHA accounts may need browser login."
                )
            raise LiftedError(f"Lifted/Firebase returned HTTP {response.status_code}.")
        try:
            return response.json()
        except ValueError:
            raise LiftedError("Lifted/Firebase returned an invalid response.") from None

    def save_tokens(self, data: dict, *, refreshing: bool = False) -> None:
        try:
            self.session = {
                "email": self.session.get("email") if refreshing else data["email"],
                "user_id": data["user_id" if refreshing else "localId"],
                "id_token": data["id_token" if refreshing else "idToken"],
                "refresh_token": data["refresh_token" if refreshing else "refreshToken"],
                "expires_at": time.time() + int(data["expires_in" if refreshing else "expiresIn"]),
            }
            if not all(self.session.values()):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise LiftedError(
                "Incomplete authentication response; browser sign-in may be needed."
            ) from None
        private_json(self.path, self.session)

    def login(self, email: str, password: str) -> None:
        data = self.request(
            "POST",
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
            params={"key": API_KEY},
            json={"email": email.strip(), "password": password, "returnSecureToken": True},
        )
        self.save_tokens(data)

    def restore(self) -> None:
        try:
            self.session = json.loads(self.path.read_text())
            if not isinstance(self.session, dict) or not all(
                self.session.get(key) for key in ("email", "user_id", "id_token", "refresh_token")
            ):
                raise ValueError
            expires = float(self.session["expires_at"])
        except (OSError, ValueError, KeyError, TypeError):
            raise LiftedError("No valid Lifted session. Run garmin-tools lifted login.") from None
        if expires <= time.time() + 60:
            self.refresh()

    def refresh(self) -> None:
        data = self.request(
            "POST",
            "https://securetoken.googleapis.com/v1/token",
            params={"key": API_KEY},
            data={"grant_type": "refresh_token", "refresh_token": self.session["refresh_token"]},
        )
        self.save_tokens(data, refreshing=True)

    def get(self, path: str, **params):
        return self.request(
            "GET",
            API_URL + path,
            params=params,
            headers={"Authorization": f"Bearer {self.session['id_token']}"},
        )

    def customer(self) -> dict:
        data = self.get("/customers", email=self.session["email"])
        matches = [
            item
            for item in data.get("customers", [])
            if str(item.get("email", "")).casefold() == self.session["email"].casefold()
        ]
        if len(matches) != 1:
            raise LiftedError("Expected exactly one customer for your login email.")
        return matches[0]

    def logs(self) -> list[dict]:
        customer = self.customer()
        customer_id = str(UUID(customer["id"]))
        data = self.get(f"/customers/{customer_id}/exercise_logs")
        if not isinstance(data, list):
            raise LiftedError("Unexpected exercise-log response.")
        return data
