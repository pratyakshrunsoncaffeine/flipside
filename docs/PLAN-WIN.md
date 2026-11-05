# Plan: Flipside to rank 1 in Track 01

Goal: move Flipside from about 4th (8.3) to 1st in the field by the team target, 7 Nov 18:00 IST.
Ordered milestones with gates; a milestone is done only when its gate command passes or its evidence file exists.

## Where we stand (field scan, 5 Nov 11:45 IST, README-based estimates)

| Entry | Switch 30 | Tech 25 | Creativity 25 | Presentation 20 | Total |
|---|---|---|---|---|---|
| Countersign (PhiBao) | 9 | 9 | 7 | 9 | 8.5 |
| Notary (Ritesh-Root) | 10 | 8.5 | 8 | 7 | 8.5 |
| Splitbrain (fabriutola-hub) | 8.5 | 9 | 9 | 6.5 | 8.35 |
| Flipside | 8.5 | 8 | 8.5 | 8 | 8.3 |

What the leaders have that we lack:
- One command that boots real Switch (standalone compose, pinned) with the bundled Mattermost, so a judge clicks in a real chat.
- A run with the two sides as separate parties on separate machines.
- A zero-install way to check a proof (Countersign's live ledger, Notary's `make verify-sample`).
- Video plus uncut real footage, linked at the top of the README.

What only we have: the session stays on the author's laptop; one step is disclosed with a Merkle proof, only after the author approves.
Six entries now pitch "trust what the agent did"; all of them check outcomes (tests, claims).
Lead with privacy plus proof, not with review.
Competitors inform only; every change below extends Flipside's own mechanism.

## Target scores

| Criterion | Now | Target | Lever |
|---|---|---|---|
| Switch 30 | 8.5 | 9.5 | M1 real Mattermost path, M5 disclosure log as a room document |
| Tech 25 | 8 | 9.5 | M1 one command on real Switch, M2 two machines, M4 verifier parity |
| Creativity 25 | 8.5 | 9 | M3 positioning: private session, provable disclosure |
| Presentation 20 | 8 | 9.5 | M3 README, M6 film plus uncut run |

Weighted target: about 9.4.

## Milestones

### M0. Land the ready work (lead)

- Merge order: #30, then #28, then #31 (#30 clears the 6 `ruff check killtests demo` errors the other two carry).
- Add `killtests` and `demo` to `make lint` so those errors cannot return.
- Gate: `make lint test g8 replay-offline` green on `main`, Ubuntu and Windows CI green.

### M1. `make demo`: real Switch and Mattermost in one command (Aarav's Claude)

- S1 spike first: on a Console-set-up server with the bundled Mattermost, does a person's Mattermost message reach agents with a Switch user id?
  If yes, people answer questions in chat and the Slack dead end (HANDOFF) closes for Mattermost.
  If no, people answer through the card and `flip` commands, and the README says so.
- `make demo` runs `replay/mattermost_demo.py` (room lane; standard library, Docker required); the Makefile target goes through the lead: fetch `ghcr.io/sandbox-quantum/standalone-compose` pinned by digest, start switch-core and Mattermost, create Author and Reviewer, register both agents, open both rooms as Mattermost channels, run the CSV-export case, print the Mattermost logins.
- The judge logs in as the author and presses Approve; logs in as the reviewer and sees the 403.
- `make demo-down` removes everything it created.
- Gate: from a fresh clone on the Mac, `make demo` exits 0 and writes `evidence/demo-mattermost-*.log` with the four refusals, the author's button press reaching author-agent, and `OK` from `flip verify`; screenshot of the card in Mattermost.

### M2. Two parties, two machines (lead plus Aarav)

- Author on the Mac, reviewer on the lead's Windows machine, one Switch server reachable on a private network only (no public exposure without the lead).
- Exchange `flip-join` lines; run the CSV-export case.
- Gate: one evidence log per machine with the same seal root and matching verdicts; a short screen clip from each side for M6.

### M3. Positioning and README (Aarav's Claude drafts, lead approves)

- Hero line: "Prove what your coding agent did, without handing over the session."
- Video at the top, then a three-line "Try it" block: `make g8`, `make replay-offline`, `make demo`.
- Comparison table: outcome checkers (tests, claims, jurors) versus Flipside (private session, author-approved disclosure, offline proof); name categories, not competitors.
- Move K1 to K4, G1 to G8 and M-numbers below the fold; keep them in VERIFICATION.
- Gate: blind run with `blind/head.txt`, our README and the three leaders' READMEs anonymised; Flipside ranks 1st with both Claude and Codex, two runs each, order shuffled.

### M4. Zero-install proof check (Pratyaksh's Codex)

- `docs/verify/index.html`: one static page; paste or drop a proof JSON, the bundle and the commit; WebCrypto SHA-256; same salted leaves and RFC 6962 prefixes as `docs/seal/SPEC.md`.
- Reads only local input; no network.
- Gate: a parity test runs the page headless over every `examples/` and `fixtures/` proof and matches `flip verify` verdicts exactly, including `PROOF_FAIL` on `q2-forged.json`.
- Hosting on GitHub Pages waits for the repo to go public (lead).

### M5. Disclosure log as a room document (Aarav's Claude, after M1)

- BUILD stretch S2: reviewer-agent creates one room document "Disclosure log" per PR and appends each verified leaf (step, chunk, leaf hash, verdict, approver).
- Switch lets only the creator edit it, so the room holds a record neither side can rewrite.
- Gate: a kill test shows author-agent's edit is refused and the document lists every verified leaf from `make demo`.

### M6. Video (Aarav)

- One file of at most 150 s (BUILD M6): the v6 film (65 s) then an uncut real-time run of `make demo` in Mattermost (at most 80 s): question, card press, the four refusals, `flip verify` OK and `PROOF_FAIL`.
- Gate: duration at most 150 s, -14 LUFS, released as a GitHub release asset, SHA-256 in VERIFICATION.

### M7. Submit (lead)

- Final blind run (M3 gate) on the final README and video.
- VERIFICATION refreshed: test counts per OS, `make demo` evidence, two-machine logs, video SHA-256.
- Lead makes the repo public, then submits.
- Gate: fresh public clone passes `make lint test g8 replay-offline`; the submission form is filed before 7 Nov 23:59 IST.

## Order and owners

| Order | Milestone | Owner | Depends on |
|---|---|---|---|
| 1 | M0 | lead | none |
| 2 | M1 (S1 spike first) | Aarav's Claude | Docker running on the Mac |
| 2 | M4 | Pratyaksh's Codex | none |
| 3 | M3 draft | Aarav's Claude | S1 result |
| 4 | M2 | lead plus Aarav | M1 |
| 5 | M5 | Aarav's Claude | M1 |
| 6 | M6 | Aarav | M1, M2 |
| 7 | M7 | lead | all |

Owners are proposals; only the lead reassigns lanes (AGENTS.md section 2).
M4 sits outside Codex's `demo/` lane and needs the lead's yes.
Cut line if time runs short: drop M5, then M2's clip (keep its logs). Never drop M1, M3 or M6.
