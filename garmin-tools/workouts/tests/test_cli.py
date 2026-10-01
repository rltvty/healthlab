import json
import logging
from unittest.mock import Mock

import pytest
import typer
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from typer.testing import CliRunner

from garmin_workouts import auth, cli

runner = CliRunner()


def test_saved_session_reused_without_prompts(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "session_directory", lambda: tmp_path)
    api = Mock()
    monkeypatch.setattr(auth, "Garmin", lambda: api)
    monkeypatch.setattr(auth.typer, "prompt", Mock(side_effect=AssertionError("Must not prompt")))
    assert auth.connect(interactive=True) is api
    api.login.assert_called_once_with(str(tmp_path))
    api.client.dump.assert_called_once_with(str(tmp_path))


@pytest.mark.parametrize("error", [GarminConnectAuthenticationError, GarminConnectConnectionError])
def test_fresh_login_and_mfa_follow_upstream_flow(monkeypatch, tmp_path, error):
    monkeypatch.setattr(auth, "session_directory", lambda: tmp_path)
    restore, fresh = Mock(), Mock()
    restore.login.side_effect = error("No tokens")
    factory = Mock(side_effect=[restore, fresh])
    monkeypatch.setattr(auth, "Garmin", factory)
    answers = iter([" email@example.com ", "password", " 123456 "])
    prompt = Mock(side_effect=lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(auth.typer, "prompt", prompt)
    logger = logging.getLogger("garminconnect")
    previous_level = logger.level
    assert auth.connect(interactive=True) is fresh
    credentials = factory.call_args.kwargs
    assert credentials["email"] == "email@example.com"
    assert credentials["password"] == "password"
    assert credentials["prompt_mfa"]() == "123456"
    assert prompt.call_args.kwargs["hide_input"] is True
    fresh.login.assert_called_once_with(str(tmp_path))
    fresh.client.dump.assert_called_once_with(str(tmp_path))
    assert logger.level == previous_level


def test_device_listing_reads_without_writes(monkeypatch):
    api = Mock(spec=["get_devices"])
    api.get_devices.return_value = [{"displayName": "Forerunner 970", "deviceId": 123}]
    monkeypatch.setattr(cli, "connect", lambda: api)
    result = runner.invoke(cli.app, ["devices", "list"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == api.get_devices.return_value
    api.get_devices.assert_called_once_with()


def test_device_listing_does_not_prompt_when_session_missing(monkeypatch):
    api = Mock()
    api.login.side_effect = GarminConnectAuthenticationError("No tokens")
    monkeypatch.setattr(auth, "Garmin", lambda: api)
    prompt = Mock(side_effect=AssertionError("Must not prompt"))
    monkeypatch.setattr(auth.typer, "prompt", prompt)
    result = runner.invoke(cli.app, ["devices", "list"])
    assert result.exit_code == 1
    assert "auth login" in result.output
    prompt.assert_not_called()


def test_rate_limit_stops_without_prompt_or_retry(monkeypatch):
    api = Mock()
    api.login.side_effect = GarminConnectTooManyRequestsError("SECRET")
    monkeypatch.setattr(auth, "Garmin", lambda: api)
    prompt = Mock(side_effect=AssertionError("Must not prompt"))
    monkeypatch.setattr(auth.typer, "prompt", prompt)
    result = runner.invoke(cli.app, ["auth", "login"])
    assert result.exit_code == 1
    assert "HTTP 429" in result.output
    assert "SECRET" not in result.output
    api.login.assert_called_once()
    prompt.assert_not_called()


def test_login_cancellation_is_not_a_connection_failure(monkeypatch):
    monkeypatch.setattr(cli, "connect", Mock(side_effect=typer.Abort()))
    result = runner.invoke(cli.app, ["auth", "login"])
    assert result.exit_code == 1
    assert "Aborted" in result.output
    assert "Garmin operation failed" not in result.output


def test_save_failure_does_not_report_success(monkeypatch):
    api = Mock()
    api.client.dump.side_effect = PermissionError("SECRET PATH")
    monkeypatch.setattr(auth, "Garmin", lambda: api)
    result = runner.invoke(cli.app, ["auth", "login"])
    assert result.exit_code == 1
    assert "Connected." not in result.output
    assert "permissions" in result.output
    assert "SECRET" not in result.output


def test_api_errors_do_not_expose_sensitive_details(monkeypatch):
    monkeypatch.setattr(cli, "connect", Mock(side_effect=RuntimeError("SECRET TOKEN")))
    result = runner.invoke(cli.app, ["devices", "list"])
    assert result.exit_code == 1
    assert "SECRET TOKEN" not in result.output
