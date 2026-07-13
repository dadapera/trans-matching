import type { MatchResultDTO, ResultFilter } from "../types";
import { filterResults } from "../types";
import { ResultSummary } from "./ResultSummary";

interface Props {
  results: MatchResultDTO[];
  resultFilter: ResultFilter;
  onResultFilterChange: (filter: ResultFilter) => void;
  onSelectTrace: (traceId: string) => void;
}

export function ReportTable({
  results,
  resultFilter,
  onResultFilterChange,
  onSelectTrace,
}: Props) {
  if (results.length === 0) {
    return (
      <p className="empty-state">
        Il report si costruisce man mano: ogni transazione analizzata apparirà qui.
      </p>
    );
  }

  const visibleResults = filterResults(results, resultFilter);

  return (
    <div className="report-table-wrap">
      <ResultSummary
        results={results}
        filter={resultFilter}
        onFilterChange={onResultFilterChange}
      />
      {visibleResults.length === 0 ? (
        <p className="empty-state">Nessuna transazione corrisponde al filtro selezionato.</p>
      ) : (
      <table className="report-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Data</th>
            <th>Descrizione carta</th>
            <th>Importo</th>
            <th>Esito</th>
            <th>Conf.</th>
            <th>Gestionale</th>
            <th>Motivazione</th>
          </tr>
        </thead>
        <tbody>
          {visibleResults.map((row) => (
            <tr
              key={row.row_number}
              className={
                row.matched
                  ? "row--matched"
                  : row.ambiguous
                    ? "row--ambiguous"
                    : "row--unmatched"
              }
            >
              <td>
                <button
                  type="button"
                  className="link-btn mono"
                  onClick={() => onSelectTrace(row.trace_id)}
                >
                  {row.row_number}
                </button>
              </td>
              <td>{row.card.date}</td>
              <td className="cell-desc">{row.card.description}</td>
              <td className="mono">€{row.card.amount}</td>
              <td>
                <span className={`outcome outcome--${outcomeKey(row)}`}>{outcomeLabel(row)}</span>
              </td>
              <td>
                <span className={`conf conf--${row.confidence}`}>{row.confidence}</span>
              </td>
              <td className="cell-gestionale">
                {row.gestionale.length > 0
                  ? row.gestionale.map((g) => (
                      <div key={g.identificativo || g.description}>
                        <strong>{g.identificativo || "—"}</strong> {g.description} (€{g.amount})
                      </div>
                    ))
                  : row.alternatives.length > 0
                    ? row.alternatives.map((a) => (
                        <div key={a.identificativi.join(",")} className="alt-line">
                          Alt: {a.identificativi.join(", ")} ({a.confidence})
                        </div>
                      ))
                    : "—"}
              </td>
              <td className="cell-reason">{row.reason || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
    </div>
  );
}

function outcomeKey(row: MatchResultDTO): string {
  if (row.matched) return "matched";
  if (row.ambiguous) return "ambiguous";
  return "unmatched";
}

function outcomeLabel(row: MatchResultDTO): string {
  if (row.matched) return "Match";
  if (row.ambiguous) return "Ambiguo";
  return "—";
}
