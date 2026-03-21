"""
InbXr — SQLite Backup Module
Safe hot backups using SQLite's .backup() API with automatic retention.
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Paths
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "data", "inbxr.db")
_BACKUP_DIR = os.path.join(_BASE_DIR, "data", "backups")

# Retention limits
_MAX_HOURLY = 48
_MAX_DAILY = 30


def _ensure_backup_dir():
    """Create the backups directory if it doesn't exist."""
    os.makedirs(_BACKUP_DIR, exist_ok=True)


def _backup_sqlite(dest_path):
    """
    Use SQLite's built-in .backup() for a safe hot copy.
    This works even while the database is being written to.
    """
    src = sqlite3.connect(_DB_PATH)
    dst = sqlite3.connect(dest_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _prune_backups(prefix, keep):
    """
    Remove oldest backups matching a prefix, keeping only `keep` most recent.
    """
    try:
        files = [
            f for f in os.listdir(_BACKUP_DIR)
            if f.startswith(prefix) and f.endswith(".db")
        ]
        files.sort(reverse=True)  # newest first (timestamp in name)

        for old_file in files[keep:]:
            path = os.path.join(_BACKUP_DIR, old_file)
            os.remove(path)
            logger.info("[BACKUP] Pruned old backup: %s", old_file)
    except Exception as e:
        logger.error("[BACKUP] Error pruning backups (prefix=%s): %s", prefix, e)


def run_backup():
    """
    Create an hourly backup and (if it's a new calendar day) a daily backup.
    Prunes old backups according to retention limits.
    Called by the scheduler every hour.
    """
    _ensure_backup_dir()

    now = datetime.now(timezone.utc)

    # ── Hourly backup ────────────────────────────────────
    hourly_name = now.strftime("hourly_%Y%m%d_%H%M%S.db")
    hourly_path = os.path.join(_BACKUP_DIR, hourly_name)

    try:
        _backup_sqlite(hourly_path)
        logger.info("[BACKUP] Hourly backup created: %s", hourly_name)
    except Exception as e:
        logger.error("[BACKUP] Hourly backup failed: %s", e)
        return

    _prune_backups("hourly_", _MAX_HOURLY)

    # ── Daily backup (one per calendar day) ──────────────
    today_prefix = now.strftime("daily_%Y%m%d")
    existing_daily = [
        f for f in os.listdir(_BACKUP_DIR)
        if f.startswith(today_prefix) and f.endswith(".db")
    ]

    if not existing_daily:
        daily_name = now.strftime("daily_%Y%m%d_%H%M%S.db")
        daily_path = os.path.join(_BACKUP_DIR, daily_name)
        try:
            _backup_sqlite(daily_path)
            logger.info("[BACKUP] Daily backup created: %s", daily_name)
        except Exception as e:
            logger.error("[BACKUP] Daily backup failed: %s", e)

        _prune_backups("daily_", _MAX_DAILY)
