export type RunFinishNotification = {
  runId: number;
  status: string;
  matched: number;
  processed: number;
  expected: number;
  error?: string;
};

export type ParsingCompletedNotification = {
  cartaCount: number;
  gestionaleCount: number;
  cartaFilename?: string;
  gestionaleFilename?: string;
};

function showNotification(title: string, body: string, tag: string): void {
  if (!isNotificationSupported() || Notification.permission !== "granted") return;

  const notification = new Notification(title, { body, tag });
  notification.onclick = () => {
    window.focus();
    notification.close();
  };
}

export function isNotificationSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export async function ensureNotificationPermission(): Promise<
  NotificationPermission | "unsupported"
> {
  if (!isNotificationSupported()) return "unsupported";
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  return Notification.requestPermission();
}

export function notifyParsingCompleted(payload: ParsingCompletedNotification): void {
  const { cartaCount, gestionaleCount } = payload;
  showNotification(
    "Parsing completato",
    `Carta: ${cartaCount} transazioni · Gestionale: ${gestionaleCount} documenti. Puoi avviare l'analisi.`,
    "trans-matching-parsing",
  );
}

export function notifyRunError(payload: {
  runId: number;
  error?: string;
  processed?: number;
  expected?: number;
}): void {
  const { runId, error, processed, expected } = payload;
  const progress =
    processed !== undefined && expected !== undefined
      ? ` (${processed}/${expected})`
      : "";
  showNotification(
    "Analisi fallita",
    error
      ? `Run #${runId}${progress}: ${error}`
      : `Run #${runId}${progress}: si è verificato un errore durante l'elaborazione.`,
    `trans-matching-run-${runId}`,
  );
}

export function notifyRunFinished(payload: RunFinishNotification): void {
  const { runId, status, matched, processed, expected, error } = payload;

  if (status === "error") {
    notifyRunError({ runId, error, processed, expected });
    return;
  }

  let title = "Trans Matching";
  let body = "";

  switch (status) {
    case "completed":
      title = "Analisi completata";
      body = `Run #${runId}: ${matched} match su ${processed} transazioni elaborate.`;
      break;
    case "stopped":
      title = "Analisi interrotta";
      body = `Run #${runId}: elaborate ${processed} di ${expected} transazioni.`;
      break;
    default:
      body = `Run #${runId}: stato ${status}.`;
  }

  showNotification(title, body, `trans-matching-run-${runId}`);
}
