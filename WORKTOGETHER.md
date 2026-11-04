# Gate+: start here

You are one of three coding agents building **Gate+** for the Flip the Switch hackathon.
Read this whole file before you do anything, then do section 4 ("Your first 15 minutes").
It tells you what we are building, who does what, how we talk, and what to build first.

Repo: `https://github.com/pratyakshrunsoncaffeine/gateplus` (private).
Deeper references inside the repo: [AGENTS.md](AGENTS.md) (rules, always loaded), [docs/design.md](docs/design.md) (full design and contracts), [docs/switch-protocol.md](docs/switch-protocol.md) (Switch API we rely on), [README.md](README.md) (what v1 does today).

## 1. What we are building

### The problem

Reviewers are drowning in AI-written pull requests the author cannot explain.
"Today I announced that I won't be reviewing AI generated PRs" (r/ExperiencedDevs, 1,560 upvotes, May 2026): the code looked plausible, bugs slipped through, and the thread's answer was "if you submit it, you own it".
More verified sources: [docs/sources.md](docs/sources.md). We only use problems backed by outside sources; never invent evidence.

### The product

Gate+ holds an AI-written PR in a Switch room until its human author has answered for it, and checks those answers against what the author's own coding agent actually did.

1. Before opening the PR, the author **seals** their Claude Code session: every message is hashed into a salted Merkle tree, and the 32-byte root goes into an empty git commit as a `Flipside-Seal:` trailer. The session itself stays on the author's laptop.
2. The **reviewer's own agent** opens a Switch room for the PR, reads the public manifest (metadata per step, never text), and posts numbered **gap** questions: things the PR description, the diff, CI and the session's metadata do not agree on.
3. The author answers in their own words.
4. Where an answer leans on the session ("the tests passed"), the reviewer's agent asks to see specific steps by index. The author approves, and the author's agent posts each step with an inclusion proof.
5. The reviewer's agent verifies every proof against the sealed root, checks the claim against the disclosed bytes, counts what was withheld, and pages the human reviewer only when no contradiction is left.

Why it needs Switch: two owners' agents on two sides, with private evidence on one side and verification on the other. The room is the only place they meet, and its timestamps are the independent record.

### The hackathon

- Flip the Switch (WeMakeDevs, DevTools Academy, Switch). Online, Nov 4 00:01 to Nov 7 23:59 IST. We enter Track 01, Best Business Workflow.
- Judging: (1) Use of Switch: "would the project stop working without it?"; (2) technical execution: judges clone and reproduce; (3) creativity and impact; (4) presentation: demo video and README.
- The Switch setup and the workflow must be built during the event. Existing libraries and agents are allowed.
- **Our internal deadline: submit by Nov 7 18:00 IST.**

## 2. The team

| Human | Agent | Sign every post with | Mention as | GitHub login | Owns |
|---|---|---|---|---|---|
| Pratyaksh (lead) | Claude Code | `[Pratyaksh's Claude]` | `@pratyaksh-claude` | `pratyakshrunsoncaffeine` | Gate core, reviewer agent, Switch, contracts, repo tooling |
| Aarav | Claude Code | `[Aarav's Claude]` | `@kadoo69` | `kadoo69` | The seal: seal, prove, verify |
| Pratyaksh | Codex | `[Pratyaksh's Codex]` | `@pratyaksh-codex` | `pratyakshrunsoncaffeine` | Author agent, blind fixture set B, demo |

Exact folders per owner are in the owner table in [AGENTS.md](AGENTS.md) section 5.
Edit only your own folders. To change someone else's file, ask on the board and wait for the owner or the lead.
Humans over agents. Only Pratyaksh reassigns work.

## 3. How we work together

### The board

All coordination happens on one pinned GitHub issue, the **Message Board** (issue #1), through `tools/board` (bash plus the GitHub CLI).

- `tools/board unread`: new posts since you last checked; posts that mention you are flagged `** MENTION **`.
- `tools/board post "[Your Sign] text"`: post. Say what changed, which files or contracts, what you need, from whom. Short.
- `tools/board wait`: blocks until someone else posts. Claude Code keeps one running in the background and re-arms it after each wake.
- `tools/board read -n 20`: the last 20 posts.

Rules:

- A post that mentions you or `@all`: act on it and reply on the board.
- A post not addressed to you: read it, change course only if it affects something you own. Never reply just to acknowledge.
- Post when you start a task, when you finish one, when you change a contract, and when you are blocked.

Example handoff:

```text
[Aarav's Claude] merkle.py and canon.py are on main (PR #4). @pratyaksh-claude the Disclosure dataclass is in ownership_gate/seal/model.py; please review before I build verify on it.
[Pratyaksh's Claude] @kadoo69 looks right. One change: add `commit` to Disclosure. Approved after that.
```

### Git workflow

1. Take a task from section 6. Open a GitHub issue for it (title = task id and name) and post on the board that you took it.
2. Branch `<issue#>-<slug>` from fresh `main`.
3. Small commits. Stage only your own files, never `git add -A`.
4. Before pushing: `ruff check .` and `python -m pytest -q` both pass.
5. **Push, open a PR, or merge only when your human says so.** Ask them first, every time.
6. PR body says `Closes #N` and fills the template. The author merges their own PR once CI is green and their human approves.
7. `git fetch` and rebase before pushing. Never force-push shared branches.
8. When a merge changes something others use (a message format, a dataclass, an env var), post on the board.

## 4. Your first 15 minutes

Do these in order. Ask your human for anything that needs a login or an install.

1. **Clone into your own folder.** Pratyaksh's Claude and Pratyaksh's Codex use separate clones, never the same folder.
   ```bash
   gh repo clone pratyakshrunsoncaffeine/gateplus gateplus-<your-handle>
   cd gateplus-<your-handle>
   ```
2. **Check GitHub access.** `gh auth status` must show a logged-in account. If not, ask your human to run `gh auth login`. Aarav must accept the repo invite first.
3. **Set your sign and handle** so the board knows which agent you are (required for Pratyaksh's two agents, harmless for Aarav's):
   - Claude Code: create `.claude/settings.local.json` (git-ignored):
     ```json
     { "env": { "BOARD_SIGN": "Pratyaksh's Claude", "BOARD_HANDLE": "pratyaksh-claude" } }
     ```
     Aarav uses `"Aarav's Claude"` and `"kadoo69"`. Restart the session after creating it.
   - Codex: start Codex from a shell where both are set, for example in bash `export BOARD_SIGN="Pratyaksh's Codex" BOARD_HANDLE=pratyaksh-codex`, or in PowerShell `$env:BOARD_SIGN="Pratyaksh's Codex"; $env:BOARD_HANDLE="pratyaksh-codex"`. Codex needs network access in its sandbox for `gh`, and on Windows it runs `tools/board` through Git Bash.
4. **Install and test.** Python 3.11 or later.
   ```bash
   python -m pip install -e ".[dev]"
   ruff check .
   python -m pytest -q
   ```
   Everything must pass before you change anything. If it does not, post the failure on the board.
5. **Check the board.** `tools/board whoami`, then `tools/board read -n 20`.
6. **Say hello and claim your first task.** Post one line, for example:
   `[Aarav's Claude] set up, 160 tests pass. Taking S1 (canon + merkle).`
7. Claude Code only: start `tools/board wait` in the background now and keep one running.

## 5. Architecture in one page

The side that benefits from a check runs it.

```text
Author's machine (owner A)          Switch room #pr-<n>                 Reviewer's machine (owner B)
  Claude Code session (private)       1 seal line + manifest file   <-   gate-reviewer agent
  flip seal  -> root in git trailer   2 numbered gap questions      <-     gaps from PR, diff, CI, manifest
  flip prove -> leaf + salt + proof   3 author answers "1: ..."     ->     request leaves by index
  gate-author agent                ->  4 "show leaves 41, 57"        <-     flip verify (7 checks) + coverage
                                      5 author: approve 41 57       ->     claim vs disclosed bytes
                                      6 disclosures                 ->     brief, then page the reviewer
                                      7 verdicts, brief             <-
GitHub: PR, diff, CI, empty seal commit with "Flipside-Seal: v1 root=... n=... manifest=..."
```

- Everything is deterministic Python, standard library only. No LLM decides a gap, a contradiction or a proof.
- Seal construction, the six fixes to the original seal spec (F1 to F6), test vectors, room message formats and the verify codes are in [docs/design.md](docs/design.md) sections 3 to 5. Those are the contracts; follow them exactly.
- What exists today (v1, 160 tests): transcript parsing, gap checker, contradiction checker, gate state, chat rendering, GitHub and Entire readers, a Switch client with stream resume, the live loop, replay, and the board tooling. v1 runs the gate on the author's side; Gate+ moves it to the reviewer's side (design.md section 1).
- Not done: nothing has run against a live Switch server yet (needs Docker); no seal code; no author agent; no blind fixtures.

## 6. Tasks

Take tasks in order within your row. "Needs" means wait for that task's PR to merge, or build against a fake until it does.

### Aarav's Claude: the seal (`ownership_gate/seal/`, `tests/seal/`)

| Id | Task | Done when | Needs |
|---|---|---|---|
| S1 | `canon.py` (canonical JSON) and `merkle.py` (RFC 9162 tree hash, inclusion proof, verify) | Proofs verify for every leaf of every tree size 1 to 256; flipping any bit of a sibling, the index, n or the root fails | nothing, start now |
| S2 | `model.py` in the seal folder: `Leaf`, `ManifestEntry`, `Seal`, `Disclosure` frozen dataclasses with JSON in and out. Post them on the board for review | Lead approves on the board | S1 |
| S3 | `steps.py`: Claude Code JSONL to steps to chunks, built on `ownership_gate/transcript.py`, with F2 (`mentions`), F3 (sidechains), F6 (`cmd`, `ok`) | The three test vectors in design.md reproduce byte for byte; a real session parses | S2 |
| S4 | `seal.py`: key under `.git/flipside/`, salts, manifest, trailer on an empty commit | Sealing the same session twice with the same key gives the same root | S3 |
| S5 | `prove.py` with F1 (sealed byte prefix) and `verify.py` with the 7 codes plus coverage | An edited quote gives PROOF_FAIL, a re-seal after the question gives WRONG_COMMIT, an edited session gives SESSION_CHANGED, all in a real git repo in a test | S4 |
| S6 | `python -m ownership_gate.seal seal|prove|verify` entry point in your folder; post when ready so the lead wires it into `cli.py` | Commands work from a clean clone | S5 |

### Pratyaksh's Claude: gate core, reviewer agent, Switch (lead)

| Id | Task | Done when | Needs |
|---|---|---|---|
| L1 | With Pratyaksh: install Docker, bring up Switch, register two Switch users with one agent each; write the steps in `docs/switch-setup.md` | Each owner's agent posts one message in one room | Docker installed by Pratyaksh |
| L2 | `SessionView` protocol so `gaps.py` runs on either the full session or the manifest | v1 tests still pass; `fixtures/honest` still gives zero gaps | S2 |
| L3 | `switch_client.upload_media` / `download_media`; reviewer-side loop (`reviewer_live.py`) with request, approve, disclosure and verdict messages | Offline replay with two fake agents takes the CSV-export scenario from seal to brief | L2, S5 |
| L4 | Wire `seal` into `cli.py`; review every PR that touches a contract | `ogate seal|prove|verify` work | S6 |
| L5 | Live two-owner run (Nov 6) | One real PR goes from seal to brief in a live room | L1, L3, C2 |

### Pratyaksh's Codex: author agent, blind fixtures, demo

| Id | Task | Done when | Needs |
|---|---|---|---|
| C1 | Blind fixture set B in `fixtures/b/` with `tests/blind/`. Write each scenario's expected gaps by hand **before** reading `gaps.py` or `contradictions.py` (that is what makes it blind). Copy the file layout from `fixtures/honest/` (`pr.json`, `full.jsonl`, `answers.json`). At least 3 honest PRs and 3 with real gaps, built from real Claude Code sessions with secrets removed | Tests run the CLI on each fixture and compare with the hand-written expectations; report misses on the board, do not change the rules yourself | nothing, start now |
| C2 | `ownership_gate/author/author_live.py`: the gate-author agent. Uploads the manifest, listens for requests, asks the author `approve` / `withhold`, runs `prove`, posts disclosures. Use a fake Switch client until L3 lands (see `tests/test_live.py` for the fake pattern) | Offline test: request in, approval in, verified disclosure out | S5 for real proofs; message formats from design.md section 4 |
| C3 | `demo/`: the CSV-export scenario as a tiny repo plus a replay script that runs the whole flow offline in one command | A judge can run it from a clean clone with no keys | L3, C2 |
| C4 | Nov 7: demo video script (3 minutes, design.md demo order) and README update for Gate+ | Pratyaksh approves | everything else |

## 7. Timeline and kill rules (IST)

| When | Goal |
|---|---|
| Nov 5 morning | S1 to S3, C1 started, L1 done if Docker is in |
| Nov 5 18:00 | **Checkpoint.** Seal checks (S1 to S5) green? Live Switch up? |
| Nov 6 | L3, C2, C3; live two-owner run (L5) |
| Nov 7 12:00 | Feature freeze. Only fixes, docs, video |
| Nov 7 18:00 | Submitted |

- Seal checks not green by Nov 5 18:00: ship Gate two-owner without the seal.
- No live Switch by Nov 5 18:00: ship the offline replay demo.
- Never stop the test suite from passing on `main`.

## 8. Rules that are easy to break

- A false gap on an honest PR is the worst bug we can ship. `fixtures/honest` must stay at zero gaps.
- No LLM in the gap, contradiction, seal or verify path. Same input, same output.
- Runtime code uses the Python standard library only.
- Never commit credentials, tokens, session files with secrets, `.board/`, `.ogate/` or `.claude/settings.local.json`.
- Never invent problem evidence or test results. Report what actually ran.
- Ask your human before every push, PR, merge or GitHub change.
- Do not edit another owner's files without a handoff on the board.

## 9. When you are stuck

1. Re-read [docs/design.md](docs/design.md) for the contract.
2. Post on the board: what you tried, the exact error, and who you need (`@pratyaksh-claude` for contracts and Switch, `@kadoo69` for the seal, `@pratyaksh-codex` for the author agent and fixtures).
3. Keep working on another task in your row while you wait.
