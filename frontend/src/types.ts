export type Spacing = 10 | 25 | 50;

export type TravelAdvisory = "clear" | "caution" | "no_safe_route" | "unknown";

export interface RiskReason {
  code: string;
  dimension: string;
  message: string;
  risk: number;
}

export interface WeatherSnapshot {
  wind_mph: number | null;
  wind_gust_mph?: number | null;
  rain_in_hr: number | null;
  snow_in_hr: number | null;
  temperature_f: number | null;
  visibility_miles: number | null;
  weather_code: number | null;
  forecast_time_utc?: string;
}

export interface Checkpoint {
  sequence: number;
  cumulative_miles: number;
  lat: number;
  lon: number;
  eta_utc: string;
  timezone: string;
  weather: Partial<WeatherSnapshot>;
  weather_status: "ok" | "unknown";
  base_risk: number;
  risk: number;
  risk_label: string;
  reasons: RiskReason[];
}

export interface RiskMiles {
  "1": number;
  "2": number;
  "3": number;
  "4": number;
  "5": number;
}

export interface RouteMetrics {
  no_travel_miles: number;
  severe_miles: number;
  high_miles: number;
  average_risk_score: number;
  max_risk: number;
  risk_miles?: RiskMiles;
  distance_miles?: number;
  duration_seconds?: number;
}

export interface HeatmapPoint {
  lat: number;
  lon: number;
  cumulative_miles: number;
  risk: number[];
}

export interface Heatmap {
  start_utc: string;
  hours: number;
  step_hours: number;
  points: HeatmapPoint[];
}

export interface RouteGeometry {
  type: "LineString";
  coordinates: [number, number][];
}

export interface RouteOption {
  id: number;
  sequence: number;
  rank: number;
  recommended: boolean;
  disqualified: boolean;
  distance_miles: number;
  duration_seconds: number;
  eta_utc: string;
  geometry: RouteGeometry;
  metrics: RouteMetrics;
  provider: string;
  costing: string;
  checkpoints: Record<"10" | "25" | "50", Checkpoint[]>;
  heatmap: Heatmap;
}

export interface PlaceRef {
  query: string;
  label: string;
  lat: number;
  lon: number;
  timezone: string;
}

export interface AnalysisRequest {
  origin: PlaceRef;
  destination: PlaceRef;
  departure_utc: string;
  departure_timezone: string;
  load_weight_lb: number;
  spacing_miles: Spacing;
}

export interface Analysis {
  id: string;
  status: "completed" | "partial" | "failed" | string;
  created_at: string;
  travel_advisory: TravelAdvisory;
  recommended_route_id: number | null;
  least_hazardous_route_id: number | null;
  limitations: string[];
  risk_policy_version: string;
  providers: Record<string, string>;
  error: Record<string, unknown>;
  request: AnalysisRequest;
  routes: RouteOption[];
}

export interface HistoryItem {
  id: string;
  created_at: string;
  status: string;
  travel_advisory: TravelAdvisory;
  origin: string;
  destination: string;
  departure_utc: string;
  load_weight_lb: number;
  spacing_miles: Spacing;
  route_count: number;
  recommended_route_id: number | null;
  summary_metrics: {
    distance_miles: number;
    duration_seconds: number;
    severe_miles: number;
    high_miles: number;
    average_risk_score: number;
  } | null;
}

export interface Place {
  label: string;
  lat: number;
  lon: number;
  timezone: string;
}

export interface CreateAnalysisInput {
  origin: string;
  destination: string;
  departure: string;
  load_weight_lb: number;
  spacing_miles: Spacing;
}

export interface Policy {
  version: string;
  levels: { value: number; label: string }[];
  thresholds: Record<string, Record<string, string>>;
  load_rules: string[];
  ranking_key: string[];
  spacings_miles: number[];
  heatmap_hours: number;
  missing_weather: string;
}
