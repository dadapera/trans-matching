# Stage 1: build React dashboard
FROM node:22-alpine AS frontend

WORKDIR /app/dashboard
COPY dashboard/package.json ./
RUN npm install --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# Stage 2: Python API
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DATA_DIR=/data \
    AGENT_LOG_DIR=/data/logs \
    PORT=8000

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY trans_matching/ trans_matching/
COPY main_dashboard.py main_agent.py ./

COPY --from=frontend /app/dashboard/dist /app/dashboard/dist

RUN mkdir -p /data/logs

ENV PATH="/app/.venv/bin:$PATH"

VOLUME /data
EXPOSE 8000

CMD ["python", "main_dashboard.py"]
