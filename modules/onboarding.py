"""
INBXR — Onboarding progress tracker.
Derives completion status from existing tables (check_history, user_monitors, users).
No extra writes needed — progress updates automatically.
"""

from modules.database import fetchone

STEPS = [
    {
        "key": "email_verified",
        "title": "Verify Your Email",
        "desc": "Confirm your email address to unlock all features.",
        "href": "/account",
        "cta": "Verify Email",
        "icon": "mail",
    },
    {
        "key": "first_email_test",
        "title": "Run Your First Email Test",
        "desc": "Send a test email and get instant SPF, DKIM, DMARC, spam risk, and content analysis.",
        "href": "/",
        "cta": "Run Email Test",
        "icon": "zap",
    },
    {
        "key": "first_domain_check",
        "title": "Check Sender Authentication",
        "desc": "Enter your sending domain to verify auth records and get an A-F sender health grade.",
        "href": "/sender",
        "cta": "Check Domain",
        "icon": "shield",
    },
    {
        "key": "first_monitor",
        "title": "Set Up Blocklist Monitoring",
        "desc": "Add your domain for automated scanning across 110+ blocklists every 6 hours.",
        "href": "/blacklist-monitor",
        "cta": "Add Monitor",
        "icon": "eye",
    },
    {
        "key": "first_subject_test",
        "title": "Score a Subject Line",
        "desc": "A/B test 2-10 subject lines across 7 scoring dimensions before you send.",
        "href": "/subject-scorer",
        "cta": "Score Subjects",
        "icon": "type",
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

    completed["first_subject_test"] = bool(fetchone(
        "SELECT 1 FROM check_history WHERE user_id = ? AND tool = 'subject_test' LIMIT 1",
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
