import type { TrialClass } from "../types";

const LABELS: Record<TrialClass, string> = {
  established: "Established",
  contested: "Contested",
  conceded: "Conceded",
  rejected: "Rejected",
};

const ORDER: TrialClass[] = ["established", "contested", "conceded", "rejected"];

/**
 * One cell per ruling. The mark carries the class: filled, inset, dashed
 * outline, struck. Counts are written out beside it, never colour alone.
 */
export function RulingComposition({ counts }: { counts: Record<TrialClass, number> }) {
  const total = ORDER.reduce((sum, tone) => sum + counts[tone], 0);
  if (total === 0) return null;

  const groups = ORDER.map((tone) => ({
    tone,
    cells: Array.from({ length: counts[tone] }, (_, index) => ({ tone, key: `${tone}-${index}` })),
  }));

  return (
    <figure
      className="composition"
      aria-label={`Ruling composition: ${ORDER.map((tone) => `${counts[tone]} ${LABELS[tone].toLowerCase()}`).join(", ")}`}
    >
      <div className="composition-matrix" aria-hidden="true">
        {groups.map((group) =>
          group.cells.length > 0 ? (
            <span className={`comp-group comp-group-${group.tone}`} key={group.tone}>
              {group.cells.map((cell) => (
                <span key={cell.key} className={`comp-cell comp-${cell.tone}`} />
              ))}
            </span>
          ) : null,
        )}
      </div>
      <figcaption className="composition-key">
        {ORDER.map((tone) => (
          <span key={tone} className={`composition-item comp-${tone}`}>
            <i aria-hidden="true" />
            {LABELS[tone]}
            <b className="mono">{String(counts[tone]).padStart(2, "0")}</b>
          </span>
        ))}
        <span className="composition-total mono">{String(total).padStart(2, "0")} rulings</span>
      </figcaption>
    </figure>
  );
}
