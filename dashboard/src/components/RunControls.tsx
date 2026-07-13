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
  const startLabel = running ? "In esecuzione" : starting ? "Avvio…" : "Avvia";

  return (
    <section className="panel run-controls">
      <h2>Analisi</h2>
      <div className="status-row">
        <span className={`status-badge status-badge--${status}`}>{statusLabel(status)}</span>
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
        <button
          type="button"
          className={`btn btn--primary${pending ? " btn--loading" : ""}`}
          disabled={!ready || pending}
          onClick={onStart}
          aria-busy={pending}
        >
          {pending ? <Loader2 size={16} className="btn__spinner" /> : <Play size={16} />}
          {startLabel}
        </button>
        <button
          type="button"
          className="btn btn--danger"
          disabled={!running}
          onClick={onStop}
        >
          <Square size={16} />
          Stop
        </button>
      </div>

      {!ready && !running && (
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
