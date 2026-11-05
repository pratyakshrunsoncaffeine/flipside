# Judging Flipside

This page is a short path through the repo for the four judging criteria.
Every claim links to a command you can run or a log from a real run.
All fixtures are synthetic.

## Two minutes

1. Watch the film: [`site/media/flipside-film.mp4`](site/media/flipside-film.mp4) (65 s).
2. Read "What the reviewer sees" in the [README](README.md#what-the-reviewer-sees): one PR, one question, one approved quote, and two refused attempts to pull the whole session.
3. Open `site/index.html` in a browser to play back a recorded run message by message.

## Ten minutes: reproduce it

Needs Git, Python 3.12 and [uv](https://docs.astral.sh/uv/); no accounts, keys or network after `uv sync`.

```
uv sync --frozen
make g8
make replay-offline
```

`make g8` checks two disclosures against the seal in `examples/`:

```
OK leaf 5 (session 0, step 5, chunk 0) against seal ae44db8 in commit 5db0364
PROOF_FAIL leaf 5 does not hash up to root ae44db8
```

The second file differs from the first by one edited word; its exit code is 2.
`make replay-offline` plays the whole review and ends with `RESULT PASS csv-export (offline, 5 rounds)`, after listing each refusal it saw.

With Docker, `make demo` runs the same review on a real Switch 0.31.0 server with Mattermost, both people acting as their own Mattermost accounts.
It is checked on macOS and in CI on Ubuntu (the `demo` job in [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).
Without make on Windows, use the PowerShell block in [docs/RUNNING.md](docs/RUNNING.md#without-make-windows-powershell).
To check a quote with no install at all, open `site/verify.html` and press "Try synthetic example", then "Edit sample quote" to see a one-word edit fail.
The page runs the proof checks in the browser; the Git checks still need `flip verify`.

## Use of Switch

Flipside needs a server that two owners share and that enforces each owner's rules on the other's people and agents.
That server is Switch.

| What Switch does in the review | Without it | Evidence |
|---|---|---|
| author-agent's scoped addressing policy: only its owner, the owner's agents and reviewer-agent may address it, and only in `#pr-<n>` | the reviewer can command author-agent directly | K4 (6/6), [`evidence/k4-20261104T202125.log`](evidence/k4-20261104T202125.log); refusal 1 in every run |
| Approval cards that only an addresser can answer | the reviewer can approve their own request | K2, [`evidence/k1k2-20261104T195815.log`](evidence/k1k2-20261104T195815.log); refusal 4 (HTTP 403) |
| Each room belongs to the person who made it | the reviewer can rewrite the author's private room | K5 (8/8), [`evidence/k5-20261105T153338.log`](evidence/k5-20261105T153338.log) |
| A person claims their Mattermost account in Switch | anyone in the channel can press the author's card | K5, `make demo` |

`make replay-offline` runs on `FakeSwitch`, an in-process copy of what K1, K2 and K4 measured on a real server.
It holds both owners' keys in one process, so it shows the flow, not the two-owner boundary; the live logs show the boundary.

## Technical execution

| Claim | Evidence |
|---|---|
| Seal, prove and verify follow a written spec with pinned vectors | [`docs/seal/SPEC.md`](docs/seal/SPEC.md), `make test`, [`evidence/m1-20261104T201854.log`](evidence/m1-20261104T201854.log) |
| The whole review on real Switch and Mattermost | [`evidence/demo-mattermost-csv-export-20261105T131047.log`](evidence/demo-mattermost-csv-export-20261105T131047.log), CI job `demo` |
| Author and reviewer on two machines (Mac author with Switch, Windows reviewer, private tailnet) | [`evidence/m2-author-20261105T172923.log`](evidence/m2-author-20261105T172923.log), [`evidence/m2-reviewer-20261105T172644.log`](evidence/m2-reviewer-20261105T172644.log) |
| A clean clone on a second OS reproduces the verdicts | [`evidence/m4-20261105T002230.log`](evidence/m4-20261105T002230.log), [`evidence/replay-switch-csv-export-20261105T015811.log`](evidence/replay-switch-csv-export-20261105T015811.log) |
| A real Claude Code session and a real sealed GitHub PR | [`evidence/real-session-20261104T224823.log`](evidence/real-session-20261104T224823.log), [`evidence/github-pr-20261105T002706.log`](evidence/github-pr-20261105T002706.log) |
| No model decides anything | No LLM call in `flipside/`; seal, gaps, coverage and verdicts are standard-library Python |

CI runs lint, mypy, the tests, `make g8`, the offline replay and the fixtures on Ubuntu and Windows, plus `make demo` on Ubuntu.
Every log is listed in [VERIFICATION.md](VERIFICATION.md).

## Creativity and impact

Tests and model reviewers check what a change does.
Flipside asks why it was made and checks the answer against the agent session that made it, while the author keeps the session.
The case it is built for: one team's agent writes a PR into code another team owns, and the owners need the reason behind a change the PR description does not mention.

## What it does not prove

These are the limits judges raised most often in our blind runs; the full list is in the [README](README.md#limits).

- **The seal is not proof of honesty.** It proves that every quote was in the session sealed before review began.
  A session forged before sealing is not caught, and work done outside the agent has no session, which the `UNSEALED` gap asks about.
- **A requested chunk reaches the Switch server before the author decides.** The approval card shows the exact text in the author's private room, so whoever runs the server can read it.
  In the two-machine run, Switch ran on the author's own Mac.
  Only approved chunks reach the reviewer's room.
- **The manifest is public.** It lists step counts, roles, tool names, repo paths and test outcomes, never session text.
- **Setup is real work.** Each side runs `flip setup` with its own Switch login and swaps one join line.
  Sessions are Claude Code JSONL only.
  We have not measured time saved for a real team.
