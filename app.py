"""
InbXr — Email Intelligence Platform
Flask backend: analysis API + file parsing + admin editor + user auth.
"""

import re
import os
import tempfile
import time
import threading
import uuid
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('inbxr')

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
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, make_response

app = Flask(__name__)

from flask_wtf.csrf import CSRFProtect, validate_csrf
from wtforms import ValidationError as WTFValidationError

csrf = CSRFProtect(app)

# Disable automatic CSRF checking — we enforce it selectively for HTML form POSTs
app.config["WTF_CSRF_CHECK_DEFAULT"] = False

# Paths that require CSRF validation (HTML form submissions)
_CSRF_PROTECTED_PATHS = {
    "/admin/login",
    "/signup",
    "/login",
    "/forgot-password",
    "/account/change-password",
    "/resend-verification",
}

@app.before_request
def csrf_protect_forms():
    """Enforce CSRF validation on HTML form POST submissions only."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    # Check if this path requires CSRF protection
    if request.path in _CSRF_PROTECTED_PATHS:
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        try:
            validate_csrf(token)
        except WTFValidationError:
            from flask import abort
            abort(400, description="CSRF token missing or invalid.")
    # Also protect reset-password paths (dynamic URL)
    elif request.path.startswith("/reset-password/"):
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        try:
            validate_csrf(token)
        except WTFValidationError:
            from flask import abort
            abort(400, description="CSRF token missing or invalid.")

# ── Secret key for sessions ──────────────────────────────
import sys

_DEFAULT_SECRET = "inbxr-dev-secret-change-in-production"
_is_production = os.environ.get("FLASK_ENV") == "production" or os.environ.get("INBXR_ENV") == "production"
_secret_key = os.environ.get("SECRET_KEY", "")

if _is_production:
    if not _secret_key or _secret_key == _DEFAULT_SECRET:
        logger.critical("FATAL: SECRET_KEY is missing or using the default value. "
                        "Set a strong SECRET_KEY env var before running in production.")
        sys.exit(1)
    app.secret_key = _secret_key
else:
    if not _secret_key or _secret_key == _DEFAULT_SECRET:
        logger.warning("Using default SECRET_KEY — do NOT use this in production.")
    app.secret_key = _secret_key if _secret_key else _DEFAULT_SECRET

# ── Max upload size: 10 MB ──────────────────────────────
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# ── Permanent session lifetime ───────────────────────────
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# ── Session cookie security ─────────────────────────────
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

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

from blueprints.blog_routes import blog_bp
app.register_blueprint(blog_bp)

from blueprints.framework_routes import framework_bp
app.register_blueprint(framework_bp)

from modules.scheduler import init_scheduler
init_scheduler(app)

# ── Admin credentials (MUST be set via env vars — no defaults) ──
# ADMIN_PASS_HASH takes priority: store a PBKDF2 hash instead of plaintext.
# Generate with: python -c "from modules.auth import _hash_password; print(_hash_password('yourpassword'))"
ADMIN_USER = os.environ.get("ADMIN_USER")
_ADMIN_PASS_HASH = os.environ.get("ADMIN_PASS_HASH", "")
_ADMIN_PASS_PLAIN = os.environ.get("ADMIN_PASS", "")  # fallback for backwards compat

# ── Admin login rate limiting (DB-backed, survives restarts) ──
import time as _time
_ADMIN_RATE_LIMIT_WINDOW = 15 * 60   # 15 minutes
_ADMIN_RATE_LIMIT_MAX = 5            # max failures before block

def _check_admin_rate_limit(ip):
    """Return True if IP is blocked from admin login."""
    from modules.database import fetchone
    cutoff = _time.time() - _ADMIN_RATE_LIMIT_WINDOW
    row = fetchone(
        "SELECT COUNT(*) as cnt FROM admin_audit_log WHERE action = 'login_failed' AND ip_address = ? AND created_at > datetime('now', ?)",
        (ip, f"-{_ADMIN_RATE_LIMIT_WINDOW} seconds")
    )
    return (row["cnt"] if row else 0) >= _ADMIN_RATE_LIMIT_MAX

def _record_admin_login_failure(ip):
    """Record a failed admin login attempt (logged via _log_admin_action)."""
    pass  # Failures are already logged in admin_audit_log by _log_admin_action

def _clear_admin_login_failures(ip):
    """No-op — DB-backed rate limiting doesn't need manual clearing."""
    pass

# ── Admin session expiry ──
_ADMIN_SESSION_HOURS = 4




_tracking_tags_cache = {"data": None, "ts": 0}
_TRACKING_TAGS_TTL = 300  # 5 minutes


def _invalidate_tracking_tags_cache():
    """Force the tracking tags cache to refresh on next access."""
    _tracking_tags_cache["ts"] = 0


def _get_tracking_tags():
    """Get tracking tag HTML for injection into page headers (cached, 5-min TTL)."""
    now = time.monotonic()
    if _tracking_tags_cache["data"] is not None and (now - _tracking_tags_cache["ts"]) < _TRACKING_TAGS_TTL:
        return _tracking_tags_cache["data"]

    try:
        from modules.database import fetchall
        settings = {s["key"]: s["value"] for s in fetchall("SELECT key, value FROM site_settings")}
    except Exception:
        logger.exception("Failed to load tracking tags from site_settings")
        return {"head": "", "body": ""}

    head_parts = []
    body_parts = []

    # Meta Pixel
    pixel_id = settings.get("meta_pixel_id", "").strip()
    if pixel_id:
        head_parts.append(
            "<script>!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?"
            "n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;"
            "n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;"
            "t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,"
            "document,'script','https://connect.facebook.net/en_US/fbevents.js');"
            f"fbq('init','{pixel_id}');fbq('track','PageView');</script>"
            f'<noscript><img height="1" width="1" style="display:none" '
            f'src="https://www.facebook.com/tr?id={pixel_id}&ev=PageView&noscript=1"/></noscript>'
        )

    # Google Tag
    google_id = settings.get("google_tag_id", "").strip()
    if google_id:
        if google_id.startswith("GTM-"):
            head_parts.append(
                f"<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':new Date().getTime(),event:'gtm.js'}});"
                f"var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';"
                f"j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;"
                f"f.parentNode.insertBefore(j,f);}})(window,document,'script','dataLayer','{google_id}');</script>"
            )
            body_parts.append(
                f'<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={google_id}" '
                f'height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>'
            )
        else:
            head_parts.append(
                f'<script async src="https://www.googletagmanager.com/gtag/js?id={google_id}"></script>'
                f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}"
                f"gtag('js',new Date());gtag('config','{google_id}');</script>"
            )

    # Custom scripts
    custom_head = settings.get("custom_head_scripts", "").strip()
    if custom_head:
        head_parts.append(custom_head)

    custom_body = settings.get("custom_body_scripts", "").strip()
    if custom_body:
        body_parts.append(custom_body)

    result = {"head": "\n".join(head_parts), "body": "\n".join(body_parts)}
    _tracking_tags_cache["data"] = result
    _tracking_tags_cache["ts"] = time.monotonic()
    return result


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
        "tracking_tags": _get_tracking_tags(),
    }


# ── Email verification enforcement ────────────────────
# Logged-in users who haven't verified their email get redirected to a
# verification-required page.  Anonymous/guest users are NOT affected.
# Admin routes, auth flow routes, static files and health check are exempt.

_VERIFICATION_EXEMPT_PREFIXES = (
    "/static/",
    "/admin",
    "/webhook",
    "/blog",
)

_VERIFICATION_EXEMPT_PATHS = {
    "/",
    "/login",
    "/signup",
    "/logout",
    "/resend-verification",
    "/forgot-password",
    "/health",
    "/pricing",
    "/support",
    "/verification-required",
    "/account",
    "/account/change-password",
    "/account/api-key",
    "/create-checkout-session",
    "/customer-portal",
    "/success",
}

@app.before_request
def enforce_email_verification():
    """Redirect logged-in but unverified users away from protected routes."""
    # Only applies to logged-in users
    user_id = session.get("user_id")
    if not user_id:
        return None

    # Skip exempt prefixes (static, admin, webhooks)
    path = request.path
    if any(path.startswith(p) for p in _VERIFICATION_EXEMPT_PREFIXES):
        return None

    # Skip exempt exact paths
    if path in _VERIFICATION_EXEMPT_PATHS:
        return None

    # Skip verify-email token links (dynamic path)
    if path.startswith("/verify-email/"):
        return None

    # Skip reset-password links (dynamic path)
    if path.startswith("/reset-password/"):
        return None

    # Skip team invite links so they can still accept after verifying
    if path.startswith("/team/invite/"):
        return None

    # Check verification status
    from modules.auth import get_current_user as _get_current_user
    user = _get_current_user()
    if not user:
        return None

    if user.get("email_verified"):
        return None

    # Unverified — block with appropriate response
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "error": "Please verify your email address before using this feature.",
            "verification_required": True,
            "resend_url": "/resend-verification",
        }), 403

    return redirect("/verification-required")


@app.route("/verification-required")
def verification_required_page():
    """Show the email verification required page."""
    # If not logged in, send to login
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))
    # If already verified, send to dashboard
    from modules.auth import get_current_user as _get_current_user
    user = _get_current_user()
    if user and user.get("email_verified"):
        return redirect("/dashboard")
    return render_template("auth/verification_required.html", active_page="")


# ── Page view tracking ────────────────────────────────
_TRACKED_PAGES = {
    "/", "/analyzer", "/sender", "/placement", "/subject-scorer",
    "/bimi", "/header-analyzer", "/blacklist-monitor", "/email-verifier",
    "/warmup", "/dns-generator", "/dashboard", "/pricing", "/support",
}

@app.after_request
def track_page_view(response):
    """Record page views for analytics (public pages, HTML responses only)."""
    if (
        request.method == "GET"
        and response.status_code == 200
        and response.content_type
        and "text/html" in response.content_type
        and request.path in _TRACKED_PAGES
        and not request.path.startswith("/admin")
    ):
        try:
            from modules.database import execute
            # Map URL to page name
            page_name = request.path.strip("/") or "index"
            execute(
                "INSERT INTO page_views (page_name, ip_address, user_agent, referrer, user_id) VALUES (?, ?, ?, ?, ?)",
                (page_name, request.remote_addr, request.user_agent.string[:200] if request.user_agent else None,
                 request.referrer[:500] if request.referrer else None, session.get("user_id")),
            )
        except Exception:
            logger.exception("Failed to log page view for %s", request.path)
    return response


@app.after_request
def add_security_headers(response):
    """Add security headers to every response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com https://connect.facebook.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https: blob:; connect-src 'self' https://www.google-analytics.com https://region1.google-analytics.com; frame-ancestors 'self'; object-src 'none'; upgrade-insecure-requests"
    # Cache static assets
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=2592000'  # 30 days
    return response


# ── Error handlers ──────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def server_error(e):
    logger.exception("Unhandled 500 error: %s", e)
    return render_template('errors/500.html'), 500


# ── Health check ────────────────────────────────────
@app.route('/health')
def health_check():
    return jsonify({'status': 'ok'}), 200


@app.route('/blog-images/<path:filename>')
def serve_blog_image(filename):
    """Serve blog images — checks persistent volume, repo data/, and legacy static/ in order."""
    import os as _os
    from flask import send_from_directory, abort
    base = _os.path.dirname(_os.path.abspath(__file__))
    search_dirs = [
        _os.path.join(_os.environ.get("INBXR_DATA_DIR", _os.path.join(base, "data")), "blog_images"),
        _os.path.join(base, "data", "blog_images"),
        _os.path.join(base, "static", "images", "blog"),
    ]
    for d in search_dirs:
        full_path = _os.path.join(d, filename)
        if _os.path.exists(full_path):
            return send_from_directory(d, filename)
    app.logger.warning("[BLOG_IMAGE] 404 for %s — searched: %s", filename,
                       [d for d in search_dirs if _os.path.isdir(d)])
    abort(404)


@app.route('/robots.txt')
def robots_txt():
    """Serve robots.txt for search engines."""
    content = """User-agent: *
Allow: /
Disallow: /admin
Disallow: /admin/
Disallow: /api/
Disallow: /dashboard
Disallow: /account
Disallow: /monitors
Disallow: /team

Sitemap: https://inbxr.us/sitemap.xml
"""
    return app.response_class(content.strip(), mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    """Generate dynamic sitemap.xml."""
    from modules.database import fetchall as fetch_all
    pages = [
        ('/', '1.0', 'weekly'),
        ('/analyzer', '0.9', 'weekly'),
        ('/sender', '0.9', 'weekly'),
        ('/placement', '0.8', 'weekly'),
        ('/subject-scorer', '0.8', 'monthly'),
        ('/bimi', '0.7', 'monthly'),
        ('/header-analyzer', '0.7', 'monthly'),
        ('/blacklist-monitor', '0.7', 'monthly'),
        ('/email-verifier', '0.8', 'monthly'),
        ('/warmup', '0.6', 'monthly'),
        ('/frameworks', '0.8', 'weekly'),
        ('/blog', '0.8', 'daily'),
        ('/pricing', '0.7', 'monthly'),
        ('/support', '0.5', 'monthly'),
        ('/how-inbxr-is-different', '0.6', 'monthly'),
        ('/bulk-domain-check', '0.7', 'monthly'),
    ]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for path, priority, freq in pages:
        xml.append(f'  <url><loc>https://inbxr.us{path}</loc><priority>{priority}</priority><changefreq>{freq}</changefreq></url>')
    # Add blog posts
    try:
        posts = fetch_all("SELECT slug, updated_at, published_at FROM blog_posts WHERE status='published' ORDER BY updated_at DESC")
        for p in posts:
            lastmod = p.get("updated_at") or p.get("published_at") or ""
            lastmod_tag = f'<lastmod>{lastmod[:10]}</lastmod>' if lastmod else ''
            xml.append(f'  <url><loc>https://inbxr.us/blog/{p["slug"]}</loc>{lastmod_tag}<priority>0.6</priority><changefreq>monthly</changefreq></url>')
    except Exception:
        pass
    xml.append('</urlset>')
    return app.response_class('\n'.join(xml), mimetype='application/xml')


@app.route('/health/blog-images')
def blog_image_health():
    """Diagnostic: check blog image generation capability (admin only)."""
    if not _is_admin():
        return jsonify({'error': 'unauthorized'}), 403
    import glob as _glob
    base = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.environ.get("INBXR_DATA_DIR", os.path.join(base, "data"))
    blog_img_dir = os.path.join(data_dir, "blog_images")

    # Check directories
    dirs_info = {}
    for label, d in [("data_dir", blog_img_dir),
                     ("repo_data", os.path.join(base, "data", "blog_images")),
                     ("static", os.path.join(base, "static", "images", "blog"))]:
        if os.path.isdir(d):
            files = os.listdir(d)
            dirs_info[label] = {"path": d, "exists": True, "files": len(files), "writable": os.access(d, os.W_OK)}
        else:
            dirs_info[label] = {"path": d, "exists": False}

    # Check fonts
    fonts_found = []
    for pat in ["/nix/store/*/share/fonts/truetype/DejaVuSans.ttf",
                "/nix/store/*/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/nix/store/*/share/fonts/truetype/DejaVu/DejaVuSans.ttf",
                "/nix/store/*/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/nix/store/*/share/fonts/truetype/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        matches = _glob.glob(pat)
        if matches:
            fonts_found.extend(matches)

    # Check Pillow
    try:
        from PIL import Image as _I
        pillow_ver = _I.__version__
    except Exception as e:
        pillow_ver = f"error: {e}"

    # Check DB for posts with missing images
    from modules.database import fetchall
    posts = fetchall("SELECT id, slug, featured_image FROM blog_posts ORDER BY id DESC LIMIT 5")
    posts_info = []
    for p in posts:
        img_url = p["featured_image"]
        found = False
        if img_url:
            fname = img_url.split("/")[-1]
            for d in [blog_img_dir, os.path.join(base, "data", "blog_images"),
                      os.path.join(base, "static", "images", "blog")]:
                if os.path.exists(os.path.join(d, fname)):
                    found = True
                    break
        posts_info.append({"id": p["id"], "slug": p["slug"], "image_url": img_url, "file_exists": found})

    return jsonify({
        "INBXR_DATA_DIR": data_dir,
        "directories": dirs_info,
        "fonts_found": fonts_found[:5],
        "pillow_version": pillow_ver,
        "recent_posts": posts_info,
    })


@app.route('/health/imap')
def imap_health():
    """Diagnostic: check IMAP connectivity to seed accounts (admin only)."""
    if not _is_admin():
        return jsonify({'error': 'unauthorized'}), 403
    from modules.inbox_placement import load_seed_accounts
    import imaplib
    # Debug: check what env vars are available
    seed_debug = {
        'SEED_1_EMAIL': os.environ.get('SEED_1_EMAIL', '(not set)'),
        'SEED_ACCOUNTS': os.environ.get('SEED_ACCOUNTS', '(not set)')[:50] if os.environ.get('SEED_ACCOUNTS') else '(not set)',
    }
    accounts = load_seed_accounts()
    if not accounts:
        return jsonify({'error': 'no seed accounts found', 'debug': seed_debug})
    results = []
    for a in accounts:
        provider = a.get('provider', '')
        hosts = {'gmail': 'imap.gmail.com', 'yahoo': 'imap.mail.yahoo.com', 'outlook': 'outlook.office365.com'}
        host = a.get('imap_host', hosts.get(provider, ''))
        try:
            imap = imaplib.IMAP4_SSL(host, 993, timeout=10)
            imap.login(a['username'], a['password'])
            imap.logout()
            results.append({'email': a['email'], 'status': 'ok'})
        except Exception as e:
            results.append({'email': a['email'], 'status': f'error: {e}'})
    return jsonify({'accounts': results})


@app.route('/health/smtp')
def smtp_health():
    """Diagnostic: check email config and connectivity (admin only)."""
    if not _is_admin():
        return jsonify({'error': 'unauthorized'}), 403
    from modules.mailer import is_configured, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_FROM, BREVO_API_KEY
    info = {
        'configured': is_configured(),
        'method': 'brevo_api' if BREVO_API_KEY else 'smtp',
        'from': SMTP_FROM,
    }
    if BREVO_API_KEY:
        info['api_key'] = BREVO_API_KEY[:12] + '...'
        from http.client import HTTPSConnection
        try:
            conn = HTTPSConnection("api.brevo.com", timeout=10)
            conn.request("GET", "/v3/account", headers={"api-key": BREVO_API_KEY, "Accept": "application/json"})
            resp = conn.getresponse()
            body = resp.read().decode()
            conn.close()
            info['connection'] = 'ok' if resp.status == 200 else f'error: {resp.status} {body[:100]}'
        except Exception as e:
            info['connection'] = f'error: {e}'
    elif SMTP_HOST:
        info['host'] = SMTP_HOST
        info['port'] = SMTP_PORT
        info['user'] = SMTP_USER[:6] + '...' if SMTP_USER else ''
        import smtplib
        try:
            if SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
                server.ehlo()
                server.starttls()
                server.ehlo()
            server.login(SMTP_USER, os.environ.get('SMTP_PASS', ''))
            server.quit()
            info['connection'] = 'ok'
        except Exception as e:
            info['connection'] = f'error: {e}'
    return jsonify(info)


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
    if not session.get("is_admin", False):
        return False
    # Check session expiry
    admin_login_time = session.get("admin_login_at")
    if not admin_login_time:
        session.pop("is_admin", None)
        return False
    elapsed = _time.time() - admin_login_time
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

    # Verify admin password — prefer hashed, fallback to plaintext
    _admin_pw_ok = False
    if _ADMIN_PASS_HASH and username == ADMIN_USER:
        from modules.auth import _verify_password
        _admin_pw_ok = _verify_password(_ADMIN_PASS_HASH, password)
    elif _ADMIN_PASS_PLAIN and username == ADMIN_USER:
        import hmac
        _admin_pw_ok = hmac.compare_digest(password, _ADMIN_PASS_PLAIN)

    if _admin_pw_ok:
        session["is_admin"] = True
        session["admin_login_at"] = _time.time()
        _clear_admin_login_failures(ip)
        _log_admin_action("login", f"Admin login successful from {ip}")
        return redirect("/admin")

    _record_admin_login_failure(ip)
    _log_admin_action("login_failed", f"Failed admin login attempt from {ip} (user: {username})")
    return render_template("admin_login.html", error="Invalid username or password.")


@app.route("/admin")
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


@app.route("/admin/logout")
def admin_logout():
    _log_admin_action("logout", "Admin logged out")
    session.pop("is_admin", None)
    session.pop("admin_login_at", None)
    return redirect("/")




# ── Admin: User Management ───────────────────────────

@app.route("/admin/users")
def admin_users():
    if not _is_admin():
        return redirect("/admin/login")
    return render_template("admin_users.html", is_admin=True, active_page="admin_users")


@app.route("/admin/api/users")
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


@app.route("/admin/api/users/<int:user_id>/tier", methods=["POST"])
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


@app.route("/admin/api/users/<int:user_id>/profile")
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


@app.route("/admin/api/users/<int:user_id>/notes", methods=["POST"])
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


@app.route("/admin/api/users/<int:user_id>/notes/<int:note_id>", methods=["DELETE"])
def admin_api_delete_note(user_id, note_id):
    """Admin: Delete a note."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import execute
    execute("DELETE FROM admin_notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    return jsonify({"ok": True})


@app.route("/admin/api/users/export")
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

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=inbxr-users.csv"},
    )


# ══════════════════════════════════════════════════════
#  ADMIN — REVENUE DASHBOARD
# ══════════════════════════════════════════════════════

@app.route("/admin/revenue")
def admin_revenue():
    if not _is_admin():
        return redirect("/admin/login")
    return render_template("admin_revenue.html", is_admin=True, active_page="admin_revenue")


@app.route("/admin/api/revenue")
def admin_api_revenue():
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from modules.database import fetchone, fetchall

    PRICES = {"free": 0, "pro": 29, "agency": 79, "api": 0}

    # Current MRR
    tier_counts = fetchall("SELECT tier, COUNT(*) as cnt FROM users GROUP BY tier")
    tc = {r["tier"]: r["cnt"] for r in tier_counts}
    mrr = sum(PRICES.get(t, 0) * c for t, c in tc.items())

    # MRR trend (last 12 months) — approximate by counting users created before each month-end
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

    # Churn proxy — paid users inactive 30+ days
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

    # Conversion funnel: signups → verified → paid
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
#  ADMIN — CONVERSION DRIVERS
# ══════════════════════════════════════════════════════

@app.route("/admin/api/conversion-funnel")
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
#  ADMIN — USER SEGMENTS
# ══════════════════════════════════════════════════════

@app.route("/admin/segments")
def admin_segments():
    if not _is_admin():
        return redirect("/admin/login")
    return render_template("admin_segments.html", is_admin=True, active_page="admin_segments")


@app.route("/admin/api/segments")
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


@app.route("/admin/api/users/bulk-tier", methods=["POST"])
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
#  ADMIN — SUSPEND / REACTIVATE / FLAGS
# ══════════════════════════════════════════════════════

@app.route("/admin/api/users/<int:user_id>/suspend", methods=["POST"])
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


@app.route("/admin/api/users/<int:user_id>/reactivate", methods=["POST"])
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


@app.route("/admin/api/users/<int:user_id>/flags", methods=["POST"])
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

@app.route("/admin/api/users/<int:user_id>/email", methods=["POST"])
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


@app.route("/admin/api/users/bulk-email/status/<job_id>")
def admin_api_bulk_email_status(job_id):
    """Check the status of a bulk email job."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 403
    job = _bulk_email_jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found"}), 404
    return jsonify({"ok": True, **job})


@app.route("/admin/api/users/bulk-email", methods=["POST"])
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
#  ADMIN — FEATURE ADOPTION & TEAM ANALYTICS
# ══════════════════════════════════════════════════════

@app.route("/admin/api/feature-adoption")
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


@app.route("/admin/api/team-analytics")
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


@app.route("/admin/api/session-intelligence")
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

@app.route("/admin/api/media")
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


@app.route("/admin/api/media/upload", methods=["POST"])
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
    upload_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "static", "uploads")
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


@app.route("/admin/api/media/<int:media_id>", methods=["PUT"])
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


@app.route("/admin/api/media/<int:media_id>", methods=["DELETE"])
def admin_api_media_delete(media_id):
    if not _is_admin():
        return jsonify({"ok": False}), 403
    from modules.database import fetchone, execute
    media = fetchone("SELECT url FROM media_library WHERE id = ?", (media_id,))
    if media:
        # Try to delete physical file
        import os as _os
        filepath = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), media["url"].lstrip("/").replace("/", _os.sep))
        if _os.path.exists(filepath):
            try:
                _os.remove(filepath)
            except OSError:
                logger.exception("Failed to delete media file: %s", filepath)
        execute("DELETE FROM media_library WHERE id = ?", (media_id,))
    return jsonify({"ok": True})


_PAGE_ALIASES = {"index": "analyzer"}
def _resolve_page_name(n):
    return _PAGE_ALIASES.get(n, n)

# ── SEO Panel ────────────────────────────────────────

@app.route("/admin/api/seo/<page_name>")
def admin_api_get_seo(page_name):
    if not _is_admin():
        return jsonify({"ok": False}), 403
    page_name = _resolve_page_name(page_name)
    from modules.database import fetchone
    seo = fetchone("SELECT * FROM page_seo WHERE page_name = ?", (page_name,))
    return jsonify({"ok": True, "seo": seo})


@app.route("/admin/api/seo/<page_name>", methods=["POST"])
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

@app.route("/admin/api/page-analytics/<page_name>")
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

@app.route("/admin/api/site-settings")
def admin_api_get_settings():
    if not _is_admin():
        return jsonify({"ok": False}), 403
    from modules.database import fetchall
    settings = fetchall("SELECT key, value FROM site_settings")
    return jsonify({"ok": True, "settings": {s["key"]: s["value"] for s in settings}})


@app.route("/admin/api/site-settings", methods=["POST"])
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


@app.route("/admin/settings")
def admin_settings():
    if not _is_admin():
        return redirect("/admin/login")
    return render_template("admin_settings.html", is_admin=True, active_page="admin_settings")


# ══════════════════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("email_test.html",
                           is_admin=_is_admin(),
                           active_page="index",
                           page_title="InbXr — Sales Delivered",
                           page_description="The only email tool that diagnoses deliverability AND fixes your copy. Spam risk scoring, 100-point copy analysis, 16 copywriting frameworks, and AI rewrites — free.",
                           canonical_url="https://inbxr.us/")


@app.route("/analyzer")
def analyzer():
    return render_template("index.html",
                           is_admin=_is_admin(),
                           active_page="analyzer",
                           page_title="Email Copy Analyzer — InbXr",
                           page_description="Paste your email and get a 100-point copy score, framework detection, spam risk analysis, readability metrics, and AI-powered framework rewrites.",
                           canonical_url="https://inbxr.us/analyzer")


@app.route("/sender")
def sender():
    return render_template("sender.html",
                           is_admin=_is_admin(),
                           active_page="sender",
                           page_title="Sender Reputation Check — InbXr",
                           page_description="Check your domain's email authentication (SPF, DKIM, DMARC), scan 100+ blocklists, and get DNS fix records — all in one tool.",
                           canonical_url="https://inbxr.us/sender")


@app.route("/support")
def support_page():
    return render_template("support.html",
                           is_admin=_is_admin(),
                           active_page="support",
                           page_title="Help & Support — InbXr",
                           page_description="Get help with InbXr tools. FAQ, AI support chat, and contact information.",
                           canonical_url="https://inbxr.us/support")


@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html",
                           is_admin=_is_admin(),
                           active_page="privacy")


@app.route("/terms")
def terms_page():
    return render_template("terms.html",
                           is_admin=_is_admin(),
                           active_page="terms")


@app.route("/how-inbxr-is-different")
def how_different():
    return render_template("how_different.html",
                           is_admin=_is_admin(),
                           active_page="how_different",
                           page_title="How InbXr Is Different — Sales Delivered",
                           page_description="The only email platform with deliverability diagnostics AND copy intelligence. 100-point copy scoring, 16 copywriting frameworks, AI rewrites, and framework detection — starting at $0.",
                           canonical_url="https://inbxr.us/how-inbxr-is-different")


@app.route("/api/support/chat", methods=["POST"])
def support_chat_api():
    from modules.support_chat import chat, is_available
    if not is_available():
        return jsonify({"error": "Support chat is not available right now."}), 503

    data = request.get_json(silent=True) or {}
    agent_type = data.get("agent", "support")

    # Both support agents are free for everyone
    messages = data.get("messages", [])

    if not messages:
        return jsonify({"error": "No message provided."}), 400

    result = chat(agent_type, messages)
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route("/api/assistant/chat", methods=["POST"])
def assistant_chat_api():
    """InbXr Expert Email Assistant — Pro/Agency only."""
    if not session.get("user_id"):
        return jsonify({"error": "Please log in to use the Email Assistant.", "signup_url": "/signup"}), 429
    tier = session.get("user_tier", "free")
    if tier not in ("pro", "agency", "api"):
        return jsonify({"error": "The Email Assistant is available on Pro and Agency plans.", "upgrade_url": "/account"}), 403

    from modules.assistant_chat import chat as assistant_chat, is_available
    if not is_available():
        return jsonify({"error": "Email Assistant is not available right now."}), 503

    # Pro: 10 conversations/month; Agency/API: unlimited
    if tier == "pro":
        from modules.rate_limiter import check_monthly_limit
        allowed, remaining = check_monthly_limit(session["user_id"], "assistant_chat", 10)
        if not allowed:
            return jsonify({
                "error": "You've used your 10 Email Expert conversations for this month. Upgrade to Agency for unlimited.",
                "upgrade_url": "/account",
                "remaining": 0,
            }), 429

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "No message provided."}), 400

    user_id = session["user_id"]
    team_id = session.get("current_team_id")
    result = assistant_chat(user_id, messages, team_id=team_id)
    if "error" in result:
        return jsonify(result), 500

    # Log usage for rate limiting
    from modules.rate_limiter import log_usage
    log_usage("assistant_chat")

    # Include remaining count for Pro users
    if tier == "pro":
        from modules.rate_limiter import check_monthly_limit
        _, remaining = check_monthly_limit(session["user_id"], "assistant_chat", 10)
        result["remaining"] = remaining
        result["monthly_limit"] = 10

    return jsonify(result)


@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next="/dashboard"))

    from modules.history import get_history_stats
    from modules.rate_limiter import get_usage_summary
    from modules.tiers import get_tier, get_tier_limit

    user_id = session["user_id"]
    tier_name = session.get("user_tier", "free")
    tier = get_tier(tier_name)
    stats = get_history_stats(user_id, team_id=session.get("team_id"))
    usage = get_usage_summary(user_id)

    credits = {
        "tier": tier_name,
        "tier_label": tier["name"] if tier else tier_name.title(),
        "daily_limit": get_tier_limit(tier_name, "checks_per_day"),
        "used_today": usage.get("total_today", 0),
        "remaining": max(0, get_tier_limit(tier_name, "checks_per_day") - usage.get("total_today", 0)),
        "verify_limit": get_tier_limit(tier_name, "email_verifications_per_day"),
        "placement_limit": get_tier_limit(tier_name, "placement_tests_per_day"),
        "subject_limit": get_tier_limit(tier_name, "subject_tests_per_day"),
    }

    from modules.onboarding import get_onboarding_status
    ob_status = get_onboarding_status(user_id)

    resp = render_template("dashboard.html",
                           stats=stats,
                           credits=credits,
                           ob_status=ob_status,
                           is_admin=_is_admin(),
                           active_page="dashboard")
    session.pop("is_new_signup", None)
    return resp


@app.route("/api/onboarding")
def api_onboarding():
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    from modules.onboarding import get_onboarding_status
    status = get_onboarding_status(session["user_id"])
    return jsonify(status)


@app.route("/api/onboarding/dismiss", methods=["POST"])
def api_onboarding_dismiss():
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    from modules.database import execute as _exec
    _exec("UPDATE users SET onboarding_dismissed_at = datetime('now') WHERE id = ?",
          (session["user_id"],))
    return jsonify({"ok": True})


@app.route("/subject-scorer")
def subject_scorer():
    return render_template("subject_scorer.html",
                           is_admin=_is_admin(),
                           active_page="subject_scorer",
                           page_title="Subject Line Scorer — InbXr",
                           page_description="A/B test up to 10 subject lines across 7 dimensions. Get scores, rankings, and actionable tips to boost open rates.",
                           canonical_url="https://inbxr.us/subject-scorer")


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
    if not token or not re.match(r'^InbXr-[A-F0-9]{8}$', token):
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
        logger.exception("Email test analysis failed")
        return jsonify({"error": f"Analysis failed: {str(e)[:200]}"}), 500

    analysis["status"] = "found"

    # ── ESP vs Domain diagnostic ──
    esp_diagnostic = {"verdict": "unknown", "message": "", "details": []}
    auth_ok = True
    content_ok = True
    placement_ok = True

    # Check authentication from header grades
    header_grades = analysis.get("header_grades", [])
    for hg in header_grades:
        label = (hg.get("label") or "").upper()
        status = (hg.get("status") or "")
        if label == "SPF" and status == "fail":
            auth_ok = False
            esp_diagnostic["details"].append("SPF is failing — this is a domain/DNS issue, not your ESP.")
        if label == "DKIM" and status == "fail":
            auth_ok = False
            esp_diagnostic["details"].append("DKIM is failing — check your DNS records or ESP DKIM setup.")
        if label == "DMARC" and status == "fail":
            auth_ok = False
            esp_diagnostic["details"].append("DMARC is failing — add or fix your DMARC record.")

    # Check reputation blocklists
    rep_data_diag = analysis.get("reputation", {})
    if isinstance(rep_data_diag, dict):
        rep_section = rep_data_diag.get("reputation", rep_data_diag)
        listed_count_diag = rep_section.get("listed_count", 0) if isinstance(rep_section, dict) else 0
        if listed_count_diag > 0:
            auth_ok = False
            esp_diagnostic["details"].append(f"Your IP is listed on {listed_count_diag} blocklist(s) — this could be your ESP's shared IP.")

    # Check content (spam analysis)
    spam_diag = analysis.get("spam", {})
    if isinstance(spam_diag, dict):
        risk_score = spam_diag.get("score", 0)
        if risk_score is not None and risk_score > 60:
            content_ok = False
            esp_diagnostic["details"].append(f"Spam risk score is {risk_score}/100 — your content has spam triggers.")

    # Check placement
    placement_diag = analysis.get("placement", {})
    if isinstance(placement_diag, dict):
        if placement_diag.get("placement") == "spam" or placement_diag.get("folder") == "spam":
            placement_ok = False

    if auth_ok and content_ok and not placement_ok:
        esp_diagnostic["verdict"] = "esp"
        esp_diagnostic["message"] = "Your domain auth and content look fine, but you're landing in spam. The problem is likely your ESP's shared IP reputation. Consider switching to a dedicated IP or a different provider."
    elif not auth_ok and content_ok:
        esp_diagnostic["verdict"] = "domain"
        esp_diagnostic["message"] = "Your content is fine, but your domain authentication has issues. Fix your DNS records first — this is the most likely cause."
    elif auth_ok and not content_ok:
        esp_diagnostic["verdict"] = "content"
        esp_diagnostic["message"] = "Your domain auth is solid, but your email content is triggering spam filters. Review the spam triggers below and use the AI rewriter to fix them."
    elif not auth_ok and not content_ok:
        esp_diagnostic["verdict"] = "both"
        esp_diagnostic["message"] = "Both your domain auth and email content have issues. Fix your DNS records first, then clean up the content."
    elif auth_ok and content_ok and placement_ok:
        esp_diagnostic["verdict"] = "clean"
        esp_diagnostic["message"] = "Everything looks good. Your domain, content, and inbox placement all check out."

    analysis["esp_diagnostic"] = esp_diagnostic

    # Save to history
    if session.get("user_id"):
        from modules.tiers import has_feature
        if has_feature(session.get("user_tier", "free"), "cloud_history"):
            from modules.history import save_result
            placement = analysis.get("placement", {})
            grade_map = {"inbox": "A", "spam": "F", "trash": "F", "not_found": "D"}
            score_map = {"inbox": 100, "spam": 10, "trash": 5, "not_found": 40}
            p = placement.get("placement", "not_found")
            summary = analysis.get("content", {}).get("clean_subject") or token[:20]
            save_result(session["user_id"], "email_test", summary, analysis,
                        grade=grade_map.get(p, "C"), score=score_map.get(p, 50))

    # ── Gate logic: anonymous users see summary only ──
    is_logged_in = bool(session.get("user_id"))
    lead_cookie = request.cookies.get("inbxr_lead")
    gated = not is_logged_in and not lead_cookie

    if gated:
        # Cache full analysis so we can send it when they provide email
        import time as _cache_t
        _analysis_cache[token] = {"data": analysis, "timestamp": _cache_t.time()}
        # Clean old cache entries
        now = _cache_t.time()
        stale = [k for k, v in _analysis_cache.items() if now - v["timestamp"] > _CACHE_TTL]
        for k in stale:
            del _analysis_cache[k]

    analysis["gated"] = gated
    analysis["_token"] = token

    resp = jsonify(analysis)
    return resp


# ── Email Gate: cached analysis by token ────────────
_analysis_cache = {}  # {token: {data, timestamp}}
_CACHE_TTL = 3600  # 1 hour


# ── Email Report Sending ────────────────────────────
_email_report_rate = {}  # {ip: [timestamp, ...]}

@app.route("/api/email-report", methods=["POST"])
def api_email_report():
    """Send the email test report to a user's email address."""
    import time as _t
    from modules.mailer import _send, is_configured

    if not is_configured():
        return jsonify({"error": "Email sending is not configured."}), 503

    # Rate limit: 3 per hour per IP
    ip = request.remote_addr or "unknown"
    now = _t.time()
    cutoff = now - 3600
    hits = _email_report_rate.get(ip, [])
    hits = [t for t in hits if t > cutoff]
    if len(hits) >= 3:
        return jsonify({"error": "Too many requests. You can send up to 3 report emails per hour."}), 429
    hits.append(now)
    _email_report_rate[ip] = hits

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    email = (data.get("email") or "").strip().lower()
    report_html = (data.get("report_html") or "").strip()

    # Validate email
    if not email or not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({"error": "Please enter a valid email address."}), 400

    if not report_html or len(report_html) > 100000:
        return jsonify({"error": "Invalid report data."}), 400

    # Send using existing mailer
    subject = "Your InbXr Email Test Report"
    ok = _send(email, subject, report_html)
    if ok:
        logger.info("Email report sent to %s from IP %s", email, ip)
        return jsonify({"ok": True})
    else:
        return jsonify({"error": "Failed to send email. Please try again."}), 500


@app.route("/api/unlock-report", methods=["POST"])
def api_unlock_report():
    """Capture lead email and send verification email."""
    import secrets
    from modules.mailer import _send, is_configured
    from modules import database as db

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    email = (data.get("email") or "").strip().lower()
    token = (data.get("token") or "").strip()

    # Validate email
    if not email or not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({"error": "Please enter a valid email address."}), 400

    if not token:
        return jsonify({"error": "Missing test token."}), 400

    # Check if this email is already verified (returning lead)
    existing = db.fetchone("SELECT id, verified FROM lead_emails WHERE email = ?", (email,))
    if existing and existing["verified"]:
        # Already verified — skip verification, return full data + set cookie
        cached = _analysis_cache.get(token)
        full_data = cached["data"] if cached else None
        resp_data = {"ok": True, "verified": True}
        if full_data:
            full_data["gated"] = False
            resp_data["analysis"] = full_data
        resp = make_response(jsonify(resp_data))
        resp.set_cookie("inbxr_lead", email, max_age=60*60*24*365, httponly=True, samesite="Lax")
        return resp

    # Generate verification token
    v_token = secrets.token_urlsafe(32)

    # Store or update lead
    if existing:
        db.execute(
            "UPDATE lead_emails SET verification_token = ?, test_token = ? WHERE id = ?",
            (v_token, token, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO lead_emails (email, ip_address, source, verification_token, test_token) VALUES (?, ?, ?, ?, ?)",
            (email, request.remote_addr or "unknown", "email_test_gate", v_token, token),
        )
    logger.info("Lead captured: %s from IP %s (verification pending)", email, request.remote_addr)

    # Send verification email
    if is_configured():
        base_url = os.environ.get("BASE_URL", "https://inbxr.us")
        verify_url = f"{base_url}/verify-lead/{v_token}"
        subject = "Verify your email to unlock your InbXr report"
        html = f"""
        <div style="font-family:Inter,Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
          <h2 style="color:#0c1a3a;margin:0 0 8px;font-size:20px;">Your report is ready</h2>
          <p style="color:#334155;font-size:15px;line-height:1.6;">
            Click the button below to verify your email and unlock your full InbXr email test report.
          </p>
          <a href="{verify_url}"
             style="display:inline-block;background:#16a34a;color:#fff;padding:12px 28px;
                    border-radius:999px;text-decoration:none;font-weight:600;font-size:15px;
                    margin:20px 0;">
            Verify &amp; Unlock Report
          </a>
          <p style="color:#64748b;font-size:13px;line-height:1.5;margin-top:24px;">
            Or copy this link:<br>
            <a href="{verify_url}" style="color:#16a34a;word-break:break-all;">{verify_url}</a>
          </p>
          <p style="color:#94a3b8;font-size:12px;margin-top:32px;">
            InbXr &mdash; Free email deliverability tools. <a href="https://inbxr.us" style="color:#94a3b8;">inbxr.us</a>
          </p>
        </div>
        """
        text = f"Verify your email to unlock your InbXr report: {verify_url}"
        _send(email, subject, html, text)

    return jsonify({"ok": True, "verified": False, "lead_token": v_token})


@app.route("/verify-lead/<v_token>")
def verify_lead(v_token):
    """Verify a lead email and unlock the report."""
    from modules.mailer import _send, is_configured
    from modules import database as db

    lead = db.fetchone("SELECT * FROM lead_emails WHERE verification_token = ?", (v_token,))
    if not lead:
        return redirect("/", code=302)

    # Mark as verified
    db.execute("UPDATE lead_emails SET verified = 1 WHERE id = ?", (lead["id"],))
    logger.info("Lead verified: %s", lead["email"])

    # Send the full report email if we have cached analysis
    cached = _analysis_cache.get(lead.get("test_token", ""))
    if cached and is_configured():
        from modules.mailer import _send
        analysis = cached["data"]
        # Build a server-side report email
        report_html = _build_report_email_html(analysis)
        _send(lead["email"], "Your InbXr Email Test Report", report_html)

    # Set cookie and redirect to homepage
    resp = make_response(redirect("/?verified=1", code=302))
    resp.set_cookie("inbxr_lead", lead["email"], max_age=60*60*24*365, httponly=True, samesite="Lax")
    return resp


@app.route("/api/check-lead-status", methods=["POST"])
def api_check_lead_status():
    """Poll endpoint to check if a lead email has been verified."""
    from modules import database as db

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"verified": False})

    lead_token = (data.get("lead_token") or "").strip()
    if not lead_token:
        return jsonify({"verified": False})

    lead = db.fetchone(
        "SELECT verified, test_token FROM lead_emails WHERE verification_token = ?",
        (lead_token,),
    )
    if not lead or not lead["verified"]:
        return jsonify({"verified": False})

    # Return full analysis if available
    cached = _analysis_cache.get(lead.get("test_token", ""))
    resp_data = {"verified": True}
    if cached:
        cached["data"]["gated"] = False
        resp_data["analysis"] = cached["data"]

    resp = make_response(jsonify(resp_data))
    resp.set_cookie("inbxr_lead", "verified", max_age=60*60*24*365, httponly=True, samesite="Lax")
    return resp


def _build_report_email_html(analysis):
    """Build a comprehensive HTML email report from analysis data."""
    p = analysis.get("placement", {})
    spam = analysis.get("spam", {})
    copy = analysis.get("copy", {})
    grades = analysis.get("header_grades", [])
    esp = analysis.get("esp_diagnostic", {})

    # Verdict
    in_spam = p.get("placement") in ("spam", "trash")
    in_promo = p.get("placement") == "inbox" and p.get("tab") == "promotions"
    verdict = "Results Ready"
    verdict_color = "#3b82f6"
    if in_spam:
        verdict = "Landed in Spam"
        verdict_color = "#ef4444"
    elif in_promo:
        verdict = "Promotions Tab"
        verdict_color = "#f59e0b"
    elif p.get("placement") == "inbox":
        verdict = "Inbox"
        verdict_color = "#22c55e"

    # Grade pills
    grade_colors = {"pass": "#22c55e", "warning": "#f59e0b", "fail": "#ef4444", "missing": "#94a3b8"}
    grade_letters = {"pass": "A", "warning": "C", "fail": "F", "missing": "?"}
    grade_html = ""
    for g in grades:
        c = grade_colors.get(g.get("status"), "#94a3b8")
        l = g.get("grade") or grade_letters.get(g.get("status"), "?")
        label = g.get("label", "")
        detail = g.get("detail", "")
        grade_html += (
            f'<td style="text-align:center;padding:8px 10px;vertical-align:top;">'
            f'<span style="display:inline-block;width:32px;height:32px;line-height:32px;border-radius:50%;'
            f'background:{c};color:#fff;font-weight:700;font-size:14px;">{l}</span>'
            f'<br><span style="font-size:12px;color:#64748b;">{label}</span>'
            f'</td>'
        )

    # Issues
    issues = []
    for g in grades:
        if g.get("status") == "fail":
            issues.append(f'<strong>{g["label"]}</strong> is failing — {g.get("detail", "needs attention")}')
        elif g.get("status") == "warning":
            issues.append(f'<strong>{g["label"]}</strong> — {g.get("detail", "has warnings")}')
    if spam.get("score", 0) > 40:
        issues.append(f'Spam risk score is <strong>{spam["score"]}/100</strong> — review content triggers')
    if copy.get("score") is not None and copy["score"] < 50:
        issues.append(f'Copy score is <strong>{copy["score"]}/100</strong> — improve email content')

    issues_html = ""
    if issues:
        issues_html = '<h3 style="color:#0c1a3a;font-size:15px;margin:24px 0 8px;">Issues Found</h3><ul style="margin:0;padding-left:20px;">'
        for issue in issues:
            issues_html += f'<li style="color:#334155;font-size:14px;line-height:1.8;">{issue}</li>'
        issues_html += "</ul>"
    else:
        issues_html = '<p style="color:#22c55e;font-size:14px;margin:16px 0;">No critical issues found — your email looks good.</p>'

    # ESP diagnostic
    esp_html = ""
    if esp.get("verdict") and esp["verdict"] != "unknown":
        esp_labels = {"clean": "All Clear", "domain": "Domain Issue", "content": "Content Issue", "esp": "ESP Issue", "both": "Multiple Issues"}
        esp_html = (
            f'<div style="background:{verdict_color}10;border-left:4px solid {verdict_color};padding:12px 16px;border-radius:6px;margin:16px 0;">'
            f'<strong style="font-size:13px;">Diagnosis: {esp_labels.get(esp["verdict"], esp["verdict"])}</strong>'
            f'<p style="font-size:13px;color:#334155;margin:6px 0 0;">{esp.get("message", "")}</p>'
            f'</div>'
        )

    # Scores
    scores_html = ""
    if spam.get("score") is not None:
        sc = spam["score"]
        sc_color = "#22c55e" if sc <= 20 else "#f59e0b" if sc <= 40 else "#ef4444"
        scores_html += (
            f'<td style="padding:8px 16px;text-align:center;">'
            f'<span style="font-size:24px;font-weight:700;color:{sc_color};">{sc}</span>'
            f'<span style="color:#64748b;font-size:13px;">/100</span><br>'
            f'<span style="font-size:12px;color:#64748b;">Spam Risk</span></td>'
        )
    if copy.get("score") is not None:
        cc = copy["score"]
        cc_color = "#22c55e" if cc >= 70 else "#f59e0b" if cc >= 50 else "#ef4444"
        scores_html += (
            f'<td style="padding:8px 16px;text-align:center;">'
            f'<span style="font-size:24px;font-weight:700;color:{cc_color};">{cc}</span>'
            f'<span style="color:#64748b;font-size:13px;">/100</span><br>'
            f'<span style="font-size:12px;color:#64748b;">Copy Score</span></td>'
        )

    return (
        '<div style="font-family:Inter,Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;">'
        '<h2 style="color:#0c1a3a;margin:0 0 4px;font-size:20px;">Your Full Email Test Report</h2>'
        '<p style="color:#64748b;font-size:13px;margin:0 0 20px;">from InbXr &mdash; Email Intelligence Platform</p>'
        f'<div style="background:{verdict_color}10;border-left:4px solid {verdict_color};padding:12px 16px;border-radius:6px;margin-bottom:20px;">'
        f'<span style="font-size:16px;font-weight:700;color:{verdict_color};">{verdict}</span>'
        + (f'<span style="color:#64748b;font-size:13px;margin-left:8px;">({p.get("tab", "")})</span>' if p.get("tab") else "")
        + '</div>'
        + (f'<table style="width:100%;border-collapse:collapse;margin:16px 0;"><tr>{grade_html}</tr></table>' if grade_html else "")
        + esp_html
        + (f'<table style="width:100%;border-collapse:collapse;margin:12px 0;"><tr>{scores_html}</tr></table>' if scores_html else "")
        + issues_html
        + '<div style="text-align:center;margin:28px 0 16px;">'
        '<a href="https://inbxr.us/" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 28px;border-radius:999px;text-decoration:none;font-weight:600;font-size:15px;">Run Another Test</a>'
        '</div>'
        '<p style="color:#94a3b8;font-size:12px;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:16px;">InbXr &mdash; Free email deliverability tools. <a href="https://inbxr.us" style="color:#94a3b8;">inbxr.us</a></p>'
        '</div>'
    )


@app.route("/dns-generator")
def dns_generator():
    """Redirect to Sender Check which handles DNS generation."""
    qs = request.query_string.decode()
    target = "/sender" + ("?" + qs if qs else "")
    return redirect(target, code=302)


@app.route("/bimi")
def bimi():
    return render_template("bimi_checker.html",
                           is_admin=_is_admin(),
                           active_page="bimi",
                           page_title="BIMI Checker — InbXr",
                           page_description="Validate your BIMI record, SVG logo, and VMC certificate. Check if your brand logo will appear in email inboxes.",
                           canonical_url="https://inbxr.us/bimi")


@app.route("/placement")
def placement():
    return render_template("placement.html",
                           is_admin=_is_admin(),
                           active_page="placement",
                           page_title="Inbox Placement Test — InbXr",
                           page_description="Send a test email and see exactly where it lands — inbox, spam, or promotions — across Gmail, Yahoo, and Outlook.",
                           canonical_url="https://inbxr.us/placement")


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
    if not token or not re.match(r'^InbXr-[A-F0-9]{8}$', token):
        return jsonify({"error": "Invalid or missing test token."}), 400

    tester = InboxPlacementTester(token=token)
    try:
        results = tester.check_all()
    except Exception as e:
        logger.exception("Inbox placement check failed")
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

    response = {
        "token": token,
        "results": results,
        "summary": summary,
        "recommendations": generate_recommendations(results, summary),
    }

    # Save to history
    if session.get("user_id"):
        from modules.tiers import has_feature
        if has_feature(session.get("user_tier", "free"), "cloud_history"):
            from modules.history import save_result
            inbox_pct = round(inbox_count / total * 100) if total > 0 else 0
            grade = "A" if inbox_pct >= 90 else "B" if inbox_pct >= 70 else "C" if inbox_pct >= 50 else "F"
            save_result(session["user_id"], "placement_test", token, response,
                        grade=grade, score=inbox_pct)

    return jsonify(response)


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
        logger.exception("Seed cleanup failed")
        return jsonify({"error": f"Cleanup failed: {e}"}), 500
    return jsonify(result)


# ══════════════════════════════════════════════════════
#  HEADER ANALYZER PAGE + API
# ══════════════════════════════════════════════════════

@app.route("/header-analyzer")
def header_analyzer():
    return render_template("header_analyzer.html",
                           is_admin=_is_admin(),
                           active_page="header_analyzer",
                           page_title="Email Header Analyzer — InbXr",
                           page_description="Paste raw email headers and get authentication verdicts, routing details, TLS analysis, and delivery delay breakdowns.",
                           canonical_url="https://inbxr.us/header-analyzer")


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
        logger.exception("Failed to parse email headers")
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
            except (ValueError, TypeError):
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

    header_response = {
        "authentication_results": auth_results,
        "received_chain": received_chain,
        "tls_info": tls_info,
        "dkim_signature": dkim_sig,
        "envelope": envelope,
        "x_headers": x_headers,
        "all_headers": all_headers,
        "summary": summary,
    }

    # Save to history
    if session.get("user_id"):
        from modules.tiers import has_feature
        if has_feature(session.get("user_tier", "free"), "cloud_history"):
            from modules.history import save_result
            h_summary = envelope.get("subject", envelope.get("from", "Header Analysis"))[:80]
            h_score = round(auth_pass_count / 3 * 100) if auth_pass_count else 0
            h_grade = "A" if h_score >= 90 else "B" if h_score >= 60 else "C" if h_score >= 30 else "F"
            save_result(session["user_id"], "header_analysis", h_summary, header_response,
                        grade=h_grade, score=h_score)

    return jsonify(header_response)


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
            logger.exception("Non-fatal: DNS suggestions generation failed")
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
            logger.exception("Non-fatal: DNS suggestions generation failed")
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
#  BULK DOMAIN CHECKER
# ══════════════════════════════════════════════════════

@app.route("/bulk-domain-check")
def bulk_domain_check_page():
    return render_template("bulk_domain_check.html",
                           is_admin=_is_admin(),
                           active_page="bulk_domain_check",
                           page_title="Bulk Domain Checker — InbXr",
                           page_description="Check up to 10 domains at once. Get instant SPF, DKIM, DMARC, MX, and blocklist health grades for all your sending domains.",
                           canonical_url="https://inbxr.us/bulk-domain-check")


@app.route("/api/bulk-domain-check", methods=["POST"])
def api_bulk_domain_check():
    """Check multiple domains at once — quick health summary."""
    from modules.reputation_checker import check_domain_auth, check_domain_dnsbls
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import dns.resolver

    data = request.get_json(force=True)
    domains = data.get("domains", [])

    # Clean and validate
    domains = [d.strip().lower() for d in domains if d.strip()]
    domains = list(dict.fromkeys(domains))  # dedupe preserving order

    if not domains:
        return jsonify({"error": "No domains provided"}), 400
    if len(domains) > 10:
        return jsonify({"error": "Maximum 10 domains"}), 400

    def check_one(domain):
        result = {"domain": domain, "spf": False, "dkim": False, "dmarc": False, "mx": False, "blocklists_clean": True, "listed_count": 0, "grade": "F", "issues": []}
        try:
            # MX check
            try:
                mx = dns.resolver.resolve(domain, "MX", lifetime=5)
                result["mx"] = len(mx) > 0
            except Exception:
                result["issues"].append("No MX records")

            # SPF
            try:
                txt = dns.resolver.resolve(domain, "TXT", lifetime=5)
                for r in txt:
                    if "v=spf1" in str(r):
                        result["spf"] = True
                        break
            except Exception:
                pass
            if not result["spf"]:
                result["issues"].append("Missing SPF")

            # DMARC
            try:
                txt = dns.resolver.resolve(f"_dmarc.{domain}", "TXT", lifetime=5)
                for r in txt:
                    if "v=DMARC1" in str(r).upper():
                        result["dmarc"] = True
                        break
            except Exception:
                pass
            if not result["dmarc"]:
                result["issues"].append("Missing DMARC")

            # DKIM — try common selectors
            for sel in ["default", "google", "selector1", "selector2", "k1", "s1", "s2"]:
                try:
                    dns.resolver.resolve(f"{sel}._domainkey.{domain}", "TXT", lifetime=3)
                    result["dkim"] = True
                    break
                except Exception:
                    continue
            if not result["dkim"]:
                result["issues"].append("No DKIM found")

            # Quick blocklist check (top 5 critical only)
            critical_zones = ["dbl.spamhaus.org", "multi.surbl.org", "black.uribl.com"]
            for zone in critical_zones:
                try:
                    dns.resolver.resolve(f"{domain}.{zone}", "A", lifetime=3)
                    result["blocklists_clean"] = False
                    result["listed_count"] += 1
                except Exception:
                    pass
            if not result["blocklists_clean"]:
                result["issues"].append(f"Listed on {result['listed_count']} blocklist(s)")

            # Grade
            score = sum([result["spf"], result["dkim"], result["dmarc"], result["mx"], result["blocklists_clean"]])
            result["grade"] = ["F", "D", "C", "B", "A-", "A"][min(score, 5)]

        except Exception as e:
            result["issues"].append(f"Check failed: {str(e)[:80]}")
        return result

    results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(check_one, d): d for d in domains}
        for f in as_completed(futures):
            results.append(f.result())

    # Sort by original order
    domain_order = {d: i for i, d in enumerate(domains)}
    results.sort(key=lambda r: domain_order.get(r["domain"], 99))

    return jsonify({"ok": True, "results": results})


# ══════════════════════════════════════════════════════
#  BLACKLIST MONITOR PAGE + API
# ══════════════════════════════════════════════════════

@app.route("/blacklist-monitor")
def blacklist_monitor():
    return render_template("blacklist_monitor.html",
                           is_admin=_is_admin(),
                           active_page="blacklist_monitor",
                           page_title="Blacklist Monitor — InbXr",
                           page_description="Monitor your domains against 100+ email blocklists. Get alerts when your domain gets listed or delisted.",
                           canonical_url="https://inbxr.us/blacklist-monitor")


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
    return render_template("warmup.html",
                           is_admin=_is_admin(),
                           active_page="warmup",
                           page_title="Warm-up Tracker — InbXr",
                           page_description="Track your IP and domain warm-up campaigns with daily volume logging, progress charts, and best-practice guidance.",
                           canonical_url="https://inbxr.us/warmup")


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
    return render_template("email_verifier.html",
                           is_admin=_is_admin(),
                           active_page="email_verifier",
                           page_title="Email Verifier — InbXr",
                           page_description="Verify any email address instantly. Check syntax, MX records, disposable status, and SMTP mailbox existence.",
                           canonical_url="https://inbxr.us/email-verifier")


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

    def run_domain_age():
        from modules.reputation_checker import get_domain_age_info
        return get_domain_age_info(domain)

    domain_age_data = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_rep = executor.submit(run_reputation)
        future_bimi = executor.submit(run_bimi)
        future_mx = executor.submit(run_mx)
        future_ssl = executor.submit(run_ssl)
        future_age = executor.submit(run_domain_age)

        try:
            rep_result = future_rep.result(timeout=30)
        except Exception as e:
            return jsonify({"error": f"Check failed: {e}"}), 500

        try:
            bimi_data = future_bimi.result(timeout=15) or {}
        except Exception:
            logger.exception("Non-fatal: BIMI check failed")
            bimi_data = {}

        try:
            mx_data = future_mx.result(timeout=10)
        except Exception:
            logger.exception("Non-fatal: MX check failed")
            mx_data = {"found": False, "records": []}

        try:
            ssl_data = future_ssl.result(timeout=10)
        except Exception:
            logger.exception("Non-fatal: SSL check failed")
            ssl_data = {"connected": False}

        try:
            domain_age_data = future_age.result(timeout=10)
        except Exception:
            logger.exception("Non-fatal: Domain age check failed")
            domain_age_data = {}

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
    rep_result["domain_age"] = domain_age_data

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
    """AI-powered email rewrite using Groq API (Pro+ only)."""
    if not session.get("user_id"):
        return jsonify({"error": "Please log in to use AI rewrite.", "signup_url": "/signup"}), 429
    tier = session.get("user_tier", "free")
    if tier not in ("pro", "agency", "api"):
        return jsonify({
            "error": "AI rewrite is available on Pro and Agency plans.",
            "upgrade_url": "/account",
            "upgrade_feature": "AI Copy Rewriter",
            "upgrade_desc": "Get AI-powered rewrites with tone selection, framework-aware output, and step-mapped results.",
            "show_upgrade": True,
        }), 403

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
        logger.exception("AI rewrite failed")
        return jsonify({"error": f"Rewrite failed: {str(e)[:100]}"}), 500

    return jsonify(result)


@app.route("/ai-rewrite-framework", methods=["POST"])
def ai_rewrite_framework():
    """AI-powered email rewrite structured by a copywriting framework (Pro+ only)."""
    if not session.get("user_id"):
        return jsonify({"error": "Please log in to use AI rewrite.", "signup_url": "/signup"}), 429
    tier = session.get("user_tier", "free")
    if tier not in ("pro", "agency", "api"):
        return jsonify({
            "error": "Framework rewrites are available on Pro and Agency plans.",
            "upgrade_url": "/account",
            "upgrade_feature": "Framework-Aware AI Rewriter",
            "upgrade_desc": "Rewrite emails using 16 proven copywriting frameworks with step-by-step structure.",
            "show_upgrade": True,
        }), 403

    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    tone = (data.get("tone") or "professional").strip()
    issues = data.get("issues") or []
    framework_slug = (data.get("framework_slug") or "").strip()
    user_framework_id = data.get("user_framework_id")

    if not subject and not body:
        return jsonify({"error": "Subject or body is required."}), 400

    # Resolve framework
    import json as _json
    from modules.frameworks import get_framework_by_slug, get_user_framework, log_framework_usage
    from modules.ai_rewriter import rewrite_with_framework, is_available, AIRewriteError

    if not is_available():
        return jsonify({"error": "AI rewrite not available — set GROQ_API_KEY environment variable."}), 503

    framework_name = None
    framework_steps = None
    fw_id = None

    if user_framework_id:
        ufw = get_user_framework(session["user_id"], user_framework_id)
        if not ufw:
            return jsonify({"error": "Custom framework not found."}), 404
        framework_name = ufw["name"]
        framework_steps = _json.loads(ufw["steps_json"]) if ufw["steps_json"] else []
    elif framework_slug:
        fw = get_framework_by_slug(framework_slug)
        if not fw:
            return jsonify({"error": "Framework not found."}), 404
        fw_id = fw["id"]
        framework_name = fw["name"]
        framework_steps = _json.loads(fw["steps_json"]) if fw["steps_json"] else []
    else:
        return jsonify({"error": "framework_slug or user_framework_id is required."}), 400

    if not framework_steps:
        return jsonify({"error": "Framework has no steps defined."}), 400

    try:
        result = rewrite_with_framework(
            subject=subject, body=body,
            framework_name=framework_name, framework_steps=framework_steps,
            tone=tone, issues=issues,
        )
    except AIRewriteError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.exception("Framework rewrite failed")
        return jsonify({"error": f"Rewrite failed: {str(e)[:100]}"}), 500

    # Log usage
    try:
        log_framework_usage(
            user_id=session["user_id"],
            framework_id=fw_id,
            user_framework_id=user_framework_id,
            action="rewrite",
        )
    except Exception:
        pass

    return jsonify(result)


@app.route("/ai-optimize-primary", methods=["POST"])
def ai_optimize_primary():
    """AI-powered email optimization for Gmail Primary tab (Pro+ only)."""
    if not session.get("user_id"):
        return jsonify({"error": "Please log in to use Primary optimizer.", "signup_url": "/signup"}), 429
    tier = session.get("user_tier", "free")
    if tier not in ("pro", "agency", "api"):
        return jsonify({"error": "Primary inbox optimizer is available on Pro and Agency plans.", "upgrade_url": "/account"}), 403

    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload"}), 400

    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()

    if not subject and not body:
        return jsonify({"error": "Subject or body is required."}), 400

    from modules.ai_rewriter import optimize_for_primary, is_available, AIRewriteError

    if not is_available():
        return jsonify({"error": "AI not available — set GROQ_API_KEY environment variable."}), 503

    try:
        result = optimize_for_primary(subject=subject, body=body)
    except AIRewriteError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.exception("Primary optimization failed")
        return jsonify({"error": f"Optimization failed: {str(e)[:100]}"}), 500

    return jsonify(result)


@app.route("/ai-rewrite/status", methods=["GET"])
def ai_rewrite_status():
    """Check if AI rewrite is available (requires Pro+ tier)."""
    from modules.ai_rewriter import is_available
    tier = session.get("user_tier", "free") if session.get("user_id") else "visitor"
    api_available = is_available()
    tier_ok = tier in ("pro", "agency", "api")
    return jsonify({
        "available": api_available and tier_ok,
        "reason": None if (api_available and tier_ok) else
                  "pro_required" if not tier_ok else "unavailable",
    })


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
        logger.exception("BIMI validation failed for %s", domain)
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
        logger.exception("MTA-STS lookup failed for %s", domain)
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
        logger.exception("TLS-RPT lookup failed for %s", domain)
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
                logger.exception("Non-fatal: reputation check failed for %s", domain)

    readability_result = analyze_readability(body=body, subject=subject)

    # Link & image validation (non-fatal)
    link_image_result = None
    if body:
        try:
            link_image_result = validate_links_and_images(body)
        except Exception:
            logger.exception("Non-fatal: link/image validation failed")

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
        logger.exception("Non-fatal: benchmarks calculation failed")

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
            logger.exception("Non-fatal: DNS suggestions failed for %s", domain)

        # BIMI validation (non-fatal)
        try:
            from modules.bimi_validator import validate_bimi
            bimi_result = validate_bimi(domain)
            result["bimi"] = bimi_result
        except Exception:
            logger.exception("Non-fatal: BIMI validation failed for %s", domain)

    # Pre-send audit checklist (aggregates all results)
    try:
        from modules.presend_audit import generate_audit
        result["audit"] = generate_audit(result)
    except Exception:
        logger.exception("Non-fatal: pre-send audit generation failed")

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
        logger.exception("Failed to read uploaded file")
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
        logger.exception("Failed to parse uploaded file")
        return jsonify({"error": f"Failed to parse file: {e}"}), 500


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_ENV") != "production",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
