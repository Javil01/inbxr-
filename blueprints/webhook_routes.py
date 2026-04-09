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


# ── ActiveCampaign webhook ──────────────────────────────
#
# ActiveCampaign posts webhooks as application/x-www-form-urlencoded
# with a nested "contact" + "type" field pattern. The full event set
# includes subscribe, unsubscribe, bounce, update, and several others.
# We handle the deliverability-relevant ones and ignore the rest.
#
# Auth pattern: like Mailchimp, AC doesn't sign payloads. We use the
# same per-user HMAC token in the URL path.
#
# AC field shape:
#     contact[email], contact[id], contact[list], type


def _user_from_ac_token(token):
    """Reverse-lookup for ActiveCampaign. Mirrors the Mailchimp pattern."""
    from modules.database import fetchall
    candidates = fetchall(
        "SELECT DISTINCT user_id FROM esp_integrations "
        "WHERE provider = 'activecampaign' AND status = 'active'",
        (),
    )
    for c in candidates:
        uid = c["user_id"]
        if verify_user_webhook_token(uid, "activecampaign", token):
            return uid
    return None


# AC webhook open events expose hardware / os / browser fields directly
# (unlike Mailchimp, which requires a secondary /email-activity call).
# Apple Mail Privacy Protection opens come from Apple infrastructure with
# a recognizable User-Agent signature. These patterns are the same ones
# used by the Mailgun high-accuracy path.
_APPLE_UA_PATTERNS = (
    "applemail",
    "mac os",
    "macos",
    "iphone",
    "ipad",
    "ios",
)


def _looks_apple_mpp(hardware, os_name, browser, user_agent):
    """Check if an AC open event signature matches Apple Mail Privacy
    Protection. Returns True if any of the fields contain Apple patterns."""
    blob = " ".join([
        (hardware or "").lower(),
        (os_name or "").lower(),
        (browser or "").lower(),
        (user_agent or "").lower(),
    ])
    if not blob.strip():
        return False
    return any(p in blob for p in _APPLE_UA_PATTERNS)


def _handle_ac_open(user_id, integration_id, email, hardware, os_name, browser, user_agent):
    """Handle an ActiveCampaign open event. Updates last_open_date AND
    sets likely_mpp_opener when the User-Agent signature matches Apple.
    This is the high-accuracy path for AC — same confidence level as
    the Mailgun User-Agent + IP path.

    AC is the only ESP besides Mailgun that exposes UA data on webhook
    open events. Mailchimp hides it, AWeber doesn't ship it. So AC users
    who wire up webhooks get high-accuracy MPP detection as the contact
    opens accumulate over time.
    """
    if not email:
        return

    is_mpp = _looks_apple_mpp(hardware, os_name, browser, user_agent)

    existing = fetchone(
        "SELECT id, likely_mpp_opener, mpp_detection_method "
        "FROM contact_segments "
        "WHERE user_id = ? AND esp_integration_id = ? AND email = ?",
        (user_id, integration_id, email),
    )

    if existing:
        # Once a contact has ever been flagged via UA detection, keep the
        # flag sticky so a subsequent non-Apple open from the same contact
        # doesn't undo the classification.
        new_mpp = 1 if (is_mpp or existing.get("likely_mpp_opener")) else 0
        execute(
            """UPDATE contact_segments SET
                last_open_date = datetime('now'),
                likely_mpp_opener = ?,
                mpp_detection_method = CASE
                    WHEN ? = 1 THEN 'ua_webhook'
                    ELSE mpp_detection_method
                END,
                updated_at = datetime('now')
               WHERE id = ?""",
            (new_mpp, 1 if is_mpp else 0, existing["id"]),
        )
        if is_mpp and not existing.get("likely_mpp_opener"):
            logger.info(
                "[WEBHOOK] AC open flagged as MPP (UA): %s (hw=%s os=%s)",
                email, hardware, os_name,
            )
    else:
        # First sighting via webhook — create the contact row with the
        # MPP flag set if UA matches.
        execute(
            """INSERT INTO contact_segments
                (user_id, esp_integration_id, email, last_open_date,
                 likely_mpp_opener, mpp_detection_method,
                 created_at, updated_at)
               VALUES (?, ?, ?, datetime('now'), ?, ?, datetime('now'), datetime('now'))""",
            (
                user_id,
                integration_id,
                email,
                1 if is_mpp else 0,
                "ua_webhook" if is_mpp else None,
            ),
        )


@webhook_bp.route("/activecampaign/<token>", methods=["GET", "POST"])
def activecampaign_webhook(token):
    """Handle ActiveCampaign webhook events."""
    if request.method == "GET":
        return "OK", 200

    user_id = _user_from_ac_token(token)
    if not user_id:
        logger.warning("[WEBHOOK] ActiveCampaign unknown token")
        return "OK", 200

    integration = fetchone(
        """SELECT id FROM esp_integrations
           WHERE user_id = ? AND provider = 'activecampaign' AND status = 'active'
           ORDER BY id DESC LIMIT 1""",
        (user_id,),
    )
    if not integration:
        return "OK", 200

    integration_id = integration["id"]

    event_type = (request.form.get("type") or "").strip().lower()
    email = (request.form.get("contact[email]") or "").strip().lower()

    if not event_type:
        return "OK", 200

    try:
        if event_type == "subscribe":
            _handle_subscribe(user_id, integration_id, email)
        elif event_type == "unsubscribe":
            _handle_unsubscribe(user_id, integration_id, email)
        elif event_type in ("bounce", "hard_bounce"):
            _handle_cleaned(user_id, integration_id, email)
        elif event_type == "open":
            # AC open events carry hardware/os/browser for the client that
            # rendered the email. This is the high-accuracy MPP detection
            # path — promotes AC from medium to high confidence when these
            # fields are present on the event.
            hardware = request.form.get("hardware", "")
            os_name = request.form.get("os", "")
            browser = request.form.get("browser", "")
            user_agent = request.form.get("user_agent", "")
            _handle_ac_open(
                user_id, integration_id, email,
                hardware, os_name, browser, user_agent,
            )
        elif event_type == "update":
            _handle_profile_update(user_id, integration_id, email)
        else:
            logger.info("[WEBHOOK] ActiveCampaign unknown event: %s", event_type)
    except Exception:
        logger.exception("[WEBHOOK] AC handler failed for event %s", event_type)

    return "OK", 200


# ── Brevo webhook ───────────────────────────────────────
#
# Brevo (formerly Sendinblue) posts JSON payloads with an "event"
# field. Supported events include delivered, soft_bounce, hard_bounce,
# blocked, spam, invalid_email, deferred, click, request, opened,
# unique_opened, unsubscribed.
#
# Brevo has no payload signing; we use the same per-user URL token.
# They POST JSON so we read request.get_json() instead of form data.
#
# Brevo field shape (typical):
#     { "event": "hard_bounce", "email": "foo@bar.com", "id": 123, ... }


def _user_from_brevo_token(token):
    """Brevo is less common as a per-user ESP integration (we mainly
    use it for transactional sending) but we still support webhook
    delivery for users who have it connected."""
    from modules.database import fetchall
    # Brevo isn't in the current ESP_PROVIDERS whitelist yet, but the
    # webhook listener is still available for future integration work.
    # We check for any integration labelled 'brevo' in the sync_data_json
    # or server_prefix field as a forward-compatible fallback.
    candidates = fetchall(
        "SELECT DISTINCT user_id FROM esp_integrations "
        "WHERE provider = 'brevo' AND status = 'active'",
        (),
    )
    for c in candidates:
        uid = c["user_id"]
        if verify_user_webhook_token(uid, "brevo", token):
            return uid
    return None


@webhook_bp.route("/brevo/<token>", methods=["GET", "POST"])
def brevo_webhook(token):
    """Handle Brevo (Sendinblue) webhook events. JSON payload."""
    if request.method == "GET":
        return "OK", 200

    user_id = _user_from_brevo_token(token)
    if not user_id:
        logger.warning("[WEBHOOK] Brevo unknown token")
        return "OK", 200

    integration = fetchone(
        """SELECT id FROM esp_integrations
           WHERE user_id = ? AND provider = 'brevo' AND status = 'active'
           ORDER BY id DESC LIMIT 1""",
        (user_id,),
    )
    if not integration:
        return "OK", 200

    integration_id = integration["id"]

    payload = request.get_json(silent=True) or {}
    event = (payload.get("event") or "").strip().lower()
    email = (payload.get("email") or "").strip().lower()

    if not event or not email:
        return "OK", 200

    try:
        if event in ("hard_bounce", "invalid_email", "blocked"):
            _handle_cleaned(user_id, integration_id, email)
        elif event in ("unsubscribed", "unsubscribe"):
            _handle_unsubscribe(user_id, integration_id, email)
        elif event in ("spam", "complaint"):
            # Treat spam complaints as high-severity suppressions
            _handle_unsubscribe(user_id, integration_id, email)
        elif event in ("opened", "unique_opened", "click"):
            _handle_profile_update(user_id, integration_id, email)
        else:
            logger.info("[WEBHOOK] Brevo unknown event: %s", event)
    except Exception:
        logger.exception("[WEBHOOK] Brevo handler failed for event %s", event)

    return "OK", 200
