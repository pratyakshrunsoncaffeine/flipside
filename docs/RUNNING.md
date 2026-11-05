# Running Flipside

Run every command from the repository root.
The README has the three-command version; this page has all of them.

## Quick start

Offline, no Switch and no accounts (Git, Python 3.12, [uv](https://docs.astral.sh/uv/) and make; on Windows without make, see below):

```
uv sync --frozen
make lint test
make g8
make replay-offline
make fixtures
```

`make g8` verifies `examples/q2-ok.json` (`OK`) and `examples/q2-forged.json` (`PROOF_FAIL`) with no network.
`make replay-offline` plays the CSV-export case end to end on an in-process Switch stand-in and writes `evidence/replay-offline-*.log`.
`make fixtures` runs all 9 cases and writes `docs/results/fixtures.md`.

Live, on a local Switch server (Switch Console's built-in server, `http://127.0.0.1:52370` on macOS; set `SWITCH_BASE` for another address):

```
make killtests
make solo
make replay
```

`make solo` creates two local users (Author, Reviewer), registers each one's agent, opens both rooms and sets the scoped policies.
Each agent then runs as its own process (`flip agent`); both are killed with SIGKILL mid-flow and restarted.
It writes `evidence/solo-*.log` with every Switch message id.
`make solo-all` does the same for all 9 fixture cases.

### Without make (Windows PowerShell)

The same targets, run directly:

```
uv sync --frozen
uv run --frozen ruff check flipside tests docs/seal/example.py examples fixtures killtests demo
uv run --frozen ruff format --check flipside tests docs/seal/example.py examples fixtures killtests demo
uv run --frozen mypy
uv run --frozen pytest
$c = Get-Content examples/commit.txt
uv run --frozen python -m flipside.cli verify --bundle examples/seal.bundle --commit $c --manifest examples/manifest.json examples/q2-ok.json
uv run --frozen python -m flipside.cli verify --bundle examples/seal.bundle --commit $c --manifest examples/manifest.json examples/q2-forged.json; $LASTEXITCODE
uv run --frozen python -m flipside.cli replay --offline
uv run --frozen python -m flipside.cli replay --fixtures
```

The first verify prints `OK`; the forged one prints `PROOF_FAIL` and `$LASTEXITCODE` is 2.
On Windows, give pytest a short temporary folder if a path is too long: `uv run --frozen pytest --basetemp=C:/t/run1`.

Live, point the tools at the Console's local server first.
On Windows the Console writes `%APPDATA%\switchdash\local-switch-server\native\run\switch-core.env`, and its `SERVER_PORT` line gives the port (52115 on our machine, not 52370):

```
$env:FLIP_SWITCH_ENV = "$env:APPDATA\switchdash\local-switch-server\native\run\switch-core.env"
$env:SWITCH_BASE = "http://127.0.0.1:" + ((Select-String -Path $env:FLIP_SWITCH_ENV -Pattern '^SERVER_PORT=(\d+)').Matches[0].Groups[1].Value)
cd killtests; uv run --frozen python k1_k2.py; uv run --frozen python k4.py; cd ..
uv run --frozen python -m flipside.cli solo
uv run --frozen python -m flipside.cli replay
```

## The review in Mattermost (`make demo`)

`make demo` needs Docker with Compose v2 and no other accounts or keys.
It fetches Switch's published Compose file for release 0.31.0, checks it against a pinned digest, and starts switch-core, PostgreSQL and Mattermost bound to 127.0.0.1.
It creates the Author and the Reviewer as Switch users and as Mattermost users, and each person claims their own Mattermost account in Switch, so Switch can tell the author's messages and button presses from anyone else's.
Server secrets and the two logins are written to `.flipside-demo/` (mode 0600, git-ignored).

Then it plays the CSV-export case: both people type in the bridged Mattermost channels as themselves, the author approves author-agent's card in Mattermost, the four refusals happen, and both agents are killed and restarted.
It writes `evidence/demo-mattermost-<case>-<time>.log` with every Switch message id.

```
make demo                    # up, then run
flip demo logins             # the two local Mattermost logins, to watch at http://127.0.0.1:8065
flip demo run --press        # leave the card for you: log in as the Author and press 1. Approve
make k5                      # who Switch admits in Mattermost (8 checks)
make demo-down               # remove the containers, their data and .flipside-demo/
```

Checked on macOS only: Docker Desktop would not install on our Windows test machine (a Windows Insider build).
Windows runs everything offline and the live flow on Switch Console's local server.

## Run it on a real PR

Each side uses their own Switch login, kept in a creds file (`{"me": {"email": ..., "password": ...}}`, mode 0600).

Author, on the PR branch:

```
flip seal --base origin/main && git push       # empty seal commit; keys stay in .git/flipside/
flip setup author --pr 142 --creds me.json --as me
# send the printed flip-join line to the reviewer, get theirs back, then:
flip setup author --join "<reviewer's line>"
flip agent author --config author-agent.json
```

Reviewer, in a clone with the PR fetched (`git fetch origin pull/142/head`):

```
flip setup reviewer --join "<author's line>" --github acme/shop --pr 142 --creds me.json --as me
flip agent reviewer --config reviewer-agent.json
```

The join lines carry ids only.
Config files are written mode 0600, since they hold the agent's API key.
The reviewer reads the PR title, body, changed files and check runs with `gh api`; `--pr-json FILE --head SHA` replaces GitHub.
The page-rule timeout is `FLIP_ANSWER_TIMEOUT` seconds (default 1800).

On a Switch server with no chat app, people use `flip chat --config <their agent's config>`:
`read`, `say "Q1: ..."`, `cards`, `show <card>` (the exact text a card discloses) and `answer <card> approve|decline`.
