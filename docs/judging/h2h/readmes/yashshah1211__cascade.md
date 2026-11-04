# CASCADE — The Commitment Recovery Engine

**Flip the Switch 2026 · Best Business Workflow · Built starting November 4, 2026**

CASCADE detects which organizational commitments are impacted when a prerequisite breaks, evaluates alternative recovery plans with **deterministic** checks, and requires a verified human decision in a Switch room before applying an exception.

> **Current build status:** This is a real offline recovery engine and read-only dashboard. **Switch integration remains BLOCKED / unverified**, so this is *not yet a complete hackathon submission*. The dashboard intentionally has no approve button. No external booking or message is sent.

## Demo scenario (entirely fictitious)

430 attendees lose their auditorium. Replacement Hall A has 250 seats, Hall B 220, and the team has one AV kit. The shared kickoff must start at 10:00, sponsor showcase must happen before noon, and the INR 80,000 baseline is already committed.

| Plan | Engine verdict | Reason |
|---|---|---|
| A · Two halls, one AV kit | **FAIL** | 2 concurrent kits required, 1 available |
| B · Two halls, rent extra AV | **REQUIRES_APPROVAL** | INR 3,000 budget exception |
| C · Two sequential waves | **FAIL** | Not all attendees start at 10:00 |

Plan B can become PASS **only after** a genuine Switch message has been verified by an authenticated integration. Offline unit tests exercise this with an explicitly named fake message verifier; they do not prove the Switch integration.

## Getting started (Windows PowerShell)

Requires Node.js 20+ (22 recommended), npm, and Internet access for the *initial* `npm install` (TypeScript build dependencies). No Docker, database or AI subscription needed for this core.

```powershell
cd path\to\cascade
npm install
npm test
npm run demo
npm run dashboard
```

Open **http://127.0.0.1:4173** in your browser. The dashboard computes results from the TypeScript engine; switching between plans changes the checks and plan-bound approval instruction.

### No package installation needed for the precompiled demo

The release ZIP includes compiled JavaScript. If `npm install` is unavailable:

```powershell
node dist/src/cli/main.js demo
node dist/src/dashboard/server.js
```

Then open the same URL. Rebuild with `npm install` + `npm run build` when you make changes.

## What is implemented

- `src/domain` — typed scenario, commitment, plan, approval, receipt; offset-ISO checks and stable SHA-256 plan hashing
- `src/engine/impact.ts` — BFS dependency traversal with explainable paths
- `src/engine/evaluate.ts` — attendee identity coverage, overlapping hall capacity, accessible venue checks, synchronized kickoff, AV concurrency, sponsor deadline, budget approval, scenario revision; four distinct verdicts
- `src/switch/approval.ts` — authenticated message-verifier contract and branded in-memory approval; deliberate fail-closed stub for live integrations
- `src/engine/execute.ts` — revalidate before applying, idempotent atomic local artifact generation, explicit draft-vs-applied statuses
- `src/dashboard` and `web/` — responsive, read-only command center backed by `/api/demo`
- `fixtures/` — synthetic 430-person disruption and three candidate plans
- `tests/` — offline automated scenarios including constraint mutation, spoofed approvals and idempotency

## What is *not* implemented

- A working Switch-connected agent or Mattermost room (see [integration gate](docs/SWITCH_INTEGRATION.md)).
- A production `SwitchMessageVerifier` that can authenticate and fetch a human-authored chat message by ID.
- A provider-based AI planner. The three candidate plans are **fixtures**, but each verdict is genuinely computed.
- Any real-time venue booking, payments, notifications, or external data.

The project is not allowed to claim a successful Switch hackathon workflow without passing the real room acceptance checklist. Instructions for the first agent and next integration steps are in [docs/SWITCH_INTEGRATION.md](docs/SWITCH_INTEGRATION.md).

## Integrity model

1. The plan is bound to a deterministic SHA-256 hash including scenario revision.
2. A genuine human's plan-and-amount-specific Switch message must be fetched by a trusted verifier (pending integration).
3. Untrusted JSON approvals cannot pass the private runtime brand check.
4. Constraints are rerun immediately before an approved plan is applied.
5. Local artifacts are written in one staging directory and atomically published as a unit. Repeating the same successful execution returns the existing receipt.
6. Receipt status is **APPLIED_LOCALLY**; communication output is a **DRAFT**, never a sent message.

## Safety and reproducibility

All event data is synthetic and stored in `fixtures/`; no user secrets or paid API keys are included. No external API calls occur during engine tests. `npm test` compiles and runs the Node test suite; mutating Hall B capacity to 170 changes a capacity verdict from PASS to FAIL.

## Roadmap

1. **Switch acceptance gate:** connect a real human and a Codex agent in a Mattermost team channel; prove a successful reply. Only after that, integrate authenticated message verification.
2. Agent invokes CLI and posts *actual* check results to Switch; collect live evidence.
3. Human authorizes Plan B by exact hash and max additional INR 3,000; verified message unlocks `applyPlan`.
4. Capture generated artifacts and the actual Switch conversation in a 3-minute demo.

## Competition

Official event: https://www.wemakedevs.org/hackathons/switch

**Build window:** Nov 4, 12:01 AM IST through Nov 7, 11:59 PM IST. A public repo, a short demonstration video, and a Switch setup README are required.
