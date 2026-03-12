"""
INBXR — Email Intelligence Platform
Flask backend: analysis API + file parsing + admin editor + user auth.
"""

import re
import os
import tempfile

# ── Load .env file if present (no dependencies) ──────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())
import mailbox
import email as email_lib
from email import policy as email_policy
import ipaddress
from datetime import timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)

# ── Secret key for sessions ──────────────────────────────
app.secret_key = os.environ.get("SECRET_KEY", "inbxr-dev-secret-change-in-production")

# ── Max upload size: 10 MB ──────────────────────────────
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# ── Permanent session lifetime ───────────────────────────
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# ── Initialize database and register blueprints ─────────
from modules.database import init_db
init_db()

from blueprints.auth_routes import auth_bp
app.register_blueprint(auth_bp)

from blueprints.history_routes import history_bp
app.register_blueprint(history_bp)

from blueprints.bulk_routes import bulk_bp
app.register_blueprint(bulk_bp)

from blueprints.pdf_routes import pdf_bp
app.register_blueprint(pdf_bp)

from blueprints.monitor_routes import monitor_bp
app.register_blueprint(monitor_bp)

from blueprints.billing_routes import billing_bp
app.register_blueprint(billing_bp)

from blueprints.team_routes import team_bp
app.register_blueprint(team_bp)

from modules.scheduler import init_scheduler
init_scheduler(app)

# ── Admin credentials (set via env vars in production) ──
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "inbxr2026")


def _get_inline_overrides_json(page_name):
    """Get inline text overrides as a JSON string for injection."""
    import json as _json
    from modules.page_config import get_inline_overrides
    overrides = get_inline_overrides(page_name)
    return _json.dumps(overrides) if overrides else ""


def _get_custom_css(page_name):
    """Generate a <style> block from saved style overrides for a page."""
    from modules.page_config import get_page_styles, get_global_theme
    lines = []
    # Global theme variables
    theme = get_global_theme()
    if theme:
        parts = []
        for var, val in theme.items():
            parts.append(f"  {var}: {val};")
        lines.append(":root {\n" + "\n".join(parts) + "\n}")
    # Per-element overrides
    styles = get_page_styles(page_name)
    for key, props in styles.items():
        # key format: "section_id::selector"
        parts = key.split("::", 1)
        if len(parts) != 2:
            continue
        section_id, selector = parts
        declarations = []
        for prop, val in props.items():
            declarations.append(f"  {prop}: {val};")
        if declarations:
            css_selector = f'[data-section-id="{section_id}"] {selector}'
            lines.append(css_selector + " {\n" + "\n".join(declarations) + "\n}")
    return "\n".join(lines)


# ── Inject user context into all templates ───────────────
@app.context_processor
def inject_user_context():
    """Make user session data available in all templates."""
    return {
        "current_user_id": session.get("user_id"),
        "current_user_email": session.get("user_email"),
        "current_user_tier": session.get("user_tier", "free"),
        "current_user_name": session.get("user_name"),
        "current_team_id": session.get("team_id"),
        "current_team_name": session.get("team_name"),
        "current_team_role": session.get("team_role"),
        "get_custom_css": _get_custom_css,
        "get_inline_overrides_json": _get_inline_overrides_json,
    }


# ══════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════

def _rate_limit_response(info):
    """Build a 429 JSON response with signup prompt for anon users."""
    if info.get("anonymous"):
        return jsonify({
            "error": "You've used your 3 free checks for today. Create a free account to keep going — it takes 10 seconds.",
            "limit_info": info,
            "signup_url": "/signup",
        }), 429
    return jsonify({
        "error": f"Rate limit exceeded ({info.get('blocked_by', 'daily')} limit). Upgrade your plan for higher limits.",
        "limit_info": info,
        "upgrade_url": "/pricing",
    }), 429

def _is_admin():
    return session.get("is_admin", False)


def _extract_ctas_from_body(body: str) -> tuple:
    """Auto-detect URLs and CTA text from the email body."""
    urls = list(set(re.findall(r'https?://[^\s<>"\')\]]+', body)))
    cta_text_patterns = [
        r'<a[^>]*>([^<]{3,60})</a>',
        r'\[([^\]]{3,50})\]\(https?://[^\)]+\)',
        r'(?i)((?:click|get|start|claim|grab|download|try|join|sign up|register|book|schedule|access|unlock|discover|buy|shop|order)\s[^.!?\n]{3,50})',
    ]
    cta_texts = []
    for pattern in cta_text_patterns:
        cta_texts.extend(re.findall(pattern, body, re.IGNORECASE)[:3])
    return urls[:20], list(set(cta_texts))[:10]


def _extract_body(msg) -> str:
    """Extract best available body (HTML preferred, plain text fallback)."""
    html_body = None
    plain_body = None

    def _decode_part(part):
        payload = part.get_payload(decode=True)
        if not payload:
            return str(part.get_payload() or "")
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            if ct == "text/html" and html_body is None:
                html_body = _decode_part(part)
            elif ct == "text/plain" and plain_body is None:
                plain_body = _decode_part(part)
    else:
        ct = msg.get_content_type()
        decoded = _decode_part(msg)
        if ct == "text/html":
            html_body = decoded
        else:
            plain_body = decoded

    if html_body:
        return html_body
    if plain_body:
        escaped = plain_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"<pre style='white-space:pre-wrap;font-family:inherit'>{escaped}</pre>"
    return ""


# ══════════════════════════════════════════════════════
#  ADMIN AUTH ROUTES
# ══════════════════════════════════════════════════════

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        if _is_admin():
            return redirect("/")
        return render_template("admin_login.html", error=None)

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "")

    if username == ADMIN_USER and password == ADMIN_PASS:
        session["is_admin"] = True
        return redirect("/")

    return render_template("admin_login.html", error="Invalid username or password.")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect("/")


# ══════════════════════════════════════════════════════
#  ADMIN API ENDPOINTS
# ══════════════════════════════════════════════════════

@app.route("/admin/api/reorder", methods=["POST"])
def admin_reorder():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    from modules.page_config import update_section_order
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    page = data.get("page", "")
    order = data.get("order", [])

    if not page or not order:
        return jsonify({"ok": False, "error": "Missing page or order"}), 400

    success = update_section_order(page, order)
    if not success:
        return jsonify({"ok": False, "error": "Page not found"}), 404
    return jsonify({"ok": True})


@app.route("/admin/api/update-content", methods=["POST"])
def admin_update_content():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    from modules.page_config import update_section_content
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    page = data.get("page", "")
    section_id = data.get("section_id", "")
    field = data.get("field", "")
    value = data.get("value", "")

    if not all([page, section_id, field]):
        return jsonify({"ok": False, "error": "Missing required fields"}), 400

    success = update_section_content(page, section_id, field, value)
    if not success:
        return jsonify({"ok": False, "error": "Section or field not found"}), 404
    return jsonify({"ok": True})


@app.route("/admin/api/update-chip", methods=["POST"])
def admin_update_chip():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    from modules.page_config import load_config, save_config
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    page = data.get("page", "")
    section_id = data.get("section_id", "")
    field = data.get("field", "")
    index = data.get("index", 0)
    value = data.get("value", "")

    cfg = load_config()
    page_cfg = cfg.get(page)
    if not page_cfg:
        return jsonify({"ok": False, "error": "Page not found"}), 404

    for s in page_cfg["sections"]:
        if s["id"] == section_id:
            arr = s["editable_fields"].get(field, [])
            if isinstance(arr, list) and 0 <= index < len(arr):
                arr[index] = value
                save_config(cfg)
                return jsonify({"ok": True})
            break

    return jsonify({"ok": False, "error": "Field not found"}), 404


@app.route("/admin/api/toggle-visibility", methods=["POST"])
def admin_toggle_visibility():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    from modules.page_config import load_config, save_config
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    page = data.get("page", "")
    section_id = data.get("section_id", "")
    visible = data.get("visible", True)

    cfg = load_config()
    page_cfg = cfg.get(page)
    if not page_cfg:
        return jsonify({"ok": False, "error": "Page not found"}), 404

    for s in page_cfg["sections"]:
        if s["id"] == section_id:
            s["visible"] = visible
            save_config(cfg)
            return jsonify({"ok": True})

    return jsonify({"ok": False, "error": "Section not found"}), 404


@app.route("/admin/api/update-inline", methods=["POST"])
def admin_update_inline():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from modules.page_config import update_inline_override
    data = request.get_json(force=True, silent=True) or {}
    field_key = data.get("field_key") or data.get("selector", "")
    ok = update_inline_override(data.get("page", ""), data.get("section_id", ""), field_key, data.get("value", ""))
    return jsonify({"ok": ok})


@app.route("/admin/api/update-styles", methods=["POST"])
def admin_update_styles():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from modules.page_config import update_element_styles
    data = request.get_json(force=True, silent=True) or {}
    ok = update_element_styles(data.get("page", ""), data.get("section_id", ""), data.get("selector", ""), data.get("styles", {}))
    return jsonify({"ok": ok})


@app.route("/admin/api/update-theme", methods=["POST"])
def admin_update_theme():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from modules.page_config import update_global_theme
    data = request.get_json(force=True, silent=True) or {}
    ok = update_global_theme(data.get("variable", ""), data.get("value", ""))
    return jsonify({"ok": ok})


@app.route("/admin/api/get-theme", methods=["GET"])
def admin_get_theme():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from modules.page_config import get_global_theme
    return jsonify({"ok": True, "theme": get_global_theme()})


@app.route("/admin/api/upload-image", methods=["POST"])
def admin_upload_image():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from modules.page_config import save_uploaded_image
    file = request.files.get("file")
    if not file:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    url = save_uploaded_image(file)
    if not url:
        return jsonify({"ok": False, "error": "Invalid file type. Allowed: png, jpg, gif, svg, webp"}), 400
    return jsonify({"ok": True, "url": url})


@app.route("/admin/api/section-library", methods=["GET"])
def admin_section_library():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from modules.page_config import get_section_library
    return jsonify({"ok": True, "sections": get_section_library()})


@app.route("/admin/api/add-section", methods=["POST"])
def admin_add_section():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from modules.page_config import add_section_to_page
    data = request.get_json(force=True, silent=True) or {}
    section_id = add_section_to_page(data.get("page", ""), data.get("type", ""), data.get("position", 0))
    if not section_id:
        return jsonify({"ok": False, "error": "Failed to add section"}), 400
    return jsonify({"ok": True, "section_id": section_id})


@app.route("/admin/api/remove-section", methods=["POST"])
def admin_remove_section():
    if not _is_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    from modules.page_config import remove_section_from_page
    data = request.get_json(force=True, silent=True) or {}
    ok = remove_section_from_page(data.get("page", ""), data.get("section_id", ""))
    return jsonify({"ok": ok})


# ══════════════════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════════════════

@app.route("/")
def index():
    from modules.page_config import get_page_sections
    sections = get_page_sections("email_test")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("email_test.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="index")


@app.route("/analyzer")
def analyzer():
    from modules.page_config import get_page_sections
    sections = get_page_sections("analyzer")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("index.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="analyzer")


@app.route("/sender")
def sender():
    from modules.page_config import get_page_sections
    sections = get_page_sections("sender")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("sender.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="sender")


@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next="/dashboard"))

    from modules.page_config import get_page_sections
    sections = get_page_sections("dashboard")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("dashboard.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="dashboard")


@app.route("/subject-scorer")
def subject_scorer():
    from modules.page_config import get_page_sections
    sections = get_page_sections("subject_scorer")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("subject_scorer.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="subject_scorer")


@app.route("/score-subjects", methods=["POST"])
def score_subjects():
    from modules.rate_limiter import check_rate_limit, log_usage
    allowed, info = check_rate_limit("subject_test", limit_key="subject_tests_per_day")
    if not allowed:
        return _rate_limit_response(info)

    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    subjects = data.get("subjects") or []
    industry = (data.get("industry") or "Other").strip()

    if not subjects or len(subjects) < 2:
        return jsonify({"error": "At least 2 subject lines required."}), 400

    # Sanitize — strip, limit to 10
    subjects = [s.strip() for s in subjects if s.strip()][:10]

    from modules.subject_scorer import score_subjects as do_score
    result = do_score(subjects, industry=industry)
    log_usage("subject_test")

    if session.get("user_id"):
        from modules.tiers import has_feature
        if has_feature(session.get("user_tier", "free"), "cloud_history"):
            from modules.history import save_result
            summary = "; ".join(subjects[:3])
            if len(subjects) > 3:
                summary += " ..."
            best = result.get("results", [{}])[0] if result.get("results") else {}
            save_result(session["user_id"], "subject_test", summary, result,
                        grade=best.get("grade"), score=best.get("score"))

    return jsonify(result)


@app.route("/email-test")
def email_test():
    return redirect("/", code=302)


@app.route("/email-test/start", methods=["POST"])
def email_test_start():
    from modules.inbox_placement import generate_token, get_seed_info

    seeds = get_seed_info()
    if not seeds:
        return jsonify({"error": "No seed accounts configured."}), 503

    # Use the first seed (primary Gmail account)
    seed = seeds[0]
    token = generate_token()
    return jsonify({"token": token, "seed_email": seed["email"], "provider": seed["provider"]})


@app.route("/email-test/check", methods=["POST"])
def email_test_check():
    from modules.inbox_placement import check_rate_limit as imap_rate_limit
    from modules.email_test import EmailTestFetcher, run_full_analysis

    if not imap_rate_limit():
        return jsonify({"error": "Rate limit exceeded. Please wait a minute."}), 429

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    token = (data.get("token") or "").strip()
    if not token or not re.match(r'^INBXR-[A-F0-9]{8}$', token):
        return jsonify({"error": "Invalid or missing test token."}), 400

    fetcher = EmailTestFetcher(token=token)
    fetch_result = fetcher.fetch()

    if fetch_result["status"] == "error":
        return jsonify({"error": fetch_result.get("error", "Fetch failed.")}), 500

    if fetch_result["status"] == "not_found":
        return jsonify({"status": "not_found", "elapsed_ms": fetch_result.get("elapsed_ms", 0)})

    # Run full analysis
    try:
        analysis = run_full_analysis(
            raw_bytes=fetch_result["raw_bytes"],
            placement=fetch_result["placement"],
            folder=fetch_result["folder"],
            tab=fetch_result["tab"],
            provider=fetch_result["provider"],
            seed_email=fetch_result["seed_email"],
        )
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)[:200]}"}), 500

    analysis["status"] = "found"
    return jsonify(analysis)


@app.route("/dns-generator")
def dns_generator():
    """Redirect to Domain Health which now generates fix records automatically."""
    return redirect("/domain-health", code=302)


@app.route("/bimi")
def bimi():
    from modules.page_config import get_page_sections
    sections = get_page_sections("bimi")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("bimi_checker.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="bimi")


@app.route("/placement")
def placement():
    from modules.page_config import get_page_sections
    sections = get_page_sections("placement")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("placement.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="placement")


@app.route("/placement/start", methods=["POST"])
def placement_start():
    from modules.inbox_placement import get_seed_info, generate_token

    seeds = get_seed_info()
    if not seeds:
        return jsonify({"error": "No seed accounts configured. Add accounts to config/seed_accounts.json"}), 503

    token = generate_token()
    return jsonify({"token": token, "seeds": seeds})


@app.route("/placement/check", methods=["POST"])
def placement_check():
    from modules.inbox_placement import (
        InboxPlacementTester, generate_recommendations, check_rate_limit,
    )

    if not check_rate_limit():
        return jsonify({"error": "Rate limit exceeded. Please wait a minute before checking again."}), 429

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    token = (data.get("token") or "").strip()
    if not token or not re.match(r'^INBXR-[A-F0-9]{8}$', token):
        return jsonify({"error": "Invalid or missing test token."}), 400

    tester = InboxPlacementTester(token=token)
    try:
        results = tester.check_all()
    except Exception as e:
        return jsonify({"error": f"Placement check failed: {e}"}), 500

    # Build summary
    total = len(results)
    inbox_count = sum(1 for r in results if r["placement"] == "inbox")
    spam_count = sum(1 for r in results if r["placement"] == "spam")
    not_found = sum(1 for r in results if r["placement"] == "not_found")

    summary = {
        "total": total,
        "inbox": inbox_count,
        "spam": spam_count,
        "not_found": not_found,
    }

    return jsonify({
        "token": token,
        "results": results,
        "summary": summary,
        "recommendations": generate_recommendations(results, summary),
    })


@app.route("/placement/health", methods=["POST"])
def placement_health():
    """Admin-only: check IMAP connectivity of all seed accounts."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.inbox_placement import check_seed_health
    return jsonify({"seeds": check_seed_health()})


@app.route("/placement/cleanup", methods=["POST"])
def placement_cleanup():
    """Admin-only: remove old test emails from seed inboxes."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.inbox_placement import cleanup_seeds
    try:
        result = cleanup_seeds()
    except Exception as e:
        return jsonify({"error": f"Cleanup failed: {e}"}), 500
    return jsonify(result)


# ══════════════════════════════════════════════════════
#  HEADER ANALYZER PAGE + API
# ══════════════════════════════════════════════════════

@app.route("/header-analyzer")
def header_analyzer():
    from modules.page_config import get_page_sections
    sections = get_page_sections("header_analyzer")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("header_analyzer.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="header_analyzer")


@app.route("/analyze-headers", methods=["POST"])
def analyze_headers():
    """Parse raw email headers and return structured analysis."""
    from email.parser import HeaderParser
    from email.utils import parsedate_to_datetime

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    raw_headers = (data.get("headers") or "").strip()
    if not raw_headers:
        return jsonify({"error": "No headers provided."}), 400

    try:
        parser = HeaderParser()
        msg = parser.parsestr(raw_headers)
    except Exception as e:
        return jsonify({"error": f"Failed to parse headers: {str(e)[:200]}"}), 400

    # ── Envelope ──
    envelope = {
        "from": msg.get("From", ""),
        "to": msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "reply_to": msg.get("Reply-To", ""),
    }

    # ── Authentication-Results ──
    auth_results = {"spf": None, "dkim": None, "dmarc": None}
    auth_header = msg.get("Authentication-Results", "")
    if auth_header:
        auth_lower = auth_header.lower()
        for proto in ("spf", "dkim", "dmarc"):
            # Match patterns like "spf=pass", "dkim=fail", "dmarc=none"
            match = re.search(rf'{proto}\s*=\s*(\w+)', auth_lower)
            if match:
                auth_results[proto] = match.group(1)

    # ── Received chain ──
    received_headers = msg.get_all("Received") or []
    received_chain = []
    timestamps = []

    for rh in received_headers:
        hop = {"from_server": "", "by_server": "", "protocol": "", "timestamp": "", "encrypted": False, "delay_seconds": None}

        # Extract "from X"
        from_match = re.search(r'from\s+([\w.\-]+(?:\s*\([^)]*\))?)', rh, re.IGNORECASE)
        if from_match:
            hop["from_server"] = from_match.group(1).strip()

        # Extract "by X"
        by_match = re.search(r'by\s+([\w.\-]+)', rh, re.IGNORECASE)
        if by_match:
            hop["by_server"] = by_match.group(1).strip()

        # Extract protocol
        proto_match = re.search(r'with\s+(E?SMTPS?A?)', rh, re.IGNORECASE)
        if proto_match:
            hop["protocol"] = proto_match.group(1).upper()

        # Check encryption
        if re.search(r'ESMTPS|TLS|tls\s*v?\d|STARTTLS', rh, re.IGNORECASE):
            hop["encrypted"] = True

        # Extract timestamp (after semicolon)
        ts_match = re.search(r';\s*(.+)$', rh.strip())
        if ts_match:
            ts_str = ts_match.group(1).strip()
            hop["timestamp"] = ts_str
            try:
                dt = parsedate_to_datetime(ts_str)
                timestamps.append(dt)
            except Exception:
                timestamps.append(None)
        else:
            timestamps.append(None)

        received_chain.append(hop)

    # Compute delays between hops (Received headers are in reverse order)
    total_delay = 0
    for i in range(len(timestamps) - 1):
        newer = timestamps[i]
        older = timestamps[i + 1]
        if newer and older:
            delay = (newer - older).total_seconds()
            if delay < 0:
                delay = 0
            received_chain[i]["delay_seconds"] = round(delay, 1)
            total_delay += delay

    # ── TLS info ──
    tls_info = {
        "any_encrypted": any(h["encrypted"] for h in received_chain),
        "all_encrypted": all(h["encrypted"] for h in received_chain) if received_chain else False,
    }

    # ── DKIM-Signature ──
    dkim_sig = {"domain": None, "selector": None, "algorithm": None, "header_fields": None, "body_hash": None}
    dkim_header = msg.get("DKIM-Signature", "")
    if dkim_header:
        d_match = re.search(r'd\s*=\s*([^;\s]+)', dkim_header)
        s_match = re.search(r's\s*=\s*([^;\s]+)', dkim_header)
        a_match = re.search(r'a\s*=\s*([^;\s]+)', dkim_header)
        h_match = re.search(r'h\s*=\s*([^;]+)', dkim_header)
        bh_match = re.search(r'bh\s*=\s*([^;\s]+)', dkim_header)
        if d_match: dkim_sig["domain"] = d_match.group(1).strip()
        if s_match: dkim_sig["selector"] = s_match.group(1).strip()
        if a_match: dkim_sig["algorithm"] = a_match.group(1).strip()
        if h_match: dkim_sig["header_fields"] = h_match.group(1).strip()
        if bh_match: dkim_sig["body_hash"] = bh_match.group(1).strip()

    # ── X-Headers ──
    x_headers = {}
    for key in msg.keys():
        if key.lower().startswith("x-"):
            val = msg.get(key, "")
            x_headers[key] = val

    # ── All headers (for raw display) ──
    all_headers = [(k, v) for k, v in msg.items()]

    # ── Summary ──
    auth_pass_count = sum(1 for v in auth_results.values() if v == "pass")
    auth_fail_count = sum(1 for v in auth_results.values() if v and v != "pass" and v != "none")

    summary = {
        "total_hops": len(received_chain),
        "all_encrypted": tls_info["all_encrypted"],
        "auth_pass_count": auth_pass_count,
        "auth_fail_count": auth_fail_count,
        "total_delay_seconds": round(total_delay, 1),
    }

    return jsonify({
        "authentication_results": auth_results,
        "received_chain": received_chain,
        "tls_info": tls_info,
        "dkim_signature": dkim_sig,
        "envelope": envelope,
        "x_headers": x_headers,
        "all_headers": all_headers,
        "summary": summary,
    })


# ══════════════════════════════════════════════════════
#  DOMAIN HEALTH REPORT PAGE + API
# ══════════════════════════════════════════════════════

@app.route("/domain-health")
def domain_health():
    """Domain Health now redirects to Sender Check (consolidated)."""
    qs = request.query_string.decode()
    target = "/sender"
    if qs:
        target += f"?{qs}"
    return redirect(target, code=302)


@app.route("/domain-health-check", methods=["POST"])
def domain_health_check():
    """Comprehensive domain health assessment with letter grade."""
    from modules.rate_limiter import check_rate_limit, log_usage
    allowed, info = check_rate_limit("domain_check")
    if not allowed:
        return _rate_limit_response(info)

    import concurrent.futures
    import ssl
    import socket

    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    domain = (data.get("domain") or "").strip().lower().rstrip(".")
    dkim_selector = (data.get("dkim_selector") or "").strip() or None

    if not domain:
        return jsonify({"error": "Domain is required."}), 400
    if not re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
        return jsonify({"error": "Invalid domain format."}), 400

    results = {}
    errors = []

    def run_reputation():
        from modules.reputation_checker import ReputationChecker
        checker = ReputationChecker(domain=domain, dkim_selector=dkim_selector)
        return checker.analyze()

    def run_bimi():
        from modules.bimi_validator import validate_bimi
        return validate_bimi(domain)

    def run_dns_suggestions():
        from modules.dns_generators import generate_from_auth_results
        # We need auth results first, so this will be run after reputation
        return None

    def run_mx():
        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, 'MX')
            records = []
            for rdata in sorted(answers, key=lambda x: x.preference):
                records.append({"priority": rdata.preference, "host": str(rdata.exchange).rstrip('.')})
            return {"found": True, "records": records}
        except Exception as e:
            return {"found": False, "records": [], "error": str(e)[:100]}

    def run_ssl():
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
                s.settimeout(5)
                s.connect((domain, 443))
                cert = s.getpeercert()
                not_after = cert.get("notAfter", "")
                return {"connected": True, "cert_expiry": not_after, "error": None}
        except Exception as e:
            return {"connected": False, "cert_expiry": None, "error": str(e)[:100]}

    # Run all checks in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_rep = executor.submit(run_reputation)
        future_bimi = executor.submit(run_bimi)
        future_mx = executor.submit(run_mx)
        future_ssl = executor.submit(run_ssl)

        try:
            results["reputation"] = future_rep.result(timeout=30)
        except Exception as e:
            results["reputation"] = None
            errors.append(f"Reputation check failed: {str(e)[:100]}")

        try:
            results["bimi"] = future_bimi.result(timeout=15)
        except Exception as e:
            results["bimi"] = None
            errors.append(f"BIMI check failed: {str(e)[:100]}")

        try:
            results["mx"] = future_mx.result(timeout=10)
        except Exception as e:
            results["mx"] = {"found": False, "records": []}

        try:
            results["ssl"] = future_ssl.result(timeout=10)
        except Exception as e:
            results["ssl"] = {"connected": False, "error": str(e)[:100]}

    # Run DNS suggestions after reputation data is available
    if results["reputation"]:
        try:
            from modules.dns_generators import generate_from_auth_results
            auth_cats = results["reputation"].get("auth", {}).get("categories", [])
            results["dns_suggestions"] = generate_from_auth_results(
                domain=domain, auth_categories=auth_cats
            )
        except Exception:
            results["dns_suggestions"] = None

    # ── Compute scores ──
    rep = results.get("reputation") or {}
    auth_data = rep.get("auth", {})
    rep_data = rep.get("reputation", {})
    bimi_data = results.get("bimi") or {}
    mx_data = results.get("mx") or {}
    ssl_data = results.get("ssl") or {}

    # Auth score (up to 40 points)
    auth_cats = auth_data.get("categories", [])
    auth_score = 0
    auth_details = []
    for cat in auth_cats:
        label = cat.get("label", "")
        status = cat.get("status", "missing")
        if label in ("SPF", "DKIM", "DMARC"):
            if status == "pass":
                auth_score += 13
                auth_details.append(f"{label}: pass")
            elif status == "warning":
                auth_score += 7
                auth_details.append(f"{label}: warning")
            else:
                auth_details.append(f"{label}: {status}")
    auth_score = min(auth_score, 40)
    # Add 1 point if all 3 pass (bonus)
    spf_pass = any(c.get("label") == "SPF" and c.get("status") == "pass" for c in auth_cats)
    dkim_pass = any(c.get("label") == "DKIM" and c.get("status") == "pass" for c in auth_cats)
    dmarc_pass = any(c.get("label") == "DMARC" and c.get("status") == "pass" for c in auth_cats)
    if spf_pass and dkim_pass and dmarc_pass:
        auth_score = 40

    # Blocklist score (up to 25 points)
    listed_count = rep_data.get("listed_count", 0)
    dnsbl_list = rep_data.get("dnsbl", [])
    blocklist_score = 25
    blocklist_details = []
    if listed_count > 0:
        # Deduct based on severity
        for entry in dnsbl_list:
            if entry.get("listed"):
                weight = entry.get("weight", "minor")
                if weight == "critical":
                    blocklist_score -= 10
                elif weight == "major":
                    blocklist_score -= 6
                elif weight == "moderate":
                    blocklist_score -= 3
                else:
                    blocklist_score -= 1
        blocklist_score = max(blocklist_score, 0)
        blocklist_details.append(f"Listed on {listed_count} blocklist(s)")
    else:
        blocklist_details.append("Clean on all checked blocklists")

    # BIMI score (up to 10 points)
    bimi_score = 0
    bimi_details = []
    if bimi_data.get("found"):
        bimi_score += 5
        bimi_details.append("BIMI record found")
        if bimi_data.get("logo_url") or bimi_data.get("logo_valid"):
            bimi_score += 3
            bimi_details.append("Logo configured")
        if bimi_data.get("vmc_url") or bimi_data.get("vmc_valid"):
            bimi_score += 2
            bimi_details.append("VMC certificate present")
    else:
        bimi_details.append("No BIMI record")

    # Transport security score (up to 10 points): MTA-STS, TLS-RPT, SSL
    transport_score = 0
    transport_details = []
    mta_sts_cat = next((c for c in auth_cats if c.get("label") == "MTA-STS"), None)
    tls_rpt_cat = next((c for c in auth_cats if c.get("label") == "TLS-RPT"), None)
    if mta_sts_cat and mta_sts_cat.get("status") == "pass":
        transport_score += 4
        transport_details.append("MTA-STS configured")
    else:
        transport_details.append("MTA-STS not configured")
    if tls_rpt_cat and tls_rpt_cat.get("status") == "pass":
        transport_score += 3
        transport_details.append("TLS-RPT configured")
    else:
        transport_details.append("TLS-RPT not configured")
    if ssl_data.get("connected"):
        transport_score += 3
        transport_details.append("HTTPS/SSL valid")
    else:
        transport_details.append("No HTTPS or SSL issue")

    # DNS health score (up to 15 points): rDNS, FCrDNS, MX, domain setup
    dns_score = 0
    dns_details = []
    if mx_data.get("found") or (rep_data.get("mx", {}).get("found")):
        dns_score += 5
        dns_details.append("MX records found")
    else:
        dns_details.append("No MX records")

    ptr_data = rep_data.get("ptr", {})
    fcrdns_data = rep_data.get("fcrdns", {})
    if ptr_data.get("found"):
        dns_score += 5
        dns_details.append("PTR record found")
    elif ptr_data.get("checked"):
        dns_details.append("No PTR record")
    else:
        dns_score += 3  # Not checked (no IP given), partial credit
        dns_details.append("PTR not checked (no IP)")

    if fcrdns_data.get("valid"):
        dns_score += 5
        dns_details.append("FCrDNS verified")
    elif fcrdns_data.get("checked"):
        dns_details.append("FCrDNS failed")
    else:
        dns_score += 2  # Not checked, partial
        dns_details.append("FCrDNS not checked")

    dns_score = min(dns_score, 15)

    # Overall score
    overall_score = auth_score + blocklist_score + bimi_score + transport_score + dns_score
    overall_score = min(overall_score, 100)

    # Letter grade
    if overall_score >= 90:
        grade = "A"
    elif overall_score >= 80:
        grade = "B"
    elif overall_score >= 65:
        grade = "C"
    elif overall_score >= 50:
        grade = "D"
    else:
        grade = "F"

    # Category scores for display
    category_scores = {
        "auth": {"label": "Authentication", "score": auth_score, "max": 40, "details": auth_details},
        "blocklists": {"label": "Blocklists", "score": blocklist_score, "max": 25, "details": blocklist_details},
        "bimi": {"label": "BIMI", "score": bimi_score, "max": 10, "details": bimi_details},
        "transport": {"label": "Transport Security", "score": transport_score, "max": 10, "details": transport_details},
        "dns": {"label": "DNS Health", "score": dns_score, "max": 15, "details": dns_details},
    }

    # Build recommendations from reputation data
    recommendations = []
    if rep.get("recommendations"):
        recommendations = rep["recommendations"]

    # Add BIMI recommendation if missing
    if not bimi_data.get("found"):
        recommendations.append({
            "category": "BIMI",
            "item": "No BIMI record configured",
            "recommendation": f"Add a BIMI DNS record at default._bimi.{domain} to display your brand logo in supporting email clients like Gmail, Yahoo, and Apple Mail.",
        })

    # Add transport recommendations
    if not (mta_sts_cat and mta_sts_cat.get("status") == "pass"):
        recommendations.append({
            "category": "Transport Security",
            "item": "MTA-STS not configured",
            "recommendation": f"Configure MTA-STS for {domain} to enforce TLS encryption for inbound mail delivery.",
        })
    if not (tls_rpt_cat and tls_rpt_cat.get("status") == "pass"):
        recommendations.append({
            "category": "Transport Security",
            "item": "TLS-RPT not configured",
            "recommendation": f"Add a TLS-RPT DNS record for {domain} to receive reports about TLS delivery failures.",
        })

    log_usage("domain_check")

    domain_result = {
        "domain": domain,
        "grade": grade,
        "score": overall_score,
        "category_scores": category_scores,
        "reputation": rep,
        "bimi": bimi_data,
        "mx": mx_data,
        "ssl": ssl_data,
        "dns_suggestions": results.get("dns_suggestions"),
        "recommendations": recommendations,
        "errors": errors if errors else None,
    }

    if session.get("user_id"):
        from modules.tiers import has_feature
        if has_feature(session.get("user_tier", "free"), "cloud_history"):
            from modules.history import save_result
            save_result(session["user_id"], "domain_check", domain, domain_result,
                        grade=grade, score=overall_score)

    return jsonify(domain_result)


# ══════════════════════════════════════════════════════
#  FULL AUDIT PAGE + API
# ══════════════════════════════════════════════════════

@app.route("/full-audit")
def full_audit():
    """Redirect to consolidated Sender Check page."""
    qs = request.query_string.decode()
    target = "/sender"
    if qs:
        target += f"?{qs}"
    return redirect(target, code=302)


@app.route("/api/full-audit", methods=["POST"])
def full_audit_check():
    """Unified domain audit: runs ALL checks in parallel, returns one comprehensive report."""
    import concurrent.futures
    import ssl
    import socket

    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    domain = (data.get("domain") or "").strip().lower().rstrip(".")
    dkim_selector = (data.get("dkim_selector") or "").strip() or None

    if not domain:
        return jsonify({"error": "Domain is required."}), 400
    if not re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
        return jsonify({"error": "Invalid domain format."}), 400

    results = {}
    errors = []

    def run_reputation():
        from modules.reputation_checker import ReputationChecker
        checker = ReputationChecker(domain=domain, dkim_selector=dkim_selector)
        return checker.analyze()

    def run_bimi():
        from modules.bimi_validator import validate_bimi
        return validate_bimi(domain)

    def run_mx():
        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, 'MX')
            records = []
            for rdata in sorted(answers, key=lambda x: x.preference):
                records.append({"priority": rdata.preference, "host": str(rdata.exchange).rstrip('.')})
            return {"found": True, "records": records}
        except Exception as e:
            return {"found": False, "records": [], "error": str(e)[:100]}

    def run_ssl():
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
                s.settimeout(5)
                s.connect((domain, 443))
                cert = s.getpeercert()
                not_after = cert.get("notAfter", "")
                return {"connected": True, "cert_expiry": not_after, "error": None}
        except Exception as e:
            return {"connected": False, "cert_expiry": None, "error": str(e)[:100]}

    # Run all checks in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_rep = executor.submit(run_reputation)
        future_bimi = executor.submit(run_bimi)
        future_mx = executor.submit(run_mx)
        future_ssl = executor.submit(run_ssl)

        try:
            results["reputation"] = future_rep.result(timeout=30)
        except Exception as e:
            results["reputation"] = None
            errors.append(f"Reputation check failed: {str(e)[:100]}")

        try:
            results["bimi"] = future_bimi.result(timeout=15)
        except Exception as e:
            results["bimi"] = None
            errors.append(f"BIMI check failed: {str(e)[:100]}")

        try:
            results["mx"] = future_mx.result(timeout=10)
        except Exception as e:
            results["mx"] = {"found": False, "records": []}

        try:
            results["ssl"] = future_ssl.result(timeout=10)
        except Exception as e:
            results["ssl"] = {"connected": False, "error": str(e)[:100]}

    # ── ESP Auto-Detection ──
    esp_info = {"detected": False}
    mx_data = results.get("mx") or {}
    if mx_data.get("records"):
        from modules.dns_generators import detect_esp_from_mx
        esp_info = detect_esp_from_mx(mx_data["records"])

    # ── DNS fix suggestions ──
    dns_suggestions = None
    if results["reputation"]:
        try:
            from modules.dns_generators import generate_from_auth_results
            auth_cats = results["reputation"].get("auth", {}).get("categories", [])
            dns_suggestions = generate_from_auth_results(
                domain=domain, auth_categories=auth_cats
            )
        except Exception:
            dns_suggestions = None

    # ── BIMI fix record ──
    bimi_data = results.get("bimi") or {}
    if not bimi_data.get("found") and dns_suggestions:
        dns_suggestions["suggestions"].append({
            "type": "bimi",
            "_action": "create",
            "_title": "Create BIMI Record",
            "_description": (
                "No BIMI record found. Add a BIMI DNS record to display your brand logo "
                "in Gmail, Yahoo, and Apple Mail."
            ),
            "host": f"default._bimi.{domain}",
            "dns_name": f"default._bimi.{domain}",
            "dns_type": "TXT",
            "record": f"v=BIMI1; l=https://yourdomain.com/logo.svg; a=",
            "warnings": [
                "Replace the logo URL with your actual SVG logo hosted over HTTPS.",
                "BIMI requires DMARC with p=quarantine or p=reject to work in Gmail.",
                "For the Gmail blue checkmark, you also need a VMC certificate from DigiCert or Entrust.",
            ],
        })

    # ── Compute scores (same logic as domain-health-check) ──
    rep = results.get("reputation") or {}
    auth_data = rep.get("auth", {})
    rep_data = rep.get("reputation", {})
    ssl_data = results.get("ssl") or {}

    auth_cats = auth_data.get("categories", [])
    auth_score = 0
    auth_details = []
    for cat in auth_cats:
        label = cat.get("label", "")
        status = cat.get("status", "missing")
        if label in ("SPF", "DKIM", "DMARC"):
            if status == "pass":
                auth_score += 13
                auth_details.append(f"{label}: pass")
            elif status == "warning":
                auth_score += 7
                auth_details.append(f"{label}: warning")
            else:
                auth_details.append(f"{label}: {status}")
    auth_score = min(auth_score, 40)
    spf_pass = any(c.get("label") == "SPF" and c.get("status") == "pass" for c in auth_cats)
    dkim_pass = any(c.get("label") == "DKIM" and c.get("status") == "pass" for c in auth_cats)
    dmarc_pass = any(c.get("label") == "DMARC" and c.get("status") == "pass" for c in auth_cats)
    if spf_pass and dkim_pass and dmarc_pass:
        auth_score = 40

    listed_count = rep_data.get("listed_count", 0)
    dnsbl_list = rep_data.get("dnsbl", [])
    blocklist_score = 25
    blocklist_details = []
    if listed_count > 0:
        for entry in dnsbl_list:
            if entry.get("listed"):
                weight = entry.get("weight", "minor")
                if weight == "critical":
                    blocklist_score -= 10
                elif weight == "major":
                    blocklist_score -= 6
                elif weight == "moderate":
                    blocklist_score -= 3
                else:
                    blocklist_score -= 1
        blocklist_score = max(blocklist_score, 0)
        blocklist_details.append(f"Listed on {listed_count} blocklist(s)")
    else:
        blocklist_details.append("Clean on all checked blocklists")

    bimi_score = 0
    bimi_details = []
    if bimi_data.get("found"):
        bimi_score += 5
        bimi_details.append("BIMI record found")
        if bimi_data.get("logo_url") or bimi_data.get("logo_valid"):
            bimi_score += 3
            bimi_details.append("Logo configured")
        if bimi_data.get("vmc_url") or bimi_data.get("vmc_valid"):
            bimi_score += 2
            bimi_details.append("VMC certificate present")
    else:
        bimi_details.append("No BIMI record")

    transport_score = 0
    transport_details = []
    mta_sts_cat = next((c for c in auth_cats if c.get("label") == "MTA-STS"), None)
    tls_rpt_cat = next((c for c in auth_cats if c.get("label") == "TLS-RPT"), None)
    if mta_sts_cat and mta_sts_cat.get("status") == "pass":
        transport_score += 4
        transport_details.append("MTA-STS configured")
    else:
        transport_details.append("MTA-STS not configured")
    if tls_rpt_cat and tls_rpt_cat.get("status") == "pass":
        transport_score += 3
        transport_details.append("TLS-RPT configured")
    else:
        transport_details.append("TLS-RPT not configured")
    if ssl_data.get("connected"):
        transport_score += 3
        transport_details.append("HTTPS/SSL valid")
    else:
        transport_details.append("No HTTPS or SSL issue")

    dns_score = 0
    dns_details = []
    if mx_data.get("found") or (rep_data.get("mx", {}).get("found")):
        dns_score += 5
        dns_details.append("MX records found")
    else:
        dns_details.append("No MX records")
    ptr_data = rep_data.get("ptr", {})
    fcrdns_data = rep_data.get("fcrdns", {})
    if ptr_data.get("found"):
        dns_score += 5
        dns_details.append("PTR record found")
    elif ptr_data.get("checked"):
        dns_details.append("No PTR record")
    else:
        dns_score += 3
        dns_details.append("PTR not checked (no IP)")
    if fcrdns_data.get("valid"):
        dns_score += 5
        dns_details.append("FCrDNS verified")
    elif fcrdns_data.get("checked"):
        dns_details.append("FCrDNS failed")
    else:
        dns_score += 2
        dns_details.append("FCrDNS not checked")
    dns_score = min(dns_score, 15)

    overall_score = auth_score + blocklist_score + bimi_score + transport_score + dns_score
    overall_score = min(overall_score, 100)

    if overall_score >= 90:
        grade = "A"
    elif overall_score >= 80:
        grade = "B"
    elif overall_score >= 65:
        grade = "C"
    elif overall_score >= 50:
        grade = "D"
    else:
        grade = "F"

    category_scores = {
        "auth": {"label": "Authentication", "score": auth_score, "max": 40, "details": auth_details},
        "blocklists": {"label": "Blocklists", "score": blocklist_score, "max": 25, "details": blocklist_details},
        "bimi": {"label": "BIMI", "score": bimi_score, "max": 10, "details": bimi_details},
        "transport": {"label": "Transport Security", "score": transport_score, "max": 10, "details": transport_details},
        "dns": {"label": "DNS Health", "score": dns_score, "max": 15, "details": dns_details},
    }

    # ── Recommendations ──
    recommendations = []
    if rep.get("recommendations"):
        recommendations = rep["recommendations"]
    if not bimi_data.get("found"):
        recommendations.append({
            "category": "BIMI",
            "item": "No BIMI record configured",
            "recommendation": f"Add a BIMI DNS record at default._bimi.{domain} to display your brand logo in supporting email clients.",
        })
    if not (mta_sts_cat and mta_sts_cat.get("status") == "pass"):
        recommendations.append({
            "category": "Transport Security",
            "item": "MTA-STS not configured",
            "recommendation": f"Configure MTA-STS for {domain} to enforce TLS encryption for inbound mail delivery.",
        })
    if not (tls_rpt_cat and tls_rpt_cat.get("status") == "pass"):
        recommendations.append({
            "category": "Transport Security",
            "item": "TLS-RPT not configured",
            "recommendation": f"Add a TLS-RPT DNS record for {domain} to receive reports about TLS delivery failures.",
        })

    # ── Build fix records with ESP-specific instructions ──
    fix_records = []
    if dns_suggestions and dns_suggestions.get("suggestions"):
        for sug in dns_suggestions["suggestions"]:
            fix = {
                "type": sug.get("type", ""),
                "action": sug.get("_action", "create"),
                "title": sug.get("_title", ""),
                "description": sug.get("_description", ""),
            }
            # Standard DNS record fixes
            if sug.get("record"):
                fix["host"] = sug.get("host") or sug.get("dns_name", "")
                fix["dns_type"] = sug.get("dns_type", "TXT")
                fix["record"] = sug.get("record", "")
            elif sug.get("dns_record"):
                fix["host"] = sug.get("dns_host", "")
                fix["dns_type"] = sug.get("dns_type", "TXT")
                fix["record"] = sug.get("dns_record", "")
            # DKIM instructions
            if sug.get("instructions"):
                fix["instructions"] = sug["instructions"]
                fix["host"] = sug.get("host_example", "")
                fix["record"] = sug.get("record_example", "")
                fix["dns_type"] = sug.get("dns_type", "TXT")
            # MTA-STS policy file
            if sug.get("policy_text"):
                fix["policy_text"] = sug["policy_text"]
                fix["policy_url"] = sug.get("policy_url", "")
                fix["setup_steps"] = sug.get("setup_steps", [])
            fix["warnings"] = sug.get("warnings", [])

            # Add ESP-specific context
            if esp_info.get("detected") and sug.get("type") in ("spf", "dkim"):
                fix["esp_detected"] = esp_info["esp_name"]
                if sug.get("type") == "dkim" and esp_info.get("esp_key"):
                    from modules.dns_generators import generate_dkim_instructions
                    esp_dkim = generate_dkim_instructions(domain, esp=esp_info["esp_key"])
                    fix["instructions"] = esp_dkim.get("instructions", [])
                    fix["host"] = esp_dkim.get("host_example", fix.get("host", ""))
                    fix["record"] = esp_dkim.get("record_example", fix.get("record", ""))

            fix_records.append(fix)

    # ── Severity summary counts ──
    severity_summary = {"critical": 0, "warning": 0, "pass": 0, "info": 0}
    for cat in auth_cats:
        st = cat.get("status", "missing")
        if st == "pass":
            severity_summary["pass"] += 1
        elif st in ("fail", "missing"):
            severity_summary["critical"] += 1
        elif st == "warning":
            severity_summary["warning"] += 1

    if listed_count > 0:
        severity_summary["critical"] += 1
    else:
        severity_summary["pass"] += 1

    if bimi_data.get("found"):
        severity_summary["pass"] += 1
    else:
        severity_summary["info"] += 1

    if ssl_data.get("connected"):
        severity_summary["pass"] += 1
    else:
        severity_summary["warning"] += 1

    return jsonify({
        "domain": domain,
        "grade": grade,
        "score": overall_score,
        "category_scores": category_scores,
        "severity_summary": severity_summary,
        "esp": esp_info,
        "reputation": rep,
        "bimi": bimi_data,
        "mx": mx_data,
        "ssl": ssl_data,
        "fix_records": fix_records,
        "recommendations": recommendations,
        "errors": errors if errors else None,
    })


# ══════════════════════════════════════════════════════
#  BLACKLIST MONITOR PAGE + API
# ══════════════════════════════════════════════════════

@app.route("/blacklist-monitor")
def blacklist_monitor():
    from modules.page_config import get_page_sections
    sections = get_page_sections("blacklist_monitor")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("blacklist_monitor.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="blacklist_monitor")


@app.route("/blacklist-monitor/add", methods=["POST"])
def blm_add():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    domain = (data.get("domain") or "").strip().lower().rstrip(".")
    ip = (data.get("ip") or "").strip() or None

    if not domain:
        return jsonify({"ok": False, "error": "Domain is required."}), 400
    if not re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
        return jsonify({"ok": False, "error": "Invalid domain format."}), 400
    if ip:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return jsonify({"ok": False, "error": f"Invalid IP address: {ip}"}), 400

    from modules.blacklist_monitor import add_domain
    return jsonify(add_domain(domain, ip=ip))


@app.route("/blacklist-monitor/remove", methods=["POST"])
def blm_remove():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    domain = (data.get("domain") or "").strip().lower()
    if not domain:
        return jsonify({"ok": False, "error": "Domain is required."}), 400

    from modules.blacklist_monitor import remove_domain
    return jsonify(remove_domain(domain))


@app.route("/blacklist-monitor/scan", methods=["POST"])
def blm_scan():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    domain = (data.get("domain") or "").strip().lower()
    if not domain:
        return jsonify({"ok": False, "error": "Domain is required."}), 400

    from modules.blacklist_monitor import scan_domain
    result = scan_domain(domain)
    return jsonify(result)


@app.route("/blacklist-monitor/domains", methods=["GET"])
def blm_domains():
    from modules.blacklist_monitor import get_monitored_domains
    return jsonify(get_monitored_domains())


@app.route("/blacklist-monitor/history/<domain>", methods=["GET"])
def blm_history(domain):
    from modules.blacklist_monitor import get_domain_history
    return jsonify(get_domain_history(domain))


# ══════════════════════════════════════════════════════
#  WARM-UP TRACKER PAGE + API
# ══════════════════════════════════════════════════════

@app.route("/warmup")
def warmup():
    from modules.page_config import get_page_sections
    sections = get_page_sections("warmup")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("warmup.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="warmup")


@app.route("/warmup/create", methods=["POST"])
def warmup_create():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    domain = (data.get("domain") or "").strip().lower().rstrip(".")
    esp = (data.get("esp") or "other").strip()
    daily_target = data.get("daily_target", 500)

    if not domain:
        return jsonify({"ok": False, "error": "Domain is required."}), 400
    if not re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
        return jsonify({"ok": False, "error": "Invalid domain format."}), 400

    from modules.warmup_tracker import create_campaign
    return jsonify(create_campaign(domain, esp, daily_target))


@app.route("/warmup/campaigns", methods=["GET"])
def warmup_campaigns():
    from modules.warmup_tracker import get_campaigns
    return jsonify(get_campaigns())


@app.route("/warmup/campaign/<int:campaign_id>", methods=["GET"])
def warmup_campaign(campaign_id):
    from modules.warmup_tracker import get_campaign
    result = get_campaign(campaign_id)
    if not result:
        return jsonify({"error": "Campaign not found."}), 404
    return jsonify(result)


@app.route("/warmup/log", methods=["POST"])
def warmup_log():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    campaign_id = data.get("campaign_id")
    sent_count = data.get("sent_count", 0)
    placement_result = data.get("placement_result")
    notes = data.get("notes")

    if not campaign_id:
        return jsonify({"ok": False, "error": "campaign_id is required."}), 400

    from modules.warmup_tracker import log_day
    return jsonify(log_day(campaign_id, sent_count, placement_result, notes))


@app.route("/warmup/status", methods=["POST"])
def warmup_status():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    campaign_id = data.get("campaign_id")
    status = data.get("status")

    if not campaign_id or not status:
        return jsonify({"ok": False, "error": "campaign_id and status are required."}), 400

    from modules.warmup_tracker import update_campaign_status
    return jsonify(update_campaign_status(campaign_id, status))


@app.route("/warmup/campaign/<int:campaign_id>", methods=["DELETE"])
def warmup_delete(campaign_id):
    from modules.warmup_tracker import delete_campaign
    return jsonify(delete_campaign(campaign_id))


# ══════════════════════════════════════════════════════
#  EMAIL VERIFIER PAGE + API
# ══════════════════════════════════════════════════════

@app.route("/email-verifier")
def email_verifier():
    from modules.page_config import get_page_sections
    sections = get_page_sections("email_verifier")
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("email_verifier.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="email_verifier")


@app.route("/api/verify-email", methods=["POST"])
def api_verify_email():
    from modules.rate_limiter import check_rate_limit, log_usage
    allowed, info = check_rate_limit("email_verify", limit_key="email_verifications_per_day")
    if not allowed:
        return _rate_limit_response(info)

    from modules.email_verifier import verify_email
    data = request.get_json(force=True, silent=True)
    if not data or not data.get("email"):
        return jsonify({"error": "Email address is required"}), 400
    email_addr = data["email"].strip()
    if len(email_addr) > 320:
        return jsonify({"error": "Email address too long"}), 400
    result = verify_email(email_addr)
    log_usage("email_verify")

    if session.get("user_id"):
        from modules.tiers import has_feature
        if has_feature(session.get("user_tier", "free"), "cloud_history"):
            from modules.history import save_result
            save_result(session["user_id"], "email_verify", email_addr, result,
                        grade=result.get("grade"), score=result.get("score"))

    return jsonify(result)


@app.route("/check-reputation", methods=["POST"])
def check_reputation():
    from modules.rate_limiter import check_rate_limit, log_usage
    allowed, info = check_rate_limit("domain_check")
    if not allowed:
        return _rate_limit_response(info)

    import concurrent.futures
    import ssl
    import socket

    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    domain      = (data.get("domain")        or "").strip().lower().rstrip(".")
    sender_ip   = (data.get("sender_ip")     or "").strip() or None
    dkim_selector = (data.get("dkim_selector") or "").strip() or None

    if not domain:
        return jsonify({"error": "Domain is required."}), 400

    if not re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
        return jsonify({"error": "Invalid domain format."}), 400

    if sender_ip:
        try:
            ipaddress.ip_address(sender_ip)
        except ValueError:
            return jsonify({"error": f"Invalid IP address: {sender_ip}"}), 400

    # Run reputation + BIMI + MX + SSL in parallel
    rep_result = None
    bimi_data = {}
    mx_data = {}
    ssl_data = {}

    def run_reputation():
        from modules.reputation_checker import ReputationChecker
        checker = ReputationChecker(domain=domain, sender_ip=sender_ip, dkim_selector=dkim_selector)
        return checker.analyze()

    def run_bimi():
        from modules.bimi_validator import validate_bimi
        return validate_bimi(domain)

    def run_mx():
        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, 'MX')
            records = []
            for rdata in sorted(answers, key=lambda x: x.preference):
                records.append({"priority": rdata.preference, "host": str(rdata.exchange).rstrip('.')})
            return {"found": True, "records": records}
        except Exception as e:
            return {"found": False, "records": [], "error": str(e)[:100]}

    def run_ssl():
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
                s.settimeout(5)
                s.connect((domain, 443))
                cert = s.getpeercert()
                not_after = cert.get("notAfter", "")
                return {"connected": True, "cert_expiry": not_after, "error": None}
        except Exception as e:
            return {"connected": False, "cert_expiry": None, "error": str(e)[:100]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_rep = executor.submit(run_reputation)
        future_bimi = executor.submit(run_bimi)
        future_mx = executor.submit(run_mx)
        future_ssl = executor.submit(run_ssl)

        try:
            rep_result = future_rep.result(timeout=30)
        except Exception as e:
            return jsonify({"error": f"Check failed: {e}"}), 500

        try:
            bimi_data = future_bimi.result(timeout=15) or {}
        except Exception:
            bimi_data = {}

        try:
            mx_data = future_mx.result(timeout=10)
        except Exception:
            mx_data = {"found": False, "records": []}

        try:
            ssl_data = future_ssl.result(timeout=10)
        except Exception:
            ssl_data = {"connected": False}

    # ── ESP Auto-Detection ──
    esp_info = {"detected": False}
    if mx_data.get("records"):
        from modules.dns_generators import detect_esp_from_mx
        esp_info = detect_esp_from_mx(mx_data["records"])

    # ── DNS fix suggestions ──
    dns_suggestions = None
    auth_cats = rep_result.get("auth", {}).get("categories", [])
    try:
        from modules.dns_generators import generate_from_auth_results
        dns_suggestions = generate_from_auth_results(
            domain=domain, auth_categories=auth_cats
        )
    except Exception:
        dns_suggestions = None

    # ── BIMI fix ──
    if not bimi_data.get("found") and dns_suggestions:
        dns_suggestions["suggestions"].append({
            "type": "bimi",
            "_action": "create",
            "_title": "Create BIMI Record",
            "_description": "No BIMI record found. Add a BIMI DNS record to display your brand logo in Gmail, Yahoo, and Apple Mail.",
            "host": f"default._bimi.{domain}",
            "dns_type": "TXT",
            "record": "v=BIMI1; l=https://yourdomain.com/logo.svg; a=",
            "warnings": [
                "Replace the logo URL with your actual SVG logo hosted over HTTPS.",
                "BIMI requires DMARC with p=quarantine or p=reject to work in Gmail.",
            ],
        })

    # ── Compute A-F grade ──
    rep_data = rep_result.get("reputation", {})
    auth_score = 0
    for cat in auth_cats:
        label = cat.get("label", "")
        status = cat.get("status", "missing")
        if label in ("SPF", "DKIM", "DMARC"):
            if status == "pass":
                auth_score += 13
            elif status == "warning":
                auth_score += 7
    auth_score = min(auth_score, 40)
    if all(any(c.get("label") == l and c.get("status") == "pass" for c in auth_cats) for l in ("SPF", "DKIM", "DMARC")):
        auth_score = 40

    listed_count = rep_data.get("listed_count", 0)
    dnsbl_list = rep_data.get("dnsbl", [])
    blocklist_score = 25
    if listed_count > 0:
        for entry in dnsbl_list:
            if entry.get("listed"):
                w = entry.get("weight", "minor")
                blocklist_score -= {"critical": 10, "major": 6, "moderate": 3}.get(w, 1)
        blocklist_score = max(blocklist_score, 0)

    bimi_score = 0
    if bimi_data.get("found"):
        bimi_score += 5
        if bimi_data.get("logo_url") or bimi_data.get("logo_valid"):
            bimi_score += 3
        if bimi_data.get("vmc_url") or bimi_data.get("vmc_valid"):
            bimi_score += 2

    transport_score = 0
    mta_sts_cat = next((c for c in auth_cats if c.get("label") == "MTA-STS"), None)
    tls_rpt_cat = next((c for c in auth_cats if c.get("label") == "TLS-RPT"), None)
    if mta_sts_cat and mta_sts_cat.get("status") == "pass":
        transport_score += 4
    if tls_rpt_cat and tls_rpt_cat.get("status") == "pass":
        transport_score += 3
    if ssl_data.get("connected"):
        transport_score += 3

    dns_score = 0
    if mx_data.get("found") or rep_data.get("mx", {}).get("found"):
        dns_score += 5
    ptr_data = rep_data.get("ptr", {})
    fcrdns_data = rep_data.get("fcrdns", {})
    if ptr_data.get("found"):
        dns_score += 5
    elif not ptr_data.get("checked"):
        dns_score += 3
    if fcrdns_data.get("valid"):
        dns_score += 5
    elif not fcrdns_data.get("checked"):
        dns_score += 2
    dns_score = min(dns_score, 15)

    overall_score = min(auth_score + blocklist_score + bimi_score + transport_score + dns_score, 100)

    if overall_score >= 90:
        grade = "A"
    elif overall_score >= 80:
        grade = "B"
    elif overall_score >= 65:
        grade = "C"
    elif overall_score >= 50:
        grade = "D"
    else:
        grade = "F"

    category_scores = {
        "auth": {"label": "Authentication", "score": auth_score, "max": 40},
        "blocklists": {"label": "Blocklists", "score": blocklist_score, "max": 25},
        "bimi": {"label": "BIMI", "score": bimi_score, "max": 10},
        "transport": {"label": "Transport Security", "score": transport_score, "max": 10},
        "dns": {"label": "DNS Health", "score": dns_score, "max": 15},
    }

    # ── Build fix records ──
    fix_records = []
    if dns_suggestions and dns_suggestions.get("suggestions"):
        for sug in dns_suggestions["suggestions"]:
            fix = {
                "type": sug.get("type", ""),
                "action": sug.get("_action", "create"),
                "title": sug.get("_title", ""),
                "description": sug.get("_description", ""),
                "warnings": sug.get("warnings", []),
            }
            if sug.get("record"):
                fix["host"] = sug.get("host") or sug.get("dns_name", "")
                fix["dns_type"] = sug.get("dns_type", "TXT")
                fix["record"] = sug.get("record", "")
            elif sug.get("dns_record"):
                fix["host"] = sug.get("dns_host", "")
                fix["dns_type"] = sug.get("dns_type", "TXT")
                fix["record"] = sug.get("dns_record", "")
            if sug.get("instructions"):
                fix["instructions"] = sug["instructions"]
                fix["host"] = sug.get("host_example", fix.get("host", ""))
                fix["record"] = sug.get("record_example", fix.get("record", ""))
                fix["dns_type"] = sug.get("dns_type", "TXT")
            if sug.get("policy_text"):
                fix["policy_text"] = sug["policy_text"]
                fix["policy_url"] = sug.get("policy_url", "")
                fix["setup_steps"] = sug.get("setup_steps", [])
            if esp_info.get("detected") and sug.get("type") in ("spf", "dkim"):
                fix["esp_detected"] = esp_info["esp_name"]
                if sug.get("type") == "dkim" and esp_info.get("esp_key"):
                    from modules.dns_generators import generate_dkim_instructions
                    esp_dkim = generate_dkim_instructions(domain, esp=esp_info["esp_key"])
                    fix["instructions"] = esp_dkim.get("instructions", [])
                    fix["host"] = esp_dkim.get("host_example", fix.get("host", ""))
                    fix["record"] = esp_dkim.get("record_example", fix.get("record", ""))
            fix_records.append(fix)

    # Merge extra data into the existing result format
    rep_result["grade"] = grade
    rep_result["score"] = overall_score
    rep_result["category_scores"] = category_scores
    rep_result["esp"] = esp_info
    rep_result["bimi"] = bimi_data
    rep_result["ssl"] = ssl_data
    rep_result["fix_records"] = fix_records

    log_usage("domain_check")

    if session.get("user_id"):
        from modules.tiers import has_feature
        if has_feature(session.get("user_tier", "free"), "cloud_history"):
            from modules.history import save_result
            save_result(session["user_id"], "domain_check", domain, rep_result,
                        grade=grade, score=overall_score)

    return jsonify(rep_result)


@app.route("/ai-rewrite", methods=["POST"])
def ai_rewrite():
    """AI-powered email rewrite using Groq API."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    industry = (data.get("industry") or "General").strip()
    tone = (data.get("tone") or "professional").strip()
    cta_texts = data.get("cta_texts") or []
    issues = data.get("issues") or []

    if not subject and not body:
        return jsonify({"error": "Subject or body is required."}), 400

    from modules.ai_rewriter import rewrite_email, is_available, AIRewriteError

    if not is_available():
        return jsonify({"error": "AI rewrite not available — set GROQ_API_KEY environment variable."}), 503

    try:
        result = rewrite_email(
            subject=subject, body=body, industry=industry,
            tone=tone, cta_texts=cta_texts, issues=issues,
        )
    except AIRewriteError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Rewrite failed: {str(e)[:100]}"}), 500

    return jsonify(result)


@app.route("/ai-rewrite/status", methods=["GET"])
def ai_rewrite_status():
    """Check if AI rewrite is available."""
    from modules.ai_rewriter import is_available
    return jsonify({"available": is_available()})


@app.route("/validate-bimi", methods=["POST"])
def validate_bimi_route():
    """Deep BIMI validation for a domain."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    domain = (data.get("domain") or "").strip().lower().rstrip(".")
    if not domain:
        return jsonify({"error": "Domain is required."}), 400
    if not re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
        return jsonify({"error": "Invalid domain format."}), 400

    selector = (data.get("selector") or "default").strip()

    from modules.bimi_validator import validate_bimi
    try:
        result = validate_bimi(domain, selector=selector)
    except Exception as e:
        return jsonify({"error": f"BIMI validation failed: {e}"}), 500

    return jsonify(result)


@app.route("/generate-bimi", methods=["POST"])
def generate_bimi_route():
    """Generate a BIMI DNS record."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    domain = (data.get("domain") or "").strip().lower().rstrip(".")
    if not domain:
        return jsonify({"error": "Domain is required."}), 400

    logo_url = (data.get("logo_url") or "").strip()
    vmc_url = (data.get("vmc_url") or "").strip()
    selector = (data.get("selector") or "default").strip()

    from modules.bimi_validator import generate_bimi_record
    result = generate_bimi_record(domain, logo_url, vmc_url, selector)
    if result.get("error"):
        return jsonify(result), 400

    return jsonify(result)


@app.route("/generate-dns", methods=["POST"])
def generate_dns():
    """Generate SPF, DKIM, and/or DMARC DNS records."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    domain = (data.get("domain") or "").strip().lower().rstrip(".")
    if not domain:
        return jsonify({"error": "Domain is required."}), 400
    if not re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
        return jsonify({"error": "Invalid domain format."}), 400

    from modules.dns_generators import generate_spf, generate_dmarc, generate_dkim_instructions

    results = {}
    record_type = (data.get("type") or "all").lower()

    if record_type in ("spf", "all"):
        results["spf"] = generate_spf(
            domain,
            esps=data.get("esps", []),
            extra_ips=data.get("ips", []),
            extra_includes=data.get("includes", []),
            mechanism=data.get("spf_mechanism", "-all"),
        )

    if record_type in ("dkim", "all"):
        results["dkim"] = generate_dkim_instructions(
            domain,
            esp=data.get("esp"),
            selector=data.get("dkim_selector"),
        )

    if record_type in ("dmarc", "all"):
        results["dmarc"] = generate_dmarc(
            domain,
            policy=data.get("dmarc_policy", "none"),
            rua_email=data.get("rua_email"),
            ruf_email=data.get("ruf_email"),
            pct=data.get("dmarc_pct", 100),
        )

    if record_type in ("mta_sts", "all"):
        from modules.dns_generators import generate_mta_sts
        results["mta_sts"] = generate_mta_sts(
            domain,
            mode=data.get("mta_sts_mode", "testing"),
            mx_patterns=data.get("mx_patterns"),
            max_age=data.get("mta_sts_max_age", 604800),
        )

    if record_type in ("tls_rpt", "all"):
        from modules.dns_generators import generate_tls_rpt
        results["tls_rpt"] = generate_tls_rpt(
            domain,
            rua_email=data.get("tls_rpt_email"),
            rua_https=data.get("tls_rpt_https"),
        )

    return jsonify({"domain": domain, "records": results})


@app.route("/lookup-mta-sts", methods=["POST"])
def lookup_mta_sts():
    """Standalone MTA-STS lookup for a domain."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    domain = (data.get("domain") or "").strip().lower().rstrip(".")
    if not domain:
        return jsonify({"error": "Domain is required."}), 400
    if not re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
        return jsonify({"error": "Invalid domain format."}), 400

    from modules.reputation_checker import ReputationChecker
    checker = ReputationChecker(domain=domain)
    try:
        result = checker._check_mta_sts()
    except Exception as e:
        return jsonify({"error": f"MTA-STS lookup failed: {e}"}), 500

    return jsonify({"domain": domain, **result})


@app.route("/lookup-tls-rpt", methods=["POST"])
def lookup_tls_rpt():
    """Standalone TLS-RPT lookup for a domain."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    domain = (data.get("domain") or "").strip().lower().rstrip(".")
    if not domain:
        return jsonify({"error": "Domain is required."}), 400
    if not re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
        return jsonify({"error": "Invalid domain format."}), 400

    from modules.reputation_checker import ReputationChecker
    checker = ReputationChecker(domain=domain)
    try:
        result = checker._check_tls_rpt()
    except Exception as e:
        return jsonify({"error": f"TLS-RPT lookup failed: {e}"}), 500

    return jsonify({"domain": domain, **result})


@app.route("/analyze", methods=["POST"])
def analyze():
    from modules.rate_limiter import check_rate_limit, log_usage
    allowed, info = check_rate_limit("copy_analysis")
    if not allowed:
        return _rate_limit_response(info)

    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    sender_email  = (data.get("sender_email")  or "").strip()
    industry      = (data.get("industry")       or "Other").strip()
    subject       = (data.get("subject")        or "").strip()
    preheader     = (data.get("preheader")      or "").strip()
    body          = (data.get("body")           or "").strip()
    cta_urls      = data.get("cta_urls")  or []
    cta_texts     = data.get("cta_texts") or []
    is_transactional = bool(data.get("is_transactional", False))
    is_cold_email    = bool(data.get("is_cold_email",    False))
    is_plain_text    = bool(data.get("is_plain_text",    False))

    if not sender_email:
        return jsonify({"error": "Sender email address is required."}), 400

    if not subject and not body:
        return jsonify({"error": "Please provide at least a subject line and email body."}), 400

    if body and (not cta_urls or not cta_texts):
        auto_urls, auto_texts = _extract_ctas_from_body(body)
        if not cta_urls:
            cta_urls = auto_urls
        if not cta_texts:
            cta_texts = auto_texts

    from modules.spam_analyzer import SpamAnalyzer
    from modules.copy_analyzer import CopyAnalyzer
    from modules.readability import analyze_readability
    from modules.link_image_validator import validate_links_and_images
    from modules.benchmarks import get_benchmarks

    spam = SpamAnalyzer(
        subject=subject, preheader=preheader, body=body,
        sender_email=sender_email, cta_urls=cta_urls, cta_texts=cta_texts,
        is_transactional=is_transactional, is_cold_email=is_cold_email,
        is_plain_text=is_plain_text, industry=industry,
    )
    copy = CopyAnalyzer(
        subject=subject, preheader=preheader, body=body,
        sender_email=sender_email, cta_urls=cta_urls, cta_texts=cta_texts,
        is_transactional=is_transactional, is_cold_email=is_cold_email,
        is_plain_text=is_plain_text, industry=industry,
    )

    # ── Sender reputation check (extract domain from email) ──
    reputation_result = None
    if sender_email and "@" in sender_email:
        domain = sender_email.split("@", 1)[1].strip().lower().rstrip(".")
        if domain and re.match(r'^[a-z0-9][a-z0-9.\-]{0,251}[a-z0-9]$', domain):
            from modules.reputation_checker import ReputationChecker
            try:
                checker = ReputationChecker(domain=domain)
                reputation_result = checker.analyze()
            except Exception:
                pass  # non-fatal — still return spam + copy results

    readability_result = analyze_readability(body=body, subject=subject)

    # Link & image validation (non-fatal)
    link_image_result = None
    if body:
        try:
            link_image_result = validate_links_and_images(body)
        except Exception:
            pass

    result = {
        "spam": spam.analyze(),
        "copy": copy.analyze(),
        "readability": readability_result,
        "meta": {
            "subject_length": len(subject),
            "body_word_count": len(re.findall(r"\b\w+\b", body)),
            "industry": industry,
            "email_type": (
                "Transactional" if is_transactional else
                "Cold Outreach"  if is_cold_email    else
                "Promotional"
            ),
        },
    }

    # Industry benchmarks
    try:
        result["benchmarks"] = get_benchmarks(
            industry=industry,
            spam_score=result["spam"]["score"],
            copy_score=result["copy"]["score"],
            readability_score=readability_result.get("score") if readability_result else None,
            subject_length=len(subject),
            body_word_count=len(re.findall(r"\b\w+\b", body)),
        )
    except Exception:
        pass

    if link_image_result:
        result["link_image"] = link_image_result

    if reputation_result:
        result["reputation"] = reputation_result
        # Generate DNS fix suggestions for missing/broken auth
        try:
            from modules.dns_generators import generate_from_auth_results
            auth_cats = reputation_result.get("auth", {}).get("categories", [])
            dns_suggestions = generate_from_auth_results(
                domain=domain, auth_categories=auth_cats, sender_email=sender_email,
            )
            if dns_suggestions.get("has_suggestions"):
                result["dns_suggestions"] = dns_suggestions
        except Exception:
            pass

        # BIMI validation (non-fatal)
        try:
            from modules.bimi_validator import validate_bimi
            bimi_result = validate_bimi(domain)
            result["bimi"] = bimi_result
        except Exception:
            pass

    # Pre-send audit checklist (aggregates all results)
    try:
        from modules.presend_audit import generate_audit
        result["audit"] = generate_audit(result)
    except Exception:
        pass

    log_usage("copy_analysis")

    if session.get("user_id"):
        from modules.tiers import has_feature
        if has_feature(session.get("user_tier", "free"), "cloud_history"):
            from modules.history import save_result
            summary = sender_email or subject[:60] or "Analysis"
            spam_score = result.get("spam", {}).get("score")
            spam_grade = result.get("spam", {}).get("grade")
            save_result(session["user_id"], "copy_analysis", summary, result,
                        grade=spam_grade, score=spam_score)

    return jsonify(result)


@app.route("/parse-file", methods=["POST"])
def parse_file():
    """Accept .eml / .msg / .mbox / .html uploads and return parsed fields."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = file.filename.lower()
    ext = os.path.splitext(filename)[1]

    allowed = {".html", ".htm", ".eml", ".msg", ".mbox"}
    if ext not in allowed:
        return jsonify({"error": f"Unsupported file type '{ext}'. Allowed: .html, .eml, .msg, .mbox"}), 400

    try:
        content = file.read()
    except Exception as e:
        return jsonify({"error": f"Could not read file: {e}"}), 400

    result = {"subject": "", "from_addr": "", "body": "", "filename": file.filename,
              "message_count": 1}

    try:
        if ext in (".html", ".htm"):
            result["body"] = content.decode("utf-8", errors="replace")

        elif ext == ".eml":
            msg = email_lib.message_from_bytes(content, policy=email_policy.compat32)
            result["subject"]   = str(msg.get("Subject", "") or "")
            result["from_addr"] = str(msg.get("From",    "") or "")
            result["body"]      = _extract_body(msg)

        elif ext == ".msg":
            try:
                import extract_msg
                import io
                msg_obj = extract_msg.Message(io.BytesIO(content))
                result["subject"]   = msg_obj.subject or ""
                result["from_addr"] = msg_obj.sender  or ""
                if msg_obj.htmlBody:
                    body_bytes = msg_obj.htmlBody
                    result["body"] = (
                        body_bytes.decode("utf-8", errors="replace")
                        if isinstance(body_bytes, bytes) else body_bytes
                    )
                elif msg_obj.body:
                    escaped = (msg_obj.body
                               .replace("&", "&amp;")
                               .replace("<", "&lt;")
                               .replace(">", "&gt;"))
                    result["body"] = f"<pre style='white-space:pre-wrap;font-family:inherit'>{escaped}</pre>"
                msg_obj.close()
            except ImportError:
                return jsonify({
                    "error": "The extract-msg library is not installed. Run: pip install extract-msg"
                }), 500

        elif ext == ".mbox":
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mbox", mode="wb") as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name

                mbox = mailbox.mbox(tmp_path)
                try:
                    messages = list(mbox)
                finally:
                    mbox.close()

                if not messages:
                    return jsonify({"error": "No messages found in this mbox file"}), 400

                msg = messages[0]
                result["subject"]       = str(msg.get("Subject", "") or "")
                result["from_addr"]     = str(msg.get("From",    "") or "")
                result["body"]          = _extract_body(msg)
                result["message_count"] = len(messages)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": f"Failed to parse file: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
