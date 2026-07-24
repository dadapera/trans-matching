import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import {
  fetchResults,
  fetchRunList,
  fetchRunStatus,
  fetchSession,
  isRunNotFoundError,
  SERVER_LOST_DURING_RUN,
  startRun,
  stopRun,
  subscribeRunEvents,
} from "./api";
import { LiveFeed } from "./components/LiveFeed";
import { ReportTable } from "./components/ReportTable";
import { RunControls } from "./components/RunControls";
import { RunHistory } from "./components/RunHistory";
import { UploadPanel } from "./components/UploadPanel";
import { ensureNotificationPermission, notifyRunFinished } from "./notifications";
import type {
  AgentEvent,
  MatchResultDTO,
  RunListItem,
  ResultFilter,
  TabId,
  UploadResponse,
} from "./types";

const RUN_DISCONNECT_GRACE_MS = 45_000;
const RUN_WATCHDOG_MS = 15_000;

export default function App() {
  const [sessionReady, setSessionReady] = useState(false);
  const [cartaFilename, setCartaFilename] = useState<string>();
  const [gestionaleFilename, setGestionaleFilename] = useState<string>();
  const [cartaCount, setCartaCount] = useState<number>();
  const [gestionaleCount, setGestionaleCount] = useState<number>();

  const [runId, setRunId] = useState<number | null>(null);
  const [status, setStatus] = useState("idle");
  const [processed, setProcessed] = useState(0);
  const [expected, setExpected] = useState(0);
  const [matchedCount, setMatchedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const [tab, setTab] = useState<TabId>("live");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [results, setResults] = useState<MatchResultDTO[]>([]);
  const [filterTraceId, setFilterTraceId] = useState<string | null>(null);
  const [resultFilter, setResultFilter] = useState<ResultFilter>("all");
  const [runList, setRunList] = useState<RunListItem[]>([]);
  const [transactionRange, setTransactionRange] = useState<[number, number]>([1, 1]);

  const progressRef = useRef({ processed: 0, expected: 0, matchedCount: 0 });
  progressRef.current = { processed, expected, matchedCount };

  const running = status === "running" || status === "stopping";
  const transactionCount = cartaCount ?? 0;
  const selectedTransactionCount =
    transactionCount > 0 ? transactionRange[1] - transactionRange[0] + 1 : 0;

  const loadRun = useCallback(async (id: number) => {
    setRunId(id);
    setError(null);
    try {
      const [runStatus, runResults] = await Promise.all([
        fetchRunStatus(id),
        fetchResults(id),
      ]);
      setStatus(runStatus.status);
      setProcessed(runStatus.processed);
      setExpected(runStatus.expected);
      setMatchedCount(runStatus.matched_count);
      setResults(runResults);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore caricamento run");
    }
  }, []);

  const refreshSession = useCallback(async () => {
    const session = await fetchSession();
    if (session.ready) {
      setSessionReady(true);
      setCartaFilename(session.carta_filename);
      setGestionaleFilename(session.gestionale_filename);
      setCartaCount(session.carta_count);
      setGestionaleCount(session.gestionale_count);
    }
    if (session.active_run_id) {
      await loadRun(session.active_run_id);
    }
  }, [loadRun]);

  useEffect(() => {
    refreshSession().catch(() => undefined);
    fetchRunList().then(setRunList).catch(() => undefined);
  }, [refreshSession]);

  useEffect(() => {
    if (!cartaCount || cartaCount < 1) {
      setTransactionRange([1, 1]);
      return;
    }
    setTransactionRange([1, cartaCount]);
  }, [cartaCount]);

  useEffect(() => {
    if (runId === null) return;
    // Historical / finished runs: no live stream (avoids false "server lost" probes).
    if (status !== "running" && status !== "stopping") return;

    let cancelled = false;
    let fatal = false;
    let probing = false;
    let disconnectSince: number | null = null;
    let probeTimer: ReturnType<typeof setTimeout> | null = null;
    let unsubscribe: () => void = () => undefined;

    const markLost = (message: string) => {
      if (cancelled || fatal) return;
      fatal = true;
      const snap = progressRef.current;
      setStatus("error");
      setError(message);
      notifyRunFinished({
        runId,
        status: "error",
        matched: snap.matchedCount,
        processed: snap.processed,
        expected: snap.expected,
        error: message,
      });
      fetchRunList().then(setRunList).catch(() => undefined);
      unsubscribe();
    };

    const applyTerminalStatus = (
      finalStatus: string,
      overrides?: { processed?: number; expected?: number; matched?: number; error?: string },
    ) => {
      if (cancelled || fatal) return;
      fatal = true;
      const snap = progressRef.current;
      setStatus(finalStatus);
      if (overrides?.processed !== undefined) setProcessed(overrides.processed);
      if (overrides?.expected !== undefined) setExpected(overrides.expected);
      if (overrides?.matched !== undefined) setMatchedCount(overrides.matched);
      if (finalStatus === "error") {
        setError(overrides?.error ?? "La run è terminata con errore.");
      }
      notifyRunFinished({
        runId,
        status: finalStatus,
        matched: overrides?.matched ?? snap.matchedCount,
        processed: overrides?.processed ?? snap.processed,
        expected: overrides?.expected ?? snap.expected,
        error: overrides?.error,
      });
      fetchRunList().then(setRunList).catch(() => undefined);
      unsubscribe();
    };

    const probeRunHealth = async () => {
      if (cancelled || fatal || probing) return;
      probing = true;
      try {
        const [runStatus, session] = await Promise.all([fetchRunStatus(runId), fetchSession()]);
        if (cancelled || fatal) return;
        disconnectSince = null;

        if (runStatus.status === "running" || runStatus.status === "stopping") {
          // Process restarted: DB may still say running, but nothing is active in-memory.
          if (session.active_run_id !== runId) {
            markLost(SERVER_LOST_DURING_RUN);
            return;
          }
          setStatus(runStatus.status);
          setProcessed(runStatus.processed);
          setExpected(runStatus.expected);
          setMatchedCount(runStatus.matched_count);
          return;
        }

        applyTerminalStatus(runStatus.status, {
          processed: runStatus.processed,
          expected: runStatus.expected,
          matched: runStatus.matched_count,
          error:
            runStatus.status === "error"
              ? "La run è terminata con errore (possibile riavvio del server)."
              : undefined,
        });
      } catch (err) {
        if (cancelled || fatal) return;
        if (isRunNotFoundError(err)) {
          markLost(SERVER_LOST_DURING_RUN);
          return;
        }
        if (disconnectSince !== null && Date.now() - disconnectSince >= RUN_DISCONNECT_GRACE_MS) {
          markLost(SERVER_LOST_DURING_RUN);
        }
      } finally {
        probing = false;
      }
    };

    const scheduleProbe = () => {
      if (probeTimer !== null) return;
      probeTimer = setTimeout(() => {
        probeTimer = null;
        void probeRunHealth();
      }, 1500);
    };

    unsubscribe = subscribeRunEvents(
      runId,
      (data) => {
        if (cancelled || fatal) return;
        disconnectSince = null;

        if (data.type === "agent_event") {
          setEvents((prev) => [...prev, data as AgentEvent]);
        } else if (data.type === "match_result" && data.result) {
          const result = data.result as MatchResultDTO;
          setResults((prev) => {
            const exists = prev.some((r) => r.row_number === result.row_number);
            if (exists) return prev;
            return [...prev, result].sort((a, b) => a.row_number - b.row_number);
          });
          setProcessed((p) => p + 1);
          if (result.matched) setMatchedCount((m) => m + 1);
        } else if (data.type === "run_progress") {
          setProcessed(data.processed as number);
          setExpected(data.expected as number);
        } else if (data.type === "run_started") {
          setStatus("running");
          setEvents([]);
          setResults([]);
          setMatchedCount(0);
          setProcessed(0);
          setResultFilter("all");
        } else if (data.type === "run_stopping") {
          setStatus("stopping");
        } else if (data.type === "run_finished") {
          applyTerminalStatus(data.status as string, {
            processed: data.processed as number,
            expected: data.expected as number,
            matched: data.matched as number,
          });
        } else if (data.type === "run_error") {
          const message = data.error as string;
          applyTerminalStatus("error", { error: message });
        } else if (data.type !== "connected") {
          setEvents((prev) => [...prev, data as AgentEvent]);
        }
      },
      () => {
        if (cancelled || fatal) return;
        if (disconnectSince === null) disconnectSince = Date.now();
        scheduleProbe();
        if (Date.now() - disconnectSince >= RUN_DISCONNECT_GRACE_MS) {
          void probeRunHealth();
        }
      },
    );

    const watchdog = setInterval(() => {
      void probeRunHealth();
    }, RUN_WATCHDOG_MS);

    return () => {
      cancelled = true;
      if (probeTimer !== null) clearTimeout(probeTimer);
      clearInterval(watchdog);
      unsubscribe();
    };
  }, [runId, status]);

  const handleUploaded = (info: UploadResponse) => {
    setSessionReady(true);
    setCartaFilename(info.carta_filename);
    setGestionaleFilename(info.gestionale_filename);
    setCartaCount(info.carta_count);
    setGestionaleCount(info.gestionale_count);
    setExpected(info.carta_count);
    setTransactionRange([1, info.carta_count]);
    setError(null);
  };

  const handleStart = async () => {
    setError(null);
    setStarting(true);
    void ensureNotificationPermission();
    try {
      const { run_id } = await startRun({
        row_start: transactionRange[0],
        row_end: transactionRange[1],
      });
      setRunId(run_id);
      setStatus("running");
      setEvents([]);
      setResults([]);
      setProcessed(0);
      setMatchedCount(0);
      setResultFilter("all");
      if (selectedTransactionCount) setExpected(selectedTransactionCount);
      setTab("live");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Avvio fallito");
    } finally {
      setStarting(false);
    }
  };

  const handleStop = async () => {
    if (runId === null) return;
    setStatus("stopping");
    try {
      await stopRun(runId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stop fallito");
    }
  };

  const handleSelectRun = async (id: number) => {
    await loadRun(id);
    setTab("report");
  };

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Trans Matching</h1>
          <p className="header__sub">Agente contabile — carta vs gestionale</p>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <UploadPanel
            disabled={running}
            onUploaded={handleUploaded}
            cartaFilename={cartaFilename}
            gestionaleFilename={gestionaleFilename}
            cartaCount={cartaCount}
            gestionaleCount={gestionaleCount}
          />
          <TransactionRangePanel
            total={transactionCount}
            range={transactionRange}
            disabled={running || transactionCount === 0}
            onChange={setTransactionRange}
          />
          <RunControls
            ready={sessionReady}
            running={running}
            starting={starting}
            runId={runId}
            processed={processed}
            expected={runId === null ? selectedTransactionCount : expected}
            matchedCount={matchedCount}
            status={status}
            onStart={handleStart}
            onStop={handleStop}
            error={error}
          />
          <RunHistory runs={runList} activeRunId={runId} onSelect={handleSelectRun} />
        </aside>

        <main className="main">
          <div className="tabs">
            <button
              type="button"
              className={`tab ${tab === "live" ? "tab--active" : ""}`}
              onClick={() => setTab("live")}
            >
              Attività live
            </button>
            <button
              type="button"
              className={`tab ${tab === "report" ? "tab--active" : ""}`}
              onClick={() => setTab("report")}
            >
              Report ({results.length})
            </button>
          </div>

          <div className="tab-panel">
            {tab === "live" ? (
              <LiveFeed
                events={events}
                results={results}
                resultFilter={resultFilter}
                filterTraceId={filterTraceId}
                onFilterTrace={setFilterTraceId}
              />
            ) : (
              <ReportTable
                results={results}
                resultFilter={resultFilter}
                onResultFilterChange={setResultFilter}
                onSelectTrace={(id) => {
                  setFilterTraceId(id);
                  setTab("live");
                }}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function TransactionRangePanel({
  total,
  range,
  disabled,
  onChange,
}: {
  total: number;
  range: [number, number];
  disabled: boolean;
  onChange: (range: [number, number]) => void;
}) {
  const [start, end] = range;
  const selected = total > 0 ? end - start + 1 : 0;
  const minPct = total > 1 ? ((start - 1) / (total - 1)) * 100 : 0;
  const maxPct = total > 1 ? ((end - 1) / (total - 1)) * 100 : 100;

  const updateStart = (value: number) => {
    onChange([Math.min(value, end), end]);
  };

  const updateEnd = (value: number) => {
    onChange([start, Math.max(value, start)]);
  };

  return (
    <section className="panel txn-range">
      <h2>Subset transazioni</h2>
      {total > 0 ? (
        <>
          <div className="txn-range__meta">
            <span>
              Riga {start} - {end}
            </span>
            <span>{selected} selezionate</span>
          </div>
          <div
            className="range-slider"
            style={
              {
                "--range-start": `${minPct}%`,
                "--range-end": `${maxPct}%`,
              } as CSSProperties & Record<string, string>
            }
          >
            <input
              type="range"
              min={1}
              max={total}
              value={start}
              disabled={disabled}
              aria-label="Prima transazione da analizzare"
              onChange={(event) => updateStart(Number(event.target.value))}
            />
            <input
              type="range"
              min={1}
              max={total}
              value={end}
              disabled={disabled}
              aria-label="Ultima transazione da analizzare"
              onChange={(event) => updateEnd(Number(event.target.value))}
            />
          </div>
          <div className="txn-range__bounds">
            <span>1</span>
            <span>{total}</span>
          </div>
        </>
      ) : (
        <p className="hint-text">Carica la carta per scegliere il subset.</p>
      )}
    </section>
  );
}
