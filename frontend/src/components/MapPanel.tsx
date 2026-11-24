import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { LngLatBounds, type Map as MapLibreMap, type Popup } from "maplibre-gl";
import type { FeatureCollection, LineString, Point } from "geojson";
import {
  formatDateTime,
  formatMiles,
  formatTime,
  riskColor,
  weatherSummary,
} from "../lib/format";
import type { Analysis, Checkpoint, RouteOption, Spacing } from "../types";
import RiskLegend from "./RiskLegend";

const STYLE_URL = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const EMPTY_ROUTES: FeatureCollection<LineString> = {
  type: "FeatureCollection",
  features: [],
};
const EMPTY_POINTS: FeatureCollection<Point> = { type: "FeatureCollection", features: [] };

interface Props {
  analysis: Analysis;
  route: RouteOption;
  spacing: Spacing;
  heatmapHour: number;
  onHeatmapHourChange: (hour: number) => void;
  showHeatmap: boolean;
  onShowHeatmapChange: (value: boolean) => void;
  onSelectRoute: (id: number) => void;
}

function addSourcesAndLayers(map: MapLibreMap) {
  map.addSource("routes", { type: "geojson", data: EMPTY_ROUTES });
  map.addSource("checkpoints", { type: "geojson", data: EMPTY_POINTS });
  map.addSource("heatmap", { type: "geojson", data: EMPTY_ROUTES });

  map.addLayer({
    id: "route-casing",
    type: "line",
    source: "routes",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": "#020617",
      "line-width": ["case", ["get", "selected"], 9, 6],
      "line-opacity": 0.7,
    },
  });

  map.addLayer({
    id: "route-selected-glow",
    type: "line",
    source: "routes",
    filter: ["==", ["get", "selected"], true],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#67e8f9", "line-width": 11, "line-opacity": 0.16 },
  });

  map.addLayer({
    id: "route-line",
    type: "line",
    source: "routes",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": [
        "case",
        ["get", "recommended"],
        "#bef264",
        ["get", "selected"],
        "#67e8f9",
        "#94a3b8",
      ],
      "line-width": ["case", ["get", "selected"], 4.5, 3],
      "line-opacity": ["case", ["get", "selected"], 1, 0.72],
    },
  });

  map.addLayer({
    id: "heatmap-line",
    type: "line",
    source: "heatmap",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": [
        "match",
        ["get", "risk"],
        1,
        riskColor(1),
        2,
        riskColor(2),
        3,
        riskColor(3),
        4,
        riskColor(4),
        5,
        riskColor(5),
        riskColor(0),
      ],
      "line-width": 6,
      "line-opacity": 0.92,
    },
  });

  map.addLayer({
    id: "checkpoint-halo",
    type: "circle",
    source: "checkpoints",
    paint: {
      "circle-radius": 8,
      "circle-color": "#020617",
      "circle-opacity": 0.6,
    },
  });

  map.addLayer({
    id: "checkpoints",
    type: "circle",
    source: "checkpoints",
    paint: {
      "circle-radius": ["case", ["==", ["get", "risk"], 5], 6, 4.5],
      "circle-color": [
        "match",
        ["get", "risk"],
        1,
        riskColor(1),
        2,
        riskColor(2),
        3,
        riskColor(3),
        4,
        riskColor(4),
        5,
        riskColor(5),
        riskColor(0),
      ],
      "circle-stroke-color": "#020617",
      "circle-stroke-width": 1.5,
    },
  });
}

function makePopupContent(checkpoint: Checkpoint): HTMLElement {
  const root = document.createElement("div");
  root.className = "map-popup";

  const kicker = document.createElement("span");
  kicker.className = "map-popup-kicker";
  kicker.textContent = `Mile ${Math.round(checkpoint.cumulative_miles)} · ${formatTime(
    checkpoint.eta_utc,
    checkpoint.timezone,
  )}`;
  root.appendChild(kicker);

  const title = document.createElement("strong");
  title.className = "map-popup-title";
  title.textContent = `${checkpoint.risk_label} risk`;
  title.style.color = riskColor(checkpoint.risk);
  root.appendChild(title);

  const conditions = document.createElement("p");
  conditions.className = "map-popup-conditions";
  conditions.textContent =
    checkpoint.weather_status === "unknown" ? "No forecast available" : weatherSummary(checkpoint);
  root.appendChild(conditions);

  if (checkpoint.reasons.length > 0) {
    const list = document.createElement("ul");
    checkpoint.reasons.slice(0, 4).forEach((reason) => {
      const item = document.createElement("li");
      item.textContent = reason.message;
      list.appendChild(item);
    });
    root.appendChild(list);
  } else {
    const clear = document.createElement("p");
    clear.className = "map-popup-clear";
    clear.textContent = "No threshold exceeded.";
    root.appendChild(clear);
  }

  return root;
}

export default function MapPanel({
  analysis,
  route,
  spacing,
  heatmapHour,
  onHeatmapHourChange,
  showHeatmap,
  onShowHeatmapChange,
  onSelectRoute,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const popupRef = useRef<Popup | null>(null);
  const checkpointsRef = useRef<Checkpoint[]>([]);
  const selectRouteRef = useRef(onSelectRoute);
  const [ready, setReady] = useState(false);
  const [mapSlow, setMapSlow] = useState(false);

  selectRouteRef.current = onSelectRoute;

  const checkpoints = useMemo(
    () => route.checkpoints[String(spacing) as "10" | "25" | "50"] ?? [],
    [route, spacing],
  );
  checkpointsRef.current = checkpoints;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setReady(false);
    setMapSlow(false);

    const map = new maplibregl.Map({
      container,
      style: STYLE_URL,
      center: [-98.5, 39.5],
      zoom: 3.3,
      attributionControl: { compact: true },
      fadeDuration: 0,
      preserveDrawingBuffer: true,
    });
    mapRef.current = map;
    if (import.meta.env.DEV) {
      (window as unknown as { __spotterMap?: MapLibreMap }).__spotterMap = map;
    }
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const slowTimer = window.setTimeout(() => setMapSlow(true), 9000);

    map.on("load", () => {
      window.clearTimeout(slowTimer);
      addSourcesAndLayers(map);
      map.on("click", "checkpoints", (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const sequence = Number(feature.properties?.sequence);
        const checkpoint = checkpointsRef.current.find((item) => item.sequence === sequence);
        if (!checkpoint) return;
        popupRef.current?.remove();
        popupRef.current = new maplibregl.Popup({ closeButton: true, offset: 12 })
          .setLngLat([checkpoint.lon, checkpoint.lat])
          .setDOMContent(makePopupContent(checkpoint))
          .addTo(map);
      });
      map.on("mouseenter", "checkpoints", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "checkpoints", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("click", "route-line", (event) => {
        const feature = event.features?.[0];
        const id = Number(feature?.properties?.id);
        if (Number.isFinite(id)) selectRouteRef.current(id);
      });
      map.on("mouseenter", "route-line", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "route-line", () => {
        map.getCanvas().style.cursor = "";
      });
      setReady(true);
    });

    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container);

    return () => {
      window.clearTimeout(slowTimer);
      observer.disconnect();
      popupRef.current?.remove();
      popupRef.current = null;
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  // Fit all alternatives when a new analysis is loaded.
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const coordinates = analysis.routes.flatMap((item) => item.geometry.coordinates);
    if (coordinates.length === 0) return;
    const bounds = coordinates.reduce((accumulator, coordinate) => {
      return accumulator.extend(coordinate as [number, number]);
    }, new LngLatBounds());
    mapRef.current.fitBounds(bounds, {
      padding: { top: 48, bottom: 48, left: 48, right: 48 },
      duration: 900,
      maxZoom: 8,
    });
  }, [analysis.id, analysis.routes, ready]);

  // Route geometries and selected state.
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const source = mapRef.current.getSource("routes") as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    const data: FeatureCollection<LineString> = {
      type: "FeatureCollection",
      features: analysis.routes.map((item) => ({
        type: "Feature",
        id: item.id,
        properties: {
          id: item.id,
          recommended: item.recommended,
          selected: item.id === route.id,
          disqualified: item.disqualified,
        },
        geometry: item.geometry,
      })),
    };
    source.setData(data);
  }, [ready, analysis.routes, route.id]);

  // Checkpoint markers for the selected route and spacing.
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const source = mapRef.current.getSource("checkpoints") as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!source) return;
    const data: FeatureCollection<Point> = {
      type: "FeatureCollection",
      features: checkpoints.map((checkpoint) => ({
        type: "Feature",
        id: checkpoint.sequence,
        properties: {
          sequence: checkpoint.sequence,
          risk: checkpoint.risk,
        },
        geometry: {
          type: "Point",
          coordinates: [checkpoint.lon, checkpoint.lat],
        },
      })),
    };
    source.setData(data);
    popupRef.current?.remove();
    popupRef.current = null;
  }, [ready, checkpoints]);

  // Heatmap segments for the selected route at the chosen forecast hour.
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const source = mapRef.current.getSource("heatmap") as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    const points = route.heatmap.points;
    const features: FeatureCollection<LineString>["features"] = [];
    for (let index = 0; index < points.length - 1; index += 1) {
      const current = points[index];
      const next = points[index + 1];
      const risk = current.risk[heatmapHour] ?? 0;
      features.push({
        type: "Feature",
        properties: { risk },
        geometry: {
          type: "LineString",
          coordinates: [
            [current.lon, current.lat],
            [next.lon, next.lat],
          ],
        },
      });
    }
    source.setData({ type: "FeatureCollection", features });
  }, [ready, route.heatmap, heatmapHour]);

  useEffect(() => {
    if (!ready || !mapRef.current) return;
    mapRef.current.setLayoutProperty(
      "heatmap-line",
      "visibility",
      showHeatmap ? "visible" : "none",
    );
    mapRef.current.setPaintProperty(
      "route-line",
      "line-opacity",
      showHeatmap ? 0.28 : ["case", ["get", "selected"], 1, 0.72],
    );
  }, [ready, showHeatmap]);

  const forecastTime = useMemo(() => {
    const base = new Date(route.heatmap.start_utc).getTime();
    return new Date(base + heatmapHour * 60 * 60 * 1000);
  }, [route.heatmap.start_utc, heatmapHour]);

  const forecastLabel = formatDateTime(forecastTime.toISOString(), analysis.request.origin.timezone);

  return (
    <section className="panel map-card" aria-labelledby="map-title">
      <div className="panel-heading map-heading">
        <div>
          <span className="eyebrow">Route map</span>
          <h2 id="map-title">
            Route {route.sequence + 1}
            {route.recommended ? " · recommended" : ""}
          </h2>
          <p className="subtle">
            {formatMiles(route.distance_miles)} · click a checkpoint for its ETA weather
          </p>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            checked={showHeatmap}
            onChange={(event) => onShowHeatmapChange(event.target.checked)}
          />
          <span className="switch-track" aria-hidden="true">
            <span className="switch-thumb" />
          </span>
          Forecast corridor
        </label>
      </div>

      <div className="map-wrap">
        <div ref={containerRef} className="map" aria-label="Map of route alternatives" />
        {!ready && (
          <div className="map-loading">
            <span className="spinner" aria-hidden="true" />
            <span>Loading basemap…</span>
          </div>
        )}
        {mapSlow && !ready && (
          <div className="map-fallback">
            Basemap tiles are unavailable. Route and checkpoint data remain in the cards and
            tables below.
          </div>
        )}
        <div className="map-overlay">
          <span className="map-badge">
            {showHeatmap ? `Forecast · ${forecastLabel}` : "Risk at checkpoint ETA"}
          </span>
        </div>
        <div className="map-legend">
          <RiskLegend compact />
        </div>
      </div>

      <div className="heatmap-bar">
        <div className="heatmap-readout">
          <span className="eyebrow">Corridor heatmap</span>
          <strong>{showHeatmap ? `+${heatmapHour}h` : "Forecast off"}</strong>
          <span className="subtle">{forecastLabel}</span>
        </div>
        <div className="slider-wrap">
          <input
            type="range"
            min={0}
            max={route.heatmap.hours}
            step={route.heatmap.step_hours}
            value={heatmapHour}
            onChange={(event) => onHeatmapHourChange(Number(event.target.value))}
            aria-label="Forecast hour offset from departure"
            aria-valuetext={`${heatmapHour} hours after departure, ${forecastLabel}`}
          />
          <div className="slider-ticks" aria-hidden="true">
            <span>Departure</span>
            <span>+12h</span>
            <span>+24h</span>
            <span>+36h</span>
            <span>+48h</span>
          </div>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-small"
          onClick={() => onHeatmapHourChange(0)}
          disabled={heatmapHour === 0}
        >
          Reset to departure
        </button>
      </div>
    </section>
  );
}
