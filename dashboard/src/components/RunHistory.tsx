import type { RunListItem } from "../types";

interface Props {
  runs: RunListItem[];
  activeRunId: number | null;
  onSelect: (runId: number) => void;
}

export function RunHistory({ runs, activeRunId, onSelect }: Props) {
  if (runs.length === 0) return null;

  return (
    <section className="panel run-history">
      <h2>Run recenti</h2>
      <ul className="run-history__list">
        {runs.map((run) => (
          <li key={run.id}>
            <button
              type="button"
              className={`run-history__item ${activeRunId === run.id ? "run-history__item--active" : ""}`}
              onClick={() => onSelect(run.id)}
            >
              <span className="run-history__id">#{run.id}</span>
              <span className={`status-badge status-badge--${run.status}`}>{run.status}</span>
              <span className="run-history__meta">
                {run.matched_count}/{run.total_transactions} match
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
