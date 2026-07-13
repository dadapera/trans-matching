export function formatGestionaleMatchLabel(identificativo?: string): string {
  const cleaned = identificativo?.trim();
  if (!cleaned) return "—";
  if (cleaned.includes("|")) return cleaned;
  return `[${cleaned}]`;
}

export function formatGestionaleMatchLine(
  identificativo: string | undefined,
  description: string,
  amount: string,
): string {
  const label = formatGestionaleMatchLabel(identificativo);
  return `${label} ${description} (€${amount})`;
}
