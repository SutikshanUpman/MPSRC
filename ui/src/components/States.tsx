import type { ReactNode } from "react";

/* Designed states. No spinner is used anywhere in the interface. */

export function LoadingRecord({ label = "Reading the record", rows = 5 }: { label: string; rows?: number }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <span className="eyebrow">{label}</span>
      <div className="skeletons" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <span key={index} className="skeleton" style={{ width: `${[92, 78, 86, 64, 74, 88][index % 6]}%` }} />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  note,
  action,
  compact = false,
}: {
  title: string;
  note?: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`state state-empty${compact ? " state-compact" : ""}`}>
      <span className="state-rule" aria-hidden="true" />
      <h3 className="state-title">{title}</h3>
      {note && <p className="state-note">{note}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ title, message, action }: { title: string; message?: string; action?: ReactNode }) {
  return (
    <div className="state state-error" role="alert">
      <span className="eyebrow">Not completed</span>
      <h3 className="state-title">{title}</h3>
      {message && <p className="state-note state-message">{message}</p>}
      {action}
    </div>
  );
}

/** Damaged, unreadable or out-of-time items excluded from the record. */
export function DamagedNotice({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className="damaged" aria-label={title}>
      <header className="damaged-head">
        <span className="damaged-rule" aria-hidden="true" />
        <h3 className="damaged-title">{title}</h3>
        <span className="mono damaged-count">{items.length}</span>
      </header>
      <ul className="damaged-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

/** A column that received no challenge at all is stated, not implied. */
export function UnchallengedNote({ children }: { children: ReactNode }) {
  return (
    <p className="unchallenged">
      <span className="unchallenged-rule" aria-hidden="true" />
      {children}
    </p>
  );
}
