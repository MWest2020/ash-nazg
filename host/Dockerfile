# syntax=docker/dockerfile:1.7
#
# Ash Nazg host shim — multi-stage build.
#
# Stage 1 builds a project venv with `uv`, the project's chosen package
# manager. Stage 2 copies the venv into a slim runtime image that runs
# uvicorn as a non-root user.

# --- Stage 1: build venv with uv ---------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# `pip install uv` is the documented bootstrap path for uv. Pin the
# version so the build is reproducible across rebuilds.
ENV UV_VERSION=0.5.6
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

WORKDIR /app

# Copy the dependency manifest first so the layer caches across source-only
# changes. uv.lock may not exist on the very first build (this is a
# scaffold); when it does, we use --frozen to enforce reproducibility.
COPY pyproject.toml ./
COPY uv.lock* ./
COPY src/ ./src/

RUN if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev; \
    else \
        echo ">>> WARNING: no uv.lock present — falling back to non-frozen sync." >&2 ; \
        echo ">>> Generate one with 'uv lock' before shipping a real build." >&2 ; \
        uv sync --no-dev; \
    fi

# --- Stage 2: runtime --------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Non-root user. UID/GID are fixed so volume mounts stay predictable.
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src   /app/src

# Frontend bundle. Built outside the image with `npm run build` (vite
# emits to host/static/) before `docker build`. Optional — if absent,
# admin_settings.py renders a "not built yet" warning.
COPY static/ /app/static/

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080

USER app

EXPOSE 8080

# Liveness independent of AppAPI's /heartbeat handshake, so an
# orchestrator can probe the container even before AppAPI registration.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3).status==200 else 1)"

CMD ["uvicorn", "ash_nazg.main:app", "--host", "0.0.0.0", "--port", "8080"]
