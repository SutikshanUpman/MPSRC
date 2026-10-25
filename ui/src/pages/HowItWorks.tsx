import { Link } from "react-router-dom";
import { AGENTS, type AgentId } from "../agents";
import { MythicPortrait } from "../components/MythicPortrait";
import { Braid } from "../components/Ornaments";

const AGENT_ORDER: AgentId[] = ["heimdall", "thor", "loki", "odin"];

const STEPS = [
  {
    number: "I",
    title: "Ask a focused question",
    note: "Put the as-of date in the question. The system will not quietly use evidence from the future.",
  },
  {
    number: "II",
    title: "Check what is actually in the archive",
    note: "Heimdall filters damaged, retracted, contradictory and out-of-time material before the arguments begin.",
  },
  {
    number: "III",
    title: "Build two independent views",
    note: "Thor argues the high exposure. Loki tests the lower bound, substitutions and rerouting.",
  },
  {
    number: "IV",
    title: "Odin rules, then sends the case back once",
    note: "Odin classifies every claim as established, contested, conceded or rejected. A cell with a gap goes back for a second run with new queries.",
  },
  {
    number: "V",
    title: "Read the briefing",
    note: "Odin writes only from the rulings. A cell that still has no evidence after Run 2 is flagged INSUFFICIENT_EVIDENCE, never read as zero.",
  },
];

export function HowItWorksPage() {
  return (
    <section className="page-section how-page" aria-label="How it works">
      <div className="how-hero">
        <Braid className="page-rule" />
        <span className="roman-kicker">A short guide to the record</span>
        <h1 className="display-1 mb-8">Four roles. One answer you can inspect.</h1>
        <p className="how-lede">
          The trial does not ask one model to sound certain. It separates the work into admission, argument,
          challenge and judgment so a reader can see where the answer came from.
        </p>
        <Link className="btn btn-primary" to="/app">
          Open the console <span aria-hidden="true">↗</span>
        </Link>
      </div>

      <div className="how-agents">
        <div className="how-section-title">
          <span className="roman-kicker">The four agents</span>
          <h2>Each role has a different job.</h2>
        </div>
        <div className="how-agent-grid">
          {AGENT_ORDER.map((agent) => (
            <article key={agent} className={`how-agent-card how-agent-${agent}`}>
              <MythicPortrait agent={agent} />
              <span className="mono how-agent-id">{agent}</span>
              <h3>{AGENTS[agent].name}</h3>
              <p>{AGENTS[agent].role}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="how-steps">
        <div className="how-section-title">
          <span className="roman-kicker">The sequence</span>
          <h2>What happens after you press start.</h2>
        </div>
        <ol>
          {STEPS.map((step) => (
            <li key={step.number}>
              <span className="how-step-number">{step.number}</span>
              <div>
                <h3>{step.title}</h3>
                <p>{step.note}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <div className="how-terms">
        <span className="roman-kicker">Plain-language labels</span>
        <h2>Read the result in three layers.</h2>
        <dl>
          <div>
            <dt>At a glance</dt>
            <dd>The short answer, evidence status and unresolved questions.</dd>
          </div>
          <div>
            <dt>Claim trail</dt>
            <dd>What was asserted, challenged, conceded or rejected.</dd>
          </div>
          <div>
            <dt>Source record</dt>
            <dd>The documents, trade rows and dates behind every admitted citation.</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
