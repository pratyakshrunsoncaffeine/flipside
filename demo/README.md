# Offline demo

Runs the whole review on your machine with no Switch server, no accounts and no `make`, so it also works on Windows.

```text
uv sync --frozen
uv run --frozen python -m demo.run
```

It plays the CSV-export pull request from the README: the seal, the reviewer's question, the author's answer, the approved step checked against the seal, and the four refusals.
It then checks two quotes: the real one prints `OK`, and a copy with one word edited prints `PROOF_FAIL`.

To play all nine sample pull requests and save the output:

```text
uv run --frozen python -m demo.run --all --log demo/evidence/offline.log
```

The command fails if any case gives a different question, verdict or coverage line than expected, or if the edited quote is accepted.

Everything here is synthetic: the session, the people, the pull request and the repository.
Switch is replaced by an in-process stand-in that enforces the same rules, so this shows the logic, not the server.
For the same review on a real Switch server and in Mattermost, run `make demo`, or see [VERIFICATION.md](../VERIFICATION.md) for the recorded runs.
