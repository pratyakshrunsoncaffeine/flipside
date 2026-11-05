# Flipside design

How Flipside works, the messages its two agents exchange, the deterministic rules behind every question and verdict, and the Switch API facts it relies on.
The seal and disclosure formats are in [seal/SPEC.md](seal/SPEC.md).

## 1. The product

A data team's coding agent writes a pull request for code another team owns.
The owning team needs to know why the agent changed what it changed, but the agent session that explains it is private to the author.
Flipside seals that session into the PR as one Merkle root before review.
In a Switch room, the owning team's agent asks deterministic questions built from public data (PR text, diff, CI, the sealed manifest), names the exact session steps it wants to see, and verifies every quote the author approves against the root in git.
The author answers in their own words and releases each quote on a Switch approval card only they can answer.
The rest of the session never leaves the author's machine.
Switch is the only place the two owners' agents can meet: its addressing policy stops the reviewer from driving the author's agent, and its approval cards stop anyone but the author from releasing a quote.

## 2. Architecture

```
 Author's machine (owner A)              Switch                                  Reviewer's machine (owner B)
 ┌──────────────────────────┐   #pr-142-author (private: A, author-agent)    ┌──────────────────────────┐
 │ Claude Code session JSONL│◄── approval cards, one per requested leaf ──►A │ reviewer-agent (owner B) │
 │ (private, never leaves)  │                                                │ polls GitHub PRs         │
 │ flip seal / flip prove   │   #pr-142 (shared: A, B, both agents)          │ gaps.py  (public data)   │
 │ author-agent (owner A)   │◄──────────────────────────────────────────────►│ flip verify + coverage   │
 │  secret scan, disclose   │  seal line + manifest attachment, questions,   │ brief, pages reviewer    │
 └────────────┬─────────────┘  answers, requests, disclosures, verdicts      └────────────┬─────────────┘
              │ push empty seal commit (Flipside-Seal: trailer)                           │ read PR, diff, CI, trailer
              └──────────────────────────────► GitHub ◄───────────────────────────────────┘
 author-agent addressing: owner, owner's agents, and reviewer-agent in #pr-142 only
 reviewer (human) tagging author-agent gets Switch's own refusal
```

Trust split: the side that benefits from a check runs it.
The reviewer's side computes gaps, picks leaves, verifies proofs and counts what was withheld, from public data.
The author's side only seals, scans for secrets, and discloses what the author approves.

No LLM sits in any deciding path.
Seal, verify, gaps, leaf selection, contradiction checks, coverage, the page rule and the ledger are plain Python.
The LLM work in the story is the author's own coding agent, whose session is what gets questioned.

## 3. End-to-end flow for one PR

1. **Seal.** Before opening the PR, the author runs `flip seal --base origin/main`.
   It seals the session (`docs/seal/SPEC.md`), stores the key under `.git/flipside/`, and adds an empty commit with the `Flipside-Seal:` trailer.
   The author pushes and opens the PR.
2. **Detect.** reviewer-agent polls open PRs on the watched repo (`gh api`), and finds the head commit chain contains a `Flipside-Seal:` trailer.
   A PR with no seal gets questions only (no evidence), and the brief says so.
3. **Open rooms.** The reviewer's side creates `#pr-<n>` (shared) and the author's side creates `#pr-<n>-author` (private): `flip setup` calls `POST /gateway/rooms` as each owner (`flipside/room/setup.py`).
   There is no Switch room template yet.
   The room owner adds both agents (K1 found that only the room owner can add an agent).
   author-agent's addressing policy is set to: owner, owner's agents, and reviewer-agent in `#pr-<n>` only (`PUT /gateway/agents/{id}/addressing-policy`).
4. **Publish the seal.** author-agent posts the `seal` message and uploads `manifest.json` as a room attachment.
   reviewer-agent downloads it and checks its SHA-256 against the trailer (`MANIFEST_HASH`).
5. **Gaps.** reviewer-agent computes gaps from PR title and body, changed files, CI check runs on the seal commit, and the manifest (section 5).
   It posts at most five numbered questions.
   An honest PR with no gaps gets a clean brief at once.
6. **Answers.** The author answers in their own words in `#pr-<n>`, one message per question, starting `Q<k>:`.
   reviewer-agent reads only messages whose sender is the PR author's Switch user.
7. **Requests.** For each gap with session evidence, reviewer-agent posts a `request` naming leaf indexes from the manifest (section 5.3), addressed to author-agent.
8. **Approve.** For each requested leaf, author-agent runs the secret scan, then opens one Switch approval card in `#pr-<n>-author`.
   The card detail is the exact leaf text and its hash.
   A leaf that fails the secret scan is withheld without a card, with reason `secret_scan`.
   Only the author can answer; the reviewer gets `403 You may not address this agent, so you may not answer it.`
9. **Disclose.** On approve, author-agent runs `flip prove` and posts a `disclosure`.
   On decline, it posts `withheld`.
10. **Verify.** reviewer-agent runs the seven checks against the commit the question named, posts a `verdict` per leaf, runs the contradiction rules on verified bytes, and updates coverage.
11. **Brief.** When every question is answered (or timed out, section 5.5) and every requested leaf is verified or withheld, reviewer-agent posts the `brief` and mentions the reviewer.
12. **New head.** A new head commit with a new seal starts a new round; old verdicts stay pinned to their commit.

## 4. Room protocol

Every machine message is one human-readable line, then one fenced JSON block.
Parsers read only the JSON block, and accept a message only from the sender the table names, checked by Switch sender id, never by message text.

| Type | Sender | JSON |
|---|---|---|
| `seal` | author-agent | `{"t":"seal","v":1,"pr":142,"commit":"<sha>","root":"<hex>","n":212,"manifest":"<hex>","mxc":"<media uri>"}` |
| `questions` | reviewer-agent | `{"t":"questions","v":1,"commit":"<sha>","qs":[{"q":1,"gap":"SCOPE","file":"auth/session.py","text":"…"}]}` |
| answer | PR author (human) | Free text starting `Q<k>:`; no JSON. In a messaging-app room the author types `@flipside-author-agent Q<k>: <text>` in either room instead |
| `answer` | author-agent, relaying the author | `{"t":"answer","v":1,"commit":"<sha>","q":1,"text":"…","src":"<author message id>"}`; posted once per source message that Switch addressed to author-agent for its owner |
| `request` | reviewer-agent, addressed to author-agent | `{"t":"request","v":1,"commit":"<sha>","q":1,"leaves":[41,57]}` |
| `disclosure` | author-agent | The SPEC disclosure object plus `"t":"disclosure","q":1` |
| `withheld` | author-agent | `{"t":"withheld","v":1,"commit":"<sha>","q":1,"i":57,"reason":"author|secret_scan|session_changed"}` |
| `verdict` | reviewer-agent | `{"t":"verdict","v":1,"commit":"<sha>","q":1,"i":41,"code":"OK|PROOF_FAIL|…","ref":"<disclosure message id>","leaf":{…}}`; `leaf` only when `OK` |
| `brief` | reviewer-agent, mentions the reviewer | `{"t":"brief","v":1,"commit":"<sha>","pr":142,"seal":"…","gaps":[…],"not_asked":[…],"coverage":[…],"contradictions":[…],"refused":[…]}` |

Each `coverage` entry is `{"file","sealed","disclosed","not_disclosed":[[session,step],…],"by_mention","line"}`; `line` reads `auth/session.py: 2 sealed steps, 1 disclosed, 1 not disclosed (step 6)`.
"Withheld" means only an author's decision: a `withheld` message (declined card, secret scan, changed session) and the brief's count of them.
Coverage says "not disclosed" for every sealed step without a verified leaf, asked for or not.

reviewer-agent posts one verdict per disclosure message, also after the brief, so a forged copy posted late is still refused in the room.
`session_changed` is posted when the author approved a leaf but the session's sealed prefix no longer matches (F1), so no proof can be built.

Example of the human line for a disclosure:
`Q1 · step 3, chunk 0 · approved by @priya · proof against seal 50ab222 (commit a41b2c7)`.

Free text from reviewer-agent never reaches the author's session: author-agent parses `request` with a fixed schema (`leaves` is a list of integers below `n`, `q` an integer, `commit` 40 hex) and drops everything else.
That is refusal 2 in the demo.

## 5. Deterministic rules (reviewer side)

### 5.1 Inputs

PR title, PR body, changed files with line ranges, check runs on the seal commit, the manifest, and the seal trailer.
All public.

### 5.2 Gap rules

Evaluated in this order; at most five questions per round, the rest listed in the brief as "not asked".

| Gap | Fires when | Question text |
|---|---|---|
| `CI` | A check run on the seal commit concluded `failure` | "Check `<name>` failed on the sealed commit. What happened?" |
| `TESTS` | PR body matches `\btests? (pass|passed|passing|green)\b` (case-insensitive) and either no manifest step has `cmd: test`, or the last `cmd: test` result step that ran has `ok: false`. A result with `ok: null` never ran (SPEC C14) and is skipped | "The PR says tests pass. The last sealed test run did not pass (step `<t>`). Which run is right?" or "…no sealed step ran tests…" |
| `SCOPE` | A changed file F is not mentioned in the PR title or body (path, or basename without extension, case-insensitive; a test file such as `tests/test_report.py` also counts as mentioned when the body says it adds or changes tests, e.g. "with tests" or "tests for", and names its subject `report`), and at least one sealed step has F in `files` or `mentions` | "`F` changed and the PR description does not mention it. Why?" |
| `UNSEALED` | A changed file F has no sealed step touching it | "No sealed step touched `F`. Was it changed outside the agent?" |
| `LINT`, `BUILD` | PR body claims the check passed (e.g. "ruff is clean", "lint passes", "build succeeded", "builds cleanly"; see `CLAIMS` in `rules.py`) and either no step with `cmd: lint` (or `build`) ran, or the last one that ran has `ok: false` | "The PR says lint passes. The last sealed lint run did not pass (step `<t>`). Which run is right?" or "…no sealed step ran lint…" |
| `RERUN` | `TESTS` did not apply (no pass claim) and the last `cmd: test` result that ran has `ok: false` | "The last sealed test run failed (step `<t>`) and no later test run is sealed. Was it fixed?" |
| `SIZE` | Added plus deleted lines, lockfiles excluded, exceed 400 | "This PR changes `<n>` lines (lockfiles excluded; limit 400). Can it be split? If not, which part should the reviewer read first?" |

`LINT`, `BUILD`, `RERUN` and `SIZE` are ported from the team's earlier Ownership Gate prototype.
They come after the four rules above, so they are asked only when fewer than five gaps fire before them.

The honest cases (`fixtures/cases/honest-*`) must give zero gaps.
Every rule has a unit test with one firing and one non-firing fixture.

### 5.3 Leaf selection

| Gap | Leaves requested |
|---|---|
| `CI`, `TESTS`, `RERUN` | All leaves of the last `cmd: test` call step and its result step before the seal commit |
| `LINT`, `BUILD` | The same, for the last `cmd: lint` (or `build`) call and result |
| `SCOPE` | All leaves of the most recent step that edited F (Edit, Write, MultiEdit, NotebookEdit; if none, the most recent step that mentions F), plus the leaves of the assistant text step just before it, never reaching back past a user step |
| `UNSEALED`, `SIZE` | None; the answer is text only |

Cap: 8 leaves per question, most recent first.
The author may offer extra leaves with an author-initiated `disclosure`; reviewer-agent verifies them the same way.
Typical clean case: the author offers the prompt leaf that asked for the change ("also raise the session TTL"), and the `SCOPE` gap closes with evidence.

### 5.4 Contradiction rules (on verified bytes only)

| Rule | Fires when |
|---|---|
| `C-TESTS` | The author's answer matches `\b(pass|passed|green)\b` and a verified leaf for that question has `ok: false` or contains `FAILED`, `Error:`, or `exit code [1-9]`. A Bash result that never ran (SPEC C14) never counts |
| `C-FILE` | A verified edit-step leaf requested for file F has neither F in `files` nor in `mentions` (selection bug; must never fire, tested). The text step before it is context and is not checked |

The brief lists contradictions; it never hides them and never blocks on them.

### 5.5 Page rule

reviewer-agent posts the brief and mentions the reviewer when every question has an answer, or when a fixed timeout passes (default 30 minutes, `FLIP_ANSWER_TIMEOUT`), and every requested leaf is verified or withheld.
A question with no answer is marked "no answer".
A refused verdict (`PROOF_FAIL` and the other codes) does not settle a leaf; only `OK` or `withheld` does, and the timeout lists the rest.

## 6. Author side rules

- author-agent acts only on `request` messages from reviewer-agent's agent id, and on approval outcomes from its own session.
- Secret scan on every leaf before a card opens: AWS keys, GitHub tokens, private key blocks, `.env`-style `KEY=value` with high entropy, JWTs.
  A hit withholds the leaf with reason `secret_scan` and never shows the bytes on a card.
- One approval card per leaf, in `#pr-<n>-author`, options approve (accept) and decline (decline).
  Card title: `Disclose step <t> chunk <c> to #pr-<n>?`; detail: the exact text and `sha256(leaf)[:12]`.
- Cards are opened with `POST /agent-sessions/{sid}/approvals` and outcomes read from `GET /agent-sessions/approvals/outcomes` (both proven in K2).
- `flip prove` runs only after an accept outcome for that exact leaf.
- The author may offer more leaves from `#pr-<n>-author`: `@flipside-author-agent offer Q<k> step <t>` (every chunk of main-session step t) or `offer Q<k> leaf <i>`.
  Only the author's own messages that Switch delivered as addressed count; each offered leaf goes through the same scan and card.
- `n` and the manifest come from the stored seal state, so an author-agent restarted after the session was rewritten still runs, and withholds requested leaves with `session_changed`.

## 7. Switch facts (switch-core 0.31.0, verified)

| Need | Call | Notes |
|---|---|---|
| Users, login | `POST /gateway/users`, `POST /gateway/auth/login` | Cookie auth; admin creds in the Console env file |
| API key per user | `POST /gateway/api-keys {label}` | |
| Register an agent | `POST /agents/register-known {agent_type, name, description, options, overwrite}` | Returns `id`, `api_key` |
| Create a chat room | `POST /gateway/chats {requestId, name, agentIds}` | Room id at `chat.roomId` |
| Add a member | `POST /gateway/chats/{room}/members {userId}` | |
| Add an agent | `POST /gateway/rooms/{room}/agents {agent_ids}` | Only the room owner; the reviewer adding their own agent to the author's room gets 403 |
| Scoped addressing | `PUT /gateway/agents/{id}/addressing-policy {"policy":{"rules":[…]}}` | Rule fields: rooms, room_groups, users, agents, owner, owner_agents, platform |
| Agent events | `GET /agents/{id}/events?connection_id=&scope=all&filter=all&start_from=head&rooms=` (SSE) | Beat `POST /agents/{id}/connection/beat` every 2 s; events carry `payload.addressed` |
| Agent posts | `POST /agents/{id}/message {room_id, content}` | |
| Human posts | `POST /gateway/chats/{room}/messages {requestId, body, mentionAgentId}` | |
| Attachments | `POST /agents/{id}/rooms/{room}/media` (multipart `file`), `GET` same path `?mxc=` | Capped by `agent_media_max_bytes` |
| Approval cards | `POST /agent-sessions/{sid}/started {start_source:"room"}`, `POST /agent-sessions/{sid}/approvals` | Agent endpoints take snake_case bodies; responses are camelCase (422 otherwise) |
| Answer a card | `POST /gateway/agent-sessions/{agent}/{sid}/approvals/{req}/answer {answer}` | Non-addressers get 403 (`session_activity/service.py:463`) |
| Outcomes | `GET /agent-sessions/approvals/outcomes` | |
| Refusal text | `delivery/addressing.py` ADDRESSING_DENIED_MESSAGE | Match it in code by the substring `not permitted to direct messages`; in docs write its dash as a plain `-` |

Learned on the live server:

- An agent API key cannot read `GET /gateway/chats/{room}/messages` (401). Each agent reads the transcript through its owner's gateway session and takes `addressed` from its own event stream; both carry the same `sw_…` message id.
- A chat's first agent receives untagged messages, so its policy decides those too: reviewer-agent admits author-agent and the room's people in `#pr-<n>`, or it posts a refusal to every answer.
- A rule's `users` entry matches a person's member client id, which the gateway does not expose; reviewer-agent's room rule therefore uses `users: "*"` in its own room.
- Agent names are unique per server: the same two users own the two agents in the kill tests and in `make solo`.
- Approval outcomes stay listed until acknowledged; a restarted author-agent sees them again and rebuilds its state from the transcript. `make solo` uses a fresh agent session per run, so old outcomes never carry over.

Local server: `http://127.0.0.1:52370` (Switch Console), native, no Docker needed.
The gateway OpenAPI is at `/gateway/openapi.json`.
Switch mediation hooks (`/agents/{id}/mediation/*`) do not record tool calls, so they cannot serve as an independent session log.
