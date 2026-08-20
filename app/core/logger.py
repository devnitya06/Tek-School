"""
Centralized structured logger for Tek School.

Usage:
    from app.core.logger import logger
    logger.info("Something happened")
    logger.warning("Slow query detected")
    logger.error("Crash!", exc_info=True)

Log file location: logs/app.log
"""

import logging
import sys
import os
from logging.handlers import RotatingFileHandler

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Log format — includes timestamp, level, file name, and message
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Root logger setup ──────────────────────────────────────────────────────────
logger = logging.getLogger("tekschool")
logger.setLevel(logging.INFO)

# Console handler — shows in docker logs
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

# File handler — rotates at 5MB, keeps last 3 files
file_handler = RotatingFileHandler(
    "logs/app.log",
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3,
    encoding="utf-8",
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

# Separate error-only log for quick crash hunting
error_handler = RotatingFileHandler(
    "logs/errors.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.addHandler(error_handler)

# Prevent duplicate log entries from root logger
logger.propagate = False
