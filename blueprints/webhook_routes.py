"""
InbXr — Webhook Listeners
─────────────────────────
Real-time event listeners from connected ESPs. These fill the gaps
between the 6-hour polling cycles run by the Signal Watch scheduler
job, so bounces, unsubscribes, and spam complaints are reflected in
the Signal Engine within seconds rather than hours.

Currently supports:

    Mailchimp  GET/POST /webhooks/mailchimp/<user_token>

Mailchimp webhook peculiarities to be aware of:
  1. Mailchimp POSTs webhook events as application/x-www-form-urlencoded
     (not JSON). Fields are flat with prefixes like data[email],
     data[list_id], etc. We parse them via request.form, not .get_json().
  2. Mailchimp requires a GET verification before it will save your
     webhook URL in their dashboard. The GET just needs to return 200.
  3. Mailchimp does not sign requests — authentication is entirely
     via obscurity of the URL. We use a per-user token derived from
     the user_id + the app SECRET_KEY so URLs are stable, unguessable,
     and revocable (by rotating SECRET_KEY or rebuilding the token).
  4. Events we care about:
        - cleaned:     hard bounce → mark contact is_hard_bounce
        - unsubscribe: user clicked unsubscribe → mark suppressed
        - profile:     member update → refresh last_changed timestamp

Future providers (AC, Brevo, Mailgun) get added to this file as
separate routes with their own verification patterns.
"""

import hashlib
import hmac
import logging
import os

from flask import Blueprint, request, jsonify

from modules.database import fetchone, execute

logger = logging.getLogger("inbxr.webhooks")

webhook_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


# ── Token helpers ───────────────────────────────────────


def _webhook_secret_base():
    """App-level salt for all webhook tokens. Derived from SECRET_KEY
    so rotating SECRET_KEY invalidates all existing webhook URLs."""
    return os.environ.get("SECRET_KEY", "fallback-dev-key").encode()


def make_user_webhook_token(user_id, provider):
    """Deterministic, unguessable token for a user's webhook URL.
    Same inputs always produce the same token so existing Mailchimp
    webhook configurations keep working across restarts."""
    base = _webhook_secret_base()
    msg = f"webhook:{provider}:{user_id}".encode()
    return hmac.new(base, msg, hashlib.sha256).hexdigest()[:24]


def verify_user_webhook_token(user_id, provider, token):
    """Constant-time comparison to prevent timing attacks."""
    expected = make_user_webhook_token(user_id, provider)
    return hmac.compare_digest(expected, (token or "").strip())


def _user_from_mailchimp_token(token):
    """Reverse-lookup the user from a webhook token. We iterate over
    active Mailchimp integrations and find the one whose computed token
    matches. This is O(n) over active users, which is fine for V1.
    For V2 we can add a token column indexed directly."""
    rows = fetchone(
        "SELECT COUNT(*) AS n FROM esp_integrations "
        "WHERE provider = 'mailchimp' AND status = 'active'",
        (),
    )
    if not rows or not rows["n"]:
        return None

    # Fetch candidate users
    from modules.database import fetchall
    candidates = fetchall(
        "SELECT DISTINCT user_id FROM esp_integrations "
        "WHERE provider = 'mailchimp' AND status = 'active'",
        (),
    )
    for c in candidates:
        uid = c["user_id"]
        if verify_user_webhook_token(uid, "mailchimp", token):
            return uid
    return None


# ── Mailchimp webhook ───────────────────────────────────


@webhook_bp.route("/mailchimp/<token>", methods=["GET", "POST"])
def mailchimp_webhook(token):
    """Handle Mailchimp webhook events.

    GET: Used by Mailchimp during webhook URL verification. Must return
    200 OK. We don't require the user_id to match on GET because
    Mailchimp's verification pings an empty request.

    POST: Event delivery. Parse the form-encoded body, identify the
    event type, route to the right handler. Always returns 200 unless
    there's a genuine error — returning non-200 causes Mailchimp to
    retry aggressively which we don't want.
    """
    # GET verification
    if request.method == "GET":
        return "OK", 200

    # Identify the user from the token
    user_id = _user_from_mailchimp_token(token)
    if not user_id:
        logger.warning("[WEBHOOK] Mailchimp unknown token attempt")
        # Still return 200 to prevent token probing — Mailchimp won't
        # retry on 200 but will retry aggressively on 4xx/5xx.
        return "OK", 200

    # Find the Mailchimp integration for this user
    integration = fetchone(
        """SELECT id FROM esp_integrations
           WHERE user_id = ? AND provider = 'mailchimp' AND status = 'active'
           ORDER BY id DESC LIMIT 1""",
        (user_id,),
    )
    if not integration:
        logger.warning("[WEBHOOK] Mailchimp event for user %s but no active integration", user_id)
        return "OK", 200

    integration_id = integration["id"]

    # Parse event type and data. Mailchimp uses flat form encoding
    # like type=unsubscribe&data[email]=foo@bar.com&data[list_id]=xxx
    event_type = request.form.get("type", "").strip()
    email = request.form.get("data[email]", "").strip().lower()
    list_id = request.form.get("data[list_id]", "").strip()

    if not event_type:
        return "OK", 200

    try:
        if event_type == "cleaned":
            _handle_cleaned(user_id, integration_id, email)
        elif event_type == "unsubscribe":
            _handle_unsubscribe(user_id, integration_id, email)
        elif event_type == "upemail":
            old_email = request.form.get("data[old_email]", "").strip().lower()
            new_email = request.form.get("data[new_email]", "").strip().lower()
            _handle_email_change(user_id, integration_id, old_email, new_email)
        elif event_type == "profile":
            # Member update — refresh last_changed timestamp
            _handle_profile_update(user_id, integration_id, email)
        elif event_type == "subscribe":
            _handle_subscribe(user_id, integration_id, email)
        else:
            logger.info("[WEBHOOK] Mailchimp unknown event type: %s", event_type)
    except Exception:
        logger.exception("[WEBHOOK] Mailchimp handler failed for event %s", event_type)

    return "OK", 200


# ── Event handlers ──────────────────────────────────────


def _handle_cleaned(user_id, integration_id, email):
    """Mark the contact as hard-bounced. Cleaned = the address is no
    longer valid per Mailchimp's determination, which is the equivalent
    of a hard bounce from the Signal Engine's perspective."""
    if not email:
        return
    execute(
        """UPDATE contact_segments SET
            is_hard_bounce = 1,
            updated_at = datetime('now')
           WHERE user_id = ? AND esp_integration_id = ? AND email = ?""",
        (user_id, integration_id, email),
    )
    logger.info("[WEBHOOK] Mailchimp cleaned: %s", email)


def _handle_unsubscribe(user_id, integration_id, email):
    """Mark the contact as suppressed (user-initiated unsubscribe,
    not InbXr-initiated). We still record it so Signal Recommendations
    don't try to suppress them again."""
    if not email:
        return
    execute(
        """UPDATE contact_segments SET
            is_suppressed = 1,
            suppressed_at = datetime('now'),
            suppression_reason = 'user_unsubscribe',
            updated_at = datetime('now')
           WHERE user_id = ? AND esp_integration_id = ? AND email = ?""",
        (user_id, integration_id, email),
    )
    logger.info("[WEBHOOK] Mailchimp unsubscribe: %s", email)


def _handle_email_change(user_id, integration_id, old_email, new_email):
    """User updated their email in Mailchimp. Move the row to the new
    address so future events map correctly."""
    if not old_email or not new_email:
        return
    execute(
        """UPDATE contact_segments SET
            email = ?,
            updated_at = datetime('now')
           WHERE user_id = ? AND esp_integration_id = ? AND email = ?""",
        (new_email, user_id, integration_id, old_email),
    )
    logger.info("[WEBHOOK] Mailchimp email change: %s → %s", old_email, new_email)


def _handle_profile_update(user_id, integration_id, email):
    """Profile update triggers a refresh of the contact's last_changed
    timestamp. This is a weak signal but it tells us the user is still
    interacting with their list."""
    if not email:
        return
    execute(
        """UPDATE contact_segments SET
            updated_at = datetime('now')
           WHERE user_id = ? AND esp_integration_id = ? AND email = ?""",
        (user_id, integration_id, email),
    )


def _handle_subscribe(user_id, integration_id, email):
    """New subscriber. Insert a row so the Signal Engine can see them
    from their very first moment. Acquisition_date is now."""
    if not email:
        return
    existing = fetchone(
        "SELECT id FROM contact_segments WHERE user_id = ? AND esp_integration_id = ? AND email = ?",
        (user_id, integration_id, email),
    )
    if existing:
        # Re-subscribe: clear suppression and refresh timestamps
        execute(
            """UPDATE contact_segments SET
                is_suppressed = 0,
                suppressed_at = NULL,
                suppression_reason = NULL,
                updated_at = datetime('now')
               WHERE id = ?""",
            (existing["id"],),
        )
    else:
        execute(
            """INSERT INTO contact_segments
                (user_id, esp_integration_id, email, acquisition_date, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), datetime('now'), datetime('now'))""",
            (user_id, integration_id, email),
        )
    logger.info("[WEBHOOK] Mailchimp subscribe: %s", email)
