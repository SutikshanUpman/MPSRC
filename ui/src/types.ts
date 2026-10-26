// The trial record the console reads (backend/runtime/trial_view.py, schema_version "trial-2").

export type TrialSide = "thor" | "loki" | "heimdall" | "odin";
export type TrialClass = "established" | "contested" | "conceded" | "rejected";

export interface TrialCitation {
  source_id: string;
  row_id: string | null;
  excerpt: string;
  published_at: string;
  title: string;
  source_type: string;
  reliability: number;
  /** What the source endpoint opens: DOC, DOC:P# or a trade row key DOC|YYYY-MM. */
  locator: string;
}

export interface TrialClaim {
  id: string;
  side: "thor" | "loki";
  statement: string;
  nature: "sourced_fact" | "inference";
  country: string;
  sector: string;
  estimate: number | null;
  estimate_kind: string | null;
  estimate_unit: string;
  estimate_low: number | null;
  estimate_high: number | null;
  estimate_status: string | null;
  period: string | null;
  confidence: number | null;
  citations: TrialCitation[];
  assumptions: string[];
  status: TrialClass | null;
  ruling_rationale: string | null;
  decision: "ACCEPTED" | "QUALIFIED" | "REJECTED" | null;
  claim_status: "submitted" | "superseded" | "withdrawn";
  supersedes: string | null;
  superseded_by: string | null;
  claim_type: "CELL_ESTIMATE" | "SUPPORTING";
  round: number;
}

export interface TrialChallenge {
  id: string;
  attacker: "thor" | "loki";
  target_claim_id: string;
  argument: string;
  citations: TrialCitation[];
  response: string | null;
  response_citations: TrialCitation[];
  concedes: boolean;
  outcome: string;
  kind: string;
  response_type: "DEFEND" | "QUALIFY" | "CONCEDE" | null;
}

export interface OdinRuling {
  claim_id: string;
  classification: TrialClass;
  nature: "sourced_fact" | "inference";
  rationale: string;
  citations: TrialCitation[];
  missing_evidence: string[];
  decision: "ACCEPTED" | "QUALIFIED" | "REJECTED";
  decided_by: "RULES" | "MODEL";
  rejected_by: string | null;
}

export interface SideRange {
  status: string;
  low: number | null;
  high: number | null;
}

export interface ExposureRange {
  country: string;
  sector: string;
  unit: string;
  period: string | null;
  loki_low: number | null;
  thor_high: number | null;
  odin_low: number | null;
  odin_high: number | null;
  confidence: number | null;
  assumptions: string[];
  citation_ids: string[];
  status: "ASSESSED" | "INSUFFICIENT_EVIDENCE" | "INCOMPLETE_BUDGET_LIMIT";
  reason: string | null;
  pct_low: number | null;
  pct_high: number | null;
  thor_pct: SideRange | null;
  loki_pct: SideRange | null;
  volume_low: number | null;
  volume_high: number | null;
  volume_unit: string | null;
  widened: boolean;
  calibration: string;
  targeted_queries: string[];
  calc_ids: string[];
}

export interface TrialCaseFile {
  question: string;
  as_of: string;
  corpus_pack: string;
  corpus_version: string;
  event_id: string | null;
  event_name: string | null;
  event_verified: boolean;
  verification_summary: string;
  countries: string[];
  sectors: string[];
  relevant_source_ids: string[];
  contradictions: string[];
  assumptions: string[];
  issues: string[];
  coverage: { country: string; sector: string; status: string }[];
  evidence_gaps: { country: string; sector: string; missing: string; queries: string[] }[];
  event_status: "VERIFIED" | "EVENT_UNVERIFIED";
}

export interface TrialRun {
  run_number: number;
  started_at: string;
  finished_at: string | null;
  new_evidence_ids: string[];
  new_evidence_families: string[];
  query_count: number;
  claims: TrialClaim[];
  challenges: TrialChallenge[];
  rulings: OdinRuling[];
  sufficient: boolean;
  returned_by_odin: boolean;
  missing_evidence: string[];
  errors: string[];
  no_new_evidence_reason: string | null;
}

export interface TrialBriefing {
  executive_summary: string;
  established: string[];
  contested: string[];
  conceded: string[];
  rejected: string[];
  exposure: ExposureRange[];
  outlook: string;
  outlook_parts: { drivers: string[]; risks: string[]; indicators: string[] };
  assumptions: string[];
  source_ids: string[];
  citations: TrialCitation[];
  complete: boolean;
  flagged_cells: string[];
  removed_by_validator: { section: string; paragraph_id: string; text: string; problems: string[] }[];
  ruling_mode: string;
  run2_notice: string | null;
  briefing_hash: string | null;
}

export interface MemoryAudit {
  agent: TrialSide;
  action: string;
  key: string;
  value: string | null;
  influenced_action: string | null;
  run_number: number;
  timestamp: string;
}

export interface UsageSummary {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  shadow_cost_usd: number | null;
  latency_s: number;
}

export interface TrapItem {
  type: string;
  description: string;
  count: number;
  items: Record<string, unknown>[];
}

export interface CalcExplain {
  formula: string;
  baseline_rule: string;
  status: string;
  paired_months: string[];
  inputs: {
    role: string;
    row_key: string;
    doc_id: string;
    paragraph: string;
    table_id: string | null;
    native_row_number: number | null;
    citation: string;
    repeated_row: boolean;
  }[];
  with_repeated_rows: { scenarios: Record<string, number> } | null;
  without_repeated_rows: { scenarios: Record<string, number> } | null;
  widened: boolean;
}

export interface TrialResult {
  schema_version: string;
  run_id: string;
  question: string;
  case_file: TrialCaseFile;
  runs: TrialRun[];
  briefing: TrialBriefing | null;
  memory_audit: MemoryAudit[];
  issues: string[];
  status: "completed" | "partial" | "failed" | "unverified";
  created_at: string;
  finished_at: string | null;
  provider: string | null;
  usage: UsageSummary;
  acceptance: {
    cross_examinations: number;
    rejected_or_conceded: number;
    sent_back: boolean;
    run2_new_evidence_families: string[];
    memory_decisions_changed: number;
  } | null;
  ruling_mode: string | null;
  traps: { summary: Record<string, number>; traps: TrapItem[] } | null;
  calc_explain: Record<string, CalcExplain>;
}

export interface RunEvent {
  seq: number;
  type: string;
  timestamp: string;
  step: string | null;
  agent: string | null;
  level?: string;
  data: Record<string, unknown>;
}

export interface RunSummary {
  run_id: string;
  question: string;
  mode: string;
  status: "queued" | "running" | "done" | "completed" | "partial" | "failed" | "unverified";
  created_at: string;
  error: string | null;
  provider?: string;
  briefing_hash?: string | null;
}

export interface RunemarkFeedItem {
  id: string;
  title: string;
  source_name: string;
  source_type: string;
  reliability: number;
  published_at: string;
  event_id: string;
  country: string;
  sector: string;
  excerpt: string;
}

export type ResultPayload = TrialResult;

export interface ProviderInfo {
  name: "ollama" | "anthropic" | "replay";
  label: string;
  /** Can start a run from this server right now. */
  configured: boolean;
  /** No cost: a local model. */
  free: boolean;
  description: string;
  /** What to set when it is not configured. */
  hint: string | null;
  models: string[];
  needs_model: boolean;
  default_model: string | null;
  default_label?: string;
}

export interface Meta {
  version: string;
  modes: string[];
  profiles: string[];
  tools: string[];
  providers: ProviderInfo[];
  models: { value: string; label: string; spec: string; default: boolean }[];
}
