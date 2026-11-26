# Free-tier demo deployment: Koyeb + Neon + Cloudflare Pages (no credit card)

Use this if Render asks for a payment method. Koyeb's free tier does not require a card.

```
Cloudflare Pages (static React build)
        |
        |  HTTPS + CORS
        v
Koyeb service (Docker: Django + Gunicorn, Celery eager)
        |
        v
Neon Postgres (free, no 30-day expiry)
```

## 1. Create the Koyeb service (10 minutes)

1. Sign up at <https://www.koyeb.com> with GitHub (no card).
2. **Create App** → name `route-safety`.
3. **Add service** → **Docker** → connect the `route-safety` GitHub repository.
4. Build settings:

   | Setting | Value |
   | --- | --- |
   | Builder | Dockerfile |
   | Work directory | `backend` |
   | Dockerfile | `backend/Dockerfile` |
   | Port | `8000` (Koyeb sets `PORT`; our image reads it) |
   | Health check path | `/health/live` |
   | Instance type | Nano (Free) |
   | Region | Washington, D.C. (closest to the Neon us-east-1 DB) |

5. Under **Environment variables**, paste the contents of your local `.env.render`
   (or add them one by one). Same block as Render — `DATABASE_URL` is the pooled Neon string.
6. Under **Scaling**, set **Min instances** to `1` if the free tier allows it (keeps the
   service warm); otherwise leave `0` and rely on the keep-alive workflow.
7. Deploy. First build ~4–6 minutes.

Checks:

```bash
curl -fsS https://<your-app>.koyeb.app/health/live
curl -fsS https://<your-app>.koyeb.app/health/ready
```

## 2. Deploy the frontend to Cloudflare Pages

Same as `docs/DEPLOY_RENDER.md` §3:

- Root `frontend`, build `npm ci && npm run build`, output `dist`.
- Env: `NODE_VERSION=22`, `VITE_API_BASE=https://<your-app>.koyeb.app/api/v1`.

## 3. Allow the frontend origin in Django

In Koyeb → service → **Environment**, set:

```
CORS_ALLOWED_ORIGINS=https://route-safety.pages.dev
CORS_ALLOWED_ORIGIN_REGEXES=^https://([a-z0-9-]+\.)?route-safety\.pages\.dev$
DJANGO_ALLOWED_HOSTS=.koyeb.app
```

(Add your custom domain too if you attach one.)

## 4. Keep the service awake

Koyeb scales free services to zero after a few minutes of inactivity. The existing
**Keep alive** GitHub Action pings `APP_API_URL` every 5 minutes.

1. GitHub → **Settings → Secrets and variables → Actions → Variables**.
2. Add `APP_API_URL` = `https://<your-app>.koyeb.app` (or `KOYEB_API_URL` / `RENDER_API_URL` —
   the workflow checks all three).
3. Run **Actions → Keep alive → Run workflow** once to verify.

## 5. Verify

Same checklist as `docs/DEPLOY_RENDER.md` §6, substituting the Koyeb URL.

## Free-tier limits

| Limit | Impact |
| --- | --- |
| Koyeb free: 1 service, Nano instance (512 MB, 0.1 vCPU) | Analyses take 15–40 s; one Gunicorn worker is configured. |
| Koyeb free: scales to zero after inactivity | Keep-alive workflow prevents this. |
| No background worker on free | `CELERY_TASK_ALWAYS_EAGER=1` runs the job inside the request. |
| Neon free: 1 GB, autosuspend | Plenty for a demo. |
| Cloudflare Pages free | Unlimited requests; 500 builds/month. |

For a higher-stakes demo, upgrade only the Koyeb service to a paid instance (removes
scale-to-zero and adds CPU). The rest of the setup stays the same.
