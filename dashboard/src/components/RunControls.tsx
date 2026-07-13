import { Loader2, Play, Square } from "lucide-react";

interface Props {
  ready: boolean;
  running: boolean;
  starting: boolean;
  runId: number | null;
  processed: number;
  expected: number;
  matchedCount: number;
  status: string;
  onStart: () => void;
  onStop: () => void;
  error: string | null;
}

export function RunControls({
  ready,
  running,
  starting,
  runId,
  processed,
  expected,
  matchedCount,
  status,
  onStart,
  onStop,
  error,
}: Props) {
  const pct = expected > 0 ? Math.round((processed / expected) * 100) : 0;
  const pending = starting || running;
  const statusBadgeStatus = starting ? "running" : status;
  const statusBadgeLabel = starting ? "Avvio…" : statusLabel(status);

  return (
    <section className="panel run-controls">
      <h2>Analisi</h2>
      <div className="status-row">
        <span className={`status-badge status-badge--${statusBadgeStatus}`}>
          {pending && <Loader2 size={12} className="status-badge__spinner" />}
          {statusBadgeLabel}
        </span>
        {runId !== null && <span className="run-id">Run #{runId}</span>}
      </div>

      {expected > 0 && (
        <div className="progress-block">
          <div className="progress-meta">
            <span>
              {processed} / {expected} transazioni
            </span>
            <span>{matchedCount} match</span>
          </div>
          <div className="progress-bar">
            <div className="progress-bar__fill" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      <div className="btn-row">
        {!pending && (
          <button
            type="button"
            className="btn btn--primary"
            disabled={!ready}
            onClick={onStart}
          >
            <Play size={16} />
            Avvia
          </button>
        )}
        <button
          type="button"
          className="btn btn--danger"
          disabled={!pending}
          onClick={onStop}
        >
          <Square size={16} />
          Stop
        </button>
      </div>

      {!ready && !pending && (
        <p className="hint-text">Carica carta (CSV/PDF) e gestionale PDF per avviare.</p>
      )}
      {error && <p className="error-text">{error}</p>}
    </section>
  );
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    idle: "In attesa",
    running: "In esecuzione",
    completed: "Completata",
    stopped: "Interrotta",
    error: "Errore",
    stopping: "Arresto…",
  };
  return labels[status] ?? status;
}
