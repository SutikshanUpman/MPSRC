import { useState } from "react";
import type { RunInput } from "../api";
import type { Meta } from "../types";
import { AgentLabel } from "./Ornaments";

const HANDS = [
  { agent: "heimdall" as const, text: "Opens the Case File. Verifies the event, sets aside retracted, damaged and future-dated documents." },
  { agent: "thor" as const, text: "Searches independently for the high bound of exposure and submits cited claims." },
  { agent: "loki" as const, text: "Tests substitution and rerouting for the limited bound and submits cited claims." },
  { agent: "odin" as const, text: "Rules on every claim, fixes the range, sends the case back once, writes the briefing from the rulings alone." },
];

const EXAMPLE =
  "As of 25 January 2027, how exposed are Midgard and Tolan to the end of the Orvan corridor agreement? Give a low and high range for wheat and maize imports.";

export function RunForm({
  meta,
  busy,
  onSubmit,
}: {
  meta: Meta | null;
  busy: boolean;
  onSubmit: (input: RunInput) => void;
}) {
  const [question, setQuestion] = useState("");
  const [asOf, setAsOf] = useState("");
  const [runemarkPath, setRunemarkPath] = useState("");
  const defaultModel = meta?.models.find((option) => option.default);

  return (
    <section className="intake" aria-labelledby="intake-title">
      <header className="intake-head">
        <span className="eyebrow">Ragnarok Trial Console · start here</span>
        <h1 className="intake-title" id="intake-title">
          Open a case
        </h1>
        <p className="intake-note">
          Ask one question. Heimdall opens the Case File, Thor and Loki argue, Odin rules and writes the briefing.
          Every number in it traces to a Runemark document.
        </p>
      </header>

      <div className="intake-body">
        <form
          className="intake-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!question.trim()) return;
            onSubmit({
              question,
              mode: "trial",
              profile: "mock",
              as_of_date: asOf || undefined,
              runemark_path: runemarkPath || undefined,
            });
          }}
        >
          <div className="field">
            <label className="field-label" htmlFor="question">
              Question <span className="field-hint">include the as-of date, countries and sectors</span>
            </label>
            <textarea
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={4}
              maxLength={4000}
              placeholder={EXAMPLE}
              required
            />
            <button type="button" className="link-btn" onClick={() => setQuestion(EXAMPLE)}>
              Use the E5 sample question
            </button>
          </div>

          <div className="field-row">
            <div className="field field-date">
              <label className="field-label" htmlFor="as-of">
                As-of date <span className="field-hint">optional; the question&apos;s own date wins</span>
              </label>
              <input id="as-of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </div>
            <div className="field">
              <span className="field-label">
                Agents <span className="field-hint">the console never starts a live model</span>
              </span>
              <p className="field-static">{defaultModel ? defaultModel.label : "Deterministic mock · $0"}</p>
            </div>
          </div>

          <details className="advanced-options">
            <summary>
              <span>Runemark pack</span>
              <span className="field-hint">defaults to dev_pack_E5</span>
            </summary>
            <div className="advanced-options-body">
              <div className="field">
                <label className="field-label" htmlFor="corpus">
                  Pack folder <span className="field-hint">inside the repository; any compatible pack works unchanged</span>
                </label>
                <input
                  id="corpus"
                  className="mono-input"
                  value={runemarkPath}
                  onChange={(e) => setRunemarkPath(e.target.value)}
                  placeholder="dev_pack_E5"
                />
              </div>
            </div>
          </details>

          <div className="submit-row">
            <p className="submit-note">Two bounded runs. Citations are checked against the corpus; the run is recorded and can be replayed at $0.</p>
            <button className="btn btn-primary" disabled={busy || !question.trim()}>
              {busy ? "Opening the case" : "Start the trial"}
            </button>
          </div>
        </form>

        <aside className="intake-aside" aria-label="How a trial proceeds">
          <figure className="plate">
            <img
              src="/chart/runemark-chart.jpg"
              alt="Chart of Runemark: the inner and outer seas, with twelve ports, including Orvan, Midgard, Tolan and Ravik."
              width={1600}
              height={1067}
              loading="lazy"
            />
            <figcaption>
              <span className="eyebrow">Runemark map</span>
              The trial reads only what the Runemark pack says about these coasts.
            </figcaption>
          </figure>

          <div className="hands">
            <span className="eyebrow">Four agents</span>
            <ol>
              {HANDS.map((hand, index) => (
                <li key={hand.agent}>
                  <span className="hands-numeral mono">{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <AgentLabel agent={hand.agent} />
                    <p>{hand.text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="hands-note">
              A thin record is returned once. Run 2 must bring new evidence, or the cell is flagged INSUFFICIENT_EVIDENCE
              and the briefing says so.
            </p>
          </div>
        </aside>
      </div>
    </section>
  );
}
