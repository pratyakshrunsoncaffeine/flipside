"""``flip demo``: the pinned Compose file and the generated server config."""

import hashlib
import json
import stat
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from flipside.room import demo


def test_server_config_is_private_complete_and_written_once(tmp_path: Path) -> None:
    path = tmp_path / "stack.conf"
    demo.write_conf(path)
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
