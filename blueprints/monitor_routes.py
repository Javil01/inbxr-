"""
InbXr — Monitor Blueprint
Routes for per-user domain monitoring, scan triggers, and alerts.
"""

from flask import Blueprint, render_template, request, jsonify, session

from modules.auth import login_required, tier_required, get_current_user
from modules.tiers import get_tier_limit
from modules.monitoring import (
    add_user_monitor, remove_user_monitor, get_user_monitors,
    scan_user_domain, get_monitor_history,
)
from modules.alerts import (
    get_alerts, mark_read, mark_all_read, get_unread_count,
    get_alert_preferences, save_alert_preferences,
)
from modules.tiers import has_feature

monitor_bp = Blueprint("monitors", __name__)


@monitor_bp.route("/monitors")
@login_required
@tier_required("pro", "agency", "api")
def monitors_page():
    """Page showing user's monitored domains."""
    user = get_current_user()
    return render_template(
        "auth/monitors.html",
        active_page="monitors",
        tier_limit=get_tier_limit(user["tier"], "blocklist_domains"),
    )


@monitor_bp.route("/api/monitors", methods=["GET"])
@login_required
@tier_required("pro", "agency", "api")
def list_monitors():
    """JSON list of user's monitors."""
    user = get_current_user()
    team_id = session.get("team_id")
    monitors = get_user_monitors(user["id"], team_id=team_id)
    limit = get_tier_limit(user["tier"], "blocklist_domains")
    return jsonify({"ok": True, "monitors": monitors, "limit": limit, "count": len(monitors)})


@monitor_bp.route("/api/monitors", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def add_monitor():
    """Add a new domain to monitor."""
    user = get_current_user()
    data = request.get_json(force=True) if request.is_json else {}
    domain = (data.get("domain") or "").strip()
    ip = (data.get("ip") or "").strip() or None

    if not domain:
        return jsonify({"ok": False, "error": "Domain is required."}), 400

    team_id = session.get("team_id")
    result = add_user_monitor(user["id"], domain, ip, team_id=team_id)
    if not result["ok"]:
        return jsonify(result), 400
    return jsonify(result), 201


@monitor_bp.route("/api/monitors/<int:monitor_id>", methods=["DELETE"])
@login_required
@tier_required("pro", "agency", "api")
def delete_monitor(monitor_id):
    """Remove a monitor."""
    user = get_current_user()
    team_id = session.get("team_id")
    result = remove_user_monitor(user["id"], monitor_id, team_id=team_id)
    if not result["ok"]:
        return jsonify(result), 404
    return jsonify(result)


@monitor_bp.route("/api/monitors/<int:monitor_id>/scan", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def trigger_scan(monitor_id):
    """Trigger a manual scan for a monitored domain."""
    user = get_current_user()
    team_id = session.get("team_id")
    result = scan_user_domain(user["id"], monitor_id, team_id=team_id)
    if not result["ok"]:
        return jsonify(result), 400
    return jsonify(result)


@monitor_bp.route("/api/monitors/<int:monitor_id>/history", methods=["GET"])
@login_required
@tier_required("pro", "agency", "api")
def monitor_history(monitor_id):
    """Scan history for a monitored domain."""
    user = get_current_user()
    team_id = session.get("team_id")
    limit = request.args.get("limit", 30, type=int)
    history = get_monitor_history(user["id"], monitor_id, limit=limit, team_id=team_id)
    return jsonify({"ok": True, "history": history})


# ── Alerts ────────────────────────────────────────────

@monitor_bp.route("/api/alerts", methods=["GET"])
@login_required
def list_alerts():
    """List alerts for the current user."""
    user = get_current_user()
    unread_only = request.args.get("unread", "").lower() in ("1", "true")
    alerts = get_alerts(user["id"], unread_only=unread_only)
    unread = get_unread_count(user["id"])
    return jsonify({"ok": True, "alerts": alerts, "unread_count": unread})


@monitor_bp.route("/api/alerts/read", methods=["POST"])
@login_required
def read_all_alerts():
    """Mark all alerts as read."""
    user = get_current_user()
    mark_all_read(user["id"])
    return jsonify({"ok": True})


@monitor_bp.route("/api/alerts/<int:alert_id>/read", methods=["POST"])
@login_required
def read_alert(alert_id):
    """Mark a single alert as read."""
    user = get_current_user()
    mark_read(user["id"], alert_id)
    return jsonify({"ok": True})


@monitor_bp.route("/api/alerts/unread-count", methods=["GET"])
@login_required
def unread_count():
    """Get unread alert count (lightweight endpoint for polling)."""
    user = get_current_user()
    count = get_unread_count(user["id"])
    return jsonify({"count": count})


# ── Alert Preferences ─────────────────────────────────

@monitor_bp.route("/api/alerts/preferences", methods=["GET"])
@login_required
def get_preferences():
    """Get alert preferences for the current user."""
    user = get_current_user()
    prefs = get_alert_preferences(user["id"])
    can_email = has_feature(user["tier"], "email_alerts")
    return jsonify({
        "ok": True,
        "preferences": {
            "blocklist_alerts": bool(prefs.get("blocklist_alerts", True)),
            "dns_auth_alerts": bool(prefs.get("dns_auth_alerts", True)),
            "digest_frequency": prefs.get("digest_frequency", "instant"),
            "email_notifications": bool(prefs.get("email_notifications", True)),
        },
        "email_available": can_email,
        "tier": user["tier"],
    })


@monitor_bp.route("/api/alerts/preferences", methods=["POST"])
@login_required
def update_preferences():
    """Update alert preferences."""
    user = get_current_user()
    data = request.get_json(force=True) if request.is_json else {}

    valid_frequencies = ("instant", "daily", "weekly", "off")
    freq = data.get("digest_frequency", "instant")
    if freq not in valid_frequencies:
        return jsonify({"ok": False, "error": "Invalid digest frequency."}), 400

    save_alert_preferences(user["id"], {
        "blocklist_alerts": data.get("blocklist_alerts", True),
        "dns_auth_alerts": data.get("dns_auth_alerts", True),
        "digest_frequency": freq,
        "email_notifications": data.get("email_notifications", True),
    })
    return jsonify({"ok": True})


# ── DNS Auth Check (manual trigger) ────────────────────

@monitor_bp.route("/api/monitors/<int:monitor_id>/dns-check", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def dns_check(monitor_id):
    """Trigger a manual DNS auth check for a monitored domain."""
    from modules.dns_monitor import scan_domain_dns, save_dns_snapshot, get_previous_snapshot, detect_dns_changes
    from modules.database import fetchone as _fo

    user = get_current_user()
    team_id = session.get("team_id")

    if team_id:
        monitor = _fo(
            "SELECT * FROM user_monitors WHERE id = ? AND team_id = ?",
            (monitor_id, team_id),
        )
    else:
        monitor = _fo(
            "SELECT * FROM user_monitors WHERE id = ? AND user_id = ?",
            (monitor_id, user["id"]),
        )

    if not monitor:
        return jsonify({"ok": False, "error": "Monitor not found."}), 404

    prev = get_previous_snapshot(monitor_id)
    result = scan_domain_dns(monitor["domain"])
    save_dns_snapshot(monitor_id, result)
    changes = detect_dns_changes(prev, result)

    return jsonify({
        "ok": True,
        "domain": monitor["domain"],
        "spf": result["spf"],
        "dkim": result["dkim"],
        "dmarc": result["dmarc"],
        "issues": result["issues"],
        "changes": changes,
    })
