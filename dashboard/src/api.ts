import type {
  MatchResultDTO,
  RunListItem,
  RunStartRequest,
  RunStatus,
  SessionInfo,
  UploadResponse,
  UploadStatus,
} from "./types";

function humanizeErrorBody(status: number, body: string): string {
  const trimmed = body.trim();
  if (trimmed.startsWith("<!DOCTYPE") || trimmed.startsWith("<html")) {
    if (status === 502 || status === 503 || status === 504) {
      return `Server temporaneamente non disponibile (${status}). Riprova tra poco.`;
    }
    return `Errore server (${status})`;
  }
  try {
    const json = JSON.parse(trimmed);
    const detail = json.detail ?? trimmed;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  } catch {
    return trimmed || `Errore HTTP ${status}`;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(humanizeErrorBody(res.status, body));
  }
  return res.json() as Promise<T>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isTransientNetworkError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  return (
    msg.includes("temporaneamente non disponibile") ||
    msg.includes("failed to fetch") ||
    msg.includes("networkerror") ||
    msg.includes("load failed")
  );
}

export async function fetchSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/api/session");
}

export async function fetchUploadStatus(): Promise<UploadStatus> {
  return request<UploadStatus>("/api/session/upload");
}

/** Upload files, then poll until OCR/parsing finishes (can take minutes for PDFs). */
export async function uploadFiles(
  carta: File,
  gestionale: File,
  onProgress?: (status: UploadStatus) => void,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("carta", carta);
  form.append("gestionale", gestionale);
  await request<{ status: string }>("/api/session/upload", { method: "POST", body: form });

  const started = Date.now();
  const maxMs = 15 * 60 * 1000;
  let sawProcessing = false;
  let transientFails = 0;

  while (Date.now() - started < maxMs) {
    await sleep(1000);
    let status: UploadStatus;
    try {
      status = await fetchUploadStatus();
      transientFails = 0;
    } catch (err) {
      // Instance restarts mid-OCR briefly return 502; keep polling a bit.
      if (isTransientNetworkError(err) && transientFails < 30) {
        transientFails += 1;
        onProgress?.({
          status: "processing",
          carta_count: 0,
          gestionale_count: 0,
          carta_filename: "",
          gestionale_filename: "",
          progress_message: "Server in ripresa, riprovo…",
          progress_pct: 0,
        });
        continue;
      }
      throw err;
    }

    if (status.status === "processing") {
      sawProcessing = true;
    }
    onProgress?.(status);

    if (status.status === "ready") {
      return {
        carta_count: status.carta_count,
        gestionale_count: status.gestionale_count,
        carta_filename: status.carta_filename,
        gestionale_filename: status.gestionale_filename,
      };
    }
    if (status.status === "error") {
      throw new Error(status.error || "Errore durante l'OCR/parsing");
    }
    if (status.status === "idle" && sawProcessing) {
      throw new Error(
        "Il server si è riavviato durante l'OCR (memoria insufficiente). Riprova o carica un CSV Amex.",
      );
    }
  }
  throw new Error("Timeout OCR/parsing: riprova o usa un CSV");
}

export async function startRun(options: RunStartRequest): Promise<{ run_id: number }> {
  return request<{ run_id: number }>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });
}

export async function stopRun(runId: number): Promise<void> {
  await request(`/api/runs/${runId}/stop`, { method: "POST" });
}

export async function fetchRunStatus(runId: number): Promise<RunStatus> {
  return request<RunStatus>(`/api/runs/${runId}`);
}

export async function fetchResults(runId: number): Promise<MatchResultDTO[]> {
  return request<MatchResultDTO[]>(`/api/runs/${runId}/results`);
}

export async function fetchRunList(): Promise<RunListItem[]> {
  return request<RunListItem[]>("/api/runs");
}

export function subscribeRunEvents(
  runId: number,
  onEvent: (data: Record<string, unknown>) => void,
  onError?: (err: Event) => void,
): () => void {
  const source = new EventSource(`/api/runs/${runId}/events`);

  source.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data) as Record<string, unknown>;
      onEvent(data);
    } catch {
      /* ignore malformed */
    }
  };

  source.onerror = (err) => {
    onError?.(err);
  };

  return () => source.close();
}
