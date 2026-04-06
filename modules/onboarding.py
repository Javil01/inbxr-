"""
InbXr — Onboarding progress tracker.
Derives completion status from existing tables (check_history, user_monitors, users).
No extra writes needed — progress updates automatically.
"""

from modules.database import fetchone

STEPS = [
    {
        "key": "email_verified",
        "title": "Verify Your Email",
        "desc": "Confirm your email address to unlock the full 7 Inbox Signals system.",
        "href": "/account",
        "cta": "Verify Email",
        "icon": "mail",
    },
    {
        "key": "first_email_test",
        "title": "Run Your First Inboxer Send Test",
        "desc": "Send a test email and get instant SPF, DKIM, DMARC, spam risk, and content analysis.",
        "href": "/",
        "cta": "Run Inboxer Send Test",
        "icon": "zap",
    },
    {
        "key": "first_domain_check",
        "title": "Run Inboxer Sender Check",
        "desc": "Enter your sending domain to verify SPF/DKIM/DMARC and get your Authentication Standing signal score.",
        "href": "/sender",
        "cta": "Check Domain",
        "icon": "shield",
    },
    {
        "key": "first_signal_score",
        "title": "Get Your First Signal Score",
        "desc": "Connect an ESP or upload a CSV to get a reading on all 7 Inbox Signals — your full deliverability picture in 60 seconds.",
        "href": "/signal-score",
        "cta": "Get Signal Score",
        "icon": "activity",
    },
    {
        "key": "first_monitor",
        "title": "Set Up Reputation Watch",
        "desc": "Add your domain for automated blocklist scanning across 110+ DNSBLs every 6 hours.",
        "href": "/blacklist-monitor",
        "cta": "Add Monitor",
        "icon": "eye",
    },
]


def get_onboarding_status(user_id):
    """Compute onboarding progress from existing data."""
    user = fetchone(
        "SELECT email_verified, onboarding_dismissed_at FROM users WHERE id = ?",
        (user_id,),
    )
    if not user:
        return None

    completed = {}

    completed["email_verified"] = bool(user.get("email_verified"))

    completed["first_email_test"] = bool(fetchone(
        "SELECT 1 FROM check_history WHERE user_id = ? AND tool = 'email_test' LIMIT 1",
        (user_id,),
    ))

    completed["first_domain_check"] = bool(fetchone(
        "SELECT 1 FROM check_history WHERE user_id = ? AND tool = 'domain_check' LIMIT 1",
        (user_id,),
    ))

    completed["first_monitor"] = bool(fetchone(
        "SELECT 1 FROM user_monitors WHERE user_id = ? LIMIT 1",
        (user_id,),
    ))

    # New: completed if user has any signal_scores row (CSV upload OR ESP-driven calculation)
    completed["first_signal_score"] = bool(fetchone(
        "SELECT 1 FROM signal_scores WHERE user_id = ? LIMIT 1",
        (user_id,),
    ))

    done_count = sum(1 for v in completed.values() if v)
    total = len(STEPS)

    return {
        "steps": [
            {**s, "completed": completed.get(s["key"], False)}
            for s in STEPS
        ],
        "done": done_count,
        "total": total,
        "all_complete": done_count == total,
        "dismissed": user.get("onboarding_dismissed_at") is not None,
        "pct": round(done_count / total * 100),
    }
