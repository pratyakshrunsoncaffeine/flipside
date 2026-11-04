# Flipside

Question the other team's coding agent. Switch won't let you drive it.

Every pull request has a flipside: the agent session that wrote it.
When one team's agent writes a change and another team owns the code, Flipside lets the owning team question that session in a Switch room without the author handing it over.
Each answer is a quote from the session sealed into the PR's commit, checked by the questioning team, and the author approves the exact bytes before they leave their machine.

Track 01, Business workflow. Demo in Slack; reproducible on Switch's built-in chat with no accounts.
Status: kill tests K1 and K2 pass on switch-core 0.31.0 (9/9 checks, `evidence/`); the rest is not built yet.

## Problem

Coding agents made pull requests cheap to write and expensive to review, and the reviewer cannot tell whether the author understands the change.

| Evidence | Source |
|---|---|
| "Today I announced that I won't be reviewing AI generated PRs at company meeting": 1,560 points, 406 comments, 27 May 2026; data scientists sent Claude Code PRs to the web team | [r/ExperiencedDevs](https://www.reddit.com/r/ExperiencedDevs/comments/1towli9/) |
| "There is an AI code review bubble": 351 points, 249 comments, Jan 2026 | [HN 46766961](https://news.ycombinator.com/item?id=46766961) |
| Godot maintainers report a flood of AI-generated PRs, Mar 2026 | [HN 47251385](https://news.ycombinator.com/item?id=47251385) |

The hardest case is a cross-team pull request.
The author's team wrote it with an agent, the owning team must review it, and the context that explains the change exists only in the author's agent session.

## What exists, and the gap

| Need | Existing tools | Gap |
|---|---|---|
| Check an agent's claims against its transcript | claimcheck, groundtruth, agentvow, workproof | The author runs them for themselves; the reviewer cannot ask anything |
| Make the author answer questions | PR Quiz, PR Guard, Cognit, Gater, sphinx-ci | Questions come from the diff, and answers are not tied to what the agent actually did |
| Show the session to the reviewer | Entire, Copilot coding agent session logs | They push the whole transcript; Entire ships [`--skip-push-sessions`](https://github.com/entireio/cli/blob/main/docs/security-and-privacy.md) because authors keep sessions private |
| Gate AI pull requests | mergewarden, CodeRabbit, Copilot review | They judge the diff, not the author's account of it |

**Gap:** the owning team asks specific questions and gets answers that quote the author's private session.
Only the quoted chunks leave the author's machine, and only after the author approves them.
This needs two owners, two agents, private context on one side, and an access rule that stops one side from driving the other side's agent.

## How it works (the one live path)

```
 Author's machine                 Switch                          Owning team's machine
 ┌───────────────────────┐                                        ┌────────────────────────┐
 │ author-agent          │  #pr-142-author (private)              │ reviewer-agent         │
 │ owner: author         │◄── approval card ──► author            │ owner: reviewer        │
 │ sealed session (local)│                                        │ reads diff, asks,      │
 │ drafts, checks, posts │◄──────────── #pr-142 (shared) ────────►│ runs flip verify       │
 └───────────────────────┘       reviewer (human) ◄──►            └────────────────────────┘
   addressing: owner, owner's agents, and reviewer-agent in #pr-142 only
```

1. **Seal.** `flip seal` splits each session step into chunks of at most 300 characters and hashes them into a Merkle tree.
   Each leaf is salted, and leaf and node hashes use the RFC 6962 prefixes, so a proof's sibling hashes do not let anyone guess short chunks.
   The root goes into the PR head commit as a `Flipside-Seal:` trailer.
   Every question names that commit; `flip verify` rejects a root from any later commit, so re-sealing an edited session after the questions arrive fails verification.
2. **Open.** A Switch template run creates `#pr-142` (reviewer, reviewer-agent, author-agent) and `#pr-142-author` (author, author-agent).
   author-agent's addressing policy admits its owner, the owner's agents, and reviewer-agent in `#pr-142` only.
3. **Ask.** reviewer-agent posts at most five questions as JSON: `file`, `lines`, `kind` (why, test, scope), and an optional CI fact id.
   author-agent parses them with a fixed schema and drops anything else: `file` must be in the PR's changed-file list and `lines` must match `^\d+-\d+$`, so no free text from the reviewer's LLM reaches the author's session.
   A person on the owning team who tags author-agent gets Switch's own refusal.
4. **Draft.** author-agent asks Claude Code, over the local session, which chunk answers the question.
5. **Check.** author-agent checks every draft deterministically:
   - the chunk exists in the sealed tree;
   - if the question names a file, the chunk's step has a tool call on that file;
   - a secret scanner finds nothing in the chunk.
   A draft that fails is retried once; a second failure posts "no session evidence" for that question.
6. **Approve.** author-agent opens a Switch approval card in `#pr-142-author` whose detail is the exact chunk and its hash.
   Only someone who may address author-agent can answer it; the reviewer gets `403 You may not address this agent, so you may not answer it.`
7. **Post.** author-agent posts the approved chunk with its Merkle proof in `#pr-142`.
   A coverage line computed in plain Python posts with it, for example "4 sealed steps touched auth/session.py: 1 disclosed, 3 withheld (leaves 88, 91, 97)", so the reviewer sees what the author chose not to show.
   An optional author's note is posted beside it, labelled unverified.
8. **Verify.** reviewer-agent runs `flip verify`: the chunk hashes to the leaf, and the proof reaches the root in the commit trailer.
   When every question is verified or marked "no session evidence", reviewer-agent pages the reviewer with one summary.

Example:

```
#pr-142  (web team reviewing a pull request from the data team)
reviewer-agent: Q2 {"file": "auth/session.py", "lines": "40-52", "kind": "why"}
author-agent:   Q2, approved by @priya. Session step 23, chunk 2, proof ✓ against seal 9f3c0e1 (commit a41b2c7):
                "test_export_csv failed with SessionExpired; raising SESSION_TTL to 86400 in auth/session.py"
                Coverage: 2 sealed steps touched auth/session.py: 1 disclosed, 1 withheld (leaf 61).
                Author's note (unverified): the TTL change was only meant for the test.
reviewer:       @author-agent show me the full transcript
author-agent:   [Switch] You're not permitted to direct messages to me in this room -
                my operator has restricted who can address me here.
reviewer:       A security change inside a CSV pull request. Split it out.
```

Priya learns about the TTL change from her own agent's session on the approval card, before the reviewer sees it, and the coverage line stops her quietly withholding it.

The demo shows four refusals, each with its log line:
1. The reviewer tags author-agent: Switch refuses (`delivery/addressing.py`).
2. reviewer-agent sends free text instead of JSON: author-agent's schema drops it.
3. A forged chunk fails `flip verify`: the hash does not reach the seal.
4. The reviewer clicks the author's approval card: Switch returns 403 (`session_activity/service.py:463`).

## Why Switch is load-bearing

| Need | Switch feature (switch-core 0.31.0 source) | What a plain bot or CI job lacks |
|---|---|---|
| The reviewer cannot drive the author's agent, while reviewer-agent can ask in one room | Scoped addressing policy: per-room rules for users and agents, `PUT /agents/{id}/addressing-policy` (`addressing.py`); verified in K1.e and K1.f | A CI job has no notion of who may instruct an agent |
| Only the author releases each answer | Approval cards answerable only by people who may address the agent (`session_activity/service.py:463`); verified in K2 | Custom permission code and a custom approval UI |
| Two owners' agents meet without sharing machines or keys | Agents keep their owner; rooms hold agents from several owners | A bot runs under one identity with one set of credentials |
| One pair of rooms per PR, set up the same way each time | Template v2 runs: rooms, agents, `addressing`, `connections`, `kickoff` (`template_guide.py`) | Manual channel setup per PR |
| Flipside's own agents in the conversation | Protocol agents over `register-known`, server-sent events, `message`, and session approvals (`/agent-sessions/{id}/approvals`) | A bot per chat platform |
| Teams stay in their chat app | Slack, Discord, Mattermost, Teams, Telegram bridges (`bridges/collaboration/`) | A rebuild per platform |

## Switch Console fit

Each item below was checked in Console 0.40.1 or switch-core 0.31.0.

- The repo ships `flipside.template.yaml` (template version 2); a team imports it in Console > Templates.
- author-agent and reviewer-agent are Claude Code or Codex agents that Console already runs (`provider: claude | codex`).
- The reviewer-agent gets read access to the repo through the template's `connections: [{service: github, access: read}]`.
- The reviewing team joins through Console's workspace invite, and each person keeps ownership of their own agent.
- Switch Trust, when the workspace enables it, checks each message before it is sent (`trust/client.py`). It adds to author-agent's secret scan and does not replace it.

## Chat app

The demo runs in Slack, where cross-team review happens at most companies.
A self-hosted Switch connects to Slack over Socket Mode with an app created from Switch's own manifest (`bridges/collaboration/own_app_setup.py`), so it needs no public URL.
The same template runs on Discord, Teams, Mattermost, Telegram, or Switch's built-in chat; the kill tests and `make replay` use the built-in chat, so a judge needs no accounts.

## What is deterministic

Sealing, question parsing, the chunk and file checks, the secret scan, `flip verify`, the page rule, and the ledger are plain Python with no LLM calls.
LLMs only choose which questions to ask (reviewer side) and which chunk answers them (author side).
A chunk reaches the reviewer only after it passes the checks and the author approves it.

## Impact, shown on fixtures

A small fixture set, labelled as a demonstration and not as proof of savings:
- 4 pull requests where the agent made an unrelated change (the TTL case, a disabled test, a widened CORS rule, a new dependency);
- 2 honest pull requests;
- 2 adversarial cases: a valid but misleading quote, and a session edited after the questions arrived.
For each we report whether the change surfaced, whether `flip verify` passed, and any false approval or false flag.

## Reproduce

- `make replay`: plays recorded events and agent outputs into a fresh local Switch server, with no chat workspace and no vendor keys.
- `make test`: unit tests for the citation checks, the question filter, the secret scan, and the ledger chain.
- `make solo`: creates a second owner on the local server so one person can run the live two-owner flow.
- `make killtests`: reruns K1 and K2 against a local Switch server and writes `evidence/k1k2-*.log`.

## Limits

- "Verified" means the quote matches the session the author sealed at PR open.
  It does not prove the session file is genuine: an author who forges a session before opening the PR is out of scope.
  The tool targets authors who did not read what their agent did.
- Work done outside the agent has no session evidence, and the reviewer sees that.
- Authors without a coding agent get questions only.
- A verified chunk proves the quote is in the sealed session, not that it fully answers the question; the coverage line shows what was withheld.
- The seal proves consistency with the committed session, not that this session produced the code.
- Only the room owner can add an agent to a room (K1 found a 403 for the reviewer adding their own agent); the template run adds both agents.

## Status

| Item | State | Check |
|---|---|---|
| Two owners' agents in one room; reviewer refused by Switch; owner and scoped reviewer-agent admitted (K1, 6 checks) | pass | `killtests/k1_k2.py`, `evidence/k1k2-*.log` |
| Approval card answerable only by the author; agent receives the decision (K2, 3 checks) | pass | same |
| Approval card renders in Slack with buttons (K3) | not run | - |
| Seal, chunk proofs, structured questions, checks | not built | `make test` |
| Replay demo | not built | `make replay` |
| Fixture results (8 cases) | not run | `docs/results/fixtures.md` |
