# SmartHire - Product and Technical Blueprint

**Status:** Planning baseline  
**Product:** Smart Resume Screener and Job Board  
**Primary implementation direction:** React frontend + FastAPI REST API  
**API prefix:** `/api/v1`

## 1. Executive summary

SmartHire is a three-role recruitment platform. Employers create jobs and review ranked candidates, applicants discover open jobs and apply with PDF resumes, and administrators monitor and moderate the platform. The core workflow extracts resume text, compares it with the job description and required skills, saves a match score, and ranks applications from highest to lowest score.

The implementation will follow the supplied UI concepts closely: a public landing page, role-aware authentication, navy sidebar dashboards, metric cards, searchable/filterable tables, job cards, match percentages, and responsive layouts. The green/navy concept in `Design Idea.png` is the primary visual reference because it contains the broadest screen coverage. The indigo concept in `designe idea 2.png` is a secondary reference for missing states and layout alternatives.

## 2. Source reconciliation and authority

The sources describe the same product but differ technically.

| Topic | Original requirements (`drVUnj.docx`) | New backend design / user direction | Adopted baseline |
|---|---|---|---|
| Frontend | HTML, CSS, JavaScript, Bootstrap, Jinja2 | React frontend through REST APIs | React with responsive CSS/component system; visually follow supplied screens |
| Backend | Flask | FastAPI, Pydantic v2, Clean Architecture | FastAPI |
| Authentication | Server session / Flask-Login | JWT access and refresh tokens, RBAC | JWT with refresh-token rotation and role guards |
| ORM | Flask-SQLAlchemy | SQLAlchemy 2.0 + Alembic | SQLAlchemy 2.0 + Alembic |
| Resume types | PDF only | PDF/DOC/DOCX pipeline | PDF only for MVP; extension-ready validation abstraction |
| Scoring | TF-IDF/cosine similarity and keyword overlap | Gemini semantic score, summary, skills, recommendation | Deterministic TF-IDF score is authoritative; optional Gemini enrichment must not block applications |
| Processing | Immediate | FastAPI BackgroundTasks | Create application quickly with `processing` status; process in background |
| Database | SQLite | SQLite, future PostgreSQL | SQLite locally; schema and configuration remain PostgreSQL-compatible |
| Testing | Not detailed | `unittest` | `pytest` is recommended for FastAPI ergonomics; use `unittest` only if academically mandatory |

Business requirements from the original document remain mandatory unless explicitly superseded.

## 3. Roles and permissions

### Applicant

- Register and sign in.
- View only open, non-deleted jobs belonging to active employers.
- Search and filter the job board.
- View a job's complete details and required skills.
- Upload one PDF resume per job and submit an application.
- View personal application history and processing/result status.
- View and edit own profile.

### Employer

- Register and sign in.
- View dashboard statistics for owned jobs and applications.
- Create, read, update, open, and close owned jobs.
- View owned jobs only in employer management screens.
- View applications for an owned job, ranked by final match score descending.
- View applicant name, email, matched skills, score, and processing status.
- Download the original resume only for applications to an owned job.
- View and edit employer/company profile.

### Admin

- Sign in through a pre-provisioned account; public admin registration is forbidden.
- View platform totals and trends.
- Search/filter all non-admin users and all jobs.
- Suspend/reactivate users and permanently delete them through an explicit destructive workflow.
- Remove inappropriate/spam jobs.
- View audit activity and processing totals.

### Authorization invariants

- Authentication never implies authorization.
- Every employer resource query is ownership-scoped.
- Every applicant resource query is applicant-scoped.
- Suspended/deleted users cannot authenticate or refresh tokens.
- Admin endpoints require the admin role and cannot be reached by changing client-side navigation.

## 4. Screen and route map

| Screen | Suggested route | Role | Core API dependencies |
|---|---|---|---|
| Landing | `/` | Public | Optional public platform metrics |
| Login | `/login` | Public | login, refresh, current user |
| Registration | `/register` | Public | register applicant/employer |
| Employer dashboard | `/employer/dashboard` | Employer | dashboard metrics, recent jobs, top applicants |
| Post/edit job | `/employer/jobs/new`, `/employer/jobs/:id/edit` | Employer | job create/update |
| My jobs | `/employer/jobs` | Employer | owned job list/filter/pagination |
| Ranked applicants | `/employer/jobs/:id/applications` | Employer | ranked applications, resume download |
| Employer profile | `/employer/profile` | Employer | profile read/update |
| Applicant job board | `/applicant/jobs` | Applicant | open job list/search/filter |
| Job details/apply | `/applicant/jobs/:id` | Applicant | job detail, multipart application submit |
| My applications | `/applicant/applications` | Applicant | own application history/status |
| Applicant profile | `/applicant/profile` | Applicant | profile read/update |
| Admin dashboard | `/admin/dashboard` | Admin | aggregate metrics/trends/activity |
| User management | `/admin/users` | Admin | users list/suspend/reactivate/delete |
| Job moderation | `/admin/jobs` | Admin | all jobs list/delete |
| Not found/forbidden/error | dedicated state routes | All | standardized API errors |

Notifications, messages, reports, settings, hiring stages, and interview workflows appear in some design concepts but are not required by the written MVP. They are deferred unless explicitly approved.

## 5. End-to-end user flows

### 5.1 Registration and login

1. User chooses Employer or Applicant and supplies full name, unique email, and password.
2. API validates normalized email and password policy, hashes the password, and creates the profile atomically.
3. User signs in; API returns a short-lived access token and a rotated refresh token.
4. Frontend loads `/auth/me` and routes by server-returned role.
5. Logout revokes the refresh session and clears client authentication state.

### 5.2 Employer hiring flow

1. Employer creates a draft/open job with title, description, required skills, and optional design-supported metadata.
2. Open jobs become visible to applicants; closed jobs remain visible only to owner/admin.
3. Employer dashboard shows owned-job counts and application aggregates.
4. Employer opens a job's applicant table.
5. API returns applications ordered by completed scores descending, with pending/failed items clearly labeled.
6. Employer downloads an authorized resume through a protected endpoint.

### 5.3 Applicant application flow

1. Applicant searches open jobs and opens details.
2. Frontend accepts a `.pdf`; server independently verifies size, MIME signature, extension, and readability.
3. A unique database constraint prevents a second application to the same job.
4. API stores the file under a generated identifier, creates an application with `processing`, and schedules processing.
5. Worker extracts text, calculates deterministic similarity, optionally enriches with Gemini, and persists results.
6. Applicant sees `processing`, `completed`, or `failed`; employer ranking updates when completed.

### 5.4 Admin moderation flow

1. Admin views platform metrics and recent activity.
2. Admin filters users or jobs.
3. Suspending a user blocks authentication and hides their open jobs from the public board.
4. Destructive delete requires confirmation and creates an audit record. Default implementation should prefer soft deletion for traceability; permanent purge can be a separate explicit operation.

## 6. Architecture

Use a modular monolith with dependency flow toward the domain/application layers.

```text
React client
    |
Nginx / HTTPS
    |
FastAPI presentation (routers, dependencies, schemas)
    |
Application services / use cases / unit of work
    |
Domain entities, policies, repository interfaces
    |
Infrastructure (SQLAlchemy, storage, PDF parser, TF-IDF, Gemini, logging)
    |
SQLite locally; PostgreSQL-compatible boundary for production evolution
```

Business rules belong in services/domain policies, not routers or repositories. Repositories isolate persistence. A unit of work controls multi-write transactions. Provider interfaces isolate resume extraction, scoring, file storage, and LLM calls.

## 7. Proposed repository structure

```text
SmartHire/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/v1/{router.py,endpoints/}
│   │   ├── core/{config.py,exceptions.py,logging.py,security.py}
│   │   ├── domain/{entities,interfaces,policies}/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── infrastructure/{database,storage,parsers,scoring,ai}/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── dependencies/
│   │   ├── middleware/
│   │   ├── background/
│   │   ├── constants/
│   │   └── enums/
│   ├── alembic/
│   ├── scripts/create_admin.py
│   ├── tests/{unit,integration,api}/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/{router,providers,store}/
│   │   ├── api/
│   │   ├── components/{ui,layout,feedback}/
│   │   ├── features/{auth,jobs,applications,dashboards,admin,profile}/
│   │   ├── pages/
│   │   ├── styles/
│   │   ├── types/
│   │   └── utils/
│   ├── tests/
│   ├── package.json
│   └── Dockerfile
├── deploy/nginx/
├── storage/resumes/          # ignored; local development only
├── docs/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## 8. Data model

All primary keys should be UUIDs. All entities include timezone-aware `created_at` and `updated_at`. Use normalized UTC in storage.

### `users`

- `id`, `email` (unique, normalized), `password_hash`, `full_name`
- `role`: `admin | employer | applicant`
- `status`: `active | suspended | deleted`
- `last_login_at`, audit timestamps, optional `deleted_at`

### `employer_profiles`

- `user_id` (unique FK), `company_name`, `location`, `website`, `description`

### `applicant_profiles`

- `user_id` (unique FK), `headline`, `location`, `phone`, optional structured skills

### `jobs`

- `id`, `employer_id`, `title`, `description`
- `required_skills` as normalized JSON/list for SQLite portability
- `status`: `open | closed | deleted`
- Optional UI metadata: `location`, `work_mode`, `employment_type`, `experience_level`, `education`, `salary_min`, `salary_max`, `currency`
- `published_at`, audit timestamps, optional `deleted_at`
- Indexes: employer/status, status/published date, normalized title/search fields

### `resumes`

- `id`, `applicant_id`, generated `storage_key`, original filename
- `mime_type`, `size_bytes`, `sha256`, extraction status/error
- extracted text should be protected and excluded from ordinary API responses

### `applications`

- `id`, `job_id`, `applicant_id`, `resume_id`
- `status`: `processing | completed | failed | withdrawn`
- `deterministic_score`, optional `ai_score`, `final_score`
- `matched_skills`, optional summary/recommendation, processing error, processed timestamp
- Unique constraint: `(job_id, applicant_id)`
- Indexes: job/final score, applicant/created date, processing status

### `refresh_sessions`

- `id`/token ID, `user_id`, hashed refresh token or token fingerprint
- expiry, revocation timestamp, rotation family, user-agent/IP metadata where appropriate

### `audit_logs`

- actor, action, target type/id, timestamp, request/correlation ID, safe metadata
- Never store passwords, raw JWTs, or full resume text in logs.

## 9. API contract

### Response envelopes

Success:

```json
{"success": true, "message": "Job created", "data": {}}
```

Validation/domain error:

```json
{
  "success": false,
  "message": "Validation failed",
  "error": {"code": "VALIDATION_ERROR", "details": []},
  "request_id": "..."
}
```

Lists include `items` and `meta` with page, page size, total items, and total pages. Sorting fields must be allow-listed.

### Authentication

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/register` | Applicant/employer registration only |
| POST | `/auth/login` | Authenticate and issue token pair |
| POST | `/auth/refresh` | Rotate refresh token and issue new access token |
| POST | `/auth/logout` | Revoke refresh session |
| POST | `/auth/logout-all` | Revoke all user's refresh sessions |
| GET | `/auth/me` | Current identity, role, and profile summary |

### Profiles and jobs

| Method | Endpoint | Role/purpose |
|---|---|---|
| GET/PATCH | `/profiles/me` | Current user's profile |
| GET | `/jobs` | Applicant/public-authorized open-job search |
| GET | `/jobs/{job_id}` | Open job details; owner/admin can access closed jobs |
| POST | `/employer/jobs` | Create owned job |
| GET | `/employer/jobs` | List owned jobs |
| GET/PATCH | `/employer/jobs/{job_id}` | Read/update owned job |
| PATCH | `/employer/jobs/{job_id}/status` | Open/close owned job |
| DELETE | `/employer/jobs/{job_id}` | Soft-delete owned job subject to policy |

### Applications and resume access

| Method | Endpoint | Role/purpose |
|---|---|---|
| POST | `/jobs/{job_id}/applications` | Applicant multipart PDF submission; returns `202` when queued |
| GET | `/applicant/applications` | Own application history |
| GET | `/applicant/applications/{id}` | Own application details/status |
| GET | `/employer/jobs/{job_id}/applications` | Ranked applications for owned job |
| GET | `/employer/applications/{id}` | Application details for owned job |
| GET | `/employer/applications/{id}/resume` | Authorized streamed PDF download |

### Dashboards and admin

| Method | Endpoint | Role/purpose |
|---|---|---|
| GET | `/employer/dashboard` | Owned hiring metrics and top applicants |
| GET | `/admin/dashboard` | System totals/trends/recent activity |
| GET | `/admin/users` | Paginated/filterable users |
| PATCH | `/admin/users/{id}/status` | Suspend/reactivate |
| DELETE | `/admin/users/{id}` | Explicit deletion workflow |
| GET | `/admin/jobs` | All jobs including closed |
| DELETE | `/admin/jobs/{id}` | Moderation removal |
| GET | `/admin/audit-logs` | Audit history |
| GET | `/health` | Process health |
| GET | `/ready` | Database/storage readiness |

## 10. Resume processing and scoring

### Validation and storage

- MVP accepts PDF only, with a configurable size limit (proposed 5 MB, matching the UI concept).
- Validate extension, declared content type, PDF magic bytes, parseability, page/text limits, and generated storage path.
- Never use the original filename as a filesystem path.
- Store outside public/static directories and stream through an authorized API.
- Compute SHA-256 for integrity/diagnostics; a duplicate file hash does not replace the one-application-per-job rule.

### Deterministic pipeline

1. Extract readable text with `pypdf` or `pdfplumber`.
2. Reject or mark failed if no meaningful text is extractable; OCR is a future enhancement.
3. Build reference text from job title, description, and required skills, with skills optionally weighted by repetition or a separate component.
4. Normalize Unicode/case/whitespace and punctuation consistently.
5. Calculate TF-IDF cosine similarity.
6. Calculate explicit normalized required-skill overlap.
7. Proposed transparent formula: `final deterministic score = 75% TF-IDF + 25% skill coverage`, clamped to 0-100 and rounded consistently.
8. Store matched skills and component scores for explainability.

### Optional Gemini enrichment

- Interface: `LLMProvider`; implementation: `GeminiProvider`; disabled/null provider for offline development.
- May produce summary, extracted skills, semantic score, and recommendation.
- Must use structured validated output, strict timeouts, bounded retries, and prompt/version metadata.
- Must not send data unless configured and disclosed; avoid logging prompts/resumes.
- Gemini failure cannot fail the deterministic screening result.
- For MVP ranking, deterministic score should remain authoritative unless a later product decision defines a tested blended formula.

### Background execution caveat

FastAPI `BackgroundTasks` satisfies the supplied design for a single-instance MVP, but tasks are not durable across process restarts. Keep a processor interface and persisted statuses so a later queue such as Celery/RQ/Arq can be introduced without changing API contracts.

## 11. Frontend design system

### Visual direction

- Primary palette: deep navy sidebar/header, royal blue actions, green success/match indicators, neutral white/light-gray surfaces.
- Rounded cards with fine borders and restrained shadows.
- Compact professional tables, skill chips, progress bars, role-aware side navigation.
- Preserve information hierarchy and screen composition from the supplied collages; exact sample counts/names are placeholder content only.
- Provide desktop, tablet, and mobile behavior; tables become horizontally scrollable or card-based on narrow screens.

### Required states

Every data screen needs loading skeletons, empty states, retryable errors, forbidden/not-found states, pagination feedback, confirmation dialogs, success/error toasts, keyboard focus, and accessible labels. Score must be accompanied by text, not color alone.

### Client architecture

- Feature-oriented React modules and a typed API client.
- Server-state caching (for example TanStack Query) and minimal global client state.
- Route guards improve UX, but API RBAC is authoritative.
- Prefer an access token held in memory and an HttpOnly, Secure, SameSite refresh cookie where deployment topology allows it; add CSRF protection to cookie-authenticated state-changing endpoints.

## 12. Security and privacy baseline

- Password hashing with bcrypt (or Argon2 if approved), no plaintext/reversible storage.
- Short access-token lifetime, refresh rotation/revocation, unique token IDs, strict algorithm/issuer/audience validation.
- Rate-limit authentication, uploads, and destructive admin operations.
- CORS allow-list and TrustedHost configuration from environment settings.
- Pydantic validation plus server-side business validation.
- Ownership checks and RBAC at service/dependency boundaries.
- Safe file names, content validation, size/page limits, non-public storage, authorized downloads.
- Generic login errors; standardized non-leaking exceptions.
- Secrets only through environment/secret management; `.env` and uploaded resumes ignored by Git.
- Audit login, moderation, status changes, downloads, and destructive actions.
- Define retention/deletion rules for resumes and extracted text before production.
- Back up database and resume storage together; regularly test restoration.

## 13. Observability and operations

- Structured logs with UTC timestamp, level, logger/file/function/line, request ID, user ID when safe, event, and message.
- Console logs for containers and rotating file logs for local/required deployment.
- Health endpoint checks process; readiness checks database and writable storage.
- Metrics: request latency/error rate, login failures, uploads, processing duration/failure, queue/pending count, AI calls/failures, storage usage.
- Avoid high-cardinality/sensitive resume content in logs and metrics.

## 14. Testing strategy

### Backend

- Unit: normalization, scoring, status rules, permissions, token logic, validators.
- Repository: CRUD, ownership filters, unique application constraint, ordering and pagination.
- Service: registration, jobs, apply, processing transitions, suspension/deletion.
- API integration: success and error contracts for every role.
- Security: horizontal privilege escalation, role bypass, token refresh/revocation, malicious uploads, path traversal, inactive users.
- Migration: upgrade from empty database and downgrade/forward tests where practical.

### Frontend

- Component and form tests for critical states.
- API mocking for role flows and failures.
- End-to-end: register/login, employer posts job, applicant applies, processing completes, employer views rank/downloads, admin suspends user/moderates job.
- Accessibility checks and responsive viewport snapshots against design references.

### Quality gates

- Formatting, linting, strict type checking, tests, migration check, production builds, dependency/security scans, and Docker health check.
- Target at least 80% meaningful backend service/domain coverage; do not chase coverage through trivial assertions.

## 15. Deployment topology

```text
Internet -> HTTPS/Nginx -> React static assets
                         -> /api -> Uvicorn/FastAPI
                                      |-> database
                                      |-> private resume volume/object storage
                                      |-> optional Gemini API
```

- Multi-stage production Dockerfiles and non-root runtime users.
- Docker Compose for local/staging parity.
- Environment-specific settings and explicit startup migration procedure.
- SQLite is acceptable for a single-instance semester deployment. PostgreSQL is recommended before multi-instance or high-concurrency production.
- Persist database and resume storage in mounted volumes; never inside ephemeral container layers.
- HTTPS, secure cookies, backup/restore runbook, log aggregation, health checks, and rollback procedure are production gates.

## 16. MVP acceptance criteria

- Applicant and employer can register; admin cannot self-register.
- Unique normalized emails and hashed passwords are enforced.
- Login/refresh/logout work and role-specific routing matches server identity.
- Employer can create, edit, open, close, and list owned jobs.
- Applicant sees only eligible open jobs and can submit one valid PDF per job.
- Invalid, oversized, unreadable, and duplicate submissions return clear structured errors.
- Resume is processed asynchronously and application status is visible.
- Deterministic score is saved from 0-100 with matched skills.
- Employer sees only owned-job candidates ordered by score and can securely download their PDFs.
- Applicant sees only their own applications.
- Admin sees correct totals, can suspend/reactivate users, and moderate jobs.
- All authorization rules are verified with negative tests.
- Migrations, local setup, tests, Docker deployment, health/readiness, backup, and admin provisioning are documented.

## 17. Deferred enhancements

- Applicant hiring stages, shortlisting, interview scheduling, messages, notifications.
- OCR for scanned resumes and DOC/DOCX support.
- Durable task queue, email delivery, object storage, antivirus scanning.
- PostgreSQL, full-text/vector search, advanced analytics.
- Explainable AI calibration, bias monitoring, consent controls, and multi-provider LLM support.
- Multi-tenancy, employer teams, invitations, billing, and localization.
