"""
INBXR — Critical Path Test Suite
Covers auth, admin, database, mailer, and admin API endpoints.
Run with: pytest tests/test_critical.py -v
"""

import os
import sys
import time
import tempfile

import pytest

# ── Ensure project root is importable ────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Set env vars BEFORE importing anything from the app ──
os.environ["ADMIN_USER"] = "testadmin"
os.environ["ADMIN_PASS"] = "testpass123"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ["FLASK_ENV"] = "development"

# Point database at a temp file so we never touch real data
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["INBXR_DATA_DIR"] = os.path.dirname(_tmp_db.name)
# Override the DB filename by rewriting the module-level _DB_PATH
# We do this before importing database so the module picks up our dir.
# The filename inside INBXR_DATA_DIR is always "inbxr.db", so we
# create a temp *directory* instead:
_tmp_dir = tempfile.mkdtemp(prefix="inbxr_test_")
os.environ["INBXR_DATA_DIR"] = _tmp_dir

# Clear SMTP vars so mailer reports unconfigured
for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"):
    os.environ.pop(key, None)


# ── Fixtures ─────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """Create the Flask app with a temporary database."""
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key-for-pytest"

    yield flask_app


@pytest.fixture()
def client(app):
    """Flask test client — fresh per test."""
    with app.test_client() as c:
        yield c


@pytest.fixture()
def admin_session(client):
    """Return a client that is already logged in as admin."""
    client.post("/admin/login", data={
        "username": "testadmin",
        "password": "testpass123",
    })
    return client


# ═══════════════════════════════════════════════════════════
# 1. AUTH & SESSIONS
# ═══════════════════════════════════════════════════════════

class TestAuth:
    """User registration, login, session management."""

    def test_create_user(self, app):
        """create_user returns a user dict with expected fields."""
        from modules.auth import create_user
        with app.app_context():
            user = create_user("alice@example.com", "StrongP@ss1")
            assert user is not None
            assert user["email"] == "alice@example.com"
            assert user["tier"] == "free"
            assert "password_hash" in user

    def test_create_user_duplicate_rejected(self, app):
        """Duplicate email returns None."""
        from modules.auth import create_user
        with app.app_context():
            create_user("dup@example.com", "Pass1234")
            dup = create_user("dup@example.com", "Pass1234")
            assert dup is None

    def test_authenticate_correct_password(self, app):
        """authenticate() returns user dict for correct credentials."""
        from modules.auth import create_user, authenticate
        with app.app_context():
            create_user("bob@example.com", "BobPass99")
            user = authenticate("bob@example.com", "BobPass99")
            assert user is not None
            assert user["email"] == "bob@example.com"

    def test_authenticate_wrong_password(self, app):
        """authenticate() returns None for wrong password."""
        from modules.auth import create_user, authenticate
        with app.app_context():
            create_user("carol@example.com", "CorrectPass")
            assert authenticate("carol@example.com", "WrongPass") is None

    def test_authenticate_nonexistent_user(self, app):
        """authenticate() returns None for unknown email."""
        from modules.auth import authenticate
        with app.app_context():
            assert authenticate("nobody@example.com", "whatever") is None

    def test_suspended_user_cannot_login(self, app):
        """authenticate() returns None for suspended users."""
        from modules.auth import create_user, authenticate
        from modules.database import execute
        with app.app_context():
            user = create_user("suspended@example.com", "SusPass1")
            execute(
                "UPDATE users SET status = 'suspended' WHERE id = ?",
                (user["id"],),
            )
            assert authenticate("suspended@example.com", "SusPass1") is None

    def test_login_user_sets_session(self, app):
        """login_user populates session keys."""
        from modules.auth import create_user, login_user
        with app.test_request_context():
            from flask import session
            with app.app_context():
                user = create_user("sess@example.com", "SessPass1")
                login_user(user)
                assert session.get("user_id") == user["id"]
                assert session.get("user_email") == user["email"]
                assert session.get("user_tier") == "free"

    def test_logout_user_clears_session(self, app):
        """logout_user removes all user keys from session."""
        from modules.auth import create_user, login_user, logout_user
        with app.test_request_context():
            from flask import session
            with app.app_context():
                user = create_user("logout@example.com", "LogPass1")
                login_user(user)
                assert session.get("user_id") is not None
                logout_user()
                assert session.get("user_id") is None
                assert session.get("user_email") is None
                assert session.get("user_tier") is None


# ═══════════════════════════════════════════════════════════
# 2. ADMIN AUTH
# ═══════════════════════════════════════════════════════════

class TestAdminAuth:
    """Admin login, session expiry, route protection."""

    def test_admin_login_correct_credentials(self, client):
        """POST /admin/login with correct creds sets admin session."""
        resp = client.post("/admin/login", data={
            "username": "testadmin",
            "password": "testpass123",
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin" in resp.headers.get("Location", "")

    def test_admin_login_wrong_password(self, client):
        """POST /admin/login with wrong password shows error."""
        resp = client.post("/admin/login", data={
            "username": "testadmin",
            "password": "wrongpassword",
        })
        assert resp.status_code == 200
        assert b"Invalid" in resp.data

    def test_admin_login_wrong_username(self, client):
        """POST /admin/login with wrong username shows error."""
        resp = client.post("/admin/login", data={
            "username": "notadmin",
            "password": "testpass123",
        })
        assert resp.status_code == 200
        assert b"Invalid" in resp.data

    def test_admin_session_expiry(self, app, client):
        """Admin session older than 4 hours is rejected."""
        # Log in first
        client.post("/admin/login", data={
            "username": "testadmin",
            "password": "testpass123",
        })
        # Tamper with the login timestamp to simulate expiry
        with client.session_transaction() as sess:
            sess["admin_login_at"] = time.time() - (5 * 3600)  # 5 hours ago

        # Now admin API should reject us
        resp = client.get("/admin/api/users")
        assert resp.status_code == 403

    def test_admin_routes_require_auth(self, client):
        """Admin API routes return 403 without admin session."""
        resp = client.get("/admin/api/users")
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════
# 3. CRITICAL ADMIN API ENDPOINTS
# ═══════════════════════════════════════════════════════════

class TestAdminAPI:
    """Admin-only API endpoints are properly gated."""

    def test_get_users_returns_403_without_admin(self, client):
        """GET /admin/api/users returns 403 for non-admin."""
        resp = client.get("/admin/api/users")
        assert resp.status_code == 403
        data = resp.get_json()
        assert "error" in data

    def test_get_users_succeeds_for_admin(self, admin_session):
        """GET /admin/api/users returns user list for admin."""
        resp = admin_session.get("/admin/api/users")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "users" in data
        assert "summary" in data

    def test_tier_change_requires_admin(self, client, app):
        """POST tier change returns 403 without admin session."""
        resp = client.post(
            "/admin/api/users/1/tier",
            json={"tier": "pro"},
        )
        assert resp.status_code == 403

    def test_tier_change_works_for_admin(self, admin_session, app):
        """Admin can change a user's tier."""
        from modules.auth import create_user
        with app.app_context():
            user = create_user("tiertest@example.com", "TierPass1")
            user_id = user["id"]

        resp = admin_session.post(
            f"/admin/api/users/{user_id}/tier",
            json={"tier": "pro"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["tier"] == "pro"

    def test_tier_change_invalid_tier(self, admin_session, app):
        """Invalid tier value returns 400."""
        from modules.auth import create_user
        with app.app_context():
            user = create_user("badtier@example.com", "TierPass1")
            user_id = user["id"]

        resp = admin_session.post(
            f"/admin/api/users/{user_id}/tier",
            json={"tier": "platinum"},
        )
        assert resp.status_code == 400

    def test_suspend_requires_admin(self, client):
        """POST suspend returns 403 without admin session."""
        resp = client.post("/admin/api/users/1/suspend")
        assert resp.status_code == 403

    def test_reactivate_requires_admin(self, client):
        """POST reactivate returns 403 without admin session."""
        resp = client.post("/admin/api/users/1/reactivate")
        assert resp.status_code == 403

    def test_suspend_and_reactivate_flow(self, admin_session, app):
        """Admin can suspend and reactivate a user."""
        from modules.auth import create_user
        with app.app_context():
            user = create_user("suspendme@example.com", "SusPass1")
            user_id = user["id"]

        # Suspend
        resp = admin_session.post(f"/admin/api/users/{user_id}/suspend")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "suspended"

        # Reactivate
        resp = admin_session.post(f"/admin/api/users/{user_id}/reactivate")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "active"


# ═══════════════════════════════════════════════════════════
# 4. DATABASE
# ═══════════════════════════════════════════════════════════

class TestDatabase:
    """Database init, migrations, and basic CRUD."""

    def test_init_db_creates_tables(self, app):
        """init_db runs without error and creates expected tables."""
        from modules.database import init_db, fetchall
        with app.app_context():
            init_db()  # should be idempotent
            tables = fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            table_names = {t["name"] for t in tables}
            assert "users" in table_names
            assert "usage_log" in table_names
            assert "check_history" in table_names
            assert "teams" in table_names
            assert "team_members" in table_names

    def test_migrations_run_without_error(self, app):
        """Re-running init_db (which runs migrations) is safe."""
        from modules.database import init_db
        with app.app_context():
            # Call twice — should not raise
            init_db()
            init_db()

    def test_migrations_create_expected_tables(self, app):
        """Migrations create the team_invites and admin_notes tables."""
        from modules.database import fetchall
        with app.app_context():
            tables = fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            table_names = {t["name"] for t in tables}
            assert "team_invites" in table_names
            assert "admin_notes" in table_names
            assert "admin_audit_log" in table_names

    def test_insert_fetch_update_user(self, app):
        """Basic CRUD: insert a user, fetch, update tier, verify."""
        from modules.database import execute, fetchone
        with app.app_context():
            execute(
                "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
                ("crud@example.com", "fakehash", "CRUD Test"),
            )
            user = fetchone("SELECT * FROM users WHERE email = ?", ("crud@example.com",))
            assert user is not None
            assert user["display_name"] == "CRUD Test"
            assert user["tier"] == "free"

            execute(
                "UPDATE users SET tier = 'pro' WHERE id = ?",
                (user["id"],),
            )
            updated = fetchone("SELECT tier FROM users WHERE id = ?", (user["id"],))
            assert updated["tier"] == "pro"

    def test_fetchone_returns_none_for_missing(self, app):
        """fetchone returns None when no rows match."""
        from modules.database import fetchone
        with app.app_context():
            result = fetchone("SELECT * FROM users WHERE email = ?", ("nonexistent@x.com",))
            assert result is None


# ═══════════════════════════════════════════════════════════
# 5. MAILER
# ═══════════════════════════════════════════════════════════

class TestMailer:
    """Mailer safety — no crashes when SMTP is unconfigured."""

    def test_is_configured_false_when_smtp_not_set(self):
        """is_configured() returns False when SMTP env vars are empty."""
        from modules.mailer import is_configured
        assert is_configured() is False

    def test_send_admin_email_returns_false_when_not_configured(self):
        """send_admin_email gracefully returns False (no crash)."""
        from modules.mailer import send_admin_email
        result = send_admin_email("test@example.com", "Test", "<p>Test</p>")
        assert result is False

    def test_send_verification_email_returns_false_when_not_configured(self):
        """send_verification_email gracefully returns False."""
        from modules.mailer import send_verification_email
        result = send_verification_email("test@example.com", "faketoken123")
        assert result is False

    def test_send_password_reset_returns_false_when_not_configured(self):
        """send_password_reset_email gracefully returns False."""
        from modules.mailer import send_password_reset_email
        result = send_password_reset_email("test@example.com", "faketoken123")
        assert result is False


# ═══════════════════════════════════════════════════════════
# 6. PASSWORD HASHING
# ═══════════════════════════════════════════════════════════

class TestPasswordHashing:
    """Verify the hash/verify cycle works correctly."""

    def test_hash_and_verify_roundtrip(self):
        """Hashed password verifies correctly."""
        from modules.auth import _hash_password, _verify_password
        pw = "MySecret!42"
        hashed = _hash_password(pw)
        assert _verify_password(hashed, pw) is True

    def test_wrong_password_fails_verification(self):
        """Wrong password does not verify."""
        from modules.auth import _hash_password, _verify_password
        hashed = _hash_password("RightPassword")
        assert _verify_password(hashed, "WrongPassword") is False

    def test_verify_handles_malformed_hash(self):
        """Malformed hash returns False instead of crashing."""
        from modules.auth import _verify_password
        assert _verify_password("not-a-valid-hash", "password") is False
        assert _verify_password("", "password") is False
        assert _verify_password(None, "password") is False


# ═══════════════════════════════════════════════════════════
# 7. PASSWORD RESET FLOW
# ═══════════════════════════════════════════════════════════

class TestPasswordReset:
    """Password reset token generation and redemption."""

    def test_create_and_use_reset_token(self, app):
        """Full reset flow: create token, reset password, login with new."""
        from modules.auth import create_user, create_reset_token, reset_password_with_token, authenticate
        with app.app_context():
            create_user("reset@example.com", "OldPassword1")
            token = create_reset_token("reset@example.com")
            assert token is not None

            success = reset_password_with_token(token, "NewPassword2")
            assert success is True

            # Old password should fail
            assert authenticate("reset@example.com", "OldPassword1") is None
            # New password should work
            assert authenticate("reset@example.com", "NewPassword2") is not None

    def test_reset_token_for_nonexistent_user(self, app):
        """create_reset_token returns None for unknown email."""
        from modules.auth import create_reset_token
        with app.app_context():
            assert create_reset_token("ghost@example.com") is None

    def test_invalid_reset_token(self, app):
        """reset_password_with_token returns False for bogus token."""
        from modules.auth import reset_password_with_token
        with app.app_context():
            assert reset_password_with_token("bogus-token", "NewPass") is False
