# Handoff

Updated 4 Nov 2026, 20:25 IST.

## Goal

Win Flip the Switch, Track 01 Business ($2k), with Flipside: the owning team questions the author team's private coding-agent session through Switch, and verifies every quote against a Merkle root sealed into the PR.

## State

Done:
- Idea chosen over Treaty and other candidates after several judge rounds (`docs/judging/SCORES.md`).
- Kill tests K1 and K2 pass 9/9 against switch-core 0.31.0 on the native local server, three runs in a row (`killtests/k1_k2.py`, `evidence/k1k2-*.log`).
- Seal spec v1 (visual: `docs/seal/flip-seal-spec.pdf`) and v1.1 (normative: `docs/seal/SPEC.md`, adds fixes F1 to F6).
- Seal maths prototyped in `docs/seal/example.py`: proofs verify for every tree size 1 to 69; tamper and wrong index fail. It still implements v1 fields.
- Final build plan with milestones and gates: `docs/BUILD.md`.
- Team rules and agent board files: `AGENTS.md`, `tools/board`, `.claude/`, `.github/ISSUE_TEMPLATE/`.
- Blind judging on the official rubric: Flipside 7.1 (Claude), 6.2 to 6.5 (Codex); Use of Switch 9, Creativity 9, Technical 2 to 3. Built competitors LedgerRoom, Preflight and Canary score 7.0 to 8.5.

- M0 shared parts: `pyproject.toml` (Python 3.12+, stdlib runtime, dev group pytest, ruff, mypy; `uv.lock`), `Makefile` (`test`, `lint`, `g8`, `killtests`, and `replay-offline`, `solo`, `replay` plumbing).
  `make killtests` passes K1/K2 9/9 (`evidence/k1k2-20261104T195815.log`).
- M1 seal core, all gates G1 to G8 green: `evidence/m1-20261104T201854.log`.
  Modules: `flipside/seal/` canon, merkle, steps, manifest, git, seal, prove, verify, coverage, secrets; CLI `flip seal | prove | verify` in `flipside/cli.py`.
  165 tests, ruff and mypy strict clean, green twice in a row.
  `docs/seal/example.py` is v1.1 and reproduces `tests/vectors/seal_v1_1.json` byte for byte.
  `examples/` holds the G8 offline check (`make g8`), regenerated exactly by `examples/build.py`.
- K4 passes 6/6, three runs in a row (`evidence/k4-20261104T2021*.log`, `k4-20261104T2022*.log`).
- `flip solo` and `flip replay` dispatch to `flipside.room.solo.main(argv)` and `flipside.room.replay.main(argv)`; they print "not built yet" until the room lane adds them.

Not started:
- Room lane (M2): everything in `flipside/room/`.
- Git: the folder is still not a repository, so nothing is committed or on a branch yet.
- GitHub repo and board issue (the teammate does this, `docs/SETUP-REPO.md`).
- K3 (Slack card), demo video, README.

Stale on purpose:
- `docs/PITCH.md` describes the pre-merge design; `docs/BUILD.md` section 13 lists the changes. Update it in M6.

## Decisions

| Decision | Reason |
|---|---|
| Flipside, Treaty as fallback only | Higher single and paired judge scores; uncrowded core mechanism |
| Merge in the Gate-plus-Seal review: deterministic gaps, reviewer names leaves, author answers in own words | Removes every LLM from deciding paths; stops cherry-picking; keeps the original problem (can the author explain the change) |
| Keep Switch approval cards, not chat-text approvals | K2 proved Switch itself refuses the reviewer (403); that is our strongest load-bearing proof |
| Keep scoped addressing (owner, owner's agents, reviewer-agent in this room) | K1.e and K1.f proved it; the reviewer stays refused |
| Approval cards in a private author room | A card in the shared room would show the bytes before approval |
| Seal on an empty commit with a trailer | No history rewrite; questions pin it |
| Manifest as a Switch attachment | Size; the upload endpoint exists in 0.31.0 |
| Built-in chat for kill tests and replay, Slack for the demo | No accounts for judges; Slack is where cross-team review happens |
| Python stdlib only at runtime | No dependency in the verification path; easy clean clone |
| SPEC clarifications C1 to C4 (lead, 4 Nov): floats allowed in step text only; `mentions` inherited by Bash results; step `cmd` by priority test > lint > build > other, `python3 -m` stripped; new check 0 `BAD_DISCLOSURE` | Real sessions have float tool inputs; consistency with `files` and `cmd`; malformed input needs its own code. C5 to C13 are recorded in `docs/seal/SPEC.md` |
| `flip verify --bundle` clones a git bundle into a temp dir | G8 runs with no network and no Switch (also checked under `sandbox-exec` with network denied) |
| Examples use the demo key (32 zero bytes) and a fixed git clock | The seal commit hash is the same on every machine |

## Dead ends

- Codex judge models: only `gpt-6-luna` works on this ChatGPT account.
- curl truncates the gateway OpenAPI in the sandbox; use Python `urllib`.
- Agent endpoints reject camelCase bodies with 422; send snake_case.
- The reviewer cannot add their own agent to the author's room (403); the room owner adds both agents.
- Switch mediation hooks do not record tool calls, so they cannot be an independent session log.
- Docker is not needed for the local server; the bundled Mattermost is off without it.
- `uv run --project x pytest` first classified as `other`: launcher flags that take a value must skip the value too (fixed, C5).
- argparse `REMAINDER` rejects a leading `--offline`; room commands are dispatched before argparse.
- A git bundle without `HEAD` clones with `HEAD` on `main`, which gives `NOT_IN_PR`; `examples/build.py` bundles `HEAD`.
- A gate script that pipes into `tail` hides failures; the M1 gate run uses `set -o pipefail`.
- In a shared room Switch's built-in agents post auto-replies ("Hi! I'm ...", "I don't have a session connected ...") and reviewer-agent's default policy refuses the author; room parsers must ignore every non-protocol message (seen in K4 logs).

## Files

- `docs/BUILD.md`: the build, milestones, gates, protocol, rules, demo, limits.
- `docs/seal/SPEC.md`: seal, prove, verify, coverage; normative.
- `killtests/switch_api.py`, `killtests/k1_k2.py`: working Switch client and kill tests; start `flipside/room/switch_client.py` from them.
- `docs/judging/`: judge prompts, outputs, `SCORES.md`, competitor field in `h2h/FIELD.md` and `h2h/readmes/`.

## Run

```
uv sync                               # dev tools into .venv
make lint test                        # ruff, mypy strict, 165 tests
make g8                               # offline: q2-ok OK, q2-forged PROOF_FAIL
make killtests                        # K1, K2, K4; needs Switch Console's local server at 127.0.0.1:52370
python3 docs/seal/example.py --json   # reproduces tests/vectors/seal_v1_1.json
```

Judge commands:

```
claude -p --model claude-opus-5-5 < prompt.txt
codex exec --skip-git-repo-check --sandbox read-only -m gpt-6-luna -o out.txt - < prompt.txt
```

Run Claude judges from a directory outside the repo, so the judge cannot tell which entry is ours.

## Open questions

- The teammate's GitHub login, for `AGENTS.md`.
- Does the teammate have the earlier Ownership Gate code (156 tests: `transcript.py`, `commands.py`, `contradictions.py`, `live.py`)? If yes, port the useful parts into `flipside/room/`; `docs/BUILD.md` does not depend on it.
- Slack workspace access for K3.

## Interface for the room lane

- `flipside.seal.verify.verify(repo, disclosure, manifest_bytes, *, commit, head="HEAD") -> Verdict` (`.code`, `.ok`, `.message()`, `.leaf`); pure part: `check_shape(d)`, `check_against_seal(d, manifest_bytes, SealTrailer)`.
- `flipside.seal.prove.rebuild(repo, root) -> Rebuilt`, `disclosure(rebuilt, i, commit=None)`, `prove(repo, root, i)`, `leaf_secret_hits(rebuilt, i)` (scans the whole step, so split secrets are caught); errors are `ProveError` with `.code` `SESSION_CHANGED`, `NO_STATE` or `BAD_LEAF`.
- `flipside.seal.coverage.coverage(manifest, verified_indexes, files) -> list[FileCoverage]`, `format_line(fc)`, `FileCoverage.to_json()`.
- `flipside.seal.manifest.load_manifest(bytes) -> list[dict]` (raises `ManifestError`).
- `flipside.seal.git.trailer_values(repo, commit)`, `parse_trailer(value)` for seal detection.

## Pending board posts (board not set up yet)

1. `@all` contract change: SPEC v1.1 clarifications C1 to C13, including new verify code `BAD_DISCLOSURE` (check 0) that the room lane may post as a `verdict` code.
2. M1 gates green: commands and output in `evidence/m1-20261104T201854.log`; interface above.
3. K4 green; Makefile targets `replay-offline`, `solo`, `replay` expect `flipside.room.replay.main(argv)` and `flipside.room.solo.main(argv)`; the room owner may rename them.

## Next step

Teammate: M0 (`docs/SETUP-REPO.md`), then M2.
Lead's agent: once the repo exists, commit M0 and M1 on a branch and post the three board messages; M3 starts when M2 lands.
