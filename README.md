# Ownership Gate

Your colleague sends you 2,000 lines of AI-written code and says the tests pass.
The AI's own log says they never ran.

Ownership Gate is a Switch room that holds an AI-written pull request until its human author has answered for it, on the record, and checks those answers against what the author's own coding agent actually did.
The reviewer is paged only when no contradiction is left.

Built for Flip the Switch (Track 01, Best Business Workflow).

## The problem

"Today I announced that I won't be reviewing AI generated PRs" (r/ExperiencedDevs, 1,560 upvotes, May 2026): data scientists sent Claude Code PRs to web developers, the code looked plausible, and bugs slipped through.
The thread's answer was ownership: "If you submit it, you own it."
More sources are in [docs/sources.md](docs/sources.md).

## How it works

1. The author codes with Claude Code and [Entire](https://github.com/entireio/cli), with sessions kept local (`entire configure --local --skip-push-sessions`).
2. The author's gate agent, running on their machine, polls GitHub for their open PRs (Switch has no webhook intake) and opens one Switch room per PR from [templates/pr-room.yaml](templates/pr-room.yaml).
3. A deterministic checker (no LLM) compares the PR description, the session and CI, and posts at most 5 numbered questions:
   - a test, lint or build command that failed and was never rerun, citing the step;
   - "tests pass" claimed, but no test ran in the session;
   - a command named in the PR body with no passing run;
   - failing CI, or tests claimed with no CI report;
   - a changed file that no prompt and no part of the PR description mentions;
   - a PR over the size limit (400 changed lines, lockfiles excluded).
4. A PR with no linked session gets a **No trail** badge; CI and size checks still run.
5. Only the author answers, in their own words, starting each answer with its number (`1: ...` or `Q1.`).
   Unnumbered chat is not taken as an answer; the gate replies with a hint.
   Every revision stays in the room, including revisions after the reviewer was paged.
6. A command that never executed (the tool call was rejected, denied or interrupted) counts as no run, not as a failure.
7. Each answer is checked against the session. "I tested the migration" when step 6 shows `pytest tests/migrations` failed is posted as a contradiction with the cited step. A claim with no matching run is marked unverified, not blocked.
8. When no contradiction is left, the reviewer gets one brief: questions, final answers, revision counts, unverified claims, and any gaps beyond the five asked.

The transcript never leaves the author's machine.
Only the gate's questions and findings reach the room.

## Try it in one minute (no Switch, no keys)

```bash
python -m pip install -e .
ogate demo fixtures/migration-claim
```

Other scenarios: `fixtures/honest` (zero flags), `fixtures/claimed-command`, `fixtures/no-trail`.
Check one PR without the room:

```bash
ogate check --pr-json fixtures/migration-claim/pr.json --transcript fixtures/migration-claim/full.jsonl
```

`ogate check --github OWNER/REPO#N --repo-dir .` reads a real PR and the Entire checkpoints in a local clone.
It exits 1 when there are gaps.

Record a run with `--record events.jsonl`, then `ogate replay events.jsonl` prints it, or `ogate replay events.jsonl --room-id <id>` posts it into a Switch room.

## Run it live in Switch

Needs a local Switch v0.9 (Docker for Postgres and Mattermost; see Switch's `docs/old/LOCAL_DEVELOPMENT.md`: `just init-env`, `just up`, `just migrate`, `just run`).

```bash
export SWITCH_TOKEN=<your personal API key from the Switch dashboard>
python scripts/register_agent.py --url http://localhost:8000 --name dana-gate
```

Paste the printed `export` lines, set the agent's addressing policy to **owner** in the Switch dashboard, then:

```bash
ogate run --repo acme/shop --author dana --chat-user dana --reviewer-chat sam --repo-dir ~/code/shop
```

`GITHUB_TOKEN` is optional for public repositories.
How the client talks to Switch is in [docs/switch-protocol.md](docs/switch-protocol.md).

## What it can and cannot claim

- It checks every claim in the PR against the session and CI before a reviewer spends a minute.
- It catches false statements about what ran, with the step that shows it.
- It cannot prove a human typed an answer: an author can paste the questions into an AI.
- It cannot see work done outside the agent; such claims show as unverified.
- It covers Claude Code transcripts today. Codex sessions need their own parser.

## Status of this draft

Built and tested offline: transcript parsing, gap checker, contradiction checker, gate state, chat text, GitHub and Entire readers, scenario demo, replay.
Written against Switch's source but not yet run against a live server: `switch_client.py`, `live.py`, `templates/pr-room.yaml`.
The live agent resumes its event stream after a drop (`Last-Event-ID`), reconnects with backoff, and retries a PR whose room or opening post failed.
Gate state survives a restart: open gates are rebuilt from `gates.json` and `events.jsonl` in the state directory without posting again, and the stream resumes from `cursor.txt`.

## Develop

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
```

`tests/test_e2e_scenarios.py` plays every fixture through the CLI.
Fixture set A is generated by `python -m scripts.make_fixtures`; a blind set B, written by a teammate from real sessions, is still to come.
The next step, sealed evidence checked by the reviewer's own agent, is specified in [docs/design.md](docs/design.md).

## How the team works

Each teammate's coding agent (two Claude Code, one Codex) coordinates on one pinned GitHub issue through `tools/board`, a small `gh` wrapper.
Rules, the board protocol and the folder owner table are in [AGENTS.md](AGENTS.md).
The board script, hooks and issue template come from [hackathon-agent-board](https://github.com/azizu06/hackathon-agent-board).
