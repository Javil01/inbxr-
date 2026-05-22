"""
InbXr — Auth Blueprint
Registration, login, logout, account management, password reset.
"""

import os
import re
import logging
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session

logger = logging.getLogger('inbxr.auth')

from modules.auth import (
    create_user, authenticate, login_user, logout_user,
    get_current_user, update_password, generate_api_key,
    verify_email_token, create_reset_token, reset_password_with_token,
)
from modules.tiers import get_all_tiers, get_tier
from modules.rate_limiter import get_usage_summary, burst_allow

auth_bp = Blueprint("auth", __name__)

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


def _client_ip():
    """Real client IP — assumes ProxyFix is wired so request.remote_addr is correct."""
    return request.remote_addr or "unknown"


def _auth_throttle(scope, key, limit, window_seconds):
    """Burst limiter for sensitive auth endpoints. Returns True if allowed."""
    return burst_allow(f"{scope}:{key}", limit, window_seconds)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("auth.account"))

    if request.method == "GET":
        prefill_email = (request.args.get("email") or "").strip()
        signup_source = (request.args.get("from") or "").strip().lower()
        return render_template(
            "auth/signup.html",
            error=None,
            active_page="signup",
            prefill_email=prefill_email,
            signup_source=signup_source,
        )

    # Throttle: 5 signups/hr per IP. Stops automated account creation
    # without inconveniencing humans (you only sign up once).
    if not _auth_throttle("signup_ip", _client_ip(), limit=5, window_seconds=3600):
        return render_template(
            "auth/signup.html",
            error="Too many signup attempts from this network. Please try again in an hour.",
            active_page="signup",
        ), 429

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""
    name = (request.form.get("display_name") or "").strip()

    # Validation
    if not email or not _EMAIL_RE.match(email):
        return render_template("auth/signup.html", error="Enter a valid email address.", active_page="signup")
    if len(password) < 8:
        return render_template("auth/signup.html", error="Password must be at least 8 characters.", active_page="signup")
    if password != confirm:
        return render_template("auth/signup.html", error="Passwords don't match.", active_page="signup")

    user = create_user(email, password, display_name=name)
    if not user:
        # Generic error to avoid signaling whether the email is already
        # registered. If it IS registered, send a helpful "you may already
        # have an account" email out-of-band so the legitimate owner can
        # log in or reset, while attackers learn nothing.
        try:
            from modules.mailer import send_admin_email, is_configured as _mailer_configured
            if _mailer_configured():
                send_admin_email(
                    email,
                    "Did you try to sign up for InbXr?",
                    """<p>Someone (maybe you) tried to create an InbXr account with this email address.</p>
                    <p>You already have an account here. If this was you, just <a href="https://inbxr.us/login">log in</a> or <a href="https://inbxr.us/forgot-password">reset your password</a>.</p>
                    <p>If it wasn't you, ignore this email.</p>""",
                )
        except Exception:
            logger.exception("anti-enumeration email failed for %s", email)
        return render_template(
            "auth/signup.html",
            error="We couldn't create that account. If you already have one, try logging in or resetting your password.",
            active_page="signup",
        )

    # Send verification email. If sending fails (Brevo down, network blip),
    # surface that to the user so they don't sit on /verification-required
    # forever waiting for an email that's never coming.
    from modules.mailer import send_verification_email, is_configured
    email_send_failed = False
    if is_configured() and user.get("verification_token"):
        try:
            sent = send_verification_email(email, user["verification_token"])
            if sent:
                logger.info("Verification email sent to %s", email)
            else:
                email_send_failed = True
                logger.error("send_verification_email returned falsy for %s", email)
        except Exception:
            email_send_failed = True
            logger.exception("send_verification_email raised for %s", email)
    elif not is_configured():
        logger.warning("SMTP not configured — verification email NOT sent for %s", email)

    # Don't fully log in until email is verified — redirect to verification page
    if is_configured() and user.get("verification_token"):
        session["pending_user_id"] = user["id"]
        session["pending_user_email"] = email
        session["is_new_signup"] = True
        # Stash the destination so we can honor it after verification (e.g.
        # AppSumo redeem flow, deep-linked CTAs). Production-path /verify-email
        # reads `_post_verify_redirect` once and clears it.
        next_param = request.args.get("next") or request.form.get("next")
        if next_param:
            safe = _safe_next(next_param)
            if safe and safe != "/dashboard":
                session["_post_verify_redirect"] = safe
        if email_send_failed:
            session["verification_send_failed"] = True
        return redirect("/verification-required")
    else:
        # No email configured — allow login (dev mode / email disabled)
        login_user(user)
        session["is_new_signup"] = True
        next_url = _safe_next(request.args.get("next") or request.form.get("next") or "/dashboard")
        return redirect(next_url)


def _safe_next(url):
    """Validate redirect URL to prevent open redirect."""
    if not url or not url.startswith("/") or url.startswith("//"):
        return "/dashboard"
    return url


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("auth.account"))

    if request.method == "GET":
        return render_template("auth/login.html", error=None, active_page="login")

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    # Two-axis throttle: per-IP and per-email. Either trips → 429.
    # Per-IP catches credential stuffing across many accounts.
    # Per-email catches password brute-force on a known target.
    ip = _client_ip()
    if not _auth_throttle("login_ip", ip, limit=20, window_seconds=900):
        return render_template(
            "auth/login.html",
            error="Too many login attempts from this network. Please try again in 15 minutes.",
            active_page="login",
        ), 429
    if email and not _auth_throttle("login_email", email, limit=10, window_seconds=900):
        return render_template(
            "auth/login.html",
            error="Too many login attempts for this account. Please try again in 15 minutes.",
            active_page="login",
        ), 429

    user = authenticate(email, password)
    if not user:
        return render_template("auth/login.html", error="Invalid email or password.", active_page="login")

    login_user(user)
    next_url = _safe_next(request.args.get("next") or request.form.get("next") or "/dashboard")
    return redirect(next_url)


@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect("/")


@auth_bp.route("/account")
def account():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    usage = get_usage_summary(user["id"])
    tier = get_tier(user["tier"])
    tiers = get_all_tiers()

    return render_template(
        "auth/account.html",
        user=user,
        usage=usage,
        tier=tier,
        tiers=tiers,
        active_page="account",
    )


@auth_bp.route("/account/change-password", methods=["POST"])
def change_password():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401

    # Throttle current-password attempts per user. An attacker with a hijacked
    # session can't brute-force the current password to chain into other tools.
    if not _auth_throttle("change_pw_user", str(user["id"]), limit=5, window_seconds=900):
        return jsonify({"error": "Too many attempts. Please try again in 15 minutes."}), 429

    data = request.get_json(force=True, silent=True) or {}
    current = data.get("current_password", "")
    new_pass = data.get("new_password", "")

    if len(new_pass) < 8:
        return jsonify({"error": "New password must be at least 8 characters."}), 400

    check = authenticate(user["email"], current)
    if not check:
        return jsonify({"error": "Current password is incorrect."}), 400

    update_password(user["id"], new_pass)
    return jsonify({"ok": True})


@auth_bp.route("/account/delete", methods=["POST"])
def delete_account():
    """Permanently delete the user's account and all associated data."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401

    data = request.get_json(force=True, silent=True) or {}
    if data.get("confirm") != "DELETE":
        return jsonify({"error": "Please confirm deletion by typing DELETE."}), 400

    user_id = user["id"]

    # Cancel Stripe subscription if active
    if user.get("stripe_subscription_id"):
        try:
            import stripe
            stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
            if stripe.api_key:
                stripe.Subscription.cancel(user["stripe_subscription_id"])
        except Exception:
            pass  # best effort — don't block deletion

    # Delete all user data (foreign keys with ON DELETE CASCADE handle most)
    from modules.database import execute as db_exec
    db_exec("DELETE FROM user_framework_favorites WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM user_frameworks WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM framework_usage WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM check_history WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM usage_log WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM alerts WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM alert_preferences WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM user_monitors WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM bulk_jobs WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM admin_notes WHERE user_id = ?", (user_id,))
    db_exec("DELETE FROM users WHERE id = ?", (user_id,))

    # Clear session
    session.clear()

    return jsonify({"ok": True})


@auth_bp.route("/account/api-key", methods=["POST"])
def regenerate_api_key():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401
    if user["tier"] not in ("agency", "api"):
        return jsonify({"error": "API keys require Agency or API tier."}), 403

    key = generate_api_key(user["id"])
    return jsonify({"ok": True, "api_key": key})


# ── Agency white-label settings for Signal Report PDFs ──
#
# Agency tier users can upload a logo, pick a primary color, write a
# custom footer, and optionally hide all InbXr branding. These values
# are read by modules/signal_report_pdf.py when rendering the agency
# variant of the Signal Report PDF. GET renders the form, POST saves.

# SVG omitted on purpose — SVG can carry inline <script> and is served from the
# same origin as user sessions, which would let a malicious agency upload a
# stored XSS. PNG / JPG / WEBP are bitmap formats and cannot execute.
_ALLOWED_LOGO_EXT = {"png", "jpg", "jpeg", "webp"}
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _agency_logo_dir():
    """Where agency logos land. Served from static/ so they're reachable."""
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    path = os.path.join(base, "uploads", "agency")
    os.makedirs(path, exist_ok=True)
    return path


@auth_bp.route("/account/agency", methods=["GET"])
def agency_settings():
    """Render the agency white-label settings form. Gated to agency tier."""
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))
    if user["tier"] != "agency":
        # Not an error — show an upsell message instead
        return render_template(
            "auth/agency_settings.html",
            user=user,
            locked=True,
            active_page="account",
        )

    from modules.database import fetchone as _fetchone
    row = _fetchone(
        "SELECT agency_logo_url, agency_primary_color, agency_footer_text, "
        "agency_hide_inbxr_brand FROM users WHERE id = ?",
        (user["id"],),
    )
    return render_template(
        "auth/agency_settings.html",
        user=user,
        locked=False,
        agency_logo_url=row.get("agency_logo_url") if row else None,
        agency_primary_color=(row.get("agency_primary_color") if row else None) or "#2563eb",
        agency_footer_text=row.get("agency_footer_text") if row else "",
        agency_hide_inbxr_brand=bool(row.get("agency_hide_inbxr_brand") if row else 0),
        active_page="account",
    )


@auth_bp.route("/account/agency", methods=["POST"])
def agency_settings_save():
    """Save white-label settings. Accepts multipart/form-data for the
    logo upload, or plain form data for color/footer/hide fields."""
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "error": "Not authenticated."}), 401
    if user["tier"] != "agency":
        return jsonify({"ok": False, "error": "Agency tier required."}), 403

    primary_color = (request.form.get("primary_color") or "#2563eb").strip()
    footer_text = (request.form.get("footer_text") or "").strip()[:200]
    hide_brand = 1 if request.form.get("hide_inbxr_brand") in ("on", "1", "true") else 0

    if not _HEX_COLOR_RE.match(primary_color):
        return jsonify({"ok": False, "error": "Primary color must be a 6-digit hex like #2563eb."}), 400

    # Handle optional logo upload
    logo_url = None
    logo_file = request.files.get("logo") if request.files else None
    if logo_file and logo_file.filename:
        fname = logo_file.filename.lower()
        ext = fname.rsplit(".", 1)[-1] if "." in fname else ""
        if ext not in _ALLOWED_LOGO_EXT:
            return jsonify({
                "ok": False,
                "error": f"Logo must be one of: {', '.join(sorted(_ALLOWED_LOGO_EXT))}",
            }), 400

        # Size check (read into memory since we also need to write it)
        data = logo_file.read()
        if len(data) > _MAX_LOGO_BYTES:
            return jsonify({
                "ok": False,
                "error": f"Logo must be smaller than {_MAX_LOGO_BYTES // 1024 // 1024} MB.",
            }), 400

        save_dir = _agency_logo_dir()
        safe_name = f"{user['id']}.{ext}"
        full_path = os.path.join(save_dir, safe_name)
        try:
            with open(full_path, "wb") as f:
                f.write(data)
        except Exception:
            logger.exception("[AGENCY] Failed to save uploaded logo")
            return jsonify({"ok": False, "error": "Could not save logo upload."}), 500

        logo_url = f"/static/uploads/agency/{safe_name}"

    # Update the user row
    from modules.database import execute as _execute
    if logo_url:
        _execute(
            "UPDATE users SET agency_logo_url = ?, agency_primary_color = ?, "
            "agency_footer_text = ?, agency_hide_inbxr_brand = ? WHERE id = ?",
            (logo_url, primary_color, footer_text, hide_brand, user["id"]),
        )
    else:
        _execute(
            "UPDATE users SET agency_primary_color = ?, agency_footer_text = ?, "
            "agency_hide_inbxr_brand = ? WHERE id = ?",
            (primary_color, footer_text, hide_brand, user["id"]),
        )

    return jsonify({"ok": True, "logo_url": logo_url})


@auth_bp.route("/resend-verification", methods=["POST"])
def resend_verification():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))
    if user.get("email_verified"):
        return redirect(url_for("auth.account"))

    # Generate a new token if needed
    from modules.database import execute, fetchone
    if not user.get("verification_token"):
        import secrets
        token = secrets.token_urlsafe(32)
        execute("UPDATE users SET verification_token = ? WHERE id = ?", (token, user["id"]))
    else:
        token = user["verification_token"]

    from modules.mailer import send_verification_email, is_configured
    if is_configured():
        send_verification_email(user["email"], token)

    # If user is unverified, redirect to verification-required page (not account)
    if not user.get("email_verified"):
        return redirect("/verification-required?resent=1")
    return redirect(url_for("auth.account") + "?resent=1")


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    verified_user = verify_email_token(token)
    if not verified_user:
        return render_template("auth/email_verified.html", error="Invalid or expired link.", active_page="")

    # Auto-login the freshly-verified user (clears pending_* keys via
    # session.clear inside login_user) and honor any deep-link destination
    # they were headed to before verification interrupted them.
    login_user(verified_user)

    from modules.mailer import send_welcome_email, is_configured
    if is_configured():
        send_welcome_email(verified_user["email"], verified_user.get("display_name"))

    next_url = session.pop("_post_verify_redirect", None) or session.pop("_post_signup_redirect", None)
    return render_template(
        "auth/email_verified.html",
        active_page="",
        next_url=next_url or "/dashboard",
    )


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("auth/forgot_password.html", error=None, success=False, active_page="")

    email = (request.form.get("email") or "").strip().lower()
    logger.info("Password reset requested for: %s", email)

    # Throttle by IP and by email. Stops mail-bombing a target inbox and
    # rate-limits enumeration probing.
    ip = _client_ip()
    if not _auth_throttle("forgot_ip", ip, limit=10, window_seconds=3600):
        # Still render success to avoid telling the attacker we're throttling
        return render_template("auth/forgot_password.html", error=None, success=True, active_page="")
    if email and not _auth_throttle("forgot_email", email, limit=3, window_seconds=3600):
        return render_template("auth/forgot_password.html", error=None, success=True, active_page="")

    # Always show success to prevent email enumeration
    token = create_reset_token(email)
    if token:
        from modules.mailer import send_password_reset_email, is_configured
        if is_configured():
            result = send_password_reset_email(email, token)
            logger.info("Password reset email sent to %s: %s", email, result)
        else:
            logger.warning("SMTP not configured — password reset email NOT sent for %s", email)
    else:
        logger.info("No user found for %s (no email sent)", email)
    return render_template("auth/forgot_password.html", error=None, success=True, active_page="")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if request.method == "GET":
        return render_template("auth/reset_password.html", token=token, error=None, active_page="")

    new_pass = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if len(new_pass) < 8:
        return render_template("auth/reset_password.html", token=token, error="Password must be at least 8 characters.", active_page="")
    if new_pass != confirm:
        return render_template("auth/reset_password.html", token=token, error="Passwords don't match.", active_page="")

    success = reset_password_with_token(token, new_pass)
    if not success:
        return render_template("auth/reset_password.html", token=token, error="Invalid or expired reset link.", active_page="")

    return redirect(url_for("auth.login") + "?reset=1")


@auth_bp.route("/pricing")
def pricing():
    tiers = get_all_tiers()
    user = get_current_user()
    return render_template(
        "auth/pricing.html",
        tiers=tiers,
        user=user,
        active_page="pricing",
        page_title="Pricing · InbXr",
        page_description="Simple, transparent pricing for email deliverability tools. Start free, upgrade when you need more.",
        canonical_url="https://inbxr.us/pricing",
    )
