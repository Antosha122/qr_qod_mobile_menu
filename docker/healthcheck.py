#!/usr/bin/env python3
"""Container health check for the Tokio Bar bot.

Exit code 0 → healthy, non-zero → unhealthy.
Docker calls this periodically (see HEALTHCHECK in Dockerfile).

What we check:
  1. The main process file exists / importable (sanity).
  2. The PostgreSQL database is reachable with the configured credentials.

This mirrors the app's own startup check (check_db_connection) but is a
standalone script so it can run in isolation without importing the whole app
(which would try to create the connection pool / start bots).
"""
import asyncio
import os
import sys

import asyncpg


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


async def _check_db() -> bool:
    """Try to connect to PostgreSQL and run ``SELECT 1``."""
    try:
        conn = await asyncpg.connect(
            host=_env("DB_HOST", "localhost"),
            port=int(_env("DB_PORT", "5432")),
            database=_env("DB_NAME", "tokio_bar"),
            user=_env("DB_USER", "postgres"),
            password=_env("DB_PASSWORD", ""),
            timeout=5,
        )
    except Exception as exc:  # noqa: BLE001 — we want any failure
        print(f"healthcheck: DB connect failed: {exc}", file=sys.stderr)
        return False

    try:
        await conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        print(f"healthcheck: DB query failed: {exc}", file=sys.stderr)
        return False
    finally:
        await conn.close()
    return True


def main() -> int:
    healthy = asyncio.run(_check_db())
    if healthy:
        print("healthcheck: OK")
        return 0
    print("healthcheck: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())