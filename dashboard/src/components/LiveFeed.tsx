import { useEffect, useRef } from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  GitBranch,
  HelpCircle,
  Wrench,
} from "lucide-react";
import type { AgentEvent } from "../types";

interface Props {
  events: AgentEvent[];
  filterTraceId: string | null;
  onFilterTrace: (traceId: string | null) => void;
}

const LIVE_EVENTS = new Set([
  "txn_start",
  "txn_end",
  "tool_call",
  "agent_step",
  "confidence_gate",
  "router_classify",
  "rate_limit_retry",
  "error",
  "run_started",
  "run_finished",
  "run_stopping",
  "run_error",
]);

export function LiveFeed({ events, filterTraceId, onFilterTrace }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  const filtered = events.filter((ev) => {
    const name = (ev.event ?? ev.type) as string;
    if (!LIVE_EVENTS.has(name) && ev.type !== "agent_event") return false;
    if (filterTraceId && ev.trace_id && ev.trace_id !== filterTraceId) return false;
    return true;
  });

  return (
    <div className="live-feed">
      {filterTraceId && (
        <div className="filter-bar">
          Filtro: <code>{filterTraceId}</code>
          <button type="button" className="link-btn" onClick={() => onFilterTrace(null)}>
            Rimuovi
          </button>
        </div>
      )}
      <div className="live-feed__list">
        {filtered.length === 0 && (
          <p className="empty-state">Gli eventi dell&apos;agente appariranno qui in tempo reale.</p>
        )}
        {filtered.map((ev, i) => (
          <EventLine key={`${ev.ts}-${i}`} event={ev} onFilterTrace={onFilterTrace} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function EventLine({
  event,
  onFilterTrace,
}: {
  event: AgentEvent;
  onFilterTrace: (id: string | null) => void;
}) {
  const name = (event.event ?? event.type) as string;
  const icon = eventIcon(name, event);
  const summary = formatEvent(name, event);

  return (
    <div className={`event-line event-line--${eventClass(name, event)}`}>
      <span className="event-line__icon">{icon}</span>
      <div className="event-line__body">
        <div className="event-line__head">
          <span className="event-line__type">{name}</span>
          {event.trace_id && (
            <button
              type="button"
              className="trace-chip"
              onClick={() => onFilterTrace(event.trace_id!)}
            >
              {event.trace_id}
            </button>
          )}
          {event.ts && <time className="event-line__time">{formatTime(event.ts)}</time>}
        </div>
        <p className="event-line__summary">{summary}</p>
      </div>
    </div>
  );
}

function eventIcon(name: string, event: AgentEvent) {
  if (name === "error" || name === "run_error") return <AlertCircle size={16} />;
  if (name === "tool_call") return <Wrench size={16} />;
  if (name === "agent_step") return <Bot size={16} />;
  if (name === "confidence_gate" || name === "txn_end") {
    return event.matched ? <CheckCircle2 size={16} /> : <HelpCircle size={16} />;
  }
  if (name === "router_classify") return <GitBranch size={16} />;
  return <Bot size={16} />;
}

function eventClass(name: string, event: AgentEvent): string {
  if (name === "error" || name === "run_error") return "error";
  if (name === "confidence_gate" || name === "txn_end") {
    return event.matched ? "success" : "neutral";
  }
  if (name === "tool_call") return "tool";
  return "default";
}

function formatEvent(name: string, event: AgentEvent): string {
  switch (name) {
    case "txn_start":
      return `#${event.row_number} ${String(event.card_description ?? "").slice(0, 60)} — €${event.card_amount}`;
    case "txn_end":
      return event.matched
        ? `Match (${event.confidence})`
        : `Nessun match (${event.confidence})`;
    case "tool_call": {
      const tool = event.tool as string | undefined;
      const phase = event.phase as string | undefined;
      if (phase === "start") return `→ ${tool}`;
      return `← ${tool}: ${String(event.output_summary ?? "").slice(0, 120)}`;
    }
    case "agent_step":
      return String(event.log ?? event.action ?? "").slice(0, 300);
    case "confidence_gate":
      return `Decisione: ${event.matched ? "match" : "no match"} (${event.confidence})`;
    case "router_classify":
      return `Categoria: ${event.category}`;
    case "rate_limit_retry":
      return `Retry ${event.attempt} tra ${event.wait_seconds}s`;
    case "error":
    case "run_error":
      return String(event.error ?? "Errore sconosciuto");
    case "run_finished":
      return `Fine run — ${event.matched}/${event.processed} match`;
    case "run_stopping":
      return "Arresto richiesto, attendo fine transazione corrente…";
    default:
      return JSON.stringify(
        Object.fromEntries(
          Object.entries(event).filter(([k]) => !["event", "type", "ts", "trace_id", "run_id"].includes(k)),
        ),
      ).slice(0, 200);
  }
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("it-IT");
  } catch {
    return iso;
  }
}
