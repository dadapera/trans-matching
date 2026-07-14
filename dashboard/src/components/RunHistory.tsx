import type { RunListItem } from "../types";
import { formatRunCost } from "../utils/formatCost";

interface Props {
  runs: RunListItem[];
  activeRunId: number | null;
  onSelect: (runId: number) => void;
}

function formatElapsed(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "-";
  const totalSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  if (minutes === 0) return `${remainingSeconds}s`;
  return `${minutes}m ${remainingSeconds.toString().padStart(2, "0")}s`;
}

export function RunHistory({ runs, activeRunId, onSelect }: Props) {
  if (runs.length === 0) return null;

  return (
    <section className="panel run-history">
      <h2>Run recenti</h2>
      <ul className="run-history__list">
        {runs.map((run) => {
          const cost = formatRunCost(run.llm_cost_usd);
          const elapsed = formatElapsed(run.elapsed_seconds);
          return (
            <li key={run.id}>
              <button
                type="button"
                className={`run-history__item ${activeRunId === run.id ? "run-history__item--active" : ""}`}
                onClick={() => onSelect(run.id)}
              >
                <span className="run-history__id">#{run.id}</span>
                <span className={`status-badge status-badge--${run.status}`}>{run.status}</span>
                <span className="run-history__meta">
                  {elapsed}
                  {cost ? ` · ${cost}` : ""}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
