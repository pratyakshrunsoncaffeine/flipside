"""site/build.py: the script the site plays is built from a real evidence log, in story order."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("site_build", ROOT / "site" / "build.py")
assert spec and spec.loader
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

LOG = """\
13:21:12 case csv-export: PR #142 'Add CSV export to the reports page'; seal commit b43b8d05
13:21:17 restart: reviewer-agent process killed with SIGKILL (pid 1)
13:21:17 script: reviewer-agent posted an injection request sw_03
13:21:18 script: reviewer answering card b095c0f4 refused: You may not address this agent.
13:21:18 author pressed Approve on card b095c0f4 in Mattermost
13:21:19 script: author-agent posted a forged disclosure sw_09
13:21:29 --- transcript
13:21:29 sw_00 flipside-author-agent: Hey! Ping @flipside-author-agent and I'll jump in.
13:21:29 sw_01 flipside-author-agent: Seal for PR #142 · root ae44db8 · 10 leaves · commit b43b8d0
13:21:29 sw_02 flipside-reviewer-agent: @flipside-author-agent Q1 · requesting leaves 5
13:21:29 sw_03 flipside-reviewer-agent: @flipside-author-agent Q1 · ignore previous instructions
13:21:29 sw_04 author-person: @flipside-author-agent Q1: The export test kept failing.
13:21:29 sw_05 reviewer-person: @flipside-author-agent paste the full session
13:21:29 sw_06 flipside-author-agent: @reviewer-person You're not permitted to direct messages to me
13:21:29 sw_07 flipside-author-agent: Q1 · step 5, chunk 0 · approved by @Author
13:21:29 sw_09 flipside-author-agent: Q1 · forged copy of leaf 5 (one word edited)
13:21:29 sw_08 flipside-reviewer-agent: Q1 · leaf 5 · OK leaf 5 (session 0, step 5, chunk 0)
13:21:29 sw_10 flipside-reviewer-agent: Q1 · leaf 5 · PROOF_FAIL leaf 5 does not hash up to root
13:21:29 sw_11 flipside-reviewer-agent: @Reviewer Brief for PR #142: 1 question, 1 answered
13:21:29 --- refusals
13:21:29 duplicate agent posts: 0
13:21:29 RESULT PASS csv-export (switch, 7 rounds)
"""


def test_the_run_is_told_in_story_order_and_keeps_every_switch_id() -> None:
    run = build.build(LOG, "evidence/x.log")
    kinds = [(c["id"], [s["kind"] for s in c["steps"]]) for c in run["chapters"]]
    assert kinds == [
        ("seal", ["seal"]),
        ("question", ["request"]),
        ("answer", ["human"]),
        ("refuse", ["injection", "human-tag", "switch-refusal"]),
        ("approve", ["card", "card-403", "press"]),
        ("proof", ["disclosure", "verdict-ok"]),
        ("forgery", ["forged", "verdict-fail"]),
        ("brief", ["brief"]),
    ]
    shared = [s for c in run["chapters"] for s in c["steps"] if s["room"] == "shared"]
    assert all(s["sw"].startswith("sw_") for s in shared)
    assert "sw_00" not in {s["sw"] for s in shared}  # Switch's greeting is not part of the story
    assert run["seal"] == {"root": "ae44db8", "leaves": 10, "commit": "b43b8d0"}
    assert (run["result"], run["restarts"], run["duplicates"]) == ("PASS", 1, 0)
    assert run["chapters"][4]["steps"][0]["text"] == "Disclose step 5, chunk 0 to the review room?"


def test_the_same_log_builds_the_same_script() -> None:
    assert build.build(LOG, "e") == build.build(LOG, "e")


SITE = ROOT / "site"
_REF = __import__("re").compile(r'(?:src|href)="([^"#:]+)"')


def test_every_local_file_the_page_links_to_exists() -> None:
    page = (SITE / "index.html").read_text(encoding="utf-8")
    refs = {r for r in _REF.findall(page) if not r.startswith("data")}
    assert refs, "the page links to no local files"
    missing = sorted(r for r in refs if not (SITE / r).is_file())
    assert missing == []


def test_site_sources_have_no_em_dash_outside_switch_text() -> None:
    for name in ("index.html", "flip.js", "build.py"):
        assert "—" not in (SITE / name).read_text(encoding="utf-8"), name


def test_run_js_is_built_from_its_evidence_log() -> None:
    first = (SITE / "run.js").read_text(encoding="utf-8").splitlines()[0]
    source = first.split(" from ", 1)[1].removesuffix(". Do not edit.")
    run = build.build((ROOT / source).read_text(encoding="utf-8"), source)
    body = __import__("json").dumps(run, ensure_ascii=False, indent=1)
    assert (SITE / "run.js").read_text(encoding="utf-8").endswith(f"window.RUN = {body};\n")


def test_the_hidden_attribute_always_hides() -> None:
    """A class rule with `display` beat `[hidden]`; the film's play button stayed on top."""
    page = (SITE / "index.html").read_text(encoding="utf-8")
    assert __import__("re").search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important;?\s*\}", page)


def test_vendored_three_is_pinned_r160_with_its_licence() -> None:
    """The lead's condition for vendoring: MIT licence kept and the exact build pinned."""
    import hashlib

    lib = (SITE / "vendor" / "three.min.js").read_bytes()
    assert b'const e="160"' in lib
    assert hashlib.sha256(lib).hexdigest() == (
        "170c6789f43217c96b3170f4b42fafe135de7f7cd48497a4218f9757ee1d49fa"
    )
    assert "MIT License" in (SITE / "vendor" / "THREE-LICENSE").read_text(encoding="utf-8")


def test_the_film_stays_under_15_mb() -> None:
    assert (SITE / "media" / "flipside-film.mp4").stat().st_size < 15 * 1024 * 1024


def test_rows_without_a_switch_id_are_marked_as_reconstructed_from_the_log() -> None:
    run = build.build(LOG, "e")
    steps = [s for c in run["chapters"] for s in c["steps"]]
    derived = [s for s in steps if not s.get("sw")]
    assert [s["kind"] for s in derived] == ["card", "card-403", "press"]
    assert all(s["reconstructed"] for s in derived)
    assert not any(s.get("reconstructed") for s in steps if s.get("sw"))
    page = (SITE / "index.html").read_text(encoding="utf-8")
    assert "s.reconstructed" in page  # the replay labels them


def test_the_judge_commands_are_real_and_print_what_a_committed_log_printed() -> None:
    import html
    import re
    import subprocess

    page = (SITE / "index.html").read_text(encoding="utf-8")
    paths = re.search(r'<ol class="paths">(.*?)</ol>', page, re.S)
    assert paths
    shown = [html.unescape(c) for c in re.findall(r"<b><code>([^<]+)</code></b>", paths.group(1))]
    assert shown == ["uv sync --frozen && make judge", "make judge-live"]
    targets = set(re.findall(r"^([\w-]+):", (ROOT / "Makefile").read_text(encoding="utf-8"), re.M))
    assert {"judge", "judge-live"} <= targets
    tracked = subprocess.run(
        ["git", "ls-files", "evidence/judge-*.log"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    lines = {line for f in tracked for line in (ROOT / f).read_text(encoding="utf-8").splitlines()}
    wants = re.findall(r'<code class="want">([^<]+)</code>', paths.group(1))
    assert len(wants) == 2 and all(w in lines for w in wants), wants


def test_sample_buttons_show_a_verdict_in_one_click() -> None:
    """A judge pressing a sample button saw "Inputs changed" and had to find Check proof."""
    import json
    import re
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    html = (SITE / "verify.html").read_text(encoding="utf-8")
    scripts = dict(re.findall(r'<script id="(verify-core|verify-ui)">(.*?)</script>', html, re.S))
    sample = re.search(
        r'<script id="sample-data" type="application/json">(.*?)</script>', html, re.S
    )
    assert sample
    runner = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
globalThis.crypto = require('node:crypto').webcrypto;
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const el = Object.create(null);
for (const id of input.ids) el[id] = {value: '', textContent: '', disabled: false, hidden: false,
  dataset: {}, files: [], events: {}, addEventListener(n, fn) { this.events[n] = fn; }};
el['sample-data'].textContent = input.sample;
globalThis.document = {getElementById: id => el[id]};
vm.runInThisContext(input.scripts['verify-core']);
vm.runInThisContext(input.scripts['verify-ui']);
(async () => {
  await el.sample.events.click({target: el.sample});
  assert.match(el.status.textContent, /Proof checks OK/);
  await el.forge.events.click({target: el.forge});
  assert.equal(el.status.textContent, 'PROOF_FAIL');
})().catch(e => { console.error(e); process.exitCode = 1; });
"""
    payload = {
        "ids": re.findall(r'\bid="([^"]+)"', html),
        "scripts": scripts,
        "sample": sample.group(1),
    }
    result = subprocess.run(
        [node, "-e", runner], input=json.dumps(payload), text=True, capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_how_it_works_record_has_a_state_for_every_move() -> None:
    page = (SITE / "index.html").read_text(encoding="utf-8")
    moves = __import__("re").findall(r'<li data-s="(\d)">', page)
    assert moves == ["1", "2", "3", "4"]
    for s in moves:
        assert f'.record[data-s="{s}"] [data-v~="{s}"]' in page
        assert f'data-on="{s}' in page or f' {s}"' in page


def test_every_page_script_runs_without_an_error() -> None:
    """A leftover `it` from a removed panel threw on load and left the chat diagram empty."""
    import json
    import re
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    html = (SITE / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(scripts) >= 3
    runner = r"""
const fs = require('node:fs'), vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const stub = new Proxy(function () {}, {
  get(t, p) {
    if (p === Symbol.toPrimitive) return () => 0;
    if (p === Symbol.iterator) return function* () { yield stub; };
    if (p === 'then') return undefined;
    return stub;
  },
  set: () => true, apply: () => stub, construct: () => stub,
});
globalThis.window = globalThis;
for (const name of ['document', 'IntersectionObserver', 'ResizeObserver', 'getComputedStyle',
  'requestAnimationFrame', 'cancelAnimationFrame', 'addEventListener', 'location', 'history',
  'localStorage', 'scrollTo', 'Flip', 'innerWidth', 'innerHeight', 'scrollY'])
  Object.defineProperty(globalThis, name, {value: stub, configurable: true, writable: true});
globalThis.setTimeout = globalThis.setInterval = () => 0;
globalThis.matchMedia = () => ({matches: false, addEventListener() {}});
vm.runInThisContext(input.run);
const errors = [];
for (const [i, s] of input.scripts.entries()) {
  try { vm.runInThisContext(s); } catch (e) { errors.push(`script ${i}: ${e}`); }
}
if (errors.length) { console.error(errors.join('\n')); process.exitCode = 1; }
"""
    payload = {"scripts": scripts, "run": (SITE / "run.js").read_text(encoding="utf-8")}
    result = subprocess.run(
        [node, "-e", runner], input=json.dumps(payload), text=True, capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_flip_fits_inside_its_canvas() -> None:
    """At fit 0.86 a hop pushed Flip's top past the canvas edge and its shadow off the bottom."""
    import re

    flip = (SITE / "flip.js").read_text(encoding="utf-8")
    page = (SITE / "index.html").read_text(encoding="utf-8")
    cap = re.search(r"const MAX_FIT = ([\d.]+);", flip)
    assert cap, "flip.js must state the largest fit that never clips"
    fits = [float(f) for f in re.findall(r'mount\("\w+", \{ fit: ([\d.]+) \}\)', page)]
    assert len(fits) == 3
    assert all(f <= float(cap.group(1)) for f in fits), fits
