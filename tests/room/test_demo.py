"""``flip demo``: the pinned Compose file and the generated server config."""

import hashlib
import json
import os
import stat
import subprocess
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from flipside.room import demo


def test_server_config_is_private_complete_and_written_once(tmp_path: Path) -> None:
    path = tmp_path / "stack.conf"
    demo.write_conf(path)
    if os.name == "posix":  # Windows has no owner-only mode bits
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    conf = demo._read_conf(path)
    for key in ("SWITCH_VERSION", "SECRET_KEYS", "GATEWAY_ADMIN_PASSWORD", "MATTERMOST_TEAM_NAME"):
        assert conf[key]
    assert conf["SWITCH_VERSION"] == demo.SWITCH_VERSION
    first = path.read_bytes()
    demo.write_conf(path)
    assert path.read_bytes() == first  # never regenerated under a running server


def _fake_registry(monkeypatch: pytest.MonkeyPatch, manifest: bytes, blob: bytes) -> None:
    def ghcr(path: str, token: str, accept: str = "") -> bytes:
        return manifest if path.startswith("manifests/") else blob

    class Resp:
        def __enter__(self) -> "Resp":
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"token": "t"}).encode()

    monkeypatch.setattr(demo, "_ghcr", ghcr)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Resp())


def test_compose_file_is_refused_unless_it_matches_the_pinned_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob = b"services: {}\n"
    manifest = json.dumps({"layers": [{"digest": demo.COMPOSE_BLOB}]}).encode()
    monkeypatch.setattr(demo, "COMPOSE_MANIFEST", "sha256:" + hashlib.sha256(manifest).hexdigest())
    _fake_registry(monkeypatch, manifest, blob)
    with pytest.raises(demo.DemoError, match="compose file does not match"):
        demo.fetch_compose(tmp_path / "compose.yml")
    assert not (tmp_path / "compose.yml").exists()


def test_compose_manifest_is_refused_unless_it_matches_the_pinned_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_registry(monkeypatch, b'{"layers": []}', b"")
    with pytest.raises(demo.DemoError, match="manifest does not match"):
        demo.fetch_compose(tmp_path / "compose.yml")


def test_a_matching_compose_file_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob = b"services: {}\n"
    digest = "sha256:" + hashlib.sha256(blob).hexdigest()
    manifest = json.dumps({"layers": [{"digest": digest}]}).encode()
    monkeypatch.setattr(demo, "COMPOSE_BLOB", digest)
    monkeypatch.setattr(demo, "COMPOSE_MANIFEST", "sha256:" + hashlib.sha256(manifest).hexdigest())
    _fake_registry(monkeypatch, manifest, blob)
    demo.fetch_compose(tmp_path / "compose.yml")
    assert (tmp_path / "compose.yml").read_bytes() == blob


class _Owner:
    """A person's gateway handle that may read only the rooms they created."""

    def __init__(self, rooms: dict[str, str]) -> None:
        self.rooms = rooms

    def get(self, path: str) -> Any:
        room = path.rsplit("/", 1)[1]
        if room not in self.rooms:
            raise PermissionError("Not authorized to read this resource")
        return {"external_channel_id": self.rooms[room]}


def test_each_rooms_channel_is_read_by_the_person_who_created_it() -> None:
    cast = SimpleNamespace(shared="r-shared", private="r-private")
    live = SimpleNamespace(
        cast=cast,
        reviewer_h=_Owner({"r-shared": "ch-shared"}),
        author_h=_Owner({"r-private": "ch-private"}),
    )
    assert demo.channels(live) == {"r-shared": "ch-shared", "r-private": "ch-private"}


class _Admin:
    """The demo server's admin: lists rooms, records deletes and connection changes."""

    def __init__(self, rooms: list[dict[str, Any]]) -> None:
        self.rooms = rooms
        self.calls: list[tuple[str, str, Any]] = []

    def get(self, path: str) -> Any:
        return self.rooms if path == "/gateway/rooms" else []

    def request(self, method: str, path: str, body: Any = None) -> Any:
        self.calls.append((method, path, body))
        return None


def test_a_run_clears_the_previous_runs_review_rooms_and_their_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rooms: list[dict[str, Any]] = [
        {"id": "r1", "name": "pr-142", "bridge_type": "mattermost"},
        {"id": "r2", "name": "pr-142-author", "bridge_type": "mattermost"},
        {"id": "r3", "name": "town-square", "bridge_type": "mattermost"},
        {"id": "r4", "name": "pr-142", "bridge_type": None},  # a Switch chat, not the demo's
        {"id": "r5", "name": "pr-142-notes", "bridge_type": "mattermost"},
    ]
    adm = _Admin(rooms)
    monkeypatch.setattr(demo, "admin", lambda _conf: adm)
    assert demo.clear_rooms({}) == 2
    assert adm.calls == [
        ("DELETE", "/gateway/rooms/r1?retire_channel=true", None),
        ("DELETE", "/gateway/rooms/r2?retire_channel=true", None),
    ]


def test_switchs_generic_agent_greetings_are_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    adm = _Admin([])
    monkeypatch.setattr(demo, "admin", lambda _conf: adm)
    demo.quiet_greetings({}, "b-1")
    assert adm.calls == [
        ("PATCH", "/gateway/collaborations/b-1", {"agent_greetings_enabled": False})
    ]


def _stack(tmp_path: Path) -> list[Path]:
    files = [tmp_path / n for n in ("stack.conf", "people.json", "users.json", "compose.yml")]
    for f in files:
        f.write_text("x", encoding="utf-8", newline="")
    return files


def test_down_keeps_the_config_when_docker_cannot_remove_the_stack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deleting the logins after a failed `compose down` would strand running containers."""
    files = _stack(tmp_path)
    monkeypatch.setattr(demo, "DIR", tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "daemon unavailable"),
    )
    assert demo.down() == 1
    assert all(f.exists() for f in files)
    assert "daemon unavailable" in capsys.readouterr().err


def test_down_removes_the_config_once_docker_has_removed_the_stack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = _stack(tmp_path)
    monkeypatch.setattr(demo, "DIR", tmp_path)
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", "")
    )
    assert demo.down() == 0
    assert not any(f.exists() for f in files)


def test_down_removes_the_stack_by_project_name_when_the_config_is_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Found 5 Nov 20:55 IST: with .flipside-demo/ missing, down printed "removed" and ran
    nothing, leaving Switch, Mattermost and Postgres running."""
    calls: list[list[str]] = []

    def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(demo, "DIR", tmp_path / "missing")
    monkeypatch.setattr(subprocess, "run", run)
    assert demo.down() == 0
    assert calls == [["docker", "compose", "-p", demo.PROJECT, "down", "-v", "--remove-orphans"]]


def test_a_run_archives_review_channels_no_room_bridges_any_more() -> None:
    """Channels left by rooms removed without retiring them stay in the sidebar (issue #63)."""

    class FakeMM:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def call(self, method: str, path: str, body: object = None) -> object:
            if method == "GET" and path == f"/teams/name/{demo.TEAM}":
                return {"id": "team1"}
            if method == "GET" and path.startswith("/teams/team1/channels/private"):
                return [
                    {"id": "old", "display_name": "pr-142-author", "delete_at": 0},
                    {"id": "gone", "display_name": "pr-142-author", "delete_at": 5},
                    {"id": "other", "display_name": "design-review", "delete_at": 0},
                ]
            if method == "GET" and path.startswith("/teams/team1/channels"):
                return [
                    {"id": "shared", "display_name": "pr-142", "delete_at": 0},
                    {"id": "town", "display_name": "Town Square", "delete_at": 0},
                ]
            if method == "DELETE":
                self.deleted.append(path)
                return {}
            raise AssertionError(f"unexpected {method} {path}")

    mm = FakeMM()
    assert demo.archive_stale_channels(mm) == 2  # type: ignore[arg-type]
    assert mm.deleted == ["/channels/shared", "/channels/old"]


def test_a_run_turns_off_mattermosts_email_preview_banner() -> None:
    """The demo sends no email, so Mattermost's "Preview Mode" banner is only noise (issue #63)."""
    calls: list[tuple[str, str, object]] = []

    class FakeMM:
        def call(self, method: str, path: str, body: object = None) -> object:
            calls.append((method, path, body))
            return {}

    demo.quiet_banner(FakeMM())  # type: ignore[arg-type]
    assert calls == [
        ("PUT", "/config/patch", {"EmailSettings": {"EnablePreviewModeBanner": False}})
    ]


def test_a_run_lets_the_printed_address_open_mattermosts_live_connection() -> None:
    """Mattermost refused the websocket from 127.0.0.1 with a 403, so a person who opened the
    printed address saw new posts only after switching channels (issue #63)."""
    calls: list[tuple[str, str, object]] = []

    class FakeMM:
        def call(self, method: str, path: str, body: object = None) -> object:
            calls.append((method, path, body))
            return {}

    demo.allow_printed_origin(FakeMM())  # type: ignore[arg-type]
    assert calls == [("PUT", "/config/patch", {"ServiceSettings": {"AllowCorsFrom": demo.MM_BASE}})]
