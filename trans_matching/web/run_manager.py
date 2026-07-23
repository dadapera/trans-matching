from __future__ import annotations

import json
import queue
import shutil
import tempfile
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from trans_matching.agent.logging import create_run_logger
from trans_matching.agent.pipeline import run_agent_matching
from trans_matching.llm_usage import reset_llm_usage
from trans_matching.matchers.agent_models import AgentMatchResult
from trans_matching.models import Transaction
from trans_matching.openai_http import verify_openai_connection
from trans_matching.email import verify_gmail_connection
from trans_matching.storage.agent_repository import (
    create_agent_run,
    get_agent_run,
    load_agent_results,
    save_agent_match_result,
    update_agent_run,
)
from trans_matching.web.schemas import match_result_to_dto
from trans_matching.web.upload import parse_carta_and_gestionale


@dataclass
class UploadSession:
    card_transactions: list[Transaction]
    gestionale_transactions: list[Transaction]
    carta_filename: str
    gestionale_filename: str


UploadJobStatus = Literal["idle", "processing", "ready", "error"]


@dataclass
class UploadJob:
    status: UploadJobStatus = "idle"
    carta_filename: str = ""
    gestionale_filename: str = ""
    carta_count: int = 0
    gestionale_count: int = 0
    error: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    progress_message: str = ""
    thread: threading.Thread | None = None


@dataclass
class ActiveRun:
    run_id: int
    cancel_event: threading.Event
    thread: threading.Thread
    lock: threading.Lock = field(default_factory=threading.Lock)
    status: str = "running"
    error_message: str | None = None


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._upload: UploadSession | None = None
        self._upload_job = UploadJob()
        self._active: ActiveRun | None = None
        self._subscribers: dict[int, list[queue.Queue[str]]] = defaultdict(list)

    def set_upload(
        self,
        card_transactions: list[Transaction],
        gestionale_transactions: list[Transaction],
        carta_filename: str,
        gestionale_filename: str,
    ) -> UploadSession:
        session = UploadSession(
            card_transactions=card_transactions,
            gestionale_transactions=gestionale_transactions,
            carta_filename=carta_filename,
            gestionale_filename=gestionale_filename,
        )
        with self._lock:
            self._upload = session
            self._upload_job = UploadJob(
                status="ready",
                carta_filename=carta_filename,
                gestionale_filename=gestionale_filename,
                carta_count=len(card_transactions),
                gestionale_count=len(gestionale_transactions),
                progress_current=1,
                progress_total=1,
                progress_message="Completato",
            )
        return session

    def get_upload(self) -> UploadSession | None:
        with self._lock:
            return self._upload

    def is_upload_processing(self) -> bool:
        with self._lock:
            return self._upload_job.status == "processing"

    def set_upload_progress(self, current: int, total: int, message: str) -> None:
        with self._lock:
            if self._upload_job.status != "processing":
                return
            self._upload_job.progress_current = current
            self._upload_job.progress_total = total
            self._upload_job.progress_message = message

    def get_upload_status(self) -> dict[str, Any]:
        with self._lock:
            job = self._upload_job
            progress_pct = 0.0
            if job.status == "ready":
                progress_pct = 100.0
            elif job.progress_total > 0:
                progress_pct = min(100.0, 100.0 * job.progress_current / job.progress_total)
            return {
                "status": job.status,
                "carta_count": job.carta_count,
                "gestionale_count": job.gestionale_count,
                "carta_filename": job.carta_filename,
                "gestionale_filename": job.gestionale_filename,
                "error": job.error,
                "progress_current": job.progress_current,
                "progress_total": job.progress_total,
                "progress_message": job.progress_message,
                "progress_pct": progress_pct,
            }

    def start_upload_parse(
        self,
        carta_bytes: bytes,
        gestionale_bytes: bytes,
        carta_filename: str,
        gestionale_filename: str,
    ) -> None:
        with self._lock:
            if self._active is not None and self._active.status == "running":
                raise RuntimeError("Analisi in corso: attendi o fermala prima di ricaricare")
            if self._upload_job.status == "processing":
                raise RuntimeError("Upload già in elaborazione")

            self._upload = None
            self._upload_job = UploadJob(
                status="processing",
                carta_filename=carta_filename,
                gestionale_filename=gestionale_filename,
            )

        tmp_dir = Path(tempfile.mkdtemp(prefix="trans-matching-upload-"))
        carta_path = tmp_dir / f"carta{Path(carta_filename).suffix.lower()}"
        gestionale_path = tmp_dir / "gestionale.pdf"
        carta_path.write_bytes(carta_bytes)
        gestionale_path.write_bytes(gestionale_bytes)

        def worker() -> None:
            try:
                card_txns, gestionale_txns = parse_carta_and_gestionale(
                    carta_path,
                    gestionale_path,
                    on_progress=self.set_upload_progress,
                )
                self.set_upload(
                    card_txns,
                    gestionale_txns,
                    carta_filename,
                    gestionale_filename,
                )
            except Exception as exc:
                with self._lock:
                    self._upload = None
                    self._upload_job = UploadJob(
                        status="error",
                        carta_filename=carta_filename,
                        gestionale_filename=gestionale_filename,
                        error=str(exc),
                    )
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        thread = threading.Thread(target=worker, name="upload-parse", daemon=True)
        with self._lock:
            self._upload_job.thread = thread
        thread.start()

    def is_running(self) -> bool:
        with self._lock:
            return self._active is not None and self._active.status == "running"

    def get_active_run_id(self) -> int | None:
        with self._lock:
            if self._active is None:
                return None
            return self._active.run_id

    def start_run(self, row_start: int | None = None, row_end: int | None = None) -> int:
        with self._lock:
            if self._active is not None and self._active.status == "running":
                raise RuntimeError("Una analisi è già in corso")
            if self._upload_job.status == "processing":
                raise RuntimeError("Attendere il completamento dell'OCR/upload")
            if self._upload is None:
                raise RuntimeError("Carica prima i file carta e gestionale")

            upload = self._upload

        total_rows = len(upload.card_transactions)
        start = row_start or 1
        end = row_end or total_rows
        if start > end:
            raise RuntimeError("Subset transazioni non valido: inizio maggiore della fine")
        if start < 1 or end > total_rows:
            raise RuntimeError(f"Subset transazioni fuori range: scegli righe tra 1 e {total_rows}")

        selected_card_transactions = upload.card_transactions[start - 1 : end]

        try:
            verify_openai_connection()
        except RuntimeError as exc:
            raise RuntimeError(str(exc)) from exc

        try:
            verify_gmail_connection()
        except (RuntimeError, ValueError) as exc:
            raise RuntimeError(str(exc)) from exc

        reset_llm_usage()
        expected_transactions = len(selected_card_transactions)
        run_id = create_agent_run(expected_transactions)
        cancel_event = threading.Event()

        def on_event(record: dict[str, Any]) -> None:
            self._broadcast(run_id, {"type": "agent_event", **record})

        logger = create_run_logger(run_id, on_event=on_event)

        def on_result(result: AgentMatchResult) -> None:
            save_agent_match_result(run_id, result)
            dto = match_result_to_dto(result)
            self._broadcast(
                run_id,
                {"type": "match_result", "run_id": run_id, "result": dto.model_dump()},
            )

        def progress_callback(current: int, total: int) -> None:
            self._broadcast(
                run_id,
                {
                    "type": "run_progress",
                    "run_id": run_id,
                    "processed": current - 1,
                    "expected": total,
                },
            )

        def worker() -> None:
            started = time.perf_counter()
            final_status = "completed"
            error_message: str | None = None
            try:
                results, _, run_logger = run_agent_matching(
                    selected_card_transactions,
                    upload.gestionale_transactions,
                    run_id=run_id,
                    logger=logger,
                    cancel_event=cancel_event,
                    on_result=on_result,
                    progress_callback=progress_callback,
                    row_offset=start - 1,
                    quiet=True,
                    save_at_end=False,
                )
                matched = sum(1 for item in results if item.matched)
                elapsed = time.perf_counter() - started
                if cancel_event.is_set():
                    final_status = "stopped"
                update_agent_run(
                    run_id,
                    status=final_status,
                    elapsed_seconds=elapsed,
                    log_path=run_logger.log_path,
                    matched_count=matched,
                    total_transactions=len(results),
                )
                self._broadcast(
                    run_id,
                    {
                        "type": "run_finished",
                        "run_id": run_id,
                        "status": final_status,
                        "matched": matched,
                        "processed": len(results),
                        "expected": expected_transactions,
                        "elapsed_seconds": round(elapsed, 2),
                    },
                )
            except Exception as exc:
                final_status = "error"
                error_message = str(exc)
                elapsed = time.perf_counter() - started
                update_agent_run(
                    run_id,
                    status="error",
                    elapsed_seconds=elapsed,
                    log_path=logger.log_path,
                )
                logger.log_error("error", exc, phase="run_worker")
                self._broadcast(
                    run_id,
                    {
                        "type": "run_error",
                        "run_id": run_id,
                        "error": error_message,
                    },
                )
            finally:
                with self._lock:
                    if self._active is not None and self._active.run_id == run_id:
                        self._active.status = final_status
                        self._active.error_message = error_message

        thread = threading.Thread(target=worker, name=f"agent-run-{run_id}", daemon=True)
        active = ActiveRun(run_id=run_id, cancel_event=cancel_event, thread=thread)
        with self._lock:
            self._active = active
            self._subscribers[run_id] = []

        thread.start()
        self._broadcast(run_id, {"type": "run_started", "run_id": run_id})
        return run_id

    def stop_run(self, run_id: int) -> None:
        with self._lock:
            if self._active is None or self._active.run_id != run_id:
                raise RuntimeError(f"Run {run_id} non attiva")
            if self._active.status != "running":
                raise RuntimeError(f"Run {run_id} non è in esecuzione")
            self._active.cancel_event.set()
        self._broadcast(run_id, {"type": "run_stopping", "run_id": run_id})

    def subscribe(self, run_id: int) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue(maxsize=500)
        with self._lock:
            self._subscribers[run_id].append(q)
        return q

    def unsubscribe(self, run_id: int, q: queue.Queue[str]) -> None:
        with self._lock:
            subs = self._subscribers.get(run_id, [])
            if q in subs:
                subs.remove(q)

    def _broadcast(self, run_id: int, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            queues = list(self._subscribers.get(run_id, []))
        for q in queues:
            try:
                q.put_nowait(line)
            except queue.Full:
                pass

    def get_run_status(self, run_id: int) -> dict[str, Any]:
        run = get_agent_run(run_id)
        expected = run.expected_transactions or run.total_transactions
        return {
            "run_id": run.id,
            "status": run.status,
            "processed": run.total_transactions,
            "expected": expected,
            "matched_count": run.matched_count,
            "elapsed_seconds": run.elapsed_seconds,
            "log_path": run.log_path,
            "openai_model": run.openai_model,
            "created_at": run.created_at,
        }

    def get_results(self, run_id: int) -> list[dict[str, Any]]:
        results = load_agent_results(run_id)
        return [match_result_to_dto(r).model_dump() for r in results]


run_manager = RunManager()
