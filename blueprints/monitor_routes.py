"""
INBXR — Monitor Blueprint
Routes for per-user domain monitoring, scan triggers, and alerts.
"""

from flask import Blueprint, render_template, request, jsonify, session

from modules.auth import login_required, tier_required, get_current_user
from modules.tiers import get_tier_limit
from modules.monitoring import (
    add_user_monitor, remove_user_monitor, get_user_monitors,
    scan_user_domain, get_monitor_history,
)
from modules.alerts import get_alerts, mark_read, mark_all_read, get_unread_count

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
    monitors = get_user_monitors(user["id"])
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

    result = add_user_monitor(user["id"], domain, ip)
    if not result["ok"]:
        return jsonify(result), 400
    return jsonify(result), 201


@monitor_bp.route("/api/monitors/<int:monitor_id>", methods=["DELETE"])
@login_required
@tier_required("pro", "agency", "api")
def delete_monitor(monitor_id):
    """Remove a monitor."""
    user = get_current_user()
    result = remove_user_monitor(user["id"], monitor_id)
    if not result["ok"]:
        return jsonify(result), 404
    return jsonify(result)


@monitor_bp.route("/api/monitors/<int:monitor_id>/scan", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def trigger_scan(monitor_id):
    """Trigger a manual scan for a monitored domain."""
    user = get_current_user()
    result = scan_user_domain(user["id"], monitor_id)
    if not result["ok"]:
        return jsonify(result), 400
    return jsonify(result)


@monitor_bp.route("/api/monitors/<int:monitor_id>/history", methods=["GET"])
@login_required
@tier_required("pro", "agency", "api")
def monitor_history(monitor_id):
    """Scan history for a monitored domain."""
    user = get_current_user()
    limit = request.args.get("limit", 30, type=int)
    history = get_monitor_history(user["id"], monitor_id, limit=limit)
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
