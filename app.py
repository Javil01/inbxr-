"""
INBXR — Email Copy Assessment Tool
Flask backend: analysis API + file parsing + admin editor.
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
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)

# ── Secret key for sessions ──────────────────────────────
app.secret_key = os.environ.get("SECRET_KEY", "inbxr-dev-secret-change-in-production")

# ── Max upload size: 10 MB ──────────────────────────────
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# ── Admin credentials (set via env vars in production) ──
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "inbxr2026")


# ══════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════════════════

@app.route("/")
def index():
    from modules.page_config import get_page_sections
    sections = get_page_sections("index")
    # For non-admin visitors, filter out hidden sections
    if not _is_admin():
        sections = [s for s in sections if s.get("visible", True)]
    return render_template("index.html",
                           sections=sections,
                           is_admin=_is_admin(),
                           active_page="index")


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
    return jsonify(result)


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


@app.route("/check-reputation", methods=["POST"])
def check_reputation():
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

    from modules.reputation_checker import ReputationChecker

    checker = ReputationChecker(domain=domain, sender_ip=sender_ip, dkim_selector=dkim_selector)
    try:
        result = checker.analyze()
    except Exception as e:
        return jsonify({"error": f"Check failed: {e}"}), 500

    return jsonify(result)


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

    return jsonify({"domain": domain, "records": results})


@app.route("/analyze", methods=["POST"])
def analyze():
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
