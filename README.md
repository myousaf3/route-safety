# Spotter Route Safety

Weather-aware truck routing for safer departure decisions. Enter an origin, destination,
departure time, and load weight; the app retrieves three truck-route alternatives, samples the
forecast **at each checkpoint's ETA**, scores wind / rain / snow risk with load overrides, and
recommends the least hazardous route.

![Spotter analysis view](docs/screenshot.png)

## What it does

- **Three route alternatives** from Valhalla truck costing, with Valhalla general-traffic and
  OSRM fallbacks when fewer than three distinct truck routes are available.
- **ETA-aware weather** from Open-Meteo: each checkpoint is sampled at the time the truck is
  forecast to reach it, not at departure.
- **Distance-weighted risk**: 10-mile samples drive `no_travel`, `severe`, `high`, and average
  risk metrics. The 25- and 50-mile checkpoint views are display-only.
- **Load-aware overrides** for high wind: `>=55 mph` is No Travel for any load, `45–54 mph` is
  No Travel above 30,000 lb, and `35–44 mph` is Severe above 40,000 lb.
- **Explicit recommendation**: fewest No Travel miles, then Severe miles, then High miles, then
  average risk, then travel time. If every route has No Travel mileage, the least hazardous
  route is shown only as context and marked **not recommended for travel**.
- **Map + 0–48 hour corridor heatmap**: switch routes, inspect every checkpoint, and scrub the
  forecast timeline while the route stays fixed.
- **Persisted analyses**: results stay reproducible after live forecasts change, with saved
  history, deep links (`/#/analysis/<uuid>`), and per-user scoping when authenticated.
- **Honest unknowns**: missing forecasts are labelled Unknown, never treated as safe, and
  excluded from average risk rather than counted as zero.
- **Asynchronous jobs**: long analyses run in Celery workers; the API returns `202 Accepted`
  and the UI polls until the job reaches a terminal state.
- **Token auth**: JWT registration/login/refresh with a dedicated auth page (`#/login`,
  `#/register`), an account control in the header, automatic access-token refresh, and
  owner-scoped history.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, TanStack Query, MapLibre GL JS |
| Backend | Django 5.2, Django REST Framework, drf-spectacular, SimpleJWT |
| Async | Celery 5.4, Redis 7 |
| Data | PostgreSQL 16 (production) / SQLite (local), JSON fields, UUID analyses |
| Routing | Valhalla (truck + auto), OSRM fallback |
| Geocoding | Nominatim / OpenStreetMap |
| Weather | Open-Meteo hourly forecasts |
| Ops | Docker Compose, nginx, Gunicorn, Prometheus, Grafana, GitHub Actions |

No API keys are required.

## Quick start (local)

### 1. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo --count 5   # optional demo data
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Celery runs in eager mode by default (`CELERY_TASK_ALWAYS_EAGER=1`), so no worker is needed
locally.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api`, `/health`, and `/metrics` to Django on port
8000.

## Docker Compose

### Core stack

```bash
cp .env.example .env    # set a real DJANGO_SECRET_KEY for a public deployment
docker compose up --build
```

Open <http://localhost:8080>. The stack runs migrations on startup, serves the built React app
from nginx, proxies the API to Gunicorn, runs a Celery worker, and persists PostgreSQL/Redis
data in named volumes.

### With monitoring

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up --build
```

- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3000> (default `admin` / `admin`)

### For a public host

1. Set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DATABASE_URL`.
2. Terminate TLS at the edge or in nginx (see `frontend/deploy/nginx.conf`) and set
   `DJANGO_SECURE_SSL_REDIRECT=1`.
3. Set `CELERY_TASK_ALWAYS_EAGER=0` and run at least one worker.
4. If the API is served from a different origin, build the frontend with
   `VITE_API_BASE=https://api.example.com/api/v1` and add the web origin to
   `CORS_ALLOWED_ORIGINS`.
5. Point the platform health check at `/health/ready`.

## API

Base path: `/api/v1`.

### Auth

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register/` | Create an account; returns JWT access/refresh tokens |
| `POST` | `/auth/token/` | Obtain JWT access/refresh tokens |
| `POST` | `/auth/token/refresh/` | Refresh an access token |
| `GET` | `/auth/me/` | Current user (if authenticated) |

### Analyses

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/analyses/` | Queue an analysis (returns `202 Accepted` with the current payload) |
| `GET` | `/analyses/` | Cursor-paginated history (scoped to the authenticated user when signed in) |
| `GET` | `/analyses/{uuid}/` | Saved analysis detail (poll until terminal) |
| `DELETE` | `/analyses/{uuid}/` | Delete a saved analysis |

Anonymous callers can create and read anonymous analyses; signed-in users additionally see their
own analyses. Private analyses return `404` to other users so history stays account-scoped.

### Frontend routes

| Route | Screen |
| --- | --- |
| `/` | Route form, saved history, and analysis results |
| `#/login` | Standalone sign-in page |
| `#/register` | Standalone account-creation page |
| `#/analysis/{uuid}` | Deep link to a saved analysis |

The auth page stores JWTs in `localStorage`, attaches the access token as a bearer header,
refreshes it automatically, and returns the user to the app when complete. The header account
control shows the current user and supports sign-out. Anonymous analyses remain available.

### Other

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/places/?q=` | Autocomplete via Nominatim (max 5) |
| `GET` | `/policy/` | Machine-readable thresholds, load rules, ranking key |
| `GET` | `/openapi/` | OpenAPI 3 schema |

Outside the versioned API: `GET /health/live`, `GET /health/ready`, `GET /metrics`, and Swagger UI
at `/api/docs/`.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyses/ \
  -H 'Content-Type: application/json' \
  -d '{
    "origin": "Chicago, IL",
    "destination": "Denver, CO",
    "departure": "2026-11-24T15:00:00Z",
    "load_weight_lb": 42000,
    "spacing_miles": 25
  }'
```

Errors use RFC 9457-style problem details with a stable `code`, human `detail`, field `errors`,
and an `X-Correlation-ID` for logs.

## Risk policy (`2026-11-a`)

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind (mph) | `<25` | `25–34` | `35–44` | `45–54` | `>=55` |
| Rain (in/hr) | `<0.10` | `0.10–0.25` | `0.25–0.50` | `0.50–1.00` | `>1.00` |
| Snow (in/hr) | `<0.5` | `0.5–1.0` | `1.0–2.0` | `2.0–3.0` | `>3.0` |

Base risk is the worst of wind, rain, and snow. Load overrides are applied afterwards:

- Wind `>=55 mph` → No Travel for every load.
- Wind `45–54 mph` and load `>30,000 lb` → No Travel.
- Wind `35–44 mph` and load `>40,000 lb` → Severe.

Each checkpoint's risk is applied to the road distance around it (midpoint attribution), so the
metrics describe mileage, not a count of samples.

## How an analysis runs

1. Validate the request and persist a queued analysis row.
2. Enqueue a Celery job (eager in dev/test).
3. Geocode both endpoints (Nominatim, cached and rate-limited).
4. Request truck alternatives from Valhalla; fill with general-traffic and OSRM alternatives until
   three distinct routes are available.
5. Simplify and store geometry; sample checkpoints at 10, 25, and 50 miles.
6. Compute each checkpoint ETA from route distance and duration, then batch-fetch Open-Meteo hourly
   forecasts for the unique coordinates (threaded).
7. Sample the forecast valid at each ETA, score base risk, apply load overrides, and attribute
   distance-weighted risk miles.
8. Build a 0–48 hour heatmap at each 10-mile point, rank routes, persist everything, and return the
   assembled payload.

Provider HTTP calls use a shared session with retries (3 attempts, exponential backoff, retry on
429/5xx) and respect `Retry-After`.

## Observability and operations

- **Metrics**: `/metrics` exposes Prometheus-format counters and gauges including
  `http_requests_total`, `http_responses_total`, `http_requests_in_flight`,
  `http_requests_last_60s`, `http_errors_last_60s`, `http_error_rate_last_60s`, latency quantiles,
  and `analyses_total{status}`.
- **Logging**: structured JSON access logs with correlation IDs (`X-Correlation-ID`) and provider
  latency.
- **Health**: `/health/live` and `/health/ready` (DB + cache).
- **Tracing/errors**: optional Sentry via `SENTRY_DSN`.
- **Backups**: `scripts/backup.sh` dumps PostgreSQL (gzip, 14-backup retention).
- **Retention**: `python manage.py cleanup_analyses --days 30` (add `--include-demo` to remove
  seeded data).
- **Load testing**: `python scripts/load_test.py --users 20 --requests 50`.

## Tests and quality gates

```bash
# Backend (68 tests)
cd backend
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .

# Frontend
cd frontend
npm run typecheck
npm run lint
npm run build
```

CI (`.github/workflows/ci.yml`) enforces backend lint/format/tests, frontend typecheck/lint/build,
and Docker image builds.

## Project layout

```text
backend/
  config/                 Django settings, URLs, WSGI, Celery app
  core/
    auth.py               JWT registration/login/me
    management/commands/  seed_demo, cleanup_analyses
    services/             geocoding, routing, weather, risk, geo, analysis pipeline
    tasks.py              Celery analysis jobs
    tests/                risk, geo, pipeline, API, auth, seed tests
  requirements*.txt
frontend/
  src/
    components/           AuthPage, account control, form, history, route cards, map, inspector
    lib/                  API client, session/auth, formatting and risk helpers
  deploy/nginx.conf       SPA + API reverse proxy, rate limits, TLS hooks
docs/
  WALKTHROUGH.md          five-to-ten minute demo script
  screenshot.png          analysis view
monitoring/
  prometheus.yml          Prometheus scrape config
scripts/
  backup.sh               PostgreSQL backup
  load_test.py            Concurrent load smoke test
docker-compose.yml        Core production stack
docker-compose.monitoring.yml  Prometheus + Grafana
```

## Deliberate MVP trade-offs

- **Synchronous API contract is now async**: clients must poll `GET /analyses/{id}/` until the
  status is `completed`, `partial`, or `failed`.
- **No auth required for demo**: anonymous analyses still work; signing in scopes history to the
  account. Account history is private: anonymous callers only see anonymous analyses.
- **Public free providers**: no API keys, but availability and rate limits are outside our control.
  Adapters isolate providers so a commercial routing or weather API can be swapped in.
- **Forecast advisory, not a road report**: the score does not model closures, chain controls,
  visibility, ice, driver skill, or vehicle configuration beyond load weight.

See [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) for the demo script.
