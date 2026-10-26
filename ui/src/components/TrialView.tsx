import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { api } from "../api";
import { agentShort } from "../agents";
import { compactNumber, formatDay, formatMoment, money, moneyTitle, pctLabel, roman } from "../format";
import type {
  ExposureRange,
  RunemarkFeedItem,
  TrialChallenge,
  TrialCitation,
  TrialClass,
  TrialClaim,
  TrialResult,
  TrialRun,
} from "../types";
import { DispatchTimeline, quarterOf } from "./DispatchTimeline";
import { ExposurePlot } from "./ExposurePlot";
import { AgentLabel, FactMark, SectionHead, TierMark } from "./Ornaments";
import { RulingComposition } from "./RulingComposition";
import { RunemarkChart } from "./RunemarkChart";
import { useSource } from "./SourcePanel";
import { DamagedNotice, EmptyState, LoadingRecord, UnchallengedNote } from "./States";

/** A run is sufficient, sent back by Odin, or (the last run) stopped by the run limit with its gaps flagged. */
function runState(run: TrialRun): string {
  if (run.sufficient) return "sufficient";
  return run.returned_by_odin ? "returned for evidence" : "run limit reached · gaps flagged";
}

const TABS = ["Briefing", "Case File", "Runemark map", "Document feed", "Trial", "Exposure", "Audit"] as const;
type Tab = (typeof TABS)[number];

export function TrialView({ result, onReplay }: { result: TrialResult; onReplay?: () => void }) {
  const [tab, setTab] = useState<Tab>(() => {
    const wanted = new URLSearchParams(window.location.search).get("tab");   // deep link: /app?run=<id>&tab=Exposure
    return (TABS as readonly string[]).includes(wanted ?? "") ? (wanted as Tab) : "Briefing";
  });
  const navRef = useRef<HTMLElement>(null);
  const briefing = result.briefing;
  const exposureCount = briefing?.exposure.length ?? 0;
  const issueCount = new Set([...result.issues, ...result.case_file.issues]).size;
  const certified = result.status === "completed" && briefing?.complete === true;

  const move = (event: KeyboardEvent<HTMLElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const index = TABS.indexOf(tab);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? TABS.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + TABS.length) % TABS.length;
    setTab(TABS[next]);
    navRef.current?.querySelectorAll<HTMLButtonElement>("[role=tab]")[next]?.focus();
  };

  return (
    <article className="trial" aria-labelledby="case-question">
      <header className="case-head">
        <span className="eyebrow">
          Trial of the Nine Realms · case {result.case_file.event_id ?? "unfiled"}
          {result.case_file.event_name ? ` · ${result.case_file.event_name}` : ""}
        </span>
        <h1 className="case-question" id="case-question">
          {result.question}
        </h1>
        <div className="case-actions">
          {onReplay && (
            <button type="button" className="btn btn-quiet" onClick={onReplay} title="Re-runs this trial from its recorded model calls: $0, byte-identical">
              Replay at $0
            </button>
          )}
        </div>
        <dl className="case-meta">
          <div>
            <dt>As of</dt>
            <dd className="mono">{formatDay(result.case_file.as_of)}</dd>
          </div>
          <div>
            <dt>Runs</dt>
            <dd className="mono">{roman(result.runs.length)} / II</dd>
          </div>
          <div>
            <dt>Documents</dt>
            <dd className="mono">{result.case_file.relevant_source_ids.length}</dd>
          </div>
          <div>
            <dt>Corpus</dt>
            <dd className="mono">{result.case_file.corpus_pack}</dd>
          </div>
          <div>
            <dt>State</dt>
            <dd>{result.status}</dd>
          </div>
        </dl>
      </header>

      <Posture result={result} certified={certified} issueCount={issueCount} onAudit={() => setTab("Audit")} />

      <nav className="tabs" aria-label="Trial record" role="tablist" ref={navRef} onKeyDown={move}>
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            id={`tab-${name.replace(/\s/g, "-")}`}
            aria-selected={tab === name}
            aria-controls="tab-panel"
            tabIndex={tab === name ? 0 : -1}
            className={tab === name ? "is-active" : ""}
            onClick={() => setTab(name)}
          >
            {name}
            {name === "Exposure" && exposureCount > 0 && <span className="tab-count mono">{exposureCount}</span>}
          </button>
        ))}
      </nav>

      <div className="tab-panel" id="tab-panel" role="tabpanel" aria-labelledby={`tab-${tab.replace(/\s/g, "-")}`}>
        {tab === "Briefing" && <BriefingView result={result} certified={certified} />}
        {tab === "Case File" && <CaseFileView result={result} />}
        {tab === "Runemark map" && <RunemarkChart result={result} />}
        {tab === "Document feed" && <DispatchesView runId={result.run_id} asOf={result.case_file.as_of} />}
        {tab === "Trial" && <TrialRecordView result={result} />}
        {tab === "Exposure" && <ExposureView result={result} />}
        {tab === "Audit" && <AuditView result={result} onReplay={onReplay} />}
      </div>
    </article>
  );
}

/* ---------------------------------------------------------------- posture */

function Posture({
  result,
  certified,
  issueCount,
  onAudit,
}: {
  result: TrialResult;
  certified: boolean;
  issueCount: number;
  onAudit: () => void;
}) {
  return (
    <section className={`posture ${certified ? "posture-certified" : "posture-open"}`} aria-label="Evidence posture">
      <div className="posture-main">
        <span className="eyebrow">Evidence posture</span>
        <strong>{certified ? "Certified record" : "Uncertified record"}</strong>
        <p>
          {result.case_file.event_verified
            ? "The event is verified against the Runemark corpus."
            : "The event could not be fully verified from the Runemark corpus."}
        </p>
      </div>
      <dl className="posture-facts">
        <div>
          <dt>Sources</dt>
          <dd className="mono">{result.case_file.relevant_source_ids.length}</dd>
        </div>
        <div>
          <dt>Issues</dt>
          <dd className="mono">{issueCount}</dd>
        </div>
      </dl>
      <button type="button" className="btn btn-quiet" onClick={onAudit}>
        Review audit
      </button>
    </section>
  );
}

/* --------------------------------------------------------------- briefing */

function BriefingView({ result, certified }: { result: TrialResult; certified: boolean }) {
  const briefing = result.briefing;
  if (!briefing) {
    return (
      <EmptyState
        title="No briefing was issued"
        note="Odin did not issue a final briefing. This record is not certified for decision-making. The case file and the trial record remain readable."
      />
    );
  }
  const rulings = result.runs.reduce((total, run) => total + run.rulings.length, 0);

  return (
    <div className="stack">
      <section className="brief">
        <div className="brief-main">
          <SectionHead
            kicker="Executive briefing"
            title="What the record supports"
            aside={<AgentLabel agent="odin" compact />}
          />
          <p className="brief-text">{briefing.executive_summary}</p>
          <BriefingNotices briefing={briefing} />
          <p className="brief-note">
            {certified
              ? "Drawn only from Odin's rulings, not from Thor's or Loki's raw argument."
              : "This briefing is provisional: the full sufficiency protocol was not certified."}
          </p>
        </div>
        <dl className="brief-facts">
          <div>
            <dt>Runs</dt>
            <dd>{roman(result.runs.length)}</dd>
          </div>
          <div>
            <dt>Rulings</dt>
            <dd>{rulings}</dd>
          </div>
          <div>
            <dt>Sources</dt>
            <dd>{result.case_file.relevant_source_ids.length}</dd>
          </div>
          <div>
            <dt>As of</dt>
            <dd className="mono">{formatDay(result.case_file.as_of)}</dd>
          </div>
        </dl>
      </section>

      <VerdictSection result={result} />

      {briefing.exposure.length > 0 && (
        <section>
          <SectionHead
            kicker="Exposure · country by sector"
            title="Ranges Odin fixed"
            note="Low and high are Odin's range. The bar is drawn on a shared scale across the rows."
          />
          <ExposurePlot rows={briefing.exposure} />
          <ExposureTable rows={briefing.exposure} runId={result.run_id} result={result} />
        </section>
      )}

      <section className="rulings-ledger">
        <SectionHead kicker="Ruling ledger" title="Every claim, as classified" />
        <RulingComposition
          counts={{
            established: briefing.established.length,
            contested: briefing.contested.length,
            conceded: briefing.conceded.length,
            rejected: briefing.rejected.length,
          }}
        />
        <div className="vg-grid">
          <RulingGroup tone="established" items={briefing.established} />
          <RulingGroup tone="contested" items={briefing.contested} />
          <RulingGroup tone="conceded" items={briefing.conceded} />
        </div>
        <RulingGroup tone="rejected" items={briefing.rejected} wide />
      </section>

      <div className="columns-2">
        {briefing.outlook && (
          <section className="prose-block">
            <SectionHead kicker="Next quarter" title="Outlook" as="div" />
            <p>{briefing.outlook}</p>
          </section>
        )}
        {briefing.assumptions.length > 0 && (
          <section className="prose-block prose-block-ruled">
            <SectionHead kicker="Standing assumptions" title="What the range rests on" as="div" />
            <ul className="assumption-list">
              {briefing.assumptions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {briefing.citations.length > 0 && (
        <section>
          <SectionHead kicker="Sealed sources" title="Citations behind the ruling" />
          <ul className="cite-list">
            {briefing.citations.map((citation) => (
              <li key={citation.locator}>
                <Citation citation={citation} runId={result.run_id} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

const TONE_LABEL: Record<TrialClass, string> = {
  established: "Established",
  contested: "Contested",
  conceded: "Conceded",
  rejected: "Rejected",
};

function RulingGroup({ tone, items, wide }: { tone: TrialClass; items: string[]; wide?: boolean }) {
  return (
    <section className={`vg vg-${tone}${wide ? " vg-wide" : ""}`} aria-label={TONE_LABEL[tone]}>
      <header className="vg-head">
        <span className={`ruling-mark rm-${tone}`} aria-hidden="true" />
        <h3>{TONE_LABEL[tone]}</h3>
        <span className="vg-count mono">{String(items.length).padStart(2, "0")}</span>
      </header>
      {items.length === 0 ? (
        <p className="vg-none">None entered.</p>
      ) : (
        <ul className="vg-items">
          {items.map((item, index) => (
            <li key={`${tone}-${index}`}>
              <span className="vg-index mono" aria-hidden="true">
                {tone === "established" ? String(index + 1).padStart(2, "0") : tone === "conceded" ? "(" : "—"}
              </span>
              <span className="vg-text">{item}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ---------------------------------------------------------------- exposure */

function ExposureTable({ rows, runId, result }: { rows: ExposureRange[]; runId: string; result?: TrialResult }) {
  const { open } = useSource();
  const values = rows.flatMap((row) => [row.loki_low, row.thor_high, row.odin_low, row.odin_high]);
  const max = Math.max(...values.filter((value): value is number => value != null && Number.isFinite(value)), 0);
  const position = (value: number | null) => (value == null || max <= 0 ? 0 : Math.min(100, (value / max) * 100));

  return (
    <>
      <div className="table-scroll">
        <table className="exposure">
        <thead>
          <tr>
            <th scope="col">Country</th>
            <th scope="col">Sector</th>
            <th scope="col" className="num">
              Low
            </th>
            <th scope="col" className="num">
              High
            </th>
            <th scope="col">Range</th>
            <th scope="col" className="num">
              Net shortfall
            </th>
            <th scope="col" className="num">
              Volume
            </th>
            <th scope="col" className="num">
              Confidence
            </th>
            <th scope="col">Period</th>
            <th scope="col">Evidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const low = row.odin_low ?? row.loki_low;
            const high = row.odin_high ?? row.thor_high;
            const left = position(low);
            const width = Math.max(0, position(high) - left);
            return (
              <tr key={`${row.country}-${row.sector}`}>
                <th scope="row">{row.country}</th>
                <td>{row.sector}</td>
                <td className="num" title={moneyTitle(row.odin_low ?? row.loki_low, row.unit)}>
                  {row.status === "ASSESSED" ? money(low, row.unit) : <span className="muted">insufficient evidence</span>}
                </td>
                <td className="num" title={moneyTitle(row.odin_high ?? row.thor_high, row.unit)}>
                  {row.status === "ASSESSED" ? money(high, row.unit) : "—"}
                </td>
                <td>
                  <span
                    className="rangebar"
                    role="img"
                    aria-label={`Range ${money(low, row.unit)} to ${money(high, row.unit)}`}
                  >
                    <span className="rangebar-track" aria-hidden="true" />
                    <span className="rangebar-span" style={{ left: `${left}%`, width: `${width}%` }} aria-hidden="true" />
                    {row.loki_low != null && (
                      <span className="rangebar-tick" style={{ left: `${position(row.loki_low)}%` }} aria-hidden="true" />
                    )}
                    {row.thor_high != null && (
                      <span className="rangebar-tick" style={{ left: `${position(row.thor_high)}%` }} aria-hidden="true" />
                    )}
                  </span>
                </td>
                <td className="num">{row.pct_low == null ? "—" : `${row.pct_low}% to ${row.pct_high}%`}</td>
                <td className="num">
                  {row.volume_low == null ? "—" : `${compactNumber(row.volume_low)} to ${compactNumber(row.volume_high ?? 0)} ${row.volume_unit ?? ""}`}
                </td>
                <td className="num">{row.confidence == null ? "—" : pctLabel(row.confidence)}</td>
                <td className="muted exposure-period">{row.period ?? "next quarter"}</td>
                <td>
                  <span className="cite-inline">
                    {row.citation_ids.slice(0, 4).map((id) => (
                      <button
                        key={id}
                        type="button"
                        className="cite cite-id"
                        aria-label={`Open source ${id}`}
                        onClick={() => open({ runId, sourceId: id })}
                      >
                        <code>{id}</code>
                      </button>
                    ))}
                    {row.citation_ids.length > 4 && <span className="muted small">+{row.citation_ids.length - 4} more, under the cell</span>}
                    {row.citation_ids.length === 0 && <span className="muted small">none</span>}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
        </table>
        <p className="table-note">
          Ticks mark Thor's and Loki's argued bounds (Loki floor, Thor ceiling). Unit: {rows[0]?.unit ?? "USD"}.
        </p>
      </div>
      <p className="table-hint">Swipe the table sideways for confidence, period and evidence.</p>
      {result && <CellDrill rows={rows} result={result} runId={runId} />}
    </>
  );
}

function ExposureView({ result }: { result: TrialResult }) {
  const rows = result.briefing?.exposure ?? [];
  const assumptions = Array.from(new Set(rows.flatMap((row) => row.assumptions)));
  if (rows.length === 0) {
    return (
      <EmptyState
        title="No range was fixed"
          note="Odin accepted no bounded range from this record. Read the rulings to see which claims failed."
      />
    );
  }
  return (
    <div className="stack">
      <section>
        <SectionHead
          kicker="Exposure · country by sector"
          title="Ranges Odin fixed"
          note="Numerals are Odin's range, right-aligned for comparison. The bar shares one scale."
        />
        <ExposurePlot rows={rows} />
        <ExposureTable rows={rows} runId={result.run_id} result={result} />
      </section>
      {assumptions.length > 0 && (
        <section className="prose-block prose-block-ruled">
          <SectionHead kicker="Standing assumptions" title="What the ranges rest on" as="div" />
          <ul className="assumption-list">
            {assumptions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- case file */

function CaseFileView({ result }: { result: TrialResult }) {
  const c = result.case_file;
  return (
    <div className="stack">
      <section className="casefile">
        <div>
          <SectionHead
            kicker="The case file"
            title={c.event_name ?? c.event_id ?? "Unfiled event"}
            aside={<AgentLabel agent="heimdall" compact />}
          />
          <p className="casefile-text">{c.verification_summary || "No verification summary was filed."}</p>
          <p className={`verify-line ${c.event_verified ? "verify-ok" : "verify-warn"}`}>
            {c.event_verified ? "Event verified against the corpus." : "Event not fully verified."}
          </p>
        </div>
        <dl className="casefile-facts">
          <div>
            <dt>Event</dt>
            <dd className="mono">{c.event_id ?? "—"}</dd>
          </div>
          <div>
            <dt>Corpus</dt>
            <dd className="mono">
              {c.corpus_pack} · {c.corpus_version}
            </dd>
          </div>
          <div>
            <dt>As of</dt>
            <dd className="mono">{formatDay(c.as_of)}</dd>
          </div>
          <div>
            <dt>Source pool</dt>
            <dd className="mono">{c.relevant_source_ids.length} documents</dd>
          </div>
          <div>
            <dt>Countries</dt>
            <dd>{c.countries.length ? c.countries.join(" · ") : "—"}</dd>
          </div>
          <div>
            <dt>Sectors</dt>
            <dd>{c.sectors.length ? c.sectors.join(" · ") : "—"}</dd>
          </div>
        </dl>
      </section>

      {c.contradictions.length > 0 && (
        <section>
          <SectionHead kicker="Contradictions" title="Where the corpus disagrees with itself" />
          <ul className="ruled-list">
            {c.contradictions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {c.assumptions.length > 0 && (
        <section className="prose-block prose-block-ruled">
          <SectionHead kicker="Case assumptions" title="Read in before the trial" as="div" />
          <ul className="assumption-list">
            {c.assumptions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      <DamagedNotice title="Excluded documents and damaged items" items={c.issues} />
    </div>
  );
}

/* --------------------------------------------------------------- dispatches */

function DispatchesView({ runId, asOf }: { runId: string; asOf: string }) {
  const [items, setItems] = useState<RunemarkFeedItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sourceType, setSourceType] = useState("all");
  const [period, setPeriod] = useState<string | null>(null);
  const { open } = useSource();

  useEffect(() => {
    let alive = true;
    setItems(null);
    setError(null);
    api
      .feed(runId)
      .then((feed) => alive && setItems(feed))
      .catch((reason: Error) => alive && setError(reason.message));
    return () => {
      alive = false;
    };
  }, [runId]);

  if (error)
    return (
      <EmptyState
        title="The archive is not readable"
        note={`The corpus could not be opened in this session. ${error}`}
      />
    );
  if (!items) return <LoadingRecord label="Opening the sealed archive" rows={6} />;
  if (items.length === 0)
    return (
      <EmptyState
        title="No document admitted"
        note={`Nothing in the corpus is dated on or before ${formatDay(asOf)}. The as-of date closes the record.`}
      />
    );

  const sourceTypes = Array.from(new Set(items.map((item) => item.source_type))).sort();
  const normalizedQuery = query.trim().toLowerCase();
  const ordered = [...items].sort((a, b) => b.published_at.localeCompare(a.published_at));
  const filtered = ordered.filter((item) => {
    const matchesType = sourceType === "all" || item.source_type === sourceType;
    const matchesPeriod = !period || quarterOf(item.published_at) === period;
    const haystack = `${item.id} ${item.title} ${item.source_name} ${item.country} ${item.sector} ${item.excerpt}`.toLowerCase();
    return matchesType && matchesPeriod && (!normalizedQuery || haystack.includes(normalizedQuery));
  });

  return (
    <section className="dispatches">
      <SectionHead
        kicker="The archive"
        title={`Documents available as of ${formatDay(asOf)}`}
        note="Most recent first. Nothing after the as-of date is admitted."
        aside={
          <span className="mono sec-count">
            {filtered.length}/{items.length}
          </span>
        }
      />
      <DispatchTimeline items={items} period={period} onPeriod={setPeriod} />
      <div className="dispatch-controls" role="search" aria-label="Filter dispatches">
        <label>
          <span className="sr-only">Search dispatches</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search title, country, sector, source"
          />
        </label>
        <label>
          <span className="sr-only">Filter by source type</span>
          <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
            <option value="all">All source types</option>
            {sourceTypes.map((type) => (
              <option key={type} value={type}>
                {type.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title={period ? "No dispatch in this quarter" : "No dispatch matches"}
          note="Clear the month, broaden the search, or reset the source filter."
          compact
        />
      ) : (
        <ol className="dispatch-list">
          {filtered.map((item) => (
            <li key={item.id} className="dispatch">
              <span className="dispatch-date mono">{formatDay(item.published_at)}</span>
              <TierMark tier={item.reliability} />
              <button
                type="button"
                className="dispatch-title"
                onClick={() =>
                  open({
                    runId,
                    sourceId: item.id,
                    fallback: { id: item.id, title: item.title, excerpt: item.excerpt, published_at: item.published_at, source_name: item.source_name, reliability: item.reliability },
                  })
                }
              >
                {item.title}
              </button>
              <span className="dispatch-id mono">{item.id}</span>
              <span className="dispatch-source">
                {item.source_name} · {item.source_type.replace(/_/g, " ")} · {item.country} · {item.sector}
              </span>
              <span className="dispatch-excerpt">{item.excerpt}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------- trial */

function TrialRecordView({ result }: { result: TrialResult }) {
  const last = Math.max(0, result.runs.length - 1);
  const [round, setRound] = useState(last);
  useEffect(() => setRound(last), [last, result.run_id]);
  const run = result.runs[Math.min(round, last)] as TrialRun | undefined;
  const claims = useMemo(() => run?.claims ?? [], [run]);
  const claimsById = useMemo(() => new Map(claims.map((claim) => [claim.id, claim])), [claims]);

  if (!run) return <EmptyState title="No run recorded" note="This case filed no trial run." />;

  const thor = claims.filter((claim) => claim.side === "thor");
  const loki = claims.filter((claim) => claim.side === "loki");
  const attacked = new Set(run.challenges.map((challenge) => claimsById.get(challenge.target_claim_id)?.side));
  const thorUnchallenged = thor.length > 0 && !attacked.has("thor");
  const lokiUnchallenged = loki.length > 0 && !attacked.has("loki");

  return (
    <div className="trial-record">
      {result.runs.length > 1 && (
        <div className="round-picker" role="group" aria-label="Trial run">
          {result.runs.map((item, index) => (
            <button
              key={item.run_number}
              type="button"
              className={index === round ? "is-active" : ""}
              onClick={() => setRound(index)}
              aria-pressed={index === round}
            >
              <span className="mono">{roman(item.run_number)}</span>
              <span>
                Run {roman(item.run_number)}
                <em className="mono">
                  {item.claims.length} claims · {item.query_count} searches
                </em>
              </span>
              <span className="round-state">{item.sufficient ? "sufficient" : item.returned_by_odin ? "returned" : "limit reached"}</span>
            </button>
          ))}
        </div>
      )}

      <dl className="round-facts">
        <div>
          <dt>Claims</dt>
          <dd>{claims.length}</dd>
        </div>
        <div>
          <dt>Searches</dt>
          <dd>{run.query_count}</dd>
        </div>
        <div>
          <dt>New evidence families</dt>
          <dd>{run.run_number === 2 ? run.new_evidence_families.length : "—"}</dd>
        </div>
        <div>
          <dt>Challenges</dt>
          <dd>{run.challenges.length}</dd>
        </div>
        <div>
          <dt>Rulings</dt>
          <dd>{run.rulings.length}</dd>
        </div>
        <div>
          <dt>Record</dt>
          <dd>{runState(run)}</dd>
        </div>
      </dl>

      <div className="advocates">
        <CounselColumn
          runId={result.run_id}
          side="thor"
          claims={thor}
          unchallenged={thorUnchallenged}
        />
        <CounselColumn
          runId={result.run_id}
          side="loki"
          claims={loki}
          unchallenged={lokiUnchallenged}
        />
      </div>

      <section className="bench">
        <SectionHead
          kicker="Odin · rulings"
          title="Odin's rulings, this run"
          aside={<AgentLabel agent="odin" compact />}
        />
        {run.rulings.length === 0 ? (
          <p className="bench-empty">No ruling was entered in this run.</p>
        ) : (
          <ul className="bench-list">
            {run.rulings.map((ruling) => (
              <li key={ruling.claim_id} className="ruling">
                <span className={`ruling-mark rm-${ruling.classification}`} aria-hidden="true" />
                <div>
                  <div className="ruling-head">
                    <code>{ruling.claim_id}</code>
                    <span className={`ruling-word rw-${ruling.classification}`}>{ruling.classification}</span>
                    <FactMark nature={ruling.nature} />
                  </div>
                  <p className="ruling-body">{ruling.rationale}</p>
                  {ruling.missing_evidence.length > 0 && (
                    <p className="ruling-missing">Missing: {ruling.missing_evidence.join("; ")}</p>
                  )}
                  {ruling.citations.length > 0 && (
                    <ul className="cite-inline">
                      {ruling.citations.map((citation) => (
                        <li key={citation.locator}>
                          <Citation citation={citation} runId={result.run_id} />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="examination">
        <SectionHead
          kicker="Cross-examination"
          title="Attacks, defences and concessions"
          note="Each challenge names the claim it attacks and the document it relies on."
        />
        {run.challenges.length === 0 ? (
          <p className="bench-empty">No challenge was recorded in this run.</p>
        ) : (
          <ol className="challenge-list">
            {run.challenges.map((challenge) => (
              <ChallengeEntry
                key={challenge.id}
                challenge={challenge}
                claimsById={claimsById}
                runId={result.run_id}
              />
            ))}
          </ol>
        )}
      </section>

      {run.run_number === 2 && (
        <section className="prose-block prose-block-ruled">
          <SectionHead kicker="Run II" title="What the send-back found" as="div" />
          {run.new_evidence_families.length > 0 ? (
            <p>
              Heimdall's targeted re-search found {run.new_evidence_families.length} evidence families nobody had
              retrieved in Run I ({run.new_evidence_families.join(", ")}).
            </p>
          ) : (
            <p>{run.no_new_evidence_reason ?? "Run II found no new evidence."}</p>
          )}
          {run.missing_evidence.length > 0 && (
            <ul className="assumption-list">
              {run.missing_evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      <DamagedNotice title="Run errors" items={run.errors} />
    </div>
  );
}

function CounselColumn({
  runId,
  side,
  claims,
  unchallenged,
}: {
  runId: string;
  side: "thor" | "loki";
  claims: TrialClaim[];
  unchallenged: boolean;
}) {
  const high = side === "thor";
  return (
    <article className="counsel">
      <header className="counsel-head">
        <AgentLabel agent={high ? "thor" : "loki"} />
        <span className="counsel-count mono">{claims.length} claims</span>
      </header>
      {claims.length === 0 && <p className="counsel-empty">No claims were entered.</p>}
      <div className="claim-list">
        {claims.map((claim) => (
          <ClaimCard key={claim.id} claim={claim} runId={runId} />
        ))}
      </div>
      {unchallenged && (
        <UnchallengedNote>
          No challenge was entered against this side this run. Its claims stand as argued, not as tested.
        </UnchallengedNote>
      )}
    </article>
  );
}

function ClaimCard({ claim, runId }: { claim: TrialClaim; runId: string }) {
  return (
    <article className="claim">
      <div className="claim-head">
        <code>{claim.id}</code>
        <FactMark nature={claim.nature} />
        {claim.status && <span className={`ruling-word rw-${claim.status}`}>{claim.status}</span>}
        {claim.claim_status !== "submitted" && (
          <span className="ruling-word rw-contested">
            {claim.claim_status}
            {claim.superseded_by ? ` → ${claim.superseded_by}` : ""}
          </span>
        )}
        {claim.supersedes && <span className="muted small">updates {claim.supersedes}</span>}
      </div>
      <p className="claim-text">{claim.statement}</p>
      <div className="claim-figures">
        <span className="claim-estimate mono">
          {claim.estimate_low != null
            ? `${claim.estimate_low}% to ${claim.estimate_high}%`
            : claim.estimate_status && claim.estimate_status !== "ESTIMATED"
              ? claim.estimate_status.replace(/_/g, " ").toLowerCase()
              : claim.estimate != null
                ? money(claim.estimate, claim.estimate_unit)
                : "no estimate"}
        </span>
        <span className="claim-meta">
          {claim.country} · {claim.sector}
          {claim.period ? ` · ${claim.period}` : ""}
          {claim.confidence != null ? ` · confidence ${pctLabel(claim.confidence)}` : ""}
        </span>
      </div>
      {claim.citations.length > 0 && (
        <ul className="cite-inline">
          {claim.citations.map((citation) => (
            <li key={`${claim.id}-${citation.locator}`}>
              <Citation citation={citation} runId={runId} />
            </li>
          ))}
        </ul>
      )}
      {claim.assumptions.length > 0 && <p className="claim-assumes">Assumes: {claim.assumptions.join("; ")}</p>}
      {claim.ruling_rationale && <p className="claim-ruling">{claim.ruling_rationale}</p>}
    </article>
  );
}

function ChallengeEntry({
  challenge,
  claimsById,
  runId,
}: {
  challenge: TrialChallenge;
  claimsById: Map<string, TrialClaim>;
  runId: string;
}) {
  const target = claimsById.get(challenge.target_claim_id);
  return (
    <li className="challenge">
      <div className="challenge-head">
        <code>{challenge.id}</code>
        <span className={`attacker attacker-${challenge.attacker}`}>
          {agentShort(challenge.attacker)} attacks
        </span>
        <span className="muted small">{challenge.kind.replace(/_/g, " ").toLowerCase()}</span>
        <span className={`ruling-word rw-${challenge.concedes ? "conceded" : "contested"}`}>
          {challenge.concedes ? "conceded" : challenge.outcome}
        </span>
        <span className="challenge-target-id mono">→ {challenge.target_claim_id}</span>
      </div>
      {target && <p className="challenge-target">“{target.statement}”</p>}
      <p className="challenge-argument">{challenge.argument}</p>
      {challenge.citations.length > 0 && (
        <ul className="cite-inline">
          {challenge.citations.map((citation) => (
            <li key={citation.locator}>
              <Citation citation={citation} runId={runId} />
            </li>
          ))}
        </ul>
      )}
      {challenge.response && (
        <div className={`defence ${challenge.concedes ? "defence-conceded" : ""}`}>
          <span className="eyebrow">{challenge.concedes ? "Concession" : "Defence"}</span>
          <p>{challenge.response}</p>
          {challenge.response_citations.length > 0 && (
            <ul className="cite-inline">
              {challenge.response_citations.map((citation) => (
                <li key={citation.locator}>
                  <Citation citation={citation} runId={runId} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

/* ------------------------------------------------------------------- audit */

function AuditView({ result, onReplay }: { result: TrialResult; onReplay?: () => void }) {
  return (
    <div className="stack">
      <section className="rounds">
        <SectionHead
          kicker="Execution trace"
          title="The two bounded runs"
          note="A thin record is returned once. Run 2 must bring new retrieval, or the cell is flagged INSUFFICIENT_EVIDENCE."
        />
        {result.runs.map((run) => (
          <article className="round-card" key={run.run_number}>
            <span className="round-seal mono">{roman(run.run_number)}</span>
            <div>
              <div className="round-head">
                <h4>Trial run {roman(run.run_number)}</h4>
                <span className={`round-state ${run.sufficient ? "ok" : "open"}`}>
                  {runState(run)}
                </span>
              </div>
              <dl className="round-dl">
                <div>
                  <dt>Claims</dt>
                  <dd>{run.claims.length}</dd>
                </div>
                <div>
                  <dt>Queries</dt>
                  <dd>{run.query_count}</dd>
                </div>
                <div>
                  <dt>New retrievals</dt>
                  <dd>{run.new_evidence_ids.length}</dd>
                </div>
                <div>
                  <dt>Rulings</dt>
                  <dd>{run.rulings.length}</dd>
                </div>
                <div>
                  <dt>Started</dt>
                  <dd className="mono">{formatMoment(run.started_at)}</dd>
                </div>
              </dl>
              {run.missing_evidence.length > 0 && (
                <p className="round-missing">Missing evidence: {run.missing_evidence.join("; ")}</p>
              )}
              <DamagedNotice title="Run errors" items={run.errors} />
            </div>
          </article>
        ))}
      </section>

      <section>
        <SectionHead kicker="Private memory" title="What Thor and Loki carried forward" />
        {result.memory_audit.length === 0 ? (
          <p className="bench-empty">No memory events were recorded.</p>
        ) : (
          <ul className="memory-list">
            {result.memory_audit.map((item, index) => (
              <li key={`${item.timestamp}-${index}`}>
                <span className="memory-agent">
                  <AgentLabel agent={item.agent} compact />
                </span>
                <code>{item.action}</code>
                <span className="memory-key mono">{item.key}</span>
                {item.value && <span className="memory-value">{item.value}</span>}
                {item.influenced_action && (
                  <span className="memory-influence">influenced: {item.influenced_action}</span>
                )}
                <span className="mono memory-time">{formatMoment(item.timestamp)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <AcceptanceFacts result={result} onReplay={onReplay} />
      <TrapReportView result={result} />

      <dl className="facts">
        <div>
          <dt>Calls</dt>
          <dd>{result.usage.calls}</dd>
        </div>
        <div>
          <dt>Tokens in</dt>
          <dd>{result.usage.input_tokens.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Tokens out</dt>
          <dd>{result.usage.output_tokens.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Latency</dt>
          <dd>{result.usage.latency_s.toFixed(1)}s</dd>
        </div>
        <div>
          <dt>Cost</dt>
          <dd>
            {result.usage.cost_usd == null
              ? "not priced"
              : result.usage.cost_usd === 0 && result.usage.shadow_cost_usd != null
                ? `$0 spent · ${result.provider ?? "local"} · ~$${result.usage.shadow_cost_usd.toFixed(4)} at configured prices`
                : `$${result.usage.cost_usd.toFixed(4)}`}
          </dd>
        </div>
        <div>
          <dt>Record</dt>
          <dd className="mono">
            {result.schema_version} · {result.run_id}
          </dd>
        </div>
      </dl>

      <DamagedNotice title="Run issues" items={result.issues} />
    </div>
  );
}

/* ------------------------------------------------------------------ pieces */

function Citation({ citation, runId }: { citation: TrialCitation; runId: string }) {
  const { open } = useSource();
  return (
    <button
      type="button"
      className="cite"
      aria-label={`Open source ${citation.locator}, ${citation.title}`}
      onClick={() =>
        open({
          runId,
          sourceId: citation.locator,
          fallback: {
            id: citation.locator,
            title: citation.title,
            excerpt: citation.excerpt,
            published_at: citation.published_at,
            reliability: citation.reliability,
          },
        })
      }
    >
      <code>{citation.locator}</code>
      <span className="cite-date mono">{formatDay(citation.published_at)}</span>
      <span className="cite-title">{citation.title}</span>
    </button>
  );
}


/* ------------------------------------------------------------ final-build pieces */

function VerdictSection({ result }: { result: TrialResult }) {
  const briefing = result.briefing;
  const premise = result.case_file.premise;
  if (!briefing || briefing.verification.length === 0) return null;
  return (
    <section className="rulings-ledger">
      <SectionHead
        kicker="Event verification"
        title={premise?.status === "REJECTED_PREMISE" ? "A claim in the question was rejected" : "What was verified"}
        note="Heimdall's verdict on the event and on what the question takes for granted, with the documents each rests on."
        aside={<AgentLabel agent="heimdall" compact />}
      />
      <ul className="ruled-list">
        {briefing.verification.map((item, index) => (
          <li key={index}>
            <span className={`ruling-word rw-${item.classification === "REJECTED" ? "rejected" : "established"}`}>{item.classification.toLowerCase()}</span>{" "}
            {item.text.replace(/\[[^\]]*\]/g, "").replace(/\s+/g, " ").trim()}
            <ul className="cite-inline">
              {item.citations.map((citation) => (
                <li key={citation.locator}>
                  <Citation citation={citation} runId={result.run_id} />
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  );
}


function BriefingNotices({ briefing }: { briefing: NonNullable<TrialResult["briefing"]> }) {
  return (
    <>
      {briefing.flagged_cells.length > 0 && (
        <p className="brief-note brief-flag">
          <strong>Insufficient evidence after Run II:</strong> {briefing.flagged_cells.join("; ")}. These cells carry no
          number; they are not read as zero.
        </p>
      )}
      {briefing.run2_notice && <p className="brief-note brief-flag">{briefing.run2_notice}</p>}
      {briefing.removed_by_validator.length > 0 && (
        <p className="brief-note brief-flag">
          <strong>Removed by the validator:</strong> {briefing.removed_by_validator.length} line(s) failed the number, quote,
          citation or entity guards and were taken out of the briefing.
        </p>
      )}
      <p className="brief-note mono">Rulings by {briefing.ruling_mode}</p>
    </>
  );
}

function CellDrill({ rows, result, runId }: { rows: ExposureRange[]; result: TrialResult; runId: string }) {
  const { open } = useSource();
  return (
    <div className="drills">
      {rows.map((row) => (
        <details className="drill" key={`${row.country}-${row.sector}`}>
          <summary>
            {row.country} · {row.sector}: why this range, and where it comes from
          </summary>
          <p>{row.calibration}</p>
          {row.thor_pct && row.loki_pct && (
            <p className="small muted">
              Thor argued {row.thor_pct.low != null ? `${row.thor_pct.low}% to ${row.thor_pct.high}%` : row.thor_pct.status}; Loki
              argued {row.loki_pct.low != null ? `${row.loki_pct.low}% to ${row.loki_pct.high}%` : row.loki_pct.status}.
            </p>
          )}
          {row.citation_ids.length > 0 && (
            <ul className="cite-inline">
              {row.citation_ids.map((id) => (
                <li key={id}>
                  <button type="button" className="cite cite-id" onClick={() => open({ runId, sourceId: id })} aria-label={`Open source ${id}`}>
                    <code>{id}</code>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {row.targeted_queries.length > 0 && (
            <p className="small">Targeted queries tried in Run II: {row.targeted_queries.join("; ")}.</p>
          )}
          {row.calc_ids.map((id) => {
            const calc = result.calc_explain[id];
            if (!calc) return null;
            const scenarios = (x: { scenarios: Record<string, number> } | null) =>
              x ? Object.entries(x.scenarios).map(([k, v]) => `${k.replace("_", " ")} ${v}%`).join(" · ") : "n/a";
            return (
              <div className="calc-explain" key={id}>
                <span className="eyebrow">Why this number · {id}</span>
                <p className="small">{calc.formula}</p>
                <p className="small">{calc.baseline_rule}</p>
                <p className="small mono">
                  With repeated rows: {scenarios(calc.with_repeated_rows)}
                  <br />
                  Without repeated rows: {scenarios(calc.without_repeated_rows)}
                </p>
                <ul className="cite-inline">
                  {calc.inputs.map((input) => (
                    <li key={input.row_key}>
                      <button
                        type="button"
                        className="cite cite-id"
                        onClick={() => open({ runId, sourceId: input.row_key })}
                        aria-label={`Open trade row ${input.row_key}`}
                      >
                        <code>{input.row_key}</code>
                        <span className="cite-date mono">{input.role}</span>
                        {input.repeated_row && <span className="cite-title">repeated row</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </details>
      ))}
    </div>
  );
}

function AcceptanceFacts({ result, onReplay }: { result: TrialResult; onReplay?: () => void }) {
  const a = result.acceptance;
  if (!a) return null;
  return (
    <section>
      <SectionHead kicker="Acceptance evidence" title="What this run shows" aside={
        onReplay ? (
          <button type="button" className="btn btn-quiet" onClick={onReplay}>
            Replay at $0
          </button>
        ) : undefined
      } />
      <ul className="ruled-list">
        <li>Cross-examinations: {a.cross_examinations}</li>
        <li>Claims rejected or conceded: {a.rejected_or_conceded}</li>
        <li>
          Odin sent the case back: {a.sent_back ? "yes, once" : "no"}; new evidence families in Run II:{" "}
          {a.run2_new_evidence_families.length ? a.run2_new_evidence_families.join(", ") : "none"}
        </li>
        <li>Decisions changed by private memory: {a.memory_decisions_changed}</li>
        <li>
          Briefing hash <code>{result.briefing?.briefing_hash ?? "none"}</code>: a replay must reproduce it.
        </li>
      </ul>
    </section>
  );
}

function TrapReportView({ result }: { result: TrialResult }) {
  const t = result.traps;
  if (!t) return null;
  return (
    <section>
      <SectionHead kicker="Trap report" title="What the pipeline caught" note="Each item is read from the corpus, the Case File and the trace." />
      <div className="traps">
        {t.traps.map((trap) => (
          <details key={trap.type} className={trap.count ? "" : "zero"}>
            <summary>
              {trap.type.replace(/_/g, " ").toLowerCase()} <span className="tab-count mono">{trap.count}</span>
            </summary>
            <p className="small muted">{trap.description}</p>
            <ul className="ruled-list">
              {trap.items.slice(0, 10).map((item, index) => (
                <li key={index} className="small mono">
                  {JSON.stringify(item)}
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}
