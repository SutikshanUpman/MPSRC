import type { RunemarkFeedItem } from "../types";

const WIDTH = 860;
const HEIGHT = 128;
const TOP = 28;
const BOTTOM = 34;
const SIDE = 10;

export function quarterOf(iso: string) {
  const year = iso.slice(0, 4);
  const month = Number(iso.slice(5, 7));
  return `${year}-Q${Math.ceil(month / 3)}`;
}

export function quarterLabel(key: string) {
  const [year, quarter] = key.split("-");
  return { quarter, year, full: `${quarter} ${year}` };
}

/** Documents per populated quarter. A column filters the list. */
export function DispatchTimeline({
  items,
  period,
  onPeriod,
}: {
  items: RunemarkFeedItem[];
  period: string | null;
  onPeriod: (period: string | null) => void;
}) {
  const counts = new Map<string, number>();
  for (const item of items) {
    if (!/^\d{4}-\d{2}/.test(item.published_at)) continue;
    const key = quarterOf(item.published_at);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const keys = [...counts.keys()].sort();
  if (keys.length === 0) return null;

  const shown = keys.slice(-12);
  const omitted = keys.length - shown.length;
  const max = Math.max(...shown.map((key) => counts.get(key) ?? 0), 1);
  const baseline = HEIGHT - BOTTOM;
  const band = (WIDTH - SIDE * 2) / shown.length;
  const barWidth = Math.max(10, Math.min(44, band * 0.42));
  const plotHeight = baseline - TOP - 10;

  return (
    <figure className="timeline">
      <figcaption className="timeline-head">
        <span className="eyebrow">Documents by quarter · admitted only</span>
        <span className="timeline-actions">
          {period && <span className="mono timeline-current">{quarterLabel(period).full}</span>}
          <button type="button" className="link-btn" onClick={() => onPeriod(null)} disabled={!period}>
            All quarters
          </button>
        </span>
      </figcaption>
      <div className="timeline-scroll">
        <svg
          className="timeline-svg"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="group"
          aria-label="Documents per quarter; select a quarter to filter the list"
        >
          <line className="tl-axis" x1={SIDE} x2={WIDTH - SIDE} y1={baseline} y2={baseline} />
          {shown.map((key, index) => {
            const count = counts.get(key) ?? 0;
            const centre = SIDE + band * (index + 0.5);
            const height = Math.max(3, (count / max) * plotHeight);
            const active = period === key;
            const label = quarterLabel(key);
            return (
              <g
                key={key}
                className={`tl-col${active ? " is-active" : ""}`}
                role="button"
                tabIndex={0}
                aria-pressed={active}
                aria-label={`${label.full}: ${count} ${count === 1 ? "document" : "documents"}`}
                onClick={() => onPeriod(active ? null : key)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onPeriod(active ? null : key);
                  }
                }}
              >
                <rect
                  className="tl-hit"
                  x={centre - band / 2}
                  y={TOP - 14}
                  width={band}
                  height={baseline - TOP + 20}
                />
                <rect
                  className="tl-bar"
                  x={centre - barWidth / 2}
                  y={baseline - height}
                  width={barWidth}
                  height={height}
                />
                <text className="tl-count" x={centre} y={baseline - height - 7} textAnchor="middle">
                  {count}
                </text>
                <text className="tl-label" x={centre} y={baseline + 16} textAnchor="middle">
                  {label.quarter}
                </text>
                <text className="tl-year" x={centre} y={baseline + 27} textAnchor="middle">
                  {label.year}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      {omitted > 0 && <p className="timeline-note">Twelve most recent quarters shown; {omitted} earlier quarters remain in the list.</p>}
    </figure>
  );
}
