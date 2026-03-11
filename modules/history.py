"""
INBXR — Cloud History
Save, retrieve, and manage check results for logged-in users.
"""

import json
from modules.database import execute, fetchone, fetchall


def save_result(user_id, tool, input_summary, result_dict, grade=None, score=None):
    """Save a check result to history. Returns the new row ID."""
    result_json = json.dumps(result_dict, default=str)
    cur = execute(
        """INSERT INTO check_history (user_id, tool, input_summary, result_json, grade, score)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, tool, input_summary, result_json, grade, score),
    )
    return cur.lastrowid


def get_history(user_id, tool=None, limit=50, offset=0):
    """Fetch user's history list (without full result_json for performance).
    Returns list of dicts with id, tool, input_summary, grade, score, created_at.
    """
    limit = min(max(int(limit), 1), 200)
    offset = max(int(offset), 0)

    if tool:
        rows = fetchall(
            """SELECT id, tool, input_summary, grade, score, created_at
               FROM check_history
               WHERE user_id = ? AND tool = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, tool, limit, offset),
        )
    else:
        rows = fetchall(
            """SELECT id, tool, input_summary, grade, score, created_at
               FROM check_history
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        )
    return rows


def get_result(history_id, user_id):
    """Fetch a single full result including deserialized result_json.
    Verifies user_id ownership for security. Returns dict or None.
    """
    row = fetchone(
        """SELECT id, tool, input_summary, result_json, grade, score, created_at
           FROM check_history
           WHERE id = ? AND user_id = ?""",
        (history_id, user_id),
    )
    if not row:
        return None

    result = dict(row)
    try:
        result["result_json"] = json.loads(result["result_json"])
    except (json.JSONDecodeError, TypeError):
        result["result_json"] = None
    return result


def delete_result(history_id, user_id):
    """Delete a history result, verifying ownership. Returns True if deleted."""
    cur = execute(
        "DELETE FROM check_history WHERE id = ? AND user_id = ?",
        (history_id, user_id),
    )
    return cur.rowcount > 0


def get_history_stats(user_id):
    """Return summary stats for a user's history."""
    total = fetchone(
        "SELECT COUNT(*) AS cnt FROM check_history WHERE user_id = ?",
        (user_id,),
    )
    total_checks = total["cnt"] if total else 0

    tools = fetchall(
        "SELECT DISTINCT tool FROM check_history WHERE user_id = ?",
        (user_id,),
    )
    tools_used = [r["tool"] for r in tools]

    avg = fetchone(
        "SELECT AVG(score) AS avg_score FROM check_history WHERE user_id = ? AND score IS NOT NULL",
        (user_id,),
    )
    avg_score = round(avg["avg_score"], 1) if avg and avg["avg_score"] is not None else None

    best = fetchone(
        """SELECT grade FROM check_history
           WHERE user_id = ? AND grade IS NOT NULL
           ORDER BY score DESC LIMIT 1""",
        (user_id,),
    )
    best_grade = best["grade"] if best else None

    week = fetchone(
        """SELECT COUNT(*) AS cnt FROM check_history
           WHERE user_id = ? AND created_at >= datetime('now', '-7 days')""",
        (user_id,),
    )
    checks_this_week = week["cnt"] if week else 0

    return {
        "total_checks": total_checks,
        "tools_used": tools_used,
        "avg_score": avg_score,
        "best_grade": best_grade,
        "checks_this_week": checks_this_week,
    }
