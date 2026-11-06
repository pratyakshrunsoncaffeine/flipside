"""Check rendered mobile layouts with the repository's Chromium driver."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TypedDict

import pytest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tools" / "mobile_check.mjs"
VIEWPORTS = {(320, 640), (360, 780), (390, 844), (414, 896), (768, 1024), (844, 390)}


class Issue(TypedDict):
    area: str
    kind: str
    selector: str
    message: str


class Case(TypedDict):
    page: str
    width: int
    height: int
    issues: list[Issue]


class KnownLayoutFailure(AssertionError):
    """A failure recorded before the responsive changes."""


# Exact failures from the checked-in baseline. Remove a row when its issue is fixed.
KNOWN = {
    (
        "index.html",
        "footer",
        "tap",
        'a[href="https://github.com/pratyakshrunsoncaffeine/gateplus"]',
    ),
    (
        "index.html",
        "footer",
        "tap",
        'a[href="https://github.com/pratyakshrunsoncaffeine/gateplus/blob/main/VERIFICATION.md"]',
    ),
    ("index.html", "footer", "tap", 'a[href="https://github.com/sandbox-quantum/switch"]'),
    ("index.html", "footer", "tap", 'a[href="verify.html"]'),
    ("index.html", "nav", "tap", 'a.brand[href="#top"]'),
    ("index.html", "nav", "tap", 'a[href="#film"]'),
    ("index.html", "nav", "tap", 'a[href="#how"]'),
    ("index.html", "nav", "tap", 'a[href="#player"]'),
    ("index.html", "nav", "tap", 'a[href="#run"]'),
    ("index.html", "replay", "tap", 'button[aria-label="Chapter 1: seal"]'),
    ("index.html", "replay", "tap", 'button[aria-label="Chapter 2: question"]'),
    ("index.html", "replay", "tap", 'button[aria-label="Chapter 3: answer"]'),
    ("index.html", "replay", "tap", 'button[aria-label="Chapter 4: refuse"]'),
    ("index.html", "replay", "tap", 'button[aria-label="Chapter 5: approve"]'),
    ("index.html", "replay", "tap", 'button[aria-label="Chapter 6: proof"]'),
    ("index.html", "replay", "tap", 'button[aria-label="Chapter 7: forgery"]'),
    ("index.html", "replay", "tap", 'button[aria-label="Chapter 8: brief"]'),
    ("index.html", "replay", "text", "code.sw"),
    ("index.html", "replay", "text", "p#privempty"),
    ("index.html", "run", "overflow", "code.want"),
    ("index.html", "run", "text", "p.judgelink.rise"),
    ("index.html", "top", "tap", 'a.textlink[href="#film"]'),
    ("index.html", "top", "tap", "button#herobtn"),
    ("index.html", "top", "text", "li"),
    ("verify.html", "nav", "tap", 'a.back[href="index.html"]'),
    ("verify.html", "nav", "tap", 'a.brand[href="index.html"]'),
    ("verify.html", "page", "tap", "input#disclosure-file"),
    ("verify.html", "page", "tap", "input#manifest-file"),
    ("verify.html", "page", "text", "input#disclosure-file"),
    ("verify.html", "page", "text", "input#manifest-file"),
    ("verify.html", "page", "text", "p.hint"),
    ("verify.html", "page", "text", "textarea#disclosure"),
    ("verify.html", "page", "text", "textarea#manifest"),
    ("verify.html", "page", "text", "textarea#trailer"),
}


@pytest.fixture(scope="module")
def mobile_cases() -> list[Case]:
    required = os.environ.get("FLIP_REQUIRE_CHROME") == "1"
    if not required and os.environ.get("FLIP_MOBILE") != "1":
        pytest.skip("The reference platform is Ubuntu CI. Set FLIP_MOBILE=1 to opt in.")
    node = shutil.which("node")
    if node is None:
        if required:
            pytest.fail("Mobile checking requires Node 22 and Chrome.")
        pytest.skip("Mobile checking requires Node 22 and Chrome.")

    command = [node, str(DRIVER)]
    detected = subprocess.run(
        [*command, "--browser-path"], cwd=ROOT, capture_output=True, text=True, timeout=15
    )
    if detected.returncode == 1:
        if required:
            pytest.fail("Set CHROME or install Chrome on the required mobile checker runner.")
        pytest.skip("Chrome was not found. Set CHROME to its executable.")
    assert detected.returncode == 0, detected.stderr

    screenshot_dir = ROOT / "mobile-check-screenshots"
    screenshot_dir.mkdir(exist_ok=True)
    artifacts = Path(tempfile.mkdtemp(prefix="pytest-", dir=screenshot_dir))
    env = {
        **os.environ,
        "PYTHON": sys.executable,
        "MOBILE_ARTIFACTS": str(artifacts),
        "MOBILE_EVIDENCE_DIR": str(artifacts),
    }
    run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=420)
    assert run.returncode in (0, 1), run.stdout + run.stderr
    cases: list[Case] = json.loads((artifacts / "report.json").read_text(encoding="utf-8"))
    assert len(cases) == 12, run.stdout
    assert {(case["page"], case["width"], case["height"]) for case in cases} == {
        (page, width, height)
        for page in ("index.html", "verify.html")
        for width, height in VIEWPORTS
    }
    assert (run.returncode == 1) == any(case["issues"] for case in cases)
    return cases


def test_no_unexpected_mobile_failures(mobile_cases: list[Case]) -> None:
    unexpected = [
        f"{case['page']} {case['width']}x{case['height']} "
        f"[{issue['area']}/{issue['kind']}] {issue['selector']}: {issue['message']}"
        for case in mobile_cases
        for issue in case["issues"]
        if (case["page"], issue["area"], issue["kind"], issue["selector"]) not in KNOWN
    ]
    assert not unexpected, "\n".join(unexpected)


@pytest.mark.parametrize(
    ("page", "area", "kind", "selector"),
    [
        pytest.param(
            page,
            area,
            kind,
            selector,
            id=f"{page}-{area}-{kind}-{selector}",
            marks=pytest.mark.xfail(
                strict=True, raises=KnownLayoutFailure, reason="Recorded mobile baseline"
            ),
        )
        for page, area, kind, selector in sorted(KNOWN)
    ],
)
def test_known_mobile_failures(
    mobile_cases: list[Case], page: str, area: str, kind: str, selector: str
) -> None:
    failures = [
        f"{case['width']}x{case['height']} {issue['message']}"
        for case in mobile_cases
        for issue in case["issues"]
        if (case["page"], issue["area"], issue["kind"], issue["selector"])
        == (page, area, kind, selector)
    ]
    if failures:
        raise KnownLayoutFailure("\n".join(failures))
