import { useMemo, useState } from "react";
import {
  formatTime,
  riskColor,
  RISK_LABELS,
  spacingLabel,
  weatherSummary,
} from "../lib/format";
import type { Checkpoint, RouteOption, Spacing } from "../types";

interface Props {
  route: RouteOption;
  spacing: Spacing;
  onSpacingChange: (spacing: Spacing) => void;
}

const SPACINGS: Spacing[] = [10, 25, 50];

function riskClass(risk: number): string {
  return `risk-bg-${risk}`;
}

function RiskPill({ risk, label }: { risk: number; label: string }) {
  return (
    <span className="risk-pill" style={{ borderColor: riskColor(risk), color: riskColor(risk) }}>
      <span className="risk-pill-dot" style={{ backgroundColor: riskColor(risk) }} />
      {label}
    </span>
  );
}

export default function CheckpointInspector({ route, spacing, onSpacingChange }: Props) {
  const [showUnknownOnly, setShowUnknownOnly] = useState(false);
  const checkpoints = useMemo(
    () => route.checkpoints[String(spacing) as "10" | "25" | "50"] ?? [],
    [route, spacing],
  );

  const counts = useMemo(() => {
    const result: Record<number, number> = { 0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
    for (const checkpoint of checkpoints) result[checkpoint.risk] += 1;
    return result;
  }, [checkpoints]);

  const visible = showUnknownOnly
    ? checkpoints.filter((checkpoint) => checkpoint.weather_status === "unknown")
    : checkpoints;

  return (
    <section className="panel inspector" aria-labelledby="inspector-title">
      <div className="panel-heading inspector-heading">
        <div>
          <span className="eyebrow">Checkpoint inspector</span>
          <h2 id="inspector-title">Route {route.sequence + 1} conditions</h2>
          <p className="subtle">
            {checkpoints.length} checkpoints · {spacingLabel(spacing)} spacing · risk at each ETA
          </p>
        </div>
        <div className="segmented segmented-small" role="group" aria-label="Checkpoint spacing">
          {SPACINGS.map((option) => (
            <button
              key={option}
              type="button"
              className={spacing === option ? "segment active" : "segment"}
              onClick={() => onSpacingChange(option)}
              aria-pressed={spacing === option}
            >
              {option} mi
            </button>
          ))}
        </div>
      </div>

      <div className="checkpoint-summary" aria-label="Risk distribution">
        {[1, 2, 3, 4, 5].map((level) => (
          <span key={level} className="summary-chip">
            <span className="legend-dot" style={{ backgroundColor: riskColor(level) }} />
            <strong>{counts[level]}</strong> {RISK_LABELS[level]}
          </span>
        ))}
        {counts[0] > 0 && (
          <span className="summary-chip">
            <span className="legend-dot" style={{ backgroundColor: riskColor(0) }} />
            <strong>{counts[0]}</strong> Unknown
          </span>
        )}
        {counts[0] > 0 && (
          <label className="inline-check">
            <input
              type="checkbox"
              checked={showUnknownOnly}
              onChange={(event) => setShowUnknownOnly(event.target.checked)}
            />
            Unknown only
          </label>
        )}
      </div>

      <div className="table-wrap">
        <table className="checkpoint-table">
          <caption className="sr-only">
            Weather, ETA, and risk for each checkpoint on route {route.sequence + 1}
          </caption>
          <thead>
            <tr>
              <th scope="col">Mile</th>
              <th scope="col">ETA (local)</th>
              <th scope="col">Conditions</th>
              <th scope="col">Risk</th>
              <th scope="col">Reason</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((checkpoint: Checkpoint) => (
              <tr key={checkpoint.sequence} className={riskClass(checkpoint.risk)}>
                <td className="mono" data-label="Mile">
                  {Math.round(checkpoint.cumulative_miles)}
                </td>
                <td data-label="ETA">
                  <span className="cell-strong">
                    {formatTime(checkpoint.eta_utc, checkpoint.timezone)}
                  </span>
                  <span className="cell-sub">{checkpoint.timezone}</span>
                </td>
                <td data-label="Conditions">
                  <span className="cell-strong">{weatherSummary(checkpoint)}</span>
                  {checkpoint.weather_status === "unknown" && (
                    <span className="cell-sub">Unknown is not treated as safe</span>
                  )}
                </td>
                <td data-label="Risk">
                  <RiskPill risk={checkpoint.risk} label={checkpoint.risk_label} />
                </td>
                <td className="reason-cell" data-label="Reason">
                  {checkpoint.reasons.length > 0 ? (
                    <ul className="reason-list">
                      {checkpoint.reasons.map((reason) => (
                        <li key={reason.code}>{reason.message}</li>
                      ))}
                    </ul>
                  ) : (
                    <span className="cell-sub">No threshold exceeded</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && (
          <p className="table-empty">No checkpoints match this filter.</p>
        )}
      </div>
    </section>
  );
}
