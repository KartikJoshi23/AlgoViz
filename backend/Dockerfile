# syntax=docker/dockerfile:1.7
# AlgoViz backend — multi-stage build, non-root, production CMD.

# ── Builder: compile wheels into a venv ─────────────────────────────
FROM python:3.11-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && pip install -r requirements.txt

# ── Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appuser alembic.ini pyproject.toml ./
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser algoviz ./algoviz
COPY --chown=appuser:appuser scripts ./scripts
RUN mkdir -p /app/data /app/ml_models && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8000/health/live || exit 1
# The app resolves forwarded client addresses itself (TRUSTED_PROXIES), so uvicorn must not.
CMD ["uvicorn", "algoviz.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
