export function formatRunCost(usd: number | null | undefined): string | null {
  if (usd == null || Number.isNaN(usd)) return null;
  return `$${usd.toFixed(4)}`;
}
