"""
INBXR — User Authentication
Registration, login, password hashing, session management, decorators.
"""

import os
import hashlib
import secrets
import functools
from datetime import datetime, timedelta, timezone

from flask import session, request, redirect, url_for, jsonify, g

from modules.database import execute, fetchone, fetchall


# ── Password Hashing (uses hashlib — no extra deps) ─────

def _hash_password(password):
    """Hash password with PBKDF2-SHA256 + random salt."""
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)
    return salt.hex() + ":" + key.hex()


def _verify_password(stored_hash, password):
    """Verify password against stored hash."""
    try:
        salt_hex, key_hex = stored_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        actual_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)
        return secrets.compare_digest(expected_key, actual_key)
    except (ValueError, AttributeError):
        return False


# ── User CRUD ────────────────────────────────────────────

def create_user(email, password, display_name=""):
    """Create a new user. Returns user dict or None if email taken."""
    email = email.strip().lower()
    existing = fetchone("SELECT id FROM users WHERE email = ?", (email,))
    if existing:
        return None

    password_hash = _hash_password(password)
    verification_token = secrets.token_urlsafe(32)

    execute(
        """INSERT INTO users (email, password_hash, display_name, verification_token)
           VALUES (?, ?, ?, ?)""",
        (email, password_hash, display_name.strip(), verification_token),
    )
    return get_user_by_email(email)


def get_user_by_id(user_id):
    """Fetch user by ID."""
    return fetchone("SELECT * FROM users WHERE id = ?", (user_id,))


def get_user_by_email(email):
    """Fetch user by email."""
    return fetchone("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))


def get_user_by_api_key(api_key):
    """Fetch user by API key."""
    if not api_key:
        return None
    return fetchone("SELECT * FROM users WHERE api_key = ?", (api_key,))


def authenticate(email, password):
    """Check email + password. Returns user dict or None."""
    user = get_user_by_email(email)
    if not user:
        return None
    if _verify_password(user["password_hash"], password):
        return user
    return None


def update_password(user_id, new_password):
    """Update a user's password."""
    password_hash = _hash_password(new_password)
    execute(
        "UPDATE users SET password_hash = ?, updated_at = datetime('now') WHERE id = ?",
        (password_hash, user_id),
    )


def generate_api_key(user_id):
    """Generate and store a new API key for a user."""
    api_key = "inbxr_" + secrets.token_hex(24)
    execute(
        "UPDATE users SET api_key = ?, updated_at = datetime('now') WHERE id = ?",
        (api_key, user_id),
    )
    return api_key


def update_user_tier(user_id, tier, stripe_customer_id=None, stripe_subscription_id=None):
    """Update user tier and optional Stripe IDs."""
    params = [tier]
    sql_parts = ["tier = ?"]

    if stripe_customer_id is not None:
        sql_parts.append("stripe_customer_id = ?")
        params.append(stripe_customer_id)
    if stripe_subscription_id is not None:
        sql_parts.append("stripe_subscription_id = ?")
        params.append(stripe_subscription_id)

    sql_parts.append("updated_at = datetime('now')")
    params.append(user_id)

    execute(f"UPDATE users SET {', '.join(sql_parts)} WHERE id = ?", params)


def verify_email_token(token):
    """Verify a user's email by token. Returns True if successful."""
    user = fetchone("SELECT id FROM users WHERE verification_token = ?", (token,))
    if not user:
        return False
    execute(
        "UPDATE users SET email_verified = 1, verification_token = NULL, updated_at = datetime('now') WHERE id = ?",
        (user["id"],),
    )
    return True


def create_reset_token(email):
    """Generate a password reset token. Returns token or None if user not found."""
    user = get_user_by_email(email)
    if not user:
        return None
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    execute(
        "UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?",
        (token, expires, user["id"]),
    )
    return token


def reset_password_with_token(token, new_password):
    """Reset password using a reset token. Returns True if successful."""
    user = fetchone(
        "SELECT id, reset_token_expires FROM users WHERE reset_token = ?", (token,)
    )
    if not user:
        return False
    if user["reset_token_expires"]:
        expires = datetime.fromisoformat(user["reset_token_expires"])
        if datetime.now(timezone.utc) > expires:
            return False
    update_password(user["id"], new_password)
    execute(
        "UPDATE users SET reset_token = NULL, reset_token_expires = NULL WHERE id = ?",
        (user["id"],),
    )
    return True


# ── Session Management ───────────────────────────────────

def login_user(user):
    """Set session for logged-in user."""
    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    session["user_tier"] = user["tier"]
    session["user_name"] = user["display_name"] or user["email"].split("@")[0]
    session.permanent = True


def logout_user():
    """Clear user session."""
    session.pop("user_id", None)
    session.pop("user_email", None)
    session.pop("user_tier", None)
    session.pop("user_name", None)


def get_current_user():
    """Get current user from session. Returns user dict or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    if not hasattr(g, "_current_user"):
        g._current_user = get_user_by_id(user_id)
        # Sync session tier with DB (in case of upgrade/downgrade)
        if g._current_user and g._current_user["tier"] != session.get("user_tier"):
            session["user_tier"] = g._current_user["tier"]
    return g._current_user


def current_user_tier():
    """Get current user's tier name. Returns 'free' for anonymous."""
    return session.get("user_tier", "free")


# ── Decorators ───────────────────────────────────────────

def login_required(f):
    """Decorator: redirect to login if not authenticated."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def tier_required(*allowed_tiers):
    """Decorator: require user to be on one of the specified tiers."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({"error": "Authentication required."}), 401
                return redirect(url_for("auth.login", next=request.path))
            if user["tier"] not in allowed_tiers:
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({
                        "error": "This feature requires a higher plan.",
                        "current_tier": user["tier"],
                        "required_tiers": list(allowed_tiers),
                    }), 403
                return redirect(url_for("auth.account") + "?upgrade=1")
            return f(*args, **kwargs)
        return wrapper
    return decorator


def api_key_required(f):
    """Decorator: authenticate via API key in header or query param."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not api_key:
            return jsonify({"error": "API key required. Pass via X-API-Key header."}), 401
        user = get_user_by_api_key(api_key)
        if not user:
            return jsonify({"error": "Invalid API key."}), 401
        if user["tier"] not in ("agency", "api"):
            return jsonify({"error": "API access requires Agency or API tier."}), 403
        g._current_user = user
        g._api_user = user
        return f(*args, **kwargs)
    return wrapper
