"""
InbXr — Bulk Email Verification Routes
Upload CSV / paste emails, run bulk verification, download results.
"""

import csv
import io
import logging
import threading

from flask import (
    Blueprint, render_template, request, jsonify, session, Response,
)

logger = logging.getLogger('inbxr.bulk_routes')

from modules.auth import login_required, tier_required, get_current_user
from modules.tiers import get_tier_limit
from modules.rate_limiter import check_rate_limit, log_usage
from modules.bulk_verify import (
    create_bulk_job, process_bulk_job,
    get_job_status, get_job_results, get_user_jobs, generate_csv,
)

bulk_bp = Blueprint("bulk", __name__)


def _get_daily_verify_usage(user_id):
    """Count how many email verifications the user has used today."""
    from datetime import datetime, timedelta, timezone
    from modules.database import fetchone

    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()
    row = fetchone(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id = ? AND action = 'email_verify' AND created_at > ?",
        (user_id, day_ago),
    )
    return row["cnt"] if row else 0


def _parse_csv_emails(file_content):
    """Parse emails from a CSV file content string.

    Looks for a column named 'email' (case-insensitive), or uses the
    first column if the file has only one column.

    Returns
    -------
    list[str]
        List of email strings extracted from the CSV.
    """
    emails = []
    try:
        reader = csv.reader(io.StringIO(file_content))
        rows = list(reader)
    except csv.Error:
        logger.exception("Failed to parse CSV content")
        return emails

    if not rows:
        return emails

    # Check header row for 'email' column
    header = rows[0]
    email_col = None

    for i, col in enumerate(header):
        if col.strip().lower() == "email":
            email_col = i
            break

    # If no 'email' column found and only one column, use it
    if email_col is None and len(header) == 1:
        email_col = 0
        # First row might be data, not a header
        first_val = header[0].strip()
        if "@" in first_val:
            emails.append(first_val)

    if email_col is None:
        return emails

    # Extract emails from remaining rows
    for row in rows[1:]:
        if email_col < len(row):
            val = row[email_col].strip()
            if val and "@" in val:
                emails.append(val)

    return emails


# ── Pages ──────────────────────────────────────────────

@bulk_bp.route("/bulk-verify")
@login_required
@tier_required("pro", "agency", "api")
def bulk_verify_page():
    """Render the bulk verification page."""
    user = get_current_user()
    tier = user["tier"]
    daily_limit = get_tier_limit(tier, "email_verifications_per_day")
    used_today = _get_daily_verify_usage(user["id"])
    remaining = max(0, daily_limit - used_today)
    team_id = session.get("team_id")
    jobs = get_user_jobs(user["id"], team_id=team_id)

    return render_template(
        "auth/bulk_verify.html",
        active_page="bulk_verify",
        daily_limit=daily_limit,
        used_today=used_today,
        remaining=remaining,
        jobs=jobs,
    )


# ── API Routes ─────────────────────────────────────────

@bulk_bp.route("/api/bulk-verify", methods=["POST"])
@login_required
@tier_required("pro", "agency", "api")
def create_bulk():
    """Accept CSV file or JSON array, create and start a bulk job."""
    user = get_current_user()
    user_id = user["id"]
    tier = user["tier"]
    daily_limit = get_tier_limit(tier, "email_verifications_per_day")
    used_today = _get_daily_verify_usage(user_id)
    remaining = max(0, daily_limit - used_today)

    emails = []
    filename = None

    # Parse input: file upload or JSON body
    if request.content_type and "multipart/form-data" in request.content_type:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file uploaded."}), 400

        filename = file.filename
        try:
            content = file.read().decode("utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            return jsonify({"error": "Could not read file."}), 400

        # Check if it's a plain text file (one email per line)
        if filename and filename.lower().endswith(".txt"):
            emails = [
                line.strip()
                for line in content.splitlines()
                if line.strip() and "@" in line.strip()
            ]
        else:
            emails = _parse_csv_emails(content)

    elif request.is_json:
        data = request.get_json(silent=True)
        if not data or "emails" not in data:
            return jsonify({"error": "JSON body must include 'emails' array."}), 400
        emails = data["emails"]
        if not isinstance(emails, list):
            return jsonify({"error": "'emails' must be an array."}), 400

    else:
        return jsonify({"error": "Send a CSV file or JSON with 'emails' array."}), 400

    if not emails:
        return jsonify({"error": "No emails found in the input."}), 400

    # Check against daily limit
    if len(emails) > remaining:
        return jsonify({
            "error": f"Not enough daily verifications remaining. You have {remaining:,} left but submitted {len(emails):,}.",
            "remaining": remaining,
            "submitted": len(emails),
        }), 429

    # Create the job
    team_id = session.get("team_id")
    try:
        job_id = create_bulk_job(user_id, emails, filename=filename, team_id=team_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Log usage for each email being verified
    for _ in range(len(emails)):
        log_usage("email_verify")

    # Start processing in background thread
    threading.Thread(
        target=process_bulk_job,
        args=(job_id,),
        daemon=True,
    ).start()

    return jsonify({
        "job_id": job_id,
        "total_emails": len(emails),
        "status": "processing",
    }), 201


@bulk_bp.route("/api/bulk-verify/<int:job_id>")
@login_required
@tier_required("pro", "agency", "api")
def job_status(job_id):
    """Get job status and summary."""
    user = get_current_user()
    team_id = session.get("team_id")
    status = get_job_status(job_id, user["id"], team_id=team_id)

    if not status:
        return jsonify({"error": "Job not found."}), 404

    return jsonify(status)


@bulk_bp.route("/api/bulk-verify/<int:job_id>/results")
@login_required
@tier_required("pro", "agency", "api")
def job_results(job_id):
    """Get paginated results for a job."""
    user = get_current_user()

    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        limit = 100
        offset = 0

    team_id = session.get("team_id")
    results = get_job_results(job_id, user["id"], limit=limit, offset=offset, team_id=team_id)
    if results is None:
        return jsonify({"error": "Job not found."}), 404

    return jsonify({
        "job_id": job_id,
        "limit": limit,
        "offset": offset,
        "count": len(results),
        "results": results,
    })


@bulk_bp.route("/api/bulk-verify/<int:job_id>/csv")
@login_required
@tier_required("pro", "agency", "api")
def job_csv(job_id):
    """Download results as CSV file."""
    user = get_current_user()
    team_id = session.get("team_id")
    csv_content = generate_csv(job_id, user["id"], team_id=team_id)

    if csv_content is None:
        return jsonify({"error": "Job not found."}), 404

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=inbxr-bulk-{job_id}.csv",
        },
    )


@bulk_bp.route("/api/bulk-verify/jobs")
@login_required
@tier_required("pro", "agency", "api")
def list_jobs():
    """List all bulk jobs for the current user."""
    user = get_current_user()
    team_id = session.get("team_id")
    jobs = get_user_jobs(user["id"], team_id=team_id)
    return jsonify({"jobs": jobs})
