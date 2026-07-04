#!/bin/sh
# =============================================================================
# entrypoint.sh — Tokio Bar bot container entrypoint
# =============================================================================
# Responsibilities:
#   1. Wait for PostgreSQL to accept connections (tcp check + python probe).
#   2. Run database migrations (Alembic, via bootstrap_database) + seed data
#      (idempotent, safe to run always).
#   3. Hand off to the main process (CMD) via exec so signals work correctly.
# =============================================================================
# -e: exit on error, -u: error on undefined variable.
# (pipefail is not POSIX-sh/dash compatible — we avoid it here.)
set -eu

echo "===================================================="
echo " Tokio Bar Bot — entrypoint"
echo " $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "===================================================="

# ---------------------------------------------------------------------------
# 1. Wait for the database to accept TCP connections.
#    We retry for up to DB_WAIT_TIMEOUT seconds (default 60).
# ---------------------------------------------------------------------------
: "${DB_HOST:=localhost}"
: "${DB_PORT:=5432}"
: "${DB_WAIT_TIMEOUT:=60}"
: "${DB_WAIT_INTERVAL:=2}"

echo "[entrypoint] Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} ..."

elapsed=0
until python - <<'PY' 2>/dev/null
import os, socket, sys
host = os.environ.get("DB_HOST", "localhost")
port = int(os.environ.get("DB_PORT", "5432"))
try:
    with socket.create_connection((host, port), timeout=2):
        pass  # TCP connect success is enough; no data exchange required
except Exception:
    sys.exit(1)
PY
do
    if [ "$elapsed" -ge "$DB_WAIT_TIMEOUT" ]; then
        echo "[entrypoint] ERROR: database did not become available in ${DB_WAIT_TIMEOUT}s." >&2
        exit 1
    fi
    echo "[entrypoint] PostgreSQL not ready yet (${elapsed}s elapsed). Retrying in ${DB_WAIT_INTERVAL}s..."
    sleep "$DB_WAIT_INTERVAL"
    elapsed=$((elapsed + DB_WAIT_INTERVAL))
done
echo "[entrypoint] PostgreSQL is accepting connections."

# ---------------------------------------------------------------------------
# 2. Verify a real PostgreSQL connection with credentials (asyncpg).
#    Retries here guard against the server being "up" but still initialising.
# ---------------------------------------------------------------------------
echo "[entrypoint] Verifying PostgreSQL credentials..."
attempt=0
max_attempts=10
until python - <<'PY' 2>/dev/null
import asyncio, os, sys
import asyncpg

async def main():
    conn = await asyncpg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "tokio_bar"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        timeout=5,
    )
    await conn.execute("SELECT 1")
    await conn.close()

asyncio.run(main())
PY
do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "[entrypoint] ERROR: cannot authenticate to PostgreSQL after ${max_attempts} attempts." >&2
        exit 1
    fi
    echo "[entrypoint] PostgreSQL credentials not ready (attempt ${attempt}/${max_attempts}). Retrying..."
    sleep 3
done
echo "[entrypoint] PostgreSQL credentials OK."

# ---------------------------------------------------------------------------
# 3. Wait for Redis (if REDIS_URL is set). Non-fatal: the bot falls back to
#    in-memory storage when Redis is unavailable.
# ---------------------------------------------------------------------------
if [ -n "${REDIS_URL:-}" ]; then
    echo "[entrypoint] Waiting for Redis at ${REDIS_URL} ..."
    attempt=0
    redis_max_attempts=10
    until python - <<'PY' 2>/dev/null
import os, sys
url = os.environ.get("REDIS_URL", "")
if not url:
    sys.exit(1)
try:
    import redis
except ImportError:
    sys.exit(1)
r = redis.from_url(url, socket_connect_timeout=2)
try:
    r.ping()
except Exception:
    sys.exit(1)
PY
    do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge "$redis_max_attempts" ]; then
            echo "[entrypoint] WARNING: Redis not reachable after ${redis_max_attempts} attempts. Continuing (in-memory mode)." >&2
            break
        fi
        echo "[entrypoint] Redis not ready (attempt ${attempt}/${redis_max_attempts}). Retrying..."
        sleep 2
    done
    echo "[entrypoint] Redis is ready."
else
    echo "[entrypoint] REDIS_URL is not set — skipping Redis check (in-memory mode)."
fi

# ---------------------------------------------------------------------------
# 4. Initialise the database: apply Alembic migrations, seed reference data,
#    ensure the default admin exists, and hash legacy passwords.
#    ``init_db.py`` delegates to ``database/migrations.py::bootstrap_database``
#    (the same routine ``main.py`` uses) — idempotent and safe to run always.
#    SKIP_DB_INIT=1 lets you skip this for specialised scenarios.
# ---------------------------------------------------------------------------
if [ "${SKIP_DB_INIT:-0}" = "1" ]; then
    echo "[entrypoint] SKIP_DB_INIT=1 → skipping database initialisation."
else
    echo "[entrypoint] Running database initialisation (Alembic + seeds)..."
    python init_db.py
    echo "[entrypoint] Database initialisation complete."
fi

# ---------------------------------------------------------------------------
# 5. Hand off to the main command (default: python main.py).
#    exec ensures the child becomes PID 1 and receives SIGTERM/SIGINT directly.
# ---------------------------------------------------------------------------
echo "[entrypoint] Starting main process: $*"
exec "$@"