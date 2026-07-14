import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  GitBranch,
  HelpCircle,
  Mail,
  Wrench,
} from "lucide-react";
import type { AgentEvent, MatchResultDTO, ResultFilter } from "../types";
import { matchesResultFilter } from "../types";
import { formatAlternativeLabel } from "../utils/alternatives";
import { formatGestionaleMatchLabel } from "../utils/gestionaleMatch";
import { buildGestionaleReuseMap, hasGestionaleReuse, reusedGestionaleLabels } from "../utils/gestionaleReuse";

interface Props {
  events: AgentEvent[];
  results: MatchResultDTO[];
  resultFilter: ResultFilter;
  filterTraceId: string | null;
  onFilterTrace: (traceId: string | null) => void;
}

interface TraceGroup {
  traceId: string;
  events: AgentEvent[];
  result?: MatchResultDTO;
}

const LIVE_EVENTS = new Set([
  "txn_start",
  "txn_end",
  "tool_call",
  "agent_step",
  "confidence_gate",
  "email_search",
  "llm_call",
  "pool_update",
  "router_classify",
  "rate_limit_retry",
  "error",
  "run_started",
  "run_finished",
  "run_stopping",
  "run_error",
]);

export function LiveFeed({
  events,
  results,
  resultFilter,
  filterTraceId,
  onFilterTrace,
}: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const [debugMode, setDebugMode] = useState(false);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) return;
    const list = listRef.current;
    list?.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
  }, [events.length, results.length]);

  const updateAutoScroll = () => {
    const list = listRef.current;
    if (!list) return;

    const distanceFromBottom = list.scrollHeight - list.scrollTop - list.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 80;
  };

  const systemEvents = events.filter((ev) => {
    const name = eventName(ev);
    return !ev.trace_id && LIVE_EVENTS.has(name);
  });

  const reuseMap = useMemo(() => buildGestionaleReuseMap(results), [results]);

  const traces = useMemo(() => {
    const groups = new Map<string, TraceGroup>();

    for (const event of events) {
      const name = eventName(event);
      const traceId = event.trace_id;
      if (!traceId || (!LIVE_EVENTS.has(name) && event.type !== "agent_event")) continue;

      const group = groups.get(traceId) ?? { traceId, events: [] };
      group.events.push(event);
      groups.set(traceId, group);
    }

    for (const result of results) {
      const group = groups.get(result.trace_id) ?? { traceId: result.trace_id, events: [] };
      group.result = result;
      groups.set(result.trace_id, group);
    }

    return Array.from(groups.values())
      .filter((group) => !filterTraceId || group.traceId === filterTraceId)
      .filter((group) => {
        if (resultFilter !== "ambiguous") return matchesResultFilter(group.result, resultFilter);
        return Boolean(group.result && (group.result.ambiguous || hasGestionaleReuse(group.result, reuseMap)));
      })
      .sort((a, b) => traceSortKey(a) - traceSortKey(b));
  }, [events, filterTraceId, resultFilter, results, reuseMap]);

  return (
    <div className="live-feed">
      <div className="live-feed__toolbar">
        {filterTraceId ? (
          <div className="filter-bar">
            Focus: <code>{filterTraceId}</code>
            <button type="button" className="link-btn" onClick={() => onFilterTrace(null)}>
              Mostra tutte
            </button>
          </div>
        ) : (
          <span className="live-feed__hint">Monitoraggio aggregato per transazione</span>
        )}
        <div className="mode-switch" aria-label="Modalita log">
          <button
            type="button"
            className={`mode-switch__btn ${!debugMode ? "mode-switch__btn--active" : ""}`}
            onClick={() => setDebugMode(false)}
          >
            Normale
          </button>
          <button
            type="button"
            className={`mode-switch__btn ${debugMode ? "mode-switch__btn--active" : ""}`}
            onClick={() => setDebugMode(true)}
          >
            Debug
          </button>
        </div>
      </div>

      <div className="live-feed__list" ref={listRef} onScroll={updateAutoScroll}>
        {systemEvents.length > 0 && !filterTraceId && (
          <div className="run-events">
            {systemEvents.map((event, i) => (
              <RunEvent key={`${event.ts ?? eventName(event)}-${i}`} event={event} />
            ))}
          </div>
        )}
        {traces.length === 0 && (
          <p className="empty-state">Gli eventi dell&apos;agente appariranno qui in tempo reale.</p>
        )}
        {traces.map((trace) => (
          <TraceCard
            key={trace.traceId}
            trace={trace}
            debugMode={debugMode}
            hasReuse={trace.result ? hasGestionaleReuse(trace.result, reuseMap) : false}
            reuseLabels={trace.result ? reusedGestionaleLabels(trace.result, reuseMap) : []}
            focused={trace.traceId === filterTraceId}
            onFilterTrace={onFilterTrace}
          />
        ))}
      </div>
    </div>
  );
}

function TraceCard({
  trace,
  debugMode,
  hasReuse,
  reuseLabels,
  focused,
  onFilterTrace,
}: {
  trace: TraceGroup;
  debugMode: boolean;
  hasReuse: boolean;
  reuseLabels: string[];
  focused: boolean;
  onFilterTrace: (id: string | null) => void;
}) {
  const start = trace.events.find((event) => eventName(event) === "txn_start");
  const end = trace.events.find((event) => eventName(event) === "txn_end");
  const error = trace.events.find((event) => eventName(event) === "error");
  const title = transactionTitle(start, trace.result);
  const outcome = trace.result ? outcomeKey(trace.result, hasReuse) : error ? "error" : end ? "done" : "running";

  return (
    <article className={`trace-card trace-card--${outcome} ${focused ? "trace-card--focused" : ""}`}>
      <header className="trace-card__header">
        <div>
          <div className="trace-card__eyebrow">
            <button
              type="button"
              className="trace-chip"
              onClick={() => onFilterTrace(focused ? null : trace.traceId)}
            >
              {trace.traceId}
            </button>
            {start?.ts && <time>{formatTime(start.ts)}</time>}
          </div>
          <h3>{title}</h3>
          <p>{transactionMeta(start, trace.result)}</p>
        </div>
        <span className={`trace-status trace-status--${outcome}`}>{statusLabel(trace, error, hasReuse)}</span>
      </header>

      <div className="trace-timeline">
        {buildSteps(trace).map((step, index) => (
          <TraceStep key={`${step.event.ts ?? step.name}-${index}`} step={step} debugMode={debugMode} />
        ))}
        {trace.result && <ResultStep result={trace.result} debugMode={debugMode} reuseLabels={reuseLabels} />}
      </div>
    </article>
  );
}

function TraceStep({ step, debugMode }: { step: TraceStepData; debugMode: boolean }) {
  const icon = eventIcon(step.name, step.event);
  const details = stepDetails(step.event, debugMode);

  return (
    <div className={`trace-step trace-step--${eventClass(step.name, step.event)}`}>
      <span className="trace-step__icon">{icon}</span>
      <div className="trace-step__body">
        <div className="trace-step__head">
          <span>{step.title}</span>
          {step.event.ts && <time>{formatTime(step.event.ts)}</time>}
        </div>
        {step.summary && <p>{step.summary}</p>}
        {details && (
          <details className="trace-details">
            <summary>{debugMode ? "Log raw" : "Dettagli"}</summary>
            <pre>{details}</pre>
          </details>
        )}
      </div>
    </div>
  );
}

function ResultStep({
  result,
  debugMode,
  reuseLabels,
}: {
  result: MatchResultDTO;
  debugMode: boolean;
  reuseLabels: string[];
}) {
  const hasReuse = reuseLabels.length > 0;
  return (
    <div className={`trace-step trace-step--result trace-step--${outcomeKey(result, hasReuse)}`}>
      <span className="trace-step__icon">
        {result.matched ? <CheckCircle2 size={16} /> : <HelpCircle size={16} />}
      </span>
      <div className="trace-step__body">
        <div className="trace-step__head">
          <span>Risultato: {hasReuse ? "match ambiguo" : result.matched ? "match" : result.ambiguous ? "ambiguo" : "nessun match"}</span>
          <span className={`conf conf--${result.confidence}`}>{result.confidence}</span>
        </div>
        <p>{result.reason || "Nessun razionale disponibile."}</p>
        {reuseLabels.map((label) => (
          <p key={label}>Ambiguità: {label}</p>
        ))}
        <details className="trace-details">
          <summary>Apri info e razionale</summary>
          <div className="result-detail">
            <strong>Strategia</strong>
            <p>{result.strategy || "-"}</p>
            <strong>Gestionale</strong>
            {result.gestionale.length > 0 ? (
              result.gestionale.map((item) => (
                <p key={item.identificativo || item.description}>
                  <strong>{formatGestionaleMatchLabel(item.identificativo)}</strong>{" "}
                  {item.description} · €{item.amount}
                </p>
              ))
            ) : (
              <p>-</p>
            )}
            {result.alternatives.length > 0 && (
              <>
                <strong>Alternative</strong>
                {result.alternatives.map((alt, index) => (
                  <p key={`${index}-${formatAlternativeLabel(alt)}`}>
                    {formatAlternativeLabel(alt)} · {alt.confidence}
                    {alt.reason ? ` · ${alt.reason}` : ""}
                  </p>
                ))}
              </>
            )}
            {debugMode && <pre>{formatJson(result)}</pre>}
          </div>
        </details>
      </div>
    </div>
  );
}

function RunEvent({ event }: { event: AgentEvent }) {
  const name = eventName(event);
  return (
    <div className={`run-event run-event--${eventClass(name, event)}`}>
      <span>{formatEvent(name, event)}</span>
      {event.ts && <time>{formatTime(event.ts)}</time>}
    </div>
  );
}

interface TraceStepData {
  name: string;
  title: string;
  summary: string;
  event: AgentEvent;
}

function buildSteps(trace: TraceGroup): TraceStepData[] {
  return trace.events
    .filter((event) => eventName(event) !== "txn_end")
    .map((event) => {
      const name = eventName(event);
      return {
        name,
        title: stepTitle(name, event),
        summary: stepSummary(name, event),
        event,
      };
    });
}

function eventIcon(name: string, event: AgentEvent) {
  if (name === "error" || name === "run_error") return <AlertCircle size={16} />;
  if (isExpediaContextTool(event)) return <Mail size={16} />;
  if (name === "tool_call") return <Wrench size={16} />;
  if (name === "email_search") return <Mail size={16} />;
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

function eventName(event: AgentEvent): string {
  return (event.event ?? event.type ?? "unknown") as string;
}

function formatEvent(name: string, event: AgentEvent): string {
  switch (name) {
    case "run_started":
      return "Run avviata";
    case "txn_start":
      return `#${event.row_number} ${String(event.card_description ?? "").slice(0, 60)} — €${event.card_amount}`;
    case "txn_end":
      return event.matched
        ? `Match (${event.confidence})`
        : `Nessun match (${event.confidence})`;
    case "tool_call": {
      const tool = event.tool as string | undefined;
      const phase = event.phase as string | undefined;
      if (tool === "expedia_context") return `Contesto Expedia: ${compactExpediaContextSummary(event.output_summary)}`;
      if (phase === "start") return `→ ${tool}`;
      return `← ${tool ?? "tool"}: ${formatSummary(event.output_summary).slice(0, 120)}`;
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
      return "Arresto richiesto, attendo fine transazione corrente...";
    default:
      return JSON.stringify(
        Object.fromEntries(
          Object.entries(event).filter(([k]) => !["event", "type", "ts", "trace_id", "run_id"].includes(k)),
        ),
      ).slice(0, 200);
  }
}

function stepTitle(name: string, event: AgentEvent): string {
  switch (name) {
    case "txn_start":
      return `Sto analizzando la transazione #${event.row_number ?? "?"}`;
    case "router_classify":
      return `Classifico la transazione: ${event.category ?? "categoria non definita"}`;
    case "tool_call":
      if (isExpediaContextTool(event)) return "Raccolgo contesto Expedia";
      return `Uso tool ${String(event.tool ?? "tool")}`;
    case "email_search":
      return `Cerco email ${String(event.provider ?? "")}`.trim();
    case "agent_step":
      return event.action === "finish"
        ? "L'agente prepara la decisione"
        : `L'agente valuta il prossimo passo${event.action ? `: ${String(event.action)}` : ""}`;
    case "confidence_gate":
      return "Valuto la confidence e applico la soglia";
    case "rate_limit_retry":
      return "Retry per rate limit";
    case "pool_update":
      return "Aggiorno il pool gestionale";
    case "llm_call":
      return "Chiamata LLM completata";
    case "error":
      return "Errore durante l'analisi";
    default:
      return name;
  }
}

function stepSummary(name: string, event: AgentEvent): string {
  switch (name) {
    case "txn_start":
      return `${event.card_date ?? "-"} · ${event.card_description ?? "-"} · €${event.card_amount ?? "-"}`;
    case "router_classify":
      return `Uso questa categoria per scegliere strategia e tool più adatti.`;
    case "tool_call": {
      const phase = event.phase as string | undefined;
      if (isExpediaContextTool(event)) return compactExpediaContextSummary(event.output_summary);
      if (phase === "start") return "Il tool è stato invocato; i dettagli sono disponibili cliccando.";
      return compactToolSummary(event.output_summary);
    }
    case "email_search":
      return `${event.results ?? 0} email trovate per la ricerca.`;
    case "agent_step":
      return "Sintesi: l'agente sta confrontando evidenze, candidati e vincoli prima della decisione finale.";
    case "confidence_gate":
      return `Decisione preliminare: ${event.matched ? "match" : "no match"} con confidence ${event.confidence ?? "-"}.`;
    case "rate_limit_retry":
      return `Tentativo ${event.attempt ?? "?"}: riprovo tra ${event.wait_seconds ?? "?"}s.`;
    case "pool_update":
      return `${event.assigned ?? 0} righe assegnate, ${event.available ?? "?"} ancora disponibili.`;
    case "llm_call":
      return `${event.model ?? "modello"} · ${event.duration_ms ?? "?"}ms · ${event.prompt_tokens ?? 0}/${event.completion_tokens ?? 0} token.`;
    case "error":
      return String(event.error ?? "Errore sconosciuto");
    default:
      return formatEvent(name, event);
  }
}

function stepDetails(event: AgentEvent, debugMode: boolean): string | null {
  const name = eventName(event);
  if (debugMode) return formatJson(event);
  if (name === "tool_call") {
    if (isExpediaContextTool(event)) {
      return formatJson({
        status: outputSummaryValue(event, "status"),
        booking_code: outputSummaryValue(event, "booking_code"),
        candidate_strategy: outputSummaryValue(event, "candidate_strategy"),
        candidates: outputSummaryValue(event, "candidates"),
        duration_ms: event.duration_ms,
      });
    }
    return formatJson({
      input: event.input,
      output_summary: event.output_summary,
      duration_ms: event.duration_ms,
    });
  }
  if (name === "email_search") {
    return formatJson({
      provider: event.provider,
      query: event.query,
      keyword: event.keyword,
      from_address: event.from_address,
      search_date: event.search_date,
      date_from: event.date_from,
      date_to: event.date_to,
      results: event.results,
    });
  }
  return null;
}

function formatSummary(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function compactToolSummary(value: unknown): string {
  const text = formatSummary(value);
  return text ? text.slice(0, 180) : "Tool completato.";
}

function compactExpediaContextSummary(value: unknown): string {
  const status = String(summaryValue(value, "status") ?? "");
  const bookingCode = summaryValue(value, "booking_code");
  const candidates = summaryValue(value, "candidates");
  const strategy = summaryValue(value, "candidate_strategy");

  if (status === "candidates_found") {
    return `${candidates ?? 0} candidati gestionale trovati${bookingCode ? ` per ${bookingCode}` : ""}${strategy ? ` (${strategy})` : ""}.`;
  }
  if (status === "no_candidates") {
    return `Email Expedia trovata${bookingCode ? ` per ${bookingCode}` : ""}, ma nessun candidato gestionale.`;
  }
  if (status === "no_email") {
    return `Nessuna email Expedia trovata${bookingCode ? ` per ${bookingCode}` : ""}.`;
  }
  if (status === "no_booking_code") return "Codice prenotazione Expedia non trovato.";
  if (candidates !== undefined) return `${candidates} candidati gestionale trovati.`;
  return compactToolSummary(value);
}

function isExpediaContextTool(event: AgentEvent): boolean {
  return eventName(event) === "tool_call" && event.tool === "expedia_context";
}

function outputSummaryValue(event: AgentEvent, key: string): unknown {
  return summaryValue(event.output_summary, key);
}

function summaryValue(value: unknown, key: string): unknown {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return (value as Record<string, unknown>)[key];
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("it-IT");
  } catch {
    return iso;
  }
}

function traceSortKey(group: TraceGroup): number {
  const row = group.result?.row_number ?? group.events.find((event) => event.row_number)?.row_number;
  if (typeof row === "number") return row;
  const firstTime = group.events[0]?.ts;
  return firstTime ? new Date(firstTime).getTime() : Number.MAX_SAFE_INTEGER;
}

function transactionTitle(start: AgentEvent | undefined, result: MatchResultDTO | undefined): string {
  const row = result?.row_number ?? start?.row_number ?? "?";
  const description = result?.card.description ?? start?.card_description ?? "Transazione";
  return `Transazione #${row} · ${String(description).slice(0, 90)}`;
}

function transactionMeta(start: AgentEvent | undefined, result: MatchResultDTO | undefined): string {
  const date = result?.card.date ?? start?.card_date ?? "-";
  const amount = result?.card.amount ?? start?.card_amount ?? "-";
  const category = start?.category ? ` · ${start.category}` : "";
  return `${date} · €${amount}${category}`;
}

function statusLabel(trace: TraceGroup, error: AgentEvent | undefined, hasReuse = false): string {
  if (error) return "Errore";
  if (trace.result?.matched && hasReuse) return "Match ambiguo";
  if (trace.result?.matched) return "Match";
  if (trace.result?.ambiguous) return "Ambiguo";
  if (trace.result) return "No match";
  if (trace.events.some((event) => eventName(event) === "txn_end")) return "Completata";
  return "In corso";
}

function outcomeKey(result: MatchResultDTO, hasReuse = false): string {
  if (hasReuse) return "ambiguous";
  if (result.matched) return "matched";
  if (result.ambiguous) return "ambiguous";
  return "unmatched";
}
