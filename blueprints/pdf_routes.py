"""
InbXr — PDF Report Routes
Generate and serve PDF/HTML reports for saved check results.
"""

import json
import re
from datetime import datetime
from flask import Blueprint, request, jsonify, session, Response

from modules.auth import get_current_user, login_required
from modules.tiers import has_feature
from modules.database import fetchone
from modules.pdf_report import generate_report, generate_report_html, HAS_REPORTLAB

pdf_bp = Blueprint("pdf", __name__)


def _get_history_record(history_id, user_id):
    """
    Fetch a check_history record that belongs to the given user.
    Returns a dict with result_json deserialized, or None.
    This is a local helper — once modules/history.py lands with
    get_result(), this can delegate to that instead.
    """
    row = fetchone(
        "SELECT * FROM check_history WHERE id = ? AND user_id = ?",
        (history_id, user_id),
    )
    if not row:
        return None

    record = dict(row)
    # Deserialize result_json
    raw = record.get("result_json", "{}")
    if isinstance(raw, str):
        try:
            record["result_json"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            record["result_json"] = {}
    return record


def _sanitize_filename(text):
    """Make a safe filename from arbitrary text."""
    clean = re.sub(r'[^a-zA-Z0-9._@-]', '-', str(text))
    clean = re.sub(r'-{2,}', '-', clean).strip('-')
    return clean[:60] or "report"


@pdf_bp.route("/api/report/<int:history_id>/pdf")
@login_required
def download_pdf(history_id):
    """Generate and return a PDF report for a saved result."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    user_tier = user.get("tier", "free")
    if not has_feature(user_tier, "pdf_reports"):
        return jsonify({
            "error": "PDF reports require a Pro, Agency, or API plan.",
            "upgrade_url": "/pricing",
        }), 403

    record = _get_history_record(history_id, user["id"])
    if not record:
        return jsonify({"error": "Report not found."}), 404

    result_data = record.get("result_json", {})
    tool = record.get("tool", "check")
    input_summary = record.get("input_summary", "unknown")
    grade = record.get("grade")
    score = record.get("score")
    created_at = record.get("created_at")

    # Try PDF generation with reportlab
    pdf_bytes = generate_report(
        result_data, tool, input_summary,
        created_at=created_at, grade=grade, score=score,
    )

    if pdf_bytes:
        # Build filename: inbxr-example.com-2026-03-11.pdf
        date_part = ""
        try:
            if created_at:
                if isinstance(created_at, str):
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                else:
                    dt = created_at
                date_part = dt.strftime("%Y-%m-%d")
            else:
                date_part = datetime.now().strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            date_part = datetime.now().strftime("%Y-%m-%d")

        filename = f"inbxr-{_sanitize_filename(input_summary)}-{date_part}.pdf"

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/pdf",
            },
        )

    # Fallback: return HTML with print-friendly notice
    html = generate_report_html(
        result_data, tool, input_summary,
        created_at=created_at, grade=grade, score=score,
    )
    # Wrap with a print prompt banner
    fallback_banner = """
    <div style="background:#fef3c7;border:1px solid #f59e0b;padding:12px 20px;
                border-radius:8px;margin-bottom:20px;font-size:14px;color:#92400e;"
         class="no-print">
        <strong>PDF library not available.</strong>
        Use your browser's Print function (Ctrl+P / Cmd+P) and select "Save as PDF"
        to download this report.
    </div>
    """
    html = html.replace("<body>", "<body>" + fallback_banner, 1)
    return Response(html, mimetype="text/html")


@pdf_bp.route("/api/report/<int:history_id>/html")
@login_required
def preview_html(history_id):
    """Return a styled HTML preview of the report."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Authentication required."}), 401

    user_tier = user.get("tier", "free")
    if not has_feature(user_tier, "pdf_reports"):
        return jsonify({
            "error": "Report preview requires a Pro, Agency, or API plan.",
            "upgrade_url": "/pricing",
        }), 403

    record = _get_history_record(history_id, user["id"])
    if not record:
        return jsonify({"error": "Report not found."}), 404

    result_data = record.get("result_json", {})
    tool = record.get("tool", "check")
    input_summary = record.get("input_summary", "unknown")
    grade = record.get("grade")
    score = record.get("score")
    created_at = record.get("created_at")

    html = generate_report_html(
        result_data, tool, input_summary,
        created_at=created_at, grade=grade, score=score,
    )
    return Response(html, mimetype="text/html")
