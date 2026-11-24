import { RISK_COLORS, RISK_DESCRIPTIONS, RISK_LABELS } from "../lib/format";

export default function RiskLegend({ compact = false }: { compact?: boolean }) {
  return (
    <ul className={`risk-legend ${compact ? "risk-legend-compact" : ""}`}>
      {[1, 2, 3, 4, 5].map((value) => (
        <li key={value}>
          <span className="legend-dot" style={{ backgroundColor: RISK_COLORS[value] }} />
          <span className="legend-label">{RISK_LABELS[value]}</span>
          {!compact && <span className="legend-desc">{RISK_DESCRIPTIONS[value]}</span>}
        </li>
      ))}
      <li>
        <span className="legend-dot" style={{ backgroundColor: RISK_COLORS[0] }} />
        <span className="legend-label">Unknown</span>
        {!compact && <span className="legend-desc">No forecast; never assumed safe</span>}
      </li>
    </ul>
  );
}
