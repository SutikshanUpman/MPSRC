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

const RUNNABLE = ["ollama", "openai", "anthropic"] as const;

export function RunForm({
  meta,
  busy,
  onSubmit,
}: {
  meta: Meta | null;
  busy: boolean;
  onSubmit: (input: RunInput) => void;
}) {
  const providers = useMemo(() => (meta?.providers ?? []).filter((p) => (RUNNABLE as readonly string[]).includes(p.name)), [meta]);
  const [question, setQuestion] = useState("");
  const [asOf, setAsOf] = useState("");
  const [runemarkPath, setRunemarkPath] = useState("");
  const [providerName, setProviderName] = useState<RunInput["provider"] | "">("");
  const [model, setModel] = useState("");
  const [odinModel, setOdinModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  // Start on the first provider that is ready; keep the user's choice once they make one.
  useEffect(() => {
    if (providerName || providers.length === 0) return;
    const ready = providers.find((p) => p.configured) ?? providers[0];
    setProviderName(ready.name as RunInput["provider"]);
  }, [providers, providerName]);

  const provider: ProviderInfo | undefined = providers.find((p) => p.name === providerName);
  useEffect(() => {
    setModel(provider?.default_model ?? "");
    setOdinModel("");
  }, [provider?.name, provider?.default_model]);

  const needsModel = provider?.needs_model ?? false;
  const ready = Boolean(provider?.configured) && (!needsModel || model.trim().length > 0);

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
            if (!question.trim() || !ready || !providerName) return;
            onSubmit({
              question,
              mode: "trial",
              provider: providerName,
              model: model.trim() || undefined,
              odin_model: odinModel.trim() || undefined,
              base_url: baseUrl.trim() || undefined,
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

          <fieldset className="field proceeding">
            <legend className="field-label">
              Run the agents on <span className="field-hint">keys stay in the server&apos;s environment; the page never sees them</span>
            </legend>
            <div className="mode-list">
              {providers.map((p) => (
                <label key={p.name} className={`mode${providerName === p.name ? " is-selected" : ""}`}>
                  <input type="radio" name="provider" value={p.name} checked={providerName === p.name} onChange={() => setProviderName(p.name as RunInput["provider"])} />
                  <span className="mode-name">
                    {p.label}
                    <em className="mono provider-state">
                      {p.configured ? (p.free ? "ready · free" : "ready · metered") : "not set up"}
                    </em>
                  </span>
                </label>
              ))}
            </div>
            {provider && <p className="mode-note">{provider.description}</p>}
            {provider && !provider.configured && provider.hint && <p className="mode-note provider-hint">{provider.hint}</p>}
          </fieldset>

          {provider && (
            <div className="field-row">
              <div className="field">
                <label className="field-label" htmlFor="model">
                  Model <span className="field-hint">{needsModel ? "Heimdall, Thor, Loki and Odin" : "optional; the configured Haiku/Sonnet split by default"}</span>
                </label>
                {provider.models.length > 0 ? (
                  <>
                    <input
                      id="model"
                      className="mono-input"
                      list="model-options"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      placeholder={provider.default_model ?? "model name"}
                      required={needsModel}
                    />
                    <datalist id="model-options">
                      {provider.models.map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                  </>
                ) : (
                  <input
                    id="model"
                    className="mono-input"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder={provider.name === "ollama" ? "e.g. qwen2.5:14b  (ollama pull it first)" : "e.g. gpt-4o-mini"}
                    required={needsModel}
                  />
                )}
              </div>
              <div className="field">
                <label className="field-label" htmlFor="as-of">
                  As-of date <span className="field-hint">optional; the question&apos;s own date wins</span>
                </label>
                <input id="as-of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
              </div>
            </div>
          )}

          <details className="advanced-options">
            <summary>
              <span>Advanced</span>
              <span className="field-hint">Odin&apos;s model, endpoint, Runemark pack</span>
            </summary>
            <div className="advanced-options-body">
              <div className="field">
                <label className="field-label" htmlFor="odin-model">
                  Odin&apos;s model <span className="field-hint">optional; a stronger model for the judge</span>
                </label>
                <input id="odin-model" className="mono-input" value={odinModel} onChange={(e) => setOdinModel(e.target.value)} placeholder={model || "same as above"} />
              </div>
              {provider && provider.name !== "anthropic" && (
                <div className="field">
                  <label className="field-label" htmlFor="base-url">
                    Endpoint <span className="field-hint">a local server only (localhost); remote ones are set in the server&apos;s environment</span>
                  </label>
                  <input
                    id="base-url"
                    className="mono-input"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder={provider.name === "ollama" ? "http://127.0.0.1:11434" : "http://127.0.0.1:1234/v1"}
                  />
                </div>
              )}
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
              {provider && !provider.free && " This provider is metered: the per-case cap, Odin's reserve and the project ledger apply."}
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
