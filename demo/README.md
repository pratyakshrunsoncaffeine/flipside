# Offline demonstration

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

## Recording sequence, at most 2 minutes 30 seconds

| Elapsed | Show and explain |
|---|---|
| 0:00-0:20 | A CSV-export PR also changes `auth/session.py`; the reviewer needs the reason from the author's private session. |
| 0:20-0:45 | The seal and public manifest appear; Q1 names the hidden auth change and requests its leaf. |
| 0:45-1:10 | The author answers, sees the exact leaf on their private card, and approves it; the reviewer verifies it as `OK`. |
| 1:10-1:55 | Show the four refusals: unauthorized addressing, injected request, forged quote and reviewer answering the author's card. |
| 1:55-2:15 | Show the brief and per-file coverage, including the steps that were not disclosed. |
| 2:15-2:30 | Show the G8 `OK` and `PROOF_FAIL` results and the reproduction command. |

For the final video, record the live flow with `flip setup` and `flip chat` as described in the root README.
Label any offline footage as FakeSwitch.
The script above is a recording plan, not evidence that a video or live run exists.
