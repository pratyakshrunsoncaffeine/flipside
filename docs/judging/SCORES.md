# Agent judge scores

Prompt: `JUDGE-PROMPT.md` + `PITCH.md` (a plan; nothing built). Weights: Switch 30, Technical 25, Creativity 25, Presentation 20.

| Round | Pitch | Judge | Switch | Technical | Creativity | Presentation | Total | Shortlist |
|---|---|---|---|---|---|---|---|---|
| 1 | Ownership Gate | Claude Opus 5.5 | 7 | 5 | 7 | 7 | 6.5 | yes, narrowly |
| 1 | Ownership Gate | Codex gpt-6-luna | 7 | 2 | 6 | 4 | 4.9 | no |
| 2 | Deposition (verified claims, one path, status table) | Claude Opus 5.5 | 8 | 2 | 7 | 7 | 6.05 | no |
| 2 | Deposition | Codex gpt-6-luna | 8 | 2 | 8 | 4 | 5.7 | no |

Round 2 to round 3 changes (not yet judged): session sealed into a Merkle root in the PR description at open; reviewer-side `flip verify`; structured questions only; approval bound to a hash of the exact bytes; 30 fixtures at a 20% base rate with reviewers who did not build it; cited source lines.

Both judges' remaining top deduction: nothing runs. Only K1, K2, `make test`, and `make replay` fix it.

## Head-to-head vs Treaty (4 Nov), prompts and outputs in `h2h/`

Field sample: 31 public hackathon repos (`h2h/FIELD.md`). Dev workflow (incident, bug-to-PR, PR review) is 11-12 of ~23 described entries; pure PR review/gates 3; API-change coordination 0.

| Run | Flipside | Treaty | Pick |
|---|---|---|---|
| Claude single (plan as is) | 6.1 | 5.6 | - |
| Codex single (plan as is) | 5.85 | 4.95 | - |
| Claude pairwise, Flipside first (if built) | 7.50 | 6.20 | Flipside |
| Claude pairwise, Treaty first (if built) | 8.05 | 6.75 | Flipside |
| Codex pairwise, Flipside first (if built) | 8.25 | 8.50 | Treaty |
| Codex pairwise, Treaty first (if built) | 8.50 | 8.38 | Treaty (crowding) |

All four pairwise runs file Flipside under "AI PR review"; all name that as its biggest risk.
New design gaps found: reviewer-side substring check needs the full step bytes (fix: Merkle leaves = quotable chunks); root in an editable PR description (fix: check run or commit trailer); LLM paraphrase shown beside verified quotes; hero refusal is Switch default, so also show Flipside's own blocks.

## Round 3 (after K1/K2 pass, repositioning, chunked seal), 4 Nov

| Judge | Switch | Technical | Creativity | Presentation | Total | Shortlist |
|---|---|---|---|---|---|---|
| Claude Opus 5.5 | 8 | 4 | 7 | 7 | 6.55 | yes, conditional on `make replay` from a clean clone |
| Codex gpt-6-luna | 9 | 4 | 8 | 5 | 6.7 | no |

Fixed after round 3: false "same moment" claim; ellipsis in a quote that must hash; seal pinned to the questioned commit; coverage line (disclosed vs withheld); salted leaves with RFC 6962 prefixes; file must be a changed file, lines regex; fixture study cut to 8 labelled cases incl. 2 adversarial.
Remaining top deduction from both: most of the product is unbuilt.

## Blind round (2026-11-04 ~19:00 IST)

Neutral prompt: official rubric only, no panel-preference hints, no history. Flipside = PITCH.md + seal spec. Files in `blind/`.
Note: Claude ran with cwd in the flipside repo and guessed X was ours; it says it scored all four the same way. Codex agrees on the result.

| Entry | Claude | Codex |
|---|---|---|
| Flipside (plan), run 1 / run 2 | 7.1 / 7.1 | 6.2 / 6.5 |
| LedgerRoom (built, CI, video) | 7.3 | 8.5 |
| Preflight (built, 240+ tests) | 7.7 | 7.4 |
| Canary (built, live site) | 7.0 | 7.6 |

Blind ranking of all four, anonymised: Claude W(LedgerRoom) Y(Preflight) X(Flipside) Z(Canary); Codex W Y Z X.
Flipside per criterion in the ranking: Switch 9/9, Technical 3/2, Creativity 9/9 (highest of the four for both), Presentation 6/6.

## Final README, blind (5 Nov 2026, 10:45 to 11:00 IST)

Same neutral prompt as the blind round (`blind/head.txt`, the README as the only material, `blind/single-tail.txt`).
Judges were fresh Claude Opus 5.5 subagents that read only the prompt file.
Prompts: `blind/final-prompt-a.txt` (README at `5ec12a4`, after #22), `blind/final-prompt-b.txt` (this PR: walkthrough, diagram, terms).
Outputs: `blind/claude-final-a1.out`, `a2`, `b1`, `b2`.

| README | Run | Switch | Technical | Creativity | Presentation | Total | Shortlist |
|---|---|---|---|---|---|---|---|
| a (after #22) | 1 | 8 | 8 | 7 | 6 | 7.4 | yes |
| a (after #22) | 2 | 8 | 9 | 7 | 6 | 7.6 | yes |
| b (walkthrough, diagram, terms) | 1 | 8 | 9 | 7 | 7 | 7.8 | yes |
| b (walkthrough, diagram, terms) | 2 | 8 | 8 | 7 | 7 | 7.6 | yes |

Shared deductions on b: the offline stand-in makes Switch look replaceable; people cannot answer in Slack (no user id on Slack-typed messages); no evidence that teams want it; author and reviewer on two machines not run; jargon still dense.
After b, the README gained the public demand evidence and a paragraph on why the offline stand-in does not replace Switch; not judged yet.
