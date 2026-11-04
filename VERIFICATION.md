# Verification record

Recorded 4 Nov 2026, 21:15 IST, updated 22:10 IST, by the lead's agent on the lead's machine.
Machine: macOS 26.1, Python 3.12.2 (uv), git 2.50.1, local Switch server switch-core 0.31.0 at `http://127.0.0.1:52370`.
Every line below is backed by a command that passed or an evidence file in `evidence/`.

## Test counts

| OS | Command | Result |
|---|---|---|
| macOS 26.1 | `make lint test`, twice | ruff and mypy clean; 241 passed, twice |
| Ubuntu | `.github/workflows/ci.yml` | Not run yet: the GitHub repo does not exist yet |

## Clean clone

A fresh `git clone` of branch `m3-live-switch` into a temp directory, then `uv sync --frozen`, `make lint`, `make test`, `make g8`, `make replay-offline` and `make fixtures`: all exit 0, 228 passed, 8/8 fixtures match.
The second-machine run (M4 gate, the teammate's laptop) is not done yet.

## Gates

| Gate | Command | Evidence |
|---|---|---|
| K1, K2 (9/9) | `make killtests` | `evidence/k1k2-20261104T195815.log` |
| K4 (6/6, three runs) | `make killtests` | `evidence/k4-20261104T202125.log`, `evidence/k4-20261104T202158.log`, `evidence/k4-20261104T202207.log` |
| M1: G1 to G8 | `make lint test`, `make g8` | `evidence/m1-20261104T201854.log` |
| M2: offline flow | `make replay-offline` | `evidence/replay-offline-csv-export-20261104T205047.log` |
| M3: live flow, twice, four refusals, restart | `make solo` | `evidence/solo-csv-export-20261104T210302.log`, `evidence/solo-csv-export-20261104T210641.log` |
| M4: live replay on this machine | `make replay` | `evidence/replay-switch-csv-export-20261104T210939.log` |
| M3 with each agent in its own process, both killed with SIGKILL mid-flow and restarted | `make solo` | `evidence/solo-csv-export-20261104T212946.log` |
| All 8 fixture cases live, twice | `make solo-all` | `evidence/solo-all-20261104T214727.log` (8/8, after both fixes below), `evidence/solo-all-20261104T215327.log` (8/8; `daemon.py` gained the reviewer-head default from GitHub while this run was going, which the fixture configs do not use) |
| All 9 fixture cases live, twice, after SPEC C14 and C15 | `make solo-all` | `evidence/solo-all-20261104T222327.log` (9/9), `evidence/solo-all-20261104T222923.log` (9/9) |
| M5: 9 fixture cases | `make fixtures` | `docs/results/fixtures.md` |

Two earlier `make solo` runs are kept as they ran:
- `evidence/solo-csv-export-20261104T205555.log` failed: the duplicate check counted the scripted injection request as a repeat of the real request.
  Attack posts are now excluded (`tests/room/test_run.py`).
- `evidence/solo-csv-export-20261104T205916.log` passed, but reviewer-agent also refused untagged messages from the author and author-agent.
  `make solo` now sets reviewer-agent's room rule before author-agent joins.

The first `make solo-all` run (`evidence/solo-all-20261104T213925.log`) passed 6/8, and both failures are fixed with tests:
- csv-export: the forged copy landed after the brief, so the brief had no `PROOF_FAIL`; the run summary now counts verdicts in the room (`tests/room/test_run.py`).
- reseal-after-questions: the restarted author-agent crashed because the session had been rewritten; it now withholds `session_changed` (`tests/room/test_agents.py`).

## Switch message ids (M3, `evidence/solo-csv-export-20261104T210641.log`)

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

## Demo video

Not recorded yet; its SHA-256 goes here.

## Outside the checked scope

- K3, Slack rendering of the approval card: not run; it needs the lead's Slack login.
- Two machines live (author and reviewer on different laptops): not run.
- PR data (title, body, changed files, check runs) comes from each case's `case.json`; there is no GitHub API reader yet.
- All sessions and repos in `fixtures/` and `examples/` are synthetic.
  Real Claude Code sessions were sealed only for G4, G6 and G7 (M1 evidence log).
- reviewer-agent's room rule admits every person in its own `#pr-<n>` room (`users: "*"`): Switch matches people by a member client id that the gateway does not expose.
  Only the author and the reviewer are members, and reviewer-agent acts only on answers from the PR author's sender id.
- `make replay` used the already-running local server, not a fresh one.

`evidence/solo-all-20261104T221502.log` passed 9/9 but is not gate evidence.
It started after the C14 fix and before C15 and the `PreToolUse:` prefix, and the fixtures were regenerated while it ran.
The two runs above use the committed code.
