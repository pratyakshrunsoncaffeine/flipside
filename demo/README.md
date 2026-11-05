# Offline demonstration

A no-`make` runner for the offline review, useful on Windows.
`make judge` covers the same ground plus more; see [JUDGING.md](../JUDGING.md).

From the repository root, with Python 3.12+, Git and uv installed:

```text
uv sync --frozen
uv run --frozen python -m demo.run
```

The command runs the existing public CLI on the synthetic CSV-export scenario, then verifies the original and forged G8 quotes.
It needs no Switch server, accounts, keys, Bash or make.
The session, people, PR and repository are synthetic.
FakeSwitch simulates the addressing and card permissions; this is offline evidence.
Live Switch and process-restart evidence are separate gates in `VERIFICATION.md`.

To replay all nine existing cases and retain actual output:

```text
uv run --frozen python -m demo.run --all --log demo/evidence/offline.log
```

Each subprocess has a two-minute timeout.
A nonmatching exit status fails the command, including an unexpected acceptance of the forged quote.
The existing replay also checks its expected questions, verdicts and coverage, requires a brief, and rejects duplicate posts.
The runner does not rewrite fixtures, expected results or the generated fixture report.
