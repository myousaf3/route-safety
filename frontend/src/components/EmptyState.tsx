import RiskLegend from "./RiskLegend";

const steps = [
  {
    number: "01",
    title: "Request alternatives",
    body: "Geocode the endpoints and retrieve three distinct truck-capable routes.",
  },
  {
    number: "02",
    title: "Sample at arrival time",
    body: "Create 10/25/50-mile checkpoints and fetch the forecast valid at each ETA.",
  },
  {
    number: "03",
    title: "Score & recommend",
    body: "Apply wind, rain, snow, and load rules, then rank by risk miles and time.",
  },
];

export default function EmptyState() {
  return (
    <div className="empty-state">
      <section className="hero panel">
        <div className="hero-copy">
          <span className="eyebrow">Weather-aware truck routing</span>
          <h1>
            Choose the road that keeps you <em>out</em> of the weather.
          </h1>
          <p>
            Compare three route alternatives using the forecast at the exact time your truck
            reaches each point, not today’s weather. See risk miles, checkpoint conditions, and a
            48-hour corridor heatmap before you commit.
          </p>
          <div className="hero-points">
            <span>✓ ETA-aware forecasts</span>
            <span>✓ Load-weight overrides</span>
            <span>✓ Distance-weighted risk</span>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="hero-route" />
          <div className="hero-pin hero-pin-a" />
          <div className="hero-pin hero-pin-b" />
          <div className="hero-weather-card">
            <span className="tiny-label">Checkpoint · mile 412</span>
            <strong>42 mph wind</strong>
            <span className="hero-risk">Severe · 42,000 lb</span>
          </div>
        </div>
      </section>

      <section className="steps">
        {steps.map((step) => (
          <article key={step.number} className="step-card panel">
            <span className="step-number">{step.number}</span>
            <h2>{step.title}</h2>
            <p>{step.body}</p>
          </article>
        ))}
      </section>

      <section className="panel legend-panel">
        <div>
          <span className="eyebrow">Risk scale</span>
          <h2>Text first, color second</h2>
          <p className="subtle">
            Every marker, segment, and checkpoint carries an accessible risk label. No Travel is
            never presented as a safe route.
          </p>
        </div>
        <RiskLegend />
      </section>

      <section className="panel method-brief">
        <span className="eyebrow">Method</span>
        <h2>How the recommendation is ordered</h2>
        <ol className="ranking-list">
          <li>Fewest No Travel miles</li>
          <li>Fewest Severe miles</li>
          <li>Fewest High miles</li>
          <li>Lowest average risk score</li>
          <li>Shortest travel time</li>
        </ol>
        <p className="subtle">
          If every alternative includes No Travel mileage, the least hazardous route is shown for
          context and explicitly marked <strong>not recommended for travel</strong>.
        </p>
      </section>
    </div>
  );
}
