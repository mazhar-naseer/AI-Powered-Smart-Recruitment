# Railway Deployment Guide

Deploys SmartHire with the backend and PostgreSQL on Railway, the frontend on
Vercel, and file storage on Cloudinary. Targets a short-lived demo deployment
(roughly 10 days) on Railway's Trial credit.

## Why this split

| Piece | Host | Cost | Card required |
|---|---|---|---|
| FastAPI backend | Railway | ~$1.70 / 10 days | No (Trial) |
| PostgreSQL | Railway | ~$0.85 / 10 days | No (Trial) |
| React frontend | Vercel | Free | No |
| Resume / avatar files | Cloudinary | Free (25 GB) | No |

The frontend goes on Vercel rather than Railway because static hosting is free
there, which leaves the Trial credit for the two services that actually need
compute.

## Cost and time limits

Railway's Trial grants a **one-time $5 credit valid for 30 days**
([Railway docs](https://docs.railway.com/pricing/free-trial)). When the credit is
spent or the window closes, containers stop, and volume data is retained for 30
days before deletion.

For a 10-day demo, expect roughly $3 of the $5 to be consumed. Watch the balance
in **Workspace → Billing**; there is no automatic cutoff warning in the app
itself.

Two limits worth knowing before you start:

- **Trial instances cap at 1 GB RAM.** The backend imports scikit-learn, pymupdf,
  pytesseract, and Pillow. Baseline sits well under the cap, but OCR on a large
  scanned PDF can spike. If you hit an OOM restart, see
  [Troubleshooting](#backend-restarts-with-oom).
- **Account verification.** Unverified Trial accounts get network restrictions.
  Verify at [railway.com/verify](https://railway.com/verify) with your GitHub
  account *before* building anything else — this is the single most likely thing
  to block you, and it depends on your GitHub account's age and activity.

---

## Step 1 — Cloudinary

1. Sign up at [cloudinary.com](https://cloudinary.com/users/register/free).
2. From the dashboard, copy **Cloud Name**, **API Key**, and **API Secret**.

Keep the API Secret out of git. It goes into Railway's variable editor only.

## Step 2 — Verify your Railway account

1. Sign up at [railway.com](https://railway.com) with GitHub.
2. Go to [railway.com/verify](https://railway.com/verify) and connect GitHub.
3. Confirm the workspace shows **Trial** and not **Limited Trial** in
   **Workspace → Billing**.

If it still says Limited Trial, Railway could not verify you automatically. Your
options are to add a card (you are not charged on Trial) or switch to a host with
no verification gate — Hugging Face Spaces is the usual fallback.

## Step 3 — Create the project and database

1. **New Project → Deploy PostgreSQL**.
2. Once provisioned, note the service name. It defaults to `Postgres`.

Railway exposes the connection string as a service variable. You will reference
it from the backend rather than copying the value.

## Step 4 — Deploy the backend

1. In the same project: **New → GitHub Repo**, select this repository.
2. Open the new service → **Settings**:
   - **Root Directory**: `backend`
   - **Builder**: Dockerfile (auto-detected from `backend/railway.json`)
   - **Auto Deploy**: **off** if you plan to use the GitHub Actions workflow;
     leave on for dashboard-driven deploys. Do not leave it on while also running
     the workflow, or every push deploys twice and skips the CI gate.
3. Rename the service to `backend` so it matches the workflow default.

### Backend variables

Set these under **Variables**. `DATABASE_URL` uses Railway's reference syntax so
it stays correct if the database is recreated:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
ENVIRONMENT=production
SECRET_KEY=<paste output of: openssl rand -hex 32>
COOKIE_SECURE=true

USE_CLOUDINARY=true
CLOUDINARY_CLOUD_NAME=<from step 1>
CLOUDINARY_API_KEY=<from step 1>
CLOUDINARY_API_SECRET=<from step 1>

# Fill these in after step 5, once you know the Vercel URL.
FRONTEND_ORIGINS=https://<your-app>.vercel.app
FRONTEND_URL=https://<your-app>.vercel.app
```

Optional, for the Gemini half of the hybrid scorer:

```env
GEMINI_API_KEY=<your key>
GEMINI_ENABLED=true
```

Leave `GEMINI_API_KEY` empty and deterministic scoring still runs — the app falls
back cleanly.

If the `Postgres` service is named something else, adjust the reference to match:
`${{<ServiceName>.DATABASE_URL}}`.

> Railway hands out `postgresql://`, but SQLAlchemy needs the psycopg driver.
> `normalize_database_url` in `backend/app/config.py` rewrites the scheme to
> `postgresql+psycopg://` automatically, so paste the reference as-is.

### Generate a public URL

**Settings → Networking → Generate Domain**. You get
`https://<service>.up.railway.app`. Record it; the frontend needs it.

Migrations run automatically — the Dockerfile's `CMD` executes
`alembic upgrade head` before starting Uvicorn.

### Confirm it came up

```bash
curl https://<your-backend>.up.railway.app/health
```

Expect `{"status":"healthy"}`. If it fails, open the service's **Deploy Logs**.

## Step 5 — Deploy the frontend

1. Sign up at [vercel.com](https://vercel.com) with GitHub.
2. **Add New → Project**, import this repository.
3. Set **Root Directory** to `frontend`. Vercel reads `frontend/vercel.json` for
   the framework preset and SPA rewrites.
4. Under **Environment Variables**, add:

   ```env
   VITE_API_URL=https://<your-backend>.up.railway.app/api/v1
   ```

   This is baked in at build time, not read at runtime. Changing it later
   requires a rebuild, not just a redeploy.
5. Deploy. You get `https://<your-app>.vercel.app`.

## Step 6 — Close the CORS loop

Go back to the Railway backend service and set `FRONTEND_ORIGINS` and
`FRONTEND_URL` to the real Vercel URL from step 5. Railway redeploys on variable
change.

The origin must match exactly — scheme, host, no trailing slash. A mismatch here
produces a CORS error in the browser console and nothing useful in the backend
logs.

## Step 7 — Create an administrator

Public registration only creates applicants and employers by design. Provision
the admin through Railway's shell:

```bash
npm install -g @railway/cli
railway login
railway link          # select your project
railway run --service backend python scripts/create_admin.py \
  --email admin@example.com \
  --password 'ReplaceWithAStrongPassword!' \
  --name 'Platform Administrator'
```

`railway run` executes against the deployed service's environment, so it picks up
the same `DATABASE_URL`.

## Step 8 — Verify end to end

1. Open the Vercel URL.
2. Register an applicant. Without SMTP configured, the verification code is
   returned to the UI in non-production mode; with `ENVIRONMENT=production` you
   need real SMTP settings, so configure `SMTP_*` variables if you want the full
   registration flow.
3. Register an employer, publish a job.
4. As the applicant, upload a PDF resume and confirm the match report renders.
5. As the employer, download the resume — this exercises the Cloudinary read
   path.

If the upload succeeds but the download 404s, the Cloudinary credentials are set
for writes but the signed-read path is failing. Check backend logs for
`StorageError`.

---

## Automated deploys

Once the manual path works, wire up CI/CD with
[GITHUB_ACTIONS_DEPLOYMENT.md](GITHUB_ACTIONS_DEPLOYMENT.md). Turn **Auto Deploy
off** in Railway first, or the CI gate does nothing.

---

## Troubleshooting

### Workspace stuck on "Limited Trial"

Verification did not pass. Connect GitHub at
[railway.com/verify](https://railway.com/verify). Account age and activity factor
in, so a brand-new GitHub account may not clear it.

### Backend restarts with OOM

Trial caps at 1 GB. The OCR path is the usual cause — it rasterizes each PDF page
at 2× scale before running Tesseract, which is memory-hungry on long documents.

To disable OCR, edit `_pdf_text` in `backend/app/resume_parser.py` and return the
pypdf result directly instead of falling through to the `fitz`/`pytesseract`
branch. Text-based PDFs are unaffected; scanned PDFs will return the existing
"insufficient extractable text" error, which the UI already handles as retryable.

### Build fails on `pip install`

The image builds scikit-learn and pymupdf. Both ship wheels for
`linux/amd64`/Python 3.12, so this should not compile from source. If it does,
confirm the base image is still `python:3.12-slim` and not a variant without
wheel support.

### `psycopg2` module not found

`DATABASE_URL` reached SQLAlchemy without the `+psycopg` driver suffix. Confirm
`normalize_database_url` is present in `backend/app/config.py` and that you did
not override `DATABASE_URL` with a hand-edited value that bypasses it.

### CORS errors in the browser

`FRONTEND_ORIGINS` does not match the Vercel origin exactly. Compare character by
character. Vercel preview deployments get distinct URLs, so a preview build will
fail CORS against a production-only origin list.

### Resume upload returns 500

All three Cloudinary variables must be set *and* `USE_CLOUDINARY=true`. With the
flag on but credentials missing, `_cloudinary_enabled` returns false and the code
silently falls back to local disk — which on Railway is wiped on redeploy.

### Trial credit exhausted

Containers stop immediately; volume data is held 30 days. Check
**Workspace → Billing**. Upgrading to Hobby ($5/month, includes $5 of usage)
resumes the services.

---

## Tearing it down

After the demo, delete the Railway project to stop consuming credit, and remove
the Cloudinary assets if the resumes contain real personal data. Uploaded resumes
are personal information — do not leave a demo deployment holding other people's
CVs indefinitely.

## References

- [Railway free trial](https://docs.railway.com/pricing/free-trial)
- [Railway pricing plans](https://docs.railway.com/pricing/plans)
- [Vercel CLI](https://vercel.com/docs/cli)
- [Cloudinary free plan](https://cloudinary.com/pricing)
