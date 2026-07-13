import type { MatchAlternativeDTO } from "../types";

export function formatAlternativeLabel(alt: MatchAlternativeDTO): string {
  const ids = alt.identificativi.map((id) => id.trim()).filter(Boolean);
  if (ids.length > 0) return ids.join(", ");
  if (alt.gestionale_preview.trim()) return alt.gestionale_preview;
  if (alt.reason.trim()) return alt.reason;
  return "—";
}
