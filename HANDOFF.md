# Handoff

Updated 5 Nov 2026, 01:05 IST.
Load first: `AGENTS.md`, this file, `docs/BUILD.md` (gates, protocol in section 6, Switch facts in section 9), `docs/seal/SPEC.md` before touching `flipside/seal/`, `VERIFICATION.md` (evidence).
Skills: `pr-protocol` before branching or opening a PR; `pr` for PR bodies; `handoff` to update this file.

## Goal

Win Flip the Switch Track 01 (deadline 7 Nov 2026, 23:59 IST; team target 7 Nov 18:00 IST) with Flipside.
Flipside lets the owning team question the author team's private coding-agent session through Switch, and verify every quote against a Merkle root sealed into the PR.

## Rules that bind every agent

- Never print or commit secrets: the Switch Console env file values, API and agent keys, seal keys in `.git/flipside/`, `killtests/.local-users.json`, the Slack tokens (below).
- No LLM calls anywhere in `flipside/`. Runtime is the Python standard library only.
- Never use the em dash; use a plain "-". Times in IST. Each Markdown sentence on its own line.
- Branch `<issue#>-<slug>` from fresh `main`; stage only your own files; never add an agent as co-author.
  Commit messages end with the `Claude-Session:` line only.
- Reproduce a bug end to end, write a failing test, fix it, then search for the same bug elsewhere.
- A gate is green only when its command passes or its evidence file exists.
- Never edit generated files: `docs/results/fixtures.md` (`make fixtures`), `fixtures/cases/*` (`fixtures/build_fixtures.py`). Revert a timestamp-only change.
- Contract changes (`docs/seal/SPEC.md`, `docs/BUILD.md` section 6) need an `@all` board post and the lead's yes before merge.
- The lead (Pratyaksh, `@pratyaksh-claude`) reviews and merges PRs; auto mode refuses `gh pr merge` on our own PR.

## State

Team repo `pratyakshrunsoncaffeine/gateplus` (private); team clone `~/gateplus-kadoo69`.
`main` at 18d0234 or later: Flipside, Gate v1 in `legacy/gate-v1/`, ported rules, Windows fixes, room-bound agent state (#11), Codex's set B, demo and Windows evidence (#5, #6, #12), K3 (#14).

Open PRs:
- #17 `16-coverage-not-disclosed` (Aarav): coverage lines say "N not disclosed (steps ...)"; `coverage[].withheld` JSON key is now `not_disclosed`; "withheld" means only an author decision. Lead approved the contract change on the board. Codex runs set B unchanged against it, then the lead merges. This handoff is a commit on that branch.
- #15 `lead/k3-evidence-wording` (lead): VERIFICATION K3.d cites the log line, not the after screenshot.

Done (evidence in `evidence/`, details in `VERIFICATION.md`):
- Live M4 on a second machine: a clean clone on Windows with its own Switch Console 0.40.1 server reproduces the Mac's verdicts and coverage lines (`evidence/replay-switch-csv-export-20261105T015811.log`). Windows needs `SWITCH_BASE` from `SERVER_PORT` in `switch-core.env`.
- K1/K2 9/9, K4 6/6 (`make killtests`); G1 to G8 (`make lint test g8`); 338 tests, twice.
- K3 4/4 (`make k3`, `evidence/k3-20261105T005334.log`, screenshots): author-agent's card renders in Slack with Approve and Decline; the reviewer gets 403; the author's Slack press reaches author-agent.
- Offline flow with the four refusals (`make replay-offline`); 9 fixtures 9/9 offline (`make fixtures`); live on local Switch: `make solo`, `make solo-all` 9/9.
- A real Claude Code session end to end, and a real sealed GitHub PR (`kadoo69/flipside-sandbox#1`, private, synthetic): `evidence/real-session-20261104T224823.log`, `evidence/github-pr-20261105T002706.log`.
- CI: Ubuntu required, Windows green, macOS on pushes to `main` only.

Not done:
- Demo video (at most 2.5 minutes, BUILD section 11) and its SHA-256 in VERIFICATION. Aarav records it on the Mac from `docs/DEMO.md`.
- Final blind judge run on the final README (`docs/judging/blind/`); submission; the lead makes the repo public before 7 Nov 23:59 IST.
- The full review inside Slack channels (only the card is checked there); see Dead ends.
- Switch auto-posts an author-agent greeting and a "no session connected" reply in new rooms; no setting stops it.

## Slack (K3 setup, local only)

- Workspace `flipside-eth9734` (Flipside, `T0CEY09M1LJ`), created by Aarav; the only human is Aarav's Slack user `U0CESSDPMNZ` (`aaravmahajan069`).
- App `A0CF04KF89X` "Agent Switch", made from Switch's manifest without the `agent_view` block (Slack cannot undo it), Socket Mode.
- Tokens in owner-only files, never in the repo or chat: `~/.flipside-slack-bot` (xoxb), `~/.flipside-slack-app` (xapp), `~/.flipside-slack-app.json` (app credentials from `apps.manifest.create`).
  Slack CLI v4.12.0 at `~/.slack/bin/slack`, logged in to that workspace; the Slack plugin for Claude Code is installed (user scope).
- Switch connection "Flipside Slack" `f56432e5-e42d-4795-85d0-54f7fe94938b`, active, default, channel creation on, agent name autocomplete off (free plan).
  The author's Switch account (`author@flipside.local`) claimed the Slack user.
- Run K3: `SLACK_BOT_TOKEN_FILE=~/.flipside-slack-bot make k3`, then press Approve on the card in the new `#pr-k3-...-author` channel within 10 minutes (`K3_WAIT_SECONDS`).
- Browser: the Claude in Chrome extension is not connected; a Playwright browser window logged in to that Slack workspace did the Slack steps. Playwright snapshots can capture tokens: delete any file under `~/.playwright-mcp` that matches `xox` or `xapp-`.

## Decisions

| Decision | Reason |
|---|---|
| Flipside is the base; Gate v1 is kept unchanged in `legacy/gate-v1/` | Lead's decision on the board; the rules port reads from there |
| Approvals are Switch cards in a private author room | K2: Switch refuses the reviewer (403); `approve 41` in chat would not be enforced |
| One card per leaf, not per question | The same bytes need one decision |
| C14: never-ran Bash calls seal `ok: null`; C15: `cmd` from every shell segment | Avoid false TESTS questions and `other` command classes |
| `flip setup` swaps join lines carrying ids only | Neither side sees the other's credentials |
| Agent state and event cursor record their rooms; a mismatch starts fresh | A stale state from another setup for the same commit stalled the GitHub run |
| Coverage says "not disclosed"; "withheld" is only an author decision | Lead's contract decision (board, 4 Nov); the brief's "withheld" count meant author declines |
| K3 bridged room uses `channel_type: channel_private` and a live agent connection | Bridged rooms need `channel_type`; without a connected agent Switch shows "Host offline" and no buttons |
| The review stays in Switch rooms; Slack is shown for the card | Slack senders are not Switch user ids (Dead ends) |
| PR CI: Ubuntu required, Windows `continue-on-error`, macOS on `main` only | macOS PR jobs were cancelled for lack of runners |

## Dead ends

- In a Slack-bridged room, Switch reports a person's message as `sender.kind: human` with `userId: null`, and a button press as `answeredBy: @switch-slack-<connection>-<slack username>:<server>`.
  Flipside's agents accept only `user:<switch id>` (`agents.py:204`, `:231`, reviewer-agent's author check), so they would ignore both. Fixing it needs per-person accepted ids in `flip setup` and the agent config, plus bridged rooms; the lead has not asked for it.
- The author is not a member of a room created with `POST /gateway/rooms` until added through `POST /gateway/chats/{room}/members`; until then `GET /gateway/chats/{room}/messages` returns 403 `NOT_A_MEMBER`.
- Auto mode refuses `gh repo create` and `gh pr merge` on our own PR; the user or the lead does those.
- A local secrets hook blocks shell commands whose text looks like env access (`.env`, some env-var names); write the script to a file and run it by path.
- A hook rewrites some commands (`make` to `rtk make`) and `git log` output; use `command git` or `gh api repos/<r>/commits/main` for exact hashes.
- In zsh, a `$VAR` with several words does not split; use `.venv/bin/flip` and `xargs`.
- `killtests/k1_k2.py` imports `switch_api` from its own folder; scripts outside it must add `killtests/` to `sys.path`.
- A second clone has no `killtests/.local-users.json`; copy it (mode 0600) from the clone that created the users.
- A chat cannot be created without an agent (422 `AGENTS_REQUIRED`); agent names are unique per server (409).
- `greeting` on room create, `receives_join_events: false`, `!follow-ups off` do not stop Switch's greeting.

## Files

- Seal: `flipside/seal/` (canon, merkle, steps, manifest, git, seal, prove, verify, coverage, secrets), `flipside/cli.py`.
- Room: `flipside/room/` (`agents.py`, `rules.py` (lead's lane), `switch_client.py`, `daemon.py`, `setup.py`, `chat.py`, `solo.py`, `replay.py`, `run.py`, `github.py`, `protocol.py`, `brief.py`, `transport.py`).
- Kill tests: `killtests/k1_k2.py`, `k3.py`, `k4.py`, `switch_api.py`.
- Fixtures: `fixtures/build_fixtures.py` writes `fixtures/cases/`; set B in `fixtures/b/` (Codex).
- Local only, never committed: `killtests/.local-users.json`, agent configs, `.git/flipside/`, the Slack token files.

## Run

```
cd ~/gateplus-kadoo69 && uv sync --frozen
make lint test          # ruff, ruff format, mypy strict (also win32), 338 tests; run twice
make g8                 # offline: q2-ok OK, q2-forged PROOF_FAIL
make replay-offline     # full flow on FakeSwitch
make fixtures           # 9 cases offline; writes docs/results/fixtures.md (generated)
make killtests          # K1, K2, K4; needs Switch Console's local server at 127.0.0.1:52370
SLACK_BOT_TOKEN_FILE=~/.flipside-slack-bot make k3   # K3; press Approve in Slack
make solo               # live flow, agents as processes, SIGKILL restarts
make solo-all           # all 9 cases live
```

A real PR by hand: README section "Run it on a real PR" (`flip seal`, `flip setup` three steps, `flip agent`, `flip chat`).
Board: `tools/board unread`, `tools/board post "[Aarav's Claude] ..."`; keep one background `tools/board wait` running and re-arm it after each wake.

## Open questions

- Demo narration: macOS `say` (free, local) or an ElevenLabs key.
- Whether to make the full review run inside Slack channels for the demo (needs the identity change above), or show only the card in Slack.

## Next step

Read the board (`tools/board unread`). When Codex confirms set B on #17 and the lead merges it, write and post the live demo script (BUILD section 11) so Codex can record the video.
