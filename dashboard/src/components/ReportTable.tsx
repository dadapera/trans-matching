import { Download } from "lucide-react";
import { useState } from "react";
import type { MatchResultDTO, ResultFilter } from "../types";
import { filterResults } from "../types";
import { formatAlternativeLabel } from "../utils/alternatives";
import { formatGestionaleMatchLabel } from "../utils/gestionaleMatch";
import {
  buildGestionaleReuseMap,
  hasGestionaleReuse,
  reusedGestionaleLabels,
} from "../utils/gestionaleReuse";
import { exportReportXlsx } from "../utils/exportReport";
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
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  if (results.length === 0) {
    return (
      <p className="empty-state">
        Il report si costruisce man mano: ogni transazione analizzata apparirà qui.
      </p>
    );
  }

  const reuseMap = buildGestionaleReuseMap(results);
  const visibleResults = resultFilter === "ambiguous"
    ? results.filter((row) => row.ambiguous || hasGestionaleReuse(row, reuseMap))
    : filterResults(results, resultFilter);

  const handleExport = async () => {
    if (visibleResults.length === 0 || exporting) return;
    setExporting(true);
    setExportError(null);
    try {
      await exportReportXlsx(visibleResults, resultFilter);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Esportazione fallita");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="report-table-wrap">
      <div className="report-toolbar">
        <ResultSummary
          results={results}
          filter={resultFilter}
          onFilterChange={onResultFilterChange}
        />
        <button
          type="button"
          className="btn btn--ghost"
          disabled={visibleResults.length === 0 || exporting}
          onClick={() => void handleExport()}
        >
          <Download size={16} />
          {exporting ? "Esportazione…" : "Esporta XLSX"}
        </button>
      </div>
      {exportError && <p className="error-text">{exportError}</p>}
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
                hasGestionaleReuse(row, reuseMap)
                  ? "row--ambiguous"
                  : row.matched
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
                <span className={`outcome outcome--${outcomeKey(row, reuseMap)}`}>{outcomeLabel(row, reuseMap)}</span>
              </td>
              <td>
                <span className={`conf conf--${row.confidence}`}>{row.confidence}</span>
              </td>
              <td className="cell-gestionale">
                {row.gestionale.length > 0
                  ? row.gestionale.map((g) => (
                      <div key={g.identificativo || g.description}>
                        <strong>{formatGestionaleMatchLabel(g.identificativo)}</strong>{" "}
                        {g.description} (€{g.amount})
                      </div>
                    ))
                  : row.alternatives.length > 0
                    ? row.alternatives.map((a, index) => (
                        <div key={`${index}-${formatAlternativeLabel(a)}`} className="alt-line">
                          Alt: {formatAlternativeLabel(a)} ({a.confidence})
                        </div>
                      ))
                    : "—"}
                {reusedGestionaleLabels(row, reuseMap).map((label) => (
                  <div key={label} className="alt-line">
                    Ambiguità: {label}
                  </div>
                ))}
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

function outcomeKey(row: MatchResultDTO, reuseMap: Map<string, number[]>): string {
  if (hasGestionaleReuse(row, reuseMap)) return "ambiguous";
  if (row.matched) return "matched";
  if (row.ambiguous) return "ambiguous";
  return "unmatched";
}

function outcomeLabel(row: MatchResultDTO, reuseMap: Map<string, number[]>): string {
  if (hasGestionaleReuse(row, reuseMap)) return "Match ambiguo";
  if (row.matched) return "Match";
  if (row.ambiguous) return "Ambiguo";
  return "—";
}
