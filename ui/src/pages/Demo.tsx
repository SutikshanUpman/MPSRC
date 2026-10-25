import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ResultView } from "../components/ResultView";
import { SourcePanelProvider } from "../components/SourcePanel";
import { LoadingRecord, ErrorState } from "../components/States";
import type { ResultPayload } from "../types";

export function DemoPage() {
  const [result, setResult] = useState<ResultPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/qa-fixture.json")
      .then((response) => {
        if (!response.ok) throw new Error(`fixture request returned ${response.status}`);
        return response.json() as Promise<ResultPayload>;
      })
      .then((value) => alive && setResult(value))
      .catch((reason: Error) => alive && setError(reason.message));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <SourcePanelProvider>
      <section className="demo-page page-section" aria-labelledby="demo-title">
        <header className="demo-head">
          <div>
            <span className="roman-kicker">Read-only example · dev_pack_E5</span>
            <h1 id="demo-title">A real record, not a mock screen.</h1>
            <p>
              This page opens the corpus-backed QA fixture so you can see the briefing, the exposure ranges and the
              evidence trail before starting your own analysis.
            </p>
          </div>
          <Link className="btn btn-primary" to="/app">
            Open the console <span aria-hidden="true">↗</span>
          </Link>
        </header>

        {error && <ErrorState title="The read-only example could not be opened" message={error} />}
        {!error && !result && <LoadingRecord label="Opening the example record" rows={6} />}
        {result && <ResultView result={result} />}
      </section>
    </SourcePanelProvider>
  );
}
