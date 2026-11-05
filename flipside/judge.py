"""flip judge: check every README claim from a fresh clone, offline, in under a minute.

Each check runs the same public command a judge would type, and states the claim it backs,
the command, what it expects and what it got. Tamper checks build their inputs fresh from
the shipped example, so a judge sees refusals of files nobody prepared in advance.

Without --live: no network, no Docker, no Switch server. Never a model: standard library only.
With --live it also starts pinned Switch 0.31.0 and Mattermost in Docker, plays the review
with both people, and runs K5 (who Switch admits), checking the logs written by that run.
Exit 0 when every check passes, 2 when one fails. Writes evidence/judge-<time>.json and .log.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"
PY = [sys.executable, "-m", "flipside.cli"]


@dataclass
class Check:
    id: str
    claim: str
    command: str
    expect: str
    got: str = ""
    ok: bool = False
    code: list[str] = field(default_factory=list)


def _run(args: list[str], timeout: int = 300) -> tuple[int, str]:
    p = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return p.returncode, (p.stdout + p.stderr).strip()


def _show(args: list[str]) -> str:
    """The command as a judge would type it from the repo root."""
    parts = ["uv", "run", "flip", *args[len(PY) :]] if args[: len(PY)] == PY else args
    return " ".join(shlex.quote(str(a)) for a in parts).replace(str(ROOT) + "/", "")


def _verify_args(disclosure: Path, manifest: Path) -> list[str]:
    commit = (EX / "commit.txt").read_text(encoding="utf-8").strip()
    return [
        *PY,
        "verify",
        "--bundle",
        str(EX / "seal.bundle"),
        "--commit",
        commit,
        "--manifest",
        str(manifest),
        str(disclosure),
    ]


def verify_check(
    cid: str, claim: str, want: str, tamper: Callable[[dict[str, Any]], str] | None, tmp: Path
) -> Check:
    """Verify the shipped disclosure, or a copy changed by ``tamper``; expect verdict ``want``."""
    d = json.loads((EX / "q2-ok.json").read_text(encoding="utf-8"))
    manifest = EX / "manifest.json"
    how = "shipped disclosure"
    if tamper is not None:
        how = tamper(d)
        if how.startswith("manifest:"):
            manifest = tmp / f"{cid}-manifest.json"
            raw = (EX / "manifest.json").read_bytes()
            manifest.write_bytes(raw.replace(b'"role"', b'"Role"', 1))
            how = how.removeprefix("manifest:")
    path = tmp / f"{cid}.json"
    path.write_text(json.dumps(d), encoding="utf-8", newline="\n")
    args = _verify_args(path, manifest)
    rc, out = _run(args)
    first = out.splitlines()[0] if out else ""
    want_rc = 0 if want == "OK" else 2
    ok = rc == want_rc and first.startswith(want)
    return Check(
        cid,
        claim,
        f"{_show(args)}  # {how}",
        f"exit {want_rc}, {want}",
        f"exit {rc}, {first}",
        ok,
        ["flipside/seal/verify.py", "flipside/seal/merkle.py"],
    )


def _edit_word(d: dict[str, Any]) -> str:
    text = d["leaf"]["text"]
    d["leaf"]["text"] = text.replace("86400", "864000", 1) if "86400" in text else text + "."
    return "leaf text: one word edited"


def _other_salt(d: dict[str, Any]) -> str:
    d["salt"] = "0" * 64
    return "salt replaced"


def _other_index(d: dict[str, Any]) -> str:
    d["i"] = (d["i"] + 1) % d["n"]
    return "same text claimed as another step"


def _short_proof(d: dict[str, Any]) -> str:
    d["proof"] = d["proof"][:-1]
    return "one proof hash dropped"


def _other_commit(d: dict[str, Any]) -> str:
    d["commit"] = "f" * 40
    return "disclosure names a different commit"


def _manifest_edit(d: dict[str, Any]) -> str:
    return "manifest:public manifest edited by one byte"


def summary_line(out: str) -> dict[str, Any]:
    for line in out.splitlines():
        if "--- summary " in line:
            parsed: dict[str, Any] = json.loads(line.split("--- summary ", 1)[1])
            return parsed
    return {}


def review_check() -> Check:
    args = [*PY, "replay", "--offline", "--no-evidence"]
    rc, out = _run(args)
    s = summary_line(out)
    want = {
        "card_403": 1,
        "dropped_requests": 1,
        "switch_refusals": 1,
        "verdicts": {"OK": 1, "PROOF_FAIL": 1},
    }
    got = {k: s.get(k) for k in want}
    cov = [c for c in s.get("coverage", []) if "not disclosed" in c]
    ok = rc == 0 and "RESULT PASS" in out and got == want and bool(cov)
    return Check(
        "J8",
        "The whole review runs: question, own-words answer, one approved step, four refusals, "
        "a brief that says what was not shown",
        _show(args),
        "RESULT PASS; card_403 1, dropped_requests 1, switch_refusals 1, OK 1, PROOF_FAIL 1; "
        "coverage names the steps not disclosed",
        f"exit {rc}; {json.dumps(got, sort_keys=True)}; coverage: {'; '.join(cov) or 'none'}",
        ok,
        ["flipside/room/replay.py", "flipside/room/agents.py", "flipside/room/rules.py"],
    )


def fixtures_check() -> Check:
    args = [*PY, "replay", "--fixtures", "--out", str(ROOT / ".flip-judge" / "fixtures.md")]
    rc, out = _run(args)
    m = re.search(r"(\d+)/(\d+) match", out)
    ok = rc == 0 and m is not None and m.group(1) == m.group(2)
    return Check(
        "J9",
        "Questions come from fixed rules: 9 labelled cases, 2 of them adversarial, "
        "give the expected questions and verdicts",
        _show(args),
        "9/9 match",
        m.group(0) if m else f"exit {rc}",
        ok,
        ["flipside/room/rules.py", "fixtures/"],
    )


def _tracked(pattern: str) -> list[Path]:
    """Committed evidence files matching ``pattern``: what every clone of the repo holds."""
    p = subprocess.run(
        ["git", "ls-files", "--", f"evidence/{pattern}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return sorted(ROOT / line for line in p.stdout.split())


def _logs(pattern: str, since: float | None) -> list[Path]:
    """Without ``since``: committed logs only, so a judge can open the file the check read.
    With ``since``: logs this run wrote, oldest first."""
    if since is None:
        return _tracked(pattern)
    logs = sorted((ROOT / "evidence").glob(pattern))
    return [p for p in logs if p.stat().st_mtime >= since]


def live_evidence_check(since: float | None = None) -> Check:
    """J10 reads the newest committed real-Switch log, or with ``since`` the one written now."""
    logs = _logs("demo-mattermost-*.log", since)
    if not logs:
        return Check(
            "J10", "real Switch run", "", "a demo log", "no new demo-mattermost log", False
        )
    text = logs[-1].read_text(encoding="utf-8", errors="replace")
    need = [
        "four refusals live: yes",
        "agent step errors: 0",
        "RESULT PASS csv-export (switch",
        "You may not address this agent, so you may not answer it.",
    ]
    missing = [n for n in need if n not in text]
    ids = len(set(re.findall(r"\bsw_[0-9a-f]{32}\b", text)))
    return Check(
        "J10",
        "The same review "
        + ("ran now" if since is not None else "ran (recorded)")
        + " on real Switch 0.31.0 and Mattermost, both people on their own accounts"
        + ("" if since is not None else " (re-run live: `make judge-live`, needs Docker)"),
        f"read {logs[-1].relative_to(ROOT)}",
        "RESULT PASS on switch, four refusals live, no step errors, Switch message ids",
        f"{'all lines present' if not missing else 'missing: ' + '; '.join(missing)}; "
        f"{ids} Switch message ids",
        not missing and ids > 0,
        ["flipside/room/demo.py", "flipside/room/switch_client.py", ".github/workflows/"],
    )


def admission_check(since: float) -> Check:
    """J12, live only: Switch decides who may address author-agent and answer its card."""
    args = [sys.executable, "k5.py"]
    p = subprocess.run(
        args,
        cwd=ROOT / "killtests",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    logs = _logs("k5-*.log", since)
    text = logs[-1].read_text(encoding="utf-8", errors="replace") if logs else p.stdout
    m = re.search(r"K5 (\d+)/(\d+) passed", text)
    passes = re.findall(r"PASS (K5\.[a-z])", text)
    return Check(
        "J12",
        "Switch, not Flipside, decides who is the author: only the author's claimed Mattermost "
        "account may address author-agent or answer its approval card",
        "cd killtests && python3 k5.py",
        "K5 n/n passed (claimed author admitted; reviewer and unclaimed stranger refused)",
        f"exit {p.returncode}; {m.group(0) if m else 'no K5 result'}; {', '.join(passes)}",
        p.returncode == 0 and m is not None and m.group(1) == m.group(2),
        ["killtests/k5.py", "flipside/room/setup.py", "flipside/room/mattermost.py"],
    )


def live_run() -> tuple[float, Check]:
    """Start pinned Switch and Mattermost in Docker and play the case with both people."""
    since = time.time()
    for step in (["demo", "up"], ["demo", "run"]):
        rc, out = _run([*PY, *step], timeout=1200)
        if rc != 0:
            tail = " | ".join(out.splitlines()[-3:])
            return since, Check(
                "J0",
                "Docker demo starts",
                _show([*PY, *step]),
                "exit 0",
                f"exit {rc}: {tail}",
                False,
            )
    return since, Check(
        "J0",
        "Pinned Switch 0.31.0 and Mattermost start in Docker; the case plays with both people",
        "uv run flip demo up && uv run flip demo run",
        "exit 0",
        "exit 0",
        True,
        ["flipside/room/demo.py"],
    )


MODEL_SDKS = re.compile(
    r"^\s*(import|from)\s+(anthropic|openai|google\.generativeai|mistralai|cohere|ollama|"
    r"litellm|langchain)\b",
    re.M,
)


def deterministic_check() -> Check:
    hits = [
        str(p.relative_to(ROOT))
        for p in sorted((ROOT / "flipside").rglob("*.py"))
        if MODEL_SDKS.search(p.read_text(encoding="utf-8"))
    ]
    deps = re.search(
        r"^dependencies\s*=\s*(\[.*?\])",
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        re.S | re.M,
    )
    no_deps = deps is not None and deps.group(1).replace(" ", "") == "[]"
    return Check(
        "J11",
        "No model decides anything: questions, verdicts and coverage are standard-library Python",
        "scan flipside/**/*.py for model SDK imports; read pyproject.toml dependencies",
        "no model SDK import; dependencies = []",
        f"{'no model SDK import' if not hits else 'imports in ' + ', '.join(hits)}; "
        f"dependencies {'= []' if no_deps else 'not empty'}",
        not hits and no_deps,
        ["flipside/", "pyproject.toml"],
    )


def run_all(live: bool = False) -> list[Check]:
    # Tamper inputs stay in .flip-judge/ (git-ignored) so every printed command can be re-run.
    tmp = ROOT / ".flip-judge"
    tmp.mkdir(exist_ok=True)
    seal = [
        ("J1", "A disclosed step proves itself against the sealed root", "OK", None),
        ("J2", "Editing one word of a disclosed step is caught", "PROOF_FAIL", _edit_word),
        ("J3", "A step cannot be re-salted to fit", "PROOF_FAIL", _other_salt),
        ("J4", "A step cannot pass as a different step", "MANIFEST_MISMATCH", _other_index),
        ("J5", "A truncated proof is refused", "BAD_SIZE", _short_proof),
        (
            "J6",
            "A proof counts only for the commit the question named",
            "WRONG_COMMIT",
            _other_commit,
        ),
        ("J7", "The public manifest cannot change after sealing", "MANIFEST_HASH", _manifest_edit),
    ]
    checks = [verify_check(cid, claim, want, t, tmp) for cid, claim, want, t in seal]
    checks += [review_check(), fixtures_check()]
    if not live:
        return [*checks, live_evidence_check(), deterministic_check()]
    since, started = live_run()
    if not started.ok:
        return [*checks, started, deterministic_check()]
    return [
        *checks,
        started,
        live_evidence_check(since),
        admission_check(since),
        deterministic_check(),
    ]


def render(checks: list[Check], secs: float) -> str:
    lines = []
    for c in checks:
        lines.append(f"{'PASS' if c.ok else 'FAIL'}  {c.id:<4} {c.claim}")
        lines.append(f"        run:    {c.command}")
        lines.append(f"        expect: {c.expect}")
        lines.append(f"        got:    {c.got}")
        if c.code:
            lines.append(f"        code:   {', '.join(c.code)}")
    passed = sum(c.ok for c in checks)
    verdict = "PASS" if passed == len(checks) else "FAIL"
    lines.append(f"RESULT {verdict} {passed}/{len(checks)} checks in {secs:.1f} s")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="flip judge", description=(__doc__ or "").splitlines()[0])
    p.add_argument("--no-evidence", action="store_true", help="do not write evidence/judge-*")
    p.add_argument(
        "--live", action="store_true", help="also run the review on real Switch in Docker"
    )
    a = p.parse_args(argv)
    t0 = time.monotonic()
    checks = run_all(a.live)
    secs = time.monotonic() - t0
    text = render(checks, secs)
    print(text)
    if not a.no_evidence:
        stamp = time.strftime("%Y%m%dT%H%M%S")
        out = ROOT / "evidence" / f"judge-{stamp}"
        out.with_suffix(".log").write_text(text + "\n", encoding="utf-8", newline="\n")
        record = {
            "local_time": stamp,
            "live": a.live,
            "seconds": round(secs, 1),
            "checks": [asdict(c) for c in checks],
        }
        out.with_suffix(".json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"evidence {out.relative_to(ROOT)}.log and .json")
    return 0 if all(c.ok for c in checks) else 2


if __name__ == "__main__":
    sys.exit(main())
