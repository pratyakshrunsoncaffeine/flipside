"""The local page's actual WebCrypto code agrees with the public CLI.

Node 22+ runs the exact inline core, with no browser/npm package or test substitute.
Git checks are deliberately outside the page's claim; CLI comparison repos have a
valid, pinned seal commit. All added data is synthetic.
"""

import base64
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from flipside.seal.canon import canon
from flipside.seal.manifest import manifest_bytes
from flipside.seal.merkle import inclusion_proof, leaf_hash, mth

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "site" / "verify.html"
VECTORS = sorted((ROOT / "tests" / "vectors").glob("*.json"))
NODE_RUNNER = r"""
const fs = require('node:fs');
const vm = require('node:vm');
globalThis.crypto = require('node:crypto').webcrypto;
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
vm.runInThisContext(input.script, {filename: 'site/verify.html#verify-core'});
(async () => {
  const out = [];
  for (const c of input.cases) {
    const bytes = new Uint8Array(Buffer.from(c.manifest, 'base64'));
    const v = await FlipsideVerify.verify(c.disclosure, bytes, c.trailer);
    out.push(v.code);
  }
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exitCode = 1; });
"""


def node_executable() -> str:
    """Missing Node is fatal in CI and optional for local Python-only installs."""
    node = shutil.which("node")
    if node is None:
        if os.environ.get("FLIP_REQUIRE_NODE") == "1":
            pytest.fail("Browser parity is mandatory in CI: Node 22+ must be on PATH.")
        pytest.skip("Browser parity needs Node 22+; set FLIP_REQUIRE_NODE=1 to require it.")
    return node


def page_codes(cases: list[dict[str, str]]) -> list[str]:
    """Run the shipped verifier script with the platform's real WebCrypto."""
    node = node_executable()
    html = PAGE.read_text(encoding="utf-8")
    core = re.search(r'<script id="verify-core">(.*?)</script>', html, re.S)
    assert core, "Page must ship the core exercised by this parity gate"
    result = subprocess.run(
        [node, "-e", NODE_RUNNER],
        input=json.dumps({"script": core.group(1), "cases": cases}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
        timeout=60,
    )
    codes: list[str] = json.loads(result.stdout)
    return codes


def case(d: Any, manifest: bytes, trailer: str) -> dict[str, str]:
    return {
        "disclosure": json.dumps(d, ensure_ascii=False),
        "manifest": base64.b64encode(manifest).decode("ascii"),
        "trailer": trailer,
    }


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def seal_repo(repo: Path, trailer: str) -> str:
    """A synthetic local seal commit, independent of the developer's git identity."""
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(
        repo,
        "-c",
        "user.name=Browser parity fixture",
        "-c",
        "user.email=browser@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--allow-empty",
        "-qm",
        "Synthetic parity seal\n\n" + trailer,
    )
    return git(repo, "rev-parse", "HEAD")


def cli_code(c: dict[str, str], tmp: Path, *, commit: str, repo: Path | None = None) -> str:
    """Exercise flip verify as a real process, including its exit contract."""
    disclosure, manifest = tmp / "disclosure.json", tmp / "manifest.json"
    disclosure.write_text(c["disclosure"], encoding="utf-8", newline="")
    manifest.write_bytes(base64.b64decode(c["manifest"]))
    source = ["--repo", str(repo)] if repo else ["--bundle", str(ROOT / "examples/seal.bundle")]
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "flipside.cli",
            "verify",
            *source,
            "--commit",
            commit,
            "--manifest",
            str(manifest),
            str(disclosure),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    code = p.stdout.split()[0] if p.stdout else ""
    assert p.returncode == (0 if code == "OK" else 2), p.stdout + p.stderr
    return code


@pytest.mark.parametrize("vector", VECTORS, ids=lambda p: p.name)
def test_every_pinned_vector_matches_cli(vector: Path, tmp_path: Path) -> None:
    v = json.loads(vector.read_text(encoding="utf-8"))
    repo = tmp_path / "repo"
    commit = seal_repo(repo, v["trailer"])
    d = {**v["disclosure"], "commit": commit}
    c = case(d, v["manifest"].encode("utf-8"), v["trailer"])
    assert page_codes([c]) == [cli_code(c, tmp_path, commit=commit, repo=repo)] == ["OK"]


@pytest.mark.parametrize("name,expected", [("q2-ok.json", "OK"), ("q2-forged.json", "PROOF_FAIL")])
def test_g8_examples_match_cli(name: str, expected: str, tmp_path: Path) -> None:
    ex = ROOT / "examples"
    # Read the independent seal record from the committed git bundle, not the proof.
    clone = tmp_path / "bundle.git"
    subprocess.run(
        ["git", "clone", "--bare", "-q", str(ex / "seal.bundle"), str(clone)], check=True
    )
    commit = (ex / "commit.txt").read_text(encoding="utf-8").strip()
    trailer = next(
        line
        for line in git(clone, "show", "-s", "--format=%B", commit).splitlines()
        if line.startswith("Flipside-Seal:")
    )
    c = case(
        json.loads((ex / name).read_text(encoding="utf-8")),
        (ex / "manifest.json").read_bytes(),
        trailer,
    )
    assert page_codes([c]) == [cli_code(c, tmp_path, commit=commit)] == [expected]


def test_ordered_failures_match_cli(tmp_path: Path) -> None:
    v = json.loads(VECTORS[0].read_text(encoding="utf-8"))
    repo = tmp_path / "repo"
    commit = seal_repo(repo, v["trailer"])
    good = {**v["disclosure"], "commit": commit}
    manifest = v["manifest"].encode("utf-8")
    cases: list[dict[str, str]] = []
    expected: list[str] = []

    def add(d: Any, code: str, m: bytes = manifest) -> None:
        cases.append(case(d, m, v["trailer"]))
        expected.append(code)

    add(good, "OK")
    add({**good, "salt": good["salt"] + "\n"}, "OK")
    add({**good, "proof": [p + "\n" for p in good["proof"]]}, "OK")
    add({**good, "salt": good["salt"] + "\r\n"}, "BAD_DISCLOSURE")
    value: Any
    for key in good:
        d = copy.deepcopy(good)
        del d[key]
        add(d, "BAD_DISCLOSURE")
    for key, value in (
        ("v", True),
        ("v", 1.0),
        ("i", True),
        ("i", -1),
        ("n", 1.0),
        ("commit", "A" * 40),
        ("salt", "x" * 64),
        ("proof", ["not a hash"]),
    ):
        add({**good, key: value}, "BAD_DISCLOSURE", b"also bad manifest")
    for key, value in (
        ("text", 1),
        ("step", 1.0),
        ("tools", [1]),
        ("ok", 0),
        ("role", "system"),
        ("cmd", "unknown"),
        ("extra", "x"),
    ):
        d = copy.deepcopy(good)
        d["leaf"][key] = value
        add(d, "BAD_DISCLOSURE")
    add([], "BAD_DISCLOSURE")
    add({**good, "unrelated": {"x": 1.5}}, "OK")  # extra top-level keys are ignored
    add(good, "MANIFEST_HASH", manifest + b"\n")  # hash exact input bytes
    d = copy.deepcopy(good)
    d["leaf"]["step"] += 1
    d["n"] = 0  # metadata failure takes precedence over size
    add(d, "MANIFEST_MISMATCH")
    add({**good, "i": len(json.loads(manifest)) + 1}, "BAD_SIZE")
    add({**good, "n": 0}, "BAD_SIZE")
    add({**good, "n": good["n"] + 1}, "BAD_SIZE")
    add({**good, "proof": good["proof"][:-1]}, "BAD_SIZE")
    for key in ("text", "salt", "proof"):
        d = copy.deepcopy(good)
        if key == "text":
            d["leaf"]["text"] += " edited"
        elif key == "salt":
            d[key] = "00" * 32
        else:
            d[key][0] = "00" * 32
        add(d, "PROOF_FAIL")
    cli = [cli_code(c, tmp_path, commit=commit, repo=repo) for c in cases]
    assert page_codes(cases) == cli == expected


@pytest.mark.parametrize("bad_manifest", [b"[]", b"[{}]", b"\xff", b"not JSON"])
def test_matching_hash_cannot_hide_malformed_manifest(bad_manifest: bytes, tmp_path: Path) -> None:
    v = json.loads(VECTORS[0].read_text(encoding="utf-8"))
    trailer = re.sub(
        r"manifest=[0-9a-f]+", "manifest=" + hashlib.sha256(bad_manifest).hexdigest(), v["trailer"]
    )
    repo = tmp_path / "repo"
    commit = seal_repo(repo, trailer)
    c = case({**v["disclosure"], "commit": commit}, bad_manifest, trailer)
    assert page_codes([c]) == [cli_code(c, tmp_path, commit=commit, repo=repo)] == ["MANIFEST_HASH"]


def test_unicode_and_unbounded_integers_are_hashed_without_rounding(tmp_path: Path) -> None:
    v = json.loads(VECTORS[0].read_text(encoding="utf-8"))
    leaf = {**v["disclosure"]["leaf"], "step": 2**100, "text": "café e\u0301 雪 😀\n\t\u0000"}
    manifest = manifest_bytes([leaf])
    salt = "01" * 32
    root = leaf_hash(bytes.fromhex(salt), canon(leaf)).hex()
    trailer = f"Flipside-Seal: v1 root={root} n=1 manifest={hashlib.sha256(manifest).hexdigest()}"
    repo = tmp_path / "repo"
    commit = seal_repo(repo, trailer)
    d = {"v": 1, "commit": commit, "i": 0, "n": 1, "salt": salt, "leaf": leaf, "proof": []}
    c = case(d, manifest, trailer)
    assert page_codes([c]) == [cli_code(c, tmp_path, commit=commit, repo=repo)] == ["OK"]


def test_every_leaf_of_balanced_and_unbalanced_trees() -> None:
    """Independent Python-generated paths exercise both branches and the short tail."""
    v = json.loads(VECTORS[0].read_text(encoding="utf-8"))
    cases = []
    for n in (1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 32, 33):
        leaves = [
            {**v["disclosure"]["leaf"], "step": i, "text": f"Synthetic leaf {i}"} for i in range(n)
        ]
        manifest = manifest_bytes(leaves)
        salts = [hashlib.sha256(f"synthetic salt {i}".encode()).digest() for i in range(n)]
        hashes = [leaf_hash(salt, canon(leaf)) for salt, leaf in zip(salts, leaves, strict=True)]
        trailer = (
            f"v1 root={mth(hashes).hex()} n={n} manifest={hashlib.sha256(manifest).hexdigest()}"
        )
        for i, leaf in enumerate(leaves):
            d = {
                **v["disclosure"],
                "leaf": leaf,
                "i": i,
                "n": n,
                "salt": salts[i].hex(),
                "proof": [p.hex() for p in inclusion_proof(i, hashes)],
            }
            cases.append(case(d, manifest, trailer))
    assert page_codes(cases) == ["OK"] * len(cases)


def test_embedded_sample_and_edited_sample() -> None:
    html = PAGE.read_text(encoding="utf-8")
    sample = re.search(
        r'<script id="sample-data" type="application/json">(.*?)</script>', html, re.S
    )
    assert sample
    data = json.loads(sample.group(1))
    good = case(data["disclosure"], data["manifest"].encode("utf-8"), data["trailer"])
    data["disclosure"]["leaf"]["text"] += " [edited after sealing]"
    bad = case(data["disclosure"], data["manifest"].encode("utf-8"), data["trailer"])
    assert page_codes([good, bad]) == ["OK", "PROOF_FAIL"]


def test_page_is_local_and_names_git_checks_without_claiming_them() -> None:
    html = PAGE.read_text(encoding="utf-8")
    assert "connect-src 'none'" in html
    assert not re.search(r"<(?:script|link|iframe)[^>]+(?:src|href)=", html)
    for code in ("NO_SEAL", "WRONG_COMMIT", "NOT_IN_PR"):
        assert code in html
    assert "run flip verify" in html
    assert "Git checks not run" in html


def test_file_read_races_cannot_leave_a_stale_ok() -> None:
    """Exercise the shipped UI handlers with controllable local-file read promises.

    This is a DOM stub, not a browser rendering/file-picker claim.
    """
    html = PAGE.read_text(encoding="utf-8")
    scripts = dict(re.findall(r'<script id="(verify-core|verify-ui)">(.*?)</script>', html, re.S))
    sample = re.search(
        r'<script id="sample-data" type="application/json">(.*?)</script>', html, re.S
    )
    assert sample
    runner = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
globalThis.crypto = require('node:crypto').webcrypto;
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const elements = Object.create(null);
for (const id of input.ids) elements[id] = {
  value: '', textContent: '', disabled: false, hidden: false, dataset: {}, files: [], events: {},
  addEventListener(name, fn) { this.events[name] = fn; }
};
elements['sample-data'].textContent = input.sample;
globalThis.document = {getElementById: id => elements[id]};
vm.runInThisContext(input.scripts['verify-core']);
vm.runInThisContext(input.scripts['verify-ui']);
const fire = (id, name) => elements[id].events[name]({target: elements[id]});
const file = (id, bytes) => {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  elements[id + '-file'].files = [{arrayBuffer: () => promise}];
  const done = fire(id + '-file', 'change');
  return {done, resolve: () => resolve(new TextEncoder().encode(bytes).buffer)};
};
(async () => {
  fire('sample', 'click');
  await fire('check', 'click');
  assert.match(elements.status.textContent, /Proof checks OK/);
  const proof = elements.disclosure.value;
  const manifest = file('manifest', 'MALFORMED NEW MANIFEST');
  assert.equal(elements.check.disabled, true, 'Check must be disabled during a file read');
  assert.doesNotMatch(elements.status.textContent, /Proof checks OK/);
  const disclosure = file('disclosure', proof);
  manifest.resolve(); await manifest.done;
  assert.equal(elements.manifest.value, 'MALFORMED NEW MANIFEST',
    'Other file must not cancel this read');
  assert.equal(elements.check.disabled, true, 'Second file is still pending');
  disclosure.resolve(); await disclosure.done;
  assert.equal(elements.check.disabled, false);
  await fire('check', 'click');
  assert.equal(elements.status.textContent, 'MANIFEST_HASH');
  fire('sample', 'click');
  await fire('check', 'click');
  elements.trailer.value = '';
  fire('trailer', 'input');
  assert.doesNotMatch(elements.status.textContent, /Proof checks OK/);
  const late = file('manifest', 'LATE STALE BYTES');
  fire('clear', 'click');
  late.resolve(); await late.done;
  assert.equal(elements.manifest.value, '', 'Clear must cancel in-flight file data');
  assert.equal(elements.check.disabled, false);
})().catch(e => { console.error(e); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node_executable(), "-e", runner],
        input=json.dumps(
            {
                "ids": re.findall(r'\bid="([^"]+)"', html),
                "scripts": scripts,
                "sample": sample.group(1),
            }
        ),
        encoding="utf-8",
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("required", [False, True])
def test_missing_node_is_optional_locally_but_fatal_in_ci(
    required: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.setenv("FLIP_REQUIRE_NODE", "1" if required else "0")
    expected = pytest.fail.Exception if required else pytest.skip.Exception
    with pytest.raises(expected):
        page_codes([])
