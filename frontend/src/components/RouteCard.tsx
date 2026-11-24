import {
  cx,
  formatDateTime,
  formatDuration,
  formatMiles,
  riskColor,
  riskFromAverage,
  riskLabel,
} from "../lib/format";
import type { RouteOption } from "../types";

interface Props {
  route: RouteOption;
  selected: boolean;
  destinationTimezone: string;
  onSelect: (id: number) => void;
}

export default function RouteCard({ route, selected, destinationTimezone, onSelect }: Props) {
  const averageLevel = riskFromAverage(route.metrics.average_risk_score);
  const hasNoTravel = route.metrics.no_travel_miles > 0;

  return (
    <button
      type="button"
      className={cx(
        "route-card",
        selected && "selected",
        route.recommended && "recommended",
        route.disqualified && "disqualified",
      )}
      onClick={() => onSelect(route.id)}
      aria-pressed={selected}
      aria-label={`Route ${route.sequence + 1}, ${formatMiles(route.distance_miles)}, ${
        route.recommended ? "recommended" : `rank ${route.rank}`
      }`}
    >
      <span className="route-card-top">
        <span className="route-rank">#{route.rank}</span>
        <span className="route-badges">
          {route.recommended && <span className="badge badge-recommended">Recommended</span>}
          {route.disqualified && <span className="badge badge-danger">Not recommended</span>}
          {!route.recommended && !route.disqualified && (
            <span className="badge badge-muted">Alternative</span>
          )}
        </span>
      </span>

      <span className="route-title-row">
        <span className="route-title">Route {route.sequence + 1}</span>
        <span
          className="risk-chip"
          style={{
            color: riskColor(averageLevel),
            borderColor: riskColor(averageLevel),
          }}
        >
          {riskLabel(averageLevel)}
        </span>
      </span>

      <span className="route-distance">{formatMiles(route.distance_miles)}</span>
      <span className="route-time">
        {formatDuration(route.duration_seconds)} drive · arrives{" "}
        {formatDateTime(route.eta_utc, destinationTimezone)}
      </span>

      <span className="route-metrics">
        <span>
          <span className="metric-label">Severe</span>
          <span className="metric-value">{formatMiles(route.metrics.severe_miles)}</span>
        </span>
        <span>
          <span className="metric-label">High</span>
          <span className="metric-value">{formatMiles(route.metrics.high_miles)}</span>
        </span>
        <span>
          <span className="metric-label">Avg risk</span>
          <span className="metric-value">{route.metrics.average_risk_score.toFixed(2)}</span>
        </span>
      </span>

      <span className={cx("route-foot", hasNoTravel && "danger-text")}>
        {hasNoTravel
          ? `${formatMiles(route.metrics.no_travel_miles)} rated No Travel`
          : "No Travel mileage: 0 mi"}
      </span>

      <span className="route-provider">
        {route.provider.toUpperCase()} · {route.costing} costing
      </span>
    </button>
  );
}
