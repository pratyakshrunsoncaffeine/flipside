"""``flip demo``: the whole review on a real Switch server, in Mattermost, from one command.

    flip demo up      # start Switch and its bundled Mattermost in Docker; create the people
    flip demo run     # play the CSV-export case with both people acting in Mattermost
    flip demo logins  # the two Mattermost logins, to watch or act in the browser yourself
    flip demo down    # remove the containers, their data and the demo's local files

``up`` fetches Switch's published Compose file for one pinned release and checks it against
its pinned digest, writes a server config with fresh random secrets to ``.flipside-demo/``
(mode 0600, git-ignored), and starts switch-core, PostgreSQL and Mattermost. It then
creates the Author and the Reviewer as Switch users and as Mattermost users, and each
person claims their own Mattermost account in Switch. That claim is what lets Switch tell
the author's messages and button presses from anyone else's.

``run`` is ``flip solo --mattermost`` with the people in Mattermost: they post in the
bridged channels as themselves, and the author presses Approve on the card Switch renders
there. It writes ``evidence/demo-mattermost-<case>-<time>.log``.

Needs Docker with Compose v2. No model keys, no accounts anywhere else. Nothing is printed
that grants access, except by ``logins``, which prints the two local Mattermost passwords.
"""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from flipside.room.mattermost import MM, MattermostError, MattermostHumans
from flipside.room.replay import DEFAULT_CASE, ROOT
from flipside.room.run import Humans, Log
from flipside.room.switch_client import Http, SwitchError

SWITCH_VERSION = "0.31.0"
COMPOSE_REPO = "sandbox-quantum/standalone-compose"
# The OCI manifest of standalone-compose:0.31.0 and the one Compose file it holds.
COMPOSE_MANIFEST = "sha256:166a8f6ab77172e4278b402589893f0364271d854ef1c57401371a7909bb0d2c"
COMPOSE_BLOB = "sha256:cba238878078cf3d77fd9e136ef432f1ce5fd1bfe597acd172b9faa6720f0121"
PROJECT = "flipside-demo"
DIR = ROOT / ".flipside-demo"
API_PORT, MM_PORT, PG_PORT = 8100, 8065, 55432
BASE = f"http://127.0.0.1:{API_PORT}"
MM_BASE = f"http://127.0.0.1:{MM_PORT}"
TEAM = "flipside"
ROLES = ("author", "reviewer")


class DemoError(RuntimeError):
    """The demo stack is missing, unhealthy, or misconfigured."""


def _private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)  # binary: no CRT newline mapping on Windows
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.chmod(path, 0o600)


def _read_conf(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line
    )


def _ghcr(path: str, token: str, accept: str = "") -> bytes:
    req = urllib.request.Request(f"https://ghcr.io/v2/{COMPOSE_REPO}/{path}")
    req.add_header("Authorization", f"Bearer {token}")
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=60) as r:
        return bytes(r.read())


def fetch_compose(dest: Path) -> None:
    """Download the pinned Compose file and refuse it unless both digests match."""
    if dest.exists() and "sha256:" + hashlib.sha256(dest.read_bytes()).hexdigest() == COMPOSE_BLOB:
        return
    url = f"https://ghcr.io/token?scope=repository:{COMPOSE_REPO}:pull"
    with urllib.request.urlopen(url, timeout=60) as r:
        token = json.loads(r.read())["token"]
    manifest = _ghcr(
        f"manifests/{COMPOSE_MANIFEST}", token, "application/vnd.oci.image.manifest.v1+json"
    )
    if "sha256:" + hashlib.sha256(manifest).hexdigest() != COMPOSE_MANIFEST:
        raise DemoError("the standalone-compose manifest does not match its pinned digest")
    layers = [x["digest"] for x in json.loads(manifest)["layers"]]
    if layers != [COMPOSE_BLOB]:
        raise DemoError(f"unexpected standalone-compose layers {layers}")
    blob = _ghcr(f"blobs/{COMPOSE_BLOB}", token)
    if "sha256:" + hashlib.sha256(blob).hexdigest() != COMPOSE_BLOB:
        raise DemoError("the standalone-compose file does not match its pinned digest")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)


def write_conf(path: Path) -> None:
    """A server config with fresh random secrets, once per demo directory."""
    if path.exists():
        return

    def t() -> str:
        return secrets.token_urlsafe(24)

    conf = {
        "SWITCH_VERSION": SWITCH_VERSION,
        "DB_USER": "switch_app",
        "DB_PASSWORD": t(),
        "DB_OWNER_USER": "switchdb",
        "DB_OWNER_PASSWORD": t(),
        "DB_NAME": "switch",
        "AGENT_REGISTRATION_TOKEN": t(),
        "SECRET_KEYS": "demo001:" + secrets.token_hex(32),
        "GATEWAY_ADMIN_EMAIL": "admin@flipside.local",
        "GATEWAY_ADMIN_PASSWORD": t(),
        "FRONTEND_BASE_URL": "http://localhost:3000",
        "GATEWAY_PUBLIC_URL": BASE,
        # Mattermost requires a mixed-character password.
        "MATTERMOST_ADMIN_USER": "mmadmin",
        "MATTERMOST_ADMIN_PASSWORD": "Aa1!" + t(),
        "MATTERMOST_TEAM_NAME": TEAM,
        "MATTERMOST_USER": "flipside-demo",
        "MATTERMOST_USER_PASSWORD": "Aa1!" + t(),
        "API_HOST_PORT": str(API_PORT),
        "MATTERMOST_HOST_PORT": str(MM_PORT),
        "POSTGRES_HOST_PORT": str(PG_PORT),
        "TELEMETRY_ENABLED": "false",
        "THIRD_PARTY_AVATARS_ENABLED": "false",
    }
    _private_write(path, "".join(f"{k}={v}\n" for k, v in conf.items()))


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = [
        "docker",
        "compose",
        "-p",
        PROJECT,
        "--env-file",
        str(DIR / "stack.conf"),
        "-f",
        str(DIR / "compose.yml"),
        "--profile",
        "collab",
        *args,
    ]
    res = subprocess.run(cmd, cwd=DIR, text=True, capture_output=True)
    if check and res.returncode != 0:
        raise DemoError(f"docker compose {' '.join(args)} failed:\n{res.stderr[-2000:]}")
    return res


def admin(conf: dict[str, str]) -> Http:
    h = Http(BASE)
    h.login(conf["GATEWAY_ADMIN_EMAIL"], conf["GATEWAY_ADMIN_PASSWORD"])
    return h


def wait_ready(conf: dict[str, str], timeout: float = 600.0) -> str:
    """Wait until Switch accepts the admin and its Mattermost connection is active.
    Returns the connection id. Mattermost runs emulated on arm64, so first start is slow."""
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            for b in admin(conf).get("/gateway/collaborations") or []:
                if b.get("bridge_type") == "mattermost" and b.get("status") == "active":
                    return str(b["bridge_id"])
            last = "no active Mattermost connection yet"
        except (SwitchError, OSError) as e:
            last = str(e)[:120]
        time.sleep(3)
    raise DemoError(f"Switch or Mattermost not ready after {timeout:.0f} s: {last}")


def mm_admin(conf: dict[str, str]) -> MM:
    return MM(MM_BASE).login(conf["MATTERMOST_ADMIN_USER"], conf["MATTERMOST_ADMIN_PASSWORD"])


def people_file() -> Path:
    return DIR / "people.json"


def make_people(conf: dict[str, str], bridge: str, log: Any = print) -> None:
    """Both people as Switch users and Mattermost users; each claims their own account."""
    from flipside.room import solo

    path = people_file()
    people: dict[str, dict[str, str]] = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    )
    for role in ROLES:
        people.setdefault(
            role, {"mm_user": f"{role}-person", "mm_password": "Aa1!" + secrets.token_urlsafe(18)}
        )
    _private_write(path, json.dumps(people))
    mma = mm_admin(conf)
    team = mma.call("GET", f"/teams/name/{TEAM}")
    adm = admin(conf)
    for role in ROLES:
        p = people[role]
        try:
            u = mma.call(
                "POST",
                "/users",
                {
                    "username": p["mm_user"],
                    "email": f"{p['mm_user']}@flipside.local",
                    "password": p["mm_password"],
                    "first_name": role.capitalize(),
                },
            )
        except MattermostError:
            u = mma.call("GET", f"/users/username/{p['mm_user']}")
        mma.call(
            "POST", f"/teams/{team['id']}/members", {"team_id": team["id"], "user_id": u["id"]}
        )
        h, uid, _ = solo.person(adm, BASE, role)
        mine = {i.get("external_username") for i in h.get("/gateway/auth/me/identities") or []}
        if p["mm_user"] not in mine:
            h.post(
                f"/gateway/collaborations/{bridge}/identities",
                {"external_user_id": u["id"], "username": p["mm_user"]},
            )
        log(f"{role}: Switch user {uid}, Mattermost account {p['mm_user']} claimed in Switch")


def env() -> None:
    """Point the solo machinery at the demo server, its admin config and its users."""
    os.environ["SWITCH_BASE"] = BASE
    os.environ["FLIP_SWITCH_ENV"] = str(DIR / "stack.conf")
    os.environ["FLIP_USERS_FILE"] = str(DIR / "users.json")


def up() -> int:
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        raise DemoError("Docker is not running; start Docker Desktop (or the daemon) first")
    fetch_compose(DIR / "compose.yml")
    write_conf(DIR / "stack.conf")
    print(f"Switch {SWITCH_VERSION} (compose {COMPOSE_BLOB[:19]}...) with Mattermost: starting")
    compose("up", "-d", "--quiet-pull")
    conf = _read_conf(DIR / "stack.conf")
    bridge = wait_ready(conf)
    env()
    make_people(conf, bridge)
    print(f"ready: Switch {BASE}, Mattermost {MM_BASE} (team {TEAM}); next: flip demo run")
    return 0


def channels(live: Any) -> dict[str, str]:
    """Each room's Mattermost channel id, read by the person who created the room: a bridged
    room is private to its creator, so the other person may not read it (spike S5)."""
    c = live.cast
    owner = {c.shared: live.reviewer_h, c.private: live.author_h}
    return {r: str(h.get(f"/gateway/rooms/{r}")["external_channel_id"]) for r, h in owner.items()}


def people_for(conf: dict[str, str]) -> Any:
    """The ``people`` factory for ``run_switch``: both people act in Mattermost."""
    from flipside.room.solo import Live

    creds = json.loads(people_file().read_text(encoding="utf-8"))

    def build(live: Live, log: Log) -> Humans:
        c = live.cast
        mm = {r: MM(MM_BASE).login(creds[r]["mm_user"], creds[r]["mm_password"]) for r in ROLES}
        chans = channels(live)
        ids = {"author": c.a_agent.split(":", 1)[1], "reviewer": c.r_agent.split(":", 1)[1]}
        gateway = {"author": live.author_h, "reviewer": live.reviewer_h}
        log(f"Mattermost channels: shared {chans[c.shared]}, private {chans[c.private]}")
        return MattermostHumans(mm, chans, gateway, ids, c.private, log)

    return build


def run(case: Path, restarts: bool, press: bool, pace: float) -> int:
    if not (DIR / "stack.conf").exists():
        raise DemoError("no demo stack; run `flip demo up` first")
    env()
    conf = _read_conf(DIR / "stack.conf")
    wait_ready(conf, timeout=60)
    from flipside.room import solo

    people = None if press else people_for(conf)
    ok, _ = solo.run_case(
        case, restarts, "mattermost", press, pace, people=people, prefix="demo-mattermost"
    )
    print(f"watch it: {MM_BASE}, team {TEAM}; `flip demo logins` prints the two logins")
    return 0 if ok else 1


def logins() -> int:
    creds = json.loads(people_file().read_text(encoding="utf-8"))
    print(f"Mattermost {MM_BASE}, team {TEAM}")
    for role in ROLES:
        print(f"  {role}: {creds[role]['mm_user']} / {creds[role]['mm_password']}")
    return 0


def down() -> int:
    if (DIR / "compose.yml").exists() and (DIR / "stack.conf").exists():
        compose("down", "-v", "--remove-orphans", check=False)
    for name in ("stack.conf", "people.json", "users.json", "compose.yml"):
        (DIR / name).unlink(missing_ok=True)
    print("demo stack removed (containers, volumes, local config and users)")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="flip demo", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("up", help="start Switch and Mattermost in Docker; create the people")
    r = sub.add_parser("run", help="play a case with both people in Mattermost")
    r.add_argument("--case", default=str(DEFAULT_CASE))
    r.add_argument("--no-restart", action="store_true", help="skip the agent restart test")
    r.add_argument(
        "--press",
        action="store_true",
        help="leave the author's cards for you to press in Mattermost (log in as the author)",
    )
    r.add_argument("--pace", type=float, default=1.0, help="seconds between the people's turns")
    sub.add_parser("logins", help="print the two Mattermost logins")
    sub.add_parser("down", help="remove the demo stack and its local files")
    a = p.parse_args(argv)
    try:
        if a.cmd == "up":
            return up()
        if a.cmd == "run":
            return run(Path(a.case), not a.no_restart, a.press, a.pace)
        if a.cmd == "logins":
            return logins()
        return down()
    except (DemoError, MattermostError, SwitchError) as e:
        print(f"flip demo: {e}", file=sys.stderr)
        return 1
