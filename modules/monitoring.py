"""
InbXr — Per-User Domain Monitoring
Manages monitored domains per user, runs scans, tracks history.
Stores everything in the main inbxr.db via modules/database.
"""

import json
import logging
from modules.database import execute, fetchone, fetchall
from modules.tiers import get_tier_limit

logger = logging.getLogger('inbxr.monitoring')


def add_user_monitor(user_id, domain, ip=None, team_id=None):
    """Add a domain to a user's (or team's) monitored list. Checks tier limit."""
    from modules.auth import get_user_by_id

    domain = domain.strip().lower().rstrip(".")
    if not domain:
        return {"ok": False, "error": "Domain is required."}

    user = get_user_by_id(user_id)
    if not user:
        return {"ok": False, "error": "User not found."}

    # Use team owner's tier for limit if in team context
    tier = user["tier"]
    if team_id:
        from modules.database import fetchone as _fo
        team = _fo("SELECT owner_id FROM teams WHERE id = ?", (team_id,))
        if team:
            owner = get_user_by_id(team["owner_id"])
            if owner:
                tier = owner["tier"]

    limit = get_tier_limit(tier, "blocklist_domains")
    count_clause = "team_id = ?" if team_id else "user_id = ?"
    count_param = team_id if team_id else user_id
    current = fetchone(
        f"SELECT COUNT(*) as cnt FROM user_monitors WHERE {count_clause}", (count_param,)
    )
    if current and current["cnt"] >= limit:
        return {"ok": False, "error": f"You can monitor up to {limit} domains on your plan."}

    try:
        cur = execute(
            """INSERT INTO user_monitors (user_id, domain, ip, team_id)
               VALUES (?, ?, ?, ?)""",
            (user_id, domain, ip or None, team_id),
        )
        return {"ok": True, "id": cur.lastrowid, "domain": domain}
    except Exception:
        logger.exception("Failed to add monitor for domain %s", domain)
        return {"ok": False, "error": f"{domain} is already being monitored."}


def remove_user_monitor(user_id, monitor_id, team_id=None):
    """Remove a monitor. Verifies ownership (personal or team)."""
    if team_id:
        row = fetchone(
            "SELECT id FROM user_monitors WHERE id = ? AND team_id = ?",
            (monitor_id, team_id),
        )
    else:
        row = fetchone(
            "SELECT id FROM user_monitors WHERE id = ? AND user_id = ?",
            (monitor_id, user_id),
        )
    if not row:
        return {"ok": False, "error": "Monitor not found."}

    execute("DELETE FROM monitor_scans WHERE monitor_id = ?", (monitor_id,))
    execute("DELETE FROM user_monitors WHERE id = ?", (monitor_id,))
    return {"ok": True}


def get_user_monitors(user_id, team_id=None):
    """List all monitored domains for a user (or team) with latest scan info."""
    if team_id:
        monitors = fetchall(
            "SELECT * FROM user_monitors WHERE team_id = ? ORDER BY created_at DESC",
            (team_id,),
        )
    else:
        monitors = fetchall(
            "SELECT * FROM user_monitors WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
    for m in monitors:
        scan = fetchone(
            "SELECT * FROM monitor_scans WHERE monitor_id = ? ORDER BY scanned_at DESC LIMIT 1",
            (m["id"],),
        )
        if scan:
            m["last_scan"] = {
                "scanned_at": scan["scanned_at"],
                "total_lists": scan["total_lists"],
                "listed_count": scan["listed_count"],
                "listed_on": json.loads(scan["listed_on"]) if scan["listed_on"] else [],
                "clean": bool(scan["clean"]),
            }
        else:
            m["last_scan"] = None
    return monitors


def scan_user_domain(user_id, monitor_id, team_id=None):
    """Run a scan for a specific monitored domain. Store result and check for changes."""
    from modules.blacklist_monitor import scan_domain as _bl_scan_domain
    from modules.alerts import send_blocklist_alert

    if team_id:
        monitor = fetchone(
            "SELECT * FROM user_monitors WHERE id = ? AND team_id = ?",
            (monitor_id, team_id),
        )
    else:
        monitor = fetchone(
            "SELECT * FROM user_monitors WHERE id = ? AND user_id = ?",
            (monitor_id, user_id),
        )
    if not monitor:
        return {"ok": False, "error": "Monitor not found."}

    domain = monitor["domain"]
    ip = monitor["ip"]

    # We need the domain in the global blacklist monitor to scan it
    # Instead, directly use reputation checker like blacklist_monitor does
    from modules.reputation_checker import ReputationChecker

    try:
        checker = ReputationChecker(domain=domain, sender_ip=ip)
        dnsbl_results = checker._run_dnsbl_checks(check_ip=ip)
    except Exception as e:
        return {"ok": False, "error": f"Scan failed: {str(e)}"}

    total_lists = len(dnsbl_results)
    listed_entries = [r for r in dnsbl_results if r.get("listed")]
    listed_count = len(listed_entries)
    listed_on = [
        {"name": r["name"], "zone": r["zone"], "weight": r.get("weight", 1),
         "type": r.get("type", ""), "reason": r.get("reason"),
         "delist": r.get("delist", ""), "info": r.get("info", "")}
        for r in listed_entries
    ]
    clean = listed_count == 0

    # Store scan result
    execute(
        """INSERT INTO monitor_scans (monitor_id, total_lists, listed_count, listed_on, clean)
           VALUES (?, ?, ?, ?, ?)""",
        (monitor_id, total_lists, listed_count, json.dumps(listed_on), int(clean)),
    )

    # Update monitor record
    execute(
        """UPDATE user_monitors SET last_scanned_at = datetime('now'),
           last_listed_count = ? WHERE id = ?""",
        (listed_count, monitor_id),
    )

    # Check for changes and alert
    changes = check_for_changes(user_id, monitor_id, listed_on)
    if changes["newly_listed"] or changes["newly_delisted"]:
        if monitor["alert_on_change"]:
            send_blocklist_alert(user_id, domain, changes["newly_listed"], changes["newly_delisted"])

    return {
        "ok": True,
        "domain": domain,
        "total_lists": total_lists,
        "listed_count": listed_count,
        "listed_on": listed_on,
        "clean": clean,
        "changes": changes,
    }


def scan_all_user_domains(user_id):
    """Scan all of a user's monitored domains. Returns list of results."""
    monitors = fetchall(
        "SELECT id FROM user_monitors WHERE user_id = ?", (user_id,)
    )
    results = []
    for m in monitors:
        result = scan_user_domain(user_id, m["id"])
        results.append(result)
    return results


def get_monitor_history(user_id, monitor_id, limit=30, team_id=None):
    """Get scan history for a specific monitor. Verifies ownership."""
    if team_id:
        monitor = fetchone(
            "SELECT id FROM user_monitors WHERE id = ? AND team_id = ?",
            (monitor_id, team_id),
        )
    else:
        monitor = fetchone(
            "SELECT id FROM user_monitors WHERE id = ? AND user_id = ?",
            (monitor_id, user_id),
        )
    if not monitor:
        return []

    scans = fetchall(
        "SELECT * FROM monitor_scans WHERE monitor_id = ? ORDER BY scanned_at DESC LIMIT ?",
        (monitor_id, limit),
    )
    for s in scans:
        s["listed_on"] = json.loads(s["listed_on"]) if s["listed_on"] else []
        s["clean"] = bool(s["clean"])
    return scans


def check_for_changes(user_id, monitor_id, new_listed_on):
    """Compare current scan with previous scan. Return newly listed/delisted."""
    # Get the second most recent scan (the one before the one we just inserted)
    scans = fetchall(
        "SELECT listed_on FROM monitor_scans WHERE monitor_id = ? ORDER BY scanned_at DESC LIMIT 2",
        (monitor_id,),
    )

    if len(scans) < 2:
        # No previous scan to compare
        return {"newly_listed": [], "newly_delisted": []}

    prev_listed_on = json.loads(scans[1]["listed_on"]) if scans[1]["listed_on"] else []

    # Extract names for comparison
    new_names = {(bl["name"] if isinstance(bl, dict) else str(bl)) for bl in new_listed_on}
    prev_names = {(bl["name"] if isinstance(bl, dict) else str(bl)) for bl in prev_listed_on}

    newly_listed_names = new_names - prev_names
    newly_delisted_names = prev_names - new_names

    newly_listed = [bl for bl in new_listed_on if (bl["name"] if isinstance(bl, dict) else str(bl)) in newly_listed_names]
    newly_delisted = [bl for bl in prev_listed_on if (bl["name"] if isinstance(bl, dict) else str(bl)) in newly_delisted_names]

    return {
        "newly_listed": newly_listed,
        "newly_delisted": newly_delisted,
    }
