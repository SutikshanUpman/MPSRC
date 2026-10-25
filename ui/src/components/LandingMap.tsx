import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PORTS } from "./RunemarkChart";

const ROUTES = [
  { key: "orvan-midgard", label: "Orvan → Midgard", path: "M88.2 68.4 Q91.6 58 90.2 47.6", ports: ["Orvan", "Midgard"] },
  { key: "orvan-tolan", label: "Orvan → Tolan", path: "M88.2 68.4 Q86.4 73.2 84 77.6", ports: ["Orvan", "Tolan"] },
  { key: "orvan-ravik", label: "Orvan → Ravik", path: "M88.2 68.4 Q74 48 63.4 22.4", ports: ["Orvan", "Ravik"] },
] as const;

const PORT_NOTES: Record<string, string> = {
  Orvan: "The grain port at the heart of the corridor story.",
  Midgard: "A harbour whose exposure can be tested against the record.",
  Tolan: "A harbour on the southern route from Orvan.",
  Ravik: "The rail link used to examine substitution and rerouting.",
};

export function LandingMap() {
  const [selected, setSelected] = useState("Orvan");
  const [showRoutes, setShowRoutes] = useState(true);
  const selectedPort = useMemo(() => PORTS.find((port) => port.name === selected) ?? PORTS[0], [selected]);

  return (
    <section className="landing-section landing-map-section" id="map" aria-labelledby="landing-map-title">
      <div className="landing-section-head">
        <div>
          <span className="roman-kicker">III · the chart</span>
          <h2 id="landing-map-title">Start with the geography.</h2>
          <p>
            Select a port to see its place in the record. The live workspace adds documents, claims and exposure
            ranges when a case is opened.
          </p>
        </div>
        <button className="map-toggle" type="button" aria-pressed={showRoutes} onClick={() => setShowRoutes((value) => !value)}>
          <span className="map-toggle-mark" aria-hidden="true" />
          {showRoutes ? "Hide corridor lines" : "Show corridor lines"}
        </button>
      </div>

      <div className="landing-map-layout">
        <figure className="landing-map-plate">
          <div className="landing-map-frame">
            <img
              src="/chart/runemark-chart.jpg"
              alt="Runemark chart with twelve named ports."
              width={1600}
              height={1067}
            />
            <svg className="landing-map-routes" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {showRoutes &&
                ROUTES.map((route) => {
                  const active = route.ports.some((port) => port === selectedPort.name);
                  return (
                    <g key={route.key} className={active ? "is-active" : ""}>
                      <path className="landing-route-halo" d={route.path} />
                      <path className="landing-route" d={route.path} />
                    </g>
                  );
                })}
            </svg>
            <div className="landing-map-pins">
              {PORTS.map((port) => (
                <button
                  key={port.name}
                  type="button"
                  className={`landing-map-pin${selectedPort.name === port.name ? " is-selected" : ""}`}
                  style={{ left: `${port.x}%`, top: `${port.y}%` }}
                  aria-pressed={selectedPort.name === port.name}
                  aria-label={`${port.name}, ${port.role}`}
                  onClick={() => setSelected(port.name)}
                >
                  <span className="landing-map-pin-dot" aria-hidden="true" />
                  <span className="landing-map-pin-label">{port.name}</span>
                </button>
              ))}
            </div>
          </div>
          <figcaption>
            <span className="roman-kicker">Runemark · plate II</span>
            A living map for orientation; the sealed corpus remains the source of truth.
          </figcaption>
        </figure>

        <aside className="landing-map-dossier" aria-live="polite">
          <span className="roman-kicker">Selected port</span>
          <h3>{selectedPort.name}</h3>
          <p className="landing-map-role">{selectedPort.role}</p>
          <p>{PORT_NOTES[selectedPort.name] ?? "A named place on the Runemark chart."}</p>
          <dl>
            <div>
              <dt>Chart position</dt>
              <dd className="mono">{selectedPort.x.toFixed(1)}° · {selectedPort.y.toFixed(1)}°</dd>
            </div>
            <div>
              <dt>Available in</dt>
              <dd>Live case records</dd>
            </div>
          </dl>
          <Link className="text-link" to="/app">
            Open the console <span aria-hidden="true">↗</span>
          </Link>
        </aside>
      </div>
    </section>
  );
}
