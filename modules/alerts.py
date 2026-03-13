"""
INBXR — Alert System
Creates, stores, and sends notifications for blocklist changes and other events.
"""

import json
import logging
from modules.database import execute, fetchone, fetchall
from modules.mailer import is_configured, _send

logger = logging.getLogger('inbxr.alerts')


def create_alert(user_id, alert_type, title, message, data=None, team_id=None, severity=None):
    """Store an alert in the database. Returns the alert id.
    When team_id is set, creates alerts for all team members.
    """
    data_json = json.dumps(data) if data else None

    if team_id:
        # Create alert for each team member
        try:
            from modules.teams import get_team_user_ids
            member_ids = get_team_user_ids(team_id)
        except Exception:
            logger.exception("Failed to get team user IDs for team %s, falling back to user %s", team_id, user_id)
            member_ids = [user_id]

        last_id = None
        for uid in member_ids:
            cur = execute(
                """INSERT INTO alerts (user_id, alert_type, title, message, data_json, team_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (uid, alert_type, title, message, data_json, team_id),
            )
            last_id = cur.lastrowid
        return last_id

    cur = execute(
        """INSERT INTO alerts (user_id, alert_type, title, message, data_json)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, alert_type, title, message, data_json),
    )
    return cur.lastrowid


def get_alerts(user_id, unread_only=False, limit=20):
    """Fetch alerts for a user, newest first."""
    if unread_only:
        return fetchall(
            "SELECT * FROM alerts WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
    return fetchall(
        "SELECT * FROM alerts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )


def mark_read(user_id, alert_id):
    """Mark a single alert as read. Verifies ownership."""
    execute(
        "UPDATE alerts SET is_read = 1 WHERE id = ? AND user_id = ?",
        (alert_id, user_id),
    )


def mark_all_read(user_id):
    """Mark all alerts as read for a user."""
    execute(
        "UPDATE alerts SET is_read = 1 WHERE user_id = ? AND is_read = 0",
        (user_id,),
    )


def get_unread_count(user_id):
    """Return count of unread alerts for a user."""
    row = fetchone(
        "SELECT COUNT(*) as cnt FROM alerts WHERE user_id = ? AND is_read = 0",
        (user_id,),
    )
    return row["cnt"] if row else 0


def send_blocklist_alert(user_id, domain, newly_listed, newly_delisted):
    """Create an in-app alert and send an email notification for blocklist changes."""
    from modules.auth import get_user_by_id

    parts = []
    if newly_listed:
        names = [bl["name"] if isinstance(bl, dict) else str(bl) for bl in newly_listed]
        parts.append(f"Newly listed on: {', '.join(names)}")
    if newly_delisted:
        names = [bl["name"] if isinstance(bl, dict) else str(bl) for bl in newly_delisted]
        parts.append(f"Delisted from: {', '.join(names)}")

    message = f"Blocklist status changed for {domain}. " + " | ".join(parts)

    if newly_listed:
        title = f"{domain} listed on {len(newly_listed)} new blocklist(s)"
        alert_type = "blocklist_listed"
    else:
        title = f"{domain} removed from {len(newly_delisted)} blocklist(s)"
        alert_type = "blocklist_delisted"

    data = {
        "domain": domain,
        "newly_listed": newly_listed,
        "newly_delisted": newly_delisted,
    }

    create_alert(user_id, alert_type, title, message, data)

    # Send email notification
    user = get_user_by_id(user_id)
    if not user or not is_configured():
        return

    listed_color = "#dc2626"
    delisted_color = "#16a34a"
    rows_html = ""
    for bl in (newly_listed or []):
        name = bl["name"] if isinstance(bl, dict) else str(bl)
        rows_html += f'<tr><td style="padding:6px 12px;color:{listed_color};font-weight:600;">LISTED</td><td style="padding:6px 12px;">{name}</td></tr>'
    for bl in (newly_delisted or []):
        name = bl["name"] if isinstance(bl, dict) else str(bl)
        rows_html += f'<tr><td style="padding:6px 12px;color:{delisted_color};font-weight:600;">DELISTED</td><td style="padding:6px 12px;">{name}</td></tr>'

    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
      <h2 style="color:#0c1a3a;margin:0 0 8px;">Blocklist Alert: {domain}</h2>
      <p style="color:#334155;font-size:15px;line-height:1.6;">{message}</p>
      <table style="width:100%;border-collapse:collapse;margin:16px 0;">
        <thead><tr style="background:#f1f5f9;">
          <th style="padding:8px 12px;text-align:left;font-size:13px;">Status</th>
          <th style="padding:8px 12px;text-align:left;font-size:13px;">Blocklist</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
      <a href="/monitors" style="display:inline-block;background:#16a34a;color:#fff;padding:10px 24px;border-radius:999px;text-decoration:none;font-weight:600;font-size:14px;margin:12px 0;">View Monitors</a>
      <p style="color:#94a3b8;font-size:12px;margin-top:24px;">INBXR — Blocklist Monitoring</p>
    </div>
    """
    text = f"Blocklist Alert: {domain}\n\n{message}\n\nView your monitors at /monitors"
    _send(user["email"], f"Blocklist Alert: {title}", html, text)
