"""
INBXR — Background Scheduler
Uses APScheduler to run periodic tasks: blocklist scans, log cleanup.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler = None


def init_scheduler(app):
    """Initialize and start the background scheduler."""
    global _scheduler

    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(daemon=True)

    # Job 1: Scan all monitored domains for paid users every 6 hours
    _scheduler.add_job(
        _scheduled_scan_all,
        IntervalTrigger(hours=6),
        id="scheduled_blocklist_scan",
        name="Blocklist Scan (all users)",
        replace_existing=True,
        next_run_time=None,  # Don't run immediately on startup
    )

    # Job 2: Clean up old usage logs daily
    _scheduler.add_job(
        _scheduled_cleanup,
        IntervalTrigger(hours=24),
        id="daily_log_cleanup",
        name="Daily Log Cleanup",
        replace_existing=True,
        next_run_time=None,
    )

    # Job 3: SQLite database backup every hour
    _scheduler.add_job(
        _scheduled_backup,
        IntervalTrigger(hours=1),
        id="hourly_db_backup",
        name="Hourly DB Backup",
        replace_existing=True,
        next_run_time=None,
    )

    _scheduler.start()
    logger.info("[SCHEDULER] Started with %d jobs", len(_scheduler.get_jobs()))


def _scheduled_scan_all():
    """Scan all monitored domains for users with scheduled_monitoring feature."""
    from modules.database import fetchall
    from modules.monitoring import scan_all_user_domains

    try:
        users = fetchall(
            "SELECT id, email, tier FROM users WHERE tier IN ('pro', 'agency', 'api')"
        )
        logger.info("[SCHEDULER] Running scheduled scan for %d users", len(users))

        for user in users:
            try:
                results = scan_all_user_domains(user["id"])
                scanned = len(results)
                issues = sum(1 for r in results if r.get("ok") and not r.get("clean", True))
                logger.info(
                    "[SCHEDULER] User %s: scanned %d domains, %d with listings",
                    user["email"], scanned, issues,
                )
            except Exception as e:
                logger.error("[SCHEDULER] Error scanning for user %s: %s", user["email"], e)
    except Exception as e:
        logger.error("[SCHEDULER] Scheduled scan failed: %s", e)


def _scheduled_cleanup():
    """Clean up old usage logs."""
    from modules.rate_limiter import cleanup_old_logs

    try:
        cleanup_old_logs(30)
        logger.info("[SCHEDULER] Old usage logs cleaned up")
    except Exception as e:
        logger.error("[SCHEDULER] Cleanup failed: %s", e)


def _scheduled_backup():
    """Run an hourly SQLite database backup."""
    from modules.backup import run_backup

    try:
        run_backup()
        logger.info("[SCHEDULER] Database backup completed")
    except Exception as e:
        logger.error("[SCHEDULER] Database backup failed: %s", e)


def get_scheduler_status():
    """Return dict with scheduler status and job info."""
    if _scheduler is None:
        return {"running": False, "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
            "pending": job.pending,
        })

    return {
        "running": _scheduler.running,
        "jobs": jobs,
    }
