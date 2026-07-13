import type { MatchAlternativeDTO } from "../types";

export function formatAlternativeLabel(alt: MatchAlternativeDTO): string {
  const ids = alt.identificativi.map((id) => id.trim()).filter(Boolean);
  if (ids.length > 0) return ids.join(", ");
  const preview = alt.gestionale_preview?.trim();
  if (preview) return preview;
  const reason = alt.reason.trim();
  if (reason) return reason;
  return "—";
}
