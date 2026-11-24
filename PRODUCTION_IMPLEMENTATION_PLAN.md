# Weather-Aware Truck Routing - Production Implementation Plan

## 1. Delivery goal

Build a React + Django application that accepts origin, destination, departure time,
and load weight; obtains exactly three viable route alternatives; samples forecast weather
at distance-based, ETA-aware checkpoints; scores safety; and recommends the safest route
using the required ordered tie-breakers.

The definition of done is a hosted app, reproducible repository, and a 5-10 minute
walkthrough. Correct route, weather, risk, and recommendation behavior plus a smooth map
and heatmap are the highest-priority work.

## 2. Scope and assumptions

### Required MVP

- React UI with a form for origin, destination, timezone-aware departure time, and load weight.
- Geocode addresses, request three alternative truck-capable routes, and display routes on a map.
- Generate 10, 25, and 50 mile checkpoint sets for every route.
- Calculate an ETA for every checkpoint, fetch the forecast at that ETA, classify risk, and
  apply the load overrides.
- Show route summaries, checkpoints, per-checkpoint weather/risk/ETA, and a 0-48 hour
  weather heatmap time slider.
- Rank routes by: fewest severe miles, fewest high miles, lowest average risk, shortest ETA.
- Clear loading, empty, invalid-input, partial-data, and provider-error states.

### Production hardening included

- JWT bearer-token authentication and ownership isolation for saved route analyses.
- API schema documentation (OpenAPI/Swagger), structured logs, metrics, health checks,
  retry/backoff, caching, rate limiting, and containerized deployment.
- Background work for provider fan-out and long-running analyses, with polling or SSE status
  updates. The first screen should remain usable while an analysis is running.

### Explicit non-goals for the assessment

- Building a routing engine, historical weather analytics, fleet management, and exact road-level
  weather interpolation. Use documented third-party providers and label provider limitations.

## 3. Recommended architecture

```text
React + TypeScript (Vite)                         Django REST Framework
MapLibre GL + react-query                   API / OpenAPI / JWT / throttling
        |                                               |
        +-- request/status/results ---------------------+
                                                        |
                                  PostgreSQL <--- Django domain services
                                                        |
Redis <--- Celery workers/beat <--- routing, geocoding, weather adapters
                      |              (bounded parallel I/O, retries, caching)
                      +-- status/progress events (SSE optional)
```

Use provider adapters so routing and weather vendors can be replaced without changing the
domain logic. For the assessment, Mapbox (Directions/Geocoding) plus Open-Meteo is a
pragmatic default; the routing adapter must verify that alternative routes are actually returned.
If truck-restriction-aware routing is available within budget, prefer it and document the
provider/configuration used.

## 4. Data model

- `User` / `RefreshToken` - authenticated users and revocable sessions.
- `RouteAnalysis` - immutable request: inputs, timezone, status, provider versions,
  timestamps, selected/recommended route, and error summary.
- `RouteOption` - geometry (encoded polyline/GeoJSON), distance, duration, rank, and aggregates.
- `Checkpoint` - route sequence, cumulative mile, coordinates, ETA, spacing strategy,
  weather snapshot, base risk, final risk, and reason codes.
- `WeatherObservation` - normalized forecast values, provider timestamp, retrieval time,
  raw provider attribution/version, and cache key.
- `AnalysisEvent` - progress/audit events without secrets or provider payloads.

Persist normalized results so a completed analysis can be viewed without refetching changing
forecasts. Store geometry in PostGIS when available; otherwise retain compact encoded polylines
and add PostGIS before scaling geographic queries.

## 5. Core analysis pipeline

1. Validate and normalize the request. Reject identical endpoints, invalid dates, dates outside
   the weather provider horizon, non-positive/out-of-range weight, and invalid local times.
2. Geocode endpoints and resolve their IANA time zones. Persist input display values and
   normalized UTC departure time.
3. Obtain up to three distinct route alternatives. Reject malformed geometry and de-duplicate
   near-identical alternatives; return an explicit provider limitation if fewer than three exist.
4. Decode each route geometry and create checkpoint positions at cumulative distances. For the
   initial analysis choose the requested spacing; the UI can switch among 10/25/50-mile sampled
   result sets without recomputing a route. Always include origin and destination.
5. Compute checkpoint ETA from the route's cumulative duration ratio (or provider segment ETA
   when supplied), crossing timezone boundaries in UTC and rendering in the checkpoint locale.
6. Group weather requests by rounded coordinate/time bucket; fetch them with bounded concurrency
   (for example, 8-12 requests/worker), cache the normalized result, and map each response back
   to a checkpoint. Do not create uncontrolled threads in Django request handlers.
7. Normalize units: wind mph, rain inches/hour, snow inches/hour. Missing precipitation must be
   represented as unknown rather than silently treated as zero.
8. Classify every weather dimension, take the worst base risk, then apply the load overrides:
   wind >=55 mph is No Travel; 45-54 mph with >30,000 lb is No Travel; 35-44 mph with >40,000 lb
   is Severe. Save human-readable reason codes.
9. Estimate risk miles by attributing each checkpoint's risk to the following route segment
   (or using midpoint samples). This avoids counting samples rather than road distance.
10. Rank using the specified lexicographic key:
    `(no_travel_miles, severe_miles, high_miles, average_risk_score, duration_seconds)`.
    Treat any No Travel distance as disqualifying; if all three are disqualified, still show the
    least hazardous route as **not recommended for travel**, never as safe.
11. Persist results atomically, expose them through the API, and publish status progression:
    `queued -> routing -> weather -> scoring -> completed | failed | partial`.

## 6. Risk engine design

- Implement thresholds as typed, table-driven configuration, not nested UI conditionals.
- Define an ordered enum: `LOW=1`, `MODERATE=2`, `HIGH=3`, `SEVERE=4`, `NO_TRAVEL=5`.
- Unit-test every boundary (for example, 25/35/45/55 mph), every precipitation boundary, and
  each load override. Include mixed-condition cases and provider-unit conversion tests.
- Version the risk-policy configuration on each analysis so future policy changes do not change
  historical results unexpectedly.

## 7. API contract

- `POST /api/v1/auth/token` and `/refresh` - JWT issuance/refresh; short-lived access token,
  rotating refresh token in an HttpOnly secure cookie where the deployment supports it.
- `POST /api/v1/analyses` - validates request and returns `202 { id, status }`.
- `GET /api/v1/analyses/{id}` - full result for its owner; compact route geometry by default.
- `GET /api/v1/analyses/{id}/events` - SSE progress stream (polling fallback).
- `GET /api/v1/analyses` - paginated history, cursor pagination, bounded page size, filterable
  by status/date; do not return every checkpoint in list views.
- `DELETE /api/v1/analyses/{id}` - owner-only deletion/retention control (if required).
- `GET /api/v1/openapi/` and `/api/docs/` - generated OpenAPI schema and Swagger UI.
- `GET /health/live`, `/health/ready`, `/metrics` - liveness, dependency-aware readiness, and
  Prometheus-compatible metrics.

Use DRF serializers as the validation layer, strict request/response schemas, stable error codes,
RFC 9457-style problem details, correlation IDs, and OpenAPI-generated TypeScript client types.

## 8. Frontend plan

### Screens and interaction

- **Route request page:** accessible form, address autocomplete with manual-entry fallback,
  ISO/local datetime input with timezone disclosure, weight unit, sampling choice, and inline
  validation.
- **Analysis page:** non-blocking progress state, recommended-route card, safety warning banner,
  comparison cards/table, map, checkpoint inspector, and method/provider attribution.
- **Map:** colored route lines, selected-route focus, clickable checkpoint markers, popup with
  localized ETA/weather/risk reasons, and responsive mobile layout.
- **Heatmap:** route corridor rendered in segments colored by risk at the selected forecast time;
  a throttled 0-48 hour slider updates style data, not the whole map. Use a legend that exposes
  the No Travel state distinctly.
- **History/detail:** cursor-paginated saved analyses with deep-linkable result URLs.

### Performance and accessibility

- Use React Query for cache, retries, cancellation, and analysis-status polling/SSE.
- Render line/GeoJSON sources in MapLibre; cluster markers, virtualize checkpoint lists, and
  memoize derived map data. Avoid one React component per long-route map marker.
- Debounce geocoding and time-slider events; abort stale browser requests.
- Keyboard-accessible controls, visible focus, semantic risk text in addition to color,
  WCAG AA contrast, reduced-motion support, and screen-reader summaries.

## 9. Reliability, security, and observability

- **Async/concurrency:** Celery workers make outbound routing/weather calls outside web workers.
  Use task idempotency keys, chord/group-style fan-out only with bounded concurrency, task time
  limits, and durable result status. This is scalable multi-worker processing, rather than unsafe
  in-process multi-threading.
- **Retries:** retry only transient errors (timeouts, 429, 5xx) with exponential backoff + jitter,
  per-provider retry budgets, and `Retry-After` support. Do not retry 4xx validation/auth errors.
  On permanent weather gaps, complete with a clearly flagged partial result rather than fabricated
  data.
- **Rate control:** per-user/IP API throttles, provider-specific token buckets, request-size/page
  bounds, geocoding debounce, and cache keys that include provider/version/coordinates/time.
- **Caching:** Redis cache for geocoding, route alternatives, and weather buckets with provider-
  appropriate TTL. Cache only safe normalized data; never cache a user's authenticated response
  without a user-aware key.
- **Security:** secrets only in environment/secret manager, CORS allowlist, HTTPS, secure cookie
  flags, CSRF protection where cookies are used, JWT rotation/revocation, authorization on every
  object lookup, input limits, audit logs, dependency scanning, and CSP/security headers.
- **Logging:** JSON logs with timestamp, level, request/correlation ID, analysis ID, provider,
  latency, retry count, and sanitized error code. Never log tokens, addresses beyond necessary
  operational retention, or raw provider secrets.
- **Metrics:** request rate, error rate, response latency (p50/p95/p99), 4xx/5xx count, queue
  depth/age, task duration/failures/retries, provider latency/error/429 rate, cache hit ratio,
  analyses completed/partial/failed, and client map render errors. Alert on SLO burn, sustained
  provider failure, queue backlog, or elevated analysis-failure rate.

## 10. Testing and quality gates

- Python: `ruff`, `mypy`, formatter, Django checks, migration checks, unit tests for all risk and
  ranking rules, API serializer/authorization tests, adapter contract tests, and Celery task tests.
- TypeScript: ESLint, typecheck, component tests, Playwright end-to-end tests for form -> result,
  no-travel warning, a provider failure, and slider/map interaction.
- Deterministic fixtures: saved routing and weather responses for every demo/test; no test relies
  on a live forecast.
- Integration tests with provider adapters mocked at HTTP boundaries; a small scheduled staging
  smoke test may call real providers with a capped budget.
- CI gate: lint, typecheck, tests, build, dependency/security audit, OpenAPI diff check, Docker
  image build, and coverage threshold on the risk/recommendation package.

## 11. Deployment and operations

- Docker Compose for local dev: frontend, Django API, worker, PostgreSQL/PostGIS, Redis, and
  reverse proxy. Production uses separate web and worker replicas with managed Postgres/Redis.
- GitHub Actions deploy pipeline: immutable image, migrations as a one-off release step, health
  check, rollback-ready release, and environment-specific secret injection.
- Configure backups, migration recovery procedure, retention for analyses/audit logs, and a short
  runbook for provider outage, queue backlog, and bad forecast data.
- Seed a deterministic demo analysis so the walkthrough works even if an external provider is
  temporarily unavailable; clearly identify it as demo data.

## 12. Implementation sequence

### Phase 0 - Foundation (0.5-1 day)

- Bootstrap monorepo, Docker/local environment, settings split, CI, lint/type/test tooling,
  environment template, README, and issue board.
- Establish provider adapter interfaces and fixture data before UI work.

### Phase 1 - Correctness first (1-2 days)

- Build request validation, geocoding/routing integration, geometry checkpointing, ETA engine,
  risk policy, risk-mile aggregation, ranking, and comprehensive tests.
- Expose synchronous development endpoint first, then put the same service behind a Celery task.

### Phase 2 - Assessment UI (1-2 days)

- Build form, progress flow, results cards, map routes/checkpoints, detail inspector, and
  responsive/error states.
- Add the time slider and optimized heatmap after route correctness is visible.

### Phase 3 - Production readiness (1-1.5 days)

- Add JWT/auth, persistence/history pagination, Redis cache, bounded fan-out, retry policy,
  logging/metrics/health endpoints, Swagger, security headers, and integration tests.

### Phase 4 - Demo readiness (0.5-1 day)

- Deploy, perform staging smoke test, run accessibility/performance pass, add screenshots and
  architecture/risk-decision documentation, and record the walkthrough.

If time is constrained, ship Phase 1 and Phase 2 completely before adding authentication or
history. Never trade away correct risk rules, ETA-aware forecast lookup, or map/heatmap smoothness.

## 13. Acceptance checklist

- [ ] A valid request returns three visibly distinct routes, or a transparent documented reason
      that the provider cannot supply three.
- [ ] Every route has checkpoint ETAs, weather values, reason-coded final risk, and distance-based
      risk-mile totals.
- [ ] All threshold and load-rule boundaries are tested and displayed correctly.
- [ ] Recommendation follows the required ordering and never labels a No Travel route as safe.
- [ ] Map and 0-48 hour heatmap slider remain responsive for the demo route.
- [ ] Loading, validation, empty, partial, timeout, and provider-error states are usable.
- [ ] API documentation, local setup, deployment instructions, and architecture/risk decisions are
      documented; secrets are absent from the repository.
- [ ] CI is green; production health, error, request, response, queue, and provider metrics are
      available; the hosted application and walkthrough are complete.
