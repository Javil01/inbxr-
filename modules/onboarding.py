"""
InbXr — Onboarding Progress Tracker
───────────────────────────────────
The onboarding flow is four steps mapped to the layer-thesis product
architecture: Welcome (verify) → Connect (ESP or CSV) → Read (first
Signal Score) → Act (first Signal Recommendation). Every step is
derivable from existing data, so the state updates automatically as
the user interacts with the product. No extra writes needed.

Layer meaning of each step:
    1. Welcome:   prove you are who you say (email verification)
    2. Connect:   give the Signal Engine something to read
    3. Read:      the first Signal Score lands
    4. Act:       the first Signal Recommendation is set

The old 5-step flow (email test, sender check, monitor) is retired.
Those tools still exist under the Toolkit menu but aren't required
first-time steps — they're destinations, not onboarding friction.
"""

from modules.database import fetchone

STEPS = [
    {
        "key": "email_verified",
        "title": "Verify your email",
        "desc": "Confirm your email so the Signal Engine can send your weekly report and alerts.",
        "href": "/account",
        "cta": "Verify email",
        "icon": "mail",
    },
    {
        "key": "connected_source",
        "title": "Connect your list",
        "desc": "Connect Mailchimp, ActiveCampaign, Mailgun, or AWeber — or upload a CSV if you don't have ESP access. The Signal Engine needs a list to read.",
        "href": "/account/integrations",
        "cta": "Connect",
        "icon": "link",
    },
    {
        "key": "first_signal_score",
        "title": "Get your first Signal Score",
        "desc": "See all 7 Inbox Signals and your composite grade. Takes under 60 seconds once your list is connected.",
        "href": "/signal-score",
        "cta": "Read signals",
        "icon": "activity",
    },
    {
        "key": "first_signal_rule",
        "title": "Set your first Signal Recommendation",
        "desc": "Pick one automation rule that runs every 6 hours. InbXr will watch for the condition and act on it so you don't have to.",
        "href": "/signal-rules",
        "cta": "Set recommendation",
        "icon": "zap",
    },
]


def get_onboarding_status(user_id):
    """Compute onboarding progress from existing tables. Each step's
    completion is inferred from a specific signal in the DB, so the
    user never has to "mark complete" anything — it just flips as
    they use the product."""
    user = fetchone(
        "SELECT email_verified, onboarding_dismissed_at FROM users WHERE id = ?",
        (user_id,),
    )
    if not user:
        return None

    completed = {}

    # Step 1: email verification
    completed["email_verified"] = bool(user.get("email_verified"))

    # Step 2: connected list. True if the user has an active ESP
    # integration OR has uploaded a CSV that produced a signal_scores row.
    completed["connected_source"] = bool(fetchone(
        "SELECT 1 FROM esp_integrations WHERE user_id = ? AND status = 'active' LIMIT 1",
        (user_id,),
    )) or bool(fetchone(
        "SELECT 1 FROM signal_scores WHERE user_id = ? AND data_source = 'csv_upload' LIMIT 1",
        (user_id,),
    ))

    # Step 3: first Signal Score. True if signal_scores has any row for
    # this user regardless of source.
    completed["first_signal_score"] = bool(fetchone(
        "SELECT 1 FROM signal_scores WHERE user_id = ? LIMIT 1",
        (user_id,),
    ))

    # Step 4: first Signal Recommendation. True if signal_rules has any
    # row for this user. We don't require it to be active or live — just
    # that they took the action of creating one.
    completed["first_signal_rule"] = bool(fetchone(
        "SELECT 1 FROM signal_rules WHERE user_id = ? LIMIT 1",
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
