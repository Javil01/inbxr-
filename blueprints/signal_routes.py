"""
InbXr — Signal Intelligence Blueprint

All routes for the 7 Inbox Signals system:
- /signal-score            Signal Score Dashboard (primary)
- /signal-score/calculate  Trigger a manual calculation
- /signal-score/from-csv   Upload CSV for free-tier reading
- /signal-score/history    Historical trend data
- /signal-map              Contact segment visualization
- /signal-alerts           Early Warning + Signal Rule alerts
- /signal-alerts/<id>/dismiss
- /signal-rules            Rule CRUD + preview + toggle
- /signal-rules/<id>/preview  Dry-run
- /signal-rules/<id>/toggle   Enable/disable
- /signal-rules/<id>/flip-dry-run
- /signal-rules/<id>/delete
- /send-readiness          Pre-campaign gate
- /recovery-sequences      AI re-engagement sequence generator (stub for now)

Reference: SIGNAL_SPEC.md Phase 3 + Phase 4.

All routes use raw SQLite + session auth (not SQLAlchemy + Flask-Login).
"""

import json
import logging

from flask import Blueprint, render_template, request, jsonify, Response

from modules.auth import login_required, tier_required, get_current_user
from modules.database import execute, fetchone, fetchall
from modules.tiers import has_feature, get_tier_limit
from modules.signal_copy import (
    SIGNAL_DIMENSION_COPY,
    SIGNAL_GRADE_COPY,
    ACTION_RECOMMENDATIONS,
    PRE_BUILT_RULE_TEMPLATES,
    SEGMENT_LABELS,
    TRAJECTORY_DIRECTION_LABELS,
    TRAJECTORY_DIRECTION_MESSAGES,
    MPP_ACCURACY_LABELS,
    FREE_TIER_LOCKED_SIGNALS,
    get_homepage_signal_pills,
)
from modules.signal_score import (
    calculate_signal_score,
    calculate_signal_score_from_csv,
    calculate_domain_signal_score,
    save_signal_score,
    get_latest_signal_score,
    get_signal_history,
    make_share_token,
    parse_share_token,
    get_signal_score_by_id,
)
from modules.signal_rules import (
    preview_signal_rule,
    create_rule_from_template,
    create_custom_rule,
    toggle_rule,
    flip_dry_run,
    delete_rule,
    get_user_rules,
    get_rule_log,
)
from modules.signal_alerts import (
    get_signal_alerts,
    dismiss_alert,
    get_unread_signal_alert_count,
)

logger = logging.getLogger("inbxr.signal_routes")

signal_bp = Blueprint("signal", __name__)


# ── Helper: weakest signal identification ─────────────

def _weakest_signal(latest_score):
    """Return the tuple (dimension_key, score_value, weight) of the weakest signal."""
    if not latest_score:
        return None

    signals = {
        'bounce_exposure': (latest_score.get('bounce_exposure_score', 0), 25),
        'engagement_trajectory': (latest_score.get('engagement_trajectory_score', 0), 25),
        'acquisition_quality': (latest_score.get('acquisition_quality_score', 0), 15),
        'domain_reputation': (latest_score.get('domain_reputation_score', 0), 15),
        'dormancy_risk': (latest_score.get('dormancy_risk_score', 0), 10),
        'authentication_standing': (latest_score.get('authentication_standing_score', 0), 5),
        'decay_velocity': (latest_score.get('decay_velocity_score', 0), 5),
    }

    # Filter out locked signals for free tier
    tier = latest_score.get('tier_at_calculation', 'pro')
    if tier == 'free':
        for s in FREE_TIER_LOCKED_SIGNALS:
            signals.pop(s, None)

    weakest_key = min(signals.keys(), key=lambda k: (signals[k][0] / signals[k][1]) if signals[k][1] else 1)
    return (weakest_key, signals[weakest_key][0], signals[weakest_key][1])


# ── Dashboard ──────────────────────────────────────────

@signal_bp.route("/signal-score")
def signal_score_dashboard():
    """
    Signal Score Dashboard — main 7-signal visualization page.

    PUBLIC ROUTE. Anonymous visitors see the educational empty state +
    a working CSV upload path (the result renders inline without
    requiring signup). This is the single most important marketing
    surface — every pillar post, ad, and cold-outreach link funnels here.
    """
    user = get_current_user()

    # Anonymous visitor: render the empty/educational state.
    if not user:
        return render_template(
            "signal/dashboard.html",
            active_page="signal_score",
            latest=None,
            history=[],
            weakest=None,
            weakest_name=None,
            weakest_action=None,
            alerts=[],
            unread_alert_count=0,
            signal_dimensions=SIGNAL_DIMENSION_COPY,
            grade_copy=SIGNAL_GRADE_COPY,
            segment_labels=SEGMENT_LABELS,
            mpp_labels=MPP_ACCURACY_LABELS,
            trajectory_labels=TRAJECTORY_DIRECTION_LABELS,
            trajectory_messages=TRAJECTORY_DIRECTION_MESSAGES,
            free_tier_locked=list(FREE_TIER_LOCKED_SIGNALS),
            tier="anon",
            is_anonymous=True,
            allow_index=True,
            title="Free Signal Score — The 7 Inbox Signals",
        )

    user_id = user["id"]
    tier = user.get("tier", "free")

    latest = get_latest_signal_score(user_id, esp_integration_id=None)
    # Also try per-integration (for users with connected ESP)
    if not latest:
        integration_latest = fetchone(
            """SELECT * FROM signal_scores
               WHERE user_id = ? AND esp_integration_id IS NOT NULL
               ORDER BY calculated_at DESC LIMIT 1""",
            (user_id,),
        )
        if integration_latest:
            latest = integration_latest

    history = []
    weakest = None
    weakest_action = None
    weakest_name = None

    if latest:
        history = get_signal_history(user_id, latest.get("esp_integration_id"), limit=30)
        weakest = _weakest_signal(latest)
        if weakest:
            weakest_name = SIGNAL_DIMENSION_COPY.get(weakest[0], {}).get("name", weakest[0])
            weakest_action = ACTION_RECOMMENDATIONS.get(weakest[0])

    alerts = get_signal_alerts(user_id, limit=10)
    unread_alert_count = get_unread_signal_alert_count(user_id)

    return render_template(
        "signal/dashboard.html",
        active_page="signal_score",
        latest=latest,
        history=history,
        weakest=weakest,
        weakest_name=weakest_name,
        weakest_action=weakest_action,
        alerts=alerts,
        unread_alert_count=unread_alert_count,
        signal_dimensions=SIGNAL_DIMENSION_COPY,
        grade_copy=SIGNAL_GRADE_COPY,
        segment_labels=SEGMENT_LABELS,
        mpp_labels=MPP_ACCURACY_LABELS,
        trajectory_labels=TRAJECTORY_DIRECTION_LABELS,
        trajectory_messages=TRAJECTORY_DIRECTION_MESSAGES,
        free_tier_locked=list(FREE_TIER_LOCKED_SIGNALS),
        tier=tier,
        is_anonymous=False,
        allow_index=True,
        title="Signal Score",
    )


@signal_bp.route("/signal-score/calculate", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def calculate_signal_score_now():
    """
    Manually trigger a Signal Score recalculation.
    Requires a connected ESP — users without one should use the CSV upload path.
    """
    from modules.esp_contact_sync import get_contacts_for_signal_score
    from modules.scheduler import _get_auth_data_for_user

    user = get_current_user()
    user_id = user["id"]
    tier = user.get("tier", "pro")

    # Find first active integration
    integration = fetchone(
        """SELECT id, provider FROM esp_integrations
           WHERE user_id = ? AND status = 'active'
           ORDER BY created_at LIMIT 1""",
        (user_id,),
    )

    if not integration:
        return jsonify({
            "ok": False,
            "error": "No active ESP connected. Connect an ESP or upload a CSV.",
        }), 400

    integration_id = integration["id"]
    provider = integration["provider"]

    # Fetch existing contact data (assumes periodic sync has run at least once)
    contacts = get_contacts_for_signal_score(user_id, integration_id, limit=50000)
    auth_data = _get_auth_data_for_user(user_id)

    result = calculate_signal_score(
        user_id=user_id,
        esp_integration_id=integration_id,
        contact_data=contacts,
        auth_data=auth_data,
        esp_type=provider,
        tier=tier,
    )
    save_signal_score(user_id, integration_id, result)

    # Run Early Warning + Signal Rules
    from modules.signal_alerts import check_early_warning_conditions
    from modules.signal_rules import execute_signal_rules
    check_early_warning_conditions(user_id, result)
    execute_signal_rules(user_id, integration_id, result, contacts)

    return jsonify({
        "ok": True,
        "score": result["total_signal_score"],
        "grade": result["signal_grade"],
        "trajectory": result["trajectory_direction"],
        "total_contacts": result["segments"]["total"],
    })


@signal_bp.route("/signal-score/from-domain", methods=["POST"])
def calculate_signal_score_from_domain():
    """
    Calculate a partial Signal Score from a domain alone.

    PUBLIC ENDPOINT. The lowest-friction Signal Score entry point. Anonymous
    visitors type a domain, get back 2 of 7 signals (Authentication Standing
    + Domain Reputation) calculated from public DNS data. The other 5 signals
    require list data and return as locked cards in the UI.

    Accepts JSON {domain: "example.com"} or form data {domain: "..."}.

    Returns the same result dict shape as /signal-score/from-csv with:
      - is_partial: True
      - visible_signals: 2 / locked_signals: 5
      - 2 visible signal scores filled in
      - 5 locked signal scores set to None
    """
    # Accept both JSON and form-encoded
    if request.is_json:
        data = request.get_json(silent=True) or {}
        domain = data.get("domain", "")
    else:
        domain = request.form.get("domain", "") or request.values.get("domain", "")

    if not domain:
        return jsonify({"ok": False, "error": "Domain is required."}), 400

    result = calculate_domain_signal_score(domain)

    if result.get("error"):
        return jsonify({
            "ok": False,
            "error": result.get("message", result.get("error")),
        }), 400

    return jsonify({
        "ok": True,
        "is_partial": True,
        "is_anonymous": True,
        "domain": result["domain"],
        "score": result["total_signal_score"],
        "grade": result["signal_grade"],
        "visible_signals": result["visible_signals"],
        "locked_signals": result["locked_signals"],
        "scores": result["scores"],
        "metadata": result["metadata"],
        "recommendations": result.get("recommendations", []),
    })


@signal_bp.route("/signal-score/from-csv", methods=["POST"])
def calculate_signal_score_csv():
    """
    Calculate a Signal Score from an uploaded CSV file.

    PUBLIC ENDPOINT. Anonymous visitors get a full 7-signal reading
    without signup — the result returns inline as JSON for the dashboard
    to render. Saving the result to history / scheduling recalculation /
    connecting an ESP all require signup (email-gate on the result card).

    Authenticated users: result is saved to signal_scores + history and
    the JSON response includes the same result payload.
    """
    user = get_current_user()
    is_anonymous = user is None

    if is_anonymous:
        user_id = None
        tier = "free"
    else:
        user_id = user["id"]
        tier = user.get("tier", "free")

        if not has_feature(tier, "signal_csv_upload"):
            return jsonify({"ok": False, "error": "CSV upload not available on your tier"}), 403

    if "csv_file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400

    f = request.files["csv_file"]
    try:
        csv_content = f.read().decode("utf-8")
    except UnicodeDecodeError:
        try:
            f.seek(0)
            csv_content = f.read().decode("latin-1")
        except Exception:
            return jsonify({"ok": False, "error": "Could not decode CSV file. Use UTF-8."}), 400

    # Anonymous visitors skip auth data lookup (no user -> no DNS monitor data)
    auth_data = None
    if not is_anonymous:
        from modules.scheduler import _get_auth_data_for_user
        auth_data = _get_auth_data_for_user(user_id)

    result = calculate_signal_score_from_csv(
        user_id=user_id,
        csv_content=csv_content,
        auth_data=auth_data,
        tier=tier,
    )

    if result.get("error"):
        return jsonify({"ok": False, "error": result.get("message", "CSV parse error")}), 400

    # Only persist for authenticated users. Anonymous results are one-shot.
    if not is_anonymous:
        save_signal_score(user_id, None, result)

    # Full payload so the dashboard can render inline for both anon + auth.
    # Includes per-signal scores and metadata for the 7-signal cards.
    return jsonify({
        "ok": True,
        "is_anonymous": is_anonymous,
        "score": result["total_signal_score"],
        "grade": result["signal_grade"],
        "rows_parsed": result["rows_parsed"],
        "rows_skipped": result["rows_skipped"],
        "total_contacts": result["segments"]["total"],
        "scores": result.get("scores", {}),
        "metadata": result.get("metadata", {}),
        "segments": result.get("segments", {}),
        "trajectory_direction": result.get("trajectory_direction"),
        "mpp_accuracy": result.get("mpp_accuracy"),
    })


# ── Public share URL ──────────────────────────────────
#
# Read-only share of a saved Signal Score report. Token is HMAC-signed
# against the app SECRET_KEY so visitors can't enumerate other users'
# reports by incrementing an id. No auth required.

@signal_bp.route("/signal-score/public/<token>")
def signal_score_public(token):
    """Public read-only Signal Score report by tamper-proof share token."""
    row_id = parse_share_token(token)
    if not row_id:
        return render_template(
            "signal/public_share.html",
            row=None,
            error="invalid_token",
            signal_dimensions=SIGNAL_DIMENSION_COPY,
            grade_copy=SIGNAL_GRADE_COPY,
            allow_index=False,
            title="Signal Score Report",
        ), 404

    row = get_signal_score_by_id(row_id)
    if not row:
        return render_template(
            "signal/public_share.html",
            row=None,
            scores={},
            error="not_found",
            signal_dimensions=SIGNAL_DIMENSION_COPY,
            grade_copy=SIGNAL_GRADE_COPY,
            allow_index=False,
            title="Signal Score Report",
        ), 404

    # Pre-parse the scores_json so the template doesn't need a custom filter
    scores = {}
    raw_scores = row.get("scores_json") if hasattr(row, "get") else row["scores_json"]
    if raw_scores:
        try:
            scores = json.loads(raw_scores) if isinstance(raw_scores, str) else raw_scores
        except (ValueError, TypeError):
            scores = {}

    return render_template(
        "signal/public_share.html",
        row=row,
        scores=scores,
        error=None,
        signal_dimensions=SIGNAL_DIMENSION_COPY,
        grade_copy=SIGNAL_GRADE_COPY,
        trajectory_labels=TRAJECTORY_DIRECTION_LABELS,
        allow_index=False,
        title="Signal Score Report",
    )


@signal_bp.route("/signal-score/<int:row_id>/share-token")
@login_required
def signal_score_share_token(row_id):
    """Return the share token URL for a saved Signal Score row (auth-only)."""
    user = get_current_user()
    row = fetchone(
        "SELECT id, user_id FROM signal_scores WHERE id = ?",
        (row_id,),
    )
    if not row or row["user_id"] != user["id"]:
        return jsonify({"ok": False, "error": "not_found"}), 404

    token = make_share_token(row_id)
    return jsonify({
        "ok": True,
        "token": token,
        "url": f"/signal-score/public/{token}",
    })


@signal_bp.route("/clients")
@login_required
@tier_required("agency", "api")
def agency_clients_page():
    """Multi-client dashboard for Agency tier. Lists all clients the
    agency tracks, with a live Signal Score card per client pulled from
    the domain_leaderboard cache. Agencies add clients via the form and
    re-score on demand."""
    user = get_current_user()
    clients = fetchall(
        """SELECT ac.id, ac.client_name, ac.domain, ac.contact_email, ac.notes,
                  ac.created_at, dl.total_score, dl.grade, dl.last_scanned_at
           FROM agency_clients ac
           LEFT JOIN domain_leaderboard dl ON dl.domain = ac.domain
           WHERE ac.agency_user_id = ?
           ORDER BY ac.client_name""",
        (user["id"],),
    )
    return render_template(
        "signal/agency_clients.html",
        active_page="clients",
        clients=clients,
        title="Multi-client dashboard",
    )


@signal_bp.route("/clients/add", methods=["POST"])
@login_required
@tier_required("agency", "api")
def agency_clients_add():
    """Add a new client to the agency's dashboard. Requires client_name
    and domain. Scoring happens in the background by calling the
    Domain Signal Score engine immediately so the card renders with
    real data right away."""
    user = get_current_user()
    data = request.get_json(silent=True) or request.form.to_dict()
    client_name = (data.get("client_name") or "").strip()
    domain = (data.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    contact_email = (data.get("contact_email") or "").strip()
    notes = (data.get("notes") or "").strip()[:500]

    if not client_name or not domain or "." not in domain:
        return jsonify({"ok": False, "error": "Client name and domain are required."}), 400

    try:
        execute(
            """INSERT INTO agency_clients
                (agency_user_id, client_name, domain, contact_email, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (user["id"], client_name, domain, contact_email, notes),
        )
    except Exception:
        return jsonify({"ok": False, "error": "A client with that domain already exists."}), 400

    # Trigger a fresh score so the card has data immediately
    try:
        calculate_domain_signal_score(domain)
    except Exception:
        logger.exception("[AGENCY_CLIENTS] initial score failed for %s", domain)

    return jsonify({"ok": True})


@signal_bp.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
@tier_required("agency", "api")
def agency_clients_delete(client_id):
    """Remove a client from the dashboard. Does not affect
    domain_leaderboard (that's public shared data)."""
    user = get_current_user()
    execute(
        "DELETE FROM agency_clients WHERE id = ? AND agency_user_id = ?",
        (client_id, user["id"]),
    )
    return jsonify({"ok": True})


@signal_bp.route("/clients/<int:client_id>/rescore", methods=["POST"])
@login_required
@tier_required("agency", "api")
def agency_clients_rescore(client_id):
    """Re-run the Domain Signal Score for a specific client's domain.
    Used when the agency has just deployed a DNS fix and wants to see
    the updated score immediately rather than waiting for the next
    user-initiated scan."""
    user = get_current_user()
    row = fetchone(
        "SELECT domain FROM agency_clients WHERE id = ? AND agency_user_id = ?",
        (client_id, user["id"]),
    )
    if not row:
        return jsonify({"ok": False, "error": "Client not found."}), 404

    try:
        result = calculate_domain_signal_score(row["domain"])
    except Exception:
        logger.exception("[AGENCY_CLIENTS] rescore failed")
        return jsonify({"ok": False, "error": "Rescore failed."}), 500

    return jsonify({
        "ok": True,
        "domain": row["domain"],
        "score": result.get("total_signal_score"),
        "grade": result.get("signal_grade"),
    })


@signal_bp.route("/bulk-triage")
@login_required
@tier_required("agency", "api")
def bulk_triage_page():
    """Bulk list grading UI for Agency tier. Users upload multiple CSVs
    in one session; each is triaged and shown in a dashboard table.
    Results are held in the session (not persisted) so the user can
    review + download without us storing client list data."""
    from flask import session
    results = session.get("_bulk_triage_results") or []
    return render_template(
        "signal/bulk_triage.html",
        active_page="bulk_triage",
        results=results,
        title="Bulk List Grading",
    )


@signal_bp.route("/bulk-triage/upload", methods=["POST"])
@login_required
@tier_required("agency", "api")
def bulk_triage_upload():
    """Accept one CSV, triage it, append to the session bulk results."""
    from modules.list_triage import triage_list
    from flask import session

    upload = request.files.get("file") if request.files else None
    if not upload or not upload.filename:
        return jsonify({"ok": False, "error": "No file uploaded."}), 400

    raw = upload.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        return jsonify({"ok": False, "error": "File too large. Max 5 MB per list."}), 400

    try:
        csv_content = raw.decode("utf-8", errors="replace")
    except Exception:
        return jsonify({"ok": False, "error": "Could not decode CSV."}), 400

    result = triage_list(csv_content)
    if not result.get("ok"):
        return jsonify(result), 400

    # Slim down for session storage — drop the full buckets, keep counts + summaries
    slim = {
        "filename": upload.filename,
        "total_parsed": result.get("total_parsed"),
        "counts": result.get("counts"),
        "percentages": result.get("percentages"),
        "summaries": result.get("summaries"),
        "severity": "danger" if result["percentages"]["remove"] > 40 else (
            "warning" if result["percentages"]["remove"] > 20 else "good"
        ),
    }

    existing = session.get("_bulk_triage_results") or []
    existing.insert(0, slim)
    existing = existing[:50]  # cap at 50 lists per session
    session["_bulk_triage_results"] = existing

    return jsonify({"ok": True, "result": slim, "total_lists": len(existing)})


@signal_bp.route("/bulk-triage/clear", methods=["POST"])
@login_required
@tier_required("agency", "api")
def bulk_triage_clear():
    """Clear the session's bulk triage results."""
    from flask import session
    session.pop("_bulk_triage_results", None)
    return jsonify({"ok": True})


@signal_bp.route("/signal-score/pdf")
@login_required
def signal_score_pdf():
    """Generate and stream a Signal Report PDF for the current user.

    Variant is resolved from the user's tier: free users get the basic
    one-page report with InbXr branding, pro users get history charts,
    agency users get white-label output. Daily rate limit enforced via
    signal_pdfs_per_day in tiers.py. Every generation is logged to
    pdf_generations for success-metric tracking.
    """
    from modules.signal_report_pdf import (
        generate_pdf,
        log_pdf_generation,
        count_pdfs_today,
    )

    user = get_current_user()
    user_id = user["id"]
    tier = user.get("tier", "free")

    # Rate limit check
    daily_limit = get_tier_limit(tier, "signal_pdfs_per_day") or 0
    if daily_limit <= 0:
        return jsonify({
            "ok": False,
            "error": "PDF export is not available on your plan.",
            "upgrade_url": "/pricing",
        }), 403

    used_today = count_pdfs_today(user_id)
    if used_today >= daily_limit:
        return jsonify({
            "ok": False,
            "error": f"Daily PDF limit reached ({daily_limit}/day on {tier}).",
            "upgrade_url": "/pricing",
        }), 429

    # Generate
    pdf_bytes, meta = generate_pdf(user_id)
    if pdf_bytes is None:
        reason = meta.get("error", "unknown")
        if reason == "no_score_yet":
            return jsonify({
                "ok": False,
                "error": "Run your first Signal Score before exporting a PDF.",
            }), 400
        return jsonify({"ok": False, "error": f"PDF generation failed ({reason})."}), 500

    # Log the generation (non-blocking: failure to log should not block the download)
    log_pdf_generation(
        user_id=user_id,
        tier=tier,
        variant=meta.get("variant", "free"),
        score=meta.get("score"),
        size_bytes=meta.get("size_bytes"),
    )

    # Stream with a descriptive filename so downloads land cleanly
    from datetime import datetime as _dt
    date_str = _dt.utcnow().strftime("%Y-%m-%d")
    filename = f"inbxr-signal-report-{date_str}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
            "Cache-Control": "no-store",
        },
    )


@signal_bp.route("/signal-score/history")
@login_required
def signal_score_history():
    """Signal Score history as JSON for chart rendering."""
    user = get_current_user()
    history = get_signal_history(user["id"], esp_integration_id=None, limit=90)

    chart_data = [{
        "date": h.get("recorded_at"),
        "score": h.get("total_signal_score"),
        "grade": h.get("signal_grade"),
        "event_type": h.get("event_type"),
        "event_label": h.get("event_label"),
        "total_contacts": h.get("total_contacts"),
    } for h in history]

    return jsonify({"ok": True, "history": chart_data})


# ── Signal Map ─────────────────────────────────────────

@signal_bp.route("/signal-map")
@login_required
def signal_map():
    """Signal Map — visual breakdown of Active / Warm / At-Risk / Dormant segments."""
    user = get_current_user()
    latest = get_latest_signal_score(user["id"], esp_integration_id=None)

    # Count suppressed contacts
    suppressed_count = 0
    if latest:
        result = fetchone(
            """SELECT COUNT(*) as cnt FROM contact_segments
               WHERE user_id = ? AND is_suppressed = 1""",
            (user["id"],),
        )
        suppressed_count = result["cnt"] if result else 0

    return render_template(
        "signal/map.html",
        active_page="signal_map",
        latest=latest,
        suppressed_count=suppressed_count,
        segment_labels=SEGMENT_LABELS,
        title="Signal Map",
    )


# ── Signal Alerts ──────────────────────────────────────

@signal_bp.route("/signal-alerts")
@login_required
@tier_required("pro", "agency", "api")
def signal_alerts_page():
    """Signal Alerts list — Early Warning + Signal Rule firings."""
    user = get_current_user()
    alerts = get_signal_alerts(user["id"], limit=50)
    return render_template(
        "signal/alerts.html",
        active_page="signal_alerts",
        alerts=alerts,
        title="Signal Alerts",
    )


@signal_bp.route("/signal-alerts/<int:alert_id>/dismiss", methods=["POST"])
@login_required
def dismiss_signal_alert(alert_id):
    """Dismiss a signal alert."""
    user = get_current_user()
    dismiss_alert(user["id"], alert_id)
    return jsonify({"ok": True})


# ── Signal Rules ───────────────────────────────────────

@signal_bp.route("/signal-rules")
@login_required
@tier_required("pro", "agency", "api")
def signal_rules_page():
    """Signal Rules management page."""
    user = get_current_user()
    rules = get_user_rules(user["id"])
    rule_log = get_rule_log(user["id"], limit=20)

    return render_template(
        "signal/rules.html",
        active_page="signal_rules",
        rules=rules,
        rule_log=rule_log,
        templates=PRE_BUILT_RULE_TEMPLATES,
        signal_dimensions=SIGNAL_DIMENSION_COPY,
        rules_max=get_tier_limit(user.get("tier", "pro"), "signal_rules_max"),
        title="Signal Rules",
    )


@signal_bp.route("/signal-rules/create-from-template", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def create_rule_from_template_route():
    user = get_current_user()
    data = request.get_json(force=True) if request.is_json else request.form.to_dict()

    template_id = data.get("template_id")
    if not template_id:
        return jsonify({"ok": False, "error": "template_id required"}), 400

    # Check rule count limit
    existing_count = len(get_user_rules(user["id"]))
    max_rules = get_tier_limit(user.get("tier", "pro"), "signal_rules_max")
    if existing_count >= max_rules:
        return jsonify({
            "ok": False,
            "error": f"Rule limit reached ({max_rules}). Upgrade for more."
        }), 403

    result = create_rule_from_template(user["id"], template_id)
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 400
    return jsonify({"ok": True, "rule": result.get("rule")})


@signal_bp.route("/signal-rules/<int:rule_id>/preview", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def preview_rule(rule_id):
    """Dry-run preview: show what a rule WOULD do."""
    from modules.esp_contact_sync import get_contacts_for_signal_score

    user = get_current_user()

    latest = get_latest_signal_score(user["id"])
    if not latest:
        return jsonify({
            "ok": False,
            "error": "No Signal Score calculated yet. Run a calculation first."
        }), 400

    integration_id = latest.get("esp_integration_id")
    contacts = get_contacts_for_signal_score(user["id"], integration_id, limit=50000)

    # Build minimal signal_result dict from the latest row
    signal_result = {
        "scores": {
            "bounce_exposure": latest.get("bounce_exposure_score", 0),
            "engagement_trajectory": latest.get("engagement_trajectory_score", 0),
            "acquisition_quality": latest.get("acquisition_quality_score", 0),
            "domain_reputation": latest.get("domain_reputation_score", 0),
            "dormancy_risk": latest.get("dormancy_risk_score", 0),
            "authentication_standing": latest.get("authentication_standing_score", 0),
            "decay_velocity": latest.get("decay_velocity_score", 0),
        },
        "total_signal_score": latest.get("total_signal_score", 0),
    }

    preview = preview_signal_rule(user["id"], rule_id, contacts, signal_result)
    if preview.get("error"):
        return jsonify({"ok": False, "error": preview["error"]}), 404
    return jsonify({"ok": True, **preview})


@signal_bp.route("/signal-rules/<int:rule_id>/toggle", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def toggle_rule_route(rule_id):
    user = get_current_user()
    result = toggle_rule(user["id"], rule_id)
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 404
    return jsonify({"ok": True, **result})


@signal_bp.route("/signal-rules/<int:rule_id>/flip-dry-run", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def flip_rule_dry_run(rule_id):
    """
    Explicitly flip a rule from dry-run to live (or back).
    This is the ONLY way to activate a rule for real ESP/data changes.
    """
    user = get_current_user()
    result = flip_dry_run(user["id"], rule_id)
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 404
    return jsonify({"ok": True, **result})


@signal_bp.route("/signal-rules/<int:rule_id>", methods=["DELETE"])
@login_required
@tier_required("pro", "agency", "api")
def delete_rule_route(rule_id):
    user = get_current_user()
    result = delete_rule(user["id"], rule_id)
    return jsonify({"ok": True, **result})


# ── Send Readiness ─────────────────────────────────────

@signal_bp.route("/send-readiness")
@login_required
@tier_required("pro", "agency", "api")
def send_readiness_page():
    """Pre-campaign Signal readiness gate."""
    user = get_current_user()
    latest = get_latest_signal_score(user["id"])
    readiness = _calculate_send_readiness(latest)
    return render_template(
        "signal/send_readiness.html",
        active_page="send_readiness",
        latest=latest,
        readiness=readiness,
        title="Pre-send Check",
    )


@signal_bp.route("/send-readiness/check", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def send_readiness_check():
    """Check send readiness for a specific campaign/segment."""
    user = get_current_user()
    latest = get_latest_signal_score(user["id"])
    readiness = _calculate_send_readiness(latest)

    # Log the check event in history
    if latest:
        execute(
            """INSERT INTO signal_score_history (
                user_id, esp_integration_id, total_signal_score, signal_grade,
                event_type, event_label
            ) VALUES (?, ?, ?, ?, 'send_readiness_check', ?)""",
            (
                user["id"],
                latest.get("esp_integration_id"),
                latest["total_signal_score"],
                latest["signal_grade"],
                f"Send check: {readiness['status_label']}",
            ),
        )

    return jsonify({"ok": True, **readiness})


def _calculate_send_readiness(latest):
    """
    Compose green/amber/red send readiness gate from latest signal data.
    Green: score >= 70, no critical signals failing
    Amber: score 45-69, or one signal warning
    Red: score < 45, or authentication failing, or blacklisted
    """
    if not latest:
        return {
            "status": "amber",
            "status_label": "No signal data",
            "message": "Calculate your Signal Score first.",
            "issues": [],
            "actions": ["Connect your ESP or upload a CSV"],
        }

    issues = []
    actions = []
    score = latest.get("total_signal_score", 0)

    # Authentication check
    auth_score = latest.get("authentication_standing_score", 0)
    if auth_score < 3:
        issues.append("Authentication Standing is below threshold — emails may be rejected")
        actions.append("Fix authentication in Inboxer Sender Check")

    # Bounce exposure
    bounce_score = latest.get("bounce_exposure_score", 0)
    if bounce_score < 10:
        issues.append("Bounce Exposure is elevated — risk of reputation damage")
        actions.append("Run List Verification before sending")

    # Spam Trap Exposure
    dormancy = latest.get("dormancy_risk_score", 0)
    if dormancy < 5:
        issues.append("Spam Trap Exposure is high — suppress dormant contacts first")
        actions.append("Apply Signal Rules to suppress 180+ day dormant contacts")

    # Segment composition
    at_risk = latest.get("at_risk_contacts", 0)
    total = latest.get("total_contacts", 0) or 1
    at_risk_pct = (at_risk / total) * 100

    if at_risk_pct > 20:
        issues.append(f"{at_risk_pct:.0f}% of your list is At-Risk — sending to full list not recommended")
        actions.append("Run Recovery Sequences on At-Risk segment first")

    if score >= 70 and not issues:
        status = "green"
        label = "Clear"
        message = "Clear to send. All 7 Inbox Signals are in good condition."
    elif score >= 45 and len(issues) <= 1:
        status = "amber"
        label = "Caution"
        message = f'{len(issues)} signal{"s" if len(issues) != 1 else ""} need attention before sending.'
    else:
        status = "red"
        label = "Hold"
        message = "Do not send to your full list. Resolve signal issues first."

    return {
        "status": status,
        "status_label": label,
        "score": score,
        "grade": latest.get("signal_grade"),
        "message": message,
        "issues": issues,
        "actions": actions,
    }


# ── Recovery Sequences (stub — depends on Groq integration) ──

@signal_bp.route("/recovery-sequences")
@login_required
@tier_required("pro", "agency", "api")
def recovery_sequences_page():
    """Recovery Sequences page — AI-generated re-engagement email flow."""
    user = get_current_user()
    latest = get_latest_signal_score(user["id"])
    return render_template(
        "signal/recovery_sequences.html",
        active_page="recovery_sequences",
        latest=latest,
        title="Recovery Sequences",
    )


@signal_bp.route("/recovery-sequences/generate", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def generate_recovery_sequence():
    """
    Generate a 2-3 email re-engagement sequence via Groq.
    Stubs the Groq call for now — full integration in next session.
    """
    data = request.get_json(force=True) if request.is_json else request.form.to_dict()
    segment = data.get("segment", "at_risk")
    brand_name = data.get("brand_name", "our brand")
    tone = data.get("tone", "conversational")
    num_emails = int(data.get("num_emails", 3))

    # Build prompt and call Groq — uses existing ai_rewriter pattern
    try:
        sequence = _generate_sequence_via_groq(segment, brand_name, tone, num_emails)
        return jsonify({"ok": True, "sequence": sequence})
    except Exception as e:
        logger.exception("Recovery Sequences generation failed")
        return jsonify({"ok": False, "error": "Generation failed. Try again."}), 500


@signal_bp.route("/recovery-sequences/export-mailchimp", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def export_recovery_to_mailchimp():
    """Take a generated recovery sequence and push each email as a
    draft campaign into the user's connected Mailchimp account.

    Expected JSON body:
        sequence: list of email dicts (from /recovery-sequences/generate)
        from_name: sender display name
        reply_to: reply-to email address

    The user must have an active Mailchimp integration. Each email in
    the sequence becomes a separate draft campaign — the user opens
    Mailchimp, reviews, edits styling, and schedules from there.
    Every generation is logged to esp_writeback_log with outcome.
    """
    from modules.esp_writeback import export_recovery_sequence_to_mailchimp

    user = get_current_user()
    user_id = user["id"]

    data = request.get_json(silent=True) or {}
    sequence = data.get("sequence") or []
    from_name = (data.get("from_name") or user.get("display_name") or "Your Brand").strip()[:100]
    reply_to = (data.get("reply_to") or user.get("email") or "").strip()

    if not sequence:
        return jsonify({"ok": False, "error": "No sequence provided."}), 400

    # Find the user's active Mailchimp integration
    integration = fetchone(
        """SELECT id FROM esp_integrations
           WHERE user_id = ? AND provider = 'mailchimp' AND status = 'active'
           ORDER BY id DESC LIMIT 1""",
        (user_id,),
    )
    if not integration:
        return jsonify({
            "ok": False,
            "error": "No active Mailchimp integration found. Connect Mailchimp first in Settings → Integrations.",
        }), 400

    try:
        result = export_recovery_sequence_to_mailchimp(
            user_id=user_id,
            esp_integration_id=integration["id"],
            sequence=sequence,
            from_name=from_name,
            reply_to=reply_to,
        )
    except Exception:
        logger.exception("Recovery Sequences Mailchimp export failed")
        return jsonify({"ok": False, "error": "Export failed. Please try again."}), 500

    return jsonify(result)


def _generate_sequence_via_groq(segment, brand_name, tone, num_emails):
    """
    Call Groq with a recovery sequence prompt. Uses the same HTTPSConnection
    pattern as modules/ai_rewriter.py and modules/assistant_chat.py for
    consistency (urllib's default User-Agent gets 403 from some endpoints).

    Returns a list of email dicts: [{subject_variants, preview_text, body, cta_text}, ...]
    """
    import os
    import re
    import ssl
    from http.client import HTTPSConnection

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not configured")

    api_host = os.environ.get("AI_API_HOST", "api.groq.com")
    api_path = os.environ.get("AI_API_PATH", "/openai/v1/chat/completions")
    model = os.environ.get("AI_MODEL", "llama-3.3-70b-versatile")

    days_map = {"at_risk": "91-180", "dormant": "180+", "warm": "31-90", "cold_acquisition": "never engaged"}
    days_inactive = days_map.get(segment, "90+")

    prompt = f"""You are an expert email re-engagement copywriter. Generate a {num_emails}-email re-engagement sequence as JSON.

Context from InbXr's 7 Inbox Signals:
- Segment: {segment} ({days_inactive} days since last engagement)
- Brand: {brand_name}
- Tone: {tone}

Structure:
- Email 1 (Day 1): Gentle re-connection — did we lose you?
- Email 2 (Day 4): Value reminder — what they're missing
{f"- Email 3 (Day 8): Stay or go? Binary final ask" if num_emails >= 3 else ""}

Return ONLY a valid JSON object with key "emails" mapping to an array. Each email object has:
- subject_1, subject_2, subject_3 (3 subject line variants)
- preview_text (preheader, ~50 chars)
- body (150-200 words)
- cta_text

Rules:
- Focus: re-engagement signal (click or reply), not selling
- Avoid: ALL CAPS, excessive punctuation, "Act Now" urgency, spam triggers
- Match tone: {tone}"""

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2500,
        "response_format": {"type": "json_object"},
    })

    ctx = ssl.create_default_context()
    conn = HTTPSConnection(api_host, 443, timeout=60, context=ctx)

    try:
        conn.request("POST", api_path, body=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")

        if resp.status != 200:
            try:
                err = json.loads(body).get("error", {}).get("message", body[:200])
            except (json.JSONDecodeError, KeyError, TypeError):
                err = body[:200]
            raise RuntimeError(f"Groq API {resp.status}: {err}")

        response = json.loads(body)
        content = response["choices"][0]["message"]["content"]
    finally:
        conn.close()

    # Parse the JSON response (response_format=json_object guarantees valid JSON)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)
    parsed = json.loads(cleaned)

    # Extract emails array — accept either {"emails": [...]} or a bare list
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("emails", "sequence", "messages", "results"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
        # Fall back: if dict has email-like keys, wrap as single-item list
        if "subject_1" in parsed or "body" in parsed:
            return [parsed]
    raise RuntimeError("Unexpected Groq response shape")
