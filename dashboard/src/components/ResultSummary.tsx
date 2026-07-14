import type { MatchResultDTO, ResultFilter } from "../types";
import { buildGestionaleReuseMap, hasGestionaleReuse } from "../utils/gestionaleReuse";

interface Props {
  results: MatchResultDTO[];
  filter: ResultFilter;
  onFilterChange: (filter: ResultFilter) => void;
}

export function ResultSummary({ results, filter, onFilterChange }: Props) {
  const reuseMap = buildGestionaleReuseMap(results);
  const matched = results.filter((row) => row.matched).length;
  const ambiguous = results.filter((row) => row.ambiguous || hasGestionaleReuse(row, reuseMap)).length;

  const toggle = (next: ResultFilter) => {
    onFilterChange(filter === next ? "all" : next);
  };

  return (
    <div className="report-summary">
      <button
        type="button"
        className={`report-stat report-stat--ok${filter === "matched" ? " report-stat--active" : ""}`}
        onClick={() => toggle("matched")}
        aria-pressed={filter === "matched"}
      >
        {matched} match
      </button>
      <button
        type="button"
        className={`report-stat report-stat--warn${filter === "ambiguous" ? " report-stat--active" : ""}`}
        onClick={() => toggle("ambiguous")}
        aria-pressed={filter === "ambiguous"}
      >
        {ambiguous} ambigui
      </button>
      <button
        type="button"
        className={`report-stat${filter === "all" ? " report-stat--active" : ""}`}
        onClick={() => onFilterChange("all")}
        aria-pressed={filter === "all"}
      >
        {results.length} totali
      </button>
    </div>
  );
}
