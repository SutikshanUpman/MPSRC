import { money } from "../format";
import type { ExposureRange } from "../types";

const WIDTH = 860;
const LEFT = 158;
const RIGHT = 138;
const TOP = 38;
const ROW = 58;
const BOTTOM = 34;

function niceStep(raw: number) {
  if (!Number.isFinite(raw) || raw <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(raw));
  const n = raw / power;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return step * power;
}

function scale(max: number) {
  const step = niceStep(max / 4);
  return { step, top: Math.max(step, Math.ceil(max / step) * step) };
}

/**
 * A range plot on one shared scale: Odin's range is the bar, the argued
 * bounds are ticks. Exact numerals remain in the table below.
 */
export function ExposurePlot({ rows }: { rows: ExposureRange[] }) {
  if (rows.length === 0) return null;
  const all = rows.flatMap((row) => [row.loki_low, row.thor_high, row.odin_low, row.odin_high]);
  const max = Math.max(...all.filter((value): value is number => value != null && Number.isFinite(value)), 0);
  const { step, top } = scale(max);
  const height = TOP + rows.length * ROW + BOTTOM;
  const plotRight = WIDTH - RIGHT;
  const x = (value: number) => LEFT + (value / top) * (plotRight - LEFT);
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, index) => index * step);
  const unit = rows[0]?.unit ?? "USD";

  return (
    <figure className="plot">
      <figcaption className="plot-cap">
        <span className="eyebrow">Range plot · one scale across rows</span>
        <span className="mono plot-unit">{unit} · compact</span>
      </figcaption>
      <div className="plot-scroll">
        <svg
          className="plot-svg"
          viewBox={`0 0 ${WIDTH} ${height}`}
          role="img"
          aria-label={`Exposure ranges for ${rows.map((row) => `${row.country} ${row.sector}`).join(", ")}. The bar is Odin's range; ticks mark the argued floor and ceiling.`}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line className="plot-grid-line" x1={x(tick)} x2={x(tick)} y1={TOP - 14} y2={TOP + rows.length * ROW - 10} />
              <text className="plot-tick-label" x={x(tick)} y={TOP - 22} textAnchor="middle">
                {tick === 0 ? "0" : money(tick, unit)}
              </text>
            </g>
          ))}

          {rows.map((row, index) => {
            const y = TOP + index * ROW;
            const low = row.odin_low ?? row.loki_low;
            const high = row.odin_high ?? row.thor_high;
            const floor = row.loki_low;
            const ceiling = row.thor_high;
            return (
              <g key={`${row.country}-${row.sector}`} className="plot-row">
                <title>
                  {`${row.country} ${row.sector}: ${money(low, row.unit)} to ${money(high, row.unit)}; ` +
                    `Loki floor ${money(floor, row.unit)}, Thor ceiling ${money(ceiling, row.unit)}`}
                </title>
                <text className="plot-country" x={LEFT - 14} y={y + 4} textAnchor="end">
                  {row.country}
                </text>
                <text className="plot-sector" x={LEFT - 14} y={y + 19} textAnchor="end">
                  {row.sector}
                  {row.period ? ` · ${row.period}` : ""}
                </text>
                <line className="plot-row-rule" x1={LEFT} x2={plotRight} y1={y + 11} y2={y + 11} />
                {low != null && high != null && (
                  <rect
                    className="plot-range"
                    x={x(low)}
                    y={y + 7}
                    width={Math.max(3, x(high) - x(low))}
                    height={8}
                  />
                )}
                {floor != null && (
                  <line className="plot-tick plot-floor" x1={x(floor)} x2={x(floor)} y1={y - 1} y2={y + 23} />
                )}
                {ceiling != null && (
                  <line className="plot-tick plot-ceiling" x1={x(ceiling)} x2={x(ceiling)} y1={y - 1} y2={y + 23} />
                )}
                <text className="plot-value" x={WIDTH - RIGHT + 16} y={y + 9}>
                  {row.status === "ASSESSED" ? `${money(low, row.unit)} – ${money(high, row.unit)}` : "Insufficient evidence"}
                </text>
                <text className="plot-confidence" x={WIDTH - RIGHT + 16} y={y + 23}>
                  {row.confidence == null ? "no confidence" : `${Math.round(row.confidence * 100)}% confidence`}
                </text>
              </g>
            );
          })}

          <line className="plot-axis" x1={LEFT} x2={plotRight} y1={TOP + rows.length * ROW - 10} y2={TOP + rows.length * ROW - 10} />
        </svg>
      </div>
      <div className="plot-legend">
        <span className="plot-key">
          <i className="plot-swatch plot-swatch-range" aria-hidden="true" />
          Odin range
        </span>
        <span className="plot-key">
          <i className="plot-swatch plot-swatch-floor" aria-hidden="true" />
          Loki floor
        </span>
        <span className="plot-key">
          <i className="plot-swatch plot-swatch-ceiling" aria-hidden="true" />
          Thor ceiling
        </span>
      </div>
    </figure>
  );
}
