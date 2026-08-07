# GitHub Actions Deployment

Automates deploys to Railway (backend) and Vercel (frontend), gated on CI.

Set the manual path up first — [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md) —
and confirm both services run. Automating a deployment that has never worked
manually just moves the debugging into CI logs, where it is harder to read.

## Pipeline shape

```
push to main
   │
   ▼
CI  ──────────────────────────────────────────
   backend:  ruff + pytest
   frontend: eslint + vitest + vite build
   docker:   build both images (not pushed)
   │
   ├── fails ──> stop, nothing deploys
   │
   ▼ passes
Deploy ───────────────────────────────────────
   backend  -> railway up
   frontend -> vercel build + deploy --prod
   │
   ▼
Smoke ────────────────────────────────────────
   poll /health until 200 (or fail after ~3 min)
```

`workflow_run` fires whether CI passed or failed, so the deploy job explicitly
checks `github.event.workflow_run.conclusion == 'success'`. Without that guard, a
red CI run would still ship.

## Prerequisites

- Backend service live on Railway, frontend project live on Vercel
- Cloudinary configured and a resume upload verified end to end
- Repo pushed to GitHub

---

## Part 1 — Disable platform auto-deploy

Both platforms deploy on push by default. Left enabled, they deploy *before* CI
finishes, which defeats the gate entirely.

**Railway:** Service → **Settings → Source** → turn **Auto Deploy** off.

**Vercel:** Project → **Settings → Git** → set **Ignored Build Step** to
`exit 0`, which tells Vercel to skip its own Git-triggered builds. The CLI deploy
from Actions still goes through.

---

## Part 2 — Railway credentials

### RAILWAY_TOKEN

1. Open your Railway **project** (not the workspace).
2. **Settings → Tokens → Create Token**.
3. Scope it to the environment you deploy to (`production`).
4. Copy the value — it is shown once.

A *project* token is scoped to one project and environment, so the workflow does
not need to pass `--environment`. An *account* token would work too but grants far
more access than this needs.

### Service name

The workflow deploys `railway up --service "$SERVICE"`. It defaults to `backend`.
If your service has a different name, set the `RAILWAY_BACKEND_SERVICE` repository
variable to match, or rename the service in Railway.

---

## Part 3 — Vercel credentials

### VERCEL_TOKEN

[vercel.com/account/tokens](https://vercel.com/account/tokens) → **Create Token**.
Scope to your account, no expiry needed for a short-lived demo.

### VERCEL_ORG_ID and VERCEL_PROJECT_ID

Run once locally, from the repo root:

```bash
npm install -g vercel
cd frontend
vercel link
```

That writes `.vercel/project.json`:

```json
{ "orgId": "team_xxxxx", "projectId": "prj_xxxxx" }
```

Copy both values. `.vercel/` is gitignored by Vercel's CLI — leave it that way.

### VITE_API_URL

This is baked in at build time, so it must be set on the **Vercel project**, not
in the workflow. Project → **Settings → Environment Variables** →
`VITE_API_URL = https://<your-backend>.up.railway.app/api/v1`, scoped to
Production. The workflow's `vercel pull` step fetches it before building.

---

## Part 4 — Configure GitHub

**Settings → Secrets and variables → Actions.**

### Secrets

| Name | Value |
|---|---|
| `RAILWAY_TOKEN` | Project token from Part 2 |
| `VERCEL_TOKEN` | Account token from Part 3 |
| `VERCEL_ORG_ID` | `orgId` from `.vercel/project.json` |
| `VERCEL_PROJECT_ID` | `projectId` from `.vercel/project.json` |

### Variables

| Name | Value | Purpose |
|---|---|---|
| `PUBLIC_API_URL` | `https://<your-backend>.up.railway.app` | Smoke test target. Omit and the smoke step skips rather than fails. |
| `RAILWAY_BACKEND_SERVICE` | `backend` | Only needed if the service is named something else. |
| `VITE_API_URL` | `https://<your-backend>.up.railway.app/api/v1` | Used by the CI build only, so `npm run build` compiles against a realistic URL. |

### Environment

The deploy jobs declare `environment: production`. Create it under
**Settings → Environments → New environment → `production`**.

Optional but worth it for a demo with real data: add yourself as a **required
reviewer**. Every deploy then waits for a manual approval click, which is a cheap
safeguard against an accidental push going live.

---

## Part 5 — Run it

```bash
git add .
git commit -m "Deploy via GitHub Actions to Railway and Vercel"
git push origin main
```

Watch **Actions**. CI takes roughly 3–5 minutes, deploy another 3–5.

### Manual and targeted deploys

**Actions → Deploy → Run workflow** takes a `target` input:

- `both` (default)
- `backend` — Railway only
- `frontend` — Vercel only

Useful when only one side changed, or when re-running a failed half without
rebuilding everything.

---

## Troubleshooting

### `Unauthorized` from the Railway CLI

The token is wrong, expired, or scoped to a different project. Regenerate under
**Project → Settings → Tokens**. Confirm you copied a *project* token, not a
workspace invite link.

### `Service not found`

`RAILWAY_BACKEND_SERVICE` does not match the service name in Railway. Names are
case-sensitive. Check the service header in the Railway dashboard.

### Vercel deploys but the app calls the wrong API

`VITE_API_URL` is compiled into the bundle. If you changed it, a redeploy of the
existing build will not pick it up — you need a rebuild. Re-run the Deploy
workflow rather than clicking "Redeploy" in Vercel, which by default reuses the
previous build.

Confirm what actually shipped:

```bash
curl -s https://<your-app>.vercel.app/assets/index-*.js | grep -o 'https://[^"]*railway[^"]*'
```

### Smoke test times out

The backend deployed but `/health` never returned 200. Check Railway's **Deploy
Logs**. The usual causes are a failed `alembic upgrade head` (bad `DATABASE_URL`)
or an OOM kill on the 1 GB Trial cap.

The smoke job only runs when the backend job succeeded, so a failure here means
the container started and then became unhealthy — not that the deploy never
happened.

### CI passes locally but fails in Actions

Most often a lockfile drift. CI uses `npm ci`, which installs strictly from
`package-lock.json`, while local `npm install` may have quietly updated it. Commit
the lockfile.

For Python, CI installs from `requirements.txt` and `requirements-dev.txt`, not
from `pyproject.toml` extras. A dependency added to only one of those will pass
locally and fail in CI.

### Deploy job skipped entirely

`workflow_run` only triggers for workflows on the **default branch**. If you
renamed the CI workflow, the `workflows: ["CI"]` filter in `deploy.yml` no longer
matches — the name there must equal the `name:` field in `ci.yml`.

---

## Rolling back

Railway keeps prior deployments: **Deployments** tab → pick a previous one →
**Redeploy**. Vercel is the same: **Deployments** → **Promote to Production**.

Both are faster than reverting the commit and waiting for a full CI cycle, which
matters if something is broken while people are looking at it.

## References

- [Railway CLI](https://docs.railway.com/reference/cli-api)
- [Vercel CLI](https://vercel.com/docs/cli)
- [GitHub Actions: workflow_run](https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#workflow_run)
