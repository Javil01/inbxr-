"""
InbXr — Alert System
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


def get_alert_preferences(user_id):
    """Get alert preferences for a user. Creates defaults if missing."""
    row = fetchone(
        "SELECT * FROM alert_preferences WHERE user_id = ?", (user_id,)
    )
    if row:
        return row
    # Return defaults (don't create yet — created on first save)
    return {
        "user_id": user_id,
        "blocklist_alerts": 1,
        "dns_auth_alerts": 1,
        "digest_frequency": "instant",
        "email_notifications": 1,
        "last_digest_at": None,
    }


def save_alert_preferences(user_id, prefs):
    """Save alert preferences. Creates or updates."""
    existing = fetchone("SELECT id FROM alert_preferences WHERE user_id = ?", (user_id,))
    if existing:
        execute(
            """UPDATE alert_preferences
               SET blocklist_alerts = ?, dns_auth_alerts = ?,
                   digest_frequency = ?, email_notifications = ?,
                   updated_at = datetime('now')
               WHERE user_id = ?""",
            (
                int(prefs.get("blocklist_alerts", True)),
                int(prefs.get("dns_auth_alerts", True)),
                prefs.get("digest_frequency", "instant"),
                int(prefs.get("email_notifications", True)),
                user_id,
            ),
        )
    else:
        execute(
            """INSERT INTO alert_preferences
               (user_id, blocklist_alerts, dns_auth_alerts, digest_frequency, email_notifications)
               VALUES (?, ?, ?, ?, ?)""",
            (
                user_id,
                int(prefs.get("blocklist_alerts", True)),
                int(prefs.get("dns_auth_alerts", True)),
                prefs.get("digest_frequency", "instant"),
                int(prefs.get("email_notifications", True)),
            ),
        )


def should_send_email_alert(user_id):
    """Check if this user should receive email alerts (tier + preferences)."""
    from modules.tiers import has_feature
    from modules.auth import get_user_by_id

    user = get_user_by_id(user_id)
    if not user:
        return False

    if not has_feature(user["tier"], "email_alerts"):
        return False

    prefs = get_alert_preferences(user_id)
    return bool(prefs.get("email_notifications", True))


def send_digest_emails(frequency):
    """Send digest emails for users with the given frequency ('daily' or 'weekly').
    Collects unread alerts since last digest and sends a summary email.
    """
    from modules.mailer import _send, is_configured, BASE_URL

    if not is_configured():
        return 0

    users = fetchall(
        """SELECT ap.user_id, ap.last_digest_at, u.email, u.display_name, u.tier
           FROM alert_preferences ap
           JOIN users u ON u.id = ap.user_id
           WHERE ap.digest_frequency = ? AND ap.email_notifications = 1""",
        (frequency,),
    )

    sent = 0
    for user in users:
        from modules.tiers import has_feature
        if not has_feature(user["tier"], "email_alerts"):
            continue

        since = user["last_digest_at"] or "2000-01-01"
        alerts = fetchall(
            """SELECT * FROM alerts WHERE user_id = ? AND created_at > ?
               ORDER BY created_at DESC LIMIT 50""",
            (user["user_id"], since),
        )

        if not alerts:
            continue

        # Build digest HTML
        name = user["display_name"] or user["email"].split("@")[0]
        rows_html = ""
        for a in alerts[:20]:
            icon = "🔴" if "listed" in a.get("alert_type", "") else "🔵"
            rows_html += f'<tr><td style="padding:8px 12px;font-size:13px;">{icon} {a["title"]}</td><td style="padding:8px 12px;font-size:12px;color:#64748b;">{a["created_at"][:16]}</td></tr>'

        remaining = len(alerts) - 20
        extra = f'<p style="color:#64748b;font-size:13px;">...and {remaining} more alerts</p>' if remaining > 0 else ""

        html = f"""
        <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
          <h2 style="color:#0c1a3a;margin:0 0 8px;">Your {frequency.title()} Alert Digest</h2>
          <p style="color:#334155;font-size:15px;line-height:1.6;">
            Hey {name}, here's a summary of your recent alerts.
          </p>
          <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <thead><tr style="background:#f1f5f9;">
              <th style="padding:8px 12px;text-align:left;font-size:13px;">Alert</th>
              <th style="padding:8px 12px;text-align:left;font-size:13px;">Time</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
          {extra}
          <a href="{BASE_URL}/monitors" style="display:inline-block;background:#16a34a;color:#fff;padding:10px 24px;border-radius:999px;text-decoration:none;font-weight:600;font-size:14px;margin:12px 0;">View All Alerts</a>
          <p style="color:#94a3b8;font-size:12px;margin-top:24px;">
            InbXr — Email Intelligence Platform<br>
            <a href="{BASE_URL}/monitors" style="color:#94a3b8;">Manage alert preferences</a>
          </p>
        </div>
        """
        text = f"Your {frequency} alert digest — {len(alerts)} new alerts. View at {BASE_URL}/monitors"

        if _send(user["email"], f"InbXr {frequency.title()} Digest — {len(alerts)} Alert(s)", html, text):
            execute(
                "UPDATE alert_preferences SET last_digest_at = datetime('now') WHERE user_id = ?",
                (user["user_id"],),
            )
            sent += 1

    logger.info("[DIGEST] Sent %d %s digest emails", sent, frequency)
    return sent


def cleanup_old_alerts(days=90):
    """Delete read alerts older than N days."""
    execute(
        "DELETE FROM alerts WHERE is_read = 1 AND created_at < datetime('now', ?)",
        (f'-{days} days',),
    )
    logger.info("[ALERTS] Cleaned up read alerts older than %d days", days)


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

    # Build enriched blocklist details for in-app display
    listed_details = []
    for bl in (newly_listed or []):
        if isinstance(bl, dict):
            listed_details.append({
                "name": bl.get("name", "Unknown"),
                "weight": bl.get("weight", ""),
                "delist": bl.get("delist", ""),
                "info": bl.get("info", ""),
                "reason": bl.get("reason", ""),
            })
        else:
            listed_details.append({"name": str(bl)})

    delisted_details = []
    for bl in (newly_delisted or []):
        if isinstance(bl, dict):
            delisted_details.append({
                "name": bl.get("name", "Unknown"),
                "weight": bl.get("weight", ""),
            })
        else:
            delisted_details.append({"name": str(bl)})

    data = {
        "domain": domain,
        "newly_listed": newly_listed,
        "newly_delisted": newly_delisted,
        "listed_details": listed_details,
        "delisted_details": delisted_details,
    }

    # Check blocklist alert preference
    prefs = get_alert_preferences(user_id)
    if not prefs.get("blocklist_alerts", True):
        return

    create_alert(user_id, alert_type, title, message, data)

    # Send email notification (only if instant + email enabled + tier allows)
    if not should_send_email_alert(user_id):
        return
    if prefs.get("digest_frequency") != "instant":
        return  # Will be included in digest

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
      <p style="color:#94a3b8;font-size:12px;margin-top:24px;">InbXr — Blocklist Monitoring</p>
    </div>
    """
    text = f"Blocklist Alert: {domain}\n\n{message}\n\nView your monitors at /monitors"
    _send(user["email"], f"Blocklist Alert: {title}", html, text)
