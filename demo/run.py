"""Run the synthetic offline demo through the public CLI, without a shell or Switch."""

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Replay synthetic cases and return failure if the CLI or proof checks disagree."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="replay all nine synthetic cases")
    parser.add_argument("--log", type=Path, help="save the actual UTF-8 command output here")
    args = parser.parse_args()
    lines = [
        "Synthetic offline demo; FakeSwitch enforces the simulated room policies.",
        "This run does not demonstrate a live Switch server or process restarts.",
        "Started "
        + dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat()
        + " IST",
    ]
    failures = 0
    cases = ROOT / "fixtures" / "cases"
    selected = (
        sorted(p for p in cases.iterdir() if p.is_dir()) if args.all else [cases / "csv-export"]
    )
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    def run(label: str, argv: list[str], expected: int = 0, prefix: str | None = None) -> None:
        nonlocal failures
        lines.append(f"--- {label}")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "flipside.cli", *argv],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures += 1
            lines.append(f"FAIL {label}: {exc}")
            return
        lines.extend([result.stdout.rstrip(), result.stderr.rstrip()])
        ok = result.returncode == expected and (prefix is None or result.stdout.startswith(prefix))
        failures += not ok
        lines.append(
            f"{'PASS' if ok else 'FAIL'} {label}: exit {result.returncode}, expected {expected}"
        )
        if prefix is not None and not result.stdout.startswith(prefix):
            lines.append(f"FAIL {label}: expected output beginning {prefix!r}")

    if not selected:
        lines.append("FAIL: no fixture cases found")
        failures += 1
    for case in selected:
        run(case.name, ["replay", "--offline", "--case", str(case), "--no-evidence"])
    commit = (ROOT / "examples" / "commit.txt").read_text().strip()
    verify = [
        "verify",
        "--bundle",
        str(ROOT / "examples" / "seal.bundle"),
        "--commit",
        commit,
        "--manifest",
        str(ROOT / "examples" / "manifest.json"),
    ]
    run("G8 original quote", [*verify, str(ROOT / "examples" / "q2-ok.json")], prefix="OK ")
    run(
        "G8 forged quote",
        [*verify, str(ROOT / "examples" / "q2-forged.json")],
        expected=2,
        prefix="PROOF_FAIL ",
    )
    lines.append(f"RESULT {'FAIL' if failures else 'PASS'}: {failures} failed commands")
    output = "\n".join(line for line in lines if line) + "\n"
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_text(output, encoding="utf-8", newline="")
    print(output, end="")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
