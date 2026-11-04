# DeskPilot: AI support triage that a human signs off, in team chat via Switch

**Flip the Switch Hackathon 2026 · Best Business Workflow**

DeskPilot is an AI teammate for a customer-support team. It sits in a Mattermost channel connected through [Switch](https://github.com/sandbox-quantum/switch), and it does the slow part of every ticket: classify it, find the policy rule that applies, work out the refund or credit, and write the reply. Then it stops and waits. **Nothing reaches a customer until a person in the channel says `approve`.**

🎬 **Demo video (1:45):** https://youtu.be/UGVRk4aICCA

![DeskPilot triage card in Mattermost](docs/screenshots/02-triage-card.png)

## The workflow

| Step | Who | What happens in the chat |
|---|---|---|
| 1 | Support agent (Sam) | Pastes a customer ticket and mentions `@deskpilot` |
| 2 | DeskPilot | Replies **in the thread** with a triage card: category, priority (P1–P3), sentiment, the exact policy clause, the proposed action (refund or credit), and a draft reply |
| 3 | Sam | Types `approve`. The refund is above the $100 auto-approval limit, so DeskPilot **refuses** and asks a support lead |
| 4 | Lead (Raja) | Types `edit: tell them we keep their data for 30 days`. DeskPilot revises and posts draft v2 |
| 5 | Lead (Raja) | Types `approve`. DeskPilot releases the reply to the outbox, queues the refund for Finance, and updates the **`ticket-ledger` room document** |
| 6 | Anyone | A security ticket comes in. DeskPilot flags it **P1**, creates a linked **`#oncall-escalations`** room for on-call and posts the case there |
| 7 | Anyone | `@deskpilot summary` posts the desk as one table: decided, by whom, and what is still waiting on a human |

`reject <reason>` closes a ticket with nothing sent. Every decision is logged with who made it and when.

## How Switch is used (and why it matters here)

Switch is the backbone, not a wrapper. DeskPilot is a **custom agent written against the Switch agent protocol** (SSE down, HTTP up), with no SDK:

| Switch feature | Where DeskPilot uses it |
|---|---|
| Agent registration (`POST /agents`, registration token) | `scripts/register_agent.sh` registers DeskPilot as an `always_on` agent with its own API key |
| Event stream (`GET /agents/{id}/events`, `scope=single`, room declared on the URL) + 2 s heartbeat (`/connection/beat`) | `Desk.stream()` / `Desk.heartbeat()` in `deskpilot/agent.py`; same connection id across reconnects, `Last-Event-ID` resume |
| `message.addressed` + `thread_id` on events | Mentions start a ticket; replies in a ticket's thread are the human decisions |
| `create_room` (bridged to Mattermost, with people) | Creates `#helpdesk` for the desk and `#oncall-escalations` for P1s |
| `linked_rooms` | The escalation room links back to the desk room it came from |
| `connect_to_room` + `post_message(thread_id=…)` | Threaded triage cards and decisions |
| Room documents (`create_room_document`, `update_room_document`) | `support-policy` (the rules the agent quotes) and `ticket-ledger` (the audit trail), shared with everyone in the room |
| `POST /agents/{id}/message` | Posting into the escalation room without moving the connection's claim |
| Addressing policy (Gateway API) | Opened so every teammate in the room, not only the owner, can address DeskPilot |
| Collaboration bridge (Mattermost) | People never leave their chat app; agent posts appear as the DeskPilot bot |

```
Mattermost #helpdesk  ⇄  Switch core (Postgres bus, rooms, docs, access)  ⇄  DeskPilot  →  LLM
     people type here            bridge + agent bridge                         SSE in / HTTP ops out   Gemini or any
                                                                                                         OpenAI-compatible API
```

Governance lives in the workflow: refunds or credits above $100 (and every P1) need someone in `DESKPILOT_LEADS`, a rule enforced in code rather than left to the model; the agent can never send without a human message in the thread; every decision is written to a room document the whole team can read.

## Run it yourself

### Option A: Switch's own dev stack (Docker)

```bash
# 1. Switch server + Postgres + Mattermost (bundled 'collab' setup)
git clone https://github.com/sandbox-quantum/switch && cd switch
just init-env          # writes .env with fresh secrets
just up                # Postgres + Mattermost in Docker, seeds team 'switch' and user 'user'
just run               # switch-core on :8000 (keep running)

# 2. DeskPilot
cd .. && git clone https://github.com/hassaanraja282-lgtm/deskpilot-switch && cd deskpilot-switch
pip install -r requirements.txt
SWITCH_DIR=../switch DESKPILOT_ROOM_USERS=user DESKPILOT_LEADS=user ./scripts/register_agent.sh
set -a; . ./.env.deskpilot; set +a
# optional: export GEMINI_API_KEY=...   (default is a keyless OpenAI-compatible endpoint, rate-limited)
python -m deskpilot.agent
```

Open Mattermost at http://localhost:8065 (user `user`, password from Switch's `.env`), go to the new **helpdesk** channel and post:

```
@deskpilot New ticket from dana@northwind.dev: We bought the Annual Team plan 9 days ago ($180, invoice INV-5520) but we're consolidating tools. Can we cancel and get our money back?
```

Then reply in the thread with `approve`, `edit <change>` or `reject <reason>`, and try `@deskpilot summary`.

### Option B: no Docker (how the demo was recorded)

The demo ran on a plain Debian arm64 box with no Docker: Postgres 17 from apt, the Mattermost release tarball, and switch-core from source (`uv sync` in `switch/core`). `dev/sandbox-up.sh` and `dev/seed.sh` are the exact scripts (they reuse Switch's own `deploy/shared_resources/setup.py` to seed Mattermost and register the bridge).

### Configuration

| Variable | Meaning |
|---|---|
| `SWITCH_URL` | Switch agent bridge, e.g. `http://localhost:8000` |
| `DESKPILOT_AGENT_ID`, `DESKPILOT_API_KEY` | From registration |
| `DESKPILOT_ROOM` | Room/channel to run the desk in (default `helpdesk`) |
| `DESKPILOT_ROOM_USERS` | Chat usernames added to the rooms DeskPilot creates |
| `DESKPILOT_LEADS` | Usernames allowed to approve tickets the policy reserves for a lead |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Use Gemini (default `gemini-2.5-flash`) |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Otherwise any OpenAI-compatible chat endpoint (default keyless `text.pollinations.ai`, 1 reply / 45 s per IP) |

The policy the agent enforces is plain Markdown in `deskpilot/policy.md`; change it and restart.

## Files

```
deskpilot/agent.py     the agent: protocol client, workflow, governance
deskpilot/llm.py       Gemini / OpenAI-compatible adapter returning JSON
deskpilot/policy.md    the support policy (also published to the room as a document)
scripts/register_agent.sh   register with Switch + open addressing, writes .env.deskpilot
dev/                   no-Docker stack scripts used for the demo
docs/screenshots/      screens from the demo run
```

## Screens

| | |
|---|---|
| ![](docs/screenshots/01-ticket.png) | ![](docs/screenshots/03-lead-gate.png) |
| ![](docs/screenshots/04-approved.png) | ![](docs/screenshots/05-escalation.png) |
| ![](docs/screenshots/03b-draft-v2.png) | ![](docs/screenshots/06-summary.png) |

## Built during the hackathon

Everything here (the Switch setup, the agent, the policy and the workflow) was built during the Flip the Switch build window, Nov 4–7, 2026. Switch is © SandboxAQ, Apache 2.0 + Commons Clause; DeskPilot is MIT.
