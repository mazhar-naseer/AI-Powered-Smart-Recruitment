# SmartHire Commercial SaaS Test Report

Date: 2026-08-06

## Delivered scope

- Per-organization subscriptions with Starter, Growth, and Scale plans
- Server-side entitlements for jobs, team seats, monthly AI analyses, and private storage
- Monthly usage metering and tenant usage dashboard
- Trial/active subscription lifecycle and local manual plan changes
- Workspace brand, timezone, careers URL, email preference, and retention controls
- Audited tenant data export
- HMAC-authenticated, idempotent provider webhook foundation
- Separate platform-admin SaaS account and estimated-MRR view
- PostgreSQL migration `0007_commercial_saas`

## Automated verification

| Check | Result |
|---|---|
| Backend Pytest suite | 30 passed |
| Frontend Vitest suite | 5 passed |
| ESLint | 0 errors; 6 pre-existing warnings |
| TypeScript/Vite production build | Passed |
| PostgreSQL Alembic migration | Applied through `0007_commercial_saas` |

New backend coverage verifies subscription creation, settings persistence, Starter quota enforcement, Growth upgrade capacity, tenant export, viewer denial, admin commercial visibility, and closed webhooks when no secret is configured.

## Live PostgreSQL/API verification

The updated FastAPI application was started on an isolated port and tested using the existing live employer workspace.

| Operation | Result |
|---|---|
| Employer login | HTTP 200 |
| `GET /api/v1/workspace/saas` | HTTP 200 |
| Starter trial subscription | Present |
| Active-job usage | 1 used / 3 limit |
| Plan catalog | Starter, Growth, Scale |
| `GET /api/v1/workspace/data-export` | HTTP 200 |
| Export content | 1 job, 1 application |

The running service on port 8000 was a stale pre-change process and returned 404 for the new route. Restart the backend once before manual browser testing.

## Manual browser test flow

1. Restart FastAPI and keep Vite running.
2. Sign in as an employer workspace owner.
3. Open **Workspace & Billing** in the employer sidebar.
4. Confirm the onboarding cards, Starter plan, usage meters, and three plan cards appear.
5. Change company name, timezone, domain, careers URL, retention period, and brand color; save and refresh.
6. On Starter, publish jobs until the active-job meter reaches 3. The fourth open job must return a plan-limit message.
7. Select Growth and publish another job; it must succeed and the new limit must show as 25.
8. Invite recruiters and confirm team-seat usage changes.
9. Submit an applicant resume and confirm AI-analysis/storage usage increments.
10. Click **Export workspace data** and inspect the downloaded tenant-scoped JSON.
11. Sign in at `/admin/login`, open **SaaS Accounts**, and confirm organization, subscription, MRR, plan, and status data.
12. Open **Operations & Audit** and confirm settings, plan-change, and export events are recorded.

## Production boundary

The SaaS domain, plan enforcement, subscription state, provider IDs, webhook verification, and local/manual billing flow are operational. Real card collection is deliberately not simulated. Before commercial launch, connect a selected payment provider’s checkout and customer portal, configure its signing secret, and test provider sandbox events. This external step requires the merchant account and credentials; it does not change ATS or AI-scoring behavior.

## AI/ATS impact

The existing deterministic + Gemini hybrid pipeline is unchanged. Each submitted application still enters the tenant pipeline, is analyzed by the background worker, and exposes evidence to employer/admin views. The commercial layer only checks and meters the organization’s AI entitlement before queueing analysis; it does not alter scoring weights, evidence extraction, Gemini guardrails, or human-review controls.
