"""
InbXr — Public API v1
─────────────────────
Authenticated REST API for Agency tier subscribers. Drives Zapier,
Make, custom workflows, and third-party integrations that need
programmatic access to the Signal Engine.

Authentication: X-API-Key header (api_key_required decorator).
Rate limits: enforced via existing check_rate_limit on the
             api_calls_per_hour limit in tiers.py.
CORS: allowed for all origins so the API can be called from
      browser-side JS on customer sites.

Endpoints:

    GET  /api/v1/signal-score/<domain>
         → Full Domain Signal Score for a domain. Same engine that
           powers the homepage lookup. Returns all 7 signals.

    GET  /api/v1/my-score
         → The authenticated user's latest Signal Score from their
           connected ESP integration. Returns full list-backed data.

    GET  /api/v1/leaderboard
         → Top 100 domains from the public leaderboard. Anonymized.

    POST /api/v1/csv-triage
         → Upload a CSV body and receive the Remove/Re-engage/Keep
           triage as JSON. Mirrors the public flow.

    GET  /api/v1/health
         → Ping endpoint for uptime monitoring.

All endpoints return JSON, all endpoints set Access-Control-Allow-Origin.
Errors follow the shape: {"ok": false, "error": "...", "code": "..."}
Successes follow:         {"ok": true, ...payload}
"""

import logging

from flask import Blueprint, request, jsonify, g

from modules.auth import api_key_required
from modules.database import fetchone

logger = logging.getLogger("inbxr.api_v1")

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


# ── CORS helper ─────────────────────────────────────────


@api_v1_bp.after_request
def _cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    return response


# ── Health / status ─────────────────────────────────────


@api_v1_bp.route("/health")
def health():
    """Ping endpoint. Returns 200 without auth so uptime monitors
    and API consumers can verify the API is reachable."""
    return jsonify({
        "ok": True,
        "service": "InbXr API v1",
        "version": "1.0.0",
    })


# ── Domain Signal Score lookup ──────────────────────────


@api_v1_bp.route("/signal-score/<domain>")
@api_key_required
def api_signal_score_domain(domain):
    """Return the Domain Signal Score for any sending domain.

    This is a 2-of-7 signal reading (auth + reputation) that works
    from public DNS data alone. For full 7-signal readings, use
    /api/v1/my-score which reads the authenticated user's own
    connected ESP.
    """
    from modules.signal_score import calculate_domain_signal_score

    clean = (domain or "").strip().lower()
    if not clean or "." not in clean:
        return jsonify({
            "ok": False,
            "error": "Invalid domain format.",
            "code": "invalid_domain",
        }), 400

    try:
        result = calculate_domain_signal_score(clean)
    except Exception:
        logger.exception("[API v1] domain score failed for %s", clean)
        return jsonify({
            "ok": False,
            "error": "Score computation failed.",
            "code": "engine_error",
        }), 500

    if result.get("error"):
        return jsonify({
            "ok": False,
            "error": result.get("message", "Scoring failed."),
            "code": result.get("error"),
        }), 400

    # Slim payload: return the user-facing fields only, not internal state
    return jsonify({
        "ok": True,
        "domain": result.get("domain"),
        "total_signal_score": result.get("total_signal_score"),
        "signal_grade": result.get("signal_grade"),
        "visible_signals": result.get("visible_signals"),
        "locked_signals": result.get("locked_signals"),
        "scores": result.get("scores"),
        "metadata": {
            "authentication_standing": result.get("metadata", {}).get("authentication_standing"),
            "domain_reputation": result.get("metadata", {}).get("domain_reputation"),
        },
        "recommendations": result.get("recommendations", []),
    })


# ── Authenticated user's own Signal Score ──────────────


@api_v1_bp.route("/my-score")
@api_key_required
def api_my_signal_score():
    """Return the authenticated user's latest Signal Score from their
    connected ESP. Full 7-signal reading with list data (bounce
    exposure, engagement trajectory, etc). Only populated if the
    user has an active ESP integration and Signal Watch has run."""
    user = g._api_user
    user_id = user["id"]

    row = fetchone(
        """SELECT total_signal_score, signal_grade,
                  bounce_exposure_score, engagement_trajectory_score,
                  acquisition_quality_score, domain_reputation_score,
                  dormancy_risk_score, authentication_standing_score,
                  decay_velocity_score,
                  active_contacts, warm_contacts, at_risk_contacts,
                  dormant_contacts, total_contacts,
                  trajectory_direction, velocity_rate,
                  calculated_at
           FROM signal_scores
           WHERE user_id = ?
           ORDER BY calculated_at DESC LIMIT 1""",
        (user_id,),
    )

    if not row:
        return jsonify({
            "ok": False,
            "error": "No Signal Score on record yet. Connect an ESP or upload a CSV first.",
            "code": "no_score",
        }), 404

    return jsonify({
        "ok": True,
        "user_id": user_id,
        "calculated_at": row["calculated_at"],
        "total_signal_score": row["total_signal_score"],
        "signal_grade": row["signal_grade"],
        "signals": {
            "bounce_exposure": row["bounce_exposure_score"],
            "engagement_trajectory": row["engagement_trajectory_score"],
            "acquisition_quality": row["acquisition_quality_score"],
            "domain_reputation": row["domain_reputation_score"],
            "dormancy_risk": row["dormancy_risk_score"],
            "authentication_standing": row["authentication_standing_score"],
            "decay_velocity": row["decay_velocity_score"],
        },
        "segments": {
            "active": row["active_contacts"],
            "warm": row["warm_contacts"],
            "at_risk": row["at_risk_contacts"],
            "dormant": row["dormant_contacts"],
            "total": row["total_contacts"],
        },
        "trajectory": {
            "direction": row["trajectory_direction"],
            "velocity_rate": row["velocity_rate"],
        },
    })


# ── Public leaderboard ──────────────────────────────────


@api_v1_bp.route("/leaderboard")
@api_key_required
def api_leaderboard():
    """Return the top 100 public leaderboard domains. Anonymized
    aggregate data. Useful for external dashboards showing 'how
    does my domain compare'."""
    from modules.leaderboard import get_top_domains, get_leaderboard_stats

    limit = min(int(request.args.get("limit", 100)), 500)
    grade = (request.args.get("grade") or "").strip().upper() or None

    top = get_top_domains(limit=limit, grade_filter=grade)
    stats = get_leaderboard_stats()

    return jsonify({
        "ok": True,
        "count": len(top),
        "stats": stats,
        "leaderboard": [
            {
                "rank": i + 1,
                "domain": r["domain"],
                "total_score": r["total_score"],
                "grade": r["grade"],
                "auth_score": r["auth_score"],
                "rep_score": r["rep_score"],
                "scan_count": r["scan_count"],
                "last_scanned_at": r["last_scanned_at"],
            }
            for i, r in enumerate(top)
        ],
    })


# ── CSV triage ──────────────────────────────────────────


@api_v1_bp.route("/csv-triage", methods=["POST"])
@api_key_required
def api_csv_triage():
    """Upload a CSV body (as raw text in the request body or
    application/x-www-form-urlencoded csv_content field) and receive
    the Remove / Re-engage / Keep classification. Useful for Zapier
    workflows that want to auto-triage lists before sends."""
    from modules.list_triage import triage_list

    csv_content = None

    if request.is_json:
        data = request.get_json(silent=True) or {}
        csv_content = data.get("csv_content", "")
    elif request.content_type and "text/csv" in request.content_type.lower():
        csv_content = request.get_data(as_text=True)
    else:
        csv_content = request.form.get("csv_content", "")

    if not csv_content or len(csv_content.strip()) < 10:
        return jsonify({
            "ok": False,
            "error": "CSV content required. Pass as 'csv_content' field or raw text/csv body.",
            "code": "no_csv",
        }), 400

    # 5 MB cap matching the public endpoint
    if len(csv_content.encode("utf-8")) > 5 * 1024 * 1024:
        return jsonify({
            "ok": False,
            "error": "CSV too large. Max 5 MB.",
            "code": "too_large",
        }), 400

    try:
        result = triage_list(csv_content)
    except Exception:
        logger.exception("[API v1] csv-triage failed")
        return jsonify({
            "ok": False,
            "error": "Triage failed.",
            "code": "engine_error",
        }), 500

    if not result.get("ok"):
        return jsonify(result), 400

    # Strip internal buckets from the response
    result.pop("_full_buckets", None)
    return jsonify(result)
