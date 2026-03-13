"""
INBXR — Centralized Database Manager
SQLite with WAL mode. Handles schema creation and migrations.
"""

import os
import sqlite3
import threading

_DEFAULT_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_DIR = os.environ.get("INBXR_DATA_DIR", _DEFAULT_DB_DIR)
_DB_PATH = os.path.join(_DB_DIR, "inbxr.db")
_local = threading.local()


def _get_conn():
    """Get a thread-local SQLite connection with WAL mode."""
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(_DB_DIR, exist_ok=True)
        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return _local.conn


def execute(sql, params=(), commit=True):
    """Execute a single SQL statement. Returns cursor."""
    conn = _get_conn()
    cur = conn.execute(sql, params)
    if commit:
        conn.commit()
    return cur


def fetchone(sql, params=()):
    """Execute and fetch one row as dict (or None)."""
    cur = execute(sql, params, commit=False)
    row = cur.fetchone()
    return dict(row) if row else None


def fetchall(sql, params=()):
    """Execute and fetch all rows as list of dicts."""
    cur = execute(sql, params, commit=False)
    return [dict(r) for r in cur.fetchall()]


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    conn = _get_conn()
    conn.executescript(_SCHEMA)
    conn.commit()
    _run_migrations(conn)


def _run_migrations(conn):
    """Run any pending schema migrations."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    applied = {r["name"] for r in fetchall("SELECT name FROM _migrations")}

    for name, sql in _MIGRATIONS:
        if name not in applied:
            conn.executescript(sql)
            conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
            conn.commit()


# ── Schema ──────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    tier TEXT DEFAULT 'free' CHECK(tier IN ('free', 'pro', 'agency', 'api')),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    api_key TEXT UNIQUE,
    email_verified INTEGER DEFAULT 0,
    verification_token TEXT,
    reset_token TEXT,
    reset_token_expires TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users(stripe_customer_id);

CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    ip_address TEXT,
    action TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_log_user_action ON usage_log(user_id, action, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_log_ip_action ON usage_log(ip_address, action, created_at);

CREATE TABLE IF NOT EXISTS check_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tool TEXT NOT NULL,
    input_summary TEXT,
    result_json TEXT,
    grade TEXT,
    score INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_check_history_user_tool ON check_history(user_id, tool, created_at);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT DEFAULT 'member' CHECK(role IN ('owner', 'admin', 'member')),
    joined_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(team_id, user_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS bulk_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    filename TEXT,
    total_emails INTEGER DEFAULT 0,
    processed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
    summary_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bulk_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    verdict TEXT,
    score INTEGER,
    result_json TEXT,
    FOREIGN KEY (job_id) REFERENCES bulk_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bulk_jobs_user ON bulk_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_bulk_results_job ON bulk_results(job_id);

CREATE TABLE IF NOT EXISTS user_monitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    ip TEXT,
    scan_interval_hours INTEGER DEFAULT 6,
    last_scanned_at TEXT,
    last_listed_count INTEGER DEFAULT 0,
    alert_on_change INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_user_monitors_user ON user_monitors(user_id);

CREATE TABLE IF NOT EXISTS monitor_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id INTEGER NOT NULL,
    total_lists INTEGER DEFAULT 0,
    listed_count INTEGER DEFAULT 0,
    listed_on TEXT,
    clean INTEGER DEFAULT 1,
    scanned_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (monitor_id) REFERENCES user_monitors(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_monitor_scans_monitor ON monitor_scans(monitor_id, scanned_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    alert_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    data_json TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id, is_read, created_at DESC);
"""

# ── Migrations (append-only list) ───────────────────────

_MIGRATIONS = [
    ("001_team_invites", """
        CREATE TABLE IF NOT EXISTS team_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE,
            role TEXT DEFAULT 'member' CHECK(role IN ('admin', 'member')),
            token TEXT UNIQUE NOT NULL,
            invited_by INTEGER NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'declined', 'expired')),
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT DEFAULT (datetime('now', '+7 days')),
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (invited_by) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_team_invites_token ON team_invites(token);
        CREATE INDEX IF NOT EXISTS idx_team_invites_email ON team_invites(email);
    """),
    ("002_team_id_on_shared_tables", """
        ALTER TABLE check_history ADD COLUMN team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL;
        ALTER TABLE user_monitors ADD COLUMN team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL;
        ALTER TABLE bulk_jobs ADD COLUMN team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL;
        ALTER TABLE alerts ADD COLUMN team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL;
    """),
    ("004_admin_notes", """
        CREATE TABLE IF NOT EXISTS admin_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_admin_notes_user ON admin_notes(user_id);
    """),
    ("003_team_id_indexes", """
        CREATE INDEX IF NOT EXISTS idx_check_history_team ON check_history(team_id);
        CREATE INDEX IF NOT EXISTS idx_user_monitors_team ON user_monitors(team_id);
        CREATE INDEX IF NOT EXISTS idx_bulk_jobs_team ON bulk_jobs(team_id);
        CREATE INDEX IF NOT EXISTS idx_alerts_team ON alerts(team_id);
    """),
    ("005_user_status_and_note_tags", """
        ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active' CHECK(status IN ('active', 'suspended'));
        ALTER TABLE users ADD COLUMN suspended_at TEXT;
        ALTER TABLE users ADD COLUMN admin_flags TEXT DEFAULT '';
        ALTER TABLE admin_notes ADD COLUMN tag TEXT DEFAULT 'general' CHECK(tag IN ('general', 'vip', 'support', 'complaint', 'follow_up', 'bug'));
    """),
    ("006_builder_system", """
        CREATE TABLE IF NOT EXISTS page_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_name TEXT NOT NULL,
            version_data TEXT NOT NULL,
            label TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_page_versions_page ON page_versions(page_name, created_at DESC);

        CREATE TABLE IF NOT EXISTS page_drafts (
            page_name TEXT PRIMARY KEY,
            draft_data TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS page_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            thumbnail TEXT DEFAULT '',
            template_data TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS media_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            url TEXT NOT NULL,
            alt_text TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            mime_type TEXT DEFAULT '',
            width INTEGER,
            height INTEGER,
            tags TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_media_created ON media_library(created_at DESC);

        CREATE TABLE IF NOT EXISTS page_seo (
            page_name TEXT PRIMARY KEY,
            meta_title TEXT DEFAULT '',
            meta_description TEXT DEFAULT '',
            og_title TEXT DEFAULT '',
            og_description TEXT DEFAULT '',
            og_image TEXT DEFAULT '',
            canonical_url TEXT DEFAULT '',
            noindex INTEGER DEFAULT 0,
            json_ld TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS page_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_name TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            referrer TEXT,
            user_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_page_views_page ON page_views(page_name, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_page_views_date ON page_views(created_at);

        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """),
]
