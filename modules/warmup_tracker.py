"""
InbXr — Warm-up Tracker
Tracks IP/domain warm-up campaigns with daily volume logging and health assessment.
"""

import os
import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta

logger = logging.getLogger('inbxr.warmup_tracker')

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "warmup.db")

# Recommended daily volumes by day range
WARMUP_SCHEDULE = [
    {"day_start": 1,  "day_end": 3,  "volume": 20,   "label": "Day 1-3"},
    {"day_start": 4,  "day_end": 7,  "volume": 50,   "label": "Day 4-7"},
    {"day_start": 8,  "day_end": 14, "volume": 100,  "label": "Day 8-14"},
    {"day_start": 15, "day_end": 21, "volume": 250,  "label": "Day 15-21"},
    {"day_start": 22, "day_end": 30, "volume": 500,  "label": "Day 22-30"},
    {"day_start": 31, "day_end": 9999, "volume": None, "label": "Day 30+"},
]


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS warmup_campaigns (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            domain       TEXT    NOT NULL,
            esp          TEXT    NOT NULL DEFAULT 'other',
            daily_target INTEGER NOT NULL DEFAULT 500,
            started_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            status       TEXT    NOT NULL DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS warmup_days (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id      INTEGER NOT NULL REFERENCES warmup_campaigns(id) ON DELETE CASCADE,
            day_number       INTEGER NOT NULL,
            date             TEXT    NOT NULL DEFAULT (date('now')),
            sent_count       INTEGER NOT NULL DEFAULT 0,
            placement_result TEXT,
            notes            TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_days_campaign ON warmup_days(campaign_id, day_number);
    """)
    conn.close()


def create_campaign(domain, esp, daily_target):
    """Create a new warm-up campaign."""
    domain = domain.strip().lower().rstrip(".")
    if not domain:
        return {"ok": False, "error": "Domain is required."}
    daily_target = int(daily_target) if daily_target else 500

    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO warmup_campaigns (domain, esp, daily_target) VALUES (?, ?, ?)",
            (domain, esp or "other", daily_target),
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid, "domain": domain}
    finally:
        conn.close()


def get_campaigns():
    """List all campaigns with summary stats."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM warmup_campaigns ORDER BY started_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            # Get summary
            stats = conn.execute(
                """SELECT COUNT(*) as total_days, COALESCE(SUM(sent_count), 0) as total_sent,
                   MAX(day_number) as last_day
                   FROM warmup_days WHERE campaign_id = ?""",
                (row["id"],),
            ).fetchone()
            d["total_days"] = stats["total_days"]
            d["total_sent"] = stats["total_sent"]
            d["last_day"] = stats["last_day"] or 0
            result.append(d)
        return result
    finally:
        conn.close()


def get_campaign(campaign_id):
    """Get a single campaign with all day logs."""
    conn = _get_conn()
    try:
        campaign = conn.execute(
            "SELECT * FROM warmup_campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if not campaign:
            return None

        d = dict(campaign)
        days = conn.execute(
            "SELECT * FROM warmup_days WHERE campaign_id = ? ORDER BY day_number ASC",
            (campaign_id,),
        ).fetchall()
        d["days"] = [
            {
                "id": day["id"],
                "day_number": day["day_number"],
                "date": day["date"],
                "sent_count": day["sent_count"],
                "placement_result": json.loads(day["placement_result"]) if day["placement_result"] else None,
                "notes": day["notes"],
            }
            for day in days
        ]
        return d
    finally:
        conn.close()


def log_day(campaign_id, sent_count, placement_result=None, notes=None):
    """Log a day's warm-up activity."""
    conn = _get_conn()
    try:
        campaign = conn.execute(
            "SELECT * FROM warmup_campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if not campaign:
            return {"ok": False, "error": "Campaign not found."}

        # Determine next day number
        last = conn.execute(
            "SELECT MAX(day_number) as last_day FROM warmup_days WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        next_day = (last["last_day"] or 0) + 1

        placement_json = json.dumps(placement_result) if placement_result else None

        conn.execute(
            """INSERT INTO warmup_days (campaign_id, day_number, sent_count, placement_result, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (campaign_id, next_day, int(sent_count), placement_json, notes),
        )
        conn.commit()
        return {"ok": True, "day_number": next_day}
    finally:
        conn.close()


def get_campaign_stats(campaign_id):
    """Compute stats for a campaign: totals, averages, health assessment."""
    conn = _get_conn()
    try:
        campaign = conn.execute(
            "SELECT * FROM warmup_campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if not campaign:
            return None

        days = conn.execute(
            "SELECT * FROM warmup_days WHERE campaign_id = ? ORDER BY day_number ASC",
            (campaign_id,),
        ).fetchall()

        if not days:
            return {
                "total_days": 0,
                "total_sent": 0,
                "avg_daily": 0,
                "health": "not_started",
                "health_label": "Not Started",
                "recommended_today": 20,
            }

        total_days = len(days)
        total_sent = sum(d["sent_count"] for d in days)
        avg_daily = round(total_sent / total_days) if total_days > 0 else 0
        current_day = days[-1]["day_number"]
        last_sent = days[-1]["sent_count"]

        # Determine recommended volume for current day
        recommended = None
        for bracket in WARMUP_SCHEDULE:
            if bracket["day_start"] <= current_day <= bracket["day_end"]:
                recommended = bracket["volume"]
                break

        if recommended is None:
            # Past day 30 — target is the campaign daily_target
            recommended = campaign["daily_target"]

        # Health assessment
        if recommended and last_sent >= recommended * 0.9:
            health = "on_track"
            health_label = "On Track"
        elif recommended and last_sent >= recommended * 1.3:
            health = "ahead"
            health_label = "Ahead of Schedule"
        elif recommended and last_sent < recommended * 0.5:
            health = "behind"
            health_label = "Behind Schedule"
        elif recommended and last_sent < recommended * 0.9:
            health = "slightly_behind"
            health_label = "Slightly Behind"
        else:
            health = "on_track"
            health_label = "On Track"

        # Placement trend (if any placement tests logged)
        placement_days = [d for d in days if d["placement_result"]]
        placement_trend = None
        if placement_days:
            try:
                results = [json.loads(d["placement_result"]) for d in placement_days[-5:]]
                inbox_rates = []
                for pr in results:
                    total = (pr.get("inbox", 0) + pr.get("spam", 0) + pr.get("not_found", 0)) or 1
                    inbox_rates.append(round(pr.get("inbox", 0) / total * 100))
                placement_trend = inbox_rates
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                logger.exception("Failed to parse placement trend data for campaign %s", campaign_id)

        return {
            "total_days": total_days,
            "total_sent": total_sent,
            "avg_daily": avg_daily,
            "current_day": current_day,
            "last_sent": last_sent,
            "recommended_today": recommended,
            "health": health,
            "health_label": health_label,
            "placement_trend": placement_trend,
            "schedule": WARMUP_SCHEDULE,
        }
    finally:
        conn.close()


def update_campaign_status(campaign_id, status):
    """Update campaign status (active/paused/completed)."""
    if status not in ("active", "paused", "completed"):
        return {"ok": False, "error": "Invalid status."}
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE warmup_campaigns SET status = ? WHERE id = ?",
            (status, campaign_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def delete_campaign(campaign_id):
    """Delete a campaign and all its day logs."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM warmup_days WHERE campaign_id = ?", (campaign_id,))
        conn.execute("DELETE FROM warmup_campaigns WHERE id = ?", (campaign_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# Initialize DB on import
init_db()
