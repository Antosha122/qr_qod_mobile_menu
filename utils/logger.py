"""Logging configuration for the application."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from config.settings import settings


def setup_logging() -> logging.Logger:
    """Configure and return the root logger.
    
    Sets up both file (rotating) and console handlers with a consistent format.
    Log level is controlled by the LOG_LEVEL setting.
    
    Returns:
        logging.Logger: The configured root logger.
    """
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)
    
    # Clear any existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    formatter = logging.Formatter(log_format, date_format)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (rotating: max 5MB per file, 3 backups)
    # The log directory is configurable via LOG_DIR (defaults to the project root).
    # In Docker, set LOG_DIR=/app/logs so logs land on the mounted volume.
    log_dir = os.environ.get("LOG_DIR", "")
    log_file = os.path.join(log_dir, "bot.log") if log_dir else "bot.log"
    try:
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        # If the log directory is not writable, fall back to console-only logging
        # so the application can still start (e.g. read-only containers).
        print(f"WARNING: could not create file handler at '{log_file}': {e}", file=sys.stderr)
    
    # Reduce noise from third-party libraries
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized at {settings.log_level} level.")
    return root_logger