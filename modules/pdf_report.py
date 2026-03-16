"""
INBXR — PDF Report Generation
Generates professional PDF reports from check results.
Uses reportlab if available, falls back to styled HTML.
"""

import io
from datetime import datetime

# ── Try to import reportlab ──────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, inch
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# ── Color constants ──────────────────────────────────────
GREEN = "#16a34a"
RED = "#ef4444"
AMBER = "#f59e0b"
BLUE = "#2563eb"
DARK = "#1e293b"
GRAY = "#64748b"
LIGHT_BG = "#f8fafc"
BRAND_BLUE = "#2563eb"


# ══════════════════════════════════════════════════════════
#  HTML REPORT (fallback + preview)
# ══════════════════════════════════════════════════════════

def _status_color(status):
    """Return CSS color for a status string."""
    s = str(status).lower()
    if s in ("pass", "passed", "valid", "good", "deliverable", "safe", "configured"):
        return GREEN
    if s in ("fail", "failed", "invalid", "bad", "risky", "undeliverable", "missing"):
        return RED
    return AMBER


def _score_color(score, max_score=100):
    """Return CSS color based on a numeric score."""
    if score is None:
        return GRAY
    try:
        pct = float(score) / float(max_score) * 100
    except (ValueError, TypeError, ZeroDivisionError):
        return GRAY
    if pct >= 70:
        return GREEN
    if pct >= 40:
        return AMBER
    return RED


def _grade_color(grade):
    """Return CSS color based on letter grade."""
    if not grade:
        return GRAY
    g = str(grade).upper().strip()
    if g in ("A+", "A", "A-"):
        return GREEN
    if g in ("B+", "B", "B-"):
        return "#22c55e"
    if g in ("C+", "C", "C-"):
        return AMBER
    return RED


def _format_date(dt_str):
    """Format a datetime string for display."""
    if not dt_str:
        return datetime.now().strftime("%B %d, %Y")
    try:
        if isinstance(dt_str, datetime):
            return dt_str.strftime("%B %d, %Y")
        dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except (ValueError, TypeError):
        return str(dt_str)


def _safe_get(data, *keys, default=None):
    """Safely traverse nested dicts."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current if current is not None else default


# ── Section builders for HTML ────────────────────────────

def _html_domain_check(result):
    """Build HTML sections for domain/reputation check results."""
    sections = []

    # Auth records (SPF, DKIM, DMARC)
    auth_data = _safe_get(result, "authentication") or _safe_get(result, "auth") or {}
    if not auth_data:
        # Try top-level keys
        for key in ("spf", "dkim", "dmarc"):
            val = _safe_get(result, key)
            if val:
                auth_data[key] = val

    if auth_data:
        rows = ""
        for protocol in ("spf", "dkim", "dmarc"):
            rec = auth_data.get(protocol, {})
            if isinstance(rec, dict):
                status = rec.get("status", rec.get("result", "unknown"))
                detail = rec.get("record", rec.get("value", rec.get("details", "")))
            else:
                status = str(rec)
                detail = ""
            color = _status_color(status)
            rows += f"""
            <tr>
                <td style="font-weight:600;text-transform:uppercase;">{protocol}</td>
                <td style="color:{color};font-weight:600;">{status}</td>
                <td style="font-size:13px;color:#475569;word-break:break-all;">{detail}</td>
            </tr>"""
        sections.append(f"""
        <div class="section">
            <h3>Email Authentication</h3>
            <table class="data-table">
                <thead><tr><th>Protocol</th><th>Status</th><th>Record</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>""")

    # Blocklist summary
    blocklist = _safe_get(result, "blocklist") or _safe_get(result, "blacklist") or _safe_get(result, "blocklists") or {}
    if blocklist:
        listed_on = []
        clean_on = []
        if isinstance(blocklist, dict):
            items = blocklist.get("results", blocklist.get("lists", blocklist))
            if isinstance(items, dict):
                for name, info in items.items():
                    if name in ("listed_count", "total_checked", "clean_count", "summary"):
                        continue
                    if isinstance(info, dict):
                        is_listed = info.get("listed", False)
                    else:
                        is_listed = bool(info)
                    if is_listed:
                        listed_on.append(name)
                    else:
                        clean_on.append(name)
            elif isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        name = item.get("name", item.get("list", ""))
                        if item.get("listed", False):
                            listed_on.append(name)
                        else:
                            clean_on.append(name)

        listed_count = len(listed_on)
        total = listed_count + len(clean_on)
        color = RED if listed_count > 0 else GREEN
        sections.append(f"""
        <div class="section">
            <h3>Blocklist Check</h3>
            <p style="font-size:18px;font-weight:600;color:{color};">
                {"Listed on " + str(listed_count) + " of " + str(total) + " lists checked" if listed_count > 0
                 else "Clean — not listed on any of " + str(total) + " lists checked"}
            </p>
            {"<ul>" + "".join(f'<li style="color:{RED};">{name}</li>' for name in listed_on) + "</ul>" if listed_on else ""}
        </div>""")

    # Category scores
    categories = _safe_get(result, "categories") or _safe_get(result, "scores") or {}
    if isinstance(categories, dict) and categories:
        rows = ""
        for cat, score in categories.items():
            if isinstance(score, dict):
                val = score.get("score", score.get("value", ""))
                label = score.get("label", score.get("status", ""))
            else:
                val = score
                label = ""
            color = _score_color(val) if isinstance(val, (int, float)) else GRAY
            rows += f"""
            <tr>
                <td>{cat.replace("_", " ").title()}</td>
                <td style="color:{color};font-weight:600;">{val}</td>
                <td>{label}</td>
            </tr>"""
        sections.append(f"""
        <div class="section">
            <h3>Category Scores</h3>
            <table class="data-table">
                <thead><tr><th>Category</th><th>Score</th><th>Status</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>""")

    # Recommendations
    recs = _safe_get(result, "recommendations") or _safe_get(result, "suggestions") or []
    if isinstance(recs, list) and recs:
        items = "".join(f"<li>{r}</li>" for r in recs if isinstance(r, str))
        if not items:
            items = "".join(
                f"<li>{r.get('text', r.get('message', str(r)))}</li>"
                for r in recs if isinstance(r, dict)
            )
        sections.append(f"""
        <div class="section">
            <h3>Recommendations</h3>
            <ul class="rec-list">{items}</ul>
        </div>""")

    return "\n".join(sections)


def _html_copy_analysis(result):
    """Build HTML sections for copy/spam analysis results."""
    sections = []

    # Score summary
    scores = []
    for key, label in [
        ("spam_score", "Spam Score"),
        ("copy_score", "Copy Score"),
        ("readability_score", "Readability Score"),
        ("readability", "Readability"),
        ("overall_score", "Overall Score"),
    ]:
        val = _safe_get(result, key)
        if val is not None:
            if isinstance(val, dict):
                val = val.get("score", val.get("value", ""))
            scores.append((label, val))

    if scores:
        cards = ""
        for label, val in scores:
            color = _score_color(val)
            cards += f"""
            <div class="score-card">
                <div class="score-value" style="color:{color};">{val}</div>
                <div class="score-label">{label}</div>
            </div>"""
        sections.append(f'<div class="section"><h3>Scores</h3><div class="score-grid">{cards}</div></div>')

    # Issues
    issues = _safe_get(result, "issues") or _safe_get(result, "warnings") or _safe_get(result, "problems") or []
    if isinstance(issues, list) and issues:
        rows = ""
        for issue in issues[:20]:
            if isinstance(issue, dict):
                text = issue.get("message", issue.get("text", issue.get("issue", str(issue))))
                severity = issue.get("severity", issue.get("level", ""))
                color = RED if str(severity).lower() in ("high", "critical", "error") else AMBER
            else:
                text = str(issue)
                severity = ""
                color = AMBER
            rows += f'<li style="color:{color};">{text}</li>'
        sections.append(f"""
        <div class="section">
            <h3>Issues Found</h3>
            <ul class="issue-list">{rows}</ul>
        </div>""")

    # Spam triggers
    triggers = _safe_get(result, "spam_triggers") or _safe_get(result, "triggers") or []
    if isinstance(triggers, list) and triggers:
        items = ""
        for t in triggers[:15]:
            if isinstance(t, dict):
                word = t.get("word", t.get("trigger", t.get("text", str(t))))
                items += f'<li style="color:{RED};">{word}</li>'
            else:
                items += f'<li style="color:{RED};">{t}</li>'
        sections.append(f"""
        <div class="section">
            <h3>Spam Triggers</h3>
            <ul>{items}</ul>
        </div>""")

    return "\n".join(sections)


def _html_email_verification(result):
    """Build HTML sections for email verification results."""
    sections = []

    verdict = _safe_get(result, "verdict") or _safe_get(result, "result") or _safe_get(result, "status") or ""
    score = _safe_get(result, "score") or _safe_get(result, "confidence") or ""
    color = _status_color(verdict)

    sections.append(f"""
    <div class="section">
        <h3>Verification Result</h3>
        <div class="score-grid">
            <div class="score-card">
                <div class="score-value" style="color:{color};">{str(verdict).title()}</div>
                <div class="score-label">Verdict</div>
            </div>
            {"<div class='score-card'><div class='score-value' style='color:" + _score_color(score) + ";'>" + str(score) + "</div><div class='score-label'>Score</div></div>" if score else ""}
        </div>
    </div>""")

    # Checks
    checks = _safe_get(result, "checks") or {}
    if isinstance(checks, dict) and checks:
        rows = ""
        for check_name, check_val in checks.items():
            if isinstance(check_val, dict):
                passed = check_val.get("passed", check_val.get("valid", check_val.get("result", False)))
                detail = check_val.get("detail", check_val.get("message", ""))
            else:
                passed = bool(check_val)
                detail = ""
            status = "Pass" if passed else "Fail"
            color = GREEN if passed else RED
            rows += f"""
            <tr>
                <td>{check_name.replace("_", " ").title()}</td>
                <td style="color:{color};font-weight:600;">{status}</td>
                <td>{detail}</td>
            </tr>"""
        sections.append(f"""
        <div class="section">
            <h3>Checks</h3>
            <table class="data-table">
                <thead><tr><th>Check</th><th>Result</th><th>Details</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>""")

    return "\n".join(sections)


def _html_subject_scoring(result):
    """Build HTML sections for subject line scoring results."""
    sections = []

    subjects = _safe_get(result, "subjects") or _safe_get(result, "results") or []
    if isinstance(subjects, list) and subjects:
        rows = ""
        for i, subj in enumerate(subjects, 1):
            if isinstance(subj, dict):
                text = subj.get("subject", subj.get("text", subj.get("line", "")))
                score = subj.get("score", subj.get("rating", ""))
                notes = subj.get("feedback", subj.get("notes", subj.get("reason", "")))
            else:
                text = str(subj)
                score = ""
                notes = ""
            color = _score_color(score) if score else GRAY
            rows += f"""
            <tr>
                <td style="font-weight:600;">#{i}</td>
                <td>{text}</td>
                <td style="color:{color};font-weight:600;">{score}</td>
                <td style="font-size:13px;">{notes}</td>
            </tr>"""
        sections.append(f"""
        <div class="section">
            <h3>Subject Lines</h3>
            <table class="data-table">
                <thead><tr><th>#</th><th>Subject</th><th>Score</th><th>Feedback</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>""")

    return "\n".join(sections)


def _html_email_test(result):
    """Build HTML sections for full email test results."""
    sections = []

    # Placement summary
    placement = _safe_get(result, "placement") or {}
    if placement:
        folder = placement.get("folder", placement.get("placement", "unknown"))
        provider = placement.get("provider", "")
        tab = placement.get("tab", "")
        p_status = folder.lower()
        color = GREEN if p_status == "inbox" else RED if p_status in ("spam", "trash") else AMBER
        tab_html = f' &middot; Tab: <strong>{tab}</strong>' if tab and tab != "None" else ""
        sections.append(f"""
        <div class="section">
            <h3>Inbox Placement</h3>
            <div class="score-grid">
                <div class="score-card">
                    <div class="score-value" style="color:{color};">{folder.title()}</div>
                    <div class="score-label">Landed In</div>
                </div>
                {"<div class='score-card'><div class='score-value'>" + provider.title() + "</div><div class='score-label'>Provider</div></div>" if provider else ""}
                {"<div class='score-card'><div class='score-value'>" + tab.title() + "</div><div class='score-label'>Gmail Tab</div></div>" if tab and tab != 'None' else ""}
            </div>
        </div>""")

    # Authentication header grades
    header_grades = _safe_get(result, "header_grades") or []
    if header_grades:
        rows = ""
        for hg in header_grades:
            if not isinstance(hg, dict):
                continue
            label = hg.get("label", "")
            status = hg.get("status", "")
            verdict = hg.get("verdict", "")
            detail = hg.get("detail", "")
            color = _status_color(status)
            rows += f"""
            <tr>
                <td style="font-weight:600;">{label}</td>
                <td style="color:{color};font-weight:600;">{status.title()}</td>
                <td>{verdict}</td>
                <td style="font-size:12px;color:#475569;">{detail[:120]}</td>
            </tr>"""
        sections.append(f"""
        <div class="section">
            <h3>Email Authentication &amp; Headers</h3>
            <table class="data-table">
                <thead><tr><th>Check</th><th>Status</th><th>Verdict</th><th>Details</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>""")

    # Spam / Copy / Readability scores
    score_cards = ""
    for key, label in [("spam", "Spam"), ("copy", "Copy"), ("readability", "Readability")]:
        section_data = _safe_get(result, key) or {}
        if isinstance(section_data, dict):
            s = section_data.get("score")
            g = section_data.get("grade")
            if s is not None:
                color = _score_color(s)
                score_cards += f"""
                <div class="score-card">
                    <div class="score-value" style="color:{color};">{s}<span style="font-size:14px;color:#94a3b8;">{"/" + str(g) if g else ""}</span></div>
                    <div class="score-label">{label}</div>
                </div>"""
    if score_cards:
        sections.append(f'<div class="section"><h3>Content Analysis</h3><div class="score-grid">{score_cards}</div></div>')

    # Spam issues
    spam_data = _safe_get(result, "spam") or {}
    spam_issues = spam_data.get("issues") or []
    if spam_issues:
        items = ""
        for issue in spam_issues[:15]:
            if isinstance(issue, dict):
                text = issue.get("text", issue.get("message", str(issue)))
                severity = issue.get("severity", "")
                color = RED if str(severity).lower() == "high" else AMBER
            else:
                text = str(issue)
                color = AMBER
            items += f'<li style="color:{color};">{text}</li>'
        sections.append(f'<div class="section"><h3>Spam Issues</h3><ul class="issue-list">{items}</ul></div>')

    # Spam triggers
    triggers = spam_data.get("triggers") or []
    if triggers:
        trigger_list = ", ".join(str(t) for t in triggers[:20])
        sections.append(f'<div class="section"><h3>Spam Triggers</h3><p style="color:{RED};">{trigger_list}</p></div>')

    # Transport / TLS
    transport = _safe_get(result, "headers", "transport") or {}
    if transport:
        tls_used = transport.get("tls_used", False)
        tls_ver = transport.get("tls_version", "")
        hops = transport.get("hop_count", "")
        sender_ip = transport.get("sender_ip", "")
        tls_color = GREEN if tls_used else RED
        sections.append(f"""
        <div class="section">
            <h3>Transport Security</h3>
            <table class="data-table">
                <thead><tr><th>Property</th><th>Value</th></tr></thead>
                <tbody>
                    <tr><td>TLS Encryption</td><td style="color:{tls_color};font-weight:600;">{"Yes" if tls_used else "No"}{" — " + tls_ver if tls_ver else ""}</td></tr>
                    {"<tr><td>Sender IP</td><td>" + sender_ip + "</td></tr>" if sender_ip else ""}
                    {"<tr><td>Hop Count</td><td>" + str(hops) + "</td></tr>" if hops else ""}
                </tbody>
            </table>
        </div>""")

    # Audit summary (passed/warnings/failed)
    audit = _safe_get(result, "audit") or {}
    if audit:
        for category, label, color in [("failed", "Failed Checks", RED), ("warnings", "Warnings", AMBER), ("passed", "Passed Checks", GREEN)]:
            items_list = audit.get(category) or []
            if items_list:
                items_html = ""
                for item in items_list[:10]:
                    text = item.get("text", item.get("label", str(item))) if isinstance(item, dict) else str(item)
                    items_html += f'<li style="color:{color};">{text}</li>'
                sections.append(f'<div class="section"><h3>{label}</h3><ul>{items_html}</ul></div>')

    return "\n".join(sections)


def _html_placement_test(result):
    """Build HTML sections for inbox placement test results."""
    sections = []

    results_list = _safe_get(result, "results") or _safe_get(result, "placements") or []
    if isinstance(results_list, list) and results_list:
        rows = ""
        inbox_count = 0
        total = len(results_list)
        for r in results_list:
            if isinstance(r, dict):
                provider = r.get("provider", r.get("label", ""))
                folder = r.get("folder", r.get("placement", "unknown"))
                tab = r.get("tab", "")
                f_lower = str(folder).lower()
                if f_lower == "inbox":
                    inbox_count += 1
                color = GREEN if f_lower == "inbox" else RED if f_lower in ("spam", "trash") else AMBER
                tab_html = f" ({tab})" if tab and tab != "None" else ""
                rows += f"""
                <tr>
                    <td style="font-weight:600;">{provider}</td>
                    <td style="color:{color};font-weight:600;">{folder.title()}{tab_html}</td>
                </tr>"""

        pct = int(inbox_count / total * 100) if total else 0
        pct_color = GREEN if pct >= 80 else AMBER if pct >= 50 else RED
        sections.append(f"""
        <div class="section">
            <h3>Placement Summary</h3>
            <div class="score-grid">
                <div class="score-card">
                    <div class="score-value" style="color:{pct_color};">{pct}%</div>
                    <div class="score-label">Inbox Rate</div>
                </div>
                <div class="score-card">
                    <div class="score-value">{inbox_count}/{total}</div>
                    <div class="score-label">Inboxed</div>
                </div>
            </div>
        </div>
        <div class="section">
            <h3>Provider Breakdown</h3>
            <table class="data-table">
                <thead><tr><th>Provider</th><th>Placement</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>""")

    # If there's auth data embedded
    auth_sections = _html_domain_check(result)
    if auth_sections.strip():
        sections.append(auth_sections)

    return "\n".join(sections)


def generate_report_html(result_data, tool, domain_or_input, created_at=None, grade=None, score=None):
    """
    Generate a styled HTML report from check results.

    Args:
        result_data: dict — deserialized result_json from check_history
        tool: str — tool name (e.g. "domain_check", "copy_analysis")
        domain_or_input: str — the domain or input tested
        created_at: str/datetime — when the check was run
        grade: str — overall grade (A+, B, etc.)
        score: int/float — overall score
    Returns:
        str — complete HTML document
    """
    if not isinstance(result_data, dict):
        result_data = {}

    # Use values from result_data if not passed directly
    if grade is None:
        grade = _safe_get(result_data, "grade") or _safe_get(result_data, "overall_grade")
    if score is None:
        score = _safe_get(result_data, "score") or _safe_get(result_data, "overall_score")

    date_str = _format_date(created_at)
    tool_display = tool.replace("_", " ").title() if tool else "Report"

    # Build tool-specific sections
    tool_lower = (tool or "").lower()
    if tool_lower == "email_test":
        body_sections = _html_email_test(result_data)
    elif tool_lower == "placement_test":
        body_sections = _html_placement_test(result_data)
    elif "domain" in tool_lower or "reputation" in tool_lower or "auth" in tool_lower or "deliverability" in tool_lower:
        body_sections = _html_domain_check(result_data)
    elif "copy" in tool_lower or "spam" in tool_lower or "analyz" in tool_lower or "readability" in tool_lower:
        body_sections = _html_copy_analysis(result_data)
    elif "verif" in tool_lower or "email_check" in tool_lower:
        body_sections = _html_email_verification(result_data)
    elif "subject" in tool_lower:
        body_sections = _html_subject_scoring(result_data)
    else:
        # Generic: try all section builders, keep what has content
        parts = []
        for builder in (_html_email_test, _html_placement_test, _html_domain_check, _html_copy_analysis, _html_email_verification, _html_subject_scoring):
            s = builder(result_data)
            if s.strip():
                parts.append(s)
        body_sections = "\n".join(parts) if parts else "<p>No detailed data available for this result.</p>"

    # Grade/score header
    grade_html = ""
    if grade or score is not None:
        grade_html = '<div class="grade-bar">'
        if grade:
            gc = _grade_color(grade)
            grade_html += f'<div class="grade-badge" style="background:{gc};">{grade}</div>'
        if score is not None:
            sc = _score_color(score)
            grade_html += f'<div class="score-badge" style="color:{sc};">{score}<span style="font-size:16px;color:#94a3b8;">/100</span></div>'
        grade_html += "</div>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>INBXR Report — {tool_display}</title>
<style>
    @media print {{
        body {{ margin: 0; padding: 20px; }}
        .no-print {{ display: none !important; }}
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        color: {DARK};
        background: #fff;
        line-height: 1.6;
        padding: 40px;
        max-width: 900px;
        margin: 0 auto;
    }}
    .header {{
        border-bottom: 3px solid {BRAND_BLUE};
        padding-bottom: 20px;
        margin-bottom: 30px;
    }}
    .brand {{
        font-size: 28px;
        font-weight: 800;
        color: {BRAND_BLUE};
        letter-spacing: -0.5px;
    }}
    .brand span {{
        color: {DARK};
    }}
    .meta {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 12px;
        flex-wrap: wrap;
        gap: 8px;
    }}
    .meta-item {{
        font-size: 14px;
        color: {GRAY};
    }}
    .meta-item strong {{
        color: {DARK};
    }}
    .tool-badge {{
        display: inline-block;
        background: {BRAND_BLUE};
        color: #fff;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
    }}
    .grade-bar {{
        display: flex;
        align-items: center;
        gap: 20px;
        margin: 24px 0;
        padding: 20px;
        background: {LIGHT_BG};
        border-radius: 12px;
    }}
    .grade-badge {{
        font-size: 36px;
        font-weight: 800;
        color: #fff;
        width: 70px;
        height: 70px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 14px;
    }}
    .score-badge {{
        font-size: 42px;
        font-weight: 800;
    }}
    .section {{
        margin-bottom: 28px;
    }}
    .section h3 {{
        font-size: 18px;
        font-weight: 700;
        color: {DARK};
        margin-bottom: 12px;
        padding-bottom: 6px;
        border-bottom: 1px solid #e2e8f0;
    }}
    .data-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }}
    .data-table th {{
        text-align: left;
        padding: 10px 12px;
        background: {LIGHT_BG};
        font-weight: 600;
        font-size: 13px;
        color: {GRAY};
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    .data-table td {{
        padding: 10px 12px;
        border-bottom: 1px solid #f1f5f9;
    }}
    .score-grid {{
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
    }}
    .score-card {{
        background: {LIGHT_BG};
        border-radius: 10px;
        padding: 20px 28px;
        text-align: center;
        min-width: 120px;
    }}
    .score-value {{
        font-size: 32px;
        font-weight: 800;
    }}
    .score-label {{
        font-size: 13px;
        color: {GRAY};
        margin-top: 4px;
    }}
    ul {{
        padding-left: 20px;
    }}
    li {{
        margin-bottom: 6px;
    }}
    .rec-list li {{
        color: {DARK};
    }}
    .issue-list li {{
        margin-bottom: 8px;
    }}
    .footer {{
        margin-top: 40px;
        padding-top: 16px;
        border-top: 1px solid #e2e8f0;
        text-align: center;
        font-size: 12px;
        color: {GRAY};
    }}
</style>
</head>
<body>
    <div class="header">
        <div class="brand">INBXR<span> Report</span></div>
        <div class="meta">
            <span class="tool-badge">{tool_display}</span>
            <span class="meta-item"><strong>Input:</strong> {domain_or_input}</span>
            <span class="meta-item"><strong>Date:</strong> {date_str}</span>
        </div>
    </div>

    {grade_html}

    {body_sections}

    <div class="footer">
        Generated by INBXR — Email Intelligence Platform &middot; {date_str}
    </div>
</body>
</html>"""
    return html


# ══════════════════════════════════════════════════════════
#  PDF REPORT (reportlab)
# ══════════════════════════════════════════════════════════

def _build_styles():
    """Create custom paragraph styles for the PDF."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "BrandTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        textColor=HexColor(BRAND_BLUE),
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "SectionHead",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=HexColor(DARK),
        spaceBefore=16,
        spaceAfter=8,
        borderWidth=0,
        borderPadding=0,
    ))
    styles.add(ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=HexColor(GRAY),
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        "BodyText14",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=HexColor(DARK),
        spaceAfter=4,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        "GradeText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=28,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "ScoreText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=22,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "FooterText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=HexColor(GRAY),
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "CellText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=HexColor(DARK),
        leading=12,
    ))
    styles.add(ParagraphStyle(
        "CellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=HexColor(DARK),
        leading=12,
    ))

    return styles


def _make_table(headers, rows, col_widths=None):
    """Build a styled Table flowable."""
    table_data = [headers] + rows
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor(GRAY)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#e2e8f0")),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, HexColor("#f1f5f9")),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, HexColor("#e2e8f0")),
    ]))
    return t


def _colored_text(text, color, bold=False):
    """Return a Paragraph with colored text for use in table cells."""
    font = "Helvetica-Bold" if bold else "Helvetica"
    return Paragraph(f'<font color="{color}" face="{font}">{text}</font>',
                     ParagraphStyle("inline", fontSize=9, leading=12))


def _pdf_domain_check(result, styles, story, page_width):
    """Add domain check sections to the PDF story."""
    # Auth records
    auth_data = _safe_get(result, "authentication") or _safe_get(result, "auth") or {}
    if not auth_data:
        for key in ("spf", "dkim", "dmarc"):
            val = _safe_get(result, key)
            if val:
                auth_data[key] = val

    if auth_data:
        story.append(Paragraph("Email Authentication", styles["SectionHead"]))
        rows = []
        for protocol in ("spf", "dkim", "dmarc"):
            rec = auth_data.get(protocol, {})
            if isinstance(rec, dict):
                status = rec.get("status", rec.get("result", "unknown"))
                detail = rec.get("record", rec.get("value", rec.get("details", "")))
            else:
                status = str(rec)
                detail = ""
            color = _status_color(status)
            rows.append([
                Paragraph(f"<b>{protocol.upper()}</b>", styles["CellText"]),
                _colored_text(str(status).title(), color, bold=True),
                Paragraph(str(detail)[:120], styles["CellText"]),
            ])
        story.append(_make_table(["Protocol", "Status", "Record"], rows,
                                 col_widths=[70, 80, page_width - 150 - 80]))
        story.append(Spacer(1, 10))

    # Blocklist
    blocklist = _safe_get(result, "blocklist") or _safe_get(result, "blacklist") or _safe_get(result, "blocklists") or {}
    if blocklist:
        story.append(Paragraph("Blocklist Check", styles["SectionHead"]))
        listed_on = []
        clean_count = 0
        if isinstance(blocklist, dict):
            items = blocklist.get("results", blocklist.get("lists", blocklist))
            if isinstance(items, dict):
                for name, info in items.items():
                    if name in ("listed_count", "total_checked", "clean_count", "summary"):
                        continue
                    if isinstance(info, dict):
                        is_listed = info.get("listed", False)
                    else:
                        is_listed = bool(info)
                    if is_listed:
                        listed_on.append(name)
                    else:
                        clean_count += 1
            elif isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        if item.get("listed", False):
                            listed_on.append(item.get("name", item.get("list", "")))
                        else:
                            clean_count += 1

        total = len(listed_on) + clean_count
        if listed_on:
            story.append(Paragraph(
                f'<font color="{RED}"><b>Listed on {len(listed_on)} of {total} lists:</b></font> '
                + ", ".join(listed_on),
                styles["BodyText14"]
            ))
        else:
            story.append(Paragraph(
                f'<font color="{GREEN}"><b>Clean</b></font> — not listed on any of {total} lists checked',
                styles["BodyText14"]
            ))
        story.append(Spacer(1, 10))

    # Category scores
    categories = _safe_get(result, "categories") or _safe_get(result, "scores") or {}
    if isinstance(categories, dict) and categories:
        story.append(Paragraph("Category Scores", styles["SectionHead"]))
        rows = []
        for cat, val in categories.items():
            if isinstance(val, dict):
                score_val = val.get("score", val.get("value", ""))
                label = val.get("label", val.get("status", ""))
            else:
                score_val = val
                label = ""
            color = _score_color(score_val) if isinstance(score_val, (int, float)) else GRAY
            rows.append([
                Paragraph(cat.replace("_", " ").title(), styles["CellBold"]),
                _colored_text(str(score_val), color, bold=True),
                Paragraph(str(label), styles["CellText"]),
            ])
        story.append(_make_table(["Category", "Score", "Status"], rows,
                                 col_widths=[160, 80, page_width - 240 - 80]))
        story.append(Spacer(1, 10))

    # Recommendations
    recs = _safe_get(result, "recommendations") or _safe_get(result, "suggestions") or []
    if isinstance(recs, list) and recs:
        story.append(Paragraph("Recommendations", styles["SectionHead"]))
        for r in recs:
            if isinstance(r, dict):
                text = r.get("text", r.get("message", str(r)))
            else:
                text = str(r)
            story.append(Paragraph(f"&bull; {text}", styles["BodyText14"]))
        story.append(Spacer(1, 10))


def _pdf_copy_analysis(result, styles, story, page_width):
    """Add copy analysis sections to the PDF story."""
    # Scores
    score_items = []
    for key, label in [
        ("spam_score", "Spam Score"),
        ("copy_score", "Copy Score"),
        ("readability_score", "Readability"),
        ("readability", "Readability"),
        ("overall_score", "Overall"),
    ]:
        val = _safe_get(result, key)
        if val is not None:
            if isinstance(val, dict):
                val = val.get("score", val.get("value", ""))
            score_items.append((label, val))

    if score_items:
        story.append(Paragraph("Scores", styles["SectionHead"]))
        row = []
        for label, val in score_items:
            color = _score_color(val)
            row.append(Paragraph(
                f'<font color="{color}" size="16"><b>{val}</b></font><br/>'
                f'<font color="{GRAY}" size="8">{label}</font>',
                ParagraphStyle("scoreCell", alignment=TA_CENTER, fontSize=10, leading=20)
            ))
        t = Table([row], colWidths=[page_width / len(row)] * len(row))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor(LIGHT_BG)),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # Issues
    issues = _safe_get(result, "issues") or _safe_get(result, "warnings") or _safe_get(result, "problems") or []
    if isinstance(issues, list) and issues:
        story.append(Paragraph("Issues Found", styles["SectionHead"]))
        for issue in issues[:20]:
            if isinstance(issue, dict):
                text = issue.get("message", issue.get("text", issue.get("issue", str(issue))))
                severity = issue.get("severity", issue.get("level", ""))
                color = RED if str(severity).lower() in ("high", "critical", "error") else AMBER
            else:
                text = str(issue)
                color = AMBER
            story.append(Paragraph(f'<font color="{color}">&bull;</font> {text}', styles["BodyText14"]))
        story.append(Spacer(1, 10))

    # Spam triggers
    triggers = _safe_get(result, "spam_triggers") or _safe_get(result, "triggers") or []
    if isinstance(triggers, list) and triggers:
        story.append(Paragraph("Spam Triggers", styles["SectionHead"]))
        items = []
        for t in triggers[:15]:
            if isinstance(t, dict):
                word = t.get("word", t.get("trigger", t.get("text", str(t))))
            else:
                word = str(t)
            items.append(word)
        story.append(Paragraph(
            f'<font color="{RED}">' + " &middot; ".join(items) + "</font>",
            styles["BodyText14"]
        ))
        story.append(Spacer(1, 10))


def _pdf_email_verification(result, styles, story, page_width):
    """Add email verification sections to the PDF story."""
    verdict = _safe_get(result, "verdict") or _safe_get(result, "result") or _safe_get(result, "status") or ""
    score = _safe_get(result, "score") or _safe_get(result, "confidence") or ""

    story.append(Paragraph("Verification Result", styles["SectionHead"]))
    cells = []
    if verdict:
        color = _status_color(verdict)
        cells.append(Paragraph(
            f'<font color="{color}" size="16"><b>{str(verdict).title()}</b></font><br/>'
            f'<font color="{GRAY}" size="8">Verdict</font>',
            ParagraphStyle("vCell", alignment=TA_CENTER, fontSize=10, leading=20)
        ))
    if score:
        color = _score_color(score)
        cells.append(Paragraph(
            f'<font color="{color}" size="16"><b>{score}</b></font><br/>'
            f'<font color="{GRAY}" size="8">Score</font>',
            ParagraphStyle("sCell", alignment=TA_CENTER, fontSize=10, leading=20)
        ))
    if cells:
        t = Table([cells], colWidths=[page_width / len(cells)] * len(cells))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor(LIGHT_BG)),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # Checks table
    checks = _safe_get(result, "checks") or {}
    if isinstance(checks, dict) and checks:
        story.append(Paragraph("Checks", styles["SectionHead"]))
        rows = []
        for check_name, check_val in checks.items():
            if isinstance(check_val, dict):
                passed = check_val.get("passed", check_val.get("valid", check_val.get("result", False)))
                detail = check_val.get("detail", check_val.get("message", ""))
            else:
                passed = bool(check_val)
                detail = ""
            status = "Pass" if passed else "Fail"
            color = GREEN if passed else RED
            rows.append([
                Paragraph(check_name.replace("_", " ").title(), styles["CellBold"]),
                _colored_text(status, color, bold=True),
                Paragraph(str(detail)[:100], styles["CellText"]),
            ])
        story.append(_make_table(["Check", "Result", "Details"], rows,
                                 col_widths=[140, 70, page_width - 210 - 80]))
        story.append(Spacer(1, 10))


def _pdf_subject_scoring(result, styles, story, page_width):
    """Add subject scoring sections to the PDF story."""
    subjects = _safe_get(result, "subjects") or _safe_get(result, "results") or []
    if not isinstance(subjects, list) or not subjects:
        return

    story.append(Paragraph("Subject Lines", styles["SectionHead"]))
    rows = []
    for i, subj in enumerate(subjects, 1):
        if isinstance(subj, dict):
            text = subj.get("subject", subj.get("text", subj.get("line", "")))
            score = subj.get("score", subj.get("rating", ""))
            notes = subj.get("feedback", subj.get("notes", subj.get("reason", "")))
        else:
            text = str(subj)
            score = ""
            notes = ""
        color = _score_color(score) if score else GRAY
        rows.append([
            Paragraph(f"<b>#{i}</b>", styles["CellText"]),
            Paragraph(str(text)[:80], styles["CellText"]),
            _colored_text(str(score), color, bold=True),
            Paragraph(str(notes)[:100], styles["CellText"]),
        ])
    story.append(_make_table(["#", "Subject", "Score", "Feedback"], rows,
                             col_widths=[30, page_width - 30 - 60 - 160 - 80, 60, 160]))
    story.append(Spacer(1, 10))


def _pdf_email_test(result, styles, story, page_width):
    """Add email test sections to the PDF story."""
    # Placement summary
    placement = _safe_get(result, "placement") or {}
    if placement:
        folder = placement.get("folder", placement.get("placement", "unknown"))
        provider = placement.get("provider", "")
        tab = placement.get("tab", "")
        p_status = folder.lower()
        color = GREEN if p_status == "inbox" else RED if p_status in ("spam", "trash") else AMBER

        cells = [Paragraph(
            f'<font color="{color}" size="16"><b>{folder.title()}</b></font><br/>'
            f'<font color="{GRAY}" size="8">Landed In</font>',
            ParagraphStyle("pCell", alignment=TA_CENTER, fontSize=10, leading=20)
        )]
        if provider:
            cells.append(Paragraph(
                f'<font size="14"><b>{provider.title()}</b></font><br/>'
                f'<font color="{GRAY}" size="8">Provider</font>',
                ParagraphStyle("prCell", alignment=TA_CENTER, fontSize=10, leading=20)
            ))
        if tab and tab != "None":
            cells.append(Paragraph(
                f'<font size="14"><b>{tab.title()}</b></font><br/>'
                f'<font color="{GRAY}" size="8">Gmail Tab</font>',
                ParagraphStyle("tCell", alignment=TA_CENTER, fontSize=10, leading=20)
            ))

        story.append(Paragraph("Inbox Placement", styles["SectionHead"]))
        t = Table([cells], colWidths=[page_width / len(cells)] * len(cells))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor(LIGHT_BG)),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # Header grades table
    header_grades = _safe_get(result, "header_grades") or []
    if header_grades:
        story.append(Paragraph("Email Authentication &amp; Headers", styles["SectionHead"]))
        rows = []
        for hg in header_grades:
            if not isinstance(hg, dict):
                continue
            label = hg.get("label", "")
            status = hg.get("status", "")
            verdict = hg.get("verdict", "")
            detail = hg.get("detail", "")
            color = _status_color(status)
            rows.append([
                Paragraph(f"<b>{label}</b>", styles["CellText"]),
                _colored_text(status.title(), color, bold=True),
                Paragraph(str(verdict)[:60], styles["CellText"]),
                Paragraph(str(detail)[:80], styles["CellText"]),
            ])
        story.append(_make_table(
            ["Check", "Status", "Verdict", "Details"], rows,
            col_widths=[100, 60, 120, page_width - 280 - 80]
        ))
        story.append(Spacer(1, 10))

    # Content scores
    score_items = []
    for key, label in [("spam", "Spam"), ("copy", "Copy"), ("readability", "Readability")]:
        section_data = _safe_get(result, key) or {}
        if isinstance(section_data, dict):
            s = section_data.get("score")
            if s is not None:
                score_items.append((label, s))

    if score_items:
        story.append(Paragraph("Content Analysis", styles["SectionHead"]))
        cells = []
        for label, val in score_items:
            color = _score_color(val)
            cells.append(Paragraph(
                f'<font color="{color}" size="16"><b>{val}</b></font><br/>'
                f'<font color="{GRAY}" size="8">{label}</font>',
                ParagraphStyle("csCell", alignment=TA_CENTER, fontSize=10, leading=20)
            ))
        t = Table([cells], colWidths=[page_width / len(cells)] * len(cells))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor(LIGHT_BG)),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # Spam issues
    spam_data = _safe_get(result, "spam") or {}
    spam_issues = spam_data.get("issues") or []
    if spam_issues:
        story.append(Paragraph("Spam Issues", styles["SectionHead"]))
        for issue in spam_issues[:15]:
            if isinstance(issue, dict):
                text = issue.get("text", issue.get("message", str(issue)))
                severity = issue.get("severity", "")
                color = RED if str(severity).lower() == "high" else AMBER
            else:
                text = str(issue)
                color = AMBER
            story.append(Paragraph(f'<font color="{color}">&bull;</font> {text}', styles["BodyText14"]))
        story.append(Spacer(1, 10))

    # Transport
    transport = _safe_get(result, "headers", "transport") or {}
    if transport:
        story.append(Paragraph("Transport Security", styles["SectionHead"]))
        tls_used = transport.get("tls_used", False)
        tls_ver = transport.get("tls_version", "")
        sender_ip = transport.get("sender_ip", "")
        tls_color = GREEN if tls_used else RED
        rows = [
            [Paragraph("<b>TLS Encryption</b>", styles["CellText"]),
             _colored_text("Yes" + (f" — {tls_ver}" if tls_ver else "") if tls_used else "No", tls_color, bold=True)],
        ]
        if sender_ip:
            rows.append([Paragraph("<b>Sender IP</b>", styles["CellText"]),
                         Paragraph(sender_ip, styles["CellText"])])
        story.append(_make_table(["Property", "Value"], rows,
                                 col_widths=[140, page_width - 140 - 80]))
        story.append(Spacer(1, 10))

    # Audit summary
    audit = _safe_get(result, "audit") or {}
    for category, label in [("failed", "Failed Checks"), ("warnings", "Warnings")]:
        items_list = audit.get(category) or []
        if items_list:
            story.append(Paragraph(label, styles["SectionHead"]))
            color = RED if category == "failed" else AMBER
            for item in items_list[:10]:
                text = item.get("text", item.get("label", str(item))) if isinstance(item, dict) else str(item)
                story.append(Paragraph(f'<font color="{color}">&bull;</font> {text}', styles["BodyText14"]))
            story.append(Spacer(1, 10))


def _pdf_placement_test(result, styles, story, page_width):
    """Add placement test sections to the PDF story."""
    results_list = _safe_get(result, "results") or _safe_get(result, "placements") or []
    if not isinstance(results_list, list) or not results_list:
        return

    inbox_count = 0
    total = len(results_list)
    rows = []
    for r in results_list:
        if not isinstance(r, dict):
            continue
        provider = r.get("provider", r.get("label", ""))
        folder = r.get("folder", r.get("placement", "unknown"))
        tab = r.get("tab", "")
        f_lower = str(folder).lower()
        if f_lower == "inbox":
            inbox_count += 1
        color = GREEN if f_lower == "inbox" else RED if f_lower in ("spam", "trash") else AMBER
        tab_text = f" ({tab})" if tab and tab != "None" else ""
        rows.append([
            Paragraph(f"<b>{provider}</b>", styles["CellText"]),
            _colored_text(f"{folder.title()}{tab_text}", color, bold=True),
        ])

    pct = int(inbox_count / total * 100) if total else 0
    pct_color = GREEN if pct >= 80 else AMBER if pct >= 50 else RED

    # Summary cards
    story.append(Paragraph("Placement Summary", styles["SectionHead"]))
    cells = [
        Paragraph(
            f'<font color="{pct_color}" size="16"><b>{pct}%</b></font><br/>'
            f'<font color="{GRAY}" size="8">Inbox Rate</font>',
            ParagraphStyle("irCell", alignment=TA_CENTER, fontSize=10, leading=20)
        ),
        Paragraph(
            f'<font size="14"><b>{inbox_count}/{total}</b></font><br/>'
            f'<font color="{GRAY}" size="8">Inboxed</font>',
            ParagraphStyle("inCell", alignment=TA_CENTER, fontSize=10, leading=20)
        ),
    ]
    t = Table([cells], colWidths=[page_width / 2] * 2)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor(LIGHT_BG)),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # Provider breakdown
    story.append(Paragraph("Provider Breakdown", styles["SectionHead"]))
    story.append(_make_table(["Provider", "Placement"], rows,
                             col_widths=[page_width / 2, page_width / 2]))
    story.append(Spacer(1, 10))

    # Auth data if present
    _pdf_domain_check(result, styles, story, page_width)


def generate_report(result_data, tool, domain_or_input, created_at=None, grade=None, score=None):
    """
    Generate a PDF report from check results.

    Args:
        result_data: dict — deserialized result_json from check_history
        tool: str — tool name
        domain_or_input: str — the domain or input tested
        created_at: str/datetime — when the check was run
        grade: str — overall grade
        score: int/float — overall score
    Returns:
        bytes — PDF file contents, or None if reportlab is not available
    """
    if not HAS_REPORTLAB:
        return None

    if not isinstance(result_data, dict):
        result_data = {}

    # Use values from result_data if not passed directly
    if grade is None:
        grade = _safe_get(result_data, "grade") or _safe_get(result_data, "overall_grade")
    if score is None:
        score = _safe_get(result_data, "score") or _safe_get(result_data, "overall_score")

    date_str = _format_date(created_at)
    tool_display = tool.replace("_", " ").title() if tool else "Report"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=30 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    styles = _build_styles()
    story = []
    page_width = A4[0] - 40 * mm  # usable width

    # ── Header ──
    story.append(Paragraph("INBXR", styles["BrandTitle"]))
    story.append(Paragraph("Email Intelligence Report", styles["MetaText"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(
        width="100%", thickness=2,
        color=HexColor(BRAND_BLUE), spaceBefore=0, spaceAfter=10
    ))

    # Meta row as table
    meta_data = [[
        Paragraph(f'<b>Tool:</b> {tool_display}', styles["MetaText"]),
        Paragraph(f'<b>Input:</b> {domain_or_input}', styles["MetaText"]),
        Paragraph(f'<b>Date:</b> {date_str}', styles["MetaText"]),
    ]]
    meta_table = Table(meta_data, colWidths=[page_width / 3] * 3)
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # ── Grade / Score ──
    if grade or score is not None:
        grade_cells = []
        if grade:
            gc = _grade_color(grade)
            grade_cells.append(Paragraph(
                f'<font color="{gc}" size="28"><b>{grade}</b></font>',
                ParagraphStyle("gradeInline", alignment=TA_CENTER, fontSize=28, leading=36)
            ))
        if score is not None:
            sc = _score_color(score)
            grade_cells.append(Paragraph(
                f'<font color="{sc}" size="22"><b>{score}</b></font>'
                f'<font color="{GRAY}" size="12">/100</font>',
                ParagraphStyle("scoreInline", alignment=TA_CENTER, fontSize=22, leading=30)
            ))
        if grade_cells:
            gt = Table([grade_cells], colWidths=[page_width / len(grade_cells)] * len(grade_cells))
            gt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), HexColor(LIGHT_BG)),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ]))
            story.append(gt)
            story.append(Spacer(1, 14))

    # ── Tool-specific content ──
    tool_lower = (tool or "").lower()
    if tool_lower == "email_test":
        _pdf_email_test(result_data, styles, story, page_width)
    elif tool_lower == "placement_test":
        _pdf_placement_test(result_data, styles, story, page_width)
    elif "domain" in tool_lower or "reputation" in tool_lower or "auth" in tool_lower or "deliverability" in tool_lower:
        _pdf_domain_check(result_data, styles, story, page_width)
    elif "copy" in tool_lower or "spam" in tool_lower or "analyz" in tool_lower or "readability" in tool_lower:
        _pdf_copy_analysis(result_data, styles, story, page_width)
    elif "verif" in tool_lower or "email_check" in tool_lower:
        _pdf_email_verification(result_data, styles, story, page_width)
    elif "subject" in tool_lower:
        _pdf_subject_scoring(result_data, styles, story, page_width)
    else:
        for builder in (_pdf_email_test, _pdf_placement_test, _pdf_domain_check, _pdf_copy_analysis, _pdf_email_verification, _pdf_subject_scoring):
            builder(result_data, styles, story, page_width)

    # ── Footer ──
    story.append(Spacer(1, 20))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=HexColor("#e2e8f0"), spaceBefore=0, spaceAfter=8
    ))
    story.append(Paragraph(
        f"Generated by INBXR — Email Intelligence Platform &middot; {date_str}",
        styles["FooterText"]
    ))

    doc.build(story)
    return buffer.getvalue()
