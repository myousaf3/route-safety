# Loom Video Script — Spotter Weather-Aware Truck Routing (2 minutes)

## Opening paragraph (say this in the first 10–15 seconds, before the demo)

"Hi — I'm Yousaf, and this is Spotter, a weather-aware truck routing app I built for the Spotter full-stack assessment. The core idea is simple but the engineering is not: instead of asking 'what's the weather today,' Spotter asks 'what weather will this specific truck meet at each point on each route, at the exact time it arrives.' It compares three route alternatives, scores risk in miles at 10-mile checkpoints, and recommends the safest — all through an async, production-grade pipeline with JWT auth, owner-scoped history, observability, and a live deployment on Railway and Cloudflare. Let me walk you through it."

Target: ~260 spoken words (~130 wpm). Record against the live deployment
(`https://route-safety.pages.dev` + Railway API) so reviewers see real provider calls.

## Timing & narration

### 0:00–0:15 — Problem & approach (screen: empty state)
**Show:** Home page empty state, three-step pipeline card, risk legend.
**Say:** "Spotter answers one question: not what's the weather, but what weather will this truck meet at each point on each route, at the time it arrives. I compare three alternatives because a longer route can avoid a storm, and I express risk in miles so a 40-mile bad stretch is visible on a 900-mile run."

### 0:15–0:45 — Live analysis (screen: form → running → result)
**Show:** Enter Chicago → Denver, departure 15:00 UTC, 42,000 lb, 25-mile detail. Submit. Watch staged progress (geocoding → routes → forecasts → scoring). Then the result.
**Say:** "The request returns 202 immediately and a Celery job runs the pipeline; the UI polls to terminal state. Routes come from Valhalla with OSRM fallback, weather from Open-Meteo batched at 40 points with concurrency of six, and ETA-aware sampling along each alternative. Everything is cached and persisted."

### 0:45–1:15 — Risk comparison (screen: route cards + recommendation)
**Show:** The three route cards, recommended badge, disqualified alternative.
**Say:** "Risk is scored at 10-mile checkpoints — no-travel miles, severe miles, high miles, average risk, then duration. No-travel is separate from severe; unknown is never treated as safe. Load thresholds are applied: wind 35–44 becomes severe above 40,000 lb, 45–54 becomes no-travel above 30,000 lb, 55-plus is no-travel for any load."

### 1:15–1:35 — Map & heatmap (screen: map, scrub time)
**Show:** Map with route polylines, heatmap, time slider, checkpoint tooltip.
**Say:** "The map shows where the risk actually is along each route, and the time slider lets you scrub the forecast window. Deep links and the history panel make any result reproducible."

### 1:35–1:55 — Auth & production readiness (screen: auth page, header account, history, Swagger)
**Show:** Click header "Sign in" → standalone auth page → register → return to app → history scoped to user. Flash Swagger at `/api/docs/` and `/health/ready`.
**Say:** "Auth is optional: anonymous analyses work, signed-in history is owner-scoped and private with JWT plus automatic refresh. The API has throttling, pagination, problem-details errors, OpenAPI, Sentry, and Prometheus metrics. It's deployed as Django plus Gunicorn on Railway with Neon Postgres, Celery in eager mode, and the React build on Cloudflare Pages."

### 1:55–2:00 — Close (screen: home)
**Say:** "Risk policy version is 2026-11-a, pinned and versioned. Repo and walkthrough are on GitHub — happy to dive into any layer."

## Pages to show (in order)
1. Home / empty state
2. Analysis form → running progress → result
3. Route comparison cards
4. Map + heatmap + time slider
5. Auth page (`/#/login`) → account in header → history
6. Swagger (`/api/docs/`) and `/health/ready`
7. Home (close)

## Talking points that signal expertise
- ETA-aware sampling, not snapshot weather.
- Risk in miles, not just counts — makes long routes legible.
- No-travel is a distinct level from severe; unknown never treated as safe.
- 10-mile checkpoints drive scoring; 25/50-mile are display-only.
- Async by design: 202 + polling, Celery, task time limits, retries.
- Owner-scoped, private history with JWT rotation and refresh.
- Deterministic recommendation order (no-travel → severe → high → avg risk → duration).
- Observability: correlation IDs, JSON logs, Prometheus metrics, health ready probe.
- Production hardening: secrets via `*_FILE`, HSTS, rate limits, backups, cleanup command, load test.
- Honest free-tier trade-offs: Celery eager, one worker, 512 MB, keep-alive pings.

## Tips
- Keep browser zoom ~110% and narrate over real requests (not seeded data) so reviewers see live provider calls and the 202→polling flow.
- Keep mouse movement deliberate; pause 1s on each result before moving on.
- If an analysis is slow, use the seeded demo (`seed_demo --count 5`) as fallback.
