# Verification record

Recorded 4 Nov 2026, 21:15 IST, updated 22:10 IST, on a Mac.
Machine: macOS 26.1, Python 3.12.2 (uv), git 2.50.1, local Switch server switch-core 0.31.0 at `http://127.0.0.1:52370`.
Every line below is backed by a command that passed or an evidence file in `evidence/`.

Windows offline update: 5 Nov 2026, run started 00:22:30 IST, on a Windows 11 machine.
Fresh remote clone of main at `44852e64d44893210112fc647e1e32aa4de2193d`, Python 3.12.6, offline checks, Windows, no make.
The Windows offline counts are pinned to that tested commit; the CI rows below describe the current workflow.

Windows live update: 5 Nov 2026, runs from 01:56 to 02:08 IST, on the same Windows 11 machine.
Windows 11 (10.0.26300), Python 3.12.6, git 2.55.0, Switch Console 0.40.1 (switch-core 0.31.0, the same as the Mac) with its own local server at `http://127.0.0.1:52115`.
Fresh remote clone of main at `b946c5a`, `uv sync --frozen`, then the README's "Without make" live commands with `FLIP_SWITCH_ENV` and `SWITCH_BASE` set.

## Test counts

| OS | Command | Result |
|---|---|---|
| macOS 26.1 | `make lint test`, twice | ruff, ruff format, mypy strict (also `--platform win32`) clean; 332 passed, twice |
| Ubuntu | `.github/workflows/ci.yml` on every PR | Green (required job) |
| Windows | `.github/workflows/ci.yml` on every PR | Green since PR #7; a failure fails the run (PR #25) |
| macOS | `.github/workflows/ci.yml` on pushes to `main` | Runs on `main` only: GitHub cancelled PR macOS jobs for lack of runners |
| Windows, Python 3.12.6, offline, no make | Exact `uv` equivalents in `evidence/m4-20261105T002230.log` | Ruff check/format and strict mypy (default and win32) pass; 328 passed and 2 skipped, twice |

## Clean clone

A fresh `git clone` of branch `m3-live-switch` into a temp directory, then `uv sync --frozen`, `make lint`, `make test`, `make g8`, `make replay-offline` and `make fixtures`: all exit 0, 228 passed, 8/8 fixtures match.
The second-machine offline checks pass on Windows from a fresh remote clone of main at `44852e6`; evidence is `evidence/m4-20261105T002230.log`.
The two full test runs took 160.51 and 158.89 seconds, each with 328 passed and 2 skipped.
Make is absent, so the exact command argv for `uv sync --frozen`, ruff check/format, strict mypy (default and win32), both pytest runs, both G8 outcomes, offline replay and all nine fixtures were run directly and are preserved in the log.
The G8 original returns `OK` with exit 0; the forged quote returns `PROOF_FAIL` with exit 2.
Pytest uses separate short temporary directories to avoid Windows path-length failures in the synthetic home/session tests.
The live replay then ran on the same Windows machine with its own Switch server (Windows live update above).
`flip replay` passed with verdicts `OK` 1 and `PROOF_FAIL` 1, the other three refusals in its summary (`switch_refusals` 1, `dropped_requests` 1, `card_403` 1), and the coverage lines of the Mac's run after #17 (`evidence/solo-csv-export-20261105T010413.log`): `auth/session.py: 2 sealed steps, 1 disclosed, 1 not disclosed (step 6)` and `reports/export.py: 2 sealed steps, 0 disclosed, 2 not disclosed (steps 1, 2)`.
The Mac's replay log (`evidence/replay-switch-csv-export-20261104T210939.log`) predates #17, so it says "withheld" where both newer logs say "not disclosed"; the counts are the same.
On `b946c5a` both agents exited with code 1 at the end of each live run: on Windows a signal from the parent is `TerminateProcess`, which skipped the agents' shutdown.
PR #21 stops them through a stop file; `evidence/solo-csv-export-20261105T020718.log` shows both exiting 0 and logging `stopped`.

## Judge run from a fresh clone

Recorded 5 Nov 2026, 20:19 to 20:21 IST, on a second Mac (macOS 26.1, Docker 28.1.1).
Fresh clone of branch `67-judge-kit` from GitHub, `uv sync --frozen`, `make lint`, then `make judge-live`.

| Check | Result | Evidence |
|---|---|---|
| `make judge-live` from the fresh clone: 7 seal checks, offline review, 9 fixtures, Docker stack, review on real Switch 0.31.0 and Mattermost, K5, no model | 13/13 PASS in 96.8 s | `evidence/judge-20261105T202021.log`, `.json` |
| The review that run played on real Switch | RESULT PASS, four refusals live, 14 Switch message ids | `evidence/demo-mattermost-csv-export-20261105T201917.log` |
| K5 in that run | 8/8 passed | `evidence/k5-20261105T201936.log` |
| `make judge-live` with J13 (all 9 labelled cases on real Switch), 20:47 to 20:50 IST | 14/14 PASS in 192.0 s; every case RESULT PASS | `evidence/judge-20261105T205018.log`; the 9 `evidence/demo-mattermost-<case>-` logs from 20:48 to 20:50 IST |
| `make judge` offline on the Mac | 11/11 PASS in 11.6 s; reads only committed logs; tracked files unchanged | `evidence/judge-20261105T210243.log` |

## Checks

| Check | Command | Evidence |
|---|---|---|
| K1, K2 (9/9) | `make killtests` | `evidence/k1k2-20261104T195815.log` |
| K4 (6/6, three runs) | `make killtests` | `evidence/k4-20261104T202125.log`, `evidence/k4-20261104T202158.log`, `evidence/k4-20261104T202207.log` |
| Seal core: G1 to G8 | `make lint test`, `make g8` | `evidence/m1-20261104T201854.log` |
| Offline flow | `make replay-offline` | `evidence/replay-offline-csv-export-20261104T205047.log` |
| Live flow, twice, four refusals, restart | `make solo` | `evidence/solo-csv-export-20261104T210302.log`, `evidence/solo-csv-export-20261104T210641.log` |
| Live replay on this machine | `make replay` | `evidence/replay-switch-csv-export-20261104T210939.log` |
| Second machine, offline checks, Windows, no make; two full test passes, G8, replay-offline, fixtures 9/9 | Exact `uv` argv in the log | `evidence/m4-20261105T002230.log` |
| K1, K2 (9/9) and K4 (6/6) on the second machine, Windows | README "Without make" live block | `evidence/k1k2-20261105T015630.log`, `evidence/k4-20261105T015655.log` |
| Live replay from a clean clone on the second machine, Windows, its own Switch server; same verdicts and coverage lines | `uv run --frozen python -m flipside.cli replay` | `evidence/replay-switch-csv-export-20261105T015811.log` |
| Live flow on the second machine, Windows: live flow, four refusals, both agents killed and restarted | `uv run --frozen python -m flipside.cli solo` | `evidence/solo-csv-export-20261105T015719.log` (on `b946c5a`, agents exit 1 at the end), `evidence/solo-csv-export-20261105T020718.log` (PR #21, agents exit 0) |
| Offline flow on the second machine, Windows | `uv run --frozen python -m flipside.cli replay --offline` | `evidence/replay-offline-csv-export-20261105T015907.log` |
| Two machines over a private tailnet: author-agent and Switch 0.31.0 on the Mac, reviewer-agent on Windows; seal commit 29eb6c3, root 7b9cbb8, 34 leaves; 2 questions, 5 leaves OK, 0 contradictions; the reviewer's request for the whole session refused (room lines 26 and 27) | manual run | `evidence/m2-author-20261105T172923.log`, `evidence/m2-reviewer-20261105T172644.log` |
| Live flow with each agent in its own process, both killed with SIGKILL mid-flow and restarted | `make solo` | `evidence/solo-csv-export-20261104T212946.log` |
| All 8 fixture cases live, twice | `make solo-all` | `evidence/solo-all-20261104T214727.log` (8/8, after both fixes below), `evidence/solo-all-20261104T215327.log` (8/8; `daemon.py` gained the reviewer-head default from GitHub while this run was going, which the fixture configs do not use) |
| All 9 fixture cases live, twice, after SPEC C14 and C15 | `make solo-all` | `evidence/solo-all-20261104T222327.log` (9/9), `evidence/solo-all-20261104T222923.log` (9/9) |
| 9 fixture cases | `make fixtures` | `docs/results/fixtures.md` |
| Real session end to end: `claude -p` made the change in a synthetic sandbox repo, `flip seal`, `flip setup` (three steps), both `flip agent` processes, people via `flip chat`; 2 questions, 8 leaves OK, 0 contradictions | manual run | `evidence/real-session-20261104T224823.log` |
| The same sealed PR on GitHub (`kadoo69/flipside-sandbox#1`, private, with a GitHub Actions check run): reviewer cloned from GitHub, `flip setup reviewer --github`, reviewer-agent read the PR with `gh api`; 2 questions, 2 answered, 8 leaves OK, 0 contradictions | manual run | `evidence/github-pr-20261105T002706.log` |
| All 9 fixture cases live, twice, after one-card-per-leaf | `make solo-all` | `evidence/solo-all-20261104T225437.log` (9/9), `evidence/solo-all-20261104T230152.log` (9/9) |
| M1b: the whole review in Mattermost from a fresh clone; both people type as their own Mattermost accounts, the author presses Approve in Mattermost, four refusals, both agents killed and restarted | `make demo` | `evidence/demo-mattermost-csv-export-20261105T131047.log` (private rooms), `evidence/demo-mattermost-csv-export-20261105T122618.log` (fresh clone of `295bfff`), `evidence/demo-mattermost-csv-export-20261105T122010.log` |
| M1b in CI on ubuntu-latest: Switch 0.31.0 and Mattermost in Docker, the author approves in Mattermost, the reviewer's card answer refused (403), four refusals live, `RESULT PASS csv-export` | `make demo` (CI job `demo`, every PR and push to main) | CI artifact `demo-mattermost-log`; first green run 42028174363 on PR #57 |
| K5 (8/8): in Mattermost, Switch addresses the author's claimed account, refuses the reviewer's and an unclaimed account's tag, takes a card press only from the author, and refuses each person changing the other's room | `make k5` | `evidence/k5-20261105T153338.log` (8/8, after #37: only a 403 counts as a refusal), `evidence/k5-20261105T130850.log`, `evidence/k5-20261105T132226.log` (8/8); `evidence/k5-20261105T130947.log` (6/8, run on purpose against the old room setup: K5.g and K5.h accepted); `evidence/k5-20261105T123747.log`, `evidence/k5-20261105T123842.log` (6/6, before K5.g and K5.h existed) |
| `site/verify.html` gives the same verdict as `flip verify` on every pinned vector, both G8 examples and ordered malformed, metadata, size and tamper cases, for the checks a browser can run; Git checks (`NO_SEAL`, `WRONG_COMMIT`, `NOT_IN_PR`) are left to `flip verify` | `FLIP_REQUIRE_NODE=1 uv run --frozen pytest tests/blind/test_browser_verify.py` (CI, Node 22) | 15 tests; real Chromium check of the page served on 127.0.0.1: sample `OK`, edited sample `PROOF_FAIL`, no console errors (5 Nov) |
| The author presses Approve on author-agent's card in the Mattermost web app, by hand in a browser; the run waits for it and passes | `flip demo run --press` | `evidence/demo-mattermost-csv-export-20261105T131710.log`; `evidence/demo-mattermost-card-20261105T1318-before.png` (card with 1. Approve and 2. Decline), `evidence/demo-mattermost-card-20261105T1318-after.png` ("Chosen by @Author from Mattermost"), `evidence/demo-mattermost-shared-20261105T1319.png` (the shared room: answer relayed, disclosure, verdict OK, brief) |

Two earlier `make solo` runs are kept as they ran:
- `evidence/solo-csv-export-20261104T205555.log` failed: the duplicate check counted the scripted injection request as a repeat of the real request.
  Attack posts are now excluded (`tests/room/test_run.py`).
- `evidence/solo-csv-export-20261104T205916.log` passed, but reviewer-agent also refused untagged messages from the author and author-agent.
  `make solo` now sets reviewer-agent's room rule before author-agent joins.

The first `make solo-all` run (`evidence/solo-all-20261104T213925.log`) passed 6/8, and both failures are fixed with tests:
- csv-export: the forged copy landed after the brief, so the brief had no `PROOF_FAIL`; the run summary now counts verdicts in the room (`tests/room/test_run.py`).
- reseal-after-questions: the restarted author-agent crashed because the session had been rewritten; it now withholds `session_changed` (`tests/room/test_agents.py`).

## Switch message ids (live flow, `evidence/solo-csv-export-20261104T210641.log`)

| Message | Switch id |
|---|---|
| Seal (author-agent) | `sw_242dadb261c64d15b42b4697d1e64828` |
| Questions (reviewer-agent) | `sw_df03ddac09964a53a7d26529ad8ceeb8` |
| Request, Q1 leaf 5 (reviewer-agent) | `sw_24668388203d48119c58de1c23d9c303` |
| Answer Q1 (Author) | `sw_fa1f4754b6124c708a14738c6b3ea1dc` |
| Reviewer tags author-agent | `sw_c991dd86d2a54db4b38a796f0457ce66` |
| Refusal 1: Switch's own refusal, posted as author-agent | `sw_419b99579d5b4d618b465200a2b34b0f` |
| Refusal 2: free-text request, dropped by author-agent | `sw_ed05644ea71748a3958007f1fb91e9f1` |
| Refusal 4: the reviewer answering the author's card | HTTP 403 "You may not address this agent, so you may not answer it." (card `f8eebc1f`) |
| Disclosure, approved by Author | `sw_d33352832f3e4eb39be86041b505593f` |
| Forged copy (one word edited) | `sw_895d2eee1cd843f2b16d8a56d8edc6af` |
| Verdict OK | `sw_bde907166a254a0692d603a67e00a93e` |
| Refusal 3: verdict PROOF_FAIL on the forged copy | `sw_f29b92ea7256401f9b52d50354ff741e` |
| Brief, mentions the reviewer | `sw_65b88a4f00634713b715e87ca0d6987d` |

Restart test, in the same run: reviewer-agent was stopped and restarted before round 2, author-agent before round 3 (after its card was approved, before it disclosed).
The log shows 0 duplicate agent posts, and the restarted author-agent disclosed the approved leaf once.

## K3: the approval card in Slack

`make k3` with `SLACK_BOT_TOKEN_FILE` set; 4/4 in `evidence/k3-20261105T005334.log`.
Setup: a synthetic Slack workspace (Flipside, `T0CEY09M1LJ`), an app made from Switch's manifest without the `agent_view` block, Socket Mode, connected to the local server.
The author's Switch account claimed the Slack user.

| Check | Result |
|---|---|
| K3.a the author's private room is bridged to a private Slack channel | channel `C0CEGUSSJJ3` |
| K3.b author-agent's card renders with Approve and Decline buttons | `evidence/k3-slack-card-20261105T005334-before.png` |
| K3.c the reviewer cannot answer it | 403 `NOT_AUTHORIZED` |
| K3.d the author presses Approve in Slack and author-agent receives `approve` | the log records `answer: approve`, `answeredBy` the author's bridged Slack identity (`evidence/k3-20261105T005334.log`); `evidence/k3-slack-card-20261105T005334-after.png` shows the channel after the press, with the card no longer shown |

Earlier runs are kept.
`k3-20261105T004827.log`: creating a bridged room needs `channel_type`.
`k3-20261105T004840.log`: no live agent connection, so Switch showed "Host offline" and no buttons; stopped by hand.
`k3-20261105T005115.log`: 3/4; K3.d expected a Switch user id, but a Slack press carries the bridged Slack identity.

## The live flow in Slack channels

`flip solo --slack --press --pace 2 --no-restart`: PASS in `evidence/solo-csv-export-20261105T011603.log`.
`#pr-142` and `#pr-142-author` were private Slack channels on the Slack connection, with the author's linked Slack account added to both.
The people's script answered Q1 through the gateway and did not answer the card; the author pressed Approve in Slack (`evidence/solo-csv-export-20261105T011603-slack-card.png`), and author-agent disclosed leaf 5.
Four refusals live, 0 duplicate agent posts, verdict `OK` on the real disclosure and `PROOF_FAIL` on the forged copy.
`flip solo --slack` without `--press` also passed (`evidence/solo-csv-export-20261105T011008.log`).

## Demo video

Not recorded yet; its SHA-256 goes here.

## Launch film on the site

`site/media/flipside-film.mp4`: 78.0 s, 10,128,592 bytes, SHA-256 `7377051a1c39215e05e69e7852dbda23009b475dcfb96fa406b8d26c9a543035`.
It is a 78-second film with music, in the site's colours, not the demo video above; the interfaces in it are rebuilt with the real text from the evidence logs.
`tests/test_site.py` keeps it under 15 MB and pins the vendored three.js r160 by SHA-256.

## Evidence folder

`evidence/` keeps every logged run, passing or not; this page links the runs each claim rests on.

## Outside the checked scope

- Questions answered by typing in Slack: not supported. Switch reports a Slack message as `kind: human` with no user id; the agents accept a person's messages only as `user:<switch id>`.
  A card press in Slack is accepted: author-agent matches `@switch-slack-<connection>-<username>` (the id before `:<server>`) against the author's linked accounts.
- On two machines, the reviewer pressing the author's card: not run, because every card was decided; K2 and K5 check that 403 on one machine.
- In fixtures, PR data (title, body, changed files, check runs) comes from each case's `case.json`; the GitHub reader ran on the sandbox PR and on team PRs #2 and #7.
- All sessions and repos in `fixtures/` and `examples/` are synthetic.
  Real Claude Code sessions were sealed only for G4, G6 and G7 (seal core evidence log).
- reviewer-agent's room rule admits every person in its own `#pr-<n>` room (`users: "*"`): Switch matches people by a member client id that the gateway does not expose.
  Only the author and the reviewer are members, and reviewer-agent acts only on answers from the PR author's sender id.
- `make replay` used the already-running local server, not a fresh one.

`evidence/solo-all-20261104T221502.log` passed 9/9 but is not counted as evidence.
It started after the C14 fix and before C15 and the `PreToolUse:` prefix, and the fixtures were regenerated while it ran.
The two runs above use the committed code.

The GitHub run found one bug, fixed with a test: an author repo whose `.git/flipside/work-author` came from an earlier setup for the same commit made author-agent wait on that setup's cards, so the new room never got one.
Agent state and the event cursor now record their rooms (and agent), and a mismatch starts fresh.

The first real-session run found three bugs, each fixed with a test (commit e8530d0): the default work directory did not exist, so state saves failed; two questions on one merged step gave the author a card per question for the same bytes; and "with tests" did not count as mentioning the test file.
