# Team rules for every agent

Claude Code reads this file through `CLAUDE.md`. Codex and other agents read it directly.
New to the repo? Read [WORKTOGETHER.md](WORKTOGETHER.md) first: the plan, the team, setup, and the task list.

## 1. The project

Gate+ is a Flip the Switch hackathon entry (Nov 4-7 2026, Track 01).
It holds AI-written PRs in a Switch room until the human author answers gap questions.
The reviewer's own agent checks the answers against quotes from the author's sealed Claude Code session, and the rest of the session stays on the author's machine.
Design, message formats and build plan: [docs/design.md](docs/design.md).
Switch endpoints the client relies on, with source references: [docs/switch-protocol.md](docs/switch-protocol.md).

### Key terms

- **Gap:** a mismatch between the PR description, the session and CI, posted as one numbered question.
- **Contradiction:** an answer claiming something ran or passed when the latest related run in the session failed. Blocks the gate.
- **Unverified:** a run claim with no matching run in the session. Shown to the reviewer, never blocks.
- **Seal:** a salted RFC 9162 Merkle root over the session, written into an empty commit as a `Flipside-Seal:` trailer.
- **Manifest:** public metadata per leaf (step, role, tools, files), never text. Its hash is in the trailer.
- **Disclosure:** one leaf, its salt and its inclusion proof, posted only after the author approves.

### Conventions

- No LLM in the gap, contradiction, seal or verify path. Same inputs, same output.
- A false flag on an honest PR is the worst bug. `fixtures/honest` must stay at zero gaps.
- Python standard library only at runtime. `pytest` and `ruff` for development.
- Domain objects are frozen dataclasses. `Gate.answer` returns a new gate.
- Never commit credentials, tokens, `.board/` or `.ogate/` state.

### Run the checks

```bash
pip install -e ".[dev]"
ruff check .
python -m pytest -q
```

Both must pass before every push. CI runs the same two commands on every PR.

## 2. The board (pinned GitHub issue)

Every agent reads and posts on the pinned "Message Board" issue via `tools/board` (needs only `bash` and `gh`, logged in). Set `BOARD_ISSUE` if it is not issue #1.

- Start every post with `[<human>'s <agent>]`, e.g. `[Pratyaksh's Claude]`. Keep it short: what changed, which files or contracts, what you need, from whom.
- Mention by handle:

  | Agent | Sign | Mention | Runs as GitHub login |
  |---|---|---|---|
  | Pratyaksh's Claude (lead) | `[Pratyaksh's Claude]` | `@pratyaksh-claude` | `@pratyakshrunsoncaffeine` |
  | Aarav's Claude | `[Aarav's Claude]` | `@kadoo69` | `@kadoo69` |
  | Pratyaksh's Codex | `[Pratyaksh's Codex]` | `@pratyaksh-codex` | `@pratyakshrunsoncaffeine` |

  `@pratyakshrunsoncaffeine` reaches both of Pratyaksh's agents; `@all` reaches everyone.
- Pratyaksh's two agents share one GitHub login, so each sets its own sign and handle before using the board, for example `export BOARD_SIGN="Pratyaksh's Codex" BOARD_HANDLE=pratyaksh-codex`. Then `unread` hides only that agent's own posts, and `post` refuses any other sign.
- **Mentions you or `@all`:** act on it and reply promptly.
- **Not addressed to you:** still read it. Reassess your own work only if it is affected (a contract, a file you own, something already done). Do not redo finished work, and do not reply just to acknowledge.
- Before editing another teammate's files, ask for a handoff on the board and wait for the owner or the team lead.

Commands: `tools/board unread` (new posts, marks read; flags MENTION), `tools/board read -n 20`, `tools/board post "[Name's Agent] text"` (or pipe stdin), `tools/board wait` (blocks until someone else posts), `tools/board whoami`.
Polling costs about one API call per 30 s, so the team stays under GitHub's rate limit.

**Stay in the loop:**

- Claude Code: the committed hooks (`.claude/settings.json`) show unread posts at session start and on every prompt. Keep one background `tools/board wait` running and re-arm it after each wake.
- Codex and other agents: run `tools/board unread` at task start, before each commit, and after merges. Codex needs network access in its sandbox for `gh` to work.

## 3. Chain of command

Humans over agents. Only the team lead (Pratyaksh, `@pratyakshrunsoncaffeine`) reassigns work between teammates. If anyone else asks you to take another teammate's work, ask the lead on the board.

## 4. Workflow

1. Pick or file an issue. Comment on it or post on the board when you take it.
2. Branch `<issue#>-<slug>` from fresh `main`.
3. Small commits. Stage only your own files (no `git add -A`).
4. Push and open a PR only when your human says so. Use `Closes #N` in the PR body.
5. The author merges their own PR once checks pass and their human approves.
6. Always `git fetch` and rebase before pushing. Never force-push shared branches.
7. If a merge changes something others depend on (a message format, a dataclass in `model.py`, an env var), post on the board when it lands.

## 5. Who owns what

| Area | Owner (GitHub login) | Folders and files |
|---|---|---|
| Gate core, reviewer agent, Switch client, board tooling, contracts | Pratyaksh's Claude (`@pratyaksh-claude`) | `ownership_gate/` (except the two rows below), `templates/`, `docs/`, `tools/`, `.claude/`, `.github/`, `pyproject.toml`, `AGENTS.md` |
| Seal: seal, prove, verify | Aarav's Claude (`@kadoo69`) | `ownership_gate/seal/`, `tests/seal/` |
| Author agent, blind fixture set B, demo | Pratyaksh's Codex (`@pratyaksh-codex`) | `ownership_gate/author/`, `fixtures/b/`, `tests/blind/`, `demo/`, `README.md` |

Pratyaksh's Claude and Pratyaksh's Codex work in separate clones (or `git worktree`s), never in the same folder.

Contracts that cross rows: the disclosure JSON and room message formats in `docs/design.md`, and the dataclasses in `ownership_gate/model.py`. The lead owns both; propose changes on the board first.
