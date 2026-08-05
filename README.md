# SmartHire

SmartHire is a production-oriented, AI-assisted recruitment platform built with FastAPI, React, and PostgreSQL. It supports applicants, employers, and platform administrators through secured role-specific workflows, a dedicated Admin Control Center, verified-email registration, private resume processing, and explainable hybrid candidate matching.

> SmartHire supports recruiter decision-making; it must not make fully automated hiring or rejection decisions. Hybrid score disagreements are flagged for human review.

## Core features

### Applicant experience

- Email-verified account registration and automatic login after verification
- Searchable job board and detailed job views
- Private PDF resume upload with duplicate-application prevention
- Real-time processing status and retryable analysis failures
- Explainable match report containing deterministic and Gemini scores
- KPI breakdown, matched skills, missing evidence, AI confidence, and recommendations
- Clear “Application already submitted” state

### Employer experience

- Email-verified employer registration
- Dashboard and job lifecycle management
- Field-level job-form validation with actionable messages
- Ranked applicant lists and secure resume downloads
- Candidate match scores, evidence, strengths, and gaps

### Admin Control Center

- Dedicated administrator entry point at `/admin/login`
- Visually separate operations interface—not the applicant/employer shell
- Platform metrics and processing overview
- Identity and access management
- User suspension and activation
- Job-content moderation
- Server-enforced admin RBAC for every administrative endpoint
- No public admin registration; administrators are provisioned through a local script

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
└── Audit logging
          │
          ▼
PostgreSQL + private resume storage
```

## Explainable hybrid matching

Every valid resume is evaluated by two independent engines.

### 1. Deterministic Python engine

The deterministic score is fully reproducible and always runs, even when Gemini is unavailable.

```text
Semantic relevance (TF-IDF + cosine similarity)   50%
Required-skill coverage                           30%
Job-title/role alignment                          10%
Experience evidence                               10%
```

Matching every skill does not automatically produce a 100% score because required skills contribute 30% of the deterministic result; full-document relevance, role alignment, and experience contribute the remaining 70%.

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

Never commit `.env`, SMTP credentials, JWT secrets, database passwords, or Gemini API keys.

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

Public registration intentionally supports only applicants and employers.

```bash
../.venv/bin/python scripts/create_admin.py \
  --email admin@smarthire.local \
  --password 'ReplaceWithAStrongPassword!' \
  --name 'SmartHire Administrator'
```

The account is created as active and email-verified in PostgreSQL.

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

## Role workflows

### Applicant

```text
Register → verify email → automatic login → browse jobs → upload PDF
→ deterministic analysis → Gemini analysis → inspect explainable result
```

### Employer

```text
Register → verify email → automatic login → publish job
→ review ranked applicants → inspect evidence → securely download resume
```

### Administrator

```text
Provision through script → open /admin/login → authenticate
→ enter separate Control Center → manage users/jobs and monitor the platform
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

## API and processing behavior

- JWT access and refresh tokens secure authenticated requests
- Backend role checks protect applicant, employer, and admin APIs
- Unverified users cannot log in
- Verification codes and links expire and cannot be replayed
- One applicant can apply to each job only once
- Only PDF resumes within the configured size limit are accepted
- Private resumes are downloadable only by the employer who owns the associated job
- Scanned PDFs without extractable text return a clear retryable error
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

The backend waits for PostgreSQL, applies Alembic migrations, and starts Uvicorn workers. PostgreSQL data and uploaded resumes are stored in named Docker volumes.

## Production recommendations

- Deploy the application, admin portal, and API behind HTTPS
- Prefer separate hosts such as `app.example.com`, `admin.example.com`, and `api.example.com`
- Restrict the admin host with SSO, MFA, VPN, or an identity-aware proxy
- Use a managed secret store instead of plaintext environment files
- Move resume processing to a durable worker queue before horizontal scaling
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

## License

No license has been declared yet. Add an appropriate license before distributing or using the project commercially.
