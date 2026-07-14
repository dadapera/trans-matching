import type { MatchResultDTO, TransactionDTO } from "../types";
import { formatGestionaleMatchLabel } from "./gestionaleMatch";

export function gestionaleReuseKey(item: TransactionDTO): string {
  const identificativo = item.identificativo?.trim();
  if (identificativo) return identificativo.toUpperCase();
  return `${item.date}|${item.amount}|${item.description}`.toUpperCase();
}

export function buildGestionaleReuseMap(results: MatchResultDTO[]): Map<string, number[]> {
  const usage = new Map<string, Set<number>>();

  for (const row of results) {
    const keys = new Set(row.gestionale.map(gestionaleReuseKey));
    for (const key of keys) {
      const rows = usage.get(key) ?? new Set<number>();
      rows.add(row.row_number);
      usage.set(key, rows);
    }
  }

  return new Map(
    Array.from(usage.entries()).map(([key, rows]) => [key, Array.from(rows).sort((a, b) => a - b)]),
  );
}

export function hasGestionaleReuse(row: MatchResultDTO, reuseMap: Map<string, number[]>): boolean {
  return row.gestionale.some((item) => (reuseMap.get(gestionaleReuseKey(item))?.length ?? 0) > 1);
}

export function reusedGestionaleLabels(
  row: MatchResultDTO,
  reuseMap: Map<string, number[]>,
): string[] {
  const labels: string[] = [];
  const seen = new Set<string>();

  for (const item of row.gestionale) {
    const key = gestionaleReuseKey(item);
    if (seen.has(key)) continue;
    seen.add(key);

    const rows = reuseMap.get(key) ?? [];
    if (rows.length <= 1) continue;
    labels.push(`${formatGestionaleMatchLabel(item.identificativo)} anche su transazioni #${rows.join(", #")}`);
  }

  return labels;
}
