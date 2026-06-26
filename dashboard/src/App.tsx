import { useCallback, useEffect, useState, type CSSProperties } from "react";
import {
  fetchResults,
  fetchRunList,
  fetchRunStatus,
  fetchSession,
  startRun,
  stopRun,
  subscribeRunEvents,
} from "./api";
import { LiveFeed } from "./components/LiveFeed";
import { ReportTable } from "./components/ReportTable";
import { RunControls } from "./components/RunControls";
import { RunHistory } from "./components/RunHistory";
import { UploadPanel } from "./components/UploadPanel";
import type {
  AgentEvent,
  MatchResultDTO,
  RunListItem,
  TabId,
  UploadResponse,
} from "./types";

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

  const [tab, setTab] = useState<TabId>("live");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [results, setResults] = useState<MatchResultDTO[]>([]);
  const [filterTraceId, setFilterTraceId] = useState<string | null>(null);
  const [runList, setRunList] = useState<RunListItem[]>([]);
  const [transactionRange, setTransactionRange] = useState<[number, number]>([1, 1]);

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

    const unsubscribe = subscribeRunEvents(
      runId,
      (data) => {
        if (data.type === "agent_event") {
          setEvents((prev) => [...prev, data as AgentEvent]);
        } else if (data.type === "match_result" && data.result) {
          const result = data.result as MatchResultDTO;
          setResults((prev) => {
            const exists = prev.some((r) => r.row_number === result.row_number);
            if (exists) return prev;
            return [...prev, result].sort((a, b) => a.row_number - b.row_number);
          });
          setProcessed((p) => Math.min(expected || p + 1, p + 1));
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
        } else if (data.type === "run_stopping") {
          setStatus("stopping");
        } else if (data.type === "run_finished") {
          setStatus(data.status as string);
          setProcessed(data.processed as number);
          setExpected(data.expected as number);
          setMatchedCount(data.matched as number);
          fetchRunList().then(setRunList).catch(() => undefined);
        } else if (data.type === "run_error") {
          setStatus("error");
          setError(data.error as string);
        } else {
          setEvents((prev) => [...prev, data as AgentEvent]);
        }
      },
      () => {
        if (runId !== null) {
          fetchRunStatus(runId)
            .then((s) => {
              if (s.status !== "running") setStatus(s.status);
            })
            .catch(() => undefined);
        }
      },
    );

    return unsubscribe;
  }, [expected, runId]);

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
      if (selectedTransactionCount) setExpected(selectedTransactionCount);
      setTab("live");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Avvio fallito");
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
                filterTraceId={filterTraceId}
                onFilterTrace={setFilterTraceId}
              />
            ) : (
              <ReportTable
                results={results}
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
