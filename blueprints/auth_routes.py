"""
INBXR — Auth Blueprint
Registration, login, logout, account management, password reset.
"""

import re
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session

from modules.auth import (
    create_user, authenticate, login_user, logout_user,
    get_current_user, update_password, generate_api_key,
    verify_email_token, create_reset_token, reset_password_with_token,
)
from modules.tiers import get_all_tiers, get_tier
from modules.rate_limiter import get_usage_summary

auth_bp = Blueprint("auth", __name__)

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("auth.account"))

    if request.method == "GET":
        return render_template("auth/signup.html", error=None, active_page="signup")

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
        return render_template("auth/signup.html", error="An account with that email already exists.", active_page="signup")

    # Send verification email
    from modules.mailer import send_verification_email, is_configured
    if is_configured() and user.get("verification_token"):
        send_verification_email(email, user["verification_token"])

    login_user(user)
    next_url = request.args.get("next", "/dashboard")
    return redirect(next_url)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("auth.account"))

    if request.method == "GET":
        return render_template("auth/login.html", error=None, active_page="login")

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""

    user = authenticate(email, password)
    if not user:
        return render_template("auth/login.html", error="Invalid email or password.", active_page="login")

    login_user(user)
    next_url = request.args.get("next") or request.form.get("next") or "/dashboard"
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


@auth_bp.route("/account/api-key", methods=["POST"])
def regenerate_api_key():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401
    if user["tier"] not in ("agency", "api"):
        return jsonify({"error": "API keys require Agency or API tier."}), 403

    key = generate_api_key(user["id"])
    return jsonify({"ok": True, "api_key": key})


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

    return redirect(url_for("auth.account") + "?resent=1")


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    success = verify_email_token(token)
    if success:
        # Send welcome email
        from modules.mailer import send_welcome_email, is_configured
        if is_configured():
            user = get_current_user()
            if user:
                send_welcome_email(user["email"], user.get("display_name"))
        return render_template("auth/email_verified.html", active_page="")
    return render_template("auth/email_verified.html", error="Invalid or expired link.", active_page="")


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("auth/forgot_password.html", error=None, success=False, active_page="")

    email = (request.form.get("email") or "").strip()
    # Always show success to prevent email enumeration
    token = create_reset_token(email)
    if token:
        from modules.mailer import send_password_reset_email, is_configured
        if is_configured():
            send_password_reset_email(email, token)
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
    )
