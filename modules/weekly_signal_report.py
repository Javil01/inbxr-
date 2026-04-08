"""
InbXr — Weekly Signal Report Email
──────────────────────────────────
Monday morning retention hook. For every active Pro/Agency user who
has at least one Signal Score on record, send a short summary email
showing the current score, the week-over-week delta, the weakest
signal, and a single recommended action.

This is the primary retention loop for MRR. Every Monday the user
gets one concrete reminder that InbXr is watching their list and
one concrete thing to do about it. No marketing fluff, no "tips of
the week", no unsubscribes wrapped in newsletters.

Scheduler: modules/scheduler.py Job 12 (new), cron Mon 08:00 UTC.
Dedup: one row per (user_id, week_start_date) in weekly_signal_report_log.
Sender: Brevo HTTP API via modules.mailer._send.

Content:
  - Subject: "Signal Report · Score 84 · +2 this week"
  - Body: grade line, delta, weakest signal, one CTA back to dashboard
  - Plain text + HTML (mailer handles both)
"""

import logging
from datetime import datetime, timedelta

from modules.database import fetchone, fetchall, execute
from modules.signal_copy import (
    SIGNAL_DIMENSION_COPY,
    SIGNAL_GRADE_COPY,
    ACTION_RECOMMENDATIONS,
)

logger = logging.getLogger(__name__)

SIGNAL_ORDER = [
    "bounce_exposure",
    "engagement_trajectory",
    "acquisition_quality",
    "domain_reputation",
    "dormancy_risk",
    "authentication_standing",
    "decay_velocity",
]

SIGNAL_MAX_POINTS = {
    "bounce_exposure": 25,
    "engagement_trajectory": 25,
    "acquisition_quality": 15,
    "domain_reputation": 15,
    "dormancy_risk": 10,
    "authentication_standing": 5,
    "decay_velocity": 5,
}


def _week_start_date():
    """ISO date of the most recent Monday (UTC). Used as the dedup key."""
    today = datetime.utcnow().date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def _find_weakest(score_row):
    ratios = []
    for key in SIGNAL_ORDER:
        max_pts = SIGNAL_MAX_POINTS[key]
        value = score_row.get(f"{key}_score") or 0
        ratios.append((key, value / max_pts if max_pts else 1))
    ratios.sort(key=lambda x: x[1])
    return ratios[0][0] if ratios else None


def _load_previous_score(user_id, before_datetime):
    """Most recent score at least 6 days older than now, used as the
    week-over-week baseline. Returns None if the user has no history."""
    row = fetchone(
        """SELECT total_signal_score FROM signal_score_history
           WHERE user_id = ? AND recorded_at <= ?
           ORDER BY recorded_at DESC LIMIT 1""",
        (user_id, before_datetime),
    )
    return row


def _already_sent_this_week(user_id, week_start):
    row = fetchone(
        "SELECT id FROM weekly_signal_report_log "
        "WHERE user_id = ? AND week_start_date = ?",
        (user_id, week_start),
    )
    return row is not None


def _log_sent(user_id, week_start, current_score, delta, delivery_status="sent"):
    try:
        execute(
            """INSERT OR IGNORE INTO weekly_signal_report_log
                (user_id, week_start_date, current_score, delta, delivery_status)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, week_start, current_score, delta, delivery_status),
        )
    except Exception:
        logger.exception("[WEEKLY_REPORT] failed to log")


def _build_email_content(user, score_row, delta, weakest_key):
    """Return (subject, html_body, text_body) for the weekly email."""
    name = user.get("display_name") or "there"
    score = int(round(score_row.get("total_signal_score") or 0))
    grade = score_row.get("signal_grade", "F")
    grade_copy = SIGNAL_GRADE_COPY.get(grade, {})
    grade_label = grade_copy.get("label", grade)

    weakest_meta = SIGNAL_DIMENSION_COPY.get(weakest_key, {})
    weakest_name = weakest_meta.get("name", weakest_key)
    action = ACTION_RECOMMENDATIONS.get(weakest_key, {})
    action_label = action.get("label", "Review your weakest signal.")
    action_url = action.get("url", "/signal-score")

    # Subject with delta indicator
    if delta is None:
        delta_bit = ""
    elif delta > 0:
        delta_bit = f" &middot; +{delta} this week"
    elif delta < 0:
        delta_bit = f" &middot; {delta} this week"
    else:
        delta_bit = " &middot; flat this week"
    subject = f"Signal Report &middot; Score {score} &middot; Grade {grade}" + (delta_bit if delta is not None else "")
    # Email clients don't render &middot; reliably in the subject
    subject = subject.replace("&middot;", "·")

    # Delta text for body
    if delta is None:
        delta_line = "This is your first weekly report. Next week we'll show your week-over-week change."
    elif delta > 0:
        delta_line = f"You gained <strong>+{delta} points</strong> since last week. Keep it up."
    elif delta < 0:
        delta_line = f"You dropped <strong>{delta} points</strong> since last week. Read the recommended action below."
    else:
        delta_line = "Your score held steady this week. The Signal Engine is watching for drift."

    # HTML body — single-column, safe for all clients
    html = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; max-width: 560px; margin: 0 auto; padding: 28px 24px; color: #0f172a;">

  <p style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #2563eb; margin: 0 0 10px;">InbXr · Weekly Signal Report</p>

  <h1 style="font-size: 1.8rem; font-weight: 900; margin: 0 0 4px; color: #0f172a;">Hi {name},</h1>

  <p style="font-size: 1rem; line-height: 1.55; color: #334155; margin: 0 0 24px;">
    Your Signal Score this week is <strong style="color: #0f172a;">{score}/100 · Grade {grade}</strong> ({grade_label}).
    {delta_line}
  </p>

  <div style="background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 12px; padding: 20px 22px; margin: 0 0 24px;">
    <p style="font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #0284c7; margin: 0 0 8px;">Your weakest signal this week</p>
    <p style="font-size: 1.1rem; font-weight: 800; color: #0f172a; margin: 0 0 6px;">{weakest_name}</p>
    <p style="font-size: 0.9rem; line-height: 1.55; color: #334155; margin: 0 0 14px;">{action_label}</p>
    <a href="https://inbxr.us{action_url}" style="display: inline-block; background: #2563eb; color: #ffffff; padding: 10px 22px; border-radius: 999px; font-size: 0.85rem; font-weight: 700; text-decoration: none;">Take action &rarr;</a>
  </div>

  <p style="font-size: 0.85rem; line-height: 1.55; color: #64748b; margin: 0 0 20px;">
    Signal Watch is reading all 7 Inbox Signals every 6 hours. Your dashboard is always current.
  </p>

  <p style="text-align: center; margin: 20px 0 0;">
    <a href="https://inbxr.us/signal-score" style="font-size: 0.88rem; color: #2563eb; font-weight: 700; text-decoration: none;">Open your Signal Score dashboard &rarr;</a>
  </p>

  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 28px 0 16px;">

  <p style="font-size: 0.7rem; color: #94a3b8; margin: 0; text-align: center;">
    You're receiving this because you have an active Pro or Agency InbXr account.
    <a href="https://inbxr.us/account" style="color: #64748b;">Manage email preferences</a>
  </p>

</div>
    """.strip()

    text = f"""InbXr Weekly Signal Report

Hi {name},

Your Signal Score this week: {score}/100 · Grade {grade} ({grade_label})

{delta_line.replace('<strong>', '').replace('</strong>', '')}

YOUR WEAKEST SIGNAL THIS WEEK
{weakest_name}
{action_label}
https://inbxr.us{action_url}

Signal Watch is reading all 7 Inbox Signals every 6 hours.
Open your dashboard: https://inbxr.us/signal-score

You're receiving this because you have an active Pro or Agency InbXr account.
Manage preferences: https://inbxr.us/account
"""
    return subject, html, text


def send_weekly_report_for_user(user):
    """Send one weekly report email to one user. Returns True on success.
    Respects the dedup log — only sends once per ISO week."""
    user_id = user["id"]
    week_start = _week_start_date()

    if _already_sent_this_week(user_id, week_start):
        return False

    latest = fetchone(
        "SELECT * FROM signal_scores WHERE user_id = ? "
        "ORDER BY calculated_at DESC LIMIT 1",
        (user_id,),
    )
    if not latest:
        # No score yet — skip. A separate onboarding email handles this case.
        return False

    # Compute week-over-week delta from history
    week_ago_iso = (datetime.utcnow() - timedelta(days=6)).isoformat(sep=" ")
    previous = _load_previous_score(user_id, week_ago_iso)
    delta = None
    if previous and previous.get("total_signal_score") is not None:
        current = latest.get("total_signal_score") or 0
        delta = int(round(current - previous["total_signal_score"]))

    weakest = _find_weakest(latest)
    subject, html_body, text_body = _build_email_content(user, latest, delta, weakest)

    from modules.mailer import _send
    ok = _send(
        to_email=user["email"],
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )

    _log_sent(
        user_id=user_id,
        week_start=week_start,
        current_score=int(round(latest.get("total_signal_score") or 0)),
        delta=delta,
        delivery_status="sent" if ok else "failed",
    )
    return ok


def dispatch_weekly_reports():
    """Scheduler entry point. Finds every eligible user and sends the
    report. Returns a stats dict for logging."""
    users = fetchall(
        "SELECT id, email, display_name, tier FROM users "
        "WHERE tier IN ('pro', 'agency', 'api') "
        "AND email_verified = 1",
        (),
    )

    stats = {"total_eligible": len(users), "sent": 0, "skipped": 0, "failed": 0}
    for u in users:
        try:
            ok = send_weekly_report_for_user(u)
            if ok:
                stats["sent"] += 1
            else:
                stats["skipped"] += 1
        except Exception:
            stats["failed"] += 1
            logger.exception("[WEEKLY_REPORT] failed for user %s", u["id"])

    logger.info("[WEEKLY_REPORT] %s", stats)
    return stats
