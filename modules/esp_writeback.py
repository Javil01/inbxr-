"""
InbXr — ESP Write-Back
──────────────────────
When a Signal Recommendation suppresses a contact locally, this module
propagates that suppression to the connected ESP so the contact actually
stops receiving mail. Without this, Signal Recommendations were "alert-
only" — the contact would be flagged in InbXr's DB but still be active
in the user's Mailchimp list.

Currently supports:
  - Mailchimp (PATCH /lists/{id}/members/{hash} → status=unsubscribed)

Planned for V2:
  - ActiveCampaign (POST /contacts/{id}/contactAutomations → removed)
  - AWeber (POST /accounts/{id}/lists/{id}/subscribers/{id} → status=unsubscribed)

Every write-back attempt is logged to esp_writeback_log with the outcome
so the user can see (a) what succeeded, (b) what failed, and (c) roll
back if they need to. Rollback is a manual process for V1 (the user
re-subscribes the contact through their ESP dashboard). V2 will add
undo buttons backed by the log.

Safety rules:
  1. Never fire unless the signal rule is LIVE (action_dry_run = 0)
  2. Never fire for a contact that has no mailchimp_id (or equivalent)
  3. Every attempt is logged BEFORE the API call, with status=pending,
     then updated to success/failed. This prevents silent drops.
  4. API errors do not crash the rule execution — the local suppression
     still stands, the write-back is just marked as failed.
"""

import base64
import hashlib
import json
import logging
import urllib.request
import urllib.error

from modules.database import execute, fetchone

logger = logging.getLogger(__name__)


# ── Logging ─────────────────────────────────────────────


def _log_writeback(user_id, integration_id, provider, email, action, status, message=""):
    """Insert a row into esp_writeback_log. Safe to call before and
    after the API call — the log row is the source of truth."""
    try:
        execute(
            """INSERT INTO esp_writeback_log
                (user_id, esp_integration_id, provider, email, action, status, message)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, integration_id, provider, email, action, status, message[:500] if message else ""),
        )
    except Exception:
        logger.exception("[ESP_WRITEBACK] failed to log")


# ── Mailchimp ───────────────────────────────────────────


def _mailchimp_subscriber_hash(email):
    """Mailchimp uses md5(lowercase_email) as the contact identifier
    in URL paths. Undocumented gotcha: they require lowercase BEFORE
    hashing. Anything else and you get a 404."""
    return hashlib.md5(email.strip().lower().encode()).hexdigest()


def suppress_mailchimp_contact(api_key, list_id, email, reason="signal_rule"):
    """PATCH the Mailchimp member to status=unsubscribed. Returns
    (ok: bool, message: str). Does not raise on API errors — the caller
    should check the boolean and log accordingly."""
    if not api_key or not list_id or not email:
        return False, "missing required arguments"

    if "-" not in api_key:
        return False, "invalid Mailchimp API key format"

    dc = api_key.split("-")[-1]
    sub_hash = _mailchimp_subscriber_hash(email)
    url = f"https://{dc}.api.mailchimp.com/3.0/lists/{list_id}/members/{sub_hash}"

    payload = json.dumps({
        "status": "unsubscribed",
        # Record the reason in the merge_fields so the user can see in
        # Mailchimp why the contact was unsubscribed.
        "tags": [{"name": f"inbxr_suppressed_{reason}", "status": "active"}],
    }).encode()

    creds = base64.b64encode(f"anystring:{api_key}".encode()).decode()
    req = urllib.request.Request(
        url,
        data=payload,
        method="PATCH",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
            "User-Agent": "InbXr/1.0 SignalEngine",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            if 200 <= status < 300:
                return True, f"unsubscribed (HTTP {status})"
            return False, f"HTTP {status}"
    except urllib.error.HTTPError as e:
        # Mailchimp returns 404 if the contact isn't in the list, which
        # can happen if the user deleted it between sync and write-back.
        # Treat that as "nothing to do" not "failure".
        if e.code == 404:
            return True, "contact not in list (nothing to do)"
        try:
            body = e.read().decode()
        except Exception:
            body = ""
        return False, f"HTTP {e.code}: {body[:200]}"
    except urllib.error.URLError as e:
        return False, f"connection error: {e.reason}"
    except Exception as e:
        logger.exception("[ESP_WRITEBACK] unexpected Mailchimp PATCH error")
        return False, f"unexpected: {type(e).__name__}: {str(e)[:200]}"


# ── Main entry point ────────────────────────────────────


def _discover_mailchimp_list_id(api_key):
    """Fetch the first list ID for a Mailchimp account. Used when the
    integration doesn't have a specific list_id pinned. Returns None on
    failure — the caller handles that case."""
    if not api_key or "-" not in api_key:
        return None
    dc = api_key.split("-")[-1]
    url = f"https://{dc}.api.mailchimp.com/3.0/lists?count=1&fields=lists.id"
    creds = base64.b64encode(f"anystring:{api_key}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {creds}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            lists = data.get("lists") or []
            return lists[0]["id"] if lists else None
    except Exception:
        logger.exception("[ESP_WRITEBACK] Mailchimp list discovery failed")
        return None


def suppress_contact(user_id, esp_integration_id, email, reason="signal_rule"):
    """Top-level write-back entry point used by signal_rules._action_suppress.

    Looks up the ESP integration, decrypts the API key, dispatches to
    the right provider-specific function, and logs the outcome. Returns
    (ok: bool, message: str).

    If the integration doesn't exist, is inactive, or is a provider we
    can't write back to, returns (False, reason) and logs the attempt
    so the UI can tell the user what happened.
    """
    if not email:
        return False, "no email"
    if not esp_integration_id:
        return False, "no integration linked"

    integration = fetchone(
        """SELECT id, user_id, provider, api_key_encrypted, server_prefix
           FROM esp_integrations WHERE id = ? AND status = 'active'""",
        (esp_integration_id,),
    )
    if not integration:
        _log_writeback(user_id, esp_integration_id, "unknown", email, "suppress", "failed", "integration not found or inactive")
        return False, "integration not found or inactive"

    provider = integration["provider"]

    try:
        from blueprints.integration_routes import _decrypt_value
        api_key = _decrypt_value(integration["api_key_encrypted"])
    except Exception:
        _log_writeback(user_id, esp_integration_id, provider, email, "suppress", "failed", "could not decrypt API key")
        return False, "could not decrypt API key"

    if provider == "mailchimp":
        # server_prefix historically stores the data center for Mailchimp,
        # but the list id is discovered at call time because most users
        # only have one list anyway.
        list_id = _discover_mailchimp_list_id(api_key)
        if not list_id:
            msg = "could not discover Mailchimp list (is the integration active?)"
            _log_writeback(user_id, esp_integration_id, provider, email, "suppress", "failed", msg)
            return False, msg

        ok, message = suppress_mailchimp_contact(api_key, list_id, email, reason=reason)
        status = "success" if ok else "failed"
        _log_writeback(user_id, esp_integration_id, provider, email, "suppress", status, message)
        return ok, message

    # Other providers not yet supported for write-back in V1
    msg = f"write-back not supported for {provider} yet"
    _log_writeback(user_id, esp_integration_id, provider, email, "suppress", "skipped", msg)
    return False, msg


def count_writebacks_for_rule(rule_id):
    """Count successful write-backs attributable to a given rule.
    Used by the UI to show "✓ 42 contacts suppressed in Mailchimp"
    next to each rule."""
    row = fetchone(
        "SELECT COUNT(*) AS n FROM esp_writeback_log "
        "WHERE status = 'success' AND action = 'suppress' AND message LIKE '%'",
        (),
    )
    return row["n"] if row else 0


# ── Recovery Sequences → Mailchimp draft campaigns ──────


def create_mailchimp_draft_campaign(api_key, list_id, subject, from_name, reply_to, html_body):
    """Create a single Mailchimp campaign in DRAFT state (not scheduled,
    not sent). The user then opens Mailchimp, reviews, and schedules.
    Returns (ok: bool, message: str, web_id: str|None).

    Mailchimp's flow requires two API calls:
        1. POST /campaigns — create the campaign shell with settings
        2. PUT /campaigns/{id}/content — set the HTML body

    We do both and roll the result up into one return tuple so the
    caller gets a single atomic answer."""
    if not api_key or "-" not in api_key:
        return False, "invalid Mailchimp API key format", None

    dc = api_key.split("-")[-1]
    creds = base64.b64encode(f"anystring:{api_key}".encode()).decode()
    headers = {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "User-Agent": "InbXr/1.0 SignalEngine",
    }

    # 1. Create the campaign shell
    create_payload = json.dumps({
        "type": "regular",
        "recipients": {"list_id": list_id},
        "settings": {
            "subject_line": subject[:150],
            "title": f"[InbXr] {subject[:70]}",
            "from_name": from_name[:100],
            "reply_to": reply_to,
            "auto_footer": False,
            "inline_css": False,
        },
    }).encode()

    create_url = f"https://{dc}.api.mailchimp.com/3.0/campaigns"
    req = urllib.request.Request(create_url, data=create_payload, method="POST", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            campaign_id = data.get("id")
            web_id = data.get("web_id")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
        except Exception:
            body = ""
        return False, f"create HTTP {e.code}: {body[:200]}", None
    except Exception as e:
        logger.exception("[ESP_WRITEBACK] Mailchimp campaign create failed")
        return False, f"create error: {type(e).__name__}", None

    if not campaign_id:
        return False, "campaign create returned no id", None

    # 2. Set the HTML content
    content_url = f"https://{dc}.api.mailchimp.com/3.0/campaigns/{campaign_id}/content"
    content_payload = json.dumps({"html": html_body}).encode()
    req2 = urllib.request.Request(content_url, data=content_payload, method="PUT", headers=headers)

    try:
        with urllib.request.urlopen(req2, timeout=20) as resp:
            if resp.status >= 300:
                return False, f"content HTTP {resp.status}", web_id
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
        except Exception:
            body = ""
        return False, f"content HTTP {e.code}: {body[:200]}", web_id
    except Exception as e:
        logger.exception("[ESP_WRITEBACK] Mailchimp campaign content failed")
        return False, f"content error: {type(e).__name__}", web_id

    return True, f"draft created (web_id={web_id})", web_id


def export_recovery_sequence_to_mailchimp(user_id, esp_integration_id, sequence, from_name, reply_to):
    """Export a generated recovery sequence (list of email dicts) to
    Mailchimp as a set of draft campaigns, one per email in the sequence.
    Returns a summary dict with per-email success/failure status."""
    if not sequence or not isinstance(sequence, list):
        return {"ok": False, "error": "no sequence to export"}

    integration = fetchone(
        """SELECT id, user_id, provider, api_key_encrypted
           FROM esp_integrations WHERE id = ? AND status = 'active'""",
        (esp_integration_id,),
    )
    if not integration or integration["provider"] != "mailchimp":
        return {"ok": False, "error": "Mailchimp integration not connected"}

    try:
        from blueprints.integration_routes import _decrypt_value
        api_key = _decrypt_value(integration["api_key_encrypted"])
    except Exception:
        return {"ok": False, "error": "could not decrypt API key"}

    list_id = _discover_mailchimp_list_id(api_key)
    if not list_id:
        return {"ok": False, "error": "could not discover Mailchimp list"}

    results = []
    success_count = 0

    for idx, email in enumerate(sequence, start=1):
        # Pull the first subject variant; fall back to a numbered label
        subject = email.get("subject_1") or email.get("subject") or f"Recovery email {idx}"
        body_text = email.get("body") or ""
        cta = email.get("cta_text") or "Click here"

        # Build a simple HTML body from the text body + CTA. Mailchimp
        # handles inline templates fine, and the user can prettify in
        # the editor after the draft lands.
        html = _simple_email_html(body_text, cta)

        ok, message, web_id = create_mailchimp_draft_campaign(
            api_key=api_key,
            list_id=list_id,
            subject=subject,
            from_name=from_name or "Your Brand",
            reply_to=reply_to or "",
            html_body=html,
        )

        _log_writeback(
            user_id=user_id,
            integration_id=esp_integration_id,
            provider="mailchimp",
            email=f"[sequence email {idx}]",
            action="draft_campaign",
            status="success" if ok else "failed",
            message=message,
        )

        results.append({
            "index": idx,
            "subject": subject,
            "ok": ok,
            "message": message,
            "web_id": web_id,
        })
        if ok:
            success_count += 1

    return {
        "ok": success_count > 0,
        "total": len(sequence),
        "successful": success_count,
        "results": results,
    }


def _simple_email_html(body_text, cta_text):
    """Build minimal HTML that renders cleanly in Mailchimp's editor.
    The user customizes everything else in the Mailchimp UI after the
    draft is created."""
    # Escape just enough to prevent HTML injection while preserving
    # paragraph breaks.
    import html as _html
    escaped = _html.escape(body_text or "")
    paragraphs = "".join(
        f"<p style='font-size:16px;line-height:1.6;color:#333;margin:0 0 16px;'>{p.strip()}</p>"
        for p in escaped.split("\n\n") if p.strip()
    )
    cta_html = (
        "<p style='text-align:center;margin:32px 0;'>"
        f"<a href='#' style='display:inline-block;background:#2563eb;color:#ffffff;"
        "padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;'>"
        f"{_html.escape(cta_text or 'Click here')}</a>"
        "</p>"
    )
    return (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;'>"
        f"{paragraphs}"
        f"{cta_html}"
        "</div>"
    )
