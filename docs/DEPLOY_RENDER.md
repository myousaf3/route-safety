# Free-tier demo deployment: Render + Neon + Cloudflare Pages

This is the no-credit-card path for a client demo:

```
Cloudflare Pages (static React build)
        |
        |  HTTPS + CORS
        v
Render web service (Docker: Django + Gunicorn, Celery eager)
        |
        v
Neon Postgres (free, no 30-day expiry)
```

The full Docker Compose stack in `docker-compose.yml` remains the production-style deployment.
This guide trades the Celery worker and always-on service for zero cost.

## What you need

- GitHub repository: <https://github.com/myousaf3/route-safety>
- Free accounts: [Render](https://render.com), [Neon](https://neon.tech),
  [Cloudflare](https://dash.cloudflare.com)
- No credit card for any of the three.

## 1. Create the Neon database (5 minutes)

1. Sign in to Neon and create a project named `route-safety`.
2. Pick the region closest to your Render region. `render.yaml` uses `oregon`, so
   `AWS us-west-2` keeps latency low.
3. On the project dashboard, open **Connect**.
4. Turn on **Pooled connection** (the host contains `-pooler`). Copy the connection string
   and make sure it ends with `?sslmode=require`:

   ```
   postgresql://USER:PASSWORD@ep-xxxx-pooler.us-west-2.aws.neon.tech/neondb?sslmode=require
   ```

Neon's free plan includes 1 GB storage and does not expire. The compute suspends after a few
minutes idle and resumes in well under a second on the next query.

## 2. Deploy the API to Render (10 minutes)

1. In Render, choose **New → Blueprint** and connect the `route-safety` repository.
2. Render reads `render.yaml` and shows one web service, `route-safety-api`.
3. When prompted for `DATABASE_URL`, paste the Neon pooled connection string.
4. Apply the blueprint. The first Docker build takes roughly 4–6 minutes.
5. When the deploy is live, copy the service URL, e.g.
   `https://route-safety-api.onrender.com`.

The container runs `python manage.py migrate --noinput` before Gunicorn starts, so the schema
is created automatically. Django admin static files are served by WhiteNoise, so no extra
static host is required.

Useful checks:

```bash
curl -fsS https://route-safety-api.onrender.com/health/live
curl -fsS https://route-safety-api.onrender.com/health/ready
open https://route-safety-api.onrender.com/api/docs/
```

### Optional: create an admin user

Render Shell is not available on every free workspace. The most reliable way is to run the
command locally against Neon:

```bash
cd backend
DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require" \
  .venv/bin/python manage.py createsuperuser
```

The demo itself does not need the admin: drivers can register on the app's `/#/login` page.

### Manual service alternative

If you prefer not to use the blueprint, create a **Web Service** with:

| Setting | Value |
| --- | --- |
| Language / Runtime | Docker |
| Root directory | `backend` |
| Dockerfile path | `./Dockerfile` |
| Health check path | `/health/live` |
| Instance type | Free |

Then add the environment variables listed in `render.yaml`, including `DATABASE_URL`.

## 3. Deploy the frontend to Cloudflare Pages (10 minutes)

1. In the Cloudflare dashboard, open **Workers & Pages → Create → Pages → Connect to Git**.
2. Select the `route-safety` repository.
3. Use these build settings:

   | Setting | Value |
   | --- | --- |
   | Project name | `route-safety` (this sets the `route-safety.pages.dev` URL) |
   | Production branch | `main` |
   | Framework preset | Vite |
   | Build command | `npm ci && npm run build` |
   | Build output directory | `dist` |
   | Root directory | `frontend` |

4. Add environment variables for the production build:

   | Variable | Value |
   | --- | --- |
   | `NODE_VERSION` | `22` |
   | `VITE_API_BASE` | `https://route-safety-api.onrender.com/api/v1` |

   `VITE_API_BASE` is compiled into the bundle, so it must be present at build time. Changing
   it requires a new Cloudflare deployment.

5. Save and deploy. The first build takes about 1–2 minutes.

`frontend/public/_redirects` gives the SPA its `index.html` fallback for routes such as
`/#/login`; `frontend/public/_headers` adds long-lived asset caching and security headers.

## 4. Allow the frontend origin in Django (2 minutes)

In Render → `route-safety-api` → **Environment**, confirm:

```
CORS_ALLOWED_ORIGINS=https://route-safety.pages.dev
CORS_ALLOWED_ORIGIN_REGEXES=^https://([a-z0-9-]+\.)?route-safety\.pages\.dev$
DJANGO_ALLOWED_HOSTS=.onrender.com
```

The regex also allows Cloudflare preview deployments such as
`https://1a2b3c4d.route-safety.pages.dev`. If you attach a custom domain, add its exact origin
to `CORS_ALLOWED_ORIGINS`.

Saving an environment variable triggers a redeploy. Wait for the API to come back, then hard
refresh the Pages site.

## 5. Keep the free API awake (2 minutes)

A free Render web service spins down after 15 minutes without traffic and takes about a minute
to wake. The `Keep alive` GitHub Actions workflow pings it every 10 minutes.

1. In GitHub, open **Settings → Secrets and variables → Actions → Variables**.
2. Add `RENDER_API_URL` with the API base URL (no trailing slash), e.g.
   `https://route-safety-api.onrender.com`.
3. Run **Actions → Keep alive → Run workflow** once to verify it succeeds.

Notes:

- GitHub can delay scheduled workflows during busy periods. The 10-minute cadence leaves room
  inside Render's 15-minute idle window.
- GitHub disables scheduled workflows after 60 days without repository activity. Re-enable the
  workflow from the Actions tab if that happens.
- 24/7 keep-alive uses roughly 730 of the 750 free instance hours per month. If the workspace
  runs other free services, let this one sleep between demos instead.

## 6. Verify the demo path

Run through this list before the client call:

- [ ] `https://route-safety-api.onrender.com/health/live` returns `{"status": "ok"}`.
- [ ] `https://route-safety-api.onrender.com/health/ready` reports `database` and `cache` as `ok`.
- [ ] Swagger loads at `/api/docs/`.
- [ ] The Pages URL loads and the map renders.
- [ ] Create an account on `/#/login`, then reload: the session survives and history is private.
- [ ] Run a Chicago → Denver analysis, open it from history, and confirm the map and route cards.
- [ ] Open the Pages URL in a private window to confirm anonymous analysis still works.
- [ ] From the browser devtools console, confirm no CORS errors.

A cold analysis is slower on the free instance (0.1 CPU); expect roughly 15–40 seconds rather
than the 7–12 seconds quoted for Docker Compose. Run one analysis shortly before the demo so
provider caches are warm.

## 7. Operations

**Deploys.** Both Render and Cloudflare Pages redeploy on pushes to `main`.
`render.yaml` and `.github/workflows/keepalive.yml` are committed, so the setup is reproducible.

**Logs and metrics.** Render streams JSON logs. `/metrics` exposes Prometheus text metrics, and
`/health/ready` checks Postgres and the cache. Sentry is optional: set `SENTRY_DSN` in Render.

**Data.** Postgres lives in Neon, so redeploys and Render spin-downs do not lose analyses or
accounts. Nothing is stored on Render's ephemeral disk.

**Throttling.** Defaults are generous for a demo: 120 requests/min anonymous, 600/min signed in,
12 analyses/min. Override with `API_THROTTLE_*` variables if needed.

## Free-tier limits and caveats

| Limit | Impact |
| --- | --- |
| Render free: 0.1 CPU, 512 MB RAM | Analyses are slower; one Gunicorn worker is configured to stay within memory. |
| Render free: sleeps after 15 min | Keep-alive workflow prevents this, at the cost of instance hours. |
| Render free: 750 instance hours/month | One always-on service fits; additional free services can exhaust the quota. |
| Render free: no background worker | `CELERY_TASK_ALWAYS_EAGER=1` runs the job inside the request. It still returns `202` after the work completes, and the UI polls as usual. |
| Render free: ephemeral disk | Irrelevant here because the database is Neon. |
| Neon free: 1 GB, autosuspend | Plenty for a demo; the first query after idle may add a few hundred ms. |
| Cloudflare Pages free | Unlimited requests and bandwidth for static assets; 500 builds/month. |
| No custom domain required | `*.onrender.com` and `*.pages.dev` are HTTPS by default. |

For a higher-stakes demo, upgrade only the Render service to the $7/month instance. That removes
sleep, gives 0.5 CPU, and lets you switch Celery back to a real worker by adding a background
worker service and Redis. The rest of this setup stays the same.

## Troubleshooting

**`DisallowedHost` in Render logs.** Set `DJANGO_ALLOWED_HOSTS=.onrender.com` and redeploy.
`settings.py` also appends `RENDER_EXTERNAL_HOSTNAME` automatically.

**CORS error in the browser.** The Pages origin must match `CORS_ALLOWED_ORIGINS` exactly,
including `https://` and no trailing slash. Preview URLs need the regex.

**Frontend calls `https://route-safety.pages.dev/api/v1`.** `VITE_API_BASE` was missing during
the Cloudflare build. Add it under **Settings → Environment variables**, then retry the
deployment (an environment change alone does not rebuild a static site).

**`/health/ready` returns 503.** Check the Neon connection string, that `?sslmode=require` is
present, and that the Neon project is not over quota. `/health/live` should still return 200.

**Admin has no styling.** Confirm the image was rebuilt after adding WhiteNoise and that
`collectstatic` ran during the Docker build.

**First request takes about a minute.** The service was asleep. Check the keep-alive workflow
run history and the `RENDER_API_URL` variable.
