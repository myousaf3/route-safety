# Five-to-ten minute walkthrough

Use this script for the assessment walkthrough. It works with live providers or the seeded
demo analysis (`python manage.py seed_demo`). The seeded analysis is Seattle → Salt Lake City
with one alternative carrying about 40 high-risk miles and a recommended route that avoids them.

## 0. Setup (30 seconds)

```bash
cd backend && .venv/bin/python manage.py runserver 127.0.0.1:8000
cd frontend && npm run dev
```

Open <http://127.0.0.1:5173>. If providers are slow or unavailable, run
`python manage.py seed_demo --count 5` and open an analysis from the **Saved** panel.

Optional: sign in via the **Account** panel to scope history to your user. Anonymous use still
works.

## 1. Problem framing (1 minute)

- The question is not "what is the weather today?" but "what weather will the truck meet at each
  point on each route?"
- The app compares three alternatives, not one, because a longer route can avoid a storm.
- Risk is expressed in **miles**, so a 40-mile bad stretch is visible even on a 900-mile run.

## 2. Empty state (1 minute)

- Point out the three-step pipeline: alternatives, ETA sampling, scoring.
- Show the risk legend and the recommendation order. Emphasise that No Travel is a separate
  level from Severe and that Unknown is never treated as safe.

## 3. Run a live analysis (2 minutes)

Use **Chicago → Denver**, departure 15:00 UTC, 42,000 lb, 25-mile detail.

- The request returns immediately (`202 Accepted`) and the UI polls until the job is complete;
  watch the staged progress: geocoding, routes, forecasts, scoring.
- Mention that a cold analysis takes roughly 7–12 seconds because the public providers are
  batched and cached; the result is then persisted.
- The deep link (`/#/analysis/<uuid>`) and history panel make the result reproducible.

## 4. Compare routes (1.5 minutes)

- Read the cards left-to-right: distance, No Travel, Severe, High, average risk.
- Note the recommended badge and the alternative that is disqualified (if any).
- Mention load overrides: wind 35–44 mph becomes Severe above 40,000 lb, 45–54 becomes No Travel
  above 30,000 lb, and 55+ is No Travel for any load.

## 5. Map and heatmap (1.5 minutes)

- Switch routes on the map by clicking a line or a route card.
- Click a checkpoint marker to see its ETA weather and the reasons it scored as it did.
- Toggle the forecast corridor and scrub the 0–48 hour slider. The route stays fixed while the
  forecast changes, which is the point of the heatmap.

## 6. Checkpoint inspector (1 minute)

- Switch spacing between 10, 25, and 50 miles. The table changes; the totals do not, because
  risk miles are always distance-weighted from 10-mile samples.
- Filter to unknown forecasts if any are present.

## 7. Recommendation and method (1 minute)

- Open **Recommendation** and read the rank key in order.
- Open **Method & providers** to show the exact provider string, policy version, status, and any
  limitations (for example, fewer than three truck-costed alternatives).
- Open **Distance-weighted risk** to show the per-severity mileage bar.

## 8. Production trade-offs (1 minute)

- Synchronous analysis is deliberate for the MVP; a worker comes later.
- No auth and SQLite are acceptable for a single-instance assessment demo.
- Providers are isolated behind adapters; commercial routing or weather APIs can replace them.
- Forecasts are advisory: no closures, chain controls, visibility, ice, or driver factors.

## Demo tips

- If the live providers are slow, run `seed_demo` first and open the saved analysis.
- Keep the browser zoom at 100% so the map and table fit.
- If a route has all-low risk, explain that the *mechanism* is what matters: the same pipeline
  would flag a storm if one were forecast.
