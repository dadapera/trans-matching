export interface TransactionDTO {
  date: string;
  description: string;
  amount: string;
  identificativo?: string;
}

export interface MatchAlternativeDTO {
  identificativi: string[];
  confidence: string;
  reason: string;
  gestionale_preview?: string;
}

export interface MatchResultDTO {
  row_number: number;
  trace_id: string;
  matched: boolean;
  confidence: string;
  reason: string;
  strategy: string;
  card: TransactionDTO;
  gestionale: TransactionDTO[];
  alternatives: MatchAlternativeDTO[];
  ambiguous: boolean;
  metadata?: Record<string, unknown>;
}

export interface UploadResponse {
  carta_count: number;
  gestionale_count: number;
  carta_filename: string;
  gestionale_filename: string;
}

export interface SessionInfo {
  ready: boolean;
  carta_count?: number;
  gestionale_count?: number;
  carta_filename?: string;
  gestionale_filename?: string;
  active_run_id?: number | null;
}

export interface RunStartRequest {
  row_start: number;
  row_end: number;
}

export interface RunStatus {
  run_id: number;
  status: string;
  processed: number;
  expected: number;
  matched_count: number;
  elapsed_seconds: number | null;
  log_path: string | null;
  openai_model: string | null;
  created_at?: string;
}

export interface RunListItem {
  id: number;
  status: string;
  created_at: string;
  total_transactions: number;
  matched_count: number;
  expected_transactions: number | null;
  elapsed_seconds: number | null;
  llm_cost_usd: number | null;
}

export interface AgentEvent {
  type?: string;
  event?: string;
  ts?: string;
  run_id?: number;
  trace_id?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

export type TabId = "live" | "report";

export type ResultFilter = "all" | "matched" | "ambiguous";

export function filterResults(
  results: MatchResultDTO[],
  filter: ResultFilter,
): MatchResultDTO[] {
  if (filter === "matched") return results.filter((row) => row.matched);
  if (filter === "ambiguous") return results.filter((row) => row.ambiguous);
  return results;
}

export function matchesResultFilter(
  result: MatchResultDTO | undefined,
  filter: ResultFilter,
): boolean {
  if (filter === "all") return true;
  if (!result) return false;
  if (filter === "matched") return result.matched;
  if (filter === "ambiguous") return result.ambiguous;
  return true;
}
