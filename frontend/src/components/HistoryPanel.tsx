import { formatDateShort, formatMiles, RISK_COLORS } from "../lib/format";
import type { HistoryItem } from "../types";

interface Props {
  items: HistoryItem[];
  loading: boolean;
  error: string | null;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

function advisoryColor(advisory: string): string {
  if (advisory === "no_safe_route") return RISK_COLORS[5];
  if (advisory === "caution") return RISK_COLORS[3];
  if (advisory === "clear") return RISK_COLORS[1];
  return RISK_COLORS[0];
}

export default function HistoryPanel({
  items,
  loading,
  error,
  activeId,
  onSelect,
  onNew,
}: Props) {
  return (
    <section className="panel history-panel" aria-labelledby="history-title">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Saved</span>
          <h2 id="history-title">Recent analyses</h2>
        </div>
        <button type="button" className="btn btn-ghost btn-small" onClick={onNew}>
          New
        </button>
      </div>

      {loading && (
        <div className="history-skeleton" aria-label="Loading history">
          <span />
          <span />
          <span />
        </div>
      )}

      {error && <p className="inline-error">{error}</p>}

      {!loading && !error && items.length === 0 && (
        <p className="history-empty">
          Completed analyses are saved here so results stay stable after forecasts change.
        </p>
      )}

      <ul className="history-list">
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className={item.id === activeId ? "history-item active" : "history-item"}
              onClick={() => onSelect(item.id)}
              aria-current={item.id === activeId ? "true" : undefined}
            >
              <span
                className="history-dot"
                style={{ backgroundColor: advisoryColor(item.travel_advisory) }}
                aria-hidden="true"
              />
              <span className="history-main">
                <span className="history-route">
                  {item.origin.split(",")[0]} → {item.destination.split(",")[0]}
                </span>
                <span className="history-meta">
                  {formatDateShort(item.created_at)} · {item.load_weight_lb.toLocaleString()} lb
                  {item.summary_metrics
                    ? ` · ${formatMiles(item.summary_metrics.distance_miles)}`
                    : ""}
                </span>
              </span>
              <span className="history-status">{item.travel_advisory.replaceAll("_", " ")}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
