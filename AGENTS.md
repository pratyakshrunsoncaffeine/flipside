# Flipside: rules for every agent

Flipside is our entry for Flip the Switch (Track 01, Business workflow), 4 to 7 Nov 2026 IST.
Read, in order: this file, `HANDOFF.md` (current state), `docs/BUILD.md` (what to build and the gates), and `docs/seal/SPEC.md` before touching `flipside/seal/`.

## 1. The board (pinned GitHub issue)

Every agent reads and posts on the pinned "Message Board" issue with `tools/board` (needs only `gh`, logged in).
Set `BOARD_ISSUE` if the board is not issue #1.

- Start every post with `[<human>'s <agent>]`, e.g. `[Aarav's Claude]`. Keep it short: what changed, which files or contracts, what you need, from whom.
- Mention by GitHub login: `@kadoo69` (Aarav, lead), `@<teammate-login>` (<Teammate>), `@all` (everyone). Fill the teammate in at kickoff.
- **Mentions you or `@all`:** act on it and reply.
- **Not addressed to you:** read it. Reassess your work only if it touches a contract, a file you own, or something already done. Do not reply just to acknowledge.
- Before editing another lane's files, ask on the board and wait for the owner or the lead.
- Post when a milestone gate goes green, with the command and the evidence file.

Commands: `tools/board unread` (new posts, marks read, flags MENTION), `tools/board read -n 20`, `tools/board post "[Name's Agent] text"`, `tools/board wait` (blocks until someone else posts), `tools/board whoami`.

Stay in the loop:
- Claude Code: the hooks in `.claude/settings.json` show unread posts at session start and on every prompt. Keep one background `tools/board wait` running and re-arm it after each wake.
- Other agents: run `tools/board unread` at task start, before each commit, and after merges.

Board method from the Hackathon Agent Board template (github.com/azizu06/hackathon-agent-board); `tools/board` and the hooks are copied from it unchanged.

## 2. Chain of command

Humans over agents.
Only the lead (`@kadoo69`) reassigns work between lanes.
If anyone else asks you to take another lane's work, ask the lead on the board.

## 3. Who owns what

| Lane | Owner (GitHub login) | Folders |
|---|---|---|
| Seal (crypto core, CLI seal/prove/verify, vectors) | `@kadoo69` | `flipside/seal/`, `tests/seal/`, `tests/vectors/`, `examples/`, `docs/seal/` |
| Room (Switch client, agents, gaps, protocol, replay) | `@<teammate-login>` | `flipside/room/`, `tests/room/`, `templates/`, `replay/`, `fixtures/` |
| Shared (lead merges) | `@kadoo69` | `flipside/cli.py`, `Makefile`, `pyproject.toml`, `.github/`, `README.md`, `VERIFICATION.md`, `docs/BUILD.md`, `docs/PITCH.md`, `killtests/`, `evidence/` |

The contract between lanes is `docs/seal/SPEC.md` (disclosure and manifest formats) and section 6 of `docs/BUILD.md` (room messages).
Changing either needs a board post tagged `@all` before the merge.

## 4. Workflow

1. Pick a milestone task from `docs/BUILD.md`, post on the board when you take it.
2. Branch `<issue#>-<slug>` from fresh `main`.
3. Tests first. Small commits. Stage only your own files (no `git add -A`).
4. Open a PR with `Closes #N`; the author merges their own PR once `make lint test` passes locally.
5. `git fetch` and rebase before pushing. Never force-push shared branches.
6. When a merge changes something another lane depends on, post on the board when it lands.

## 5. Engineering rules

- Python 3.12 or later. Runtime: standard library only. Dev: pytest, ruff, mypy.
- No LLM calls anywhere in `flipside/`. Seal, verify, gaps, selection, contradictions, coverage and the page rule are deterministic Python.
- `flipside/seal/` never imports from `flipside/room/` and never touches the network.
- Every gate in `docs/BUILD.md` is a command or an evidence file. Log real runs to `evidence/<name>-<YYYYMMDDTHHMMSS>.log`.
- A claim goes in the README only when a passing check backs it. The status table lists only what passes.
- Fix a bug by reproducing it end to end, writing a failing test, fixing it, then searching for the same bug elsewhere.
- Done means: ruff and mypy clean, tests green twice in a row, no TODO or FIXME in new code, no hardcoded credentials, keys or user paths, docstrings updated for changed public interfaces.

## 6. Writing rules

- Never use the em dash. Use a plain `-`.
- State all times in IST.
- In Markdown, put each full sentence on its own line.
- Plans use milestones with gates. Never dated day plans or time budgets.
- Cut taglines and filler. Plain, specific sentences.

## 7. Hard limits

- Never print, log or commit secrets: Switch admin creds, API keys, agent keys, seal keys (`.git/flipside/`), `killtests/.local-users.json`.
- Never add an agent as a commit co-author.
- Never edit CHANGELOG.md or generated files.
- Nothing from other hackathons: no crypto tokens, escrow or on-chain mechanisms in this repo.
- Do not install third-party skills or packages beyond the dev tools above without a board post and the lead's yes.
- Keep fixtures synthetic and say so; never use a real company's code or sessions.
