# Deployment Summary

Target: a ~10-day demo deployment on Railway's Trial credit, with no credit card.

| Piece | Host | Cost (10 days) | Card |
|---|---|---|---|
| FastAPI backend | Railway | ~$1.70 | No |
| PostgreSQL | Railway | ~$0.85 | No |
| React frontend | Vercel | Free | No |
| Resume / avatar files | Cloudinary | Free | No |

Roughly $3 of Railway's one-time $5 Trial credit.

## Start here

1. [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md) — manual deploy, start to finish
2. [docs/GITHUB_ACTIONS_DEPLOYMENT.md](docs/GITHUB_ACTIONS_DEPLOYMENT.md) — CI/CD once the manual path works

Do them in that order. Automating a deploy that has never worked manually just
relocates the debugging into CI logs.

---

## What changed in the codebase

### Storage abstraction

Free hosts have ephemeral filesystems — uploads vanish on redeploy, restart, and
idle spin-down. With `USE_CLOUDINARY=true`, files go to Cloudinary instead of
local disk.

- `backend/app/object_storage.py` — the single storage boundary. Two backends,
  `LocalPrivateStorage` and `CloudinaryPrivateStorage`, behind one
  `put`/`read`/`open`/`delete` interface, selected by `USE_CLOUDINARY`
- `backend/app/api.py` — upload and download routes use the abstraction
- `backend/app/resume_processing.py` — uses the `open()` context manager, which
  downloads a remote file to a temp path for parsing and removes it after
- `backend/app/config.py` — Cloudinary settings, plus `normalize_database_url`
  to rewrite `postgresql://` → `postgresql+psycopg://`
- `cloudinary>=1.41,<2` added to dependencies

Cloudinary mode is exclusive: local disk is never read or written, and the local
storage directories are not even created. Keys carry a `cloudinary:` prefix, so a
key written before the switch is recognised as local and rejected rather than
read off a volume that is no longer authoritative. Enabling the flag without all
three credentials fails at startup instead of quietly falling back to disk.

Resume bytes are streamed back through the API rather than handed out as public
URLs, so the "only the owning employer may download" rule is unchanged. Cloudinary
resumes upload as authenticated raw resources — the delivery URL is useless
without a signature.

### First administrator

Registration refuses the admin role, so a fresh deployment needs a way in. Set
`ADMIN_EMAIL` and `ADMIN_PASSWORD` (optionally `ADMIN_FULL_NAME`) and
`backend/app/first_admin.py` seeds one administrator at startup. It runs only
when no administrator exists — it never resets a password or promotes an
existing account, so the variables are safe to leave set. Once signed in, that
administrator creates the others from the Control Center
(`POST /admin/users/admin`). The seeded password must meet the same strength
rules the API enforces, or the app refuses to start.

### Docker

- `backend/Dockerfile` — installs Tesseract for OCR, runs `alembic upgrade head`
  on start, binds `$PORT`, runs as non-root
- `frontend/Dockerfile` — multi-stage, `VITE_API_URL` build arg, healthcheck
- `frontend/nginx.conf` — standalone SPA config, no backend proxy

The frontend Dockerfile is kept for local `docker compose` and as a fallback host
option. The Vercel path does not use it.

### Platform config

- `backend/railway.json` — Dockerfile builder, `/health` healthcheck, restart policy
- `frontend/vercel.json` — Vite preset, SPA rewrites, security and cache headers

### CI/CD

- `.github/workflows/ci.yml` — ruff, pytest, eslint, vitest, vite build, Docker
  build check
- `.github/workflows/deploy.yml` — Railway + Vercel deploys gated on CI, plus a
  post-deploy health poll

---

## Storage configuration

Local development (default):

```env
USE_CLOUDINARY=false
# writes to ./storage/resumes and ./storage/avatars
```

Deployed:

```env
USE_CLOUDINARY=true
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

All three credentials must be present. With `USE_CLOUDINARY=true` but any of them
missing, the code falls back to local disk **silently** — which on Railway means
uploads survive until the next redeploy and then disappear.

---

## Backend environment variables

Required:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}   # Railway reference syntax
SECRET_KEY=<openssl rand -hex 32>
ENVIRONMENT=production
COOKIE_SECURE=true
USE_CLOUDINARY=true
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
FRONTEND_ORIGINS=https://<your-app>.vercel.app
FRONTEND_URL=https://<your-app>.vercel.app
```

Optional — deterministic scoring runs fine without these:

```env
GEMINI_API_KEY=...
GEMINI_ENABLED=true
```

Frontend, set on the Vercel project (build-time, not runtime):

```env
VITE_API_URL=https://<your-backend>.up.railway.app/api/v1
```

---

## Before deploying

```bash
cd backend && pip install -r requirements.txt && pytest -q
cd ../frontend && npm ci && npm run lint && npm run test && npm run build
```

Then commit and push. CI runs the same checks, so catching failures locally is
faster than round-tripping through Actions.

---

## Known constraints

**Railway Trial** grants $5 once, valid 30 days
([docs](https://docs.railway.com/pricing/free-trial)). Containers stop when it is
spent; volume data is held 30 days after.

**1 GB RAM cap on Trial.** The backend pulls in scikit-learn, pymupdf,
pytesseract, and Pillow. Baseline fits, but OCR on a large scanned PDF can spike
past it. If you hit OOM restarts, disable the OCR branch in
`backend/app/resume_parser.py` — see the troubleshooting section in the Railway
guide.

**Account verification.** Unverified Railway Trial accounts get network
restrictions. Verify with GitHub at [railway.com/verify](https://railway.com/verify)
before anything else; it weighs GitHub account age and activity, so a new account
may not clear it. If it does not, Hugging Face Spaces has no payment or
verification gate.

**Email.** With `ENVIRONMENT=production` and no SMTP configured, verification
emails go nowhere and the dev code is not returned to the UI. Either set the
`SMTP_*` variables or expect to verify accounts by editing the database directly.

---

## Teardown

Delete the Railway project when the demo is over so it stops consuming credit.

If real people uploaded real CVs, delete the Cloudinary assets too. Resumes are
personal data — a demo deployment should not sit around holding them.
