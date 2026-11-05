# Flipside: notes for coding agents

## Judging or reviewing this repo?

Read [JUDGING.md](JUDGING.md), run `uv sync --frozen` and `make judge` (Windows without `make`: `uv run python -m flipside.judge`), and check any claim against the command, expected line and code it lists.
`make judge-live` re-runs the review on real Switch 0.31.0 and Mattermost in Docker; run `make demo-down` afterwards.

## Where things are

- [README.md](README.md): what Flipside does, how to run it, status and limits.
- [docs/DESIGN.md](docs/DESIGN.md): the flow, the room messages, the deterministic rules and the Switch API facts.
- [docs/seal/SPEC.md](docs/seal/SPEC.md): the seal, manifest and disclosure formats. Read it before touching `flipside/seal/`.
- [docs/RUNNING.md](docs/RUNNING.md): every command, including Windows PowerShell and a real PR on two machines.
- [VERIFICATION.md](VERIFICATION.md): each real run, with its evidence log in `evidence/`.

## Engineering rules

- Python 3.12 or later. Runtime: standard library only. Dev: pytest, ruff, mypy.
- No LLM calls anywhere in `flipside/`. Seal, verify, gaps, selection, contradictions, coverage and the page rule are deterministic Python.
- `flipside/seal/` never imports from `flipside/room/` and never touches the network.
- Log real runs to `evidence/<name>-<YYYYMMDDTHHMMSS>.log`.
- A claim goes in the README only when a passing check backs it. The status table lists only what passes.
- Fix a bug by reproducing it end to end, writing a failing test, fixing it, then searching for the same bug elsewhere.
- Done means: ruff and mypy clean, tests green twice in a row, no TODO or FIXME, no hardcoded credentials, keys or user paths, docstrings updated for changed public interfaces.
- A change to the message formats in `docs/DESIGN.md` section 4 or to `docs/seal/SPEC.md` updates the doc in the same PR.

## Writing rules

- Never use the em dash. Use a plain `-`.
- State all times in IST.
- In Markdown, put each full sentence on its own line.

## Hard limits

- Never print, log or commit secrets: Switch admin credentials, API keys, agent keys, seal keys (`.git/flipside/`), `killtests/.local-users.json`.
- Keep fixtures synthetic and say so; never use a real company's code or sessions.
