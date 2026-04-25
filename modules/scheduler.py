"""
InbXr — Background Scheduler
Uses APScheduler to run periodic tasks: blocklist scans, log cleanup.

Single-worker guard: gunicorn runs N workers in production. Without a guard,
each worker would spin up its own BackgroundScheduler and every job would
fire N times — duplicate digest emails, duplicate hourly DB backups, duplicate
DNS scans. The guard below uses an OS-level file lock on a shared path so
exactly one worker (the first to start) holds the scheduler.
"""

import logging
import os
import sys
import atexit
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler = None
_scheduler_lock_fd = None  # held for the lifetime of the process when we own the lock


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


def _scheduled_onboarding_emails():
    """Dispatch the signal-aware onboarding email sequence.

    Fires once a day; each email in the sequence has its own signup-age
    window + precondition SQL to avoid duplicate or irrelevant sends.
    """
    from modules.onboarding_emails import dispatch_onboarding_emails

    try:
        stats = dispatch_onboarding_emails()
        logger.info(
            "[SCHEDULER] Onboarding emails: sent=%d skipped_precond=%d "
            "skipped_sent=%d errors=%d",
            stats['sent'], stats['skipped_preconditions'],
            stats['skipped_already_sent'], stats['errors'],
        )
    except Exception as e:
        logger.exception("[SCHEDULER] Onboarding emails failed: %s", e)


def _scheduled_dogfood_refresh():
    """Refresh the dogfood Signal Score for inbxr.us once per night.
    The homepage dogfood badge reads the latest row from dogfood_score
    so "this score updates automatically" is a claim the engine backs up.
    """
    from modules.dogfood import refresh_dogfood_score

    try:
        row = refresh_dogfood_score()
        if row:
            logger.info(
                "[SCHEDULER] Dogfood: %s → %d (%s)",
                row['domain'], row['total'], row['grade'],
            )
        else:
            logger.warning("[SCHEDULER] Dogfood refresh returned no row")
    except Exception as e:
        logger.exception("[SCHEDULER] Dogfood refresh failed: %s", e)


def _scheduled_weekly_signal_report():
    """Dispatch the weekly Signal Report email to all eligible users.
    Runs Monday 08:00 UTC. Dedup via weekly_signal_report_log table."""
    from modules.weekly_signal_report import dispatch_weekly_reports

    try:
        stats = dispatch_weekly_reports()
        logger.info(
            "[SCHEDULER] Weekly report: eligible=%d sent=%d skipped=%d failed=%d",
            stats['total_eligible'], stats['sent'], stats['skipped'], stats['failed'],
        )
    except Exception as e:
        logger.exception("[SCHEDULER] Weekly report failed: %s", e)


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
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', 'InbXr Team', ?, ?,
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


def _scheduled_esp_sync():
    """
    Sync all active ESP integrations AND run Signal Watch.

    This single job handles:
    1. Aggregate ESP sync (existing modules/esp_sync.py) — updates esp_sync_snapshots
    2. Per-contact sync for Phase 2 supported ESPs (Mailchimp, ActiveCampaign, Mailgun, AWeber)
    3. Signal Score recalculation for all Pro+ users
    4. Early Warning alert evaluation
    5. Signal Rules execution (alert-only, dry-run default)

    Reference: SIGNAL_SPEC.md Phase 3 — extends this job rather than adding a parallel one.
    """
    from modules.esp_sync import sync_all_active
    from modules.database import fetchall

    # Step 1: existing aggregate sync
    try:
        result = sync_all_active()
        logger.info("[SCHEDULER] ESP aggregate sync: %d synced, %d errors",
                     result["synced"], result["errors"])
    except Exception as e:
        logger.error("[SCHEDULER] ESP aggregate sync failed: %s", e)

    # Step 2 + 3: Signal Watch — per-contact sync and signal calculation
    try:
        _signal_watch_for_all_users()
    except Exception as e:
        logger.error("[SCHEDULER] Signal Watch failed: %s", e)


def _signal_watch_for_all_users():
    """
    For each Pro+ user with active integrations, pull per-contact data
    (for ESPs that support it), calculate Signal Score, fire Early Warning
    alerts, and execute live Signal Rules.

    Non-supported ESPs (Instantly, Smartlead, GHL) fall back to aggregate-only
    signal calculation using data already in esp_sync_snapshots.
    """
    from modules.database import fetchall

    # Get Pro+ users with active integrations
    users = fetchall(
        """SELECT DISTINCT u.id, u.tier, u.email
           FROM users u
           JOIN esp_integrations i ON i.user_id = u.id
           WHERE u.tier IN ('pro', 'agency', 'api')
           AND u.status = 'active'
           AND i.status = 'active'"""
    )

    logger.info("[SIGNAL_WATCH] Starting for %d Pro+ users", len(users))
    synced = 0
    errors = 0

    for u in users:
        try:
            _signal_watch_for_user(u['id'], u['tier'])
            synced += 1
        except Exception as e:
            logger.exception("[SIGNAL_WATCH] User %s failed", u['id'])
            errors += 1

    logger.info("[SIGNAL_WATCH] Done: %d synced, %d errors", synced, errors)


def _signal_watch_for_user(user_id, tier):
    """Run Signal Watch for a single user."""
    from modules.database import fetchall, fetchone
    from modules.signal_score import calculate_signal_score, save_signal_score
    from modules.esp_contact_sync import (
        sync_contacts_for_integration, get_contacts_for_signal_score,
    )
    from modules.signal_alerts import check_early_warning_conditions
    from modules.signal_rules import execute_signal_rules

    # Get user's active integrations
    integrations = fetchall(
        """SELECT id, provider FROM esp_integrations
           WHERE user_id = ? AND status = 'active'""",
        (user_id,),
    )

    for integration in integrations:
        integration_id = integration['id']
        provider = integration['provider']

        # Step 1: pull per-contact data (only for supported ESPs)
        if provider in ('mailchimp', 'activecampaign', 'mailgun', 'aweber'):
            try:
                sync_result = sync_contacts_for_integration(integration_id)
                if sync_result.get('error'):
                    logger.warning(
                        "[SIGNAL_WATCH] sync error for integration %s (%s): %s",
                        integration_id, provider, sync_result['error']
                    )
            except Exception as e:
                logger.exception(
                    "[SIGNAL_WATCH] sync exception for integration %s (%s)",
                    integration_id, provider
                )

        # Step 2: fetch contacts from contact_segments (if any)
        contacts = get_contacts_for_signal_score(user_id, integration_id, limit=50000)

        # Step 3: fetch auth data
        auth_data = _get_auth_data_for_user(user_id)

        # Step 4: calculate Signal Score
        try:
            result = calculate_signal_score(
                user_id=user_id,
                esp_integration_id=integration_id,
                contact_data=contacts,
                auth_data=auth_data,
                esp_type=provider,
                tier=tier,
            )
            save_signal_score(user_id, integration_id, result)
        except Exception as e:
            logger.exception(
                "[SIGNAL_WATCH] score calculation failed for user %s integration %s",
                user_id, integration_id
            )
            continue

        # Step 5: Early Warning
        try:
            ew_result = check_early_warning_conditions(user_id, result)
            if ew_result.get('alerts_created', 0) > 0:
                logger.info(
                    "[SIGNAL_WATCH] Fired %d Early Warning alerts for user %s",
                    ew_result['alerts_created'], user_id
                )
        except Exception as e:
            logger.exception("[SIGNAL_WATCH] Early Warning failed for user %s", user_id)

        # Step 6: Signal Rules (live rules only — dry-run ignored)
        try:
            rules_result = execute_signal_rules(user_id, integration_id, result, contacts)
            if rules_result.get('rules_fired', 0) > 0:
                logger.info(
                    "[SIGNAL_WATCH] Fired %d rules for user %s",
                    rules_result['rules_fired'], user_id
                )
        except Exception as e:
            logger.exception("[SIGNAL_WATCH] Signal Rules failed for user %s", user_id)


def _get_auth_data_for_user(user_id):
    """
    Fetch authentication data for Signal Score calculation.
    Reads from existing dns_monitor_snapshots + monitor_scans tables.
    """
    from modules.database import fetchone

    # Get latest DNS monitor snapshot across user's monitors
    dns = fetchone(
        """SELECT ds.spf_record, ds.dkim_valid, ds.dmarc_record, ds.dmarc_policy, ds.issues
           FROM dns_monitor_snapshots ds
           JOIN user_monitors um ON um.id = ds.monitor_id
           WHERE um.user_id = ?
           ORDER BY ds.scanned_at DESC LIMIT 1""",
        (user_id,),
    )

    # Get latest blocklist scan
    bl = fetchone(
        """SELECT ms.listed_count, ms.clean
           FROM monitor_scans ms
           JOIN user_monitors um ON um.id = ms.monitor_id
           WHERE um.user_id = ?
           ORDER BY ms.scanned_at DESC LIMIT 1""",
        (user_id,),
    )

    auth_data = {
        'spf_valid': bool(dns and dns.get('spf_record')),
        'dkim_valid': bool(dns and dns.get('dkim_valid')),
        'dmarc_policy': (dns.get('dmarc_policy') if dns else None) or 'none',
        'list_unsubscribe': False,  # Not tracked yet — List-Unsubscribe check is Phase 5 polish
        'blacklisted': bool(bl and bl.get('listed_count', 0) > 0),
        'blacklists_count': (bl.get('listed_count') if bl else 0) or 0,
    }
    return auth_data


def _scheduled_alert_cleanup():
    """Clean up old read alerts."""
    from modules.alerts import cleanup_old_alerts

    try:
        cleanup_old_alerts(90)
        logger.info("[SCHEDULER] Old alerts cleaned up")
    except Exception as e:
        logger.error("[SCHEDULER] Alert cleanup failed: %s", e)


# ── Scheduler init ─────────────────────────────────────


def _acquire_scheduler_lock():
    """Try to take an exclusive OS-level lock on a shared file. Returns True if
    this process (worker) owns the scheduler and should start it.

    Uses fcntl on POSIX (Railway, Linux) and msvcrt on Windows. The lock is
    held for the lifetime of the process via _scheduler_lock_fd; releasing the
    fd (process exit) automatically releases the lock so another worker can
    take over if the leader dies.
    """
    global _scheduler_lock_fd

    # Allow opting out (useful for one-off management commands / tests).
    if os.environ.get("INBXR_DISABLE_SCHEDULER", "").lower() in ("1", "true", "yes"):
        logger.info("[SCHEDULER] Disabled via INBXR_DISABLE_SCHEDULER env var")
        return False

    lock_dir = os.environ.get("INBXR_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    try:
        os.makedirs(lock_dir, exist_ok=True)
    except Exception:
        logger.exception("[SCHEDULER] Could not create lock dir, skipping leader election")
        # Fail-open is dangerous (would re-introduce duplicate jobs); fail-closed
        # so that *no* worker runs the scheduler if we can't coordinate.
        return False
    lock_path = os.path.join(lock_dir, ".scheduler.lock")

    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    except Exception:
        logger.exception("[SCHEDULER] Could not open lock file at %s", lock_path)
        return False

    try:
        if sys.platform.startswith("win"):
            import msvcrt
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                os.close(fd)
                logger.info("[SCHEDULER] Another worker holds the scheduler lock; staying idle")
                return False
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                os.close(fd)
                logger.info("[SCHEDULER] Another worker holds the scheduler lock; staying idle")
                return False
    except Exception:
        logger.exception("[SCHEDULER] Lock acquisition raised; staying idle")
        try:
            os.close(fd)
        except Exception:
            pass
        return False

    _scheduler_lock_fd = fd
    # Best-effort write of pid for ops debugging.
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
    except Exception:
        pass
    logger.info("[SCHEDULER] Acquired scheduler lock (pid=%s, path=%s)", os.getpid(), lock_path)
    return True


def init_scheduler(app):
    """Initialize and start the background scheduler.

    Only the first gunicorn worker that acquires the cross-process lock will
    actually start the scheduler. Other workers no-op so jobs fire exactly
    once per interval globally.
    """
    global _scheduler

    if _scheduler is not None:
        return

    if not _acquire_scheduler_lock():
        return

    # Make sure we release the lock cleanly on shutdown (best-effort; OS
    # releases it on process exit anyway).
    atexit.register(_release_scheduler_lock)

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

    # Job 9: Sync ESP integrations every 6 hours
    _scheduler.add_job(
        _scheduled_esp_sync,
        IntervalTrigger(hours=6),
        id="esp_integration_sync",
        name="ESP Integration Sync",
        replace_existing=True,
        next_run_time=None,
    )

    # Job 8: Auto-generate one blog post daily — DISABLED for V1.
    # Reason: daily AI-generated posts produce filler that hurts SEO authority
    # more than helps. Google spam updates specifically target this pattern.
    # V1 moves to 2 high-quality pieces per month, written deliberately.
    # Function is kept in this module so it can be re-enabled manually if needed.
    # _scheduler.add_job(
    #     _scheduled_daily_blog_post,
    #     CronTrigger(hour=9, minute=0),
    #     id="daily_blog_post",
    #     name="Daily Blog Post Generator",
    #     replace_existing=True,
    # )

    # Job 10: Onboarding email sequence — daily at 14:00 UTC
    # Reads users table by signup age + existing signal state and sends
    # the right nudge email for each user. Dedup via onboarding_email_log.
    _scheduler.add_job(
        _scheduled_onboarding_emails,
        CronTrigger(hour=14, minute=0),
        id="onboarding_emails",
        name="Signal Onboarding Email Sequence",
        replace_existing=True,
    )

    # Job 12: Weekly Signal Report email — Monday 08:00 UTC
    # Retention loop for Pro/Agency users. One concrete email per week
    # with their current score, delta, weakest signal, and one action.
    _scheduler.add_job(
        _scheduled_weekly_signal_report,
        CronTrigger(day_of_week='mon', hour=8, minute=0),
        id="weekly_signal_report",
        name="Weekly Signal Report Email",
        replace_existing=True,
    )

    # Job 11: Dogfood Signal Score refresh — DISABLED for V1.
    # The homepage badge was removed to avoid broadcasting a weak self-score
    # before inbxr.us's own SPF/DKIM/DMARC are tightened. Engine + table
    # remain available for manual testing and for later re-enablement once
    # the brand domain can ship an A-grade score cleanly.
    # _scheduler.add_job(
    #     _scheduled_dogfood_refresh,
    #     CronTrigger(hour=3, minute=0),
    #     id="dogfood_refresh",
    #     name="Dogfood Signal Score Refresh",
    #     replace_existing=True,
    # )

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


def _release_scheduler_lock():
    """Release the cross-process scheduler lock. Called on process exit."""
    global _scheduler_lock_fd
    fd = _scheduler_lock_fd
    if fd is None:
        return
    try:
        if sys.platform.startswith("win"):
            try:
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
        else:
            try:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
    finally:
        try:
            os.close(fd)
        except Exception:
            pass
        _scheduler_lock_fd = None
