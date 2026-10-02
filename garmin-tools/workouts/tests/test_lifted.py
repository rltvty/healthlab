import json
import stat
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from garmin_workouts.cli import app
from garmin_workouts.lifted import LiftedClient, LiftedError


def test_password_login_stores_only_tokens_privately(tmp_path, monkeypatch):
    request = Mock(
        return_value=Mock(
            status_code=200,
            json=lambda: {
                "email": "test@example.com",
                "localId": "user",
                "idToken": "token",
                "refreshToken": "refresh",
                "expiresIn": "3600",
            },
        )
    )
    monkeypatch.setattr("garmin_workouts.lifted.requests.request", request)
    path = tmp_path / "tokens.json"
    client = LiftedClient(path)
    client.login(" test@example.com ", "secret-password")
    assert "secret-password" not in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert request.call_args.kwargs["json"]["email"] == "test@example.com"
    assert request.call_args.kwargs["allow_redirects"] is False


def test_expired_session_refreshes_and_persists_rotated_token(tmp_path, monkeypatch):
    path = tmp_path / "tokens.json"
    path.write_text(
        json.dumps(
            {
                "email": "test@example.com",
                "user_id": "user",
                "id_token": "old",
                "refresh_token": "refresh",
                "expires_at": 0,
            }
        )
    )
    request = Mock(
        return_value=Mock(
            status_code=200,
            json=lambda: {
                "user_id": "user",
                "id_token": "new",
                "refresh_token": "rotated",
                "expires_in": "3600",
            },
        )
    )
    monkeypatch.setattr("garmin_workouts.lifted.requests.request", request)
    client = LiftedClient(path)
    client.restore()
    assert client.session["id_token"] == "new"
    assert json.loads(path.read_text())["refresh_token"] == "rotated"
    assert request.call_args.kwargs["data"]["grant_type"] == "refresh_token"


def test_login_error_does_not_expose_response(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "garmin_workouts.lifted.requests.request",
        Mock(
            return_value=Mock(
                status_code=400, text="secret token", json=lambda: {"secret": "token"}
            )
        ),
    )
    with pytest.raises(LiftedError) as error:
        LiftedClient(tmp_path / "tokens.json").login("test@example.com", "password")
    assert "secret" not in str(error.value)
    assert not (tmp_path / "tokens.json").exists()


def test_offline_logs_filter_berlin_date_and_exclude_lifted_reps(tmp_path, monkeypatch):
    monkeypatch.setattr("garmin_workouts.lifted.requests.request", Mock(side_effect=AssertionError))
    path = tmp_path / "logs.json"
    path.write_text(
        json.dumps(
            [
                {
                    "workout_id": "workout",
                    "start_datetime": "2026-10-01T23:15:00Z",
                    "has_attended": True,
                    "exercise_logs": [
                        {
                            "exercise_number": 3,
                            "set_number": 1,
                            "set_type": "main",
                            "exercise_name": "Reverse Lunge",
                            "weight": 10,
                            "reps": 4,
                        }
                    ],
                }
            ]
        )
    )
    result = CliRunner().invoke(
        app, ["lifted", "logs", "--source", str(path), "--date", "2026-10-02"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["sets"][0]["weight"] == 10
    assert "reps" not in result.stdout
