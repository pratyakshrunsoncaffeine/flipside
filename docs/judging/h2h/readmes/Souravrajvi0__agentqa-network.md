# AgentQA Network

Intelligent, real-time, multi-user QA collaboration platform with **Switch** agent integration for the Flip the Switch Hackathon (Nov 4–7, 2026).

## Features

- Multi-user projects with RBAC (Administrator, QA Lead, QA Engineer, Developer)
- Test cases, cycles, atomic claims, executions (manual + Playwright automation)
- Explainable priority recommendations
- Design decisions, developer change requests, defects, knowledge sharing
- Real-time WebSocket updates per project
- Agent API + MCP tools for Switch-connected coding agents
- Optional Switch room notifications via documented agent bridge `POST /agents/{id}/message`

## Architecture

Monorepo (npm workspaces):

| Package | Purpose |
|---------|---------|
| `backend/` | Express + Prisma + PostgreSQL + WebSocket |
| `frontend/` | React + Vite + Tailwind + TanStack Query |
| `packages/agent-mcp/` | MCP server exposing AgentQA tools to agents |
| `packages/switch-agent-runner/` | WebSocket client for Switch agent protocol |

See `architecture.md`, `switch-integration.md`, and `api.md`.

## Quick start

```bash
cd agentqa-network
cp .env.example .env
npm install
docker compose up -d postgres
npm run db:migrate:dev -w backend   # first time: creates migration
npm run db:seed -w backend
npm run dev -w backend              # terminal 1 — http://localhost:4000
npm run dev -w frontend             # terminal 2 — http://localhost:5173
```

Demo login: `qa.b@agentqa.demo` / `password123` (see seed output for all users).

## Switch integration status

| Component | Status |
|-----------|--------|
| Agent REST + MCP tools | Implemented (local verification) |
| Switch room posts via bridge API | Implemented when env vars set |
| Switch WebSocket runner | Implemented (`packages/switch-agent-runner`) |
| Live Switch server in this VM | **Not configured** — requires your Switch Console / bridge URLs and agent API keys |

Configure `.env`:

```env
SWITCH_BRIDGE_BASE_URL=https://your-bridge-host
SWITCH_ROOM_ID=...
SWITCH_NOTIFY_AGENT_ID=...
SWITCH_NOTIFY_AGENT_API_KEY=...
```

Register agents in the UI (Agents view) and attach MCP in Claude Code/Codex per `switch-integration.md`.

## Tests

```bash
npm run test -w backend
AGENTQA_INTEGRATION=1 DATABASE_URL=postgresql://agentqa:agentqa_dev@localhost:5433/agentqa npm run test -w backend
npm run test -w frontend
```

### Playwright E2E (delivery)

```bash
npm install -w e2e
npx playwright install chromium --with-deps   # once per machine
# Start backend (:4000) and frontend (:5170) or let Playwright start them
AGENTQA_E2E_BASE_URL=http://localhost:5170 AGENTQA_E2E_NO_SERVER=1 npm run test:e2e
```

Optional: `AGENTQA_E2E_LEAD_EMAIL`, `AGENTQA_E2E_QA_EMAIL`, `AGENTQA_E2E_PASSWORD`, `AGENTQA_E2E_AGENT_KEY`.

### GitHub webhook (per project)

1. Open **Admin → GitHub integration** (Administrator).
2. Save owner, repo, default branch, and webhook secret.
3. In GitHub → Webhooks, point to `{API}/api/integrations/github/webhook`, secret, event **Workflow runs**.

See `DELIVERY_COMPLETION_REPORT.md` for delivery pipeline completion details.

## Demo scenarios

See `demo.md` for step-by-step flows (multi-QA claim conflict, developer urgent change, design decision, coordination scan, Playwright run, defect lifecycle).

## License

MIT (hackathon submission)
