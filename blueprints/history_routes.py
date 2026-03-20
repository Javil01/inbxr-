"""
INBXR — History Blueprint
Routes for viewing and managing saved check results.
"""

from flask import Blueprint, render_template, request, jsonify, session

from modules.auth import login_required
from modules.tiers import has_feature
from modules.history import (get_history, get_result, get_last_scan, delete_result,
                             get_history_stats, get_tool_breakdown, get_score_trend)

history_bp = Blueprint("history", __name__)


def _require_cloud_history():
    """Check if current user has cloud_history feature. Returns error tuple or None."""
    tier = session.get("user_tier", "free")
    if not has_feature(tier, "cloud_history"):
        if request.is_json or request.path.startswith("/api/"):
            return jsonify({
                "error": "Cloud History requires a Pro plan or higher.",
                "upgrade_url": "/pricing",
            }), 403
        from flask import redirect
        return redirect("/pricing?upgrade=1")
    return None


@history_bp.route("/api/dashboard/last-scan")
@login_required
def api_last_scan():
    """Return the most recent check_history entry for the logged-in user.
    Available to ALL tiers (not gated by cloud_history).
    """
    user_id = session["user_id"]
    team_id = session.get("team_id")
    result = get_last_scan(user_id, team_id=team_id)
    if not result:
        return jsonify({"scan": None})
    return jsonify({"scan": result})


@history_bp.route("/history")
@login_required
def history_page():
    """Render the history page."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    team_id = session.get("team_id")
    tier = session.get("user_tier", "free")
    stats = get_history_stats(user_id, team_id=team_id)
    return render_template("auth/history.html", stats=stats, has_pdf=has_feature(tier, "pdf_reports"))


@history_bp.route("/api/history")
@login_required
def api_history_list():
    """JSON list of user's history with optional tool filter and pagination."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    team_id = session.get("team_id")
    tool = request.args.get("tool", "").strip() or None
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    rows = get_history(user_id, tool=tool, limit=limit, offset=offset, team_id=team_id)
    return jsonify({"results": rows, "count": len(rows)})


@history_bp.route("/api/history/<int:history_id>")
@login_required
def api_history_detail(history_id):
    """JSON single result with full data."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    team_id = session.get("team_id")
    result = get_result(history_id, user_id, team_id=team_id)
    if not result:
        return jsonify({"error": "Result not found."}), 404
    return jsonify(result)


@history_bp.route("/api/history/stats")
@login_required
def api_history_stats():
    """Combined stats, tool breakdown, and score trend for the dashboard overview."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    team_id = session.get("team_id")
    stats = get_history_stats(user_id, team_id=team_id)
    breakdown = get_tool_breakdown(user_id, team_id=team_id)
    trend = get_score_trend(user_id, days=30, team_id=team_id)
    return jsonify({"stats": stats, "breakdown": breakdown, "trend": trend})


@history_bp.route("/api/history/trend")
@login_required
def api_history_trend():
    """Score trend, optionally filtered by tool."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    team_id = session.get("team_id")
    tool = request.args.get("tool", "").strip() or None
    days = request.args.get("days", 30, type=int)
    trend = get_score_trend(user_id, tool=tool, days=min(days, 90), team_id=team_id)
    return jsonify({"trend": trend})


@history_bp.route("/api/history/<int:history_id>", methods=["DELETE"])
@login_required
def api_history_delete(history_id):
    """Delete a history result."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    team_id = session.get("team_id")
    deleted = delete_result(history_id, user_id, team_id=team_id)
    if not deleted:
        return jsonify({"error": "Result not found."}), 404
    return jsonify({"ok": True})
