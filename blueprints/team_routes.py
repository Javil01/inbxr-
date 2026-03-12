"""
INBXR — Team Routes
Create, manage, and invite members to team workspaces.
"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for

from modules.auth import login_required, get_current_user
from modules.tiers import has_feature
from modules.teams import (
    create_team, get_user_team, get_team_members, get_team_user_ids,
    invite_member, get_pending_invites, get_invite_by_token,
    accept_invite, decline_invite, cancel_invite,
    remove_member, update_member_role, leave_team, delete_team,
    get_user_pending_invites,
)

team_bp = Blueprint("team", __name__)


def _require_teams():
    """Check if current user has the teams feature."""
    tier = session.get("user_tier", "free")
    # Team members may be on free tier — check if they belong to a team
    team = get_user_team(session.get("user_id")) if session.get("user_id") else None
    if not has_feature(tier, "teams") and not team:
        if request.is_json or request.path.startswith("/api/"):
            return jsonify({"error": "Teams require an Agency plan.", "upgrade_url": "/pricing"}), 403
        return redirect("/pricing?upgrade=1")
    return None


# ── Pages ──────────────────────────────────────────────

@team_bp.route("/team")
@login_required
def team_page():
    """Team management page."""
    user = get_current_user()
    team = get_user_team(user["id"])

    # Non-agency users without a team get redirected
    if not team and not has_feature(user["tier"], "teams"):
        return redirect("/pricing?upgrade=1")

    return render_template(
        "auth/team.html",
        active_page="team",
        team=team,
        can_create=has_feature(user["tier"], "teams") and not team,
    )


@team_bp.route("/team/invite/<token>")
def invite_page(token):
    """View an invite and accept/decline."""
    invite = get_invite_by_token(token)
    if not invite or invite["status"] != "pending":
        return render_template("auth/invite_expired.html", active_page="team")
    return render_template(
        "auth/invite_accept.html",
        active_page="team",
        invite=invite,
        token=token,
    )


# ── API: Team CRUD ─────────────────────────────────────

@team_bp.route("/api/team", methods=["GET"])
@login_required
def get_team_info():
    """Get team info, members, and pending invites."""
    user = get_current_user()
    team = get_user_team(user["id"])
    if not team:
        return jsonify({"ok": True, "team": None})

    members = get_team_members(team["team_id"])
    invites = get_pending_invites(team["team_id"])
    return jsonify({
        "ok": True,
        "team": {
            "id": team["team_id"],
            "name": team["name"],
            "role": team["role"],
            "owner_id": team["owner_id"],
        },
        "members": members,
        "invites": invites,
    })


@team_bp.route("/api/team", methods=["POST"])
@login_required
def create_team_api():
    """Create a new team."""
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Team name is required."}), 400

    result = create_team(user["id"], name)
    if not result["ok"]:
        return jsonify(result), 400

    # Set team context in session
    session["team_id"] = result["id"]
    session["team_name"] = name
    session["team_role"] = "owner"

    return jsonify(result), 201


@team_bp.route("/api/team", methods=["PUT"])
@login_required
def update_team_api():
    """Update team name."""
    user = get_current_user()
    team = get_user_team(user["id"])
    if not team or team["role"] not in ("owner", "admin"):
        return jsonify({"ok": False, "error": "Permission denied."}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) > 100:
        return jsonify({"ok": False, "error": "Team name must be 1-100 characters."}), 400

    from modules.database import execute
    execute("UPDATE teams SET name = ? WHERE id = ?", (name, team["team_id"]))
    session["team_name"] = name
    return jsonify({"ok": True, "name": name})


@team_bp.route("/api/team", methods=["DELETE"])
@login_required
def delete_team_api():
    """Delete the team. Owner only."""
    user = get_current_user()
    team = get_user_team(user["id"])
    if not team:
        return jsonify({"ok": False, "error": "No team found."}), 404

    result = delete_team(team["team_id"], user["id"])
    if not result["ok"]:
        return jsonify(result), 403

    session.pop("team_id", None)
    session.pop("team_name", None)
    session.pop("team_role", None)
    return jsonify(result)


# ── API: Invites ───────────────────────────────────────

@team_bp.route("/api/team/invite", methods=["POST"])
@login_required
def send_invite():
    """Send an invite to an email address."""
    user = get_current_user()
    team = get_user_team(user["id"])
    if not team:
        return jsonify({"ok": False, "error": "No team found."}), 404

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    role = (data.get("role") or "member").strip()

    result = invite_member(team["team_id"], user["id"], email, role)
    if not result["ok"]:
        return jsonify(result), 400

    # Send invite email
    try:
        from modules.mailer import send_team_invite_email
        inviter_name = user.get("display_name") or user["email"].split("@")[0]
        send_team_invite_email(email, team["name"], inviter_name, result["token"])
    except Exception:
        pass  # Invite still created even if email fails

    return jsonify(result), 201


@team_bp.route("/api/team/invite/<int:invite_id>", methods=["DELETE"])
@login_required
def revoke_invite(invite_id):
    """Cancel a pending invite."""
    user = get_current_user()
    team = get_user_team(user["id"])
    if not team:
        return jsonify({"ok": False, "error": "No team found."}), 404

    result = cancel_invite(team["team_id"], invite_id, user["id"])
    if not result["ok"]:
        return jsonify(result), 400
    return jsonify(result)


@team_bp.route("/api/team/invite/<token>/accept", methods=["POST"])
@login_required
def accept_invite_api(token):
    """Accept an invite."""
    user = get_current_user()
    result = accept_invite(token, user["id"])
    if not result["ok"]:
        return jsonify(result), 400

    # Set team context
    session["team_id"] = result["team_id"]
    session["team_name"] = result["team_name"]
    session["team_role"] = "member"  # Could be admin, refresh from DB
    team = get_user_team(user["id"])
    if team:
        session["team_role"] = team["role"]

    return jsonify(result)


@team_bp.route("/api/team/invite/<token>/decline", methods=["POST"])
def decline_invite_api(token):
    """Decline an invite."""
    result = decline_invite(token)
    if not result["ok"]:
        return jsonify(result), 400
    return jsonify(result)


# ── API: Members ───────────────────────────────────────

@team_bp.route("/api/team/members/<int:member_user_id>", methods=["DELETE"])
@login_required
def remove_member_api(member_user_id):
    """Remove a member from the team."""
    user = get_current_user()
    team = get_user_team(user["id"])
    if not team:
        return jsonify({"ok": False, "error": "No team found."}), 404

    result = remove_member(team["team_id"], user["id"], member_user_id)
    if not result["ok"]:
        return jsonify(result), 400
    return jsonify(result)


@team_bp.route("/api/team/members/<int:member_user_id>", methods=["PUT"])
@login_required
def update_role_api(member_user_id):
    """Update a member's role."""
    user = get_current_user()
    team = get_user_team(user["id"])
    if not team:
        return jsonify({"ok": False, "error": "No team found."}), 404

    data = request.get_json(silent=True) or {}
    new_role = (data.get("role") or "").strip()

    result = update_member_role(team["team_id"], user["id"], member_user_id, new_role)
    if not result["ok"]:
        return jsonify(result), 400
    return jsonify(result)


@team_bp.route("/api/team/leave", methods=["POST"])
@login_required
def leave_team_api():
    """Leave the current team."""
    user = get_current_user()
    team = get_user_team(user["id"])
    if not team:
        return jsonify({"ok": False, "error": "No team found."}), 404

    result = leave_team(team["team_id"], user["id"])
    if not result["ok"]:
        return jsonify(result), 400

    session.pop("team_id", None)
    session.pop("team_name", None)
    session.pop("team_role", None)
    return jsonify(result)


# ── API: Pending invites for current user ──────────────

@team_bp.route("/api/team/my-invites")
@login_required
def my_invites():
    """Get pending invites for the current user's email."""
    user = get_current_user()
    invites = get_user_pending_invites(user["email"])
    return jsonify({"ok": True, "invites": invites})
