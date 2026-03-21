"""
InbXr — Cloud History
Save, retrieve, and manage check results for logged-in users.
"""

import json
from modules.database import execute, fetchone, fetchall


def save_result(user_id, tool, input_summary, result_dict, grade=None, score=None, team_id=None):
    """Save a check result to history. Returns the new row ID."""
    result_json = json.dumps(result_dict, default=str)
    cur = execute(
        """INSERT INTO check_history (user_id, tool, input_summary, result_json, grade, score, team_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, tool, input_summary, result_json, grade, score, team_id),
    )
    return cur.lastrowid


def get_history(user_id, tool=None, limit=50, offset=0, team_id=None):
    """Fetch user's history list (without full result_json for performance).
    When team_id is set, returns team-wide history instead of personal.
    """
    limit = min(max(int(limit), 1), 200)
    offset = max(int(offset), 0)

    owner_clause = "team_id = ?" if team_id else "user_id = ?"
    owner_param = team_id if team_id else user_id

    if tool:
        rows = fetchall(
            f"""SELECT id, tool, input_summary, grade, score, created_at
               FROM check_history
               WHERE {owner_clause} AND tool = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (owner_param, tool, limit, offset),
        )
    else:
        rows = fetchall(
            f"""SELECT id, tool, input_summary, grade, score, created_at
               FROM check_history
               WHERE {owner_clause}
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (owner_param, limit, offset),
        )
    return rows


def get_last_scan(user_id, team_id=None):
    """Fetch the most recent check_history entry for a user (or team).
    Returns a lightweight dict (no result_json) or None.
    """
    owner_clause = "team_id = ?" if team_id else "user_id = ?"
    owner_param = team_id if team_id else user_id
    row = fetchone(
        f"""SELECT id, tool, input_summary, grade, score, created_at
           FROM check_history
           WHERE {owner_clause}
           ORDER BY created_at DESC
           LIMIT 1""",
        (owner_param,),
    )
    return dict(row) if row else None


def get_result(history_id, user_id, team_id=None):
    """Fetch a single full result including deserialized result_json.
    Verifies ownership (personal or team). Returns dict or None.
    """
    if team_id:
        row = fetchone(
            """SELECT id, tool, input_summary, result_json, grade, score, created_at
               FROM check_history
               WHERE id = ? AND team_id = ?""",
            (history_id, team_id),
        )
    else:
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


def delete_result(history_id, user_id, team_id=None):
    """Delete a history result, verifying ownership. Returns True if deleted."""
    if team_id:
        cur = execute(
            "DELETE FROM check_history WHERE id = ? AND team_id = ?",
            (history_id, team_id),
        )
    else:
        cur = execute(
            "DELETE FROM check_history WHERE id = ? AND user_id = ?",
            (history_id, user_id),
        )
    return cur.rowcount > 0


def get_history_stats(user_id, team_id=None):
    """Return summary stats for a user's (or team's) history."""
    clause = "team_id = ?" if team_id else "user_id = ?"
    param = team_id if team_id else user_id

    total = fetchone(
        f"SELECT COUNT(*) AS cnt FROM check_history WHERE {clause}",
        (param,),
    )
    total_checks = total["cnt"] if total else 0

    tools = fetchall(
        f"SELECT DISTINCT tool FROM check_history WHERE {clause}",
        (param,),
    )
    tools_used = [r["tool"] for r in tools]

    avg = fetchone(
        f"SELECT AVG(score) AS avg_score FROM check_history WHERE {clause} AND score IS NOT NULL",
        (param,),
    )
    avg_score = round(avg["avg_score"], 1) if avg and avg["avg_score"] is not None else None

    best = fetchone(
        f"""SELECT grade FROM check_history
           WHERE {clause} AND grade IS NOT NULL
           ORDER BY score DESC LIMIT 1""",
        (param,),
    )
    best_grade = best["grade"] if best else None

    week = fetchone(
        f"""SELECT COUNT(*) AS cnt FROM check_history
           WHERE {clause} AND created_at >= datetime('now', '-7 days')""",
        (param,),
    )
    checks_this_week = week["cnt"] if week else 0

    return {
        "total_checks": total_checks,
        "tools_used": tools_used,
        "avg_score": avg_score,
        "best_grade": best_grade,
        "checks_this_week": checks_this_week,
    }


def get_tool_breakdown(user_id, team_id=None):
    """Return count and avg score per tool."""
    clause = "team_id = ?" if team_id else "user_id = ?"
    param = team_id if team_id else user_id
    rows = fetchall(
        f"""SELECT tool, COUNT(*) AS cnt, AVG(score) AS avg_score
           FROM check_history WHERE {clause}
           GROUP BY tool ORDER BY cnt DESC""",
        (param,),
    )
    return [{"tool": r["tool"], "count": r["cnt"],
             "avg_score": round(r["avg_score"], 1) if r["avg_score"] is not None else None}
            for r in rows]


def get_score_trend(user_id, tool=None, days=30, team_id=None):
    """Return daily average scores for the trend chart."""
    clause = "team_id = ?" if team_id else "user_id = ?"
    param = team_id if team_id else user_id
    params = [param, days]
    tool_filter = ""
    if tool:
        tool_filter = " AND tool = ?"
        params.append(tool)
    rows = fetchall(
        f"""SELECT DATE(created_at) AS day, AVG(score) AS avg_score, COUNT(*) AS cnt
           FROM check_history
           WHERE {clause} AND created_at >= datetime('now', '-' || ? || ' days'){tool_filter}
           GROUP BY DATE(created_at) ORDER BY day""",
        tuple(params),
    )
    return [{"day": r["day"], "avg_score": round(r["avg_score"], 1) if r["avg_score"] is not None else None,
             "count": r["cnt"]} for r in rows]
