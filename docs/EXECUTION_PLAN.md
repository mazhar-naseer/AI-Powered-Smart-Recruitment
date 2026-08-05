# SmartHire - Execution Plan

This plan intentionally separates decisions, foundations, vertical features, and production hardening. A phase is complete only when its verification gate passes.

## Operating rules

- Implement one phase at a time after user approval.
- Do not silently expand MVP scope from decorative design elements.
- Write migrations for schema changes; do not mutate an existing database manually.
- Add automated tests with each business capability, not at the end.
- Keep API schema/OpenAPI and documentation synchronized.
- Preserve supplied source documents and images unchanged.

## Phase 0 - Confirm decisions and establish traceability

**Work**

- Confirm items in `DECISIONS_AND_QUESTIONS.md` that affect implementation.
- Assign requirement IDs and turn the MVP acceptance criteria into a traceability checklist.
- Freeze primary UI reference and technical baseline.
- Record environment prerequisites and supported versions.

**Deliverables:** decision log, requirement checklist, final MVP boundary.  
**Gate:** no unresolved blocker for Phase 1.

## Phase 1 - Repository and developer foundation

**Work**

- Create `backend`, `frontend`, `deploy`, and storage/documentation structure.
- Initialize FastAPI/Python 3.12 project and React TypeScript project.
- Add formatting, linting, strict type checking, test runners, `.gitignore`, `.editorconfig`, and environment examples.
- Add Dockerfiles, Compose skeleton, Nginx development configuration, and root README.
- Add CI pipeline for lint, types, tests, and builds.

**Gate:** clean install, lint/types/tests/build pass in a fresh environment; containers start with health endpoint.

## Phase 2 - Backend core and persistence

**Work**

- Implement settings, structured logging, request IDs, exception envelope, CORS/trusted hosts.
- Configure SQLAlchemy 2.0 sessions, repositories, unit of work, and Alembic.
- Add core entities and first migration.
- Add `/health` and `/ready`.
- Add repository and migration tests.

**Gate:** upgrade from empty database succeeds; readiness detects database/storage failure; error schemas are stable.

## Phase 3 - Authentication, RBAC, and profiles

**Work**

- Registration for employer/applicant, bcrypt hashing, login, refresh rotation, logout, `/auth/me`.
- Role and active-status dependencies plus ownership policy helpers.
- Employer/applicant profile creation and update.
- Admin provisioning CLI script.
- Rate limiting and auth audit events.

**Gate:** positive and negative API tests for all roles, expired/revoked tokens, duplicate email, suspended user, and forbidden admin registration.

## Phase 4 - Frontend shell and authentication UX

**Work**

- Implement tokens, typography, icons, cards, buttons, inputs, tables, badges, feedback states, and responsive layouts from the primary design.
- Build landing, login, registration, error pages, role-aware route layout, top bar, and sidebars.
- Add typed API client, auth lifecycle, refresh handling, and server-derived redirects.
- Add accessibility and responsive tests.

**Gate:** role login/logout/refresh works end to end; layouts match references at agreed desktop/mobile widths; keyboard navigation passes critical paths.

## Phase 5 - Job management

**Work**

- Implement job schema, repositories, services, endpoints, ownership, filters, search, sorting, pagination, and status transitions.
- Build employer dashboard summary, My Jobs, create/edit forms, and open/close actions.
- Build applicant job board and job details using real APIs.
- Implement admin-visible job query boundary for later moderation.

**Gate:** employer cannot access another employer's job; applicants cannot see closed/deleted/ineligible jobs; UI and API CRUD tests pass.

## Phase 6 - Application upload and resume storage

**Work**

- Implement private storage provider and strict PDF validator.
- Add resumes/applications models, unique `(job_id, applicant_id)` constraint, and migration.
- Implement multipart submission with atomic metadata writes and cleanup on failure.
- Build applicant apply panel and My Applications status screens.
- Add authorized resume streaming boundary.

**Gate:** valid PDF returns accepted/processing; duplicate, fake, oversized, unreadable, traversal-style, and unauthorized cases are tested; files are never publicly addressable.

## Phase 7 - Screening engine and ranked applicants

**Work**

- Implement extraction provider, normalization, TF-IDF cosine score, required-skill coverage, transparent final formula, and matched skills.
- Implement persisted processing transitions and idempotent background handler.
- Add optional LLM provider interface and disabled provider; integrate Gemini only after configuration/consent decision.
- Build employer ranked-applicant table, pending/failed states, and secure download action.
- Build score fixtures and regression tests.

**Gate:** repeatable fixtures produce expected bounded scores; rankings are deterministic; restart/error behavior is recoverable; employer ownership tests pass.

## Phase 8 - Admin oversight and moderation

**Work**

- Dashboard totals/trends/recent activity.
- User search/filter/pagination and suspend/reactivate/delete workflow.
- Global job moderation and audit log viewer.
- Ensure suspension affects sessions and job visibility immediately.
- Build confirmation, feedback, empty, and error states.

**Gate:** non-admins are denied; moderation actions are audited; aggregate counts match fixtures; destructive workflows have explicit confirmation and policy tests.

## Phase 9 - Integration hardening and UX completion

**Work**

- Complete loading, empty, error, retry, forbidden, and not-found states.
- Cross-browser/responsive/a11y review against both design images.
- End-to-end role journey suite.
- Performance work: pagination, indexes, query-count review, upload/processing timing.
- Security review: token behavior, IDOR, input/file abuse, headers, CORS, CSRF if cookie refresh is used, secrets/log leakage.

**Gate:** complete E2E suite, accessibility target, no critical/high security finding, acceptable response/processing budgets.

## Phase 10 - Production packaging and release readiness

**Work**

- Final multi-stage containers, non-root users, Nginx HTTPS/reverse-proxy configuration, Compose health checks and persistent volumes.
- Production configuration matrix and secret handling.
- Migration, admin provisioning, backup/restore, deployment, rollback, and incident runbooks.
- Dependency and image scanning; release versioning and changelog.
- Staging smoke test and restoration drill.

**Gate:** clean staging deployment, migrations and smoke tests pass, backup restore is proven, rollback steps are executable, production checklist is signed off.

## Phase 11 - Optional post-MVP work

- Durable task queue, PostgreSQL, object storage, antivirus scanning.
- OCR and DOC/DOCX resume support.
- Hiring stages, shortlisting, interviews, messages, notifications.
- Gemini enrichment, calibrated scoring/bias evaluation, advanced analytics and semantic search.

## Suggested implementation command sequence

The exact commands will be finalized in Phase 1 after dependency choices are approved. The intended daily loop is:

1. Start infrastructure/application services.
2. Apply migrations.
3. Run backend lint, formatting check, type check, and tests.
4. Run frontend lint, type check, component tests, and production build.
5. Run role-based end-to-end tests for affected flows.
6. Review the changed screens at target viewports.
7. Update OpenAPI/requirements traceability and phase gate evidence.

## Definition of done for every feature

- Requirement and authorization rules are explicit.
- API schemas, success/errors, pagination, and OpenAPI are correct.
- Database migration and indexes exist when needed.
- Unit/integration/UI tests cover success, failure, and forbidden paths.
- Loading/empty/error/success states are usable and accessible.
- No secrets, personal resume text, tokens, or passwords appear in logs.
- Relevant documentation and environment examples are updated.
- Formatting, linting, typing, tests, build, and visual check pass.
