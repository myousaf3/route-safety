import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, getAnalysis, listAnalyses } from "./lib/api";
import type { Analysis } from "./types";
import RouteForm from "./components/RouteForm";
import HistoryPanel from "./components/HistoryPanel";
import AccountControl from "./components/AccountControl";
import AuthPage from "./components/AuthPage";
import type { AuthMode } from "./components/AuthPage";
import AnalysisResults from "./components/AnalysisResults";
import EmptyState from "./components/EmptyState";
import Brand from "./components/Brand";

type Route = { name: "app" } | { name: "auth"; mode: AuthMode };

function readHashId(): string | null {
  const match = window.location.hash.match(/^#\/?analysis\/([0-9a-f-]{36})$/i);
  return match ? match[1] : null;
}

/** Minimal hash router: the app shell plus the standalone auth page. */
function readRoute(): Route {
  const hash = window.location.hash.replace(/\/+$/, "");
  if (hash === "#/register") return { name: "auth", mode: "register" };
  if (hash === "#/login") return { name: "auth", mode: "login" };
  return { name: "app" };
}

export default function App() {
  const [route, setRoute] = useState<Route>(readRoute);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ApiError | null>(null);
  const mainRef = useRef<HTMLElement>(null);

  const history = useQuery({
    queryKey: ["analyses"],
    queryFn: listAnalyses,
  });

  const scrollToMain = useCallback(() => {
    window.requestAnimationFrame(() => {
      mainRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, []);

  const loadById = useCallback(
    async (id: string) => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const loaded = await getAnalysis(id);
        setAnalysis(loaded);
        window.history.replaceState(null, "", `#/analysis/${loaded.id}`);
        scrollToMain();
      } catch (error) {
        setDetailError(
          error instanceof ApiError
            ? error
            : new ApiError("Could not load that analysis.", { status: 0 }),
        );
        setAnalysis(null);
      } finally {
        setDetailLoading(false);
      }
    },
    [scrollToMain],
  );

  useEffect(() => {
    const id = readHashId();
    if (id) void loadById(id);
  }, [loadById]);

  // Keep the rendered page in sync with manual hash navigation (back/forward,
  // direct links to #/login or #/register, and deep links to an analysis).
  useEffect(() => {
    const handleHashChange = () => {
      const next = readRoute();
      setRoute(next);
      if (next.name === "app") {
        const id = readHashId();
        if (id) void loadById(id);
      }
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, [loadById]);

  // Poll queued/running analyses until they reach a terminal state.
  useEffect(() => {
    if (!analysis || ["completed", "partial", "failed"].includes(analysis.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void getAnalysis(analysis.id)
        .then((updated) => setAnalysis(updated))
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [analysis]);

  const handleCreated = useCallback(
    (created: Analysis) => {
      setAnalysis(created);
      setDetailError(null);
      window.history.replaceState(null, "", `#/analysis/${created.id}`);
      void history.refetch();
      scrollToMain();
    },
    [history, scrollToMain],
  );

  const handleNew = useCallback(() => {
    setAnalysis(null);
    setDetailError(null);
    window.history.replaceState(null, "", window.location.pathname);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const openAuth = useCallback((mode: AuthMode) => {
    window.location.hash = mode === "register" ? "#/register" : "#/login";
    setRoute({ name: "auth", mode });
    window.scrollTo({ top: 0 });
  }, []);

  const closeAuth = useCallback(() => {
    window.location.hash = "";
    setRoute({ name: "app" });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  if (route.name === "auth") {
    return <AuthPage mode={route.mode} onModeChange={openAuth} onDone={closeAuth} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <Brand />
        <div className="topbar-actions">
          <div className="topbar-meta">
            <span className="topbar-chip">ETA-aware forecast sampling</span>
            <span className="topbar-chip">0–48h corridor heatmap</span>
          </div>
          <AccountControl />
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar" aria-label="Route request and history">
          <RouteForm onCreated={handleCreated} />
          <HistoryPanel
            items={history.data?.results ?? []}
            loading={history.isLoading}
            error={history.isError ? "Could not load saved analyses." : null}
            activeId={analysis?.id ?? null}
            onSelect={(id) => void loadById(id)}
            onNew={handleNew}
          />
        </aside>

        <main id="main" ref={mainRef} className="main" tabIndex={-1}>
          {detailLoading && (
            <div className="panel loading-panel" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              <div>
                <strong>Loading saved analysis…</strong>
                <p>Fetching the persisted routes, checkpoints, and forecast snapshot.</p>
              </div>
            </div>
          )}

          {detailError && (
            <div className="panel error-panel" role="alert">
              <strong>We couldn’t load that analysis.</strong>
              <p>{detailError.detail}</p>
              {detailError.correlationId && (
                <p className="mono small">Correlation ID: {detailError.correlationId}</p>
              )}
              <button type="button" className="btn btn-secondary" onClick={handleNew}>
                Start a new analysis
              </button>
            </div>
          )}

          {!detailLoading && !detailError && !analysis && <EmptyState />}

          {analysis && (
            <AnalysisResults
              key={analysis.id}
              analysis={analysis}
              onNew={handleNew}
            />
          )}
        </main>
      </div>

      <footer className="footer">
        <span>
          Routing: Valhalla / OSRM · Geocoding: Nominatim · Weather: Open-Meteo
        </span>
        <span>Risk policy 2026-11-a · Forecast data is advisory, not a road report.</span>
      </footer>
    </div>
  );
}
