import { useMemo, useState } from "react";
import {
  cx,
  formatDateTime,
  formatDuration,
  formatMiles,
  riskColor,
  riskFromAverage,
  RISK_LABELS,
  riskLabel,
  spacingLabel,
} from "../lib/format";
import type { Analysis, RouteOption, Spacing } from "../types";
import RouteCard from "./RouteCard";
import MapPanel from "./MapPanel";
import CheckpointInspector from "./CheckpointInspector";

interface Props {
  analysis: Analysis;
  onNew: () => void;
}

function advisoryCopy(analysis: Analysis, recommended: RouteOption | null): {
  tone: string;
  title: string;
  body: string;
} {
  if (analysis.travel_advisory === "no_safe_route") {
    return {
      tone: "danger",
      title: "No safe route for this departure",
      body:
        "Every alternative includes mileage rated No Travel. The least hazardous route is shown for context only — travel is not recommended with this load at this time.",
    };
  }
  if (analysis.travel_advisory === "caution") {
    return {
      tone: "caution",
      title: "Travel with caution",
      body: recommended
        ? `Route ${recommended.sequence + 1} is the safest available option, but it still contains hazardous mileage. Review the checkpoints before departure.`
        : "The safest available option still contains hazardous mileage.",
    };
  }
  return {
    tone: "clear",
    title: "Safest route identified",
    body: recommended
      ? `Route ${recommended.sequence + 1} ranks first on risk miles, average risk, and travel time. Conditions can change — re-check before departure.`
      : "A route was ranked first using the required risk ordering.",
  };
}

function RiskBreakdown({ route }: { route: RouteOption }) {
  const riskMiles = route.metrics.risk_miles;
  const total = riskMiles
    ? [1, 2, 3, 4, 5].reduce((sum, level) => sum + (riskMiles[String(level) as "1"] ?? 0), 0)
    : 0;

  return (
    <section className="panel side-panel" aria-labelledby="breakdown-title">
      <span className="eyebrow">Distance-weighted risk</span>
      <h2 id="breakdown-title">Route {route.sequence + 1} risk miles</h2>
      <p className="subtle">
        Each checkpoint’s risk is applied to the surrounding road distance, not counted as one
        sample.
      </p>
      {riskMiles && total > 0 ? (
        <>
          <div
            className="risk-bar"
            role="img"
            aria-label="Risk mileage distribution by severity"
          >
            {[1, 2, 3, 4, 5].map((level) => {
              const miles = riskMiles[String(level) as "1"] ?? 0;
              if (miles <= 0) return null;
              return (
                <span
                  key={level}
                  style={{
                    width: `${(miles / total) * 100}%`,
                    backgroundColor: riskColor(level),
                  }}
                  title={`${RISK_LABELS[level]}: ${formatMiles(miles)}`}
                />
              );
            })}
          </div>
          <ul className="risk-breakdown-list">
            {[1, 2, 3, 4, 5].map((level) => {
              const miles = riskMiles[String(level) as "1"] ?? 0;
              return (
                <li key={level}>
                  <span className="legend-dot" style={{ backgroundColor: riskColor(level) }} />
                  <span>{RISK_LABELS[level]}</span>
                  <strong>{miles > 0 ? formatMiles(miles) : "—"}</strong>
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <p className="inline-warning">
          No known risk mileage. Unknown forecasts are excluded and never counted as safe.
        </p>
      )}
      <div className="metric-pairs">
        <div>
          <span>Average risk</span>
          <strong>{riskLabel(riskFromAverage(route.metrics.average_risk_score))}</strong>
        </div>
        <div>
          <span>Score</span>
          <strong>{route.metrics.average_risk_score.toFixed(2)}</strong>
        </div>
        <div>
          <span>Max checkpoint</span>
          <strong style={{ color: riskColor(route.metrics.max_risk) }}>
            {riskLabel(route.metrics.max_risk)}
          </strong>
        </div>
        <div>
          <span>Drive time</span>
          <strong>{formatDuration(route.duration_seconds)}</strong>
        </div>
      </div>
    </section>
  );
}

function RecommendationPanel({
  analysis,
  recommended,
  selected,
}: {
  analysis: Analysis;
  recommended: RouteOption | null;
  selected: RouteOption;
}) {
  const rows = useMemo(
    () => [
      {
        label: "No Travel miles",
        value: formatMiles(selected.metrics.no_travel_miles),
        primary: true,
      },
      { label: "Severe miles", value: formatMiles(selected.metrics.severe_miles) },
      { label: "High miles", value: formatMiles(selected.metrics.high_miles) },
      { label: "Average risk", value: selected.metrics.average_risk_score.toFixed(2) },
      { label: "Travel time", value: formatDuration(selected.duration_seconds) },
    ],
    [selected],
  );

  return (
    <section className="panel side-panel" aria-labelledby="ranking-title">
      <span className="eyebrow">Recommendation</span>
      <h2 id="ranking-title">
        {recommended
          ? `Route ${recommended.sequence + 1} ranks #1`
          : "No route recommended"}
      </h2>
      <p className="subtle">
        Routes are compared lexicographically in this exact order. A positive No Travel distance
        disqualifies a route from being recommended.
      </p>
      <ol className="rank-key">
        {rows.map((row, index) => (
          <li key={row.label} className={row.primary ? "primary" : undefined}>
            <span className="rank-index">{index + 1}</span>
            <span className="rank-label">{row.label}</span>
            <strong>{row.value}</strong>
          </li>
        ))}
      </ol>
      {analysis.travel_advisory === "no_safe_route" && (
        <p className="inline-warning">
          Least hazardous:{" "}
          {(() => {
            const least = analysis.least_hazardous_route_id
              ? analysis.routes.find(
                  (route) => route.id === analysis.least_hazardous_route_id,
                )
              : undefined;
            return least ? `Route ${least.sequence + 1}` : "—";
          })()}{" "}
          · not recommended for travel.
        </p>
      )}
      <p className="mono small">Policy {analysis.risk_policy_version}</p>
    </section>
  );
}

function MethodPanel({ analysis }: { analysis: Analysis }) {
  return (
    <section className="panel side-panel" aria-labelledby="method-title">
      <span className="eyebrow">Method & providers</span>
      <h2 id="method-title">How this was computed</h2>
      <dl className="definition-list">
        <div>
          <dt>Routing</dt>
          <dd>{analysis.providers.routing ?? "—"}</dd>
        </div>
        <div>
          <dt>Geocoding</dt>
          <dd>{analysis.providers.geocoding ?? "—"}</dd>
        </div>
        <div>
          <dt>Weather</dt>
          <dd>{analysis.providers.weather ?? "—"}</dd>
        </div>
        <div>
          <dt>Risk policy</dt>
          <dd>{analysis.risk_policy_version}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{analysis.status === "partial" ? "Completed with forecast gaps" : analysis.status}</dd>
        </div>
      </dl>

      {analysis.limitations.length > 0 && (
        <details className="limitations" open>
          <summary>Provider limitations ({analysis.limitations.length})</summary>
          <ul>
            {analysis.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </details>
      )}

      <details className="limitations">
        <summary>Risk thresholds & load rules</summary>
        <div className="threshold-grid">
          <div>
            <strong>Wind</strong>
            <p>Low &lt;25 · Moderate 25–34 · High 35–44 · Severe 45–54 · No Travel ≥55 mph</p>
          </div>
          <div>
            <strong>Rain</strong>
            <p>
              Low &lt;0.10 · Moderate 0.10–0.25 · High 0.25–0.50 · Severe 0.50–1.00 · No Travel
              &gt;1.00 in/hr
            </p>
          </div>
          <div>
            <strong>Snow</strong>
            <p>
              Low &lt;0.5 · Moderate 0.5–1.0 · High 1.0–2.0 · Severe 2.0–3.0 · No Travel &gt;3.0
              in/hr
            </p>
          </div>
        </div>
        <ul className="rule-list">
          <li>Wind ≥55 mph is No Travel for any load.</li>
          <li>Wind 45–54 mph with a load over 30,000 lb is No Travel.</li>
          <li>Wind 35–44 mph with a load over 40,000 lb is Severe.</li>
        </ul>
      </details>
      <p className="mono small analysis-id">Analysis {analysis.id.slice(0, 8)}…</p>
    </section>
  );
}

export default function AnalysisResults({ analysis, onNew }: Props) {
  const routes = useMemo(
    () => [...analysis.routes].sort((a, b) => a.rank - b.rank),
    [analysis.routes],
  );
  const recommended = routes.find((route) => route.recommended) ?? null;
  const leastHazardous = analysis.least_hazardous_route_id
    ? routes.find((route) => route.id === analysis.least_hazardous_route_id) ?? null
    : null;
  const [selectedRouteId, setSelectedRouteId] = useState<number>(
    recommended?.id ?? leastHazardous?.id ?? routes[0]?.id ?? 0,
  );
  const [spacing, setSpacing] = useState<Spacing>(analysis.request.spacing_miles);
  const [heatmapHour, setHeatmapHour] = useState(0);
  const [showHeatmap, setShowHeatmap] = useState(true);

  const selectedRoute =
    routes.find((route) => route.id === selectedRouteId) ?? routes[0];
  const advisory = advisoryCopy(analysis, recommended);

  if (!selectedRoute) {
    return (
      <div className="panel error-panel">
        <strong>This analysis has no routes.</strong>
        <p>Start a new analysis to try a different origin or departure time.</p>
        <button type="button" className="btn btn-secondary" onClick={onNew}>
          New analysis
        </button>
      </div>
    );
  }

  const arrivalTime = formatDateTime(
    selectedRoute.eta_utc,
    analysis.request.destination.timezone,
  );

  return (
    <div className="results">
      <header className="analysis-head">
        <div>
          <span className="eyebrow">
            Analysis · {analysis.status === "partial" ? "partial forecast" : analysis.status}
          </span>
          <h1>
            {analysis.request.origin.label.split(",")[0]}
            <span className="head-arrow" aria-hidden="true">
              {" "}
              →{" "}
            </span>
            {analysis.request.destination.label.split(",")[0]}
          </h1>
          <p className="head-labels">
            {analysis.request.origin.label} → {analysis.request.destination.label}
          </p>
          <div className="meta-row">
            <span>
              Departs{" "}
              <strong>
                {formatDateTime(
                  analysis.request.departure_utc,
                  analysis.request.origin.timezone,
                )}
              </strong>
            </span>
            <span>
              Load <strong>{analysis.request.load_weight_lb.toLocaleString()} lb</strong>
            </span>
            <span>
              <strong>{routes.length}</strong> alternatives
            </span>
            <span>
              Detail <strong>{spacingLabel(spacing)}</strong>
            </span>
          </div>
        </div>
        <div className="head-actions">
          <button type="button" className="btn btn-ghost" onClick={onNew}>
            New analysis
          </button>
        </div>
      </header>

      <div className={cx("advisory", `advisory-${advisory.tone}`)} role="status">
        <span className="advisory-icon" aria-hidden="true">
          {advisory.tone === "danger" ? "!" : advisory.tone === "caution" ? "△" : "✓"}
        </span>
        <div>
          <strong>{advisory.title}</strong>
          <p>{advisory.body}</p>
        </div>
        {recommended && (
          <div className="advisory-route">
            <span>Recommended</span>
            <strong>Route {recommended.sequence + 1}</strong>
            <span>{formatMiles(recommended.distance_miles)}</span>
          </div>
        )}
      </div>

      {analysis.status === "partial" && (
        <div className="partial-strip" role="note">
          Some checkpoint forecasts were unavailable and are marked Unknown. Unknown conditions
          are never treated as safe, and the affected mileage is excluded from average risk.
        </div>
      )}

      <section className="route-grid" aria-label="Route comparison">
        {routes.map((route) => (
          <RouteCard
            key={route.id}
            route={route}
            selected={route.id === selectedRoute.id}
            destinationTimezone={analysis.request.destination.timezone}
            onSelect={setSelectedRouteId}
          />
        ))}
      </section>

      <MapPanel
        analysis={analysis}
        route={selectedRoute}
        spacing={spacing}
        heatmapHour={heatmapHour}
        onHeatmapHourChange={setHeatmapHour}
        showHeatmap={showHeatmap}
        onShowHeatmapChange={setShowHeatmap}
        onSelectRoute={setSelectedRouteId}
      />

      <div className="lower-grid">
        <CheckpointInspector
          route={selectedRoute}
          spacing={spacing}
          onSpacingChange={setSpacing}
        />
        <aside className="side-stack" aria-label="Route details">
          <div className="selected-summary">
            <span className="eyebrow">Selected</span>
            <strong>Route {selectedRoute.sequence + 1}</strong>
            <span>{formatMiles(selectedRoute.distance_miles)}</span>
            <span>Arrives {arrivalTime}</span>
          </div>
          <RiskBreakdown route={selectedRoute} />
          <RecommendationPanel
            analysis={analysis}
            recommended={recommended}
            selected={selectedRoute}
          />
          <MethodPanel analysis={analysis} />
        </aside>
      </div>
    </div>
  );
}
