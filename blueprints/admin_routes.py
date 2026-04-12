"""
InbXr -- Admin Blueprint
Admin authentication, dashboard, user management, revenue, segments,
media library, SEO panel, site settings, AppSumo LTD management.
"""

import os
import re
import uuid
import logging
import threading
import time as _time_module

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    jsonify, session, Response, current_app,
)

logger = logging.getLogger('inbxr.admin')

admin_bp = Blueprint("admin", __name__)

# ---------------------------------------------------------------------------
# Helpers imported from the main app module at call time to avoid circular
# imports.  _is_admin lives in app.py because non-admin routes also use it.
# ---------------------------------------------------------------------------

def _is_admin():
    """Re-implemented here to avoid a circular import from app.py."""
    if not session.get("is_admin", False):
        return False
    admin_login_time = session.get("admin_login_at")
    if not admin_login_time:
        session.pop("is_admin", None)
        return False
    elapsed = _time_module.time() - admin_login_time
    if elapsed > _ADMIN_SESSION_HOURS * 3600:
        session.pop("is_admin", None)
        session.pop("admin_login_at", None)
        return False
    return True


def _log_admin_action(action, details=""):
    """Log an admin action to the audit log table."""
    try:
        from modules.database import execute
        ip = request.remote_addr or "unknown"
        execute(
            "INSERT INTO admin_audit_log (action, details, ip_address) VALUES (?, ?, ?)",
            (action, details, ip),
        )
    except Exception:
        logger.exception("Failed to log admin action: %s", action)


# ── Admin credentials (read from env) ────────────────
ADMIN_USER = os.environ.get("ADMIN_USER")
_ADMIN_PASS_HASH = os.environ.get("ADMIN_PASS_HASH", "")
_ADMIN_PASS_PLAIN = os.environ.get("ADMIN_PASS", "")  # fallback for backwards compat

# ── Admin login rate limiting ─────────────────────────
_ADMIN_RATE_LIMIT_WINDOW = 15 * 60   # 15 minutes
_ADMIN_RATE_LIMIT_MAX = 5            # max failures before block

def _check_admin_rate_limit(ip):
    """Return True if IP is blocked from admin login."""
    from modules.database import fetchone
    row = fetchone(
        "SELECT COUNT(*) as cnt FROM admin_audit_log WHERE action = 'login_failed' AND ip_address = ? AND created_at > datetime('now', ?)",
        (ip, f"-{_ADMIN_RATE_LIMIT_WINDOW} seconds")
    )
    return (row["cnt"] if row else 0) >= _ADMIN_RATE_LIMIT_MAX

def _record_admin_login_failure(ip):
    """Record a failed admin login attempt (logged via _log_admin_action)."""
    pass  # Failures are already logged in admin_audit_log by _log_admin_action

def _clear_admin_login_failures(ip):
    """No-op -- DB-backed rate limiting doesn't need manual clearing."""
    pass

# ── Admin session expiry ──────────────────────────────
_ADMIN_SESSION_HOURS = 4

# ── Page name aliases (for SEO / analytics endpoints) ─
_PAGE_ALIASES = {"index": "analyzer"}
def _resolve_page_name(n):
    return _PAGE_ALIASES.get(n, n)


# ══════════════════════════════════════════════════════
#  ADMIN AUTH ROUTES
# ══════════════════════════════════════════════════════

@admin_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        if _is_admin():
            return redirect("/admin")
        return render_template("admin_login.html", error=None)

    # Admin login disabled if credentials not configured
    if not ADMIN_USER or (not _ADMIN_PASS_HASH and not _ADMIN_PASS_PLAIN):
        _log_admin_action("login_disabled", "Admin login attempted but credentials not configured")
        return render_template("admin_login.html", error="Admin login is disabled. Set ADMIN_USER and ADMIN_PASS environment variables.")

    ip = request.remote_addr or "unknown"

    # Rate limit check
    if _check_admin_rate_limit(ip):
        _log_admin_action("login_blocked", f"Rate-limited IP: {ip}")
        return render_template("admin_login.html", error="Too many failed attempts. Try again in 15 minutes."), 429

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "")

    # Verify admin password -- prefer hashed, fallback to plaintext
    _admin_pw_ok = False
    if _ADMIN_PASS_HASH and username == ADMIN_USER:
        from modules.auth import _verify_password
        _admin_pw_ok = _verify_password(_ADMIN_PASS_HASH, password)
    elif _ADMIN_PASS_PLAIN and username == ADMIN_USER:
        import hmac
        _admin_pw_ok = hmac.compare_digest(password, _ADMIN_PASS_PLAIN)

    if _admin_pw_ok:
        session["is_admin"] = True
        session["admin_login_at"] = _time_module.time()
        _clear_admin_login_failures(ip)
        _log_admin_action("login", f"Admin login successful from {ip}")
        return redirect("/admin")

    _record_admin_login_failure(ip)
    _log_admin_action("login_failed", f"Failed admin login attempt from {ip} (user: {username})")
    return render_template("admin_login.html", error="Invalid username or password.")


@admin_bp.route("/admin")
def admin_dashboard():
    if not _is_admin():
        return redirect("/admin/login")

    from modules.database import fetchone, fetchall

    # User stats
    total_users = fetchone("SELECT COUNT(*) as cnt FROM users")
    tier_counts = fetchall("SELECT tier, COUNT(*) as cnt FROM users GROUP BY tier")
    today_signups = fetchone(
        "SELECT COUNT(*) as cnt FROM users WHERE created_at > datetime('now', '-1 day')"
    )
    week_signups = fetchone(
        "SELECT COUNT(*) as cnt FROM users WHERE created_at > datetime('now', '-7 days')"
    )
    verified_count = fetchone("SELECT COUNT(*) as cnt FROM users WHERE email_verified = 1")

    # Usage stats
    today_usage = fetchone(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE created_at > datetime('now', '-1 day')"
    )
    week_usage = fetchone(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE created_at > datetime('now', '-7 days')"
    )
    # Top tools today
    top_tools = fetchall(
        "SELECT action, COUNT(*) as cnt FROM usage_log WHERE created_at > datetime('now', '-1 day') GROUP BY action ORDER BY cnt DESC LIMIT 8"
    )

    # Check history stats
    total_checks = fetchone("SELECT COUNT(*) as cnt FROM check_history")
    today_checks = fetchone(
        "SELECT COUNT(*) as cnt FROM check_history WHERE created_at > datetime('now', '-1 day')"
    )

    # Active monitors
    total_monitors = fetchone("SELECT COUNT(*) as cnt FROM user_monitors")
    listed_monitors = fetchone("SELECT COUNT(*) as cnt FROM user_monitors WHERE last_listed_count > 0")

    # Bulk jobs
    active_bulk = fetchone("SELECT COUNT(*) as cnt FROM bulk_jobs WHERE status IN ('pending','processing')")
    total_bulk = fetchone("SELECT COUNT(*) as cnt FROM bulk_jobs")

    # Alerts
    total_alerts = fetchone("SELECT COUNT(*) as cnt FROM alerts")
    unread_alerts = fetchone("SELECT COUNT(*) as cnt FROM alerts WHERE is_read = 0")

    # Teams
    total_teams = fetchone("SELECT COUNT(*) as cnt FROM teams")

    # Revenue / MRR
    prices = {"free": 0, "pro": 29, "agency": 79, "api": 0}
    mrr = sum(prices.get(r["tier"], 0) * r["cnt"] for r in tier_counts)

    # Active users (7d / 30d)
    active_7d = fetchone(
        "SELECT COUNT(DISTINCT user_id) as cnt FROM usage_log WHERE created_at > datetime('now', '-7 days') AND user_id IS NOT NULL"
    )
    active_30d = fetchone(
        "SELECT COUNT(DISTINCT user_id) as cnt FROM usage_log WHERE created_at > datetime('now', '-30 days') AND user_id IS NOT NULL"
    )

    # Suspended users
    suspended_count = fetchone("SELECT COUNT(*) as cnt FROM users WHERE status = 'suspended'")

    # Recent signups (last 5)
    recent_signups = fetchall(
        "SELECT id, email, display_name, tier, created_at FROM users ORDER BY created_at DESC LIMIT 5"
    )

    # ── Traffic analytics ──
    traffic_today = fetchone("SELECT COUNT(*) as cnt FROM page_views WHERE created_at > datetime('now', '-1 day')")
    traffic_week = fetchone("SELECT COUNT(*) as cnt FROM page_views WHERE created_at > datetime('now', '-7 days')")
    traffic_month = fetchone("SELECT COUNT(*) as cnt FROM page_views WHERE created_at > datetime('now', '-30 days')")
    unique_today = fetchone("SELECT COUNT(DISTINCT ip_address) as cnt FROM page_views WHERE created_at > datetime('now', '-1 day')")
    unique_week = fetchone("SELECT COUNT(DISTINCT ip_address) as cnt FROM page_views WHERE created_at > datetime('now', '-7 days')")

    # Page views by page (last 30 days)
    traffic_by_page = fetchall("""
        SELECT page_name,
               COUNT(*) as total,
               SUM(CASE WHEN created_at > datetime('now', '-1 day') THEN 1 ELSE 0 END) as today,
               SUM(CASE WHEN created_at > datetime('now', '-7 days') THEN 1 ELSE 0 END) as week,
               COUNT(DISTINCT ip_address) as unique_visitors
        FROM page_views
        WHERE created_at > datetime('now', '-30 days')
        GROUP BY page_name ORDER BY total DESC LIMIT 20
    """)

    # Daily traffic trend (last 30 days)
    traffic_daily = fetchall("""
        SELECT date(created_at) as day, COUNT(*) as views, COUNT(DISTINCT ip_address) as visitors
        FROM page_views WHERE created_at > datetime('now', '-30 days')
        GROUP BY day ORDER BY day
    """)

    # Top referrers (last 30 days)
    top_referrers = fetchall("""
        SELECT referrer, COUNT(*) as cnt
        FROM page_views
        WHERE referrer IS NOT NULL AND referrer != '' AND created_at > datetime('now', '-30 days')
        GROUP BY referrer ORDER BY cnt DESC LIMIT 10
    """)

    # Tool usage by page (map page names to friendly labels)
    _page_labels = {
        "index": "Home / Email Test",
        "analyzer": "Email Analyzer",
        "sender": "Sender Check",
        "placement": "Inbox Placement",
        "subject-scorer": "Subject Scorer",
        "bimi": "BIMI Checker",
        "header-analyzer": "Header Analyzer",
        "blacklist-monitor": "Blacklist Monitor",
        "email-verifier": "Email Verifier",
        "warmup": "Warm-up Tracker",
        "blog": "Blog",
        "pricing": "Pricing",
        "signup": "Signup",
        "login": "Login",
        "dashboard": "Dashboard",
        "support": "Help & Support",
        "account": "Account",
    }
    for p in traffic_by_page:
        p["label"] = _page_labels.get(p["page_name"], p["page_name"])

    # Scheduler status
    try:
        from modules.scheduler import get_scheduler_status
        scheduler = get_scheduler_status()
    except Exception:
        logger.exception("Failed to get scheduler status")
        scheduler = {"running": False, "jobs": []}

    # Service health
    services = {}
    services["groq"] = bool(os.environ.get("GROQ_API_KEY"))
    services["stripe"] = bool(os.environ.get("STRIPE_SECRET_KEY"))
    services["smtp"] = bool(os.environ.get("SMTP_HOST"))

    stats = {
        "total_users": total_users["cnt"] if total_users else 0,
        "tier_counts": {r["tier"]: r["cnt"] for r in tier_counts},
        "today_signups": today_signups["cnt"] if today_signups else 0,
        "week_signups": week_signups["cnt"] if week_signups else 0,
        "verified_users": verified_count["cnt"] if verified_count else 0,
        "today_usage": today_usage["cnt"] if today_usage else 0,
        "week_usage": week_usage["cnt"] if week_usage else 0,
        "top_tools": top_tools,
        "total_checks": total_checks["cnt"] if total_checks else 0,
        "today_checks": today_checks["cnt"] if today_checks else 0,
        "total_monitors": total_monitors["cnt"] if total_monitors else 0,
        "listed_monitors": listed_monitors["cnt"] if listed_monitors else 0,
        "active_bulk": active_bulk["cnt"] if active_bulk else 0,
        "total_bulk": total_bulk["cnt"] if total_bulk else 0,
        "total_alerts": total_alerts["cnt"] if total_alerts else 0,
        "unread_alerts": unread_alerts["cnt"] if unread_alerts else 0,
        "total_teams": total_teams["cnt"] if total_teams else 0,
        "mrr": mrr,
        "active_7d": active_7d["cnt"] if active_7d else 0,
        "active_30d": active_30d["cnt"] if active_30d else 0,
        "suspended": suspended_count["cnt"] if suspended_count else 0,
        "recent_signups": recent_signups,
        "scheduler": scheduler,
        "services": services,
        "traffic_today": traffic_today["cnt"] if traffic_today else 0,
        "traffic_week": traffic_week["cnt"] if traffic_week else 0,
        "traffic_month": traffic_month["cnt"] if traffic_month else 0,
        "unique_today": unique_today["cnt"] if unique_today else 0,
        "unique_week": unique_week["cnt"] if unique_week else 0,
        "traffic_by_page": traffic_by_page,
        "traffic_daily": traffic_daily,
        "top_referrers": top_referrers,
    }

    return render_template("admin_dashboard.html", is_admin=True, stats=stats, active_page="admin")


@admin_bp.route("/admin/logout")
def admin_logout():
    _log_admin_action("logout", "Admin logged out")
    session.pop("is_admin", None)
    session.pop("admin_login_at", None)
    return redirect("/")




# ── Admin: User Management ───────────────────────────

@admin_bp.route("/admin/users")
def admin_users():
    if not _is_admin():
        return redirect("/admin/login")
    return render_template("admin_users.html", is_admin=True, active_page="admin_users")


@admin_bp.route("/admin/api/users")
def admin_api_users():
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchall, fetchone

    search = request.args.get("q", "").strip()
    tier_filter = request.args.get("tier", "")
    sort = request.args.get("sort", "created_at")
    order = "ASC" if request.args.get("order") == "asc" else "DESC"
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50

    allowed_sorts = {"created_at", "email", "tier", "display_name"}
    if sort not in allowed_sorts:
        sort = "created_at"

    where_clauses = []
    params = []

    if search:
        where_clauses.append("(u.email LIKE ? OR u.display_name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if tier_filter:
        where_clauses.append("u.tier = ?")
        params.append(tier_filter)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Total count
    total = fetchone(f"SELECT COUNT(*) as cnt FROM users u {where_sql}", tuple(params))
    total_count = total["cnt"] if total else 0

    # Users with usage stats
    users = fetchall(f"""
        SELECT u.id, u.email, u.display_name, u.tier, u.email_verified,
               u.stripe_customer_id, u.created_at, u.updated_at,
               (SELECT COUNT(*) FROM check_history ch WHERE ch.user_id = u.id) as total_checks,
               (SELECT COUNT(*) FROM usage_log ul WHERE ul.user_id = u.id
                AND ul.created_at > datetime('now', '-1 day')) as checks_today,
               (SELECT MAX(created_at) FROM usage_log ul2 WHERE ul2.user_id = u.id) as last_active
        FROM users u
        {where_sql}
        ORDER BY u.{sort} {order}
        LIMIT ? OFFSET ?
    """, tuple(params + [per_page, (page - 1) * per_page]))

    # Summary stats
    tier_counts = fetchall("SELECT tier, COUNT(*) as cnt FROM users GROUP BY tier")
    summary = {
        "total_users": total_count,
        "tier_counts": {r["tier"]: r["cnt"] for r in tier_counts},
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total_count + per_page - 1) // per_page),
    }

    return jsonify({"users": users, "summary": summary})


@admin_bp.route("/admin/api/users/<int:user_id>/tier", methods=["POST"])
def admin_api_update_tier(user_id):
    """Admin: Change a user's tier."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import execute, fetchone

    data = request.get_json(silent=True) or {}
    new_tier = data.get("tier", "")
    if new_tier not in ("free", "pro", "agency", "api"):
        return jsonify({"error": "Invalid tier"}), 400

    user = fetchone("SELECT id, email FROM users WHERE id = ?", (user_id,))
    if not user:
        return jsonify({"error": "User not found"}), 404

    execute("UPDATE users SET tier = ?, updated_at = datetime('now') WHERE id = ?", (new_tier, user_id))
    _log_admin_action("tier_change", f"User {user['email']} (id={user_id}) tier changed to {new_tier}")
    return jsonify({"ok": True, "email": user["email"], "tier": new_tier})


@admin_bp.route("/admin/api/users/<int:user_id>/profile")
def admin_api_user_profile(user_id):
    """Admin: Full user profile with activity history."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchone, fetchall

    user = fetchone("""
        SELECT id, email, display_name, tier, email_verified,
               stripe_customer_id, stripe_subscription_id, api_key,
               created_at, updated_at,
               COALESCE(status, 'active') as status, suspended_at,
               COALESCE(admin_flags, '') as admin_flags
        FROM users WHERE id = ?
    """, (user_id,))
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Usage stats
    usage_today = fetchone(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ? AND created_at > datetime('now', '-1 day')",
        (user_id,),
    )
    usage_week = fetchone(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ? AND created_at > datetime('now', '-7 days')",
        (user_id,),
    )
    usage_month = fetchone(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ? AND created_at > datetime('now', '-30 days')",
        (user_id,),
    )

    # Tool breakdown
    tool_breakdown = fetchall("""
        SELECT action, COUNT(*) as cnt
        FROM usage_log WHERE user_id = ?
        GROUP BY action ORDER BY cnt DESC
    """, (user_id,))

    # Recent test history (last 25)
    history = fetchall("""
        SELECT id, tool, input_summary, grade, score, created_at
        FROM check_history WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 25
    """, (user_id,))

    # Recent usage log (last 50 actions)
    activity = fetchall("""
        SELECT action, ip_address, created_at
        FROM usage_log WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 50
    """, (user_id,))

    # Admin notes
    notes = fetchall("""
        SELECT id, note, COALESCE(tag, 'general') as tag, created_at FROM admin_notes
        WHERE user_id = ? ORDER BY created_at DESC
    """, (user_id,))

    # Teams
    teams = fetchall("""
        SELECT t.id, t.name, tm.role
        FROM team_members tm JOIN teams t ON t.id = tm.team_id
        WHERE tm.user_id = ?
    """, (user_id,))

    return jsonify({
        "user": dict(user),
        "usage": {
            "today": usage_today["cnt"] if usage_today else 0,
            "week": usage_week["cnt"] if usage_week else 0,
            "month": usage_month["cnt"] if usage_month else 0,
        },
        "tool_breakdown": tool_breakdown,
        "history": history,
        "activity": activity,
        "notes": notes,
        "teams": teams,
    })


@admin_bp.route("/admin/api/users/<int:user_id>/notes", methods=["POST"])
def admin_api_add_note(user_id):
    """Admin: Add a note to a user's profile."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import execute, fetchone

    user = fetchone("SELECT id FROM users WHERE id = ?", (user_id,))
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    note = (data.get("note") or "").strip()
    tag = data.get("tag", "general")
    if tag not in ("general", "vip", "support", "complaint", "follow_up", "bug"):
        tag = "general"
    if not note:
        return jsonify({"error": "Note is required"}), 400

    execute("INSERT INTO admin_notes (user_id, note, tag) VALUES (?, ?, ?)", (user_id, note, tag))
    return jsonify({"ok": True})


@admin_bp.route("/admin/api/users/<int:user_id>/notes/<int:note_id>", methods=["DELETE"])
def admin_api_delete_note(user_id, note_id):
    """Admin: Delete a note."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import execute
    execute("DELETE FROM admin_notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    return jsonify({"ok": True})


@admin_bp.route("/admin/api/users/export")
def admin_api_export_users():
    """Admin: Export all users as CSV."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    import csv
    import io
    from modules.database import fetchall

    tier_filter = request.args.get("tier", "")
    where = "WHERE tier = ?" if tier_filter else ""
    params = (tier_filter,) if tier_filter else ()

    users = fetchall(f"""
        SELECT u.id, u.email, u.display_name, u.tier, u.email_verified,
               u.stripe_customer_id, u.created_at,
               (SELECT COUNT(*) FROM check_history ch WHERE ch.user_id = u.id) as total_checks,
               (SELECT COUNT(*) FROM usage_log ul WHERE ul.user_id = u.id
                AND ul.created_at > datetime('now', '-30 days')) as checks_30d,
               (SELECT MAX(created_at) FROM usage_log ul2 WHERE ul2.user_id = u.id) as last_active
        FROM users u {where}
        ORDER BY u.created_at DESC
    """, params)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Email", "Name", "Tier", "Verified", "Stripe ID",
                      "Joined", "Total Checks", "Checks (30d)", "Last Active"])
    for u in users:
        writer.writerow([
            u["id"], u["email"], u["display_name"], u["tier"],
            "Yes" if u["email_verified"] else "No",
            u["stripe_customer_id"] or "",
            u["created_at"], u["total_checks"], u["checks_30d"],
            u["last_active"] or "Never",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=inbxr-users.csv"},
    )


# ══════════════════════════════════════════════════════
#  ADMIN -- REVENUE DASHBOARD
# ══════════════════════════════════════════════════════

@admin_bp.route("/admin/revenue")
def admin_revenue():
    if not _is_admin():
        return redirect("/admin/login")
    return render_template("admin_revenue.html", is_admin=True, active_page="admin_revenue")


@admin_bp.route("/admin/signal-analytics")
def admin_signal_analytics():
    """Admin Signal Intelligence analytics -- score distribution, danger users, rule adoption."""
    if not _is_admin():
        return redirect("/admin/login")
    return render_template("admin_signal_analytics.html", is_admin=True, active_page="admin_signal_analytics")


@admin_bp.route("/admin/api/signal-analytics")
def admin_api_signal_analytics():
    """JSON data for Signal Intelligence admin dashboard."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchone, fetchall
    from datetime import datetime, timedelta

    # Score distribution (latest score per user)
    distribution = fetchall("""
        SELECT signal_grade, COUNT(*) as cnt
        FROM (
            SELECT user_id, signal_grade,
                   ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY calculated_at DESC) as rn
            FROM signal_scores
        )
        WHERE rn = 1
        GROUP BY signal_grade
    """)
    grade_buckets = {row["signal_grade"]: row["cnt"] for row in distribution}
    for g in ['A', 'B', 'C', 'D', 'F']:
        grade_buckets.setdefault(g, 0)

    # Total users with any signal score
    total_with_scores = fetchone("SELECT COUNT(DISTINCT user_id) as cnt FROM signal_scores")
    total_with_scores = total_with_scores["cnt"] if total_with_scores else 0

    # Users in Danger (F grade) -- flag for outreach
    danger_users = fetchall("""
        SELECT u.id, u.email, u.tier, ss.total_signal_score, ss.calculated_at,
               ss.total_contacts, ss.dormant_contacts
        FROM users u
        JOIN signal_scores ss ON ss.user_id = u.id
        WHERE ss.signal_grade = 'F'
        AND ss.calculated_at = (
            SELECT MAX(calculated_at) FROM signal_scores WHERE user_id = u.id
        )
        ORDER BY ss.calculated_at DESC
        LIMIT 50
    """)

    # Pro+ users count for adoption rate
    pro_users_total = fetchone("SELECT COUNT(*) as cnt FROM users WHERE tier IN ('pro', 'agency', 'api')")
    pro_users_total = pro_users_total["cnt"] if pro_users_total else 0

    # Signal Rules adoption -- % of Pro+ users with at least one active rule
    users_with_rules = fetchone("""
        SELECT COUNT(DISTINCT user_id) as cnt FROM signal_rules WHERE is_active = 1
    """)
    users_with_rules = users_with_rules["cnt"] if users_with_rules else 0
    rules_adoption_pct = round((users_with_rules / pro_users_total * 100) if pro_users_total else 0, 1)

    # Total active rules
    total_active_rules = fetchone("SELECT COUNT(*) as cnt FROM signal_rules WHERE is_active = 1")
    total_active_rules = total_active_rules["cnt"] if total_active_rules else 0

    # Live rules (not dry-run)
    live_rules = fetchone("SELECT COUNT(*) as cnt FROM signal_rules WHERE is_active = 1 AND action_dry_run = 0")
    live_rules = live_rules["cnt"] if live_rules else 0

    # Early Warning fire rate -- last 7 days
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    alerts_this_week = fetchone(
        "SELECT COUNT(*) as cnt FROM alerts WHERE alert_type = 'early_warning' AND created_at >= ?",
        (week_ago,),
    )
    alerts_this_week = alerts_this_week["cnt"] if alerts_this_week else 0

    # Rule firings this week
    rules_fired_week = fetchone(
        "SELECT COUNT(*) as cnt FROM signal_rule_log WHERE was_dry_run = 0 AND fired_at >= ?",
        (week_ago,),
    )
    rules_fired_week = rules_fired_week["cnt"] if rules_fired_week else 0

    # Total contacts under management
    total_contacts = fetchone("SELECT COUNT(*) as cnt FROM contact_segments")
    total_contacts = total_contacts["cnt"] if total_contacts else 0

    return jsonify({
        "ok": True,
        "score_distribution": grade_buckets,
        "total_users_with_scores": total_with_scores,
        "danger_users": [dict(u) for u in danger_users],
        "pro_users_total": pro_users_total,
        "rules_adoption": {
            "users_with_rules": users_with_rules,
            "pct": rules_adoption_pct,
            "total_active_rules": total_active_rules,
            "live_rules": live_rules,
        },
        "early_warning": {
            "fired_last_7d": alerts_this_week,
            "rules_fired_last_7d": rules_fired_week,
        },
        "contacts_under_management": total_contacts,
    })


@admin_bp.route("/admin/api/revenue")
def admin_api_revenue():
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchone, fetchall

    PRICES = {"free": 0, "pro": 29, "agency": 79, "api": 0}

    # Current MRR
    tier_counts = fetchall("SELECT tier, COUNT(*) as cnt FROM users GROUP BY tier")
    tc = {r["tier"]: r["cnt"] for r in tier_counts}
    mrr = sum(PRICES.get(t, 0) * c for t, c in tc.items())

    # MRR trend (last 12 months) -- approximate by counting users created before each month-end
    mrr_trend = []
    for months_ago in range(11, -1, -1):
        row = fetchall(f"""
            SELECT tier, COUNT(*) as cnt FROM users
            WHERE created_at <= datetime('now', '-{months_ago} months', 'start of month', '+1 month', '-1 second')
            GROUP BY tier
        """)
        month_tc = {r["tier"]: r["cnt"] for r in row}
        month_mrr = sum(PRICES.get(t, 0) * c for t, c in month_tc.items())
        label_row = fetchone(f"SELECT strftime('%Y-%m', datetime('now', '-{months_ago} months')) as m")
        mrr_trend.append({"month": label_row["m"] if label_row else "", "mrr": month_mrr})

    # ARPU (average revenue per user)
    total_users = sum(tc.values()) or 1
    paid_users = tc.get("pro", 0) + tc.get("agency", 0)
    arpu = round(mrr / total_users, 2) if total_users else 0
    arpu_paid = round(mrr / paid_users, 2) if paid_users else 0

    # Churn proxy -- paid users inactive 30+ days
    churned = fetchone("""
        SELECT COUNT(*) as cnt FROM users
        WHERE tier IN ('pro', 'agency')
        AND id NOT IN (
            SELECT DISTINCT user_id FROM usage_log
            WHERE created_at > datetime('now', '-30 days') AND user_id IS NOT NULL
        )
    """)

    # Revenue by tier
    revenue_by_tier = [
        {"tier": t, "users": tc.get(t, 0), "revenue": PRICES.get(t, 0) * tc.get(t, 0)}
        for t in ["pro", "agency"]
    ]

    # Top revenue users (paid with most activity)
    top_users = fetchall("""
        SELECT u.id, u.email, u.tier, u.created_at,
               (SELECT COUNT(*) FROM usage_log ul WHERE ul.user_id = u.id) as total_actions,
               (SELECT COUNT(*) FROM check_history ch WHERE ch.user_id = u.id) as total_checks
        FROM users u
        WHERE u.tier IN ('pro', 'agency')
        ORDER BY total_actions DESC LIMIT 10
    """)

    # Conversion funnel: signups -> verified -> paid
    total = fetchone("SELECT COUNT(*) as cnt FROM users")["cnt"] or 0
    verified = fetchone("SELECT COUNT(*) as cnt FROM users WHERE email_verified = 1")["cnt"] or 0
    paid = paid_users

    return jsonify({
        "mrr": mrr,
        "mrr_trend": mrr_trend,
        "arpu": arpu,
        "arpu_paid": arpu_paid,
        "paid_users": paid_users,
        "churn_risk": churned["cnt"] if churned else 0,
        "revenue_by_tier": revenue_by_tier,
        "top_users": top_users,
        "funnel": {"total": total, "verified": verified, "paid": paid},
        "tier_counts": tc,
    })


# ══════════════════════════════════════════════════════
#  ADMIN -- CONVERSION DRIVERS
# ══════════════════════════════════════════════════════

@admin_bp.route("/admin/api/conversion-funnel")
def admin_api_conversion_funnel():
    """Which tools do free users use before upgrading to paid?"""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchall

    # 1. Pre-upgrade tool usage: tools free users used BEFORE upgrading to paid.
    #    We identify upgraded users as those currently on a paid tier whose
    #    updated_at differs from created_at (i.e. their tier was changed).
    #    We then look at their usage_log entries from before the upgrade date.
    pre_upgrade = fetchall("""
        SELECT ul.action,
               COUNT(DISTINCT ul.user_id) AS converted_users,
               COUNT(*) AS total_uses
        FROM usage_log ul
        JOIN users u ON u.id = ul.user_id
        WHERE u.tier IN ('pro', 'agency')
          AND u.updated_at != u.created_at
          AND ul.created_at < u.updated_at
          AND ul.created_at > datetime(u.updated_at, '-30 days')
        GROUP BY ul.action
        ORDER BY converted_users DESC, total_uses DESC
    """)

    # 2. Paid-user retention signals: which tools do paid users use most (last 30 days)?
    paid_usage = fetchall("""
        SELECT ul.action,
               COUNT(DISTINCT ul.user_id) AS active_paid_users,
               COUNT(*) AS total_uses
        FROM usage_log ul
        JOIN users u ON u.id = ul.user_id
        WHERE u.tier IN ('pro', 'agency')
          AND ul.created_at > datetime('now', '-30 days')
        GROUP BY ul.action
        ORDER BY active_paid_users DESC, total_uses DESC
    """)

    # 3. Summary stats
    total_converted = fetchall("""
        SELECT COUNT(*) as cnt FROM users
        WHERE tier IN ('pro', 'agency') AND updated_at != created_at
    """)
    converted_count = total_converted[0]["cnt"] if total_converted else 0

    return jsonify({
        "pre_upgrade_tools": pre_upgrade,
        "paid_retention_tools": paid_usage,
        "total_converted_users": converted_count,
    })


# ══════════════════════════════════════════════════════
#  ADMIN -- USER SEGMENTS
# ══════════════════════════════════════════════════════

@admin_bp.route("/admin/segments")
def admin_segments():
    if not _is_admin():
        return redirect("/admin/login")
    return render_template("admin_segments.html", is_admin=True, active_page="admin_segments")


@admin_bp.route("/admin/api/segments")
def admin_api_segments():
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchall

    # Power free users (free tier, 50+ actions total)
    power_free = fetchall("""
        SELECT u.id, u.email, u.tier, u.created_at,
               COUNT(ul.id) as total_actions,
               MAX(ul.created_at) as last_active
        FROM users u
        JOIN usage_log ul ON ul.user_id = u.id
        WHERE u.tier = 'free'
        GROUP BY u.id
        HAVING total_actions >= 50
        ORDER BY total_actions DESC
    """)

    # At-risk paid (paid but < 5 actions in last 30 days)
    at_risk = fetchall("""
        SELECT u.id, u.email, u.tier, u.created_at,
               COALESCE(recent.cnt, 0) as recent_actions,
               (SELECT MAX(created_at) FROM usage_log ul2 WHERE ul2.user_id = u.id) as last_active
        FROM users u
        LEFT JOIN (
            SELECT user_id, COUNT(*) as cnt FROM usage_log
            WHERE created_at > datetime('now', '-30 days')
            GROUP BY user_id
        ) recent ON recent.user_id = u.id
        WHERE u.tier IN ('pro', 'agency')
        AND COALESCE(recent.cnt, 0) < 5
        ORDER BY recent_actions ASC
    """)

    # Active users (any action in last 7 days)
    active_7d = fetchall("""
        SELECT u.id, u.email, u.tier,
               COUNT(ul.id) as week_actions
        FROM users u
        JOIN usage_log ul ON ul.user_id = u.id AND ul.created_at > datetime('now', '-7 days')
        GROUP BY u.id
        ORDER BY week_actions DESC
        LIMIT 50
    """)

    # Dormant (no activity in 30+ days, has at least 1 action ever)
    dormant = fetchall("""
        SELECT u.id, u.email, u.tier, u.created_at,
               MAX(ul.created_at) as last_active,
               COUNT(ul.id) as total_actions
        FROM users u
        JOIN usage_log ul ON ul.user_id = u.id
        GROUP BY u.id
        HAVING last_active < datetime('now', '-30 days')
        ORDER BY last_active DESC
        LIMIT 50
    """)

    # New users (signed up in last 7 days)
    new_users = fetchall("""
        SELECT u.id, u.email, u.tier, u.email_verified, u.created_at,
               (SELECT COUNT(*) FROM usage_log ul WHERE ul.user_id = u.id) as total_actions
        FROM users u
        WHERE u.created_at > datetime('now', '-7 days')
        ORDER BY u.created_at DESC
    """)

    # Never used (signed up but 0 actions)
    never_used = fetchall("""
        SELECT u.id, u.email, u.tier, u.email_verified, u.created_at
        FROM users u
        LEFT JOIN usage_log ul ON ul.user_id = u.id
        WHERE ul.id IS NULL
        ORDER BY u.created_at DESC
        LIMIT 50
    """)

    return jsonify({
        "power_free": power_free,
        "at_risk": at_risk,
        "active_7d": active_7d,
        "dormant": dormant,
        "new_users": new_users,
        "never_used": never_used,
    })


@admin_bp.route("/admin/api/users/bulk-tier", methods=["POST"])
def admin_api_bulk_tier():
    """Bulk change tier for multiple users."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import execute

    data = request.get_json(silent=True) or {}
    user_ids = data.get("user_ids", [])
    new_tier = data.get("tier", "")
    if new_tier not in ("free", "pro", "agency", "api"):
        return jsonify({"error": "Invalid tier"}), 400
    if not user_ids or not isinstance(user_ids, list):
        return jsonify({"error": "No users selected"}), 400

    placeholders = ",".join("?" for _ in user_ids)
    execute(
        f"UPDATE users SET tier = ?, updated_at = datetime('now') WHERE id IN ({placeholders})",
        (new_tier, *user_ids),
    )
    return jsonify({"ok": True, "updated": len(user_ids)})


# ══════════════════════════════════════════════════════
#  ADMIN -- SUSPEND / REACTIVATE / FLAGS
# ══════════════════════════════════════════════════════

@admin_bp.route("/admin/api/users/<int:user_id>/suspend", methods=["POST"])
def admin_api_suspend_user(user_id):
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    from modules.database import execute, fetchone
    user = fetchone("SELECT id FROM users WHERE id = ?", (user_id,))
    if not user:
        return jsonify({"error": "User not found"}), 404
    execute("UPDATE users SET status = 'suspended', suspended_at = datetime('now'), updated_at = datetime('now') WHERE id = ?", (user_id,))
    _log_admin_action("suspend", f"User id={user_id} suspended")
    return jsonify({"ok": True, "status": "suspended"})


@admin_bp.route("/admin/api/users/<int:user_id>/reactivate", methods=["POST"])
def admin_api_reactivate_user(user_id):
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    from modules.database import execute, fetchone
    user = fetchone("SELECT id FROM users WHERE id = ?", (user_id,))
    if not user:
        return jsonify({"error": "User not found"}), 404
    execute("UPDATE users SET status = 'active', suspended_at = NULL, updated_at = datetime('now') WHERE id = ?", (user_id,))
    _log_admin_action("reactivate", f"User id={user_id} reactivated")
    return jsonify({"ok": True, "status": "active"})


@admin_bp.route("/admin/api/users/<int:user_id>/flags", methods=["POST"])
def admin_api_update_flags(user_id):
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    from modules.database import execute, fetchone
    user = fetchone("SELECT id FROM users WHERE id = ?", (user_id,))
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json(silent=True) or {}
    flags = data.get("flags", "")
    execute("UPDATE users SET admin_flags = ?, updated_at = datetime('now') WHERE id = ?", (flags, user_id))
    _log_admin_action("flag_change", f"User id={user_id} flags set to: {flags}")
    return jsonify({"ok": True, "flags": flags})


# ── Admin: Email Users ───────────────────────────────

@admin_bp.route("/admin/api/users/<int:user_id>/email", methods=["POST"])
def admin_api_email_user(user_id):
    """Send an individual email to a user."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    from modules.database import fetchone, execute
    from modules.mailer import send_admin_email, is_configured
    if not is_configured():
        return jsonify({"ok": False, "error": "SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASS env vars."}), 400
    user = fetchone("SELECT id, email FROM users WHERE id = ?", (user_id,))
    if not user:
        return jsonify({"ok": False, "error": "User not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()
    if not subject or not body:
        return jsonify({"ok": False, "error": "Subject and body are required"}), 400
    # Convert newlines to HTML paragraphs
    body_html = "".join(f"<p style='color:#334155;font-size:15px;line-height:1.6;margin:0 0 12px;'>{line}</p>" for line in body.split("\n") if line.strip())
    ok = send_admin_email(user["email"], subject, body_html, body)
    if ok:
        # Log it as admin note
        execute("INSERT INTO admin_notes (user_id, note, tag) VALUES (?, ?, 'general')",
                (user_id, f"[EMAIL SENT] Subject: {subject}"))
        _log_admin_action("email_sent", f"Email to {user['email']} (id={user_id}), subject: {subject}")
    return jsonify({"ok": ok, "error": "" if ok else "Failed to send"})


# ── Bulk email job tracking ───────────────────────────────
_bulk_email_jobs = {}  # job_id -> {status, total, sent, failed}


def _bulk_email_worker(job_id, users, subject, body_html, body_plain):
    """Background worker that sends bulk emails and updates job progress."""
    from modules.database import execute
    from modules.mailer import send_admin_email

    job = _bulk_email_jobs[job_id]
    job["status"] = "running"
    sent = 0
    failed = 0

    for u in users:
        try:
            ok = send_admin_email(u["email"], subject, body_html, body_plain)
        except Exception:
            logger.exception("Failed to send bulk email to %s", u["email"])
            ok = False
        if ok:
            sent += 1
        else:
            failed += 1
        job["sent"] = sent
        job["failed"] = failed

    # Log bulk email
    try:
        execute("INSERT INTO admin_notes (user_id, note, tag) VALUES (1, ?, 'general')",
                (f"[BULK EMAIL] Subject: {subject} | Sent: {sent}, Failed: {failed}, Total: {len(users)}",))
    except Exception:
        logger.exception("Failed to log bulk email admin note")

    job["status"] = "completed"


@admin_bp.route("/admin/api/users/bulk-email/status/<job_id>")
def admin_api_bulk_email_status(job_id):
    """Check the status of a bulk email job."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    job = _bulk_email_jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found"}), 404
    return jsonify({"ok": True, **job})


@admin_bp.route("/admin/api/users/bulk-email", methods=["POST"])
def admin_api_bulk_email():
    """Send bulk email to multiple users by filter or ID list (async)."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    from modules.database import fetchall
    from modules.mailer import is_configured
    if not is_configured():
        return jsonify({"ok": False, "error": "SMTP not configured"}), 400
    data = request.get_json(force=True, silent=True) or {}
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()
    if not subject or not body:
        return jsonify({"ok": False, "error": "Subject and body are required"}), 400

    # Get recipients
    user_ids = data.get("user_ids", [])
    tier_filter = data.get("tier", "")
    segment = data.get("segment", "")

    if user_ids:
        placeholders = ",".join("?" * len(user_ids))
        users = fetchall(f"SELECT id, email FROM users WHERE id IN ({placeholders})", user_ids)
    elif tier_filter:
        users = fetchall("SELECT id, email FROM users WHERE tier = ? AND status != 'suspended'", (tier_filter,))
    elif segment == "verified":
        users = fetchall("SELECT id, email FROM users WHERE email_verified = 1 AND status != 'suspended'")
    elif segment == "unverified":
        users = fetchall("SELECT id, email FROM users WHERE email_verified = 0 AND status != 'suspended'")
    elif segment == "active_7d":
        users = fetchall("""
            SELECT DISTINCT u.id, u.email FROM users u
            JOIN usage_log ul ON ul.user_id = u.id
            WHERE ul.created_at > datetime('now', '-7 days') AND u.status != 'suspended'
        """)
    elif segment == "dormant_30d":
        users = fetchall("""
            SELECT u.id, u.email FROM users u
            WHERE u.status != 'suspended'
            AND u.id NOT IN (
                SELECT DISTINCT user_id FROM usage_log
                WHERE created_at > datetime('now', '-30 days') AND user_id IS NOT NULL
            )
        """)
    elif segment == "all":
        users = fetchall("SELECT id, email FROM users WHERE status != 'suspended'")
    else:
        return jsonify({"ok": False, "error": "Specify user_ids, tier, or segment"}), 400

    if not users:
        return jsonify({"ok": False, "error": "No matching users found"}), 404

    body_html = "".join(
        f"<p style='color:#334155;font-size:15px;line-height:1.6;margin:0 0 12px;'>{line}</p>"
        for line in body.split("\n") if line.strip()
    )

    # Create job and start background thread
    job_id = uuid.uuid4().hex[:12]
    _bulk_email_jobs[job_id] = {
        "status": "queued",
        "total": len(users),
        "sent": 0,
        "failed": 0,
    }

    # Convert sqlite Row objects to plain dicts for use outside request context
    users_list = [{"id": u["id"], "email": u["email"]} for u in users]

    t = threading.Thread(
        target=_bulk_email_worker,
        args=(job_id, users_list, subject, body_html, body),
        daemon=True,
    )
    t.start()

    return jsonify({"ok": True, "job_id": job_id, "status": "queued", "total": len(users)})


# ══════════════════════════════════════════════════════
#  ADMIN -- FEATURE ADOPTION & TEAM ANALYTICS
# ══════════════════════════════════════════════════════

@admin_bp.route("/admin/api/feature-adoption")
def admin_api_feature_adoption():
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchall

    # Feature usage by tier
    by_tier = fetchall("""
        SELECT u.tier, ul.action, COUNT(*) as cnt
        FROM usage_log ul
        JOIN users u ON u.id = ul.user_id
        WHERE ul.created_at > datetime('now', '-30 days')
        GROUP BY u.tier, ul.action
        ORDER BY cnt DESC
    """)

    # Unique users per tool (last 30 days)
    unique_per_tool = fetchall("""
        SELECT action, COUNT(DISTINCT user_id) as unique_users, COUNT(*) as total_uses
        FROM usage_log
        WHERE created_at > datetime('now', '-30 days') AND user_id IS NOT NULL
        GROUP BY action
        ORDER BY unique_users DESC
    """)

    return jsonify({"by_tier": by_tier, "unique_per_tool": unique_per_tool})


@admin_bp.route("/admin/api/team-analytics")
def admin_api_team_analytics():
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchall

    teams = fetchall("""
        SELECT t.id, t.name, t.created_at,
               (SELECT email FROM users WHERE id = t.owner_id) as owner_email,
               (SELECT tier FROM users WHERE id = t.owner_id) as owner_tier,
               (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id = t.id) as member_count,
               (SELECT COUNT(*) FROM team_invites ti WHERE ti.team_id = t.id AND ti.status = 'pending') as pending_invites,
               (SELECT COUNT(*) FROM check_history ch WHERE ch.team_id = t.id) as total_checks
        FROM teams t
        ORDER BY t.created_at DESC
    """)

    # Invite stats
    invite_stats = fetchall("""
        SELECT status, COUNT(*) as cnt FROM team_invites GROUP BY status
    """)

    return jsonify({"teams": teams, "invite_stats": {r["status"]: r["cnt"] for r in invite_stats}})


@admin_bp.route("/admin/api/session-intelligence")
def admin_api_session_intelligence():
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchall, fetchone

    # Active sessions
    active_sessions = fetchone("""
        SELECT COUNT(*) as cnt FROM sessions WHERE expires_at > datetime('now')
    """)

    # Sessions by device (user_agent parsing)
    top_agents = fetchall("""
        SELECT user_agent, COUNT(*) as cnt
        FROM sessions
        WHERE expires_at > datetime('now')
        GROUP BY user_agent
        ORDER BY cnt DESC LIMIT 10
    """)

    # Top IPs with most sessions
    top_ips = fetchall("""
        SELECT ip_address, COUNT(*) as cnt,
               COUNT(DISTINCT user_id) as unique_users
        FROM sessions
        WHERE expires_at > datetime('now')
        GROUP BY ip_address
        ORDER BY cnt DESC LIMIT 15
    """)

    # Users with multiple active sessions
    multi_session = fetchall("""
        SELECT s.user_id, u.email, u.tier, COUNT(*) as session_count
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.expires_at > datetime('now')
        GROUP BY s.user_id
        HAVING session_count > 1
        ORDER BY session_count DESC LIMIT 20
    """)

    # Logins last 24h by hour
    hourly_logins = fetchall("""
        SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt
        FROM sessions
        WHERE created_at > datetime('now', '-1 day')
        GROUP BY hour
        ORDER BY hour
    """)

    return jsonify({
        "active_sessions": active_sessions["cnt"] if active_sessions else 0,
        "top_agents": top_agents,
        "top_ips": top_ips,
        "multi_session": multi_session,
        "hourly_logins": hourly_logins,
    })


# ── Media Library ────────────────────────────────────

@admin_bp.route("/admin/api/media")
def admin_api_media():
    if not _is_admin():
        return jsonify({"ok": False}), 403
    from modules.database import fetchall
    q = request.args.get("q", "").strip()
    if q:
        media = fetchall(
            "SELECT * FROM media_library WHERE filename LIKE ? OR alt_text LIKE ? OR tags LIKE ? ORDER BY created_at DESC",
            (f"%{q}%", f"%{q}%", f"%{q}%")
        )
    else:
        media = fetchall("SELECT * FROM media_library ORDER BY created_at DESC LIMIT 100")
    return jsonify({"ok": True, "media": media})


@admin_bp.route("/admin/api/media/upload", methods=["POST"])
def admin_api_media_upload():
    if not _is_admin():
        return jsonify({"ok": False}), 403
    from modules.database import execute
    import os as _os
    import time as _time
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "No file"}), 400
    # Save uploaded image
    ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    upload_dir = _os.path.join(current_app.root_path, "static", "uploads")
    _os.makedirs(upload_dir, exist_ok=True)
    fname = f.filename or "upload"
    ext = _os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_EXT:
        url = None
    else:
        from werkzeug.utils import secure_filename as _sec_fn
        safe_name = f"{int(_time.time())}_{_sec_fn(fname)}"
        f.save(_os.path.join(upload_dir, safe_name))
        url = f"/static/uploads/{safe_name}"
    if not url:
        return jsonify({"ok": False, "error": "Invalid file type"}), 400
    alt_text = request.form.get("alt_text", "")
    tags = request.form.get("tags", "")
    # Try to get file size
    f.seek(0, 2)
    file_size = f.tell()
    f.seek(0)
    execute(
        "INSERT INTO media_library (filename, url, alt_text, file_size, mime_type, tags) VALUES (?, ?, ?, ?, ?, ?)",
        (f.filename, url, alt_text, file_size, f.content_type or "", tags)
    )
    return jsonify({"ok": True, "url": url, "filename": f.filename})


@admin_bp.route("/admin/api/media/<int:media_id>", methods=["PUT"])
def admin_api_media_update(media_id):
    if not _is_admin():
        return jsonify({"ok": False}), 403
    from modules.database import execute
    data = request.get_json(force=True, silent=True) or {}
    alt_text = data.get("alt_text")
    tags = data.get("tags")
    if alt_text is not None:
        execute("UPDATE media_library SET alt_text = ? WHERE id = ?", (alt_text, media_id))
    if tags is not None:
        execute("UPDATE media_library SET tags = ? WHERE id = ?", (tags, media_id))
    return jsonify({"ok": True})


@admin_bp.route("/admin/api/media/<int:media_id>", methods=["DELETE"])
def admin_api_media_delete(media_id):
    if not _is_admin():
        return jsonify({"ok": False}), 403
    from modules.database import fetchone, execute
    media = fetchone("SELECT url FROM media_library WHERE id = ?", (media_id,))
    if media:
        # Try to delete physical file
        import os as _os
        filepath = _os.path.join(current_app.root_path, media["url"].lstrip("/").replace("/", _os.sep))
        if _os.path.exists(filepath):
            try:
                _os.remove(filepath)
            except OSError:
                logger.exception("Failed to delete media file: %s", filepath)
        execute("DELETE FROM media_library WHERE id = ?", (media_id,))
    return jsonify({"ok": True})


# ── SEO Panel ────────────────────────────────────────

@admin_bp.route("/admin/api/seo/<page_name>")
def admin_api_get_seo(page_name):
    if not _is_admin():
        return jsonify({"ok": False}), 403
    page_name = _resolve_page_name(page_name)
    from modules.database import fetchone
    seo = fetchone("SELECT * FROM page_seo WHERE page_name = ?", (page_name,))
    return jsonify({"ok": True, "seo": seo})


@admin_bp.route("/admin/api/seo/<page_name>", methods=["POST"])
def admin_api_save_seo(page_name):
    if not _is_admin():
        return jsonify({"ok": False}), 403
    page_name = _resolve_page_name(page_name)
    from modules.database import execute, fetchone
    data = request.get_json(force=True, silent=True) or {}
    fields = ["meta_title", "meta_description", "og_title", "og_description",
              "og_image", "canonical_url", "noindex", "json_ld"]
    existing = fetchone("SELECT page_name FROM page_seo WHERE page_name = ?", (page_name,))
    if existing:
        sets = []
        params = []
        for f in fields:
            if f in data:
                sets.append(f"{f} = ?")
                params.append(data[f])
        if sets:
            sets.append("updated_at = datetime('now')")
            params.append(page_name)
            execute(f"UPDATE page_seo SET {', '.join(sets)} WHERE page_name = ?", params)
    else:
        vals = {f: data.get(f, "") for f in fields}
        vals["noindex"] = data.get("noindex", 0)
        execute(
            "INSERT INTO page_seo (page_name, meta_title, meta_description, og_title, og_description, og_image, canonical_url, noindex, json_ld) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (page_name, vals["meta_title"], vals["meta_description"], vals["og_title"],
             vals["og_description"], vals["og_image"], vals["canonical_url"], vals["noindex"], vals["json_ld"])
        )
    return jsonify({"ok": True})


# ── Page Analytics ───────────────────────────────────

@admin_bp.route("/admin/api/page-analytics/<page_name>")
def admin_api_page_analytics(page_name):
    if not _is_admin():
        return jsonify({"ok": False}), 403
    page_name = _resolve_page_name(page_name)
    from modules.database import fetchone, fetchall
    total = fetchone("SELECT COUNT(*) as cnt FROM page_views WHERE page_name = ?", (page_name,))
    today = fetchone("SELECT COUNT(*) as cnt FROM page_views WHERE page_name = ? AND created_at > datetime('now', '-1 day')", (page_name,))
    week = fetchone("SELECT COUNT(*) as cnt FROM page_views WHERE page_name = ? AND created_at > datetime('now', '-7 days')", (page_name,))
    daily = fetchall("""
        SELECT date(created_at) as day, COUNT(*) as cnt
        FROM page_views WHERE page_name = ? AND created_at > datetime('now', '-30 days')
        GROUP BY day ORDER BY day
    """, (page_name,))
    referrers = fetchall("""
        SELECT referrer, COUNT(*) as cnt
        FROM page_views WHERE page_name = ? AND referrer IS NOT NULL AND referrer != ''
        GROUP BY referrer ORDER BY cnt DESC LIMIT 10
    """, (page_name,))
    return jsonify({
        "ok": True,
        "total": total["cnt"] if total else 0,
        "today": today["cnt"] if today else 0,
        "week": week["cnt"] if week else 0,
        "daily": daily,
        "referrers": referrers,
    })


# ── Site Settings (Tracking Tags, Design Tokens) ────

@admin_bp.route("/admin/api/site-settings")
def admin_api_get_settings():
    if not _is_admin():
        return jsonify({"ok": False}), 403
    from modules.database import fetchall
    settings = fetchall("SELECT key, value FROM site_settings")
    return jsonify({"ok": True, "settings": {s["key"]: s["value"] for s in settings}})


@admin_bp.route("/admin/api/site-settings", methods=["POST"])
def admin_api_save_settings():
    if not _is_admin():
        return jsonify({"ok": False}), 403
    from modules.database import execute, fetchone
    data = request.get_json(force=True, silent=True) or {}
    for key, value in data.items():
        existing = fetchone("SELECT key FROM site_settings WHERE key = ?", (key,))
        if existing:
            execute("UPDATE site_settings SET value = ?, updated_at = datetime('now') WHERE key = ?", (value, key))
        else:
            execute("INSERT INTO site_settings (key, value) VALUES (?, ?)", (key, value))
    _invalidate_tracking_tags_cache()
    return jsonify({"ok": True})


@admin_bp.route("/admin/settings")
def admin_settings():
    if not _is_admin():
        return redirect("/admin/login")
    return render_template("admin_settings.html", is_admin=True, active_page="admin_settings")


# ── Admin: AppSumo LTD ───────────────────────────────────


@admin_bp.route("/admin/appsumo")
def admin_appsumo():
    """Admin panel for AppSumo LTD code management.
    Shows redemption stats, tier distribution, and a bulk import form."""
    if not _is_admin():
        return redirect("/admin/login")

    from modules.database import fetchone as _fo, fetchall as _fa

    stats_row = _fo(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN redeemed_by_user_id IS NOT NULL THEN 1 ELSE 0 END), 0) AS redeemed, "
        "COALESCE(SUM(CASE WHEN redeemed_by_user_id IS NULL THEN 1 ELSE 0 END), 0) AS available "
        "FROM appsumo_codes",
        (),
    )

    tier_dist = _fa(
        "SELECT toolkit_tier_level AS level, COUNT(*) AS n "
        "FROM users WHERE toolkit_tier_level > 0 GROUP BY toolkit_tier_level",
        (),
    )

    # LTD -> MRR upgrade funnel (users who have both toolkit + intelligence)
    bridge_row = _fo(
        "SELECT COUNT(*) AS n FROM users "
        "WHERE toolkit_ok = 1 AND intelligence_ok = 1",
        (),
    )

    recent_redemptions = _fa(
        "SELECT ac.code, ac.batch_label, ac.redeemed_at, u.email "
        "FROM appsumo_codes ac "
        "LEFT JOIN users u ON u.id = ac.redeemed_by_user_id "
        "WHERE ac.redeemed_by_user_id IS NOT NULL "
        "ORDER BY ac.redeemed_at DESC LIMIT 20",
        (),
    )

    return render_template(
        "admin_appsumo.html",
        is_admin=True,
        active_page="admin_appsumo",
        stats={
            "total": stats_row.get("total", 0) if stats_row else 0,
            "redeemed": stats_row.get("redeemed", 0) if stats_row else 0,
            "available": stats_row.get("available", 0) if stats_row else 0,
        },
        tier_distribution={row["level"]: row["n"] for row in tier_dist},
        bridge_users=bridge_row.get("n", 0) if bridge_row else 0,
        recent_redemptions=recent_redemptions,
    )


@admin_bp.route("/admin/appsumo/import", methods=["POST"])
def admin_appsumo_import():
    """Bulk import AppSumo codes. Accepts one code per line in a
    textarea field or a CSV upload. Skips duplicates silently via
    INSERT OR IGNORE."""
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    from modules.database import execute as _ex

    codes_text = request.form.get("codes", "").strip()
    batch_label = (request.form.get("batch_label") or "manual_import").strip()[:64]

    if not codes_text:
        return jsonify({"ok": False, "error": "No codes provided."}), 400

    # Split on newlines and commas, normalize each code
    raw_codes = []
    for line in codes_text.splitlines():
        for piece in line.split(","):
            piece = piece.strip().upper()
            if piece and len(piece) >= 6:
                raw_codes.append(piece)

    imported = 0
    for code in raw_codes:
        try:
            _ex(
                "INSERT OR IGNORE INTO appsumo_codes (code, batch_label) VALUES (?, ?)",
                (code, batch_label),
            )
            imported += 1
        except Exception:
            pass

    return jsonify({
        "ok": True,
        "imported": imported,
        "total_received": len(raw_codes),
    })


def _invalidate_tracking_tags_cache():
    """Invalidate tracking tags cache in the main app module."""
    try:
        from app import _tracking_tags_cache
        _tracking_tags_cache["ts"] = 0
    except ImportError:
        pass
