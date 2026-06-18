# syntax=docker/dockerfile:1.6
# =============================================================================
# Tokio Bar Restaurant Bot — production-ready multi-stage Docker image
# =============================================================================
# Stage 1: Builder
#   - installs build tooling and Python dependencies into an isolated venv
# Stage 2: Runtime
#   - slim image, non-root user, timezone, healthcheck, minimal attack surface
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1 — Builder
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1

# Build dependencies: gcc/libpq-dev to compile asyncpg wheel if no binary exists.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Isolated virtual environment keeps the runtime image clean.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install dependencies first → maximises Docker layer cache reuse.
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2 — Runtime
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="tokio-bar-bot" \
      org.opencontainers.image.description="Tokio Bar restaurant Telegram bot system" \
      org.opencontainers.image.source="https://github.com/tokio-bar/bot"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Moscow \
    LANG=C.UTF-8 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH"

# Runtime dependencies:
#   libpq5  — shared lib needed by the asyncpg C extension
#   tzdata  — timezone database (TZ=Europe/Moscow)
#   curl    — lightweight, useful for debugging inside the container
#   tini    — tiny init to reap zombies and forward signals (SIGTERM) correctly
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        tzdata \
        curl \
        tini \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Reuse the pre-built virtual environment.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# ---- Non-root user ---------------------------------------------------------
# Running as a non-root user is a container security best practice.
RUN groupadd --system --gid 1001 bot \
    && useradd --system --uid 1001 --gid bot \
       --home-dir /app --shell /sbin/nologin bot \
    && mkdir -p /app/logs /app/qr_codes \
    && chown -R bot:bot /app

# ---- Application code ------------------------------------------------------
COPY --chown=bot:bot . /app

# ---- Scripts ---------------------------------------------------------------
COPY --chown=bot:bot docker/entrypoint.sh  /app/entrypoint.sh
COPY --chown=bot:bot docker/healthcheck.py /app/healthcheck.py
RUN chmod +x /app/entrypoint.sh

USER bot

# ---- Healthcheck -----------------------------------------------------------
# Verifies database connectivity (the critical external dependency).
# If the DB is unreachable the bot cannot serve requests → container is marked
# unhealthy so orchestrators (Docker / Compose / Swarm) can act on it.
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python /app/healthcheck.py || exit 1

# No ports to expose: the bots use Telegram long-polling (outbound HTTPS only).

# tini → entrypoint → CMD (python main.py)
# exec replaces the shell so the Python process becomes PID 1 and receives
# SIGTERM/SIGINT directly for a clean shutdown.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
CMD ["python", "main.py"]