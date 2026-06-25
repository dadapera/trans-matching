"""Avvia la dashboard web (FastAPI + static React build).

Dev workflow:
  Terminal 1 — API backend:
    uv run python main_dashboard.py

  Terminal 2 — frontend con hot reload (proxy /api → :8000):
    cd dashboard && npm install && npm run dev

  Produzione (build statico servito da FastAPI):
    cd dashboard && npm run build
    uv run python main_dashboard.py

  Docker:
    docker compose up --build
    # http://localhost:8000
"""

import os

import uvicorn


def main() -> None:
    port = int(os.environ.get("DASHBOARD_PORT", os.environ.get("PORT", "8000")))
    uvicorn.run(
        "trans_matching.web.app:app",
        host="0.0.0.0",
        port=port,
        reload=os.environ.get("DASHBOARD_RELOAD", "").lower() in {"1", "true", "yes"},
    )


if __name__ == "__main__":
    main()
