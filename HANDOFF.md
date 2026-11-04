# Handoff

Updated 4 Nov 2026, 22:15 IST.
Load first: `AGENTS.md`, this file, `docs/BUILD.md` (gates, protocol, Switch facts in section 9), `docs/seal/SPEC.md` before touching `flipside/seal/`, `VERIFICATION.md` (evidence).
Skills: `pr-protocol` before branching or opening a PR; `handoff` to update this file.

## Goal

Win Flip the Switch Track 01 (deadline 7 Nov 2026, 23:59 IST) with Flipside: the owning team questions the author team's private coding-agent session through Switch and verifies every quote against a Merkle root sealed into the PR.

## State

Done (all green; evidence in `evidence/`, details in `VERIFICATION.md`):
- M0 shared files; K1/K2 9/9, K4 6/6 (`make killtests`).
- M1 seal core, gates G1 to G8 (`evidence/m1-20261104T201854.log`).
- M2 offline room flow with the four refusals (`make replay-offline`); 8 synthetic fixtures, `make fixtures` 8/8, 0 false approvals, 0 false flags.
- M3 live on local Switch: each agent runs as its own process (`flip agent`); `make solo` kills both with SIGKILL mid-flow and restarts them, with 0 duplicate posts and the four refusals live.
- `make solo-all`: all 8 fixtures live, 8/8 twice (`evidence/solo-all-20261104T214727.log`, `evidence/solo-all-20261104T215327.log`).
- M4 on this machine: `make replay` PASS; a clean local clone passes lint, tests, G8, offline replay and fixtures.
- M5: `.github/workflows/ci.yml` (Ubuntu, macOS), `VERIFICATION.md`.
- M6 part: `README.md` (passing claims only, a real-PR quick start, full limits), `docs/PITCH.md` rewritten to the built design.
- GitHub PR reader `flipside/room/github.py` (gh api), tested on canned data and one public PR.
- 241 tests pass twice; ruff and mypy strict clean.
- Everything is committed except this file.

Not started or blocked:
- GitHub repo, board issue, CI on GitHub: waiting for the teammate (no invite yet, checked at 21:20 IST).
- M4 second-machine clean clone (the teammate).
- K3 Slack card: needs the lead's Slack login.
- A chat window for people: the local server has none without Docker; the bundled Mattermost needs Docker (Docker.app is installed) and a restart of the local server from Console. The lead decides.
- Demo video (at most 2.5 minutes, BUILD section 11) and its SHA-256. Tools exist locally: ffmpeg, macOS `say`, Playwright's Chromium in `~/Library/Caches/ms-playwright`.
- Final judge run on the README (`docs/judging/`), then submission.
- The GitHub reader has not run end to end on a sealed PR.

## Decisions

| Decision | Reason |
|---|---|
| Flipside over Treaty | Higher judge scores; uncrowded mechanism (`docs/judging/SCORES.md`) |
| Deterministic gaps; the reviewer names leaves; the author answers in their own words | No LLM decides any path; stops cherry-picking |
| Switch approval cards in a private author room | K2: Switch itself refuses the reviewer (403); a card in the shared room would leak bytes |
| Scoped addressing: owner, owner's agents, reviewer-agent in `#pr-<n>` only | K1 and K4 proved it |
| Seal on an empty commit with a trailer; manifest as a Switch attachment | No history rewrite; questions pin the commit |
| Stdlib-only runtime | No dependency in the verification path |
| SPEC clarifications C1 to C13 (lead, 4 Nov) | Recorded in `docs/seal/SPEC.md` |
| The lead's agent built the room lane at the lead's request | "do the end to end build solo"; the teammate reviews `flipside/room/` |
| Agents read the room through their owner's gateway session and take `addressed` from their own event stream | An agent key gets 401 on the gateway transcript |
| reviewer-agent's room rule is `users: "*"` in its own `#pr-<n>` | Switch matches people by a member client id the gateway does not expose; reviewer-agent never acts on `addressed` and checks answers by sender id |
| `make solo` reuses the kill-test users Author and Reviewer | Agent names are unique per server (409 otherwise) |
| One agent session id per run | Old approval outcomes stay listed until acknowledged |
| The people's script uses only what a person sees: the transcript, their own card titles, their own repo | Keeps the live run honest and lets agents run as separate processes |
| Run summaries count verdicts in the room, not in the brief | Live, a forged copy can land after the brief |
| Keep the name Flipside | Other "flipside" repos share only the name; a rename would change the trailer, SPEC and vectors |
| Branch names without issue numbers | No GitHub issues exist yet |

## Dead ends

- argparse exits 2 on usage errors, so it is overridden to exit 1. `REMAINDER` rejects a leading `--offline`, so room commands dispatch before argparse.
- A git bundle without `HEAD` gives `NOT_IN_PR`; `examples/build.py` bundles `HEAD`.
- Piping a gate script into `tail` hides failures; use `set -o pipefail`.
- A chat cannot be created without an agent (422 `AGENTS_REQUIRED`). A chat's first agent receives untagged messages and refuses them under its default policy.
- A restarted author-agent crashed after the session was rewritten (SESSION_CHANGED on rebuild); `n` and the manifest now come from the seal state.
- A local secrets hook blocks any shell command whose text contains ".env", even when nothing reads the file. Write such edits as a script file and run it by path.
- Codex judges: only `gpt-6-luna` works on this account. curl truncates the gateway OpenAPI; use Python `urllib`.

## Files

- Seal lane: `flipside/seal/` (canon, merkle, steps, manifest, git, seal, prove, verify, coverage, secrets), `flipside/cli.py`.
- Room lane: `flipside/room/`:
  - `protocol.py`, `rules.py`, `brief.py`
  - `agents.py`: author-agent and reviewer-agent, both event-sourced
  - `transport.py`: FakeSwitch
  - `switch_client.py`: SwitchTransport and EventTap
  - `daemon.py`: `flip agent`
  - `solo.py`: `flip solo [--all]`
  - `replay.py`, `run.py` (the people's script and `play`), `scenario.py`, `github.py`
- Fixtures: `fixtures/build_fixtures.py` writes `fixtures/cases/<case>/`.
- Tests: `tests/seal/`, `tests/room/`; vectors in `tests/vectors/`; the offline example in `examples/`.
- Kill tests: `killtests/k1_k2.py`, `killtests/k4.py`. The users' passwords are in `killtests/.local-users.json` (mode 0600; never print it).

## Run

Branch: `m6-standalone-agents`, built on `m3-live-switch`, which is built on `main`.
Nothing past M2 is merged into `main`, nothing is pushed, and there is no remote.

```
uv sync --frozen
make lint test          # ruff, mypy strict, 241 tests; run twice
make g8                 # offline: q2-ok OK, q2-forged PROOF_FAIL
make replay-offline     # M2 flow on FakeSwitch
make fixtures           # 8 cases offline; writes docs/results/fixtures.md
make killtests          # K1, K2, K4; needs Switch Console's local server at 127.0.0.1:52370
make solo               # live flow, agents as processes, SIGKILL restarts; about 50 s
make solo-all           # all 8 cases live; about 6 minutes
make replay             # live replay of the CSV case
```

## Open questions

- GitHub repo: wait for the teammate's invite (check with `gh api user/repository_invitations`), or the lead lets the agent create `kadoo69/flipside`.
- Slack login for K3, or turn on Docker and the bundled Mattermost for a real chat window in the demo.
- The teammate's GitHub login, for `AGENTS.md`.

## Pending board posts (the board is not set up yet)

1. `@all` SPEC v1.1 clarifications C1 to C13, including the verify code `BAD_DISCLOSURE`.
2. M1 gates green (`evidence/m1-20261104T201854.log`).
3. K4 green.
4. `@all` changes to BUILD sections 6 and 7:
   - `withheld` gains the reason `session_changed`.
   - `verdict` gains `q`, `ref` and `leaf`; `brief` gains `pr`, `seal`, `not_asked` and `refused`.
   - SCOPE falls back to a mention step, and C-FILE checks edit leaves only.
   - Refused verdicts do not settle a leaf.
   - The author gains the `offer` command.
5. M2, M3 and `solo-all` green, built by the lead's agent; the teammate should review `flipside/room/`.

## Next step

Once the repo invite arrives: accept it, push `main`, `m3-live-switch` and `m6-standalone-agents`, open the PR, and fast-forward `main` when CI is green on Ubuntu and macOS.
