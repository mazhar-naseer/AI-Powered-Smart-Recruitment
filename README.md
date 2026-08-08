# SmartHire

SmartHire is a production-oriented, AI-assisted recruitment platform built with FastAPI, React, and PostgreSQL. It supports applicants, employers, and platform administrators through secured role-specific workflows, a dedicated Admin Control Center, verified-email registration, private resume processing, and explainable hybrid candidate matching.

> SmartHire supports recruiter decision-making; it must not make fully automated hiring or rejection decisions. Hybrid score disagreements are flagged for human review.

## Core features

### Applicant experience

- Email-verified account registration and automatic login after verification
- Comprehensive professional profile with private photo, biography, contact details, links, skills, education, languages, experience, availability, notice period, and work-mode preferences
- Searchable job board and detailed job views
- Private PDF resume upload with duplicate-application prevention
- Real-time processing status and retryable analysis failures
- Explainable match report containing deterministic and Gemini scores
- KPI breakdown, matched skills, missing evidence, AI confidence, and recommendations
- Clear “Application already submitted” state

### Employer experience

- Email-verified employer registration
- Branded employer profile with private photo, company overview, industry, size, founding year, website, hiring interests, workplace languages, and professional links
- Dashboard and job lifecycle management
- Field-level job-form validation with actionable messages
- Ranked applicant lists and secure resume downloads
- Candidate match scores, evidence, strengths, and gaps
- Multi-company workspaces with an explicit active-workspace switcher
- Recruiter invitations and owner/admin/recruiter/viewer permissions
- Configurable hiring pipeline with protected default stages and custom stages
- Candidate assignments, tags, internal notes, and an immutable activity timeline
- Account notification center for invitations, assignments, new applicants, and stage progress

### Admin Control Center

- Dedicated administrator entry point at `/admin/login`
- Visually separate operations interface—not the applicant/employer shell
- Platform metrics and processing overview
- Identity and access management
- User suspension and activation
- Job-content moderation
- Server-enforced admin RBAC for every administrative endpoint
- No public admin registration; the first administrator is provisioned locally, then authenticated administrators can securely create additional admins from Identity & Access

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, React Router, Lucide icons |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy |
| Database | PostgreSQL 17, Psycopg, Alembic migrations |
| Authentication | JWT access and refresh tokens, bcrypt password hashing, role-based access control |
| Resume parsing | PyPDF |
| Deterministic intelligence | scikit-learn TF-IDF and cosine similarity, skills/title/experience evidence |
| AI intelligence | Google Gemini structured JSON assessment |
| Email | SMTP with professional HTML verification emails; local outbox fallback |
| Testing | Pytest, Vitest, Testing Library, Playwright |
| Deployment | Docker Compose, Nginx frontend container, Uvicorn backend |

## System architecture

```text
React application
├── Applicant portal
├── Employer portal
└── Separate Admin Control Center
          │
          ▼
FastAPI REST API
├── JWT authentication and RBAC
├── Job and application services
├── Resume processing
├── Deterministic scoring
├── Gemini enrichment and guardrails
├── Email verification
├── Multi-tenant workspace and ATS services
├── Durable background-job processing
├── Private object-storage abstraction
├── Notifications
└── Audit and operations monitoring
          │
          ▼
PostgreSQL + private resume storage
```

## Market-ready ATS foundation

Each employer belongs to one or more isolated company workspaces. Jobs, candidates, pipeline stages, recruiter memberships, notifications, audit context, and background jobs carry an organization identifier; API permission checks verify the active membership instead of trusting a client-provided company ID.

| Workspace role | Organization/team | Jobs | Candidates | Notes | Analytics |
|---|---:|---:|---:|---:|---:|
| Owner | Manage | Manage | Manage | Add | View |
| Admin | Team | Manage | Manage | Add | View |
| Recruiter | — | Manage | Manage | Add | View |
| Viewer | — | — | Read | — | View |

The ATS includes:

- Secure seven-day recruiter email invitations, acceptance, revocation, role changes, and member removal
- Per-company stages with Applied, Screening, Interview, Offer, Hired, and Rejected defaults
- Owner-controlled custom stages, ordering, naming, and colors
- Candidate board, filtering, assignment, tags, notes, and chronological events
- Private resume keys that never expose host filesystem paths
- Database-backed analysis jobs with retry limits, scheduling, failure details, and administrator retry APIs
- Employer and admin operational views backed by audit and queue metrics

Primary employer screens are `/employer/team`, `/employer/pipeline`, `/employer/pipeline/settings`, `/employer/candidates/:id`, and `/notifications`. Platform monitoring is available at `/admin/operations`.

## Commercial SaaS layer

Every company workspace has an independent subscription, plan entitlement set, monthly usage ledger, branding/privacy configuration, and audited data export. Employer owners access this at `/employer/settings`; platform administrators monitor all tenant accounts at `/admin/saas` in the separate Control Center.

Included commercial capabilities:

- Starter, Growth, and Scale plan catalog with server-enforced active-job, team-member, AI-analysis, and storage entitlements
- Trial and active subscription lifecycle stored per organization
- Tenant usage meters that cannot be bypassed by hiding frontend controls
- Owner-only company identity, timezone, careers URL, brand color, notification, and retention settings
- Tenant-scoped JSON data portability export with an immutable audit record
- Provider-neutral billing webhook with HMAC verification and event idempotency
- Manual billing mode for complete local testing without charging a card
- Platform-wide tenant count, active subscriptions, plan distribution, and estimated MRR

Local development uses `BILLING_PROVIDER=manual`; selecting a plan changes the tenant subscription immediately so every entitlement can be tested. Before accepting real payments, connect the checkout/customer-portal calls to a provider such as Stripe and set a strong `BILLING_WEBHOOK_SECRET`. The backend webhook contract and provider identifiers are already isolated from the ATS and AI domains.

## Explainable hybrid matching

Every valid resume is evaluated by two independent engines.

### 1. Advanced deterministic Python engine

The deterministic score is fully reproducible and always runs, even when Gemini is unavailable.

The employer configures a per-job scorecard that must total 100%. Defaults are semantic relevance 15%, skill evidence 35%, experience 25%, role alignment 15%, domain knowledge 5%, and education/certifications 5%. The semantic component combines word and character n-gram vectors. Skill detection uses a normalized ontology, so aliases such as `Postgres`/`PostgreSQL` and `JS`/`JavaScript` are evaluated consistently.

Skills can be mandatory, preferred, or optional. Missing a mandatory skill caps the deterministic result at 55%. Each criterion stores matched status, priority, criterion score, and supporting resume snippets in an evidence matrix.

### 2. Gemini assessment

When enabled, Gemini returns structured:

- Overall semantic score
- Skills, experience, and role-alignment scores
- Confidence value
- Evidence-based strengths and gaps
- Summary and recommendation

Resume and job text are marked as untrusted data in the model prompt. Gemini is instructed to ignore embedded instructions, avoid protected characteristics, and never invent candidate evidence.

### 3. Confidence-adjusted hybrid result

Gemini receives at most 35% influence. Its real influence is reduced when model confidence is lower.

```text
Effective Gemini weight = maximum Gemini weight × Gemini confidence
Deterministic weight     = 100% − effective Gemini weight
Final score              = deterministic contribution + Gemini contribution
```

Default guardrails:

- Deterministic scoring always remains the anchor
- Gemini cannot receive more than 35% influence
- Gemini timeout or failure falls back safely to the deterministic result
- Both scores, effective weights, confidence, and provider are stored
- A difference of 25 points or more sets `manual_review_required`
- No score automatically hires or rejects a person

### 4. Advanced intelligence operations

- Applicant uploads accept text PDF and DOCX; image-only PDFs use an optional OCR fallback when Tesseract is installed
- Every result stores parser, analysis, and Gemini prompt versions plus a snapshot of the job scorecard
- Employers configure weights, priorities, domains, education, and certifications in **AI Scorecard Studio**
- Employers can re-analyze historical applications after changing a scorecard
- Employer/admin score overrides require a written reason and create immutable override-history records
- The Admin **Intelligence Monitor** reports score distribution, Gemini completion, engine disagreement, manual-review volume, and override rate
- Protected characteristics are intentionally excluded from scoring and monitoring

## Repository structure

```text
SmartHire/
├── backend/
│   ├── app/                    # FastAPI application and domain services
│   ├── alembic/versions/       # PostgreSQL schema migrations
│   ├── scripts/create_admin.py # Local admin provisioning
│   ├── tests/                  # Backend tests
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/                    # React application
│   ├── e2e/                    # Playwright tests
│   ├── Dockerfile
│   └── package.json
├── docs/                       # Blueprint, execution plan, and testing guide
├── storage/resumes/            # Local private resume storage (runtime)
├── .env.example
├── docker-compose.yml
└── requirements.txt
```

## Prerequisites

- Python 3.12+
- Node.js 20+ and npm
- PostgreSQL 15+ (PostgreSQL 17 recommended)
- Optional Gemini API key
- Optional SMTP account for real verification email delivery

## Environment configuration

Create the local environment file:

```bash
cp .env.example .env
```

At minimum, replace the database password and application secret:

```env
ENVIRONMENT=development
SECRET_KEY=replace-with-a-long-random-secret

POSTGRES_DB=smarthire
POSTGRES_USER=smarthire
POSTGRES_PASSWORD=replace-with-a-strong-password
DATABASE_URL=postgresql+psycopg://smarthire:replace-with-a-strong-password@localhost:5432/smarthire

FRONTEND_ORIGINS=http://localhost:5173
FRONTEND_URL=http://localhost:5173
```

Hybrid intelligence configuration:

```env
GEMINI_API_KEY=your-api-key
GEMINI_MODEL=gemini-3.6-flash
GEMINI_ENABLED=true
GEMINI_WEIGHT=0.35
GEMINI_TIMEOUT_SECONDS=30
HYBRID_DISAGREEMENT_THRESHOLD=25
```

`GEMINI_WEIGHT` must be between `0` and `0.5`. If `GEMINI_API_KEY` is empty or Gemini is disabled, deterministic processing remains fully operational.

For real verification emails:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-username
SMTP_PASSWORD=your-password
SMTP_FROM_EMAIL=no-reply@yourdomain.com
SMTP_USE_TLS=true
```

Without SMTP configuration, development emails are saved to `.outbox/`, and a development verification code is returned to the local UI.

Commercial SaaS configuration:

```env
BILLING_PROVIDER=manual
BILLING_WEBHOOK_SECRET=
TRIAL_DAYS=14
```

`manual` mode is intended for local validation and internal invoicing. A real payment provider must supply checkout and customer-portal integration before public card billing is enabled.

Never commit `.env`, SMTP credentials, JWT secrets, database passwords, or Gemini API keys.

Google login configuration:

```env
GOOGLE_OAUTH_ENABLED=true
GOOGLE_CLIENT_ID=your-google-web-client-id
GOOGLE_CLIENT_SECRET=your-google-web-client-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/v1/auth/oauth/google/callback
```

The Google Cloud OAuth client redirect URI must match this value exactly. New users select Applicant or Employer on the registration page before continuing with Google; the login-page button signs in existing linked or email-matched accounts only.

## Local installation

### 1. Create the Python environment

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e 'backend[dev]'
```

Conventional requirements files are also available:

```bash
pip install -r requirements.txt
pip install -r backend/requirements-dev.txt
```

### 2. Start PostgreSQL

Use an existing local PostgreSQL server, or start only the Docker database:

```bash
docker compose up -d postgres
```

### 3. Apply database migrations

```bash
cd backend
../.venv/bin/alembic upgrade head
```

### 4. Create an administrator

Public registration intentionally supports only applicants and employers. Use the script once to bootstrap the first administrator.

```bash
../.venv/bin/python scripts/create_admin.py \
  --email admin@smarthire.local \
  --password 'ReplaceWithAStrongPassword!' \
  --name 'SmartHire Administrator'
```

The account is created as active and email-verified in PostgreSQL.

After signing in to the Admin Control Center, additional administrators can be created from **Identity & Access → Create Administrator**. This action requires an existing admin JWT, enforces a strong password, and writes an audit event.

### 5. Start the backend

From `backend/`:

```bash
../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend endpoints:

- API base: `http://127.0.0.1:8000/api/v1`
- OpenAPI documentation: `http://127.0.0.1:8000/api/docs`
- Health check: `http://127.0.0.1:8000/health`
- Readiness check: `http://127.0.0.1:8000/ready`

### 6. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend URLs:

- Public application: `http://127.0.0.1:5173`
- Applicant/employer login: `http://127.0.0.1:5173/login`
- Admin Control Center login: `http://127.0.0.1:5173/admin/login`
- Admin dashboard: `http://127.0.0.1:5173/admin`

If Vite reports that `5173` is occupied, use the alternate port printed in the terminal.

## One-click FastAPI debugging in PyCharm

The repository includes a shared run configuration at `.run/SmartHire_Backend_Debug.run.xml`.

1. Open the `SmartHire` repository root in PyCharm.
2. Set the project interpreter to `SmartHire/.venv/bin/python`.
3. Select **SmartHire Backend Debug** in the top run-configuration selector.
4. Add a breakpoint inside `backend/app/api.py` or another backend module.
5. Click the **Debug** button.

The configuration runs the equivalent of:

```bash
cd backend
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The working directory is intentionally `backend/`, allowing Pydantic Settings to load the root `.env` through the configured `../.env` path. Debug mode intentionally omits Uvicorn `--reload`: reload starts a child process and can make breakpoints inconsistent. Restart the debugger after backend code changes.

### Run background processing locally

Development defaults to inline processing for convenient debugging. To test the production-style durable worker, set `INLINE_BACKGROUND_JOBS=false`, keep the API running, then start this in another terminal:

```bash
cd backend
../.venv/bin/python scripts/run_worker.py
```

Applications remain queued in PostgreSQL until a worker claims them. Failed jobs retry with backoff up to the configured maximum; administrators can inspect and requeue terminal jobs from Operations.

If port `8000` is already occupied, stop the terminal-launched backend before starting the debugger:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

## Role workflows

### Applicant

```text
Register → verify email → automatic login → browse jobs → upload PDF or DOCX
→ deterministic analysis → Gemini analysis → inspect explainable result
```

### Employer

```text
Register → verify email → automatic login → publish job
→ configure AI Scorecard Studio → review ranked applicants → inspect evidence
→ optionally re-analyze or record an audited human override → securely view/download resume
→ manage workspace plan, quota usage, brand/privacy settings, and tenant export
```

### Administrator

```text
Provision through Control Center or script → open /admin/login → authenticate
→ manage users/jobs → inspect evidence/resumes → monitor intelligence quality
```

## Testing and verification

Backend tests:

```bash
.venv/bin/pytest -q backend/tests
```

Backend tests use an isolated SQLite database for speed; the deployed application uses PostgreSQL.

Frontend unit tests and production build:

```bash
cd frontend
npm run test
npm run build
```

End-to-end browser tests:

```bash
cd frontend
npx playwright install
npm run e2e
```

Additional test scenarios and manual QA instructions are documented in [docs/TESTING.md](docs/TESTING.md).
The completed commercial phase report is available in [docs/COMMERCIAL_SAAS_TEST_REPORT.md](docs/COMMERCIAL_SAAS_TEST_REPORT.md).

## API and processing behavior

- JWT access and refresh tokens secure authenticated requests
- Backend role checks protect applicant, employer, and admin APIs
- Unverified users cannot log in
- Verification codes and links expire and cannot be replayed
- One applicant can apply to each job only once
- PDF and DOCX resumes within the configured size limit are accepted
- Private resumes are downloadable only by the employer who owns the associated job
- Scanned PDFs use OCR when its optional system dependency is available; otherwise they return a clear retryable error
- Gemini failure never converts a successfully parsed resume into a failed application
- Existing deterministic-only records can use the “Retry Gemini analysis” action
- Administrative actions and important authentication events are audited

## Docker deployment

Configure `.env`, then run:

```bash
docker compose build
docker compose up -d
docker compose exec backend python scripts/create_admin.py \
  --email admin@example.com \
  --password 'ReplaceWithAStrongPassword!' \
  --name 'Platform Administrator'
```

Open:

- Application: `http://localhost:8080`
- Admin Control Center: `http://localhost:8080/admin/login`

The backend waits for PostgreSQL, applies Alembic migrations, and starts Uvicorn. The separate `worker` service claims durable analysis jobs. PostgreSQL data, resumes, and avatars are stored in named Docker volumes.

## Cloud deployment

For a hosted deployment, see [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md) — backend and PostgreSQL on Railway, frontend on Vercel, uploaded files on Cloudinary. [docs/GITHUB_ACTIONS_DEPLOYMENT.md](docs/GITHUB_ACTIONS_DEPLOYMENT.md) covers automating it.

Set `USE_CLOUDINARY=true` on any host with an ephemeral filesystem. Uploads written to local disk there are lost on every redeploy and restart. With it on, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` are all required, resumes and avatars are stored on Cloudinary only, and local disk is never used.

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` to seed the first administrator at startup — registration refuses the admin role, so a new deployment has no other way in. It is applied only when no administrator exists, and never changes an existing account. Sign in and create any further administrators from the Control Center.

## Production recommendations

- Deploy the application, admin portal, and API behind HTTPS
- Prefer separate hosts such as `app.example.com`, `admin.example.com`, and `api.example.com`
- Restrict the admin host with SSO, MFA, VPN, or an identity-aware proxy
- Use a managed secret store instead of plaintext environment files
- Replace the included database-backed worker with a dedicated broker such as Redis/SQS when sustained throughput requires horizontal worker scaling
- Encrypt resume storage and database backups
- Define resume retention and deletion policies
- Add malware scanning for uploaded files
- Monitor Gemini latency, errors, token usage, and score drift
- Periodically audit scoring fairness and disagreement rates
- Never use AI scores as the sole basis for an employment decision

## Documentation

- [Project blueprint](docs/PROJECT_BLUEPRINT.md)
- [Execution plan](docs/EXECUTION_PLAN.md)
- [Testing guide](docs/TESTING.md)
- [Decisions and open questions](docs/DECISIONS_AND_QUESTIONS.md)
- [Railway deployment guide](docs/RAILWAY_DEPLOYMENT.md)
- [GitHub Actions deployment](docs/GITHUB_ACTIONS_DEPLOYMENT.md)

## License

No license has been declared yet. Add an appropriate license before distributing or using the project commercially.
