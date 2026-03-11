"""
INBXR — Blacklist Monitor
Tracks domains against DNSBL blocklists over time using SQLite storage.
"""

import os
import json
import sqlite3
import time
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "blacklist_monitor.db")

MAX_DOMAINS = 5


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS monitored_domains (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            domain      TEXT    NOT NULL UNIQUE,
            ip          TEXT,
            added_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            last_checked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS scan_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id   INTEGER NOT NULL REFERENCES monitored_domains(id) ON DELETE CASCADE,
            checked_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            total_lists INTEGER NOT NULL DEFAULT 0,
            listed_count INTEGER NOT NULL DEFAULT 0,
            listed_on   TEXT    NOT NULL DEFAULT '[]',
            clean       INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_scan_domain ON scan_results(domain_id, checked_at DESC);
    """)
    conn.close()


def add_domain(domain, ip=None):
    """Add a domain to monitor. Returns dict with success/error."""
    domain = domain.strip().lower().rstrip(".")
    if not domain:
        return {"ok": False, "error": "Domain is required."}

    conn = _get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM monitored_domains").fetchone()[0]
        if count >= MAX_DOMAINS:
            return {"ok": False, "error": f"Maximum of {MAX_DOMAINS} monitored domains reached."}

        conn.execute(
            "INSERT INTO monitored_domains (domain, ip) VALUES (?, ?)",
            (domain, ip or None),
        )
        conn.commit()
        return {"ok": True, "domain": domain}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": f"{domain} is already being monitored."}
    finally:
        conn.close()


def remove_domain(domain):
    """Remove a domain from monitoring."""
    domain = domain.strip().lower().rstrip(".")
    conn = _get_conn()
    try:
        # Delete scan results first (CASCADE should handle but be explicit)
        row = conn.execute("SELECT id FROM monitored_domains WHERE domain = ?", (domain,)).fetchone()
        if not row:
            return {"ok": False, "error": "Domain not found."}
        conn.execute("DELETE FROM scan_results WHERE domain_id = ?", (row["id"],))
        conn.execute("DELETE FROM monitored_domains WHERE id = ?", (row["id"],))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def get_monitored_domains():
    """Return all monitored domains with their latest scan status."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM monitored_domains ORDER BY added_at DESC").fetchall()
        result = []
        for row in rows:
            d = dict(row)
            # Get latest scan
            scan = conn.execute(
                "SELECT * FROM scan_results WHERE domain_id = ? ORDER BY checked_at DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            if scan:
                d["last_scan"] = {
                    "checked_at": scan["checked_at"],
                    "total_lists": scan["total_lists"],
                    "listed_count": scan["listed_count"],
                    "listed_on": json.loads(scan["listed_on"]),
                    "clean": bool(scan["clean"]),
                }
            else:
                d["last_scan"] = None
            result.append(d)
        return result
    finally:
        conn.close()


def scan_domain(domain, ip=None):
    """Scan a single domain against DNSBL blocklists. Store results."""
    from modules.reputation_checker import (
        ReputationChecker, IP_DNSBLS, DOMAIN_DNSBLS,
    )

    domain = domain.strip().lower().rstrip(".")
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM monitored_domains WHERE domain = ?", (domain,)).fetchone()
        if not row:
            return {"ok": False, "error": "Domain not being monitored."}

        domain_id = row["id"]
        check_ip = ip or row["ip"]

        # Run DNSBL checks using reputation_checker infrastructure
        checker = ReputationChecker(domain=domain, sender_ip=check_ip)
        dnsbl_results = checker._run_dnsbl_checks(check_ip=check_ip)

        total_lists = len(dnsbl_results)
        listed_entries = [r for r in dnsbl_results if r.get("listed")]
        listed_count = len(listed_entries)
        listed_on = [{"name": r["name"], "zone": r["zone"], "weight": r["weight"],
                       "type": r.get("type", ""), "reason": r.get("reason")}
                      for r in listed_entries]
        clean = listed_count == 0

        conn.execute(
            """INSERT INTO scan_results (domain_id, total_lists, listed_count, listed_on, clean)
               VALUES (?, ?, ?, ?, ?)""",
            (domain_id, total_lists, listed_count, json.dumps(listed_on), int(clean)),
        )
        conn.execute(
            "UPDATE monitored_domains SET last_checked_at = datetime('now') WHERE id = ?",
            (domain_id,),
        )
        conn.commit()

        return {
            "ok": True,
            "domain": domain,
            "total_lists": total_lists,
            "listed_count": listed_count,
            "listed_on": listed_on,
            "clean": clean,
            "all_results": dnsbl_results,
        }
    finally:
        conn.close()


def get_domain_history(domain, limit=30):
    """Return scan history for a domain."""
    domain = domain.strip().lower().rstrip(".")
    conn = _get_conn()
    try:
        row = conn.execute("SELECT id FROM monitored_domains WHERE domain = ?", (domain,)).fetchone()
        if not row:
            return []
        scans = conn.execute(
            "SELECT * FROM scan_results WHERE domain_id = ? ORDER BY checked_at DESC LIMIT ?",
            (row["id"], limit),
        ).fetchall()
        return [
            {
                "checked_at": s["checked_at"],
                "total_lists": s["total_lists"],
                "listed_count": s["listed_count"],
                "listed_on": json.loads(s["listed_on"]),
                "clean": bool(s["clean"]),
            }
            for s in scans
        ]
    finally:
        conn.close()


def scan_all():
    """Scan all monitored domains. Returns list of results."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT domain, ip FROM monitored_domains").fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        r = scan_domain(row["domain"], ip=row["ip"])
        results.append(r)
    return results


# Initialize DB on import
init_db()
