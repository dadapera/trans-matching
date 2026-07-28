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
  runStatus: string;
  running: boolean;
}

export function ReportTable({
  results,
  resultFilter,
  onResultFilterChange,
  onSelectTrace,
  runStatus,
  running,
}: Props) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  if (results.length === 0) {
    return <EmptyReport runStatus={runStatus} running={running} />;
  }

  const reuseMap = buildGestionaleReuseMap(results);
  const visibleResults = resultFilter === "ambiguous"
    ? results.filter((row) => row.ambiguous || hasGestionaleReuse(row, reuseMap))
    : filterResults(results, resultFilter);

  const canExport = visibleResults.length > 0 && !exporting;
  const exportHint = exporting
    ? "Esportazione in corso…"
    : visibleResults.length === 0
      ? "Nessuna riga nel filtro attuale da esportare."
      : null;

  const handleExport = async () => {
    if (!canExport) return;
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
        <div className="report-export">
          <button
            type="button"
            className="btn btn--ghost"
            disabled={!canExport}
            title={exportHint ?? "Esporta le righe visibili in Excel"}
            onClick={() => void handleExport()}
          >
            <Download size={16} />
            {exporting ? "Esportazione…" : "Esporta XLSX"}
          </button>
          {exportHint && <p className="report-export__hint">{exportHint}</p>}
        </div>
      </div>
      {exportError && (
        <div className="error-panel" role="alert">
          <span className="error-panel__title">Esportazione</span>
          {exportError}
        </div>
      )}
      {visibleResults.length === 0 ? (
        <div className="empty-state empty-state--structured">
          <p className="empty-state__title">Nessuna riga per questo filtro</p>
          <p className="empty-state__body">
            Il filtro selezionato non corrisponde ad alcuna transazione del report.
          </p>
          <div className="empty-state__action">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => onResultFilterChange("all")}
            >
              Mostra tutte ({results.length})
            </button>
          </div>
        </div>
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
            <th>Gestionale / Info</th>
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
                {formatMscPassengers(row) && (
                  <div className="alt-line">MSC passeggeri: {formatMscPassengers(row)}</div>
                )}
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
                    : formatMscPassengers(row) ? null : "—"}
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

function EmptyReport({
  runStatus,
  running,
}: {
  runStatus: string;
  running: boolean;
}) {
  if (running) {
    return (
      <div className="empty-state empty-state--structured">
        <p className="empty-state__title">Report in costruzione</p>
        <p className="empty-state__body">
          Ogni transazione analizzata apparirà qui. Puoi seguire l&apos;attività live nell&apos;altra scheda.
        </p>
      </div>
    );
  }

  if (runStatus === "completed" || runStatus === "stopped") {
    return (
      <div className="empty-state empty-state--structured">
        <p className="empty-state__title">Nessun risultato in questa run</p>
        <p className="empty-state__body">
          La run è terminata senza righe di report. Controlla il subset o avvia una nuova analisi.
        </p>
      </div>
    );
  }

  if (runStatus === "error") {
    return (
      <div className="empty-state empty-state--structured">
        <p className="empty-state__title">Run interrotta da un errore</p>
        <p className="empty-state__body">
          Non ci sono risultati da mostrare. Controlla il messaggio di errore in Analisi e riprova.
        </p>
      </div>
    );
  }

  return (
    <div className="empty-state empty-state--structured">
      <p className="empty-state__title">Nessun report ancora</p>
      <p className="empty-state__body">
        Avvia un&apos;analisi dalla colonna sinistra. Il report si riempie man mano che le transazioni vengono elaborate.
      </p>
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
  if (formatMscPassengers(row)) return "Info MSC";
  return "—";
}

function formatMscPassengers(row: MatchResultDTO): string {
  const metadata = row.metadata;
  if (!metadata || typeof metadata !== "object") return "";
  const msc = metadata.msc;
  if (!msc || typeof msc !== "object" || Array.isArray(msc)) return "";
  const surnames = (msc as { passenger_surnames?: unknown }).passenger_surnames;
  if (!Array.isArray(surnames)) return "";
  return surnames.filter((item): item is string => typeof item === "string" && item.length > 0).join(", ");
}
