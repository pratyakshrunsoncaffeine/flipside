"""``flip seal | prove | verify`` as a user runs them, in subprocesses."""

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.seal.conftest import PR, run

ROOT = Path(__file__).resolve().parents[2]


def flip(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "flipside.cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_seal_prove_verify_end_to_end(pr: PR, tmp_path: Path) -> None:
    s = flip("seal", "--base", "main", "--session", str(pr.session), cwd=pr.repo)
    assert s.returncode == 0, s.stderr
    root = s.stdout.split("root=")[1].split()[0]
    commit = s.stdout.split("commit ")[1].split()[0]
    manifest = s.stdout.split("manifest ")[-1].strip()
    assert run(pr.repo, "rev-parse", "HEAD").strip() == commit

    man = json.loads(Path(manifest).read_text())
    i = next(e["i"] for e in man if "auth/session.py" in e["files"] and e["role"] == "assistant")
    p = flip("prove", "--root", root, "--leaf", str(i), cwd=pr.repo)
    assert p.returncode == 0, p.stderr
    disc = tmp_path / "q1.json"
    disc.write_text(p.stdout)

    v = flip("verify", "--commit", commit, "--manifest", manifest, str(disc), cwd=pr.repo)
    assert v.returncode == 0, v.stdout + v.stderr
    assert v.stdout.startswith(f"OK leaf {i} (session 0, step ")

    d = json.loads(p.stdout)
    d["leaf"]["text"] = d["leaf"]["text"].replace("86400", "3600")
    disc.write_text(json.dumps(d))
    v = flip("verify", "--commit", commit, "--manifest", manifest, str(disc), cwd=pr.repo)
    assert v.returncode == 2 and v.stdout.startswith("PROOF_FAIL")

    v = flip(
        "verify",
        "--commit",
        commit,
        "--manifest",
        str(tmp_path / "missing.json"),
        str(disc),
        cwd=pr.repo,
    )
    assert v.returncode == 1


def test_prove_refuses_secret_leaf(pr: PR) -> None:
    pr.builder.user("export AWS_KEY=AKIA" + "ABCDEFGHIJKLMNOP")
    pr.builder.write(pr.session)
    s = flip("seal", "--base", "main", "--session", str(pr.session), "--no-commit", cwd=pr.repo)
    assert s.returncode == 0, s.stderr
    root = s.stdout.split("root=")[1].split()[0]
    n = int(s.stdout.split("n=")[1].split()[0])
    p = flip("prove", "--root", root, "--leaf", str(n - 1), "--commit", "a" * 40, cwd=pr.repo)
    assert p.returncode == 2
    assert "SECRET_SCAN" in p.stderr and "AKIA" not in p.stderr + p.stdout


def test_prove_session_changed_exit_2(pr: PR) -> None:
    s = flip("seal", "--base", "main", "--session", str(pr.session), cwd=pr.repo)
    root = s.stdout.split("root=")[1].split()[0]
    pr.session.write_text(pr.session.read_text().replace("CSV", "XLS", 1))
    p = flip("prove", "--root", root, "--leaf", "0", cwd=pr.repo)
    assert p.returncode == 2 and "SESSION_CHANGED" in p.stderr


def test_usage_errors_exit_1(pr: PR) -> None:
    assert flip("verify", cwd=pr.repo).returncode == 1
    assert flip("prove", "--root", "0" * 64, "--leaf", "0", cwd=pr.repo).returncode == 1
    assert flip("seal", "--base", "nope", "--session", str(pr.session), cwd=pr.repo).returncode == 1


def test_seal_default_session_from_claude_projects(pr: PR) -> None:
    from flipside.seal.seal import project_dir_name

    real = Path(run(pr.repo, "rev-parse", "--show-toplevel").strip())
    proj = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / project_dir_name(real)
    proj.mkdir(parents=True)
    (proj / "s.jsonl").write_bytes(pr.session.read_bytes())
    s = flip("seal", "--base", "main", "--no-commit", cwd=pr.repo)
    assert s.returncode == 0, s.stderr
    assert s.stdout.startswith("sealed s.jsonl")


def test_every_room_command_dispatches(tmp_path: Path) -> None:
    for cmd, prog in (("solo", "flip solo"), ("replay", "flip replay"), ("agent", "flip agent")):
        r = flip(cmd, "--help", cwd=tmp_path)
        assert r.returncode == 0 and f"usage: {prog}" in r.stdout, (cmd, r.stderr)
