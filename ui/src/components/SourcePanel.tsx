import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api";
import { formatDay } from "../format";
import { LoadingRecord } from "./States";

export interface SourceRequest {
  runId: string;
  sourceId: string;
  fallback?: {
    id?: string;
    title?: string;
    excerpt?: string;
    published_at?: string;
    source_name?: string;
    reliability?: number;
  };
}

interface SourceContextValue {
  open: (request: SourceRequest) => void;
}

const SourceContext = createContext<SourceContextValue | null>(null);

export function useSource() {
  return useContext(SourceContext) ?? { open: () => undefined };
}

type Scalar = string | number | boolean | null;

interface SourceRecord {
  kind: string;
  item: Record<string, unknown>;
}

const HIDDEN = new Set([
  "text",
  "excerpt",
  "metadata",
  "path",
  "content_sha256",
  "published_at",
  "id",
  "title",
]);

/* Document metadata is rendered in its own block; do not repeat it above. */
const META_DUPLICATES = new Set(["source_name", "source_type", "reliability", "country", "sector", "event_id", "format", "readable"]);

function scalars(record: Record<string, unknown>, kind?: string): [string, Scalar][] {
  return Object.entries(record).filter(
    (entry): entry is [string, Scalar] =>
      !HIDDEN.has(entry[0]) &&
      !(kind === "document" && META_DUPLICATES.has(entry[0])) &&
      (entry[1] === null || ["string", "number", "boolean"].includes(typeof entry[1])),
  );
}

function titleOf(data: SourceRecord | null, fallback?: SourceRequest["fallback"]) {
  if (data) {
    const item = data.item;
    const meta = item.metadata as Record<string, unknown> | undefined;
    if (data.kind === "trade_row") {
      const route = [item.country_from, item.country_to].filter(Boolean).join(" to ");
      return `${route || "Trade row"} · ${String(item.sector ?? "")} ${String(item.month ?? "")}`.trim();
    }
    return String(item.title ?? meta?.title ?? fallback?.title ?? "Untitled document");
  }
  return fallback?.title ?? "Source document";
}

function identOf(data: SourceRecord | null, fallback?: SourceRequest["fallback"]) {
  if (data?.kind === "trade_row") {
    return [data.item.table_id, data.item.row_id].filter(Boolean).join(":");
  }
  if (data) return String(data.item.id ?? "");
  return fallback?.id ?? "";
}

export function SourcePanelProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<SourceRequest | null>(null);
  const [data, setData] = useState<SourceRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  const open = useCallback((next: SourceRequest) => {
    restoreRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setRequest(next);
  }, []);

  const close = useCallback(() => {
    setRequest(null);
    restoreRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!request) return;
    let alive = true;
    setData(null);
    setError(null);
    setLoading(true);
    api
      .source(request.runId, request.sourceId)
      .then((payload) => alive && setData(payload as unknown as SourceRecord))
      .catch((reason: Error) => alive && setError(reason.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [request]);

  useEffect(() => {
    if (!request) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
    };
  }, [request, close]);

  const fallback = request?.fallback;
  const longText = data
    ? String(data.item.text ?? data.item.excerpt ?? "")
    : [fallback?.excerpt].filter(Boolean).join("");
  const meta = data?.item.metadata as Record<string, unknown> | undefined;
  const tier = data?.item.reliability ?? meta?.reliability ?? fallback?.reliability;
  const sourceName = fallback?.source_name ?? (meta?.source_name != null ? String(meta.source_name) : undefined);

  return (
    <SourceContext.Provider value={{ open }}>
      {children}
      {request && (
        <>
          <div className="sp-scrim" onClick={close} aria-hidden="true" />
          <div
            className="sp"
            role="dialog"
            aria-modal="true"
            aria-labelledby="sp-title"
            ref={panelRef}
          >
            <header className="sp-head">
              <span className="eyebrow">
                {data?.kind === "trade_row" ? "Trade row" : "Source document"}
                {!data && fallback ? " · cited excerpt" : ""}
              </span>
              <h2 className="sp-title" id="sp-title">
                {titleOf(data, fallback)}
              </h2>
              <div className="sp-ident">
                <code>{identOf(data, fallback) || request.sourceId}</code>
                <span className="mono">
                  {formatDay(String(data?.item.published_at ?? meta?.published_at ?? fallback?.published_at ?? ""))}
                </span>
                {sourceName && <span className="sp-source">{sourceName}</span>}
                {tier != null && <span className="mono">T{String(tier)}</span>}
              </div>
              <button className="sp-close" onClick={close} ref={closeRef} aria-label="Close source panel">
                Close
              </button>
            </header>

            <div className="sp-body">
              {loading && <LoadingRecord label="Fetching the sealed copy" rows={4} />}
              {error && (
                <div className="sp-offline">
                  <span className="eyebrow">Body unavailable</span>
                  <p>
                    The sealed copy could not be read in this session. The cited excerpt is shown below and the
                    citation itself remains part of the record.
                  </p>
                  <p className="mono sp-error">{error}</p>
                </div>
              )}
              {data && scalars(data.item, data.kind).length > 0 && (
                <dl className="sp-facts">
                  {data.kind === "trade_row" &&
                    [
                      ["Value", `${Number(data.item.value).toLocaleString()} ${String(data.item.value_unit ?? "")}`],
                      ["Volume", `${Number(data.item.volume).toLocaleString()} ${String(data.item.volume_unit ?? "")}`],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd className="mono">{value}</dd>
                      </div>
                    ))}
                  {scalars(data.item, data.kind)
                    .filter(([key]) => !(data.kind === "trade_row" && ["value", "volume"].includes(key)))
                    .map(([key, value]) => (
                      <div key={key}>
                        <dt>{key.replace(/_/g, " ")}</dt>
                        <dd className={typeof value === "number" ? "mono" : ""}>{String(value)}</dd>
                      </div>
                    ))}
                </dl>
              )}
              {data && meta && (
                <dl className="sp-facts">
                  {Object.entries(meta)
                    .filter(([, value]) => value !== null && ["string", "number", "boolean"].includes(typeof value))
                    .map(([key, value]) => (
                      <div key={key}>
                        <dt>{key.replace(/_/g, " ")}</dt>
                        <dd>{String(value)}</dd>
                      </div>
                    ))}
                </dl>
              )}
              {longText && (
                <div className="sp-text">
                  <span className="eyebrow">{error ? "Cited excerpt" : "Document text"}</span>
                  <p className="sp-prose">{longText}</p>
                </div>
              )}
              {!loading && !error && !longText && (
                <p className="state-note">This source has no stored body text.</p>
              )}
            </div>
          </div>
        </>
      )}
    </SourceContext.Provider>
  );
}
