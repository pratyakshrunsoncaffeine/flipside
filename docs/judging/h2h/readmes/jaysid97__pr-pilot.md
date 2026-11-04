# PR Pilot 🤖✈️

> **AI-powered pull request reviews — right inside your Discord.**
> Built for the [Flip the Switch Hackathon](https://www.wemakedevs.org/hackathons/switch) · Track 01: Best Business Workflow

[![Switch](https://img.shields.io/badge/powered%20by-Switch-blueviolet)](https://github.com/sandbox-quantum/switch)
[![Discord](https://img.shields.io/badge/chat-Discord-5865F2)](https://discord.gg)
[![Antigravity](https://img.shields.io/badge/agent-Antigravity-black)](https://antigravity.dev)

---

## What It Does

PR Pilot puts two AI agents into your Discord `#pr-reviews` channel, powered by [Switch](https://github.com/sandbox-quantum/switch):

| Agent | Role |
|-------|------|
| **@pr-reviewer** | Reads the diff, summarises the PR, flags risks, asks the author pointed questions, and can approve or request changes via GitHub API |
| **@pr-standards** | Runs an objective checklist: conventional commit title, description, tests, no unlinked TODOs, docs updated, PR size |

The full loop:

```
GitHub PR opened → webhook → Switch → Discord
    • @pr-reviewer posts structured review
    • @pr-standards posts pass/fail checklist
    • Teammates ask questions → agent answers
    • Human types "approve" → PR approved on GitHub ✅
```

Switch is the infrastructure that makes this possible. Remove Switch and the agents disappear from Discord entirely.

---

## Demo

> 📹 **[Watch the 2-minute demo video](#)** ← link added on submission

![PR Pilot demo screenshot](docs/demo-screenshot.png)

---

## Quick Start (5 minutes)

### Prerequisites
- [Switch Console](https://github.com/sandbox-quantum/switch/releases) installed and running
- Docker Desktop
- A Discord server where you have admin rights
- A GitHub repo to test with
- An [Antigravity](https://antigravity.dev) account

### 1 — Clone & configure

```bash
git clone https://github.com/jaysid97/pr-pilot
cd pr-pilot
cp .env.example .env
```

Edit `.env` and fill in:
- `GITHUB_WEBHOOK_SECRET` — a random string (you'll paste this in GitHub too)
- `GITHUB_TOKEN` — a GitHub PAT with `repo` scope

### 2 — Load the Switch template

1. Open **Switch Console**
2. Click **New Room from Template**
3. Select `switch/pr-pilot.template.yaml`
4. Choose your **Discord** bridge
5. Click **Create** — two agents join your `#pr-reviews` channel

### 3 — Start the webhook receiver

```bash
docker compose up -d
docker compose logs -f webhook   # should print "PR Pilot Webhook Receiver"
```

### 4 — Expose your webhook publicly

Using [ngrok](https://ngrok.com) (free tier is fine for the demo):

```bash
ngrok http 9000
# Copy the https URL, e.g. https://abc123.ngrok.io
```

Or use [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (uncomment the `cloudflared` service in `docker-compose.yml`).

### 5 — Configure GitHub webhook

In your GitHub repo → **Settings → Webhooks → Add webhook**:
- **Payload URL**: `https://YOUR_URL/webhook/github`
- **Content type**: `application/json`
- **Secret**: same value as `GITHUB_WEBHOOK_SECRET` in `.env`
- **Events**: select **Pull requests**

### 6 — Open a PR and watch it happen

Open a pull request on your GitHub repo.
Within seconds, `#pr-reviews` in Discord will show the review from `@pr-reviewer`.

---

## Usage in Discord

| You type | What happens |
|----------|-------------|
| Any PR URL | @pr-reviewer fetches and reviews it |
| `approve` or `lgtm` | PR approved on GitHub via API |
| `block` or `request changes` | Agent asks for notes, then blocks PR on GitHub |
| Any question about the PR | Agent answers based on the diff |
| `@pr-standards re-check` | Standards bot re-runs the checklist |

---

## Architecture

```
┌──────────────┐   webhook    ┌─────────────────┐   room msg   ┌──────────────────┐
│   GitHub     │ ──────────► │  PR Pilot        │ ──────────► │  Switch Server   │
│  (PR event)  │             │  Webhook (Docker) │             │  (local, Docker) │
└──────────────┘             └─────────────────┘             └────────┬─────────┘
                                                                       │ bridge
                                                               ┌───────▼─────────┐
                                                               │    Discord       │
                                                               │  #pr-reviews     │
                                                               │                  │
                                                               │  @pr-reviewer   │◄── Antigravity
                                                               │  @pr-standards  │◄── Antigravity
                                                               │  👤 Your team   │
                                                               └─────────────────┘
                                                                       │
                                                               GitHub API (approve/block)
```

---

## File Structure

```
pr-pilot/
├── README.md
├── docker-compose.yml
├── .env.example
├── switch/
│   └── pr-pilot.template.yaml   # Switch room + agent template
├── agents/
│   ├── pr-reviewer/
│   │   └── instructions.md      # Antigravity agent prompt
│   └── pr-standards/
│       └── instructions.md      # Standards checker prompt
├── webhook/
│   ├── server.py                # FastAPI webhook receiver
│   ├── requirements.txt
│   └── Dockerfile
├── scripts/
│   ├── setup.sh                 # One-command setup helper
│   └── test-webhook.sh          # Send a test payload locally
└── docs/
    ├── setup.md                 # Detailed setup guide
    └── demo-video-script.md     # Demo script for the video
```

---

## Running Tests

```bash
# Send a test PR payload to your local webhook
bash scripts/test-webhook.sh

# Expected: message appears in #pr-reviews Discord channel
```

---

## How Switch Is Used

Switch is not optional plumbing — it's the core of this project:

1. **Rooms**: `#pr-reviews` in Discord is a Switch room. Every message, review, and approval flows through it.
2. **Agent protocol**: `@pr-reviewer` and `@pr-standards` are Switch agents. They receive messages via Switch's SSE stream and respond via HTTP — they couldn't exist in Discord without Switch.
3. **Template**: `pr-pilot.template.yaml` lets anyone reproduce the exact two-agent setup in one click in Switch Console.
4. **Bridge**: Switch's Discord bridge translates between Discord's API and the Switch agent protocol transparently.

---

## Built With

- [Switch](https://github.com/sandbox-quantum/switch) — agent ↔ team chat infrastructure
- [Antigravity](https://antigravity.dev) — AI agent runtime
- [FastAPI](https://fastapi.tiangolo.com) — webhook receiver
- [Discord](https://discord.com) — team chat
- [GitHub Webhooks](https://docs.github.com/en/webhooks) — PR event source

---

## License

MIT

