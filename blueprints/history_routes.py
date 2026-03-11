"""
INBXR — History Blueprint
Routes for viewing and managing saved check results.
"""

from flask import Blueprint, render_template, request, jsonify, session

from modules.auth import login_required
from modules.tiers import has_feature
from modules.history import get_history, get_result, delete_result, get_history_stats

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


@history_bp.route("/history")
@login_required
def history_page():
    """Render the history page."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    stats = get_history_stats(user_id)
    return render_template("auth/history.html", stats=stats)


@history_bp.route("/api/history")
@login_required
def api_history_list():
    """JSON list of user's history with optional tool filter and pagination."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    tool = request.args.get("tool", "").strip() or None
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    rows = get_history(user_id, tool=tool, limit=limit, offset=offset)
    return jsonify({"results": rows, "count": len(rows)})


@history_bp.route("/api/history/<int:history_id>")
@login_required
def api_history_detail(history_id):
    """JSON single result with full data."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    result = get_result(history_id, user_id)
    if not result:
        return jsonify({"error": "Result not found."}), 404
    return jsonify(result)


@history_bp.route("/api/history/<int:history_id>", methods=["DELETE"])
@login_required
def api_history_delete(history_id):
    """Delete a history result."""
    gate = _require_cloud_history()
    if gate:
        return gate

    user_id = session["user_id"]
    deleted = delete_result(history_id, user_id)
    if not deleted:
        return jsonify({"error": "Result not found."}), 404
    return jsonify({"ok": True})
