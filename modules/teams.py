"""
InbXr — Teams & Workspaces
Create teams, invite members, manage roles, share resources.
"""

import logging
import secrets
from modules.database import execute, fetchone, fetchall
from modules.tiers import has_feature, get_tier_limit

logger = logging.getLogger('inbxr.teams')


MAX_TEAM_MEMBERS = 10  # Agency tier cap


def create_team(owner_id, name):
    """Create a team and add the owner as the first member."""
    from modules.auth import get_user_by_id

    name = name.strip()
    if not name or len(name) > 100:
        return {"ok": False, "error": "Team name must be 1-100 characters."}

    user = get_user_by_id(owner_id)
    if not user:
        return {"ok": False, "error": "User not found."}
    if not has_feature(user["tier"], "teams"):
        return {"ok": False, "error": "Teams require an Agency plan."}

    # Check if user already owns/belongs to a team
    existing = get_user_team(owner_id)
    if existing:
        return {"ok": False, "error": "You already belong to a team."}

    cur = execute(
        "INSERT INTO teams (name, owner_id) VALUES (?, ?)",
        (name, owner_id),
    )
    team_id = cur.lastrowid

    execute(
        "INSERT INTO team_members (team_id, user_id, role) VALUES (?, ?, 'owner')",
        (team_id, owner_id),
    )

    return {"ok": True, "id": team_id, "name": name}


def get_team(team_id):
    """Get team by ID."""
    return fetchone("SELECT * FROM teams WHERE id = ?", (team_id,))


def get_user_team(user_id):
    """Get the team a user belongs to (or None)."""
    membership = fetchone(
        """SELECT tm.team_id, tm.role, t.name, t.owner_id
           FROM team_members tm
           JOIN teams t ON t.id = tm.team_id
           WHERE tm.user_id = ?""",
        (user_id,),
    )
    return membership


def get_team_members(team_id):
    """List all team members with user info."""
    return fetchall(
        """SELECT tm.id AS membership_id, tm.user_id, tm.role, tm.joined_at,
                  u.email, u.display_name
           FROM team_members tm
           JOIN users u ON u.id = tm.user_id
           WHERE tm.team_id = ?
           ORDER BY tm.role = 'owner' DESC, tm.joined_at ASC""",
        (team_id,),
    )


def get_team_user_ids(team_id):
    """Get all user IDs in a team."""
    rows = fetchall(
        "SELECT user_id FROM team_members WHERE team_id = ?",
        (team_id,),
    )
    return [r["user_id"] for r in rows]


def invite_member(team_id, inviter_id, email, role="member"):
    """Create a team invite. Returns invite dict or error."""
    email = email.strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "Valid email is required."}
    if role not in ("admin", "member"):
        return {"ok": False, "error": "Role must be admin or member."}

    # Check inviter permissions
    inviter = fetchone(
        "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, inviter_id),
    )
    if not inviter or inviter["role"] not in ("owner", "admin"):
        return {"ok": False, "error": "Only owners and admins can invite members."}

    # Check member limit
    count = fetchone(
        "SELECT COUNT(*) as cnt FROM team_members WHERE team_id = ?",
        (team_id,),
    )
    pending = fetchone(
        "SELECT COUNT(*) as cnt FROM team_invites WHERE team_id = ? AND status = 'pending'",
        (team_id,),
    )
    total = (count["cnt"] if count else 0) + (pending["cnt"] if pending else 0)
    if total >= MAX_TEAM_MEMBERS:
        return {"ok": False, "error": f"Team is at the {MAX_TEAM_MEMBERS}-member limit."}

    # Check if already a member
    existing_member = fetchone(
        """SELECT u.id FROM users u
           JOIN team_members tm ON tm.user_id = u.id
           WHERE u.email = ? AND tm.team_id = ?""",
        (email, team_id),
    )
    if existing_member:
        return {"ok": False, "error": "This person is already a team member."}

    # Check for existing pending invite
    existing_invite = fetchone(
        "SELECT id FROM team_invites WHERE team_id = ? AND email = ? AND status = 'pending'",
        (team_id, email),
    )
    if existing_invite:
        return {"ok": False, "error": "An invite is already pending for this email."}

    token = secrets.token_urlsafe(32)
    cur = execute(
        """INSERT INTO team_invites (team_id, email, role, token, invited_by)
           VALUES (?, ?, ?, ?, ?)""",
        (team_id, email, role, token, inviter_id),
    )

    return {"ok": True, "id": cur.lastrowid, "token": token, "email": email, "role": role}


def get_pending_invites(team_id):
    """List pending invites for a team."""
    return fetchall(
        """SELECT ti.id, ti.email, ti.role, ti.created_at, ti.expires_at,
                  u.display_name AS invited_by_name, u.email AS invited_by_email
           FROM team_invites ti
           JOIN users u ON u.id = ti.invited_by
           WHERE ti.team_id = ? AND ti.status = 'pending'
             AND ti.expires_at > datetime('now')
           ORDER BY ti.created_at DESC""",
        (team_id,),
    )


def get_invite_by_token(token):
    """Get invite details by token."""
    return fetchone(
        """SELECT ti.*, t.name AS team_name, u.display_name AS invited_by_name
           FROM team_invites ti
           JOIN teams t ON t.id = ti.team_id
           JOIN users u ON u.id = ti.invited_by
           WHERE ti.token = ?""",
        (token,),
    )


def accept_invite(token, user_id):
    """Accept an invite. Adds user to team."""
    invite = get_invite_by_token(token)
    if not invite:
        return {"ok": False, "error": "Invite not found."}
    if invite["status"] != "pending":
        return {"ok": False, "error": "This invite has already been used."}
    if invite["expires_at"] and invite["expires_at"] < __import__("datetime").datetime.now().isoformat():
        execute("UPDATE team_invites SET status = 'expired' WHERE id = ?", (invite["id"],))
        return {"ok": False, "error": "This invite has expired."}

    # Check user isn't already on a team
    existing = get_user_team(user_id)
    if existing:
        return {"ok": False, "error": "You already belong to a team. Leave it first."}

    # Add to team
    try:
        execute(
            "INSERT INTO team_members (team_id, user_id, role) VALUES (?, ?, ?)",
            (invite["team_id"], user_id, invite["role"]),
        )
    except Exception:
        logger.exception("Failed to add user %s to team %s", user_id, invite["team_id"])
        return {"ok": False, "error": "Could not join team."}

    execute("UPDATE team_invites SET status = 'accepted' WHERE id = ?", (invite["id"],))
    return {"ok": True, "team_id": invite["team_id"], "team_name": invite["team_name"]}


def decline_invite(token):
    """Decline an invite."""
    invite = get_invite_by_token(token)
    if not invite or invite["status"] != "pending":
        return {"ok": False, "error": "Invite not found or already used."}
    execute("UPDATE team_invites SET status = 'declined' WHERE id = ?", (invite["id"],))
    return {"ok": True}


def cancel_invite(team_id, invite_id, user_id):
    """Cancel a pending invite. Owner/admin only."""
    member = fetchone(
        "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, user_id),
    )
    if not member or member["role"] not in ("owner", "admin"):
        return {"ok": False, "error": "Permission denied."}

    invite = fetchone(
        "SELECT id FROM team_invites WHERE id = ? AND team_id = ? AND status = 'pending'",
        (invite_id, team_id),
    )
    if not invite:
        return {"ok": False, "error": "Invite not found."}

    execute("UPDATE team_invites SET status = 'declined' WHERE id = ?", (invite_id,))
    return {"ok": True}


def remove_member(team_id, remover_id, target_user_id):
    """Remove a member from the team."""
    remover = fetchone(
        "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, remover_id),
    )
    if not remover or remover["role"] not in ("owner", "admin"):
        return {"ok": False, "error": "Permission denied."}

    target = fetchone(
        "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, target_user_id),
    )
    if not target:
        return {"ok": False, "error": "Member not found."}
    if target["role"] == "owner":
        return {"ok": False, "error": "Cannot remove the team owner."}
    if target["role"] == "admin" and remover["role"] != "owner":
        return {"ok": False, "error": "Only the owner can remove admins."}

    execute(
        "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, target_user_id),
    )
    return {"ok": True}


def update_member_role(team_id, updater_id, target_user_id, new_role):
    """Change a member's role. Owner only."""
    if new_role not in ("admin", "member"):
        return {"ok": False, "error": "Role must be admin or member."}

    updater = fetchone(
        "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, updater_id),
    )
    if not updater or updater["role"] != "owner":
        return {"ok": False, "error": "Only the team owner can change roles."}

    if updater_id == target_user_id:
        return {"ok": False, "error": "Cannot change your own role."}

    target = fetchone(
        "SELECT id FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, target_user_id),
    )
    if not target:
        return {"ok": False, "error": "Member not found."}

    execute(
        "UPDATE team_members SET role = ? WHERE team_id = ? AND user_id = ?",
        (new_role, team_id, target_user_id),
    )
    return {"ok": True}


def leave_team(team_id, user_id):
    """Leave a team. Owners cannot leave (must delete)."""
    member = fetchone(
        "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, user_id),
    )
    if not member:
        return {"ok": False, "error": "Not a team member."}
    if member["role"] == "owner":
        return {"ok": False, "error": "Owners cannot leave. Delete the team instead."}

    execute(
        "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, user_id),
    )
    return {"ok": True}


def delete_team(team_id, owner_id):
    """Delete a team. Owner only. Cascades via FK."""
    team = fetchone(
        "SELECT id FROM teams WHERE id = ? AND owner_id = ?",
        (team_id, owner_id),
    )
    if not team:
        return {"ok": False, "error": "Team not found or you are not the owner."}

    execute("DELETE FROM team_invites WHERE team_id = ?", (team_id,))
    execute("DELETE FROM team_members WHERE team_id = ?", (team_id,))
    execute("DELETE FROM teams WHERE id = ?", (team_id,))
    return {"ok": True}


def get_user_pending_invites(email):
    """Get pending invites for an email address."""
    return fetchall(
        """SELECT ti.token, ti.role, ti.created_at, t.name AS team_name,
                  u.display_name AS invited_by_name
           FROM team_invites ti
           JOIN teams t ON t.id = ti.team_id
           JOIN users u ON u.id = ti.invited_by
           WHERE ti.email = ? AND ti.status = 'pending'
             AND ti.expires_at > datetime('now')
           ORDER BY ti.created_at DESC""",
        (email.strip().lower(),),
    )
