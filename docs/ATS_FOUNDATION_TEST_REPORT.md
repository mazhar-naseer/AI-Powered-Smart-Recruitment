# SmartHire Market-ready ATS Foundation — Integration Test Report

**Test date:** 5 August 2026  
**Scope:** Option 1 ATS Foundation integrated with the existing Advanced AI Hiring Intelligence module  
**Environment:** Local FastAPI + React/Vite + PostgreSQL, development configuration

## Executive result

The ATS foundation is integrated with the existing hybrid scoring system. Tenant ownership, recruiter permissions, candidate workflow, notifications, private storage, background processing, audit events, and administrator monitoring use the same jobs and applications that feed deterministic and Gemini scoring. The ATS layer does not recalculate or replace AI scores; it controls organization ownership, access, collaboration, and operational processing around the existing analysis pipeline.

Automated validation passed:

- 27 FastAPI backend tests
- 5 React unit tests
- TypeScript production build
- ESLint with zero errors (five non-blocking React development warnings)
- Python module compilation
- Docker Compose configuration validation
- Git whitespace validation
- PostgreSQL migration `0006_market_ats_foundation (head)`

Browser validation confirmed that the Vite application loads at `http://127.0.0.1:5174`, renders the SmartHire landing page, exposes employer/applicant entry points, and produces no browser console errors on initial load.

## Full live browser acceptance run — 6 August 2026

A second acceptance run exercised the actual React UI, FastAPI API, PostgreSQL database, local private storage, and configured Gemini service together. Synthetic accounts and a synthetic PDF were used; no personal resume was uploaded.

Live test identities:

- Workspace owner: `live.owner.20260806@example.com`
- Invited viewer: `live.viewer.20260806@example.com`
- Applicant: `live.applicant.20260806@example.com`
- Platform administrator: `live.admin.20260806@example.com`

Live test job: `Live ATS Backend Engineer 20260806`

Verified UI journey:

1. Owner login displayed Dashboard, workspace selector, My Jobs, Post a Job, Hiring Pipeline, Recruiter Team, AI Scorecards, Notifications, and Profile.
2. Owner created a recruiter invitation; the pending invitation and expiry appeared correctly.
3. Pipeline rendered Applied, Screening, Interview, Offer, Hired, and Rejected.
4. Pipeline Settings exposed the protected Applied entry stage and customizable remaining stages.
5. Job form blocked publishing until title, 20-character description, and required skills were valid.
6. Published job appeared in My Jobs and on the applicant Job Board.
7. AI Scorecard Studio loaded the new job with 15/35/25/15/5/5 weights totaling 100%.
8. Applicant uploaded the synthetic PDF and the application completed.
9. Applicant duplicate state replaced the upload form with Application already submitted and View my application.
10. Gemini hybrid result completed with final score 82.33%.
11. Employer received a new-applicant notification.
12. Candidate appeared under Applied with score 82.33%.
13. Assignment, tags, private note, and all timeline events persisted.
14. Candidate moved Applied → Screening and appeared only in Screening.
15. Applicant received an unread Application moved to Screening notification.
16. Viewer accepted an invitation, gained a second workspace, and the invited workspace became active.
17. Viewer dashboard showed the shared company's one job, one applicant, and 82.3% average while job, scorecard, candidate, and pipeline write controls were hidden.
18. Admin Operations showed six organizations, seven active memberships, one completed durable analysis job, zero failures, retry control, and the live audit events.
19. No browser console errors were recorded during the final owner, applicant, viewer, or admin checks.

Live AI evidence:

- Deterministic result: 76.02%
- Gemini result: 95.00%
- Gemini confidence: 95.0%
- Effective deterministic weight: 66.8%
- Effective Gemini weight: 33.3%
- Final hybrid result: 82.33%
- Provider: `gemini-3.6-flash`
- Recommendation: Strongly Recommend

Issues discovered and corrected during this live run:

1. PostgreSQL inserted timeline/notification rows in the same transaction before the new application had been flushed. The resulting foreign-key integrity error was incorrectly reported as a duplicate application. The application and resume are now flushed first; only the actual `uq_application_job_applicant` constraint maps to the duplicate message, while unrelated integrity failures are logged and return a truthful server error.
2. Pipeline Settings wording implied that every starter stage was protected. The backend intentionally protects only Applied because it is the entry stage; the UI now says Entry and explains that other stages may be customized or removed.
3. Viewer accounts saw Post a Job, AI Scorecards, and Edit controls even though backend RBAC rejected them. Workspace permissions now drive employer navigation and job-management controls, producing a clear read-only viewer dashboard.

Post-fix regression result:

- 27 backend tests passed
- 5 frontend tests passed
- Frontend production build passed

## Live PostgreSQL evidence

The local database was inspected without reading credentials or resume contents.

| Check | Result |
|---|---:|
| Organizations | 3 |
| Active membership records | 3 |
| Pipeline stages | 18 (six per organization) |
| Existing applications | 2 |
| Migration | `0006_market_ats_foundation (head)` |

Stored scoring examples prove both hybrid paths remain operational:

| Analysis path | Deterministic | Gemini | Final | Provider |
|---|---:|---:|---:|---|
| Gemini succeeded | 50.79 | 85.00 | 61.57 | `gemini-3.6-flash` |
| Gemini unavailable/failed | 37.33 | — | 37.33 | `deterministic-fallback` |

Configured AI runtime:

- Gemini enabled: yes
- API key present: yes (the value was not printed)
- Model: `gemini-3.6-flash`
- Maximum Gemini influence: 35%
- Deterministic engine: always executed
- Local processing mode: inline
- Object storage provider: local private storage

## Impact of ATS foundation on AI analysis

### Before the ATS foundation

```text
Applicant → Job → Resume → deterministic analysis → Gemini analysis → hybrid result
```

### After the ATS foundation

```text
Company workspace
  → company-owned job and scorecard
  → applicant submission
  → company-owned application in Applied stage
  → durable analysis job
  → deterministic analysis
  → Gemini assessment (when available)
  → confidence-weighted hybrid result
  → recruiter notification and candidate pipeline
  → assignment, tags, notes, stage changes, and timeline
```

The following AI behavior is unchanged:

- Per-job scorecard weights and requirements
- Deterministic semantic, skills, experience, role, domain, and education scoring
- Gemini structured assessment
- Confidence-adjusted hybrid formula
- Manual-review disagreement guardrail
- Deterministic fallback when Gemini times out or fails
- Evidence matrix, strengths, gaps, recommendations, and score overrides

The ATS foundation adds:

- `organization_id` isolation on jobs, applications, background jobs, notifications, and collaboration data
- Default `Applied` stage on submission
- Durable processing state around the existing analysis function
- Company-member notification when a candidate applies
- Company-scoped candidate visibility and resume access
- Audit context for organization and workflow actions

## Tested functional areas

### 1. Organization and tenancy

Validated:

- Employer registration automatically creates a company workspace.
- The employer becomes workspace owner.
- Existing employers, jobs, and applications are backfilled by migration 0006.
- Each organization receives Applied, Screening, Interview, Offer, Hired, and Rejected stages.
- Active workspace switching requires a valid membership.
- Jobs and applications are filtered by the active organization.
- Cross-organization candidate, stage, assignment, and resume access is rejected by the backend.

### 2. Recruiter invitations and permissions

Validated:

- Invitation creation with admin, recruiter, or viewer role
- Secure token hashing
- Seven-day expiry
- Acceptance only by the invited email
- Workspace activation after acceptance
- Pending invitation revocation
- Recruiter role changes
- Recruiter removal
- Owner membership protection
- Viewer job-creation attempt returns HTTP 403

Permission expectations:

| Role | Team | Jobs | Candidate workflow | Notes | Analytics |
|---|---|---|---|---|---|
| Owner | Manage | Manage | Manage | Add | View |
| Admin | Manage | Manage | Manage | Add | View |
| Recruiter | No team administration | Manage | Manage | Add | View |
| Viewer | No | No | Read only | No | View |

Backend permissions are authoritative. Some generic employer navigation remains visible to viewer accounts; unauthorized writes are still rejected with HTTP 403. This is a UX-hardening item, not a data-security failure.

### 3. Candidate pipeline

Validated:

- Six default stages are created in order.
- Owner can create, rename, recolor, reorder, and delete a custom stage.
- The Applied entry stage cannot be deleted; the remaining starter stages may be customized or removed.
- A stage containing candidates cannot be deleted.
- New application enters Applied.
- Candidate can move to another stage.
- Applicant receives a stage-progress notification.
- Every move creates a timeline event.

### 4. Candidate collaboration

Validated:

- Assignment only to an active member of the same organization
- Assignment notification to the selected recruiter
- Candidate tags are normalized and deduplicated
- Private internal notes are stored with author and timestamp
- Application receipt, assignment, tags, notes, and stage changes appear in timeline
- AI analysis remains accessible from the candidate workspace

### 5. Notifications

Validated for new activity:

- New-candidate notification to active company members
- Candidate-assignment notification
- Applicant stage-progress notification
- Team-invitation notification for an existing employer account
- Individual mark-as-read
- Mark-all-read
- User-scoped notification queries

Historical note: migration 0006 does not synthesize notifications for applications created before the ATS foundation. Therefore the current database can legitimately show zero notifications until new activity occurs.

### 6. Background processing

Validated:

- Every new application creates a database-backed analysis job.
- Development inline mode runs the durable job immediately.
- Dedicated worker can claim queued jobs when `INLINE_BACKGROUND_JOBS=false`.
- Job states are queued, running, completed, or failed.
- Attempts, retry delay, terminal error, and completion timestamps are stored.
- Admin can list jobs and requeue failed/completed work.
- Retry action creates an audit record.

Historical note: old applications are not converted into completed background-job records during migration. Background rows represent work submitted after the feature was introduced or explicitly requeued.

### 7. Private storage

Validated:

- New resume keys are opaque filenames rather than absolute filesystem paths.
- Requested files are resolved inside the configured private root.
- Legacy absolute paths inside the approved storage root remain readable.
- Resume access remains restricted to authorized employer workspace members and administrators.

### 8. Administration and audit

Validated:

- Separate Admin Control Center
- Organization and active-membership totals
- Background queue status totals
- Recent background-job detail and errors
- Administrator retry control
- Recent audit activity
- Existing user, job, resume, application, and AI monitoring features remain available

## Recommended manual test sequence

### Step 1 — Start the stack

```bash
cd /Users/tayyab/Desktop/SmartHire/backend
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd /Users/tayyab/Desktop/SmartHire/frontend
npm run dev -- --port 5174
```

For production-style asynchronous testing, set `INLINE_BACKGROUND_JOBS=false`, restart the API, and run in a third terminal:

```bash
cd /Users/tayyab/Desktop/SmartHire/backend
../.venv/bin/python scripts/run_worker.py
```

### Step 2 — Test company owner

1. Register Employer A and verify email.
2. Confirm automatic login.
3. Open `/employer/team`.
4. Confirm Employer A is Owner.
5. Open `/employer/pipeline/settings`.
6. Confirm the six default stages.
7. Add `Technical Interview`, change its color/position, then delete it.

Expected: company data is created once, owner and the Applied entry stage are protected, and stage operations persist after refresh.

### Step 3 — Test recruiter and viewer

1. Register Employer B and Employer C.
2. From Employer A, invite B as Recruiter and C as Viewer.
3. Accept both invitation links using the matching accounts.
4. Switch each account to Employer A's workspace.
5. With B, create/edit a job and manage a candidate.
6. With C, inspect analytics/candidates and attempt to create a job.

Expected: recruiter writes succeed; viewer write returns 403; neither account sees another workspace unless it has membership.

### Step 4 — Test job and AI configuration

1. Employer A creates a job with required skills and a detailed description.
2. Open AI Scorecard Studio.
3. Configure weights, requirement priorities, domain keywords, education, and certifications.
4. Save the scorecard.

Expected: scorecard remains attached to the job and is the deterministic/hybrid input after ATS installation.

### Step 5 — Test applicant submission

1. Register and verify an Applicant.
2. Open the job and upload a text-based PDF or DOCX.
3. Submit once.
4. Reopen job details.

Expected: submission enters Applied; duplicate UI shows already submitted; duplicate API attempt is rejected; a durable processing job and new-candidate notifications are created.

### Step 6 — Verify hybrid result

1. Open `/applicant/applications`.
2. Wait for Completed.
3. Open AI Insight.
4. As Employer A, open the candidate's full analysis.

Expected when Gemini succeeds: deterministic score, Gemini score, confidence, effective weights, final score, strengths, gaps, evidence, and provider are populated.

Expected when Gemini fails: application still completes using deterministic fallback; Gemini error/status is recorded; final score equals deterministic score; retry Gemini remains available where supported.

### Step 7 — Test recruiter collaboration

1. Open `/employer/pipeline`.
2. Open the candidate.
3. Assign Employer B.
4. Add `priority, backend, referral` tags.
5. Add an internal screening note.
6. Move Applied → Screening → Interview.

Expected: recruiter notification, applicant progress notification, deduplicated tags, private note, and complete timeline.

### Step 8 — Test notification center

1. Open `/notifications` as Employer A, Employer B, and Applicant.
2. Open a notification.
3. Use Mark all read.
4. Refresh.

Expected: action URL opens the correct workspace item and read state persists.

### Step 9 — Test tenant isolation

1. Create a job and applicant under Employer B's original workspace.
2. Switch between Employer A and Employer B workspaces.
3. Compare jobs, candidates, team, stages, and notifications.
4. Attempt a direct candidate/stage ID from the other workspace.

Expected: lists change with workspace; cross-tenant API access returns 403 or 404.

### Step 10 — Test worker failure and retry

1. Use `INLINE_BACKGROUND_JOBS=false`.
2. Stop the worker and apply to a job.
3. Confirm queued status in `/admin/operations`.
4. Start the worker and confirm queued → running → completed.
5. Use an invalid/image-only resume without OCR to produce a controlled failure.
6. Inspect the failure and click Retry.

Expected: API remains available, error is visible to operations, and retry creates a fresh queued execution with an audit event.

## Known gaps and production recommendations

These do not invalidate the tested ATS foundation, but should be completed before a commercial public launch:

1. **Viewer UX hardening:** backend RBAC is correct, but some generic employer write controls/navigation can remain visible and then return 403. Hide or disable them using workspace permissions.
2. **Historical operational events:** migrations intentionally do not invent old notifications, timeline events, or background-job executions.
3. **Cloud object storage:** the abstraction is ready, but only local private storage is currently implemented. Add S3/GCS/Azure plus signed download URLs for distributed deployment.
4. **Upload security:** add malware scanning, file quarantine, retention policies, and deletion workflows.
5. **Enterprise identity:** add MFA/SSO and stronger administrator access controls.
6. **High-scale queue:** the PostgreSQL worker is durable and valid for this phase; use Redis/SQS/RabbitMQ when sustained throughput requires multiple worker pools.
7. **Email delivery operations:** add bounce/complaint handling and delivery telemetry for production SMTP/provider integration.
8. **Browser E2E expansion:** current browser check validates application boot and console health; add persistent Playwright suites for owner, recruiter, viewer, applicant, and admin journeys in CI.

## Automated commands

```bash
cd /Users/tayyab/Desktop/SmartHire
./.venv/bin/pytest -q backend/tests

cd frontend
npm test
npm run build
npm run lint
```

## Final assessment

The new ATS domain and the previous AI domain are properly connected through the same organization-owned Job and Application records. New applications follow the full tenancy → notification → durable processing → deterministic/Gemini hybrid analysis → candidate pipeline flow. The foundation is functionally ready for local acceptance testing and controlled deployment. The items in “Known gaps” are the next production-hardening layer rather than failures in the implemented core workflow.
