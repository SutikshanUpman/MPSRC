import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, streamRun, type RunInput } from "../api";
import { EventLog } from "../components/EventLog";
import { Logo } from "../components/Logo";
import { Braid } from "../components/Ornaments";
import { ResultView } from "../components/ResultView";
import { RunForm } from "../components/RunForm";
import { SourcePanelProvider } from "../components/SourcePanel";
import { ErrorState } from "../components/States";
import { useTheme } from "../theme";
import type { Meta, ResultPayload, RunEvent, RunSummary } from "../types";

export function WorkspacePage() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [offline, setOffline] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [result, setResult] = useState<ResultPayload | null>(null);
  const [live, setLive] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closeStream = useRef<(() => void) | null>(null);
  const { theme, setTheme } = useTheme();

  const refreshRuns = useCallback(() => api.runs().then(setRuns).catch(() => undefined), []);

  useEffect(() => {
    api
      .meta()
      .then((value) => {
        setMeta(value);
        setOffline(false);
      })
      .catch(() => setOffline(true));
    refreshRuns();
    const wanted = new URLSearchParams(window.location.search).get("run");   // deep link: /app?run=<id>&tab=Exposure
    if (wanted) open(wanted);
    return () => closeStream.current?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshRuns]);

  const open = useCallback(
    (id: string) => {
      closeStream.current?.();
      setActiveId(id);
      setEvents([]);
      setResult(null);
      setError(null);
      setLive(true);
      closeStream.current = streamRun(id, (msg) => {
        if (msg.type === "event") setEvents((ev) => [...ev, msg.event]);
        else if (msg.type === "end") {
          setLive(false);
          if (msg.error) setError(msg.error);
          api
            .run(id)
            .then((r) => setResult(r.result))
            .catch((e: Error) => setError(e.message));
          refreshRuns();
        } else {
          setLive(false);
          setError(msg.error);
        }
      });
    },
    [refreshRuns],
  );

  const submit = async (input: RunInput) => {
    setError(null);
    setSubmitting(true);
    try {
      const run = await api.create(input);
      await refreshRuns();
      open(run.run_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const loadFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as ResultPayload;
      if (!parsed.schema_version?.startsWith("trial-")) throw new Error("not a trial record (schema_version trial-*)");
      closeStream.current?.();
      setActiveId(null);
      setEvents([]);
      setResult(parsed);
      setError(null);
      setOffline(false);
    } catch (e) {
      setError(`Could not open file: ${(e as Error).message}`);
    }
  };

  const replay = async () => {
    if (!activeId) return;
    setError(null);
    try {
      const run = await api.create({ profile: "replay", from: activeId.replace(/__replay$/, "") });
      await refreshRuns();
      open(run.run_id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const newCase = () => {
    closeStream.current?.();
    setActiveId(null);
    setResult(null);
    setEvents([]);
    setError(null);
  };

  const activeRun = runs.find((run) => run.run_id === activeId);

  return (
    <SourcePanelProvider>
      <div className="app workspace-app">
        <a className="skip-link" href="#main">
          Skip to the record
        </a>
        <header className="workspace-bar">
          <Link className="workspace-home" to="/" aria-label="Back to the Trial of the Nine Realms welcome page">
            <Logo size={24} />
            <span>
              <span className="workspace-bar-kicker">Ragnarok</span>
              <strong>Trial Console</strong>
            </span>
          </Link>
          <span className="workspace-location">{activeId ? "Reading a trial record" : "Open a new case"}</span>
          <nav aria-label="Workspace navigation">
            <Link to="/how-it-works">How it works</Link>
            <Link to="/">Welcome</Link>
          </nav>
        </header>
        <Braid className="page-rule workspace-rule" />

        <div className="shell">
          <aside className="rail" aria-label="Cases and providers">
            <div className="rail-head">
              <button className="brand" onClick={newCase} aria-label="Trial of the Nine Realms, open a new case">
                <Logo />
                <span className="brand-text">
                  <span className="eyebrow">Ragnarok Trial Console</span>
                  <span className="wordmark">Nine Realms</span>
                </span>
              </button>
              <p className="rail-note">
                Open a case, follow the trial, and read the briefing back to its sources.
              </p>
              <div className="rail-actions">
                <button className="btn btn-primary" onClick={newCase}>
                  New case
                </button>
                <label className="btn btn-quiet file-btn">
                  Open file
                  <input
                    type="file"
                    accept="application/json,.json"
                    onChange={(e) => {
                      void loadFile(e.target.files?.[0]);
                      e.currentTarget.value = "";
                    }}
                  />
                </label>
              </div>
            </div>

            <section className="rail-section">
              <h2 className="rail-title">Cases</h2>
              {runs.length === 0 ? (
                <p className="rail-empty">No case on this server yet. Open one, or run python scripts/run_case.py --demo.</p>
              ) : (
                <ul className="ledger">
                  {runs.map((run) => (
                    <li key={run.run_id} className={run.run_id === activeId ? "is-active" : ""}>
                      <button className="ledger-item" onClick={() => open(run.run_id)} aria-current={run.run_id === activeId}>
                        <span className="ledger-q">{run.question}</span>
                        <span className="ledger-meta">
                          <span>{run.provider ?? run.mode}</span>
                          <span className="ledger-state">{run.status}</span>
                          <span className="mono">{run.created_at.slice(0, 10)}</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {meta && (
              <section className="rail-section">
                <h2 className="rail-title">Providers</h2>
                <ul className="instruments">
                  {meta.providers.map((provider) => (
                    <li key={provider.name}>
                      <span>{provider.name.replace(/_/g, " ")}</span>
                      <span className="mono instrument-state" title={provider.description}>{provider.configured ? "ready" : "CLI only"}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="rail-foot">
              <button
                className="theme-switch"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                aria-pressed={theme === "dark"}
              >
                <span className="theme-label">Theme</span>
                <span className="mono">{theme}</span>
              </button>
              <span className="mono rail-version">v{meta?.version ?? "1.0"}</span>
            </div>
          </aside>

          <main className="main" id="main" tabIndex={-1}>
            <div className="sheet">
              {offline && (
                <div className="notice" role="status">
                  <span className="eyebrow">Server unavailable</span>
                  <p>
                    Start the console with <code>python server.py</code>, or open a saved trial record (JSON) to
                    read it offline.
                  </p>
                </div>
              )}
              {error && (
                <ErrorState
                  title="The case could not be opened"
                  message={error}
                  action={
                    <button className="btn btn-quiet" onClick={() => setError(null)}>
                      Dismiss
                    </button>
                  }
                />
              )}
              {!activeId && !result && <RunForm meta={meta} busy={submitting} onSubmit={submit} />}
              {(activeId || events.length > 0) && !result && (
                <EventLog
                  events={events}
                  live={live}
                  question={activeRun?.question}
                  status={activeRun?.status}
                  onOpen={activeId ? () => open(activeId) : undefined}
                />
              )}
              {result && <ResultView result={result} onReplay={activeId ? replay : undefined} />}
            </div>
            <footer className="colophon">
              <span className="mono">Trial of the Nine Realms {meta?.version ?? "1.0"}</span>
              <span>Runemark pack · mock and replay only</span>
            </footer>
          </main>
        </div>
      </div>
    </SourcePanelProvider>
  );
}
