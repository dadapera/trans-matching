import { useCallback, useRef, useState } from "react";
import { FileText, Upload } from "lucide-react";
import type { UploadResponse } from "../types";

interface Props {
  disabled?: boolean;
  onUploaded: (info: UploadResponse) => void;
  cartaFilename?: string;
  gestionaleFilename?: string;
  cartaCount?: number;
  gestionaleCount?: number;
}

function DropZone({
  label,
  accept,
  filename,
  count,
  onFile,
  disabled,
}: {
  label: string;
  accept: string;
  filename?: string;
  count?: number;
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDrag(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) onFile(file);
    },
    [disabled, onFile],
  );

  return (
    <div
      className={`dropzone ${drag ? "dropzone--drag" : ""} ${disabled ? "dropzone--disabled" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && !disabled && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
      <Upload size={20} className="dropzone__icon" />
      <span className="dropzone__label">{label}</span>
      {filename ? (
        <span className="dropzone__file">
          <FileText size={14} />
          {filename}
          {count !== undefined && <span className="dropzone__count">{count} transazioni</span>}
        </span>
      ) : (
        <span className="dropzone__hint">Trascina o clicca</span>
      )}
    </div>
  );
}

export function UploadPanel({
  disabled,
  onUploaded,
  cartaFilename,
  gestionaleFilename,
  cartaCount,
  gestionaleCount,
}: Props) {
  const [cartaFile, setCartaFile] = useState<File | null>(null);
  const [gestionaleFile, setGestionaleFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progressPct, setProgressPct] = useState(0);
  const [progressMessage, setProgressMessage] = useState("");

  const handleUpload = async () => {
    if (!cartaFile || !gestionaleFile) {
      setError("Seleziona entrambi i file");
      return;
    }
    setLoading(true);
    setError(null);
    setProgressPct(0);
    setProgressMessage("Upload in corso…");
    try {
      const { uploadFiles } = await import("../api");
      const res = await uploadFiles(cartaFile, gestionaleFile, (status) => {
        setProgressPct(status.progress_pct ?? 0);
        setProgressMessage(status.progress_message || "OCR / parsing in corso…");
      });
      setProgressPct(100);
      setProgressMessage("Completato");
      onUploaded(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload fallito");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="panel upload-panel">
      <h2>Documenti</h2>
      <DropZone
        label="Transazioni carta (CSV o PDF)"
        accept=".csv,.pdf"
        filename={cartaFilename ?? cartaFile?.name}
        count={cartaCount}
        onFile={setCartaFile}
        disabled={disabled}
      />
      <DropZone
        label="Gestionale (PDF)"
        accept=".pdf"
        filename={gestionaleFilename ?? gestionaleFile?.name}
        count={gestionaleCount}
        onFile={setGestionaleFile}
        disabled={disabled}
      />
      {(cartaFile || gestionaleFile) && !cartaFilename && (
        <button
          type="button"
          className="btn btn--primary btn--block"
          disabled={disabled || loading || !cartaFile || !gestionaleFile}
          onClick={handleUpload}
        >
          {loading ? "OCR / parsing in corso…" : "Conferma upload"}
        </button>
      )}
      {loading && (
        <div className="progress-block">
          <div className="progress-meta">
            <span>{progressMessage || "OCR / parsing in corso…"}</span>
            <span>{Math.round(progressPct)}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-bar__fill" style={{ width: `${progressPct}%` }} />
          </div>
          <p className="dropzone__hint">
            Il PDF Amex richiede OCR: può richiedere alcuni minuti. Non chiudere la pagina.
          </p>
        </div>
      )}
      {error && <p className="error-text">{error}</p>}
    </section>
  );
}
