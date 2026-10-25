import { useId } from "react";
import type { ReactNode } from "react";
import { agentIdentity, type AgentId } from "../agents";

/* ------------------------------------------------------------------ ornament */

/**
 * A two-strand interlace, used once at the head of the page. It reads as a
 * woven border rather than a decorative frame.
 */
export function Braid({ className = "" }: { className?: string }) {
  const key = `braid-${useId().replace(/:/g, "")}`;
  return (
    <svg className={`braid ${className}`} aria-hidden="true" focusable="false" preserveAspectRatio="none">
      <defs>
        <pattern id={key} x="0" y="0" width="28" height="12" patternUnits="userSpaceOnUse">
          <path d="M-2 9 C4 1 10 1 14 6 C18 11 24 11 30 3" fill="none" stroke="currentColor" strokeWidth="1" />
          <path d="M-2 3 C4 11 10 11 14 6 C18 1 24 1 30 9" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.55" />
          <path d="M14 4.4 V7.6" stroke="currentColor" strokeWidth="0.8" opacity="0.35" />
        </pattern>
      </defs>
      <rect width="100%" height="12" fill={`url(#${key})`} />
    </svg>
  );
}

/* ------------------------------------------------------------------- heading */

/**
 * Section heading carrying the Doric motif: one vertical rule with a capital bar.
 * Used on section headers only, never on every element.
 */
export function SectionHead({
  kicker,
  title,
  note,
  aside,
  as: Tag = "header",
  className = "",
}: {
  kicker?: string;
  title: string;
  note?: string;
  aside?: ReactNode;
  as?: "header" | "div";
  className?: string;
}) {
  return (
    <Tag className={`sec-head ${className}`}>
      <div className="sec-head-text">
        <span className="stave" aria-hidden="true" />
        <div>
          {kicker && <span className="eyebrow">{kicker}</span>}
          <h3 className="sec-title">{title}</h3>
          {note && <p className="sec-note">{note}</p>}
        </div>
      </div>
      {aside && <div className="sec-head-aside">{aside}</div>}
    </Tag>
  );
}

/* -------------------------------------------------------------------- agents */

/**
 * One simple black-figure sigil per agent, drawn on a 24-unit grid with a single
 * stroke weight. Each renders in one colour inherited from the surrounding text.
 */
export function Sigil({ agent, className = "" }: { agent: AgentId; className?: string }) {
  const identity = agentIdentity(agent);
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  return (
    <svg
      className={`sigil ${className}`}
      viewBox="0 0 24 24"
      role="img"
      aria-label={identity ? `${identity.name} sigil` : "agent sigil"}
    >
      {agent === "heimdall" && (
        <g {...common}>
          <path d="M2.5 12c2.6-3.9 5.8-5.9 9.5-5.9s6.9 2 9.5 5.9c-2.6 3.9-5.8 5.9-9.5 5.9S5.1 15.9 2.5 12Z" />
          <circle cx="12" cy="12" r="3.1" />
          <path d="M12 3.4v2M12 18.6v2M4.2 6l1.5 1.6M18.3 16.4l1.5 1.6M19.8 6l-1.5 1.6M5.7 16.4 4.2 18" />
        </g>
      )}
      {agent === "thor" && (
        <g {...common}>
          <path d="M6.2 15.8a5.8 5.8 0 0 1 11.6 0" />
          <path d="M4.2 15.8h15.6M9 19.4c.6 .9 1.6 1.4 3 1.4s2.4-.5 3-1.4" />
          <circle cx="12" cy="20.9" r="0.9" />
          <path d="M9.8 5.4c0-1.2 1-2 2.2-2s2.2.8 2.2 2v2" />
          <path d="M12 3.4v2" />
        </g>
      )}
      {agent === "loki" && (
        <g {...common}>
          <path d="M12 6.4v15.2M8.6 21.6h6.8" />
          <circle cx="12" cy="4" r="1.6" />
          <path d="M12 8.6c-2.6 0-4.6 1.4-4.6 3.4s2 3.2 4.6 3.2 4.6 1.2 4.6 3.2-2 3.4-4.6 3.4" />
          <path d="M12 8.6c2.6 0 4.6 1.4 4.6 3.4s-2 3.2-4.6 3.2-4.6 1.2-4.6 3.2 2 3.4 4.6 3.4" opacity="0.5" />
        </g>
      )}
      {agent === "odin" && (
        <g {...common}>
          <path d="M12 4.4v15.8M8.4 21.4h7.2M10 22.6h4" />
          <path d="M4.4 7.6h15.2" />
          <path d="M6.2 7.6 3.2 13.4h6ZM17.8 7.6l-3 5.8h6Z" />
          <path d="M3.6 14.2c.4 1.6 1 2.4 2.6 2.4s2.2-.8 2.6-2.4M15.2 14.2c.4 1.6 1 2.4 2.6 2.4s2.2-.8 2.6-2.4" opacity="0.55" />
        </g>
      )}
    </svg>
  );
}

/** Display label plus the canonical ID in small monospace, for display only. */
export function AgentLabel({
  agent,
  role,
  compact = false,
  className = "",
}: {
  agent: AgentId;
  role?: string;
  compact?: boolean;
  className?: string;
}) {
  const identity = agentIdentity(agent);
  return (
    <span className={`agent${compact ? " agent-compact" : ""} ${className}`} data-agent={agent}>
      <Sigil agent={agent} className="agent-sigil" />
      <span className="agent-text">
        <span className="agent-name">{identity ? `${identity.name}, ${identity.epithet}` : agent}</span>
        <code className="agent-id">{agent}</code>
        {role && !compact && <span className="agent-role">{role}</span>}
      </span>
    </span>
  );
}

/* --------------------------------------------------------------------- marks */

/** Outlet tier: a numeral, no colour coding. */
export function TierMark({ tier }: { tier: number }) {
  return (
    <span className="tier" title={`Source tier ${tier} of 4`}>
      <span className="sr-only">Tier </span>T{tier}
    </span>
  );
}

/** Sourced fact or inference: a solid or dashed rule plus a written label. */
export function FactMark({ nature }: { nature: "sourced_fact" | "inference" }) {
  const fact = nature === "sourced_fact";
  return (
    <span className={`factmark factmark-${fact ? "fact" : "inference"}`}>
      <span className="factmark-rule" aria-hidden="true" />
      {fact ? "sourced fact" : "inference"}
    </span>
  );
}
