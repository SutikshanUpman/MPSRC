import { agentShort } from "../agents";
import type { RunEvent } from "../types";
import { LoadingRecord } from "./States";

/** Events the live feed shows: the trace the Python engine writes, by its own event names. */
const HIDDEN = new Set(["SEARCH_COMPLETED_FILTERS", "TOOL_CALLED", "DOCUMENT_RETRIEVED", "INPUT_REBUILT", "BATCH_RESIZED"]);

const MAX_ROWS = 300;

function clock(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString("en-GB", { hour12: false });
}

type D = Record<string, unknown>;
const list = (x: unknown) => (Array.isArray(x) ? x : []);

function describe(e: RunEvent): string {
  const d = e.data as D;
  const who = agentShort(e.agent ?? null, "The record");
  switch (e.type) {
    case "CASE_CREATED":
      return "case opened";
    case "AS_OF_DATE_RESOLVED":
      return `as-of date ${d.as_of_date} (from the ${d.source})`;
    case "EVENT_MAPPING":
      return `event mapping ${d.decision}`;
    case "EVENT_VERIFICATION":
      return `event ${d.verdict}: ${d.reason}`;
    case "PREMISE_CHECKED":
      return `premise check ${d.status}`;
    case "COVERAGE_TESTED":
      return `coverage tested for ${list(d.cells).length} cells`;
    case "SEARCH_COMPLETED":
      return `${who} searched “${d.query}” (${list(d.result_doc_ids).length} documents)${d.run === 2 ? " · Run II" : ""}`;
    case "SEARCH_EXECUTED":
      return `${who} searched “${d.query}” (${list(d.result_doc_ids).length} documents)`;
    case "SEARCH_CACHE_HIT":
      return `${who} repeated a search; cached result used`;
    case "SEARCH_LIMIT_REACHED":
      return `${who} reached its search limit`;
    case "CASE_FILE_BUILT":
      return `Case File sealed: ${d.status}`;
    case "ROUND_1_STARTED":
      return "Run I: Thor and Loki open their cases";
    case "ROUND_1_COMPLETED":
      return `Run I claims in: ${d.claims} claims, ${d.calcs} calculations`;
    case "AGENT_STEP_STARTED":
      return `${who} starts a step on ${list(d.cells).length} cell(s)`;
    case "AGENT_STEP_COMPLETED":
      return `${who} finished a step in ${d.turns} turn(s)`;
    case "CALC_COMPUTED":
      return `${d.calc_id} ${d.country} ${d.sector}: ${d.status}${d.widened ? " (range widened by repeated rows)" : ""}`;
    case "CLAIMS_SUBMITTED":
      return `${who} submitted ${list(d.claim_ids).join(", ")}`;
    case "CLAIM_VALIDATION_FAILED":
      return `${who}'s output failed a guard (attempt ${d.attempt}): ${String(list(d.problems)[0] ?? "")}`;
    case "MEMORY_READ":
      return `${who} read private memory (${list(d.memory_ids).length} entries, ${list(d.hidden_ids).length} hidden by the as-of rule)`;
    case "MEMORY_WRITTEN":
      return `${who} wrote private memory ${d.key}`;
    case "MEMORY_HIDDEN":
      return `${who}: memory entry hidden, it postdates this case`;
    case "DECISION_CHANGED":
      return `${who}'s decision changed by memory: ${d.kind} “${d.before}” → “${d.after}”`;
    case "DECISION_UNVERIFIED":
      return `${who} claimed a memory-driven change that did not happen`;
    case "ROUND_2_STARTED":
      return "Cross-examination begins";
    case "CHALLENGES_SUBMITTED":
      return `${who} filed ${list(d.challenge_ids).length} challenge(s): ${list(d.kinds).join(", ").toLowerCase()}`;
    case "RESPONSES_SUBMITTED":
      return `${who} answered: ${list(d.types).join(", ")}`;
    case "CLAIM_SUPERSEDED":
      return `${d.claim_id} superseded by ${d.superseded_by}`;
    case "CLAIM_CONCEDED":
      return `${d.claim_id} conceded: ${d.reason}`;
    case "ROUND_2_COMPLETED":
      return `cross-examination done: ${d.challenges} challenges, ${d.responses} responses`;
    case "ODIN_RULED":
      return `Odin ruled (Run ${d.run}): ${JSON.stringify(d.decisions)}`;
    case "ODIN_SENT_BACK":
      return `Odin sent the case back: ${list(d.gaps).map((g) => `${(g as D).country} ${(g as D).sector}`).join(", ")}`;
    case "RUN_2_STARTED":
      return `Run II: ${list(d.cells).length} cell(s) re-searched`;
    case "RUN_2_NEW_EVIDENCE":
      return `Run II found ${list(d.families).length} new evidence families`;
    case "RUN_2_COMPLETED":
      return `Run II done; updated ${Object.values((d.updated as D) ?? {}).flat().join(", ") || "nothing"}`;
    case "CELL_INSUFFICIENT_EVIDENCE":
      return `${d.country} ${d.sector}: INSUFFICIENT_EVIDENCE (${d.reason})`;
    case "BRIEFING_BUILT":
      return `briefing ${d.completion}; ${d.removed} line(s) removed by the validator`;
    case "AGENT_FAILED":
      return `${who} failed: ${d.reason}`;
    case "BUDGET_CAP_REACHED":
      return `budget cap reached: ${d.detail}`;
    case "STANCE_FALLBACK":
      return "stance classifier consulted";
    default:
      if (e.type.startsWith("FALLBACK_")) return `${e.type.replace("FALLBACK_", "fallback: ").replace(/_/g, " ").toLowerCase()} ${String(d.reason ?? d.detail ?? "")}`;
      return String(d.error ?? d.message ?? e.type.replace(/_/g, " ").toLowerCase());
  }
}

export function EventLog({
  events,
  live,
  question,
  status,
}: {
  events: RunEvent[];
  live: boolean;
  question?: string;
  status?: string;
  onOpen?: () => void;
}) {
  const shown = events.filter((e) => !HIDDEN.has(e.type));
  const rows = shown.slice(-MAX_ROWS).reverse();

  return (
    <section className="hearing">
      <header className="hearing-head">
        <span className="eyebrow">{live ? "Live feed · trial under way" : "Live feed · closing the record"}</span>
        <h1 className="hearing-title">{question ?? (live ? "The trial is under way" : "Sealing the record")}</h1>
        <p className="hearing-note">
          Thor and Loki search the Runemark corpus, cite it, and answer to Odin. The log is written as steps complete;
          nothing is edited afterwards.
        </p>
        <div className="hearing-meta">
          <span className={`live-rule ${live ? "is-live" : ""}`} aria-hidden="true" />
          <span className="mono">{shown.length.toLocaleString()} entries</span>
          <span className="mono">latest first</span>
          {status && <span className="hearing-state">{status}</span>}
        </div>
      </header>

      {rows.length === 0 ? (
        <LoadingRecord label={live ? "Waiting for the first entry" : "No entry was written"} rows={4} />
      ) : (
        <ol className="log" aria-live={live ? "polite" : "off"}>
          {rows.map((e) => (
            <li key={e.seq} className={`log-row ${e.level === "WARNING" ? "log-warning" : ""} log-${e.type.toLowerCase().replace(/_/g, "-")}`}>
              <span className="log-time mono">{clock(e.timestamp)}</span>
              <span className="log-agent">{agentShort(e.agent ?? null, "Runtime")}</span>
              <code className="log-id">{e.type}</code>
              <span className="log-text">{describe(e)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
