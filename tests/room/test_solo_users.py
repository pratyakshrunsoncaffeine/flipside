"""flip solo's local users: a second clone must not invent passwords for existing users."""

import json
from pathlib import Path
from typing import Any

import pytest

from flipside.room import solo
from flipside.room.switch_client import Http


class Admin(Http):
    def __init__(self, emails: list[str]) -> None:
        super().__init__("http://fake")
        self.emails = emails
        self.created: list[str] = []

    def get(self, path: str) -> Any:
        return [{"email": e} for e in self.emails]

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        assert body is not None
        self.created.append(body["email"])
        return {}


def test_existing_user_without_local_password_stops_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Found in a second clone: person() made a new password for author@flipside.local,
    # saved it over nothing, and the login failed with 401.
    creds = tmp_path / ".local-users.json"
    monkeypatch.setattr(solo, "CREDS", creds)
    with pytest.raises(SystemExit, match="copy that file"):
        solo.person(Admin(["author@flipside.local"]), "http://fake", "author")
    assert not creds.exists()


def test_new_user_is_created_with_a_private_creds_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creds = tmp_path / ".local-users.json"
    monkeypatch.setattr(solo, "CREDS", creds)
    admin = Admin([])
    logins: list[str] = []
    monkeypatch.setattr(Http, "login", lambda self, email, pw: logins.append(email))
    monkeypatch.setattr(Http, "get", lambda self, path: [] if "users" in path else {"id": "u1"})
    solo.person(admin, "http://fake", "reviewer")
    assert admin.created == ["reviewer@flipside.local"] and logins == ["reviewer@flipside.local"]
    assert json.loads(creds.read_text())["reviewer"]["email"] == "reviewer@flipside.local"
    assert creds.stat().st_mode & 0o777 == 0o600
