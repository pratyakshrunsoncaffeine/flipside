# Kickoff prompts

Paste one of these into a fresh Claude Code session started in the repo root.
Use the lead prompt on Aarav's Mac and the teammate prompt on the teammate's machine.

## Lead (seal lane, then shared and live milestones)

```
You are building Flipside, our entry for the Flip the Switch hackathon (Track 01), in this repo.
The deadline is 7 Nov 2026 23:59 IST.

Read these files completely, in this order, before doing anything else:
1. AGENTS.md (team rules, board, lanes, hard limits)
2. HANDOFF.md (current state, decisions, dead ends)
3. docs/BUILD.md (what to build, milestones, gates)
4. docs/seal/SPEC.md (normative spec for flipside/seal/)
Treat them as the source of truth. Do not reopen decisions listed in HANDOFF.md.
If two files disagree, docs/seal/SPEC.md wins for seal formats, docs/BUILD.md wins for everything else; post the conflict on the board.

Your lane: Seal (owner @kadoo69), plus the shared files and milestones M3 to M6 once the room lane delivers M2.

Start:
1. Run `tools/board whoami` and `tools/board unread`. If the board is not set up yet, continue without it and note that in your first report.
2. Keep one background `tools/board wait` running; re-arm it after each wake. Act on posts that mention @kadoo69 or @all.
3. If M0 is not done (no pyproject.toml, no `make test`/`make lint`), do the M0 parts that live in shared files: pyproject.toml (Python 3.12+, runtime stdlib only, dev: pytest, ruff, mypy), Makefile targets `test`, `lint`, `killtests`. Run `make killtests` and confirm 9/9 against the local Switch server.
4. Build M1 exactly as docs/BUILD.md and docs/seal/SPEC.md describe:
   - tests first, one module at a time: canon, merkle, steps, seal, prove, verify, coverage, secrets;
   - then `flip seal | prove | verify` in flipside/cli.py;
   - update docs/seal/example.py to v1.1 and pin tests/vectors/seal_v1_1.json;
   - write examples/q2-ok.json and examples/q2-forged.json with a matching manifest and seal commit bundle;
   - check every gate G1 to G8 with the command that proves it.
5. When all M1 gates are green, run `make lint test` twice, write evidence/m1-<YYYYMMDDTHHMMSS>.log with the gate outputs, and post on the board: the gates, the commands, the evidence file, and the public interface the room lane imports (verify, prove, coverage, manifest loader).
6. Then continue in milestone order: M3 needs M2 from the room lane; until it lands, do K4 (killtests) and prepare `make solo` plumbing in shared files, asking on the board before touching flipside/room/.

Working rules:
- Work through the milestones without stopping to ask, except for the stop conditions below.
- A gate is green only when its command passes or its evidence file exists. Never mark a gate green from reasoning alone.
- Reproduce any bug end to end, write a failing test, fix it, then search for the same bug elsewhere.
- Never print or commit secrets: the Switch env file values, API and agent keys, seal keys in .git/flipside/, killtests/.local-users.json.
- No LLM calls anywhere in flipside/. Runtime is the Python standard library only.
- Never use the em dash; use a plain "-". Times in IST. Each Markdown sentence on its own line.
- Commit in small steps on a branch named <issue#>-<slug>, staging only your own files. Never add an agent as co-author. Do not push or open a PR without my go-ahead unless the repo and board already exist and AGENTS.md section 4 applies.

Stop and ask me when:
- a gate cannot go green after two real attempts (show the failing output);
- the spec is ambiguous in a way that changes a byte format or a message format;
- you need my Slack login (K3), a new dependency, or to touch another lane's folders without the owner's reply;
- a kill rule in docs/BUILD.md section 10 would trigger.

Report after each milestone, in under 15 lines: gates and their commands, evidence files, what changed, what is next, anything you need from me.
Before your context runs low, update HANDOFF.md (state, decisions, dead ends, next step) so a new session can continue.
```

## Teammate (room lane)

```
You are building Flipside, our entry for the Flip the Switch hackathon (Track 01), in this repo.
The deadline is 7 Nov 2026 23:59 IST.

Read these files completely, in this order, before doing anything else:
1. AGENTS.md (team rules, board, lanes, hard limits)
2. HANDOFF.md (current state, decisions, dead ends)
3. docs/BUILD.md (what to build, milestones, gates); sections 3 to 9 are your contract
4. docs/seal/SPEC.md (formats you consume: manifest, disclosure, verify codes)
5. docs/SETUP-REPO.md, if the GitHub repo and board do not exist yet
Treat them as the source of truth. Do not reopen decisions listed in HANDOFF.md.

Your lane: Room (owner @<teammate-login>): flipside/room/, tests/room/, templates/, replay/, fixtures/.

Start:
1. If the repo or board is missing, do docs/SETUP-REPO.md first, then fill your login into AGENTS.md and open that as the first PR.
2. Run `tools/board whoami` and `tools/board unread`. Keep one background `tools/board wait` running; re-arm it after each wake. Act on posts that mention you or @all.
3. Build M2 against FakeTransport, tests first:
   - protocol.py (message types and sender rules from docs/BUILD.md section 6, strict schema parsing);
   - github.py behind an interface, with recorded fixtures so tests never call GitHub;
   - gaps.py, select.py, contradictions.py, brief.py (sections 7.1 to 7.5), each rule with a firing and a non-firing test;
   - author_agent.py and reviewer_agent.py as state machines over the Transport protocol;
   - fixtures/honest (zero gaps) and the CSV-export scenario;
   - `make replay-offline`.
   Until the seal lane posts its interface, use a stub verifier with the same signature and swap it when M1 lands.
4. Port useful logic from the earlier Ownership Gate code if you have it (transcript parsing, command classification, contradiction rules), but the formats in docs/BUILD.md and docs/seal/SPEC.md win.
5. Start switch_client.py from killtests/switch_api.py; do not run live Switch tests until M2 is green.
6. When all M2 gates are green, run `make lint test` twice, write evidence/m2-<YYYYMMDDTHHMMSS>.log, and post on the board with the gates, commands and evidence file, tagging @kadoo69.
7. Then help M3 and run the M4 clean-clone check on your machine when the lead asks.

Working rules:
- A gate is green only when its command passes or its evidence file exists.
- No LLM calls anywhere in flipside/. Runtime is the Python standard library only.
- Never print or commit secrets. Never add an agent as co-author. Never use the em dash; use a plain "-". Times in IST.
- Ask on the board before touching another lane's folders. Changes to the room message formats or the seal contract need an @all post before merging.

Stop and ask your human when a gate cannot go green after two real attempts, the spec is ambiguous about a format, or a kill rule would trigger.
Report after each milestone in under 15 lines, and keep HANDOFF.md current before your context runs low.
```
