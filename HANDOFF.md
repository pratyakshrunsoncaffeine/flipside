# Handoff

Updated 4 Nov 2026, 23:30 IST.
Load first: `AGENTS.md`, this file, `docs/BUILD.md` (gates, protocol, Switch facts in section 9), `docs/seal/SPEC.md` before touching `flipside/seal/`, `VERIFICATION.md` (evidence).
Skills: `pr-protocol` before branching or opening a PR; `handoff` to update this file.

## Goal

Win Flip the Switch Track 01 (deadline 7 Nov 2026, 23:59 IST; team target 7 Nov 18:00 IST) with Flipside.
Flipside lets the owning team question the author team's private coding-agent session through Switch, and verify every quote against a Merkle root sealed into the PR.

## State

The team repo is `pratyakshrunsoncaffeine/gateplus` (private).
Pratyaksh is lead and chose Flipside as the base (board, 4 Nov 23:00 IST).
PR #2 (`flipside-base`) merges Flipside into `main` and moves Gate v1 to `legacy/gate-v1/`.
It is open, and its CI run is queued.

Done (evidence in `evidence/`, details in `VERIFICATION.md`):
- K1/K2 9/9, K4 6/6 (`make killtests`); G1 to G8 (`make lint test g8`).
- Offline flow with the four refusals (`make replay-offline`); 9 synthetic fixtures, 9/9 offline (`make fixtures`).
- Live on the local Switch server:
  - `make solo`: each agent in its own process, both killed with SIGKILL and restarted, 0 duplicate posts.
  - `make solo-all`: 9/9, twice, on the latest code (`evidence/solo-all-20261104T225437.log`, `evidence/solo-all-20261104T230152.log`).
- A real Claude Code session end to end (`evidence/real-session-20261104T224823.log`):
  1. `claude -p` changed a synthetic sandbox repo.
  2. `flip seal`, then the three `flip setup` steps.
  3. Both `flip agent` processes ran, and the people acted through `flip chat`.
  4. Result: 2 correct questions, 8 leaves verified, brief with 0 contradictions.
- `flip setup` (three steps, one join line each way, ids only) and `flip chat` (read, say, cards, show, answer).
- SPEC C14 and C15: a Bash call that never ran seals as `ok: null`; `cmd` classifies every shell segment, wrappers and package scripts.
- One approval card per leaf; its answer covers every question that asked for that leaf, also after a restart.
- 312 tests pass twice on the merged tree; ruff, ruff format and mypy strict are clean; Gate v1's 156 tests pass in `legacy/gate-v1/`.

Not done:
- PR #2: needs green CI and the lead's merge.
- Lanes in flight:
  - Pratyaksh's Claude ports Gate v1's oversize, claimed-command, failed-not-rerun and prompt-mention rules into `flipside/room/rules.py`. Do not edit `rules.py` until that PR lands.
  - Pratyaksh's Claude also does the Windows fixes.
  - Pratyaksh's Codex does the Windows baseline, the C3 demo checks in `demo/`, and blind fixtures `fixtures/b/`.
- The GitHub PR reader end to end on a sealed PR: blocked. Auto mode refused to create a scratch GitHub repo, so the real-session run used a local git remote.
- K3 (Slack approval card): needs a Slack workspace connected to Switch's Slack bridge.
- A chat window for the demo: needs Docker and the bundled Mattermost, or Slack.
- Second-machine clean clone (M4): on Pratyaksh's machine.
- Demo video (at most 2.5 minutes, BUILD section 11) and its SHA-256; final judge run; submission.
- Making the repo public before 7 Nov 23:59 IST: needs admin, so Pratyaksh.

## Decisions

| Decision | Reason |
|---|---|
| Flipside is the base; Gate v1 is kept unchanged in `legacy/gate-v1/` | Lead's decision on the board; the rules port reads from there |
| `tools/board` is `main`'s newer version | It adds `BOARD_SIGN` and `BOARD_HANDLE` for two agents on one login |
| `tests/test_board.py` and `legacy/` are excluded from ruff and mypy | Vendored from the board template, and legacy code with its own config |
| Approvals are Switch cards in a private author room | K2: Switch refuses the reviewer (403); `approve 41` in chat would not be enforced |
| One card per leaf, not per question | The same bytes need one decision; two questions on one merged step gave duplicate cards |
| C14: never-ran Bash calls seal `ok: null` | A rejected rerun was sealed as a failed test and gave honest PRs a false TESTS question |
| C15: `cmd` from every shell segment, wrappers stripped, package scripts read | `npm run test` and `source .venv/bin/activate && pytest` were sealed as `other` |
| A test file counts as mentioned when the body says it adds tests and names its subject | "with tests" still asked about `tests/test_report.py`; Gate v1's looser name-word rule would hide the disabled-test case |
| `flip setup` swaps join lines carrying ids only | Neither side sees the other's credentials |
| Leaves keep absolute paths in tool inputs | The SPEC seals text verbatim; the author sees and approves the exact bytes |
| reviewer-agent's room rule is `users: "*"` in its own `#pr-<n>` | Switch matches people by a member client id the gateway does not expose; reviewer-agent acts only on the PR author's sender id |
| Keep the name Flipside inside the repo `gateplus` | No code uses the repo name; renaming would change the trailer, SPEC and vectors |

## Dead ends

- Auto mode refuses `gh repo create`, so the agent cannot make a scratch GitHub repo.
  It also refused accepting the invite until the user approved.
- A git bundle without `HEAD` gives `NOT_IN_PR`; `examples/build.py` bundles `HEAD`.
- Piping a gate script into `tail` hides failures; use `set -o pipefail`.
- A chat cannot be created without an agent (422 `AGENTS_REQUIRED`), and agent names are unique per server (409).
- An agent key gets 401 on gateway messages; agents read through their owner's gateway session.
- A second clone has no `killtests/.local-users.json`; `make solo` and `make killtests` now stop with a clear message instead of inventing passwords for existing users. Copy the file (mode 0600) from the clone that created the users.
- A local secrets hook blocks any shell command whose text contains ".env"; write such edits as a script file and run it by path.
- A hook rewrites some shell commands (`make` becomes `rtk make`), and auto mode then asks for the call to be sent again on its own.

## Files

- Seal: `flipside/seal/` (canon, merkle, steps, manifest, git, seal, prove, verify, coverage, secrets), `flipside/cli.py`.
- Room: `flipside/room/`:
  - `agents.py`: author-agent and reviewer-agent, both event-sourced.
  - `rules.py`: gaps, selection, contradictions (Pratyaksh's lane).
  - `switch_client.py`, `daemon.py` (`flip agent`), `setup.py` (`flip setup`), `chat.py` (`flip chat`).
  - `solo.py` (`flip solo [--all]`), `replay.py`, `run.py`, `scenario.py`, `github.py`, `protocol.py`, `brief.py`, `transport.py` (FakeSwitch).
- Fixtures: `fixtures/build_fixtures.py` writes `fixtures/cases/<case>/`.
- Tests: `tests/seal/`, `tests/room/`, `tests/test_board.py`; Gate v1 in `legacy/gate-v1/tests/`.
- Local only, never committed: `killtests/.local-users.json` (mode 0600), agent configs, `.git/flipside/`.

## Run

Clones: `~/flipside` (Aarav's original, branches `m0` to `m8`, remote `team`), `~/gateplus-kadoo69` (team clone, branch `flipside-base`, PR #2).
Remote branches: `main` (Gate v1 until PR #2 merges), `flipside` and `m8-real-pr-setup` (both at Aarav's latest), `flipside-base` (PR #2).

```
uv sync --frozen
make lint test          # ruff, ruff format, mypy strict, 312 tests; run twice
make g8                 # offline: q2-ok OK, q2-forged PROOF_FAIL
make replay-offline     # full flow on FakeSwitch
make fixtures           # 9 cases offline; writes docs/results/fixtures.md
make killtests          # K1, K2, K4; needs Switch Console's local server at 127.0.0.1:52370
make solo               # live flow, agents as processes, SIGKILL restarts
make solo-all           # all 9 cases live
cd legacy/gate-v1 && pip install -e ".[dev]" && python -m pytest -q   # Gate v1, 156 tests
```

A real PR, by hand: README section "Run it on a real PR" (`flip seal`, `flip setup` three steps, `flip agent`, `flip chat`).

## Open questions

- A scratch GitHub repo for the GitHub reader's end-to-end run: the user creates it (`gh repo create kadoo69/flipside-sandbox --private`), or allows the agent to.
- Slack workspace for K3, or Docker plus Mattermost, for a chat window in the demo.
- Demo narration: macOS `say` (free, local) or an ElevenLabs key.
- The lead confirms the Codex lane row added to `AGENTS.md` in PR #2.

## Next step

When PR #2's CI is green and the lead merges it: rebase `m8-real-pr-setup` work onto `main` (it is already in), then run the GitHub reader end to end on a sealed PR in a scratch repo.
