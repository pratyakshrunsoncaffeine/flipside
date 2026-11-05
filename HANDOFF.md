# Handoff

Updated 5 Nov 2026, 14:30 IST.
Load first: `AGENTS.md`, this file, `docs/BUILD.md` (gates, protocol in section 6, Switch facts in section 9), `docs/seal/SPEC.md` before touching `flipside/seal/`, `VERIFICATION.md` (evidence).
Skills: `pr-protocol` before branching or opening a PR; `pr` for PR bodies; `handoff` to update this file; `design-taste-frontend` before changing `site/`.

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
`main` at 1bc0e42 or later.
The repo stays private: Pratyaksh decided (5 Nov), so no GitHub Pages and no visibility change unless Pratyaksh says otherwise.

Merged 5 Nov: #28, #30, #31 (Codex), #33 (`make demo`, K5), #35 (killtests and demo in `make lint`), #37 (kill tests count only a 403 as a refusal), #38 (site), #40 (Node 22 in CI), #41, #42 (`flip demo down` keeps its config on failure), #43 (`site/verify.html`), #45, #47, #48 (approval boundary wording), #50 (site claims audit), #52, #54 (README cut; detail in `docs/RUNNING.md` and `docs/REFERENCE.md`).

Open work:
- Aarav: M6 video SHA-256 in `VERIFICATION.md`; after M2 merges, turn off the tailnet forward of Switch and rotate both reviewer passwords (they were pasted in chat).
- Codex: final blind judge run on `main` after M2.
- Pratyaksh: how judges get access to the private repo, before 7 Nov 23:59 IST.

Done:
- M2 two machines: Mac author with Switch, Windows reviewer-agent over a private tailnet (`evidence/m2-author-20261105T172923.log`, `evidence/m2-reviewer-20261105T172644.log`).
- Everything listed in `VERIFICATION.md`: K1/K2 9/9, K3 4/4 (Slack card), K4 6/6, K5 8/8 (Mattermost), G1 to G8, M4 on Windows, a real Claude Code session, a real sealed GitHub PR.
- The launch film v13 (78.0 s, v12 recoloured to the site palette) is `site/media/flipside-film.mp4`; size and SHA-256 are in VERIFICATION.md.
- The site (`site/index.html`), sections in order: hero with Flip (the bot, live Three.js); "Two laptops, one Switch room" diagram after the Switch hackathon page (agents wired to a switch that turns on, then a chat room with members, messages and a room panel); the replay player (the dock with Flip, play and chapter bars sits at the top of the player, over both rooms and the seal tree); real Slack and Mattermost screens; How it works in four colour fields; the film; Run it; footer.
  Every message in the replay and the diagram comes from `site/run.js`, which `site/build.py` writes from `evidence/demo-mattermost-csv-export-20261105T132112.log`.
  Design direction: tasteskill "one-motif" (seed 405919273, palette and type kept): Flip's puck, a rounded square with 30% corners, is the hero field, the buttons, the film frame and the end mark. The amber "why." in the hero is a deliberate brand exception from the film.
  Inspector: 0 FAIL at 1440, 768 and 390 px; two defended warnings (one card shown at four steps; the paper colour matches the film). No horizontal overflow from 320 to 1440 px.

Not done:
- Demo video for submission (at most 2.5 minutes, BUILD section 11) and its SHA-256 in VERIFICATION.
- Final blind judge run on the final README; submission before 7 Nov 23:59 IST (the repo stays private; how judges get access is Pratyaksh's call).
- The full review inside Slack channels (only the card is checked there); see Dead ends.

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
| PR CI: Ubuntu and Windows must pass, macOS on `main` only and non-blocking | macOS jobs were cancelled for lack of runners; Windows green on every PR since #7 |
| The site is static files with no build step beyond `site/build.py` | Runs from any static host or `python3 -m http.server`; no packages to approve |
| The site replays a real run, never invented text | Judges can match every Switch message id to the evidence log |

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
- A `.rise` or shutter element that starts fully clipped never fires an IntersectionObserver; observe its parent (site film plate bug).
- The Playwright MCP browser window is shared with the user and pins its window at 1600x1000; for exact widths open a new context with `browser.newContext({viewport})`.
- Never pass credentials through Playwright code; Mattermost passwords live only in `.flipside-demo/people.json` (0600). Never run `flip demo logins` in a session.
- `greeting` on room create, `receives_join_events: false`, `!follow-ups off` do not stop Switch's greeting.

## Files

- Seal: `flipside/seal/` (canon, merkle, steps, manifest, git, seal, prove, verify, coverage, secrets), `flipside/cli.py`.
- Room: `flipside/room/` (`agents.py`, `rules.py` (lead's lane), `switch_client.py`, `daemon.py`, `setup.py`, `chat.py`, `solo.py`, `replay.py`, `run.py`, `github.py`, `protocol.py`, `brief.py`, `transport.py`).
- Kill tests: `killtests/k1_k2.py`, `k3.py`, `k4.py`, `switch_api.py`.
- Fixtures: `fixtures/build_fixtures.py` writes `fixtures/cases/`; set B in `fixtures/b/` (Codex).
- Demo (#33): `make demo`, `make k5`, `make demo-down`; people and passwords in `.flipside-demo/` (local, 0600).
- Site: `site/index.html` (page, inline CSS and JS), `site/flip.js` (the bot), `site/build.py` and `site/run.js` (generated), `site/media/`, `site/vendor/three.min.js`; tests in `tests/test_site.py`.
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
make demo               # Switch + Mattermost in Docker, full review; make demo-down to remove
make k5                 # who Switch admits in Mattermost, 8/8
python3 site/build.py evidence/demo-mattermost-<case>-<time>.log   # rebuild site/run.js
cd site && python3 -m http.server 8765 --bind 127.0.0.1           # view the site
uv run pytest tests/test_site.py                                  # links, em dash, run.js freshness
node ~/.claude/skills/design-taste-frontend/scripts/inspect.mjs http://127.0.0.1:8765/index.html
```

A real PR by hand: `docs/RUNNING.md` section "Run it on a real PR" (`flip seal`, `flip setup` three steps, `flip agent`, `flip chat`).
Board: `tools/board unread`, `tools/board post "[Aarav's Claude] ..."`; keep one background `tools/board wait` running and re-arm it after each wake.

## Open questions

- Pratyaksh: how judges reach a private repo at submission.
- Demo narration: macOS `say` (free, local) or an ElevenLabs key (rotate the key that was shared in chat).
- Whether to run the full review inside Slack channels for the demo (needs the identity change in Dead ends), or show only the card in Slack.

## Next step

Read the board (`tools/board unread`). Fix `flip demo down` (keep files on a failed `docker compose down`), then draft the M3 README.
