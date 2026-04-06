"""
InbXr — Signal-aware onboarding email sequence.

Scheduler job runs daily and dispatches onboarding emails based on
time-since-signup + current onboarding state. Each email is sent at most
once per user (tracked in onboarding_email_log table).

Sequence:
  day_1_welcome           — sent 1 day after signup if not verified
  day_3_first_score_nudge — sent 3 days after signup if no signal_scores row
  day_7_first_rule_nudge  — sent 7 days after signup if no signal_rules row
  day_14_check_in         — sent 14 days after signup if all onboarding complete

Uses the existing Brevo/SMTP mailer. Skips cleanly if mailer unconfigured.
"""

import logging
from datetime import datetime, timedelta, timezone

from modules.database import execute, fetchall, fetchone
from modules.mailer import _send, is_configured, BASE_URL

logger = logging.getLogger("inbxr.onboarding_emails")


# ── Email copy ─────────────────────────────────────────
#
# Each email is plain enough to render in any client. Inline CSS only.
# Subject lines are deliberately low-key to avoid promo-folder routing.

EMAILS = {
    "day_1_welcome": {
        "delay_days": 1,
        "subject": "Your first 5 minutes with InbXr",
        "precondition_sql": (
            "SELECT 1 FROM users WHERE id = ? AND email_verified = 0"
        ),
        "html_fn": lambda ctx: f"""
        <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;color:#0c1a3a;">
          <h2 style="margin:0 0 16px;font-size:22px;">Welcome to InbXr</h2>
          <p style="font-size:15px;line-height:1.6;color:#334155;">
            Thanks for signing up. If you do only one thing this week, do this:
          </p>
          <p style="font-size:15px;line-height:1.6;color:#334155;">
            <strong>Run Inboxer Sender Check on your sending domain.</strong>
            It takes 30 seconds and tells you whether your SPF / DKIM / DMARC
            setup will pass the 2025 bulk sender requirements at Gmail, Yahoo,
            and Microsoft. Most senders are surprised — it's the cheapest
            leverage in the whole 7-signal framework.
          </p>
          <p>
            <a href="{BASE_URL}/sender"
               style="display:inline-block;background:#16a34a;color:#fff;
                      padding:12px 24px;border-radius:8px;text-decoration:none;
                      font-weight:600;font-size:14px;">
              Run Inboxer Sender Check
            </a>
          </p>
          <p style="font-size:13px;color:#64748b;margin-top:24px;">
            Once your domain passes, you'll unlock the full 7 Inbox Signals
            read on your list (<a href="{BASE_URL}/signal-score"
            style="color:#16a34a;">Signal Score →</a>).
          </p>
          <hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0;">
          <p style="font-size:12px;color:#94a3b8;">
            You're getting this because you signed up at InbXr.us.
            <a href="{BASE_URL}/account" style="color:#94a3b8;">Manage preferences</a>.
          </p>
        </div>
        """,
    },

    "day_3_first_score_nudge": {
        "delay_days": 3,
        "subject": "You haven't pulled your Signal Score yet",
        "precondition_sql": (
            "SELECT 1 FROM users u WHERE u.id = ? AND NOT EXISTS "
            "(SELECT 1 FROM signal_scores s WHERE s.user_id = u.id LIMIT 1)"
        ),
        "html_fn": lambda ctx: f"""
        <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;color:#0c1a3a;">
          <h2 style="margin:0 0 16px;font-size:22px;">Quick read on your list?</h2>
          <p style="font-size:15px;line-height:1.6;color:#334155;">
            InbXr reads 7 signals your list is broadcasting at all times —
            bounce exposure, real engagement (after Apple Mail Privacy
            Protection), dormancy, authentication standing, and 3 more.
          </p>
          <p style="font-size:15px;line-height:1.6;color:#334155;">
            It takes about 60 seconds. You can connect an ESP
            (Mailchimp / ActiveCampaign / Mailgun / AWeber) for continuous
            monitoring, or just upload a CSV for a one-shot read.
          </p>
          <p>
            <a href="{BASE_URL}/signal-score"
               style="display:inline-block;background:#16a34a;color:#fff;
                      padding:12px 24px;border-radius:8px;text-decoration:none;
                      font-weight:600;font-size:14px;">
              Get Your Signal Score
            </a>
          </p>
          <p style="font-size:13px;color:#64748b;margin-top:24px;">
            Most senders find at least one signal in the yellow or red on
            their first read. Better to know now than the morning after
            your next campaign.
          </p>
          <hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0;">
          <p style="font-size:12px;color:#94a3b8;">
            You're getting this because you signed up at InbXr.us.
            <a href="{BASE_URL}/account" style="color:#94a3b8;">Manage preferences</a>.
          </p>
        </div>
        """,
    },

    "day_7_first_rule_nudge": {
        "delay_days": 7,
        "subject": "Automate the next fix — Signal Rules",
        "precondition_sql": (
            "SELECT 1 FROM users u WHERE u.id = ? "
            "AND EXISTS (SELECT 1 FROM signal_scores s WHERE s.user_id = u.id) "
            "AND NOT EXISTS (SELECT 1 FROM signal_rules r WHERE r.user_id = u.id)"
        ),
        "html_fn": lambda ctx: f"""
        <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;color:#0c1a3a;">
          <h2 style="margin:0 0 16px;font-size:22px;">One rule is worth a hundred dashboard checks</h2>
          <p style="font-size:15px;line-height:1.6;color:#334155;">
            You got your first Signal Score. Nice. The next-highest leverage
            move is to set up a <strong>Signal Rule</strong> so you never have
            to catch the same problem twice.
          </p>
          <p style="font-size:15px;line-height:1.6;color:#334155;">
            The 3 rules we recommend starting with:
          </p>
          <ul style="font-size:14px;line-height:1.6;color:#334155;">
            <li><strong>Suppress 365+ day dormant contacts</strong> — kills your
                highest-risk spam complaint cohort automatically.</li>
            <li><strong>Alert on bounce rate &gt; 5%</strong> — early warning
                for import problems.</li>
            <li><strong>Tag contacts with likely_mpp_opener</strong> — keeps
                your engagement metrics honest.</li>
          </ul>
          <p style="font-size:14px;line-height:1.6;color:#334155;">
            Every rule defaults to <em>dry-run mode</em> — you preview the
            affected contacts before anything touches live data.
          </p>
          <p>
            <a href="{BASE_URL}/signal-rules"
               style="display:inline-block;background:#16a34a;color:#fff;
                      padding:12px 24px;border-radius:8px;text-decoration:none;
                      font-weight:600;font-size:14px;">
              Set Up Your First Rule
            </a>
          </p>
          <hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0;">
          <p style="font-size:12px;color:#94a3b8;">
            You're getting this because you signed up at InbXr.us.
            <a href="{BASE_URL}/account" style="color:#94a3b8;">Manage preferences</a>.
          </p>
        </div>
        """,
    },

    "day_14_check_in": {
        "delay_days": 14,
        "subject": "Two weeks in — how's your Signal Score?",
        "precondition_sql": (
            "SELECT 1 FROM users u WHERE u.id = ? "
            "AND EXISTS (SELECT 1 FROM signal_scores s WHERE s.user_id = u.id) "
            "AND EXISTS (SELECT 1 FROM signal_rules r WHERE r.user_id = u.id)"
        ),
        "html_fn": lambda ctx: f"""
        <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;color:#0c1a3a;">
          <h2 style="margin:0 0 16px;font-size:22px;">Two weeks of Signal Watch — quick check-in</h2>
          <p style="font-size:15px;line-height:1.6;color:#334155;">
            You've had Signal Watch running for about two weeks now.
            Signal Watch recalculates your 7 signals every 6 hours and fires
            Early Warning alerts when any dimension trends toward danger.
          </p>
          <p style="font-size:15px;line-height:1.6;color:#334155;">
            Two things worth doing today:
          </p>
          <ol style="font-size:14px;line-height:1.6;color:#334155;">
            <li>Check your <a href="{BASE_URL}/signal-score"
                style="color:#16a34a;">Signal Score history chart</a> — the
                trajectory line matters more than the snapshot.</li>
            <li>Open <a href="{BASE_URL}/signal-alerts"
                style="color:#16a34a;">Early Warning alerts</a> and dismiss
                anything you've already handled. A clean inbox is a better
                signal than a fresh score.</li>
          </ol>
          <p style="font-size:14px;line-height:1.6;color:#334155;">
            If anything about InbXr has surprised you, good or bad, just hit
            reply — Joe reads every response personally.
          </p>
          <hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0;">
          <p style="font-size:12px;color:#94a3b8;">
            You're getting this because you signed up at InbXr.us.
            <a href="{BASE_URL}/account" style="color:#94a3b8;">Manage preferences</a>.
          </p>
        </div>
        """,
    },
}


# ── Log helpers ─────────────────────────────────────────

def _already_sent(user_id, email_key):
    row = fetchone(
        "SELECT 1 FROM onboarding_email_log WHERE user_id = ? AND email_key = ?",
        (user_id, email_key),
    )
    return row is not None


def _mark_sent(user_id, email_key, status='sent'):
    try:
        execute(
            """INSERT INTO onboarding_email_log (user_id, email_key, delivery_status)
               VALUES (?, ?, ?)""",
            (user_id, email_key, status),
        )
    except Exception:
        # UNIQUE constraint race — already logged
        pass


# ── Main scheduler entry point ──────────────────────────

def dispatch_onboarding_emails(max_per_run=200):
    """
    Called by the daily scheduler job.
    For each email in the sequence, find users at the right signup-age who
    haven't received that email yet and whose precondition SQL still holds,
    then send.

    Returns a stats dict.
    """
    stats = {
        'sent': 0,
        'skipped_preconditions': 0,
        'skipped_already_sent': 0,
        'errors': 0,
        'by_email': {},
    }

    if not is_configured():
        logger.info("onboarding_emails: mailer not configured, skipping")
        return stats

    total_budget = max_per_run

    for email_key, email_spec in EMAILS.items():
        delay_days = email_spec['delay_days']
        stats['by_email'][email_key] = 0

        # Candidate window: users who signed up between (delay_days) and
        # (delay_days + 1) days ago — so we don't re-hit the same user on
        # consecutive runs if they slipped through somehow
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        window_start = (now - timedelta(days=delay_days + 1)).isoformat()
        window_end = (now - timedelta(days=delay_days)).isoformat()

        candidates = fetchall(
            """SELECT id, email, display_name
               FROM users
               WHERE created_at >= ? AND created_at < ?
               AND status = 'active'
               AND email IS NOT NULL""",
            (window_start, window_end),
        )

        for user in candidates:
            if total_budget <= 0:
                logger.info("onboarding_emails: budget exhausted")
                return stats

            user_id = user['id']

            # Dedup check
            if _already_sent(user_id, email_key):
                stats['skipped_already_sent'] += 1
                continue

            # Precondition check — this is what keeps "nudge" emails from
            # being sent to users who already did the thing we were
            # nudging them toward
            precondition = fetchone(email_spec['precondition_sql'], (user_id,))
            if not precondition:
                stats['skipped_preconditions'] += 1
                continue

            # Render and send
            try:
                ctx = {
                    'user_email': user['email'],
                    'display_name': user.get('display_name') or '',
                }
                html = email_spec['html_fn'](ctx)
                ok = _send(user['email'], email_spec['subject'], html)
                if ok:
                    _mark_sent(user_id, email_key, 'sent')
                    stats['sent'] += 1
                    stats['by_email'][email_key] += 1
                    total_budget -= 1
                else:
                    _mark_sent(user_id, email_key, 'failed')
                    stats['errors'] += 1
            except Exception as e:
                logger.exception(
                    "onboarding_emails: send failed for user %s key %s",
                    user_id, email_key,
                )
                stats['errors'] += 1

    logger.info(
        "onboarding_emails dispatch: %d sent, %d skipped_precond, "
        "%d skipped_sent, %d errors",
        stats['sent'], stats['skipped_preconditions'],
        stats['skipped_already_sent'], stats['errors'],
    )
    return stats
