import type {
  MatchResultDTO,
  RunListItem,
  RunStatus,
  SessionInfo,
  UploadResponse,
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

export async function fetchSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/api/session");
}

export async function uploadFiles(carta: File, gestionale: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("carta", carta);
  form.append("gestionale", gestionale);
  return request<UploadResponse>("/api/session/upload", { method: "POST", body: form });
}

export async function startRun(): Promise<{ run_id: number }> {
  return request<{ run_id: number }>("/api/runs", { method: "POST" });
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
