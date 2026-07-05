"""One-time migration: hash plain-text passwords in the ``users`` table.

Earlier versions of the project stored staff passwords in plain text. After
introducing bcrypt hashing (see ``utils/security.py``), existing rows must be
converted so that login continues to work for accounts created before the
change.

Usage:
    python migrate_passwords.py            # run the migration
    python migrate_passwords.py --dry-run  # only report, do not write

The script is idempotent: rows whose ``password`` already looks like a bcrypt
hash (``$2a$`` / ``$2b$`` / ``$2y$``) are skipped, so it is safe to run
multiple times.
"""
import argparse
import asyncio
import logging
import sys

from database.connection import check_db_connection, close_db_pool, get_db_pool
from utils.logger import setup_logging
from utils.security import hash_password, is_hashed

logger = logging.getLogger(__name__)


async def migrate_passwords(dry_run: bool = False) -> int:
    """Hash all plain-text passwords found in the ``users`` table.

    Args:
        dry_run: If True, only report which rows would be changed without
            actually writing to the database.

    Returns:
        The number of rows that were migrated (or would be, in dry-run mode).
    """
    pool = await get_db_pool()
    migrated = 0

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, username, password FROM users WHERE password IS NOT NULL"
        )

    for row in rows:
        stored = row["password"]
        if not stored or is_hashed(stored):
            continue  # already hashed (or empty) — nothing to do

        new_hash = hash_password(stored)
        action = "Would migrate" if dry_run else "Migrated"
        logger.info("%s user '%s' (id=%s).", action, row["username"], row["id"])

        if dry_run:
            migrated += 1
            continue

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET password = $1 WHERE id = $2",
                new_hash,
                row["id"],
            )
        migrated += 1

    return migrated


async def main(dry_run: bool = False) -> int:
    """Entry point: set up logging, run migration, close the pool.

    Returns:
        Process exit code (0 on success, 1 on database connection failure).
    """
    setup_logging()
    mode = "DRY-RUN" if dry_run else "APPLY"
    logger.info("=" * 50)
    logger.info("Password migration (%s)", mode)
    logger.info("=" * 50)

    if not await check_db_connection():
        logger.error("Cannot connect to database. Check .env settings.")
        return 1

    try:
        count = await migrate_passwords(dry_run=dry_run)
        verb = "would be" if dry_run else "were"
        logger.info("Done! %d password(s) %s migrated.", count, verb)
        return 0
    finally:
        await close_db_pool()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hash plain-text passwords stored in the users table.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report which rows would be migrated; do not write changes.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        exit_code = asyncio.run(main(dry_run=args.dry_run))
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user.")
        exit_code = 130
    except Exception as exc:  # pragma: no cover - top-level safety net
        logger.error("Fatal error during migration: %s", exc, exc_info=True)
        exit_code = 1
    sys.exit(exit_code)