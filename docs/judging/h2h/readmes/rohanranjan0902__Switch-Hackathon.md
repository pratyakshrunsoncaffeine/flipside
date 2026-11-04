# DevOps AI Command Center

A human-approved incident investigation workspace built for the WeMakeDevs Flip the Switch Hackathon. It brings incident triage, logs, specialized agent roles, code review, and GitHub workflow status into one dashboard.

> **Foundation status:** The frontend and REST API run with clearly labelled demo data. Switch and GitHub execution are not connected, and no agent task, patch, or pull request is faked. No code is merged or deployed automatically.

## What works today

- Dark, responsive React dashboard with Overview, Incidents, AI Agents, Logs Explorer, Code Review, and GitHub views.
- Create demo incidents, search/filter incidents and logs, and update incident status.
- Express API with input validation, error responses, health checks, and Socket.IO incident events.
- PostgreSQL Prisma schema for users, incidents, agents, executions, logs, code changes, tests, repositories, pull requests, and approvals.
- Sample e-commerce checkout code with reproducible inventory and missing-cart defects.
- GitHub Actions, Docker Compose, linting, formatting, and basic tests.

The API currently stores incident state in memory; data resets when the API restarts. The Prisma schema is the database foundation, not a claim that the demo API is already persisting records.

## Quick start

### Local development

Requirements: Node.js 22+ and npm 10+. PostgreSQL is optional for the current in-memory API; it is required to run Prisma migrations.

```bash
cp .env.example .env
npm install
npm run dev
```

Open the frontend at [http://localhost:5173](http://localhost:5173). The API health check is at [http://localhost:4000/api/health](http://localhost:4000/api/health).

Run quality checks:

```bash
npm test
npm run lint
npm run build
```

### Docker Compose

```bash
docker compose up --build
```

The dashboard is served at `http://localhost:5173`, the API at `http://localhost:4000`, and PostgreSQL at `localhost:5432`. Compose starts PostgreSQL, but the starter API still uses demo in-memory incident state.

### Prisma database setup

Start PostgreSQL (for example with Docker Compose), then:

```bash
npm run db:generate
npm run db:migrate --workspace backend
```

Set `DATABASE_URL` in `.env` before running Prisma commands.

## API overview

All responses use a `{ data, meta }` or `{ error }` envelope. Full request/response notes are in [docs/API.md](./docs/API.md).

| Method     | Path                                                    | Purpose                                                                      |
| ---------- | ------------------------------------------------------- | ---------------------------------------------------------------------------- |
| GET        | `/api/health`                                           | API status and integration readiness                                         |
| GET, POST  | `/api/incidents`                                        | List or create demo incidents                                                |
| GET, PATCH | `/api/incidents/:id`                                    | Read or update incident status                                               |
| POST       | `/api/incidents/:id/investigate`                        | Returns an explicit unavailable response until Switch is verified/configured |
| POST       | `/api/incidents/:id/approve`                            | Reserved for authenticated human approval; currently `501`                   |
| POST       | `/api/incidents/:id/reject`                             | Reserved for authenticated human rejection; currently `501`                  |
| GET        | `/api/agents`, `/api/agents/:id`                        | Agent role catalog (demo mode)                                               |
| GET        | `/api/logs`, `/api/logs/:id`                            | Searchable sample logs                                                       |
| GET        | `/api/github/repositories`, `/api/github/pull-requests` | Explicitly reports GitHub as not connected                                   |

Socket.IO emits `incident:created` and `incident:updated` after API writes. See [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for boundaries and event details.

## Switch and GitHub setup

The Switch integration is intentionally a fail-closed adapter boundary. The official integration documentation/API could not be verified from the accessible public sources during project setup. The starter therefore does not invent an endpoint, SDK, room, or agent contract. Keep `SWITCH_ENABLED=false`; review [docs/SWITCH_INTEGRATION.md](./docs/SWITCH_INTEGRATION.md) and implement the adapter only against the verified official guidance.

Likewise, GitHub is not yet making API calls. Keep `GITHUB_ENABLED=false` until repository permissions and API behavior are implemented and reviewed. Credentials belong in local environment variables or a secret manager, never in source control or database fields.

## Team of four

See [CONTRIBUTING.md](./CONTRIBUTING.md) for ownership, interfaces, branch naming, and pull request expectations.

1. **AI Agents & Switch:** verified Switch adapter, agent orchestration, execution history.
2. **Backend & Database:** Prisma-backed repositories, authentication/authorization, incident history.
3. **Frontend & Dashboard:** API-backed views, incident detail/history, accessible states.
4. **Infrastructure, Testing & GitHub:** GitHub API integration, isolated test execution, CI/Docker hardening.

## Repository map

```text
frontend/       React + TypeScript + Vite dashboard
backend/        Express + TypeScript API, Socket.IO, Prisma schema
sample-app/     Intentionally faulty e-commerce checkout demo
infrastructure/ Reserved for deployment manifests and operational configs
docs/           API, architecture, and Switch integration notes
```
