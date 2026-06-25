from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from trans_matching.storage.agent_repository import list_agent_runs
from trans_matching.web.run_manager import run_manager
from trans_matching.web.schemas import (
    RunListItemDTO,
    RunStartResponse,
    RunStatusDTO,
    UploadResponse,
)
from trans_matching.web.upload import parse_upload_files

ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIST = ROOT / "dashboard" / "dist"

app = FastAPI(title="Trans Matching Dashboard", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/session/upload", response_model=UploadResponse)
async def upload_session(
    carta: UploadFile = File(...),
    gestionale: UploadFile = File(...),
) -> UploadResponse:
    if run_manager.is_running():
        raise HTTPException(status_code=409, detail="Analisi in corso: attendi o fermala prima di ricaricare")
    card_txns, gestionale_txns, carta_name, gestionale_name = await parse_upload_files(
        carta, gestionale
    )
    run_manager.set_upload(card_txns, gestionale_txns, carta_name, gestionale_name)
    return UploadResponse(
        carta_count=len(card_txns),
        gestionale_count=len(gestionale_txns),
        carta_filename=carta_name,
        gestionale_filename=gestionale_name,
    )


@app.post("/api/runs", response_model=RunStartResponse)
async def start_run() -> RunStartResponse:
    try:
        run_id = run_manager.start_run()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RunStartResponse(run_id=run_id)


@app.post("/api/runs/{run_id}/stop")
async def stop_run(run_id: int) -> dict[str, str]:
    try:
        run_manager.stop_run(run_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "stopping"}


@app.get("/api/runs/{run_id}", response_model=RunStatusDTO)
async def get_run(run_id: int) -> RunStatusDTO:
    try:
        data = run_manager.get_run_status(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunStatusDTO(**data)


@app.get("/api/runs/{run_id}/results")
async def get_results(run_id: int) -> list[dict]:
    try:
        run_manager.get_run_status(run_id)
        return run_manager.get_results(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/runs")
async def list_runs() -> list[RunListItemDTO]:
    runs = list_agent_runs(limit=30)
    return [
        RunListItemDTO(
            id=run.id,
            status=run.status,
            created_at=run.created_at,
            total_transactions=run.total_transactions,
            matched_count=run.matched_count,
            expected_transactions=run.expected_transactions,
        )
        for run in runs
    ]


@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: int) -> StreamingResponse:
    try:
        run_manager.get_run_status(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    event_queue = run_manager.subscribe(run_id)

    async def event_generator():
        try:
            yield "data: {\"type\":\"connected\",\"run_id\":" + str(run_id) + "}\n\n"
            while True:
                try:
                    line = await asyncio.to_thread(event_queue.get, True, 30.0)
                    yield f"data: {line}\n\n"
                    payload = __import__("json").loads(line)
                    if payload.get("type") in {"run_finished", "run_error"}:
                        break
                except Exception:
                    yield ": keepalive\n\n"
                    status = run_manager.get_run_status(run_id)
                    if status["status"] not in {"running"}:
                        break
        finally:
            run_manager.unsubscribe(run_id, event_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/session")
async def get_session() -> dict:
    upload = run_manager.get_upload()
    active_id = run_manager.get_active_run_id()
    if upload is None:
        return {"ready": False, "active_run_id": active_id}
    return {
        "ready": True,
        "carta_count": len(upload.card_transactions),
        "gestionale_count": len(upload.gestionale_transactions),
        "carta_filename": upload.carta_filename,
        "gestionale_filename": upload.gestionale_filename,
        "active_run_id": active_id,
    }


@app.get("/")
async def root():
    index = DASHBOARD_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "message": "Trans Matching API attiva. Build frontend: cd dashboard && npm run build",
        "docs": "/docs",
    }


if DASHBOARD_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DASHBOARD_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = DASHBOARD_DIST / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(index)
