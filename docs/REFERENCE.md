# Flipside reference

Terms, the six steps in order, and every passing check.
Evidence for each check is in `VERIFICATION.md`.

## Terms

| Term | Meaning |
|---|---|
| Seal | An empty commit on the PR with a `Flipside-Seal: v1 root=… n=… manifest=…` trailer, made by `flip seal` |
| Leaf | One salted chunk of one step of the author's agent session; the unit the author approves and the reviewer verifies |
| Root | The Merkle root over all leaves; a leaf with a valid inclusion proof was in the session when it was sealed |
| Manifest | Public metadata per step (role, tool, files, command class, test outcome), never text |
| Gap | A deterministic rule hit on public PR data that becomes a question (`CI`, `TESTS`, `SCOPE`, `UNSEALED`, `LINT`, `BUILD`, `RERUN`, `SIZE`) |
| Coverage line | Per changed file: sealed steps, disclosed, not disclosed |
| Page rule | When reviewer-agent posts the brief and mentions the reviewer: every question answered and every requested leaf settled, or a timeout |
| Gateway | Switch's HTTP API for people (`/gateway/...`); agents use the agent API |

## How it works

1. `flip seal` turns the author's Claude Code session (with subagents) into salted leaves, builds an RFC 9162 Merkle tree, and commits an empty seal commit with a `Flipside-Seal: v1 root=… n=… manifest=…` trailer.
   Keys and salts stay in `.git/flipside/`.
   Spec: `docs/seal/SPEC.md`.
2. author-agent posts the seal and the public manifest (step metadata, no text) in the reviewer's room `#pr-<n>`.
3. reviewer-agent finds gaps with deterministic rules (`CI`, `TESTS`, `SCOPE`, `UNSEALED`, `LINT`, `BUILD`, `RERUN`, `SIZE`), asks up to five questions, and requests the leaves that would answer them (`flipside/room/rules.py`).
4. author-agent secret-scans each requested leaf, then opens one approval card per leaf in the author's private room `#pr-<n>-author`.
   The author can offer more steps there: `@flipside-author-agent offer Q1 step 3`.
5. On approve, author-agent re-checks the sealed prefix and posts the disclosure with its inclusion proof.
   On decline it posts `withheld`.
6. reviewer-agent verifies each disclosure (`flipside/seal/verify.py`), checks contradictions on verified bytes only, and posts the brief, which mentions the reviewer.

No LLM runs anywhere in `flipside/`.
Seal, verify, gaps, selection, contradictions, coverage and the page rule are deterministic Python on the standard library.

## Status

Only checks that pass are listed; details and evidence in `VERIFICATION.md`.
K1 to K5 are kill tests of the Switch behaviour Flipside relies on; G1 to G8 are the seal checks (proofs, tamper codes, test vectors, the offline `OK` / `PROOF_FAIL` check).

| Check | Command |
|---|---|
| The whole review in Mattermost on a real Switch 0.31.0 server: both people act as their own Mattermost accounts, the author approves the card in Mattermost, four refusals, both agents killed and restarted (macOS) | `make demo`, `evidence/demo-mattermost-csv-export-20261105T131047.log` |
| K5 (8/8): in Mattermost, Switch addresses the author's claimed account, refuses the reviewer's and an unclaimed account's tag, takes a card press only from the author, and refuses each person changing the other's room | `make k5`, `evidence/k5-20261105T153338.log` |
| The author presses Approve by hand in the Mattermost web app | `flip demo run --press`, `evidence/demo-mattermost-card-20261105T1318-after.png` |
| Kill tests K1, K2 (9/9) and K4 (6/6) on switch-core 0.31.0 | `make killtests` |
| The live flow in Slack channels (`flip solo --slack --press`): the author approves the card in Slack; 4 refusals, 0 duplicate posts | `evidence/solo-csv-export-20261105T011603.log`, `evidence/solo-csv-export-20261105T011603-slack-card.png` |
| K3: author-agent's approval card renders in Slack with Approve and Decline buttons; the reviewer gets 403; the author's button press in Slack reaches author-agent (4/4) | `evidence/k3-20261105T005334.log`, `evidence/k3-slack-card-20261105T005334-before.png` |
| Seal checks G1 to G8; ruff and mypy clean; the test suite green twice | `make lint test`, `make g8` |
| Offline end to end, with the four refusals | `make replay-offline` |
| 9 fixture cases match their expected outcomes, offline and live | `make fixtures`, `make solo-all` |
| Live end to end on local Switch with the four refusals, each agent in its own process, both killed with SIGKILL and restarted without duplicate posts | `make solo` |
| GitHub PR reader, on canned data and one public PR | `tests/room/test_github.py` |
| A real Claude Code session, sealed, connected with `flip setup`, both agents as processes, people via `flip chat`: 2 questions, 8 leaves verified, brief | `evidence/real-session-20261104T224823.log` |
| The same sealed PR on GitHub, read with `gh api` (title, body, files, check runs): 2 questions, 8 leaves verified, 0 contradictions | `evidence/github-pr-20261105T002706.log` |
| CI on Ubuntu and Windows | `.github/workflows/ci.yml` |
| Clean clone on a second machine (Windows, its own Switch server): kill tests, live flow and `flip replay` reproduce the Mac's verdicts and coverage lines | `evidence/replay-switch-csv-export-20261105T015811.log` |
