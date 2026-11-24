import type { Checkpoint, RouteMetrics, Spacing } from "../types";

export const RISK_LABELS: Record<number, string> = {
  0: "Unknown",
  1: "Low",
  2: "Moderate",
  3: "High",
  4: "Severe",
  5: "No Travel",
};

export const RISK_COLORS: Record<number, string> = {
  0: "#64748b",
  1: "#22c55e",
  2: "#eab308",
  3: "#f97316",
  4: "#ef4444",
  5: "#a855f7",
};

export const RISK_DESCRIPTIONS: Record<number, string> = {
  0: "No forecast data",
  1: "Routine conditions",
  2: "Use caution",
  3: "Hazardous conditions",
  4: "Dangerous conditions",
  5: "Do not travel",
};

export function riskLabel(value: number | undefined | null): string {
  if (value === undefined || value === null) return "Unknown";
  return RISK_LABELS[value] ?? "Unknown";
}

export function riskColor(value: number | undefined | null): string {
  if (value === undefined || value === null) return RISK_COLORS[0];
  return RISK_COLORS[value] ?? RISK_COLORS[0];
}

export function riskFromAverage(score: number): number {
  if (!Number.isFinite(score) || score <= 0) return 0;
  if (score < 1.5) return 1;
  if (score < 2.5) return 2;
  if (score < 3.5) return 3;
  if (score < 4.5) return 4;
  return 5;
}

export function formatMiles(miles: number): string {
  return `${Math.round(miles).toLocaleString()} mi`;
}

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
}

export function formatDateTime(iso: string, timeZone?: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone,
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(date);
  } catch {
    return date.toLocaleString();
  }
}

export function formatTime(iso: string, timeZone?: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone,
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  } catch {
    return date.toLocaleTimeString();
  }
}

export function formatDateShort(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function localTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function defaultDepartureInput(): string {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  date.setMinutes(0, 0, 0);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function toIsoWithOffset(localInput: string): string {
  const date = new Date(localInput);
  if (Number.isNaN(date.getTime())) return localInput;
  return date.toISOString();
}

export function triggerDateInput(iso: string): string {
  const date = new Date(iso);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function maxDepartureInput(days = 15): string {
  const date = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function weatherSummary(checkpoint: Checkpoint): string {
  if (checkpoint.weather_status === "unknown") return "Forecast unavailable";
  const parts: string[] = [];
  const { wind_mph, rain_in_hr, snow_in_hr, temperature_f } = checkpoint.weather;
  if (wind_mph !== null && wind_mph !== undefined) parts.push(`${wind_mph.toFixed(0)} mph wind`);
  if (snow_in_hr !== null && snow_in_hr !== undefined && snow_in_hr > 0) {
    parts.push(`${snow_in_hr.toFixed(2)} in/hr snow`);
  } else if (rain_in_hr !== null && rain_in_hr !== undefined && rain_in_hr > 0) {
    parts.push(`${rain_in_hr.toFixed(2)} in/hr rain`);
  }
  if (temperature_f !== null && temperature_f !== undefined) {
    parts.push(`${temperature_f.toFixed(0)}°F`);
  }
  return parts.join(" · ") || "Clear";
}

export function heaviestRisk(checkpoints: Checkpoint[]): number {
  return checkpoints.reduce((worst, checkpoint) => Math.max(worst, checkpoint.risk), 0);
}

export function spacingLabel(spacing: Spacing): string {
  return `${spacing}-mile`;
}

export function metricLine(metrics: RouteMetrics): string {
  const parts = [`${formatMiles(metrics.distance_miles ?? 0)}`];
  if (metrics.no_travel_miles > 0) parts.push(`${formatMiles(metrics.no_travel_miles)} no-travel`);
  if (metrics.severe_miles > 0) parts.push(`${formatMiles(metrics.severe_miles)} severe`);
  if (metrics.high_miles > 0) parts.push(`${formatMiles(metrics.high_miles)} high`);
  return parts.join(" · ");
}

export function cx(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}
