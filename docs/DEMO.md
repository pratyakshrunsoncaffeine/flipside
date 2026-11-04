# Demo video: live script

The video shows one live run on the local Switch server, in Slack, at most 2 minutes 30 seconds.
Everything in it is synthetic: the session, the people, the PR and the Slack workspace.
It follows `docs/BUILD.md` section 11.

## Setup (Aarav's Mac, where the Switch server and the Slack workspace run)

1. Switch Console's local server answers at `127.0.0.1:52370`, and the "Flipside Slack" connection is active with agent greetings off (`HANDOFF.md`, Slack).
2. The author's Switch account has claimed the Slack user (`author@flipside.local`, "This is me").
3. Old `pr-142` channels are renamed and archived, so the new channels get their plain names.
4. A browser window of 1440 by 900, logged in to the Flipside Slack workspace.
5. The narration key file is mode 0600 and outside the repo; the recording tools read it by path and never print it.

## Run

```
flip solo --slack --press --pace 3 --no-restart
```

The author presses Approve on the card in `#pr-142-author` when the script logs `waits for the author`.
The run must end with `RESULT PASS`; its evidence log is the video's source of truth.

## Shots and narration

| # | Time | Shown | Narration |
|---|---|---|---|
| 1 | 0:00-0:15 | The PR: title "Add CSV export", changed files with `auth/session.py` | A data team's pull request adds CSV export. It also changes `auth/session.py`, and the description never says why. The reason is in the author's private coding-agent session. Today the reviewer has two options: trust the author, or ask for the whole transcript. |
| 2 | 0:15-0:35 | `#pr-142`: seal line, manifest, the question | Flipside seals the session into the PR before review: a Merkle root in an empty commit, and a public manifest of steps, tools and files, with no text. In Slack, the reviewer's agent reads the seal and finds the gap: an auth file changed, and nobody explained it. |
| 3 | 0:35-0:55 | `#pr-142`: Q1, the request for step 5, the author's answer | It asks one question, and names the one step it wants to see. The author answers in their own words. |
| 4 | 0:55-1:20 | `#pr-142-author`: the card with the exact bytes, sha256, Approve and Decline; the press | The author's agent sends nothing on its own. In the author's private channel, Switch shows an approval card with the exact bytes and their hash. Only the author can press Approve. |
| 5 | 1:20-1:40 | `#pr-142`: the disclosure and verdict `OK` | The step is posted with its Merkle proof. The reviewer's agent checks it against the sealed root, in plain Python, no model involved. Verdict: OK. |
| 6 | 1:40-2:05 | `#pr-142`: the Switch refusal, the dropped request, `PROOF_FAIL`; the 403 line from the log | Now the attacks. The reviewer tags the author's agent directly: Switch refuses. A request carrying hidden instructions: dropped by a fixed schema. A disclosure with one word changed: PROOF_FAIL. The reviewer pressing the author's card: Switch returns 403. |
| 7 | 2:05-2:20 | `#pr-142`: the brief and its coverage lines | The brief pings the reviewer: one question, answered, one step verified, and coverage that lists what was not disclosed. The rest of the session never left the author's laptop. |
| 8 | 2:20-2:30 | End card: `make replay`, `flip verify examples/q2-ok.json` | Every claim reproduces offline with make replay and flip verify. Flipside, built on Switch. |

## After recording

- Publish the video as a GitHub release asset and put its SHA-256 in `VERIFICATION.md` (Demo video).
- Keep the run's evidence log next to it in `evidence/`.
