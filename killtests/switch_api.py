"""Minimal client for a local Switch server (switch-core 0.31.0), used by the kill tests."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar

BASE = os.environ.get("SWITCH_BASE", "http://127.0.0.1:52370")
# Switch Console's env file on macOS; FLIP_SWITCH_ENV overrides it (Windows, Linux), as in
# flipside/room/solo.py.
CONSOLE_ENV = (
    pathlib.Path.home()
    / "Library/Application Support/switchdash/local-switch-server/native/run/switch-core.env"
)


def utf8_stdio() -> None:
    """Print UTF-8 on every OS: a redirected stream on Windows is cp1252, which cannot hold
    every character in a Switch reply (same as flipside/cli.py)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def env_file() -> pathlib.Path:
    return pathlib.Path(os.environ.get("FLIP_SWITCH_ENV", str(CONSOLE_ENV)))


def console_env() -> dict[str, str]:
    out = {}
    for line in env_file().read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


class HTTPError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"{status}: {body[:400]}")
        self.status, self.body = status, body


class Client:
    def __init__(self, bearer: str | None = None):
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.bearer = bearer

    def call(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.bearer:
            req.add_header("Authorization", f"Bearer {self.bearer}")
        try:
            with self.opener.open(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise HTTPError(e.code, e.read().decode()) from None

    def login(self, email: str, password: str) -> dict:
        res = self.call("POST", "/gateway/auth/login", {"email": email, "password": password})
        tok = (res or {}).get("access_token") or (res or {}).get("token")
        if tok:
            self.bearer = tok
        return res


def rid() -> str:
    return uuid.uuid4().hex


class EventTap:
    """Collects an agent's server-sent events in a background thread."""

    def __init__(self, agent_id: str, api_key: str):
        self.events: list[str] = []
        self.agent_id, self.api_key = agent_id, api_key
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        req = urllib.request.Request(f"{BASE}/agents/{self.agent_id}/events")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Accept", "text/event-stream")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                for line in r:
                    s = line.decode(errors="replace").strip()
                    if s.startswith("data:"):
                        self.events.append(s[5:].strip())
        except Exception as e:  # recorded for the evidence log
            self.events.append(f"<stream closed: {e!r}>")
