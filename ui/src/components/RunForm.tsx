import { useEffect, useMemo, useState } from "react";
import type { RunInput } from "../api";
import type { Meta, ProviderInfo } from "../types";
import { AgentLabel } from "./Ornaments";

const HANDS = [
  { agent: "heimdall" as const, text: "Opens the Case File. Verifies the event, sets aside retracted, damaged and future-dated documents." },
  { agent: "thor" as const, text: "Searches independently for the high bound of exposure and submits cited claims." },
  { agent: "loki" as const, text: "Tests substitution and rerouting for the limited bound and submits cited claims." },
  { agent: "odin" as const, text: "Rules on every claim, fixes the range, sends the case back once, writes the briefing from the rulings alone." },
];

const EXAMPLE =
  "As of 25 January 2027, how exposed are Midgard and Tolan to the end of the Orvan corridor agreement? Give a low and high range for wheat and maize imports.";

type Choice = { value: string; label: string; provider: ProviderInfo; model: string; disabled: boolean };

/** One flat list of what can be picked: the Ollama models installed here, and Claude. */
function choicesFor(providers: ProviderInfo[]): { group: string; hint: string | null; items: Choice[] }[] {
  const groups: { group: string; hint: string | null; items: Choice[] }[] = [];
  for (const provider of providers) {
    const disabled = !provider.configured;
    if (provider.name === "ollama") {
      groups.push({
        group: "Ollama · local, free",
        hint: provider.models.length === 0 ? provider.hint ?? "No model installed: run `ollama pull qwen2.5:14b`." : null,
        items: provider.models.map((m) => ({ value: `ollama::${m}`, label: m, provider, model: m, disabled })),
      });
    } else if (provider.name === "anthropic") {
      groups.push({
        group: "Claude · Anthropic API, metered",
        hint: disabled ? provider.hint : null,
        items: [
          { value: "anthropic::", label: provider.default_label ?? "Default split", provider, model: "", disabled },
          ...provider.models.map((m) => ({ value: `anthropic::${m}`, label: m, provider, model: m, disabled })),
        ],
      });
    }
  }
  return groups;
}

export function RunForm({
  meta,
  busy,
  onSubmit,
}: {
  meta: Meta | null;
  busy: boolean;
  onSubmit: (input: RunInput) => void;
}) {
  const providers = useMemo(() => (meta?.providers ?? []).filter((p) => p.name === "ollama" || p.name === "anthropic"), [meta]);
  const groups = useMemo(() => choicesFor(providers), [providers]);
  const all = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  const [question, setQuestion] = useState("");
  const [asOf, setAsOf] = useState("");
  const [runemarkPath, setRunemarkPath] = useState("");
  const [choice, setChoice] = useState("");
  const [odinChoice, setOdinChoice] = useState("");

  // Start on the first model that is ready; keep the user's choice once they make one.
  useEffect(() => {
    if (choice && all.some((c) => c.value === choice)) return;
    const ready = all.find((c) => !c.disabled);
    setChoice(ready ? ready.value : "");
  }, [all, choice]);

  const picked = all.find((c) => c.value === choice);
  const odinOptions = all.filter((c) => picked && c.provider.name === picked.provider.name && c.model !== "" && !c.disabled);
  const ready = Boolean(picked && !picked.disabled);
  const unreadyHint = picked?.disabled ? picked.provider.hint : null;

  return (
    <section className="intake" aria-labelledby="intake-title">
      <header className="intake-head">
        <span className="eyebrow">Ragnarok Trial Console · start here</span>
        <h1 className="intake-title" id="intake-title">
          Open a case
        </h1>
        <p className="intake-note">
          Ask one question and choose the model that runs the four agents. Heimdall opens the Case File, Thor and Loki
          argue, Odin rules and writes the briefing. Every number in it traces to a Runemark document.
        </p>
      </header>

      <div className="intake-body">
        <form
          className="intake-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!question.trim() || !ready || !picked) return;
            onSubmit({
              question,
              mode: "trial",
              provider: picked.provider.name as RunInput["provider"],
              model: picked.model || undefined,
              odin_model: odinChoice ? odinChoice.split("::")[1] : undefined,
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
            <div className="field">
              <label className="field-label" htmlFor="model">
                Model <span className="field-hint">Ollama (local) or Claude; keys stay on the server</span>
              </label>
              <select
                id="model"
                value={choice}
                onChange={(e) => {
                  setChoice(e.target.value);
                  setOdinChoice("");
                }}
                disabled={busy || all.length === 0}
              >
                {all.length === 0 && <option value="">No model available</option>}
                {groups.map((g) => (
                  <optgroup key={g.group} label={g.group}>
                    {g.items.length === 0 && (
                      <option disabled value={`none::${g.group}`}>
                        none installed
                      </option>
                    )}
                    {g.items.map((c) => (
                      <option key={c.value} value={c.value} disabled={c.disabled}>
                        {c.label}
                        {c.disabled ? " (not set up)" : ""}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {groups.filter((g) => g.hint).map((g) => (
                <p key={g.group} className="mode-note provider-hint">
                  {g.group.split(" ·")[0]}: {g.hint}
                </p>
              ))}
              {picked && !unreadyHint && (
                <p className="mode-note">
                  {picked.provider.free
                    ? "Runs on this machine. Free; speed depends on your hardware."
                    : "Metered: the per-case cap, Odin's reserve and the project ledger apply."}
                </p>
              )}
            </div>
            <div className="field field-date">
              <label className="field-label" htmlFor="as-of">
                As-of date <span className="field-hint">optional; the question&apos;s own date wins</span>
              </label>
              <input id="as-of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </div>
          </div>

          <details className="advanced-options">
            <summary>
              <span>Advanced</span>
              <span className="field-hint">Odin&apos;s model, Runemark pack</span>
            </summary>
            <div className="advanced-options-body">
              <div className="field">
                <label className="field-label" htmlFor="odin-model">
                  Odin&apos;s model <span className="field-hint">optional; a stronger model for the judge, same provider</span>
                </label>
                <select id="odin-model" value={odinChoice} onChange={(e) => setOdinChoice(e.target.value)} disabled={odinOptions.length === 0}>
                  <option value="">{picked?.provider.name === "anthropic" && !picked.model ? "Sonnet (the default split)" : "Same as the model above"}</option>
                  {odinOptions.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label className="field-label" htmlFor="corpus">
                  Runemark pack folder <span className="field-hint">inside the repository; defaults to dev_pack_E5</span>
                </label>
                <input id="corpus" className="mono-input" value={runemarkPath} onChange={(e) => setRunemarkPath(e.target.value)} placeholder="dev_pack_E5" />
              </div>
            </div>
          </details>

          <div className="submit-row">
            <p className="submit-note">
              Two bounded runs. Citations are checked against the corpus. Every model call is recorded, so the case can be replayed at $0.
            </p>
            <button className="btn btn-primary" disabled={busy || !question.trim() || !ready}>
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
