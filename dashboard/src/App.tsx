import { useCallback, useEffect, useState } from "react";
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

  const running = status === "running" || status === "stopping";

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
          setProcessed((p) => Math.max(p, result.row_number));
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
  }, [runId]);

  const handleUploaded = (info: UploadResponse) => {
    setSessionReady(true);
    setCartaFilename(info.carta_filename);
    setGestionaleFilename(info.gestionale_filename);
    setCartaCount(info.carta_count);
    setGestionaleCount(info.gestionale_count);
    setExpected(info.carta_count);
    setError(null);
  };

  const handleStart = async () => {
    setError(null);
    try {
      const { run_id } = await startRun();
      setRunId(run_id);
      setStatus("running");
      setEvents([]);
      setResults([]);
      setProcessed(0);
      setMatchedCount(0);
      if (cartaCount) setExpected(cartaCount);
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
          <RunControls
            ready={sessionReady}
            running={running}
            runId={runId}
            processed={processed}
            expected={expected}
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
