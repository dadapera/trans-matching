import type {
  MatchResultDTO,
  RunListItem,
  RunStartRequest,
  RunStatus,
  SessionInfo,
  UploadResponse,
  UploadStatus,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try {
      const json = JSON.parse(body);
      detail = json.detail ?? body;
    } catch {
      /* use raw body */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/api/session");
}

export async function fetchUploadStatus(): Promise<UploadStatus> {
  return request<UploadStatus>("/api/session/upload");
}

/** Upload files, then poll until OCR/parsing finishes (can take minutes for PDFs). */
export async function uploadFiles(carta: File, gestionale: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("carta", carta);
  form.append("gestionale", gestionale);
  await request<{ status: string }>("/api/session/upload", { method: "POST", body: form });

  const started = Date.now();
  const maxMs = 15 * 60 * 1000;
  while (Date.now() - started < maxMs) {
    await sleep(2000);
    const status = await fetchUploadStatus();
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
