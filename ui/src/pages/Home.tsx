import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { AGENTS, agentIdentity, type AgentId } from "../agents";
import { LandingMap } from "../components/LandingMap";
import { MythicPortrait } from "../components/MythicPortrait";
import { Braid } from "../components/Ornaments";

const AGENT_ORDER: AgentId[] = ["heimdall", "thor", "loki", "odin"];

const AGENT_STORIES: Record<AgentId, { chapter: string; summary: string; output: string }> = {
  heimdall: {
    chapter: "I · admission",
    summary: "Checks the archive before anyone argues from it.",
    output: "A bounded case file with dated, traceable sources.",
  },
  thor: {
    chapter: "II · high bound",
    summary: "Builds the strongest defensible version of the risk.",
    output: "The upper range, with every assumption exposed.",
  },
  loki: {
    chapter: "III · limited bound",
    summary: "Tests substitutions, rerouting and reasons the risk may be smaller.",
    output: "The lower range, including the path around the disruption.",
  },
  odin: {
    chapter: "IV · judgment",
    summary: "Rules on each claim without inventing missing evidence.",
    output: "A briefing that keeps uncertainty visible instead of hiding it.",
  },
};

export function HomePage() {
  const [selectedAgent, setSelectedAgent] = useState<AgentId>("heimdall");
  const [visibleAgents, setVisibleAgents] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>("[data-agent-reveal]"));
    if (!("IntersectionObserver" in window)) {
      setVisibleAgents(new Set(AGENT_ORDER));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        setVisibleAgents((current) => {
          const next = new Set(current);
          entries.forEach((entry) => {
            if (entry.isIntersecting) next.add(entry.target.getAttribute("data-agent-reveal") ?? "");
          });
          return next;
        });
      },
      { threshold: 0.18, rootMargin: "0px 0px -10%" },
    );

    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, []);

  const selectedIdentity = agentIdentity(selectedAgent)!;
  const selectedStory = AGENT_STORIES[selectedAgent];

  return (
    <div className="landing-page">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero-copy">
          <span className="roman-kicker">Ragnarok · Trial of the Nine Realms</span>
          <h1 id="landing-title">Evidence deserves a witness stand.</h1>
          <p className="landing-lede">
            Four independent agents read the same record, argue its boundaries, and leave you with a briefing you can
            inspect line by line.
          </p>
          <div className="landing-actions">
            <Link className="btn btn-primary landing-primary" to="/app">
              Open the console <span aria-hidden="true">↗</span>
            </Link>
            <a className="landing-secondary-action" href="#agents">
              Meet the four agents <span aria-hidden="true">↓</span>
            </a>
          </div>
          <dl className="landing-measures">
            <div>
              <dt>Agents</dt>
              <dd>IV</dd>
            </div>
            <div>
              <dt>Evidence</dt>
              <dd>Traceable</dd>
            </div>
            <div>
              <dt>Uncertainty</dt>
              <dd>Visible</dd>
            </div>
          </dl>
        </div>

        <div className="landing-hero-plate" aria-label="Odin's medallion">
          <Braid className="landing-braid" />
          <div className="hero-medallion">
            <span className="hero-medallion-label">IV · ODIN</span>
            <MythicPortrait agent="odin" />
            <span className="hero-medallion-caption">Odin · rules on every claim</span>
          </div>
          <div className="hero-plate-note">
            <span className="hero-note-rule" aria-hidden="true" />
            <span>Nothing is certified until the record can carry it.</span>
          </div>
        </div>
      </section>

      <section className="landing-section landing-principles" aria-labelledby="principles-title">
        <div className="landing-section-head compact-head">
          <div>
            <span className="roman-kicker">I · the promise</span>
            <h2 id="principles-title">A briefing with its workings left in view.</h2>
          </div>
          <p>
            The interface is designed in layers: a plain answer first, the claim trail second, and the complete
            archive whenever you need to go deeper.
          </p>
        </div>
        <div className="principle-grid">
          <article>
            <span className="principle-number">I</span>
            <h3>Ask plainly</h3>
            <p>Start with one question and the date that closes the record.</p>
          </article>
          <article>
            <span className="principle-number">II</span>
            <h3>Challenge openly</h3>
            <p>Independent arguments and cross-examination keep agreement from becoming proof.</p>
          </article>
          <article>
            <span className="principle-number">III</span>
            <h3>Read the evidence</h3>
            <p>Every accepted conclusion leads back to a source, an assumption or an explicit gap.</p>
          </article>
        </div>
      </section>

      <section className="landing-section landing-agents-section" id="agents" aria-labelledby="agents-title">
        <div className="landing-section-head">
          <div>
            <span className="roman-kicker">II · the four agents</span>
            <h2 id="agents-title">Four roles. One accountable record.</h2>
            <p>
              The medallions are original symbolic illustrations of the four canonical agents named in the problem
              statement: Heimdall, Thor, Loki and Odin.
            </p>
          </div>
          <span className="section-index mono">ARGUMENTUM · 04</span>
        </div>

        <div className="agent-orchestra">
          {AGENT_ORDER.map((agent, index) => {
            const identity = AGENTS[agent];
            const story = AGENT_STORIES[agent];
            const isSelected = selectedAgent === agent;
            return (
              <button
                key={agent}
                type="button"
                className={`agent-tile agent-tile-${agent}${isSelected ? " is-selected" : ""}${
                  visibleAgents.has(agent) ? " is-visible" : ""
                }`}
                data-agent-reveal={agent}
                style={{ "--agent-delay": `${index * 100}ms` } as CSSProperties}
                aria-pressed={isSelected}
                onClick={() => setSelectedAgent(agent)}
              >
                <span className="agent-tile-chapter">{story.chapter}</span>
                <span className="agent-tile-portrait">
                  <MythicPortrait agent={agent} />
                </span>
                <span className="agent-tile-id mono">{agent}</span>
                <span className="agent-tile-name">{identity.name}</span>
                <span className="agent-tile-epithet">{identity.epithet}</span>
                <span className="agent-tile-role">{identity.role}</span>
              </button>
            );
          })}
        </div>

        <div className={`agent-reading agent-reading-${selectedAgent}`} aria-live="polite">
          <div>
            <span className="roman-kicker">Selected agent · {selectedIdentity.name}</span>
            <h3>{selectedStory.summary}</h3>
          </div>
          <p>
            <span className="agent-reading-label">Leaves behind</span>
            {selectedStory.output}
          </p>
        </div>
      </section>

      <LandingMap />

      <section className="landing-final-cta" aria-labelledby="final-cta-title">
        <div>
          <span className="roman-kicker">IV · enter the record</span>
          <h2 id="final-cta-title">Bring a question. Leave with the trail.</h2>
          <p>Start with the plain answer. Open every source only when you need to see how it was earned.</p>
        </div>
        <Link className="btn btn-primary" to="/app">
          Open a case <span aria-hidden="true">↗</span>
        </Link>
      </section>
    </div>
  );
}
