export type RunFinishNotification = {
  runId: number;
  status: string;
  matched: number;
  processed: number;
  expected: number;
  error?: string;
};

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

export function notifyRunFinished(payload: RunFinishNotification): void {
  if (!isNotificationSupported() || Notification.permission !== "granted") return;

  const { runId, status, matched, processed, expected, error } = payload;
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
    case "error":
      title = "Analisi fallita";
      body = error
        ? `Run #${runId}: ${error}`
        : `Run #${runId}: si è verificato un errore durante l'elaborazione.`;
      break;
    default:
      body = `Run #${runId}: stato ${status}.`;
  }

  const notification = new Notification(title, {
    body,
    tag: `trans-matching-run-${runId}`,
  });

  notification.onclick = () => {
    window.focus();
    notification.close();
  };
}
