# Demo deployment: Railway + Neon + Cloudflare Pages

Railway runs the Docker container and does **not** sleep while you have credit, which makes
it more demo-friendly than Render/Koyeb free tiers. Caveat: Railway requires a verified
payment method on most accounts (trial credit is $5 / ~30 days).

## 1. Create the Railway service (10 minutes)

1. Sign up at <https://railway.app> (GitHub). Add a payment method if prompted.
2. **New Project → Deploy from GitHub repo** → select `route-safety`.
3. Railway detects `backend/railway.toml` and builds the Docker image. If it asks for a root
   directory, set it to `backend`.
4. In the service → **Variables**, paste the contents of your local `.env.render` (same block).
   Railway injects `PORT` automatically; our image reads it.
5. In **Settings → Healthcheck**, confirm path `/health/live`.
6. Deploy. First build ~4–6 minutes.

Checks:

```bash
curl -fsS https://<your-app>.up.railway.app/health/live
curl -fsS https://<your-app>.up.railway.app/health/ready
```

## 2. Frontend (Cloudflare Pages)

Same as `docs/DEPLOY_RENDER.md` §3, with `VITE_API_BASE=https://<your-app>.up.railway.app/api/v1`.

## 3. CORS

In Railway → Variables:

```
CORS_ALLOWED_ORIGINS=https://route-safety.pages.dev
CORS_ALLOWED_ORIGIN_REGEXES=^https://([a-z0-9-]+\.)?route-safety\.pages\.dev$
DJANGO_ALLOWED_HOSTS=.up.railway.app
```

## 4. Keep-alive

Railway services do not sleep, so the keep-alive workflow is optional. If you still want it,
set GitHub variable `APP_API_URL` (or `RAILWAY_API_URL`) to your Railway URL.

## 5. Verify

Same checklist as `docs/DEPLOY_RENDER.md` §6.

## Limits

- Trial credit: $5 (~30 days on a nano service). After that, ~$5–7/month for one small service.
- No free background worker on the trial; `CELERY_TASK_ALWAYS_EAGER=1` keeps jobs inline.
- Neon free Postgres (1 GB, no expiry) is unaffected by Railway credit.
