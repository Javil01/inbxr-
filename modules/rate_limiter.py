"""
InbXr — Per-User + Per-IP Rate Limiting
Uses the usage_log table for persistent, tier-aware rate limiting.
Anonymous users: 3 checks/day across all tools.
"""

from datetime import datetime, timedelta, timezone

from flask import request, session

from modules.database import execute, fetchone
from modules.tiers import get_tier_limit

# Anonymous users get 3 uses per tool per day
ANON_DAILY_LIMIT = 3


def _get_identifier():
    """Return (user_id, ip_address) for the current request."""
    user_id = session.get("user_id")
    ip = request.remote_addr or "unknown"
    return user_id, ip


def _is_anonymous():
    """Check if the current request is from an anonymous user."""
    return not session.get("user_id")


def _get_user_tier():
    """Get the current user's tier name."""
    return session.get("user_tier", "free")


def log_usage(action):
    """Record a usage event for the current request."""
    user_id, ip = _get_identifier()
    execute(
        "INSERT INTO usage_log (user_id, ip_address, action) VALUES (?, ?, ?)",
        (user_id, ip, action),
    )


def check_rate_limit(action, limit_key=None):
    """
    Check if the current user/IP is within rate limits for the given action.
    Returns (allowed: bool, info: dict).
    """
    user_id, ip = _get_identifier()
    anonymous = _is_anonymous()

    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()

    # ── Anonymous: flat 3/day per tool, tracked by IP ────
    if anonymous:
        daily = fetchone(
            "SELECT COUNT(*) as cnt FROM usage_log WHERE ip_address = ? AND action = ? AND created_at > ?",
            (ip, action, day_ago),
        )
        daily_count = daily["cnt"] if daily else 0

        info = {
            "tier": "anonymous",
            "anonymous": True,
            "daily_count": daily_count,
            "daily_limit": ANON_DAILY_LIMIT,
        }

        if daily_count >= ANON_DAILY_LIMIT:
            info["blocked_by"] = "daily"
            info["signup_prompt"] = True
            return False, info

        # Tell the frontend how many are left
        info["remaining"] = ANON_DAILY_LIMIT - daily_count
        return True, info

    # ── Logged-in user: tier-based limits ────────────────
    tier = _get_user_tier()

    if limit_key is None:
        limit_key = _action_to_limit_key(action)

    hourly_limit = get_tier_limit(tier, "checks_per_hour")
    daily_limit = get_tier_limit(tier, limit_key)

    if limit_key != "checks_per_day":
        specific_daily = get_tier_limit(tier, limit_key)
        if specific_daily > 0:
            daily_limit = specific_daily

    hour_ago = (now - timedelta(hours=1)).isoformat()

    hourly = fetchone(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ? AND action = ? AND created_at > ?",
        (user_id, action, hour_ago),
    )
    daily = fetchone(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ? AND action = ? AND created_at > ?",
        (user_id, action, day_ago),
    )

    hourly_count = hourly["cnt"] if hourly else 0
    daily_count = daily["cnt"] if daily else 0

    info = {
        "tier": tier,
        "anonymous": False,
        "hourly_count": hourly_count,
        "hourly_limit": hourly_limit,
        "daily_count": daily_count,
        "daily_limit": daily_limit,
    }

    if hourly_count >= hourly_limit:
        info["blocked_by"] = "hourly"
        return False, info

    if daily_count >= daily_limit:
        info["blocked_by"] = "daily"
        return False, info

    return True, info


def check_monthly_limit(user_id, action, limit):
    """Check if a user is within a monthly limit for a given action.
    Returns (allowed: bool, remaining: int).
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    row = fetchone(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ? AND action = ? AND created_at >= ?",
        (user_id, action, month_start),
    )
    count = row["cnt"] if row else 0
    remaining = max(0, limit - count)
    return count < limit, remaining


def get_usage_summary(user_id=None):
    """Get usage summary for a user (for account page)."""
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()

    if user_id:
        rows = fetchone(
            """SELECT
                COUNT(*) as total_today,
                COUNT(DISTINCT action) as tools_used
               FROM usage_log
               WHERE user_id = ? AND created_at > ?""",
            (user_id, day_ago),
        )
    else:
        return {"total_today": 0, "tools_used": 0}

    return dict(rows) if rows else {"total_today": 0, "tools_used": 0}


def cleanup_old_logs(days=30):
    """Remove usage logs older than N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    execute("DELETE FROM usage_log WHERE created_at < ?", (cutoff,))


def _action_to_limit_key(action):
    """Map an action name to its tier limit key."""
    mapping = {
        "domain_check": "checks_per_day",
        "copy_analysis": "checks_per_day",
        "email_test": "checks_per_day",
        "email_verify": "email_verifications_per_day",
        "blocklist_scan": "checks_per_day",
        "subject_test": "subject_tests_per_day",
        "placement_test": "placement_tests_per_day",
        "header_analysis": "checks_per_day",
        "bimi_check": "checks_per_day",
        "warmup": "checks_per_day",
    }
    return mapping.get(action, "checks_per_day")
