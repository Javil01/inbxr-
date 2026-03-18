"""
INBXR — Background Scheduler
Uses APScheduler to run periodic tasks: blocklist scans, log cleanup.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler = None


# ── Job functions (must be defined before init_scheduler) ──


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


def _scheduled_dns_scan():
    """Scan DNS auth for all monitored domains of paid users."""
    from modules.dns_monitor import scan_all_monitored_dns

    try:
        result = scan_all_monitored_dns()
        logger.info("[SCHEDULER] DNS scan: %d scanned, %d alerted",
                     result["scanned"], result["alerted"])
    except Exception as e:
        logger.error("[SCHEDULER] DNS scan failed: %s", e)


def _scheduled_daily_digest():
    """Send daily digest emails."""
    from modules.alerts import send_digest_emails

    try:
        sent = send_digest_emails("daily")
        logger.info("[SCHEDULER] Daily digest: sent %d emails", sent)
    except Exception as e:
        logger.error("[SCHEDULER] Daily digest failed: %s", e)


def _scheduled_weekly_digest():
    """Send weekly digest emails."""
    from modules.alerts import send_digest_emails

    try:
        sent = send_digest_emails("weekly")
        logger.info("[SCHEDULER] Weekly digest: sent %d emails", sent)
    except Exception as e:
        logger.error("[SCHEDULER] Weekly digest failed: %s", e)


def _scheduled_daily_blog_post():
    """Auto-generate and publish one SEO blog post per day."""
    import json
    import re

    from modules.database import fetchall, fetchone, execute
    from modules.blog_ai import generate_blog_post_long, generate_topic, BlogAIError

    try:
        # Check if a post was already published today
        today_post = fetchone(
            "SELECT id FROM blog_posts WHERE date(published_at) = date('now') AND id > 2"
        )
        if today_post:
            logger.info("[SCHEDULER] Blog: already published today, skipping")
            return

        # Get existing titles to avoid duplicates
        existing = fetchall(
            "SELECT title, slug FROM blog_posts ORDER BY published_at DESC LIMIT 50"
        )
        existing_titles = [p["title"] for p in existing]

        # Generate a fresh topic via AI
        topic_data = generate_topic(existing_titles)
        topic = topic_data["topic"]
        keyword = topic_data["keyword"]
        logger.info("[SCHEDULER] Blog: generating post for '%s' (keyword: %s)", topic, keyword)

        # Generate the full post (two-pass)
        data = generate_blog_post_long(
            topic=topic,
            target_keyword=keyword,
            existing_posts=existing,
        )

        # Generate featured image (CSS cover fallback if this fails)
        featured_image = ""
        try:
            from modules.blog_image import generate_blog_image
            img_path = generate_blog_image(data["title"], data["slug"], keyword=keyword)
            featured_image = img_path
            logger.info("[SCHEDULER] Blog image generated: %s", featured_image)
        except Exception as e:
            logger.exception("[SCHEDULER] Blog image generation failed (CSS cover will be used): %s", e)

        # Fix any CTA markers in content
        content = data.get("content", "")
        content = re.sub(r'href="\[CTA:(/[^\]]*)\]"', r'href="\1"', content)
        content = re.sub(r"href='\[CTA:(/[^\]]*)\]'", r"href='\1'", content)
        content = re.sub(r'\[CTA:/[^\]]*\]', '', content)

        # Calculate read time
        word_count = len(re.sub(r'<[^>]+>', '', content).split())
        read_time = max(1, round(word_count / 200))

        tags_json = json.dumps(data.get("tags", []))

        # Check slug doesn't collide
        if fetchone("SELECT id FROM blog_posts WHERE slug=?", (data["slug"],)):
            data["slug"] = data["slug"] + "-" + keyword.split()[0].lower()

        execute(
            """INSERT INTO blog_posts
               (title, slug, content, excerpt, meta_title, meta_description,
                featured_image, og_image, tags, status, author, read_time,
                keyword_target, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', 'INBXR Team', ?, ?,
                       datetime('now'))""",
            (
                data["title"], data["slug"], content,
                data.get("excerpt", ""), data["title"],
                data.get("meta_description", ""),
                featured_image, featured_image, tags_json,
                read_time, keyword,
            )
        )
        logger.info("[SCHEDULER] Blog: published '%s' (%d words) → /blog/%s",
                     data["title"], word_count, data["slug"])

    except BlogAIError as e:
        logger.error("[SCHEDULER] Blog generation failed: %s", e)
    except Exception as e:
        logger.exception("[SCHEDULER] Blog post job failed: %s", e)


def _scheduled_alert_cleanup():
    """Clean up old read alerts."""
    from modules.alerts import cleanup_old_alerts

    try:
        cleanup_old_alerts(90)
        logger.info("[SCHEDULER] Old alerts cleaned up")
    except Exception as e:
        logger.error("[SCHEDULER] Alert cleanup failed: %s", e)


# ── Scheduler init ─────────────────────────────────────


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

    # Job 4: DNS auth scan every 12 hours
    _scheduler.add_job(
        _scheduled_dns_scan,
        IntervalTrigger(hours=12),
        id="scheduled_dns_scan",
        name="DNS Auth Scan (all users)",
        replace_existing=True,
        next_run_time=None,
    )

    # Job 5: Daily digest emails
    _scheduler.add_job(
        _scheduled_daily_digest,
        IntervalTrigger(hours=24),
        id="daily_digest",
        name="Daily Alert Digest",
        replace_existing=True,
        next_run_time=None,
    )

    # Job 6: Weekly digest emails
    _scheduler.add_job(
        _scheduled_weekly_digest,
        IntervalTrigger(days=7),
        id="weekly_digest",
        name="Weekly Alert Digest",
        replace_existing=True,
        next_run_time=None,
    )

    # Job 7: Clean up old read alerts every 24 hours
    _scheduler.add_job(
        _scheduled_alert_cleanup,
        IntervalTrigger(hours=24),
        id="alert_cleanup",
        name="Old Alert Cleanup",
        replace_existing=True,
        next_run_time=None,
    )

    # Job 8: Auto-generate one blog post daily at 9:00 AM UTC
    _scheduler.add_job(
        _scheduled_daily_blog_post,
        CronTrigger(hour=9, minute=0),
        id="daily_blog_post",
        name="Daily Blog Post Generator",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("[SCHEDULER] Started with %d jobs", len(_scheduler.get_jobs()))


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
