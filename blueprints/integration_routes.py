"""
InbXr — ESP Integration Blueprint
Routes for connecting, managing, and testing external email platform integrations.
"""

import os
import json
import hashlib
import base64
import logging
import secrets
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, current_app

from modules.auth import login_required, tier_required, get_current_user
from modules.database import execute, fetchone, fetchall
from modules.tiers import get_tier_limit, has_feature

logger = logging.getLogger("inbxr.integrations")

integration_bp = Blueprint("integrations", __name__)

# ── Provider metadata ────────────────────────────────────

ESP_PROVIDERS = {
    "mailchimp": {
        "name": "Mailchimp",
        "description": "Campaign analytics, ISP-level delivery stats, bounce tracking",
        "auth_type": "api_key",
        "fields": [
            {"key": "api_key", "label": "API Key", "placeholder": "xxxxxxxxxxxxxxxx-us21", "help": "Found in Account > Extras > API Keys"},
        ],
        "docs_url": "https://mailchimp.com/developer/marketing/guides/quick-start/",
        "icon": "mailchimp",
        "data_points": ["Opens", "Clicks", "Bounces", "Complaints", "ISP stats"],
    },
    "activecampaign": {
        "name": "ActiveCampaign",
        "description": "Bounce & complaint tracking, per-contact activity, engagement scores",
        "auth_type": "api_key",
        "fields": [
            {"key": "api_key", "label": "API Key", "placeholder": "Your API key", "help": "Found in Settings > Developer"},
            {"key": "server_prefix", "label": "Account URL", "placeholder": "yourname.api-us1.com", "help": "Your ActiveCampaign account URL"},
        ],
        "docs_url": "https://developers.activecampaign.com/",
        "icon": "activecampaign",
        "data_points": ["Opens", "Clicks", "Bounces", "Complaints", "Engagement"],
    },
    "mailgun": {
        "name": "Mailgun",
        "description": "SMTP bounce codes, domain DNS verification, suppression lists",
        "auth_type": "api_key",
        "fields": [
            {"key": "api_key", "label": "API Key", "placeholder": "key-xxxxxxxxxxxxxxxx", "help": "Found in API Security settings"},
            {"key": "server_prefix", "label": "Domain", "placeholder": "mg.yourdomain.com", "help": "Your verified sending domain"},
        ],
        "docs_url": "https://documentation.mailgun.com/",
        "icon": "mailgun",
        "data_points": ["Deliveries", "Bounces", "Complaints", "DNS status", "Suppressions"],
    },
    # GoHighLevel, Instantly, Smartlead — REMOVED from V1 ESP list.
    # Reason: these are cold email platforms that do not expose per-contact
    # engagement data. The 7 Signal engine cannot run honestly against them.
    # Users of these tools get directed to the CSV upload path instead.
    # The _test_* functions below remain in the file for reference.
    "aweber": {
        "name": "AWeber",
        "description": "Subscriber activity, open/click/bounce tracking",
        "auth_type": "api_key",
        "fields": [
            {"key": "api_key", "label": "API Token", "placeholder": "Your AWeber access token", "help": "Generate a personal access token in your developer account"},
        ],
        "docs_url": "https://api.aweber.com/",
        "icon": "aweber",
        "data_points": ["Opens", "Clicks", "Bounces", "Unsubscribes"],
    },
}


# ── Encryption helpers ───────────────────────────────────

def _get_encryption_key():
    """Derive a 32-byte key from Flask SECRET_KEY for credential encryption."""
    secret = current_app.config.get("SECRET_KEY", "fallback-dev-key")
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), b"inbxr-esp-creds", 100000)


def _encrypt_value(plaintext):
    """Encrypt a string using XOR with derived key + random nonce. Returns base64 string."""
    key = _get_encryption_key()
    nonce = secrets.token_bytes(16)
    data = plaintext.encode("utf-8")
    # XOR encrypt with key stream derived from key + nonce
    key_stream = hashlib.pbkdf2_hmac("sha256", key, nonce, 1, dklen=len(data))
    encrypted = bytes(a ^ b for a, b in zip(data, key_stream))
    return base64.b64encode(nonce + encrypted).decode("ascii")


def _decrypt_value(encrypted_b64):
    """Decrypt a value encrypted by _encrypt_value."""
    key = _get_encryption_key()
    raw = base64.b64decode(encrypted_b64)
    nonce = raw[:16]
    encrypted = raw[16:]
    key_stream = hashlib.pbkdf2_hmac("sha256", key, nonce, 1, dklen=len(encrypted))
    decrypted = bytes(a ^ b for a, b in zip(encrypted, key_stream))
    return decrypted.decode("utf-8")


# ── Routes ───────────────────────────────────────────────

@integration_bp.route("/account/integrations")
@login_required
@tier_required("pro", "agency", "api")
def integrations_page():
    """Page showing connected ESP integrations."""
    user = get_current_user()
    limit = get_tier_limit(user["tier"], "esp_integrations")
    # Build the user's per-provider webhook URLs so the UI can show them
    # in the Mailchimp "connect" flow.
    from blueprints.webhook_routes import make_user_webhook_token
    mailchimp_token = make_user_webhook_token(user["id"], "mailchimp")
    mailchimp_webhook_url = f"https://inbxr.us/webhooks/mailchimp/{mailchimp_token}"
    return render_template(
        "auth/integrations.html",
        active_page="integrations",
        providers=ESP_PROVIDERS,
        tier_limit=limit,
        mailchimp_webhook_url=mailchimp_webhook_url,
    )


@integration_bp.route("/api/integrations", methods=["GET"])
@login_required
@tier_required("pro", "agency", "api")
def list_integrations():
    """JSON list of user's ESP integrations."""
    user = get_current_user()
    rows = fetchall(
        "SELECT id, provider, label, status, status_message, last_synced_at, created_at "
        "FROM esp_integrations WHERE user_id = ? ORDER BY created_at",
        (user["id"],),
    )
    limit = get_tier_limit(user["tier"], "esp_integrations")
    return jsonify({"ok": True, "integrations": rows, "limit": limit, "count": len(rows)})


@integration_bp.route("/api/integrations", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def add_integration():
    """Connect a new ESP integration."""
    user = get_current_user()
    data = request.get_json(force=True) if request.is_json else {}

    provider = (data.get("provider") or "").strip().lower()
    api_key = (data.get("api_key") or "").strip()
    server_prefix = (data.get("server_prefix") or "").strip()
    label = (data.get("label") or "").strip()

    if provider not in ESP_PROVIDERS:
        return jsonify({"ok": False, "error": "Unknown provider."}), 400
    if not api_key:
        return jsonify({"ok": False, "error": "API key is required."}), 400

    # Check tier limit
    limit = get_tier_limit(user["tier"], "esp_integrations")
    current_count = fetchone(
        "SELECT COUNT(*) as cnt FROM esp_integrations WHERE user_id = ?",
        (user["id"],),
    )["cnt"]
    if current_count >= limit:
        return jsonify({"ok": False, "error": f"Integration limit reached ({limit}). Upgrade for more."}), 403

    # Check for duplicate
    existing = fetchone(
        "SELECT id FROM esp_integrations WHERE user_id = ? AND provider = ? AND label = ?",
        (user["id"], provider, label),
    )
    if existing:
        return jsonify({"ok": False, "error": f"{ESP_PROVIDERS[provider]['name']} is already connected."}), 409

    # Encrypt and store
    encrypted_key = _encrypt_value(api_key)

    execute(
        """INSERT INTO esp_integrations
           (user_id, provider, label, api_key_encrypted, server_prefix, status)
           VALUES (?, ?, ?, ?, ?, 'pending')""",
        (user["id"], provider, label, encrypted_key, server_prefix),
    )

    row = fetchone(
        "SELECT id, provider, label, status, created_at FROM esp_integrations "
        "WHERE user_id = ? AND provider = ? AND label = ?",
        (user["id"], provider, label),
    )

    logger.info("User %s connected %s integration", user["id"], provider)
    return jsonify({"ok": True, "integration": row})


@integration_bp.route("/api/integrations/<int:integration_id>/test", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def test_integration(integration_id):
    """Test an ESP integration by making a simple API call."""
    user = get_current_user()
    row = fetchone(
        "SELECT * FROM esp_integrations WHERE id = ? AND user_id = ?",
        (integration_id, user["id"]),
    )
    if not row:
        return jsonify({"ok": False, "error": "Integration not found."}), 404

    provider = row["provider"]
    api_key = _decrypt_value(row["api_key_encrypted"])
    server_prefix = row.get("server_prefix") or ""

    ok, message = _test_provider_connection(provider, api_key, server_prefix)

    new_status = "active" if ok else "error"
    execute(
        "UPDATE esp_integrations SET status = ?, status_message = ?, updated_at = datetime('now') WHERE id = ?",
        (new_status, message, integration_id),
    )

    return jsonify({"ok": ok, "status": new_status, "message": message})


@integration_bp.route("/api/integrations/<int:integration_id>", methods=["DELETE"])
@login_required
@tier_required("pro", "agency", "api")
def delete_integration(integration_id):
    """Disconnect an ESP integration."""
    user = get_current_user()
    row = fetchone(
        "SELECT id FROM esp_integrations WHERE id = ? AND user_id = ?",
        (integration_id, user["id"]),
    )
    if not row:
        return jsonify({"ok": False, "error": "Integration not found."}), 404

    execute("DELETE FROM esp_integrations WHERE id = ?", (integration_id,))
    logger.info("User %s disconnected integration %s", user["id"], integration_id)
    return jsonify({"ok": True})


@integration_bp.route("/api/integrations/<int:integration_id>/sync", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def sync_one_integration(integration_id):
    """Trigger a manual sync for an integration."""
    from modules.esp_sync import sync_integration as do_sync

    user = get_current_user()
    row = fetchone(
        "SELECT id FROM esp_integrations WHERE id = ? AND user_id = ?",
        (integration_id, user["id"]),
    )
    if not row:
        return jsonify({"ok": False, "error": "Integration not found."}), 404

    data = do_sync(integration_id)
    if data:
        return jsonify({"ok": True, "data": data})
    return jsonify({"ok": False, "error": "Sync failed. Check your API credentials."}), 500


@integration_bp.route("/api/integrations/sync-all", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def sync_all_integrations():
    """Trigger a manual sync for all user integrations."""
    from modules.esp_sync import sync_all_for_user

    user = get_current_user()
    results = sync_all_for_user(user["id"])
    synced = sum(1 for r in results if r["data"])
    return jsonify({"ok": True, "synced": synced, "total": len(results)})


@integration_bp.route("/api/integrations/<int:integration_id>/history", methods=["GET"])
@login_required
@tier_required("pro", "agency", "api")
def get_sync_history_route(integration_id):
    """Get sync snapshot history for trend charts."""
    from modules.esp_sync import get_sync_history

    user = get_current_user()
    row = fetchone(
        "SELECT id FROM esp_integrations WHERE id = ? AND user_id = ?",
        (integration_id, user["id"]),
    )
    if not row:
        return jsonify({"ok": False, "error": "Integration not found."}), 404

    history = get_sync_history(integration_id)
    return jsonify({"ok": True, "history": history})


@integration_bp.route("/api/integrations/health", methods=["GET"])
@login_required
@tier_required("pro", "agency", "api")
def get_health_summary():
    """Get aggregated health summary across all integrations."""
    from modules.esp_sync import get_user_health_summary

    user = get_current_user()
    summary = get_user_health_summary(user["id"])
    return jsonify({"ok": True, **summary})


@integration_bp.route("/deliverability")
@login_required
@tier_required("pro", "agency", "api")
def deliverability_dashboard():
    """
    Legacy /deliverability URL — permanently redirects to /signal-score.
    The Signal Score Dashboard is now the single consolidated home for
    deliverability intelligence (primary) + aggregate ESP health (supporting).

    Preserves bookmarks, sidebar links, and SEO authority via 301.
    """
    from flask import redirect, url_for
    return redirect(url_for("signal.signal_score_dashboard"), code=301)


@integration_bp.route("/api/integrations/providers", methods=["GET"])
def list_providers():
    """Public endpoint listing available ESP providers and their metadata."""
    providers = {}
    for key, meta in ESP_PROVIDERS.items():
        providers[key] = {
            "name": meta["name"],
            "description": meta["description"],
            "auth_type": meta["auth_type"],
            "fields": meta["fields"],
            "data_points": meta["data_points"],
            "icon": meta["icon"],
        }
    return jsonify({"ok": True, "providers": providers})


# ── Provider test functions ──────────────────────────────

def _test_provider_connection(provider, api_key, server_prefix=""):
    """Test connection to an ESP. Returns (ok, message)."""
    import urllib.request
    import urllib.error

    try:
        if provider == "mailchimp":
            return _test_mailchimp(api_key)
        elif provider == "activecampaign":
            return _test_activecampaign(api_key, server_prefix)
        elif provider == "mailgun":
            return _test_mailgun(api_key, server_prefix)
        elif provider == "gohighlevel":
            return _test_gohighlevel(api_key)
        elif provider == "instantly":
            return _test_instantly(api_key)
        elif provider == "smartlead":
            return _test_smartlead(api_key)
        elif provider == "aweber":
            return _test_aweber(api_key)
        else:
            return False, "Provider not supported yet."
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Invalid API key. Check your credentials."
        elif e.code == 403:
            return False, "Access denied. Check API key permissions."
        return False, f"HTTP error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Connection failed: {e.reason}"
    except Exception as e:
        logger.exception("Integration test failed for %s", provider)
        return False, f"Connection error: {str(e)}"


def _api_request(url, headers=None, timeout=10):
    """Make a GET request and return parsed JSON."""
    import urllib.request
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _test_mailchimp(api_key):
    """Test Mailchimp API key by fetching account info."""
    # Mailchimp keys end with -usXX datacenter suffix
    if "-" not in api_key:
        return False, "Invalid key format. Mailchimp keys end with -usXX (e.g. abc123-us21)."
    dc = api_key.split("-")[-1]
    creds = base64.b64encode(f"anystring:{api_key}".encode()).decode()
    data = _api_request(
        f"https://{dc}.api.mailchimp.com/3.0/",
        headers={"Authorization": f"Basic {creds}"},
    )
    name = data.get("account_name", "Unknown")
    return True, f"Connected to account: {name}"


def _test_activecampaign(api_key, server_url):
    """Test ActiveCampaign API key."""
    if not server_url:
        return False, "Account URL is required."
    base = server_url.rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"
    data = _api_request(
        f"{base}/api/3/users/me",
        headers={"Api-Token": api_key},
    )
    user = data.get("user", {})
    name = user.get("firstName", "Unknown")
    return True, f"Connected as: {name}"


def _test_mailgun(api_key, domain):
    """Test Mailgun API key by fetching domain info."""
    if not domain:
        return False, "Sending domain is required."
    creds = base64.b64encode(f"api:{api_key}".encode()).decode()
    data = _api_request(
        f"https://api.mailgun.net/v3/domains/{domain}",
        headers={"Authorization": f"Basic {creds}"},
    )
    state = data.get("domain", {}).get("state", "unknown")
    return True, f"Domain {domain} is {state}"


def _test_gohighlevel(api_key):
    """Test GoHighLevel API key."""
    data = _api_request(
        "https://rest.gohighlevel.com/v1/custom-values/",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return True, "Connected to GoHighLevel"


def _test_instantly(api_key):
    """Test Instantly API key by fetching account list."""
    data = _api_request(
        f"https://api.instantly.ai/api/v1/account/list?api_key={api_key}&limit=1",
    )
    count = len(data) if isinstance(data, list) else 0
    return True, f"Connected ({count} sending account{'s' if count != 1 else ''})"


def _test_smartlead(api_key):
    """Test Smartlead API key."""
    data = _api_request(
        f"https://server.smartlead.ai/api/v1/campaigns?api_key={api_key}&limit=1",
    )
    return True, "Connected to Smartlead"


def _test_aweber(api_key):
    """Test AWeber access token."""
    data = _api_request(
        "https://api.aweber.com/1.0/accounts",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    entries = data.get("entries", [])
    if entries:
        return True, f"Connected to account: {entries[0].get('id', 'Unknown')}"
    return True, "Connected to AWeber"
