/**
 * Display names for the canonical agent IDs.
 *
 * The canonical IDs (heimdall, thor, loki, odin) are the contract used by the
 * engine, the result schema and the event log. They are never renamed in data:
 * this module is the only place the UI maps them to a display name.
 */

export type AgentId = "heimdall" | "thor" | "loki" | "odin";

export interface AgentIdentity {
  id: AgentId;
  name: string;
  epithet: string;
  role: string;
}

export const AGENTS: Record<AgentId, AgentIdentity> = {
  heimdall: { id: "heimdall", name: "Heimdall", epithet: "the Gatekeeper", role: "investigates and builds the case" },
  thor: { id: "thor", name: "Thor", epithet: "the Alarm", role: "argues the high exposure bound" },
  loki: { id: "loki", name: "Loki", epithet: "the Trickster", role: "argues the limited exposure bound" },
  odin: { id: "odin", name: "Odin", epithet: "the Independent Judge", role: "rules on every claim" },
};

const ALIASES: Record<string, AgentId> = {
  heimdall: "heimdall",
  thor: "thor",
  loki: "loki",
  odin: "odin",
  judge: "odin",
};

/** Resolve any agent-like string to a known identity. Unknown IDs pass through. */
export function agentIdentity(id: string | null | undefined): AgentIdentity | null {
  if (!id) return null;
  return AGENTS[ALIASES[id.trim().toLowerCase()]] ?? null;
}

export function agentName(id: string | null | undefined, fallback = "The record") {
  const identity = agentIdentity(id);
  if (!identity) return id ? titleCase(id) : fallback;
  return `${identity.name}, ${identity.epithet}`;
}

export function agentShort(id: string | null | undefined, fallback = "record") {
  return agentIdentity(id)?.name ?? (id ? titleCase(id) : fallback);
}

function titleCase(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
