"""``flip``: seal | prove | verify (docs/seal/SPEC.md), and solo | replay (room lane).

Exit codes: 0 OK, 2 refusal (a verify code, SESSION_CHANGED, SECRET_SCAN), 1 usage or I/O.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from flipside.seal.canon import canon
from flipside.seal.git import GitError
from flipside.seal.prove import ProveError, disclosure, leaf_secret_hits, rebuild
from flipside.seal.seal import SealError, latest_session, load_key, seal
from flipside.seal.verify import EXIT_OK, EXIT_REFUSED, EXIT_USAGE, verify


def _err(msg: str) -> None:
    print(f"flip: {msg}", file=sys.stderr)


def cmd_seal(a: argparse.Namespace) -> int:
    repo = Path(a.repo)
    try:
        session = Path(a.session) if a.session else latest_session(repo.resolve())
        key = load_key(Path(a.key)) if a.key else None
        res = seal(repo, session, a.base, key=key, commit=not a.no_commit, amend=a.amend)
    except (SealError, GitError, OSError) as e:
        _err(str(e))
        return EXIT_USAGE
    t = res.sealed.trailer
    print(f"sealed {session.name}: n={t.n} root={t.root} manifest={t.manifest}")
    print(f"commit {res.commit}" if res.commit else "commit skipped (--no-commit)")
    print(f"manifest {res.manifest_path}")
    return EXIT_OK


def cmd_prove(a: argparse.Namespace) -> int:
    try:
        rb = rebuild(Path(a.repo), a.root)
        if a.leaf < 0 or a.leaf >= rb.sealed.n:
            raise ProveError("BAD_LEAF", f"leaf {a.leaf} is outside 0..{rb.sealed.n - 1}")
        hits = leaf_secret_hits(rb, a.leaf)
        if hits:
            kinds = ", ".join(sorted({h.kind for h in hits}))
            _err(f"SECRET_SCAN: leaf {a.leaf} looks like it holds a secret ({kinds}); withheld")
            return EXIT_REFUSED
        d = disclosure(rb, a.leaf, a.commit)
    except ProveError as e:
        _err(str(e))
        return EXIT_REFUSED if e.code == "SESSION_CHANGED" else EXIT_USAGE
    except (SealError, GitError, OSError) as e:
        _err(str(e))
        return EXIT_USAGE
    out = canon(d) + b"\n"
    if a.out:
        Path(a.out).write_bytes(out)
    else:
        sys.stdout.buffer.write(out)
    return EXIT_OK


def _verify_in(repo: Path, a: argparse.Namespace) -> int:
    try:
        d = json.loads(Path(a.disclosure).read_text(encoding="utf-8"))
        manifest = Path(a.manifest).read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        _err(f"cannot read input: {e}")
        return EXIT_USAGE
    v = verify(repo, d, manifest, commit=a.commit, head=a.head)
    print(v.message())
    return EXIT_OK if v.ok else EXIT_REFUSED


def cmd_verify(a: argparse.Namespace) -> int:
    if not a.bundle:
        return _verify_in(Path(a.repo), a)
    with tempfile.TemporaryDirectory(prefix="flip-verify-") as tmp:
        clone = Path(tmp) / "repo.git"
        p = subprocess.run(
            ["git", "clone", "-q", "--bare", a.bundle, str(clone)],
            capture_output=True,
            text=True,
            check=False,
        )
        if p.returncode != 0:
            _err(f"cannot open bundle {a.bundle}: {p.stderr.strip()}")
            return EXIT_USAGE
        return _verify_in(clone, a)


ROOM_COMMANDS = {
    "solo": ("flipside.room.solo", "M3: two owners on the local Switch server"),
    "replay": ("flipside.room.replay", "M2/M4: replay the CSV-export scenario"),
    "agent": ("flipside.room.daemon", "run author-agent or reviewer-agent as a process"),
    "setup": ("flipside.room.setup", "connect a real PR's two owners and agents on Switch"),
    "chat": ("flipside.room.chat", "post, read and answer approval cards without a chat app"),
}


def cmd_room(a: argparse.Namespace) -> int:
    return run_room(a.command, list(a.args))


def run_room(command: str, args: list[str]) -> int:
    """Hand off to the room lane: ``<module>.main(argv) -> int``. Imported lazily, so the
    seal commands never import flipside.room."""
    import importlib

    module, _ = ROOM_COMMANDS[command]
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as e:
        if e.name is not None and module.startswith(e.name):
            _err(f"{command}: {module} is not built yet (room lane, docs/BUILD.md M2 to M4)")
            return EXIT_USAGE
        raise
    code: int = mod.main(args)
    return code


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on bad usage; flip keeps 2 for refusals and uses 1."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        _err(message)
        sys.exit(EXIT_USAGE)


def parser() -> argparse.ArgumentParser:
    p = _Parser(prog="flip", description=(__doc__ or "").splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("seal", help="seal the agent session and add the seal commit")
    s.add_argument("--base", default="origin/main", help="PR base ref (default origin/main)")
    s.add_argument("--session", help="session JSONL (default: newest for this repo)")
    s.add_argument("--key", help="reuse a 32-byte key file instead of a fresh one")
    s.add_argument("--amend", action="store_true", help="add the trailer to HEAD (unpushed)")
    s.add_argument("--no-commit", action="store_true", help="write state, skip the commit")
    s.add_argument("--repo", default=".")
    s.set_defaults(func=cmd_seal)

    pr = sub.add_parser("prove", help="disclose one leaf with its inclusion proof")
    pr.add_argument("--root", required=True)
    pr.add_argument("--leaf", required=True, type=int)
    pr.add_argument("--commit", help="seal commit (default: from local state)")
    pr.add_argument("--out", help="write the disclosure here instead of stdout")
    pr.add_argument("--repo", default=".")
    pr.set_defaults(func=cmd_prove)

    v = sub.add_parser("verify", help="run the seven checks on a disclosure")
    v.add_argument("--commit", required=True, help="the seal commit the question named")
    v.add_argument("--head", default="HEAD", help="PR head (default HEAD)")
    v.add_argument("--manifest", required=True)
    v.add_argument("--bundle", help="verify inside this git bundle instead of --repo")
    v.add_argument("--repo", default=".")
    v.add_argument("disclosure")
    v.set_defaults(func=cmd_verify)

    for name, (_, help_text) in ROOM_COMMANDS.items():
        r = sub.add_parser(name, help=help_text, add_help=False)
        r.add_argument("args", nargs=argparse.REMAINDER)
        r.set_defaults(func=cmd_room)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ROOM_COMMANDS:
        return run_room(args[0], args[1:])
    a = parser().parse_args(args)
    code: int = a.func(a)
    return code


if __name__ == "__main__":
    sys.exit(main())
