import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { formatDay, money, pctLabel, roman } from "../format";
import type { ExposureRange, RunemarkFeedItem, TrialClaim, TrialResult } from "../types";
import { FactMark, TierMark } from "./Ornaments";
import { useSource } from "./SourcePanel";
import { EmptyState, LoadingRecord } from "./States";

/** Ports of the Runemark chart, placed as percentages of the plate. */
export interface Port {
  name: string;
  role: string;
  x: number;
  y: number;
}

export const PORTS: Port[] = [
  { name: "Solvar", role: "Gas terminal", x: 19.8, y: 29.6 },
  { name: "Ravik", role: "Rail link", x: 63.4, y: 22.4 },
  { name: "Ymir", role: "Locks", x: 40.2, y: 47.3 },
  { name: "Assgard", role: "Port", x: 74.5, y: 49.3 },
  { name: "Utgard", role: "Terminal", x: 39.0, y: 61.0 },
  { name: "Ketra", role: "Terminal", x: 48.6, y: 62.2 },
  { name: "Valhalla", role: "Inland hold", x: 54.7, y: 66.5 },
  { name: "Dorin", role: "Inland hold", x: 59.0, y: 79.0 },
  { name: "Orvan", role: "Grain port", x: 88.2, y: 68.4 },
  { name: "Midgard", role: "Harbour", x: 90.2, y: 47.6 },
  { name: "Tolan", role: "Harbour", x: 84.0, y: 77.6 },
  { name: "Vanir", role: "Rike port", x: 35.5, y: 89.3 },
];

const ALIASES: Record<string, string> = { asgard: "Assgard" };
const PORT_NAMES = new Map(PORTS.map((port) => [port.name.toLowerCase(), port.name]));

function canonical(name: string) {
  const key = name.trim().toLowerCase();
  return PORT_NAMES.get(key) ?? ALIASES[key] ?? name.trim();
}

function defaultPort(result: TrialResult) {
  const rows = result.briefing?.exposure ?? [];
  const ranked = [...rows].sort((a, b) => (b.odin_high ?? 0) - (a.odin_high ?? 0));
  const country = ranked[0]?.country ?? result.case_file.countries[0];
  return country ? canonical(country) : null;
}

export function RunemarkChart({ result }: { result: TrialResult }) {
  const [selected, setSelected] = useState<string | null>(() => defaultPort(result));
  const [feed, setFeed] = useState<RunemarkFeedItem[] | null>(null);
  const [feedError, setFeedError] = useState<string | null>(null);
  const dossierRef = useRef<HTMLElement>(null);
  const { open } = useSource();

  const choose = (name: string) => {
    const next = selected === name ? null : name;
    setSelected(next);
    if (!next) return;
    const stacked = window.matchMedia("(max-width: 900px)").matches;
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (stacked) {
      requestAnimationFrame(() =>
        dossierRef.current?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" }),
      );
    }
  };

  useEffect(() => {
    setSelected(defaultPort(result));
  }, [result.run_id]);

  useEffect(() => {
    let alive = true;
    setFeed(null);
    setFeedError(null);
    api
      .feed(result.run_id)
      .then((items) => alive && setFeed(items))
      .catch((reason: Error) => alive && setFeedError(reason.message));
    return () => {
      alive = false;
    };
  }, [result.run_id]);

  const run = result.runs[result.runs.length - 1];
  const claims = run?.claims ?? [];
  const exposure = result.briefing?.exposure ?? [];

  const record = useMemo(() => {
    const map = new Map<string, { claims: TrialClaim[]; exposure: ExposureRange[] }>();
    const ensure = (country: string) => {
      const key = canonical(country);
      if (!map.has(key)) map.set(key, { claims: [], exposure: [] });
      return map.get(key)!;
    };
    for (const country of result.case_file.countries) ensure(country);
    for (const row of exposure) ensure(row.country).exposure.push(row);
    for (const claim of claims) ensure(claim.country).claims.push(claim);
    return map;
  }, [result.case_file.countries, exposure, claims]);

  const documents = useMemo(() => {
    const map = new Map<string, RunemarkFeedItem[]>();
    for (const item of feed ?? []) {
      const key = canonical(item.country);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(item);
    }
    return map;
  }, [feed]);

  const selectedPort = PORTS.find((port) => port.name === selected) ?? null;
  const selectedClaims = selected ? record.get(selected)?.claims ?? [] : [];
  const selectedExposure = selected ? record.get(selected)?.exposure ?? [] : [];
  const selectedDocs = selected ? documents.get(selected) ?? [] : [];
  const citedHere = selectedClaims.length + selectedExposure.length > 0;
  const inCaseFile =
    Boolean(selected) && result.case_file.countries.some((country) => canonical(country) === selected);
  const corridor = Boolean(record.has("Orvan")) && (record.has("Midgard") || record.has("Tolan"));
  const routes = [
    { key: "orvan-midgard", path: "M88.2 68.4 Q91.6 58 90.2 47.6", ports: ["Orvan", "Midgard"], alt: false },
    { key: "orvan-tolan", path: "M88.2 68.4 Q86.4 73.2 84 77.6", ports: ["Orvan", "Tolan"], alt: false },
    { key: "orvan-ravik", path: "M88.2 68.4 Q74 48 63.4 22.4", ports: ["Orvan", "Ravik"], alt: true },
  ].filter((route) => route.ports.every((port) => record.has(port)));

  /* A selected port keeps its argued neighbours legible and lets the rest recede. */
  const related = useMemo(() => {
    if (!selected) return null;
    const set = new Set<string>([selected]);
    if (selected === "Orvan") {
      for (const name of ["Midgard", "Tolan", "Ravik"]) if (record.has(name)) set.add(name);
    }
    if (["Midgard", "Tolan", "Ravik"].includes(selected) && record.has("Orvan")) set.add("Orvan");
    return set;
  }, [selected, record]);

  return (
    <section className="chart-room">
      <header className="chart-head">
        <div>
          <span className="eyebrow">Chart of record</span>
          <h2 className="chart-title">Where the record touches Runemark</h2>
          <p className="chart-note">
            Twelve ports on the sealed chart. A filled mark is a place the trial argued over; a dashed ring is
            held in the archive but never cited. The numeral counts the documents held from that port. Choose a
            mark to read what the record says.
          </p>
        </div>
        <dl className="chart-tally">
          <div>
            <dt>Ports in record</dt>
            <dd className="mono">
              {record.size} <span>/ {PORTS.length}</span>
            </dd>
          </div>
          <div>
            <dt>Documents</dt>
            <dd className="mono">{feed ? feed.length : "—"}</dd>
          </div>
          <div>
            <dt>As of</dt>
            <dd className="mono">{formatDay(result.case_file.as_of)}</dd>
          </div>
        </dl>
      </header>

      <div className="chart-layout">
        <figure className="chart-plate">
          <div className="chart-frame">
            <img
              src="/chart/runemark-chart.jpg"
              alt="Runemark chart showing the inner and outer seas and twelve named ports."
              width={1600}
              height={1067}
            />
            <svg
              className="chart-svg"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              aria-hidden="true"
              focusable="false"
            >
              <g className="chart-sea" fill="none" stroke="var(--rule)" stroke-width="1">
                <path d="M0 0 H100 V100 H0 Z" />
                <path d="M6 0 L0 50 L100 50 Z" />
                <path d="M6 50 L0 100 L100 100 Z" />
              </g>
              <g className="chart-ports">
                {PORTS.map((port) => {
                  const held = record.get(port.name);
                  const docs = documents.get(port.name) ?? [];
                  const count = docs.length;
                  return (
                    <g key={port.name} className="chart-port-chart">
                      <circle cx={port.x} cy={port.y} r={0.62} fill="var(--gold)" stroke="var(--ink)" stroke-width={0.12} />
                      <text className="chart-port-label" x={port.x} y={port.y} textAnchor="middle" dy="0.3em" fill="var(--ink)">{port.name}</text>
                      {count > 0 && (
                        <text className="chart-port-count" x={port.x} y={port.y + 2.2} textAnchor="middle" fill="var(--primary)">{count}</text>
                      )}
                      {held && (
                        <g className="chart-port-claims" aria-label={` ${held.claims.length} claims`}>
                          {held.claims.length > 0 && (
                            <path
                              className="chart-rune"
                              d="M-1 -1 l2 2 M-1 1 l2 -2"
                              transform={`translate(${port.x} ${port.y})`}
                              fill="none"
                              stroke="var(--primary)"
                              stroke-width={0.28}
                            />
                          )}
                        </g>
                      )}
                    </g>
                  );
                })}
              </g>
              <g className="chart-routes" aria-hidden="true">
                {corridor ? routes.map((route) => {
                  return (
                    <>
                      <path className="route-halo" d={route.path} />
                      <path className={"route" + (route.alt ? " route-alt" : "")} d={route.path} />
                    </>
                  );
                }) : null}
              </g>
            </svg>
            <div className="chart-ports">
              {PORTS.map((port) => {
                const held = record.get(port.name);
                const docs = documents.get(port.name) ?? [];
                const state = held ? "record" : docs.length ? "archive" : "silent";
                const count = docs.length;
                const label =
                  state === "record"
                    ? `${docs.length} documents; ${held!.claims.length} claims and ${held!.exposure.length} exposure rows in this record`
                    : state === "archive"
                      ? `${docs.length} documents in the archive, not cited`
                      : "named on the chart, nothing in this record";
                return (
                  <button
                    key={port.name}
                    type="button"
                    className={`chart-port chart-port-${state}${selected === port.name ? " is-selected" : ""}${
                      related && !related.has(port.name) ? " is-dim" : ""
                    }`}
                    style={{ left: `${port.x}%`, top: `${port.y}%` }}
                    aria-pressed={selected === port.name}
                    aria-label={`${port.name}, ${port.role}: ${label}`}
                    onClick={() => choose(port.name)}
                  >
                    <span className="chart-port-dot" aria-hidden="true">
                      {count > 0 && <b>{count}</b>}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
          <figcaption>
            <span className="eyebrow">Runemark · plate II</span>
            Nothing outside the sealed corpus is plotted here.
            {corridor && (
              <span className="chart-legend-inline">
                Dashed: the Orvan corridor, and the rail substitution argued through Ravik.
              </span>
            )}
          </figcaption>
          <div className="chart-key">
            <span className="chart-key-item chart-key-record">
              <i aria-hidden="true" />
              In the record
            </span>
            <span className="chart-key-item chart-key-archive">
              <i aria-hidden="true" />
              Archive only
            </span>
            <span className="chart-key-item chart-key-silent">
              <i aria-hidden="true" />
              No dispatch
            </span>
          </div>
        </figure>

        <aside className="chart-dossier" ref={dossierRef} aria-live="polite">
          {selectedPort ? (
            <>
              <header className="dossier-head">
                <span className="eyebrow">Port dossier</span>
                <h3>{selectedPort.name}</h3>
                <p>
                  {selectedPort.role}
                  {citedHere
                    ? ` · argued in round ${roman(run?.run_number ?? 1)}`
                    : inCaseFile
                      ? " · named in the case file"
                      : selectedDocs.length > 0
                        ? " · in the archive, uncited"
                        : " · outside this record"}
                </p>
              </header>

              {selectedExposure.length > 0 && (
                <section className="dossier-section">
                  <h4>Exposure fixed</h4>
                  <ul className="dossier-ranges">
                    {selectedExposure.map((row) => (
                      <li key={`${row.country}-${row.sector}`}>
                        <span className="range-sector">{row.sector}</span>
                        <span className="range-value mono">
                          {money(row.odin_low, row.unit)} – {money(row.odin_high, row.unit)}
                        </span>
                        <span className="range-args">
                           Loki floor {money(row.loki_low, row.unit)} · Thor ceiling{" "}
                          {money(row.thor_high, row.unit)}
                        </span>
                        {row.confidence != null && (
                          <span className="range-confidence">
                            <span className="confidence-meter" aria-hidden="true">
                              <i style={{ width: pctLabel(row.confidence) }} />
                            </span>
                            {pctLabel(row.confidence)} confidence
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {selectedClaims.length > 0 && (
                <section className="dossier-section">
                  <h4>Claims on this port</h4>
                  <ul className="dossier-claims">
                    {selectedClaims.map((claim) => (
                      <li key={claim.id}>
                        <div className="claim-head">
                          <code>{claim.id}</code>
                          <FactMark nature={claim.nature} />
                        </div>
                        <span className="dossier-statement">{claim.statement}</span>
                        <span className="dossier-figure mono">
                          {claim.estimate == null ? "no estimate" : money(claim.estimate, claim.estimate_unit)}
                          {claim.status ? ` · ${claim.status}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <section className="dossier-section">
                <h4>Dispatches from this port</h4>
                {feedError ? (
                  <p className="dossier-note">The archive is not reachable in this session.</p>
                ) : !feed ? (
                  <LoadingRecord label="Opening the archive" rows={2} />
                ) : selectedDocs.length === 0 ? (
                  <p className="dossier-note">No document in the sealed corpus names {selectedPort.name}.</p>
                ) : (
                  <ul className="dossier-docs">
                    {selectedDocs.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          className="dispatch-title"
                          onClick={() =>
                            open({
                              runId: result.run_id,
                              sourceId: item.id,
                              fallback: {
                                id: item.id,
                                title: item.title,
                                excerpt: item.excerpt,
                                published_at: item.published_at,
                                source_name: item.source_name,
                                reliability: item.reliability,
                              },
                            })
                          }
                        >
                          {item.title}
                        </button>
                        <span className="doc-meta">
                          <TierMark tier={item.reliability} />
                          <span className="mono">{formatDay(item.published_at)}</span> {item.source_name}{" "}
                          <code>{item.id}</code>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {!citedHere && inCaseFile && (
                <p className="dossier-note">
                  Named in the case file
                  {result.case_file.event_id ? ` for ${result.case_file.event_id}` : ""} as the event's own ground.
                  Neither Thor nor Loki entered a claim here, so no ruling rests on it.
                </p>
              )}

              {!citedHere && !inCaseFile && (
                <EmptyState
                  compact
                  title={selectedDocs.length > 0 ? "In the archive, not in the case" : "Outside this record"}
                  note={
                    selectedDocs.length > 0
                      ? "Neither Thor nor Loki relied on this port. It is not part of the ruling."
                      : "Nothing in this record reaches this coast. The chart is the whole realm; the case is not."
                  }
                />
              )}
            </>
          ) : (
            <EmptyState
              compact
              title="Choose a port"
              note="Every mark on the chart opens the claims and dispatches attached to it."
            />
          )}
        </aside>
      </div>
    </section>
  );
}
