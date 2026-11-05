# Judging Flipside

This page is for judges and for the coding agents judges use (Claude Code, Codex, others).
Every claim in the README maps to one command, the line it should print, and the code behind it.
After `git clone` and `uv sync --frozen`, nothing here needs keys, accounts or network access, except the optional Docker step.

## Paths

| Time | Needs | Do this | You see |
|---|---|---|---|
| 1 minute | A browser | Watch the film linked at the top of the README; open `site/verify.html`, press "Check the sample step", then "Check an edited copy" | One step checks out; the edited quote fails |
| 3 minutes | Git, Python 3.12, [uv](https://docs.astral.sh/uv/) | `uv sync --frozen` then `make judge` | 11 checks, `RESULT PASS 11/11` in under a minute |
| 10 minutes | The above plus Docker with Compose v2 | `make judge-live`, then `make demo-down` | 14 checks in about 3 minutes: the review, K5 and all 9 labelled cases run now on pinned Switch 0.31.0 and Mattermost |
| 20 minutes | The above | `make demo`, then log in to Mattermost at the printed address as the author and press Approve; log in as the reviewer and try | The card answers only the author; Switch refuses the reviewer |

Windows without `make`: `uv run python -m flipside.judge` (add `--live` for the Docker path).

## What `make judge` checks

Each check prints the claim, the exact command, what it expects, what it got, and the code.
Tamper checks build their inputs fresh from `examples/q2-ok.json` into `.flip-judge/`, so every printed command can be re-run by hand.

| Id | Claim | Expect | Code |
|---|---|---|---|
| J1 | A disclosed step proves itself against the root sealed into the PR | `OK leaf 5` | `flipside/seal/verify.py` |
| J2 | Editing one word of a disclosed step is caught | `PROOF_FAIL` | `flipside/seal/merkle.py` |
| J3 | A step cannot be re-salted to fit | `PROOF_FAIL` | `flipside/seal/merkle.py` |
| J4 | A step cannot pass as a different step | `MANIFEST_MISMATCH` | `flipside/seal/verify.py` |
| J5 | A truncated proof is refused | `BAD_SIZE` | `flipside/seal/verify.py` |
| J6 | A proof counts only for the commit the question named | `WRONG_COMMIT` | `flipside/seal/verify.py` |
| J7 | The public manifest cannot change after sealing | `MANIFEST_HASH` | `flipside/seal/verify.py` |
| J8 | The whole review runs: rule-based question, own-words answer, one approved step, four refusals, a brief that says what was not shown | `RESULT PASS`, `card_403 1`, `OK 1`, `PROOF_FAIL 1` | `flipside/room/` |
| J9 | Questions come from fixed rules: 9 labelled cases, 2 adversarial | `9/9 match` | `flipside/room/rules.py`, `fixtures/` |
| J10 | The same review ran on real Switch and Mattermost | Newest committed `evidence/demo-mattermost-*.log` says `RESULT PASS` and `four refusals live: yes` | `flipside/room/demo.py` |
| J11 | No model decides anything | No model SDK import in `flipside/`; `dependencies = []` | `pyproject.toml` |

`make judge-live` adds J0 (Docker stack starts and the case plays), runs J10 on the log written by that run, adds J12: K5, where Switch admits the author's claimed Mattermost account and refuses the reviewer and an unclaimed stranger, and adds J13: all 9 labelled cases, honest and adversarial, played on real Switch.

Results go to `evidence/judge-<time>.log` and `.json`.
The exit code is 0 only when every check passes.
Every push also runs `make judge` on Ubuntu and Windows and `make judge-live` in Docker on Ubuntu (`.github/workflows/ci.yml`); each run's demo, K5 and judge logs are uploaded as the `demo-mattermost-log` artifact.

## The film is the real run

Every message the film lifts out of the footage is a Switch message in `evidence/demo-mattermost-csv-export-20261105T190535.log`, recorded 5 Nov 2026, 19:05 IST, on pinned Switch 0.31.0 and Mattermost.

| Film line | Switch message |
|---|---|
| Omar's agent finds an unexplained change | `sw_3c9943b3…` reviewer-agent: Q1 `auth/session.py` changed and the PR description does not mention it |
| Priya answers in her own words | `sw_c9ab5a7e…` author: Q1: The export test kept failing with SessionExpired ... |
| A grab for everything is dropped | `sw_5b6ae5bf…` reviewer-agent: a free-text request to ignore instructions and paste secrets, dropped |
| Switch refuses the reviewer | `sw_000c8c26…` Switch's refusal: not permitted to direct messages to author-agent |
| One click shares one step | `sw_d3c9062f…` author-agent: Q1 · step 5, chunk 0 · approved by @Author |
| Omar's agent checks it against the seal | `sw_6ac8c99c…` reviewer-agent: OK leaf 5 against seal ae44db8 |
| An edited copy fails the check | `sw_cbb165bf…` forged copy, then `sw_cf28fc6c…` PROOF_FAIL |
| Omar gets the why, nothing more | `sw_07866228…` brief with the coverage line |
| The reviewer cannot answer the card | card `b095c0f4`: HTTP 403 |

## Where Switch carries the weight

The seal proves a quote is genuine; Switch decides who may ask for it and who may release it.
Without Switch there is no second owner: the reviewer could command author-agent and answer the author's approval card.

| Boundary | Enforced by | Check |
|---|---|---|
| Only the author's own account may address author-agent | Switch addressing policy plus claimed Mattermost identity | J12 (K5.a to K5.c), refusal 1 in J8 |
| Only the author may answer the approval card | Switch approval cards: HTTP 403 for anyone else | J12 (K5.d to K5.f), `card_403` in J8 |
| Each owner's room settings change only by that owner | Switch room ownership: the other owner's edit is refused | J12 (K5.g, K5.h) |

The approval card shows the author the requested chunk in full, so the Switch server holds it before the author decides; only approved chunks reach the reviewer's room.

`make replay-offline` uses `FakeSwitch`, an in-process model of what K1, K2, K4 and K5 measured on a real server.
It holds both sides' keys in one process, so it proves the flow, not the two-owner boundary; `make judge-live` proves the boundary.

## Known limits

- Sessions are Claude Code JSONL; other agents need an adapter.
- A session forged before sealing is not caught: the seal proves what was sealed, not that it was honest.
- All fixtures are synthetic.
- The full list is in [README.md](README.md#limits).
