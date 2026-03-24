"""
InbXr — Centralized Database Manager
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
    _seed_blog_posts(conn)
    _seed_frameworks(conn)
    _fix_cta_markers(conn)
    _fix_blog_image_paths(conn)


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


def _seed_blog_posts(conn):
    """Seed blog posts from JSON files in data/ directory. Skips existing slugs."""
    import json as _json
    import re as _re
    # Check both the repo's data/ dir and the DB dir (may differ on Railway)
    repo_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    seed_dirs = [repo_data_dir]
    if _DB_DIR != repo_data_dir:
        seed_dirs.append(_DB_DIR)
    # Also seed default blog categories
    for cat_name in ("Deliverability", "Authentication", "Reputation", "Content"):
        cat_slug = _re.sub(r'[^a-z0-9]+', '-', cat_name.lower()).strip('-')
        existing = conn.execute(
            "SELECT id FROM blog_categories WHERE slug=?", (cat_slug,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO blog_categories (name, slug) VALUES (?, ?)",
                (cat_name, cat_slug)
            )
    conn.commit()

    seen_files = set()
    for seed_dir in seed_dirs:
        if not os.path.isdir(seed_dir):
            continue
        for fname in sorted(os.listdir(seed_dir)):
            if not fname.startswith("blog_seed_") or not fname.endswith(".json"):
                continue
            if fname in seen_files:
                continue
            seen_files.add(fname)
            fpath = os.path.join(seed_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    posts = _json.load(f)
            except Exception:
                continue
            for p in posts:
                existing = conn.execute(
                    "SELECT id FROM blog_posts WHERE slug=?", (p["slug"],)
                ).fetchone()
                if existing:
                    continue
                # Auto-generate featured image if not in seed data
                featured = p.get("featured_image") or ""
                og_img = p.get("og_image") or ""
                if not featured:
                    try:
                        from modules.blog_image import generate_blog_image
                        img_path = generate_blog_image(
                            p["title"], p["slug"],
                            keyword=p.get("keyword_target", ""))
                        featured = img_path
                        og_img = featured
                    except Exception:
                        pass

                conn.execute(
                    """INSERT INTO blog_posts
                       (title, slug, content, excerpt, meta_title, meta_description,
                        featured_image, og_image, tags, status, author, read_time,
                        keyword_target, published_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))""",
                    (
                        p["title"], p["slug"], p.get("content", ""),
                        p.get("excerpt", ""), p.get("meta_title", p["title"]),
                        p.get("meta_description", ""), featured, og_img,
                        p.get("tags", "[]"),
                        p.get("status", "published"), p.get("author", "InbXr Team"),
                        p.get("read_time", 5), p.get("keyword_target", ""),
                        p.get("published_at"),
                    )
                )
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
    ("007_admin_audit_log", """
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            ip_address TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_admin_audit_log_action ON admin_audit_log(action, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_admin_audit_log_date ON admin_audit_log(created_at DESC);
    """),
    ("009_alert_preferences", """
        CREATE TABLE IF NOT EXISTS alert_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            blocklist_alerts INTEGER DEFAULT 1,
            dns_auth_alerts INTEGER DEFAULT 1,
            digest_frequency TEXT DEFAULT 'instant' CHECK(digest_frequency IN ('instant', 'daily', 'weekly', 'off')),
            email_notifications INTEGER DEFAULT 1,
            last_digest_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_prefs_user ON alert_preferences(user_id);

        CREATE TABLE IF NOT EXISTS dns_monitor_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER NOT NULL,
            spf_record TEXT,
            dkim_valid INTEGER,
            dmarc_record TEXT,
            dmarc_policy TEXT,
            issues TEXT DEFAULT '[]',
            scanned_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (monitor_id) REFERENCES user_monitors(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_dns_snapshots_monitor ON dns_monitor_snapshots(monitor_id, scanned_at DESC);
    """),
    ("012_fix_blog_crosslinks", """
        UPDATE blog_posts SET content = REPLACE(
            content,
            '/blog/breaking-into-your-customers-inbox-the-best-way-to-ensure-email-deliverability',
            '/blog/break-into-the-inbox-mastering-email-deliverability-to-land-in-the-primary-inbox-every-time'
        ) WHERE content LIKE '%/blog/breaking-into-your-customers-inbox%';
        UPDATE blog_posts SET content = REPLACE(
            content,
            '/blog/how-to-avoid-gmails-promotions-tab-and-improve-email-deliverability',
            '/blog/break-into-the-inbox-mastering-email-deliverability-to-land-in-the-primary-inbox-every-time'
        ) WHERE content LIKE '%/blog/how-to-avoid-gmails-promotions-tab%';
    """),
    ("011_seed_blog_posts", """
        INSERT OR IGNORE INTO blog_posts
            (title, slug, content, excerpt, meta_title, meta_description, tags, status, author, read_time, keyword_target, published_at, created_at, updated_at)
        VALUES
        ('Breaking into Your Customer''s Inbox: The Best Way to Ensure Email Deliverability',
         'breaking-into-your-customers-inbox-the-best-way-to-ensure-email-deliverability',
         '<h2>Why Your Emails Aren''t Reaching the Inbox</h2>
<p>You spent hours writing the perfect email. The subject line is sharp, the offer is strong, and the design looks great. But none of that matters if your message lands in spam — or worse, never arrives at all. <strong>Email deliverability</strong> is the difference between your campaign performing and your campaign disappearing.</p>
<p>The truth is, most senders don''t realize they have a deliverability problem until their open rates crater. ISPs like Gmail, Outlook, and Yahoo are getting smarter about filtering, and if your sending domain isn''t properly authenticated or your reputation has taken a hit, your emails will quietly vanish.</p>

<h2>The Three Pillars of Email Deliverability</h2>
<p>Getting into the inbox comes down to three things: <strong>authentication</strong>, <strong>reputation</strong>, and <strong>content quality</strong>. Miss any one of them and you''ll struggle.</p>

<h3>1. Domain Authentication (SPF, DKIM, DMARC)</h3>
<p>Authentication tells receiving servers that you are who you say you are. Without it, ISPs have no reason to trust your emails.</p>
<ul>
<li><strong>SPF</strong> — Specifies which servers are allowed to send on behalf of your domain</li>
<li><strong>DKIM</strong> — Adds a cryptographic signature to prove the email wasn''t tampered with in transit</li>
<li><strong>DMARC</strong> — Tells ISPs what to do when SPF or DKIM fails (quarantine, reject, or do nothing)</li>
</ul>
<p>Most deliverability problems start here. A missing or misconfigured SPF record, a broken DKIM signature, or a DMARC policy set to <code>p=none</code> all weaken your sending reputation. You can <a href="/sender">verify your domain authentication</a> in seconds to see exactly where you stand and get copy-paste DNS records to fix any issues.</p>

[CTA:/sender]

<h3>2. Sender Reputation</h3>
<p>Even with perfect authentication, a bad reputation will sink your emails. ISPs track your sending behavior over time — bounce rates, spam complaints, engagement levels, and whether you''re on any blocklists.</p>
<p>If you''re sending to stale lists full of invalid addresses, your bounce rate spikes and ISPs start throttling you. If recipients mark your emails as spam, that''s an even stronger negative signal. And if your domain or IP ends up on a blocklist, many servers will reject your emails outright.</p>
<p>The fix: <a href="/blacklist-monitor">monitor your domain against 100+ blocklists</a> regularly, and <a href="/email-verifier">verify email addresses</a> before sending to keep your bounce rate under 2%.</p>

[CTA:/blacklist-monitor]

<h3>3. Content Quality</h3>
<p>Spam filters scan your email content for red flags — excessive capitalization, too many links, spammy phrases like "ACT NOW" or "100% FREE," and missing unsubscribe links. Even well-intentioned emails can trip these filters if the copy isn''t clean.</p>
<p>Your subject line matters too. It''s the first thing both the recipient and the spam filter see. A misleading or overly aggressive subject line can get you filtered before the email is even opened. Use the <a href="/subject-scorer">Subject Line Scorer</a> to test your subjects across 7 dimensions before you hit send.</p>

[CTA:/subject-scorer]

<h2>How to Test Your Email Deliverability</h2>
<p>The best way to know if your emails will reach the inbox is to test before you send to your full list. Here''s a practical workflow:</p>

<h3>Step 1: Run an Email Test</h3>
<p>Send your email to a test address and get a full diagnostic report — authentication verdicts, spam score, header analysis, and a preview of how it renders in Gmail, Outlook, and Apple Mail. This catches problems before your subscribers ever see them.</p>

[CTA:/]

<h3>Step 2: Check Inbox Placement</h3>
<p>Authentication can pass and your content can look clean, but your email might still land in spam for certain providers. <a href="/placement">Inbox placement testing</a> sends your email to real seed accounts across Gmail, Outlook, and Yahoo to show you exactly where it lands — inbox, spam, or promotions tab.</p>

[CTA:/placement]

<h3>Step 3: Analyze Your Headers</h3>
<p>If something looks off, <a href="/header-analyzer">analyzing your email headers</a> reveals the full routing path — which servers handled your email, whether TLS was used, authentication results at each hop, and where delays occurred. It''s the best way to diagnose delivery issues that aren''t obvious from the outside.</p>

<h2>Building Long-Term Deliverability</h2>
<p>Testing before each campaign is important, but sustainable <strong>email deliverability</strong> requires ongoing habits:</p>
<ul>
<li><strong>Warm up new domains and IPs gradually</strong> — Don''t blast 50,000 emails from a fresh domain. Start small and scale up over 2-4 weeks. Use a <a href="/warmup">warm-up tracker</a> to stay on schedule.</li>
<li><strong>Clean your list regularly</strong> — Remove hard bounces immediately and re-verify inactive addresses every quarter.</li>
<li><strong>Monitor authentication changes</strong> — DNS records can break silently when someone changes your hosting or ESP. Set up monitoring so you know the moment something changes.</li>
<li><strong>Watch your engagement metrics</strong> — ISPs weigh engagement heavily. If your open rates drop, segment your list tighter and re-engage or remove inactive subscribers.</li>
<li><strong>Set up BIMI</strong> — <a href="/bimi">BIMI</a> displays your brand logo next to your emails in supporting inboxes. It requires a verified DMARC policy and boosts both trust and open rates.</li>
</ul>

<h2>Common Deliverability Mistakes to Avoid</h2>
<ul>
<li>Sending from a free email address (gmail.com, yahoo.com) for business email</li>
<li>Using a shared IP with poor-reputation senders</li>
<li>Ignoring spam complaints ("it''s just a few")</li>
<li>Not having an unsubscribe link or making it hard to find</li>
<li>Buying email lists instead of building them organically</li>
<li>Setting DMARC to <code>p=none</code> and forgetting about it</li>
</ul>

<h2>FAQ</h2>
<h3>What is a good email deliverability rate?</h3>
<p>A healthy deliverability rate is 95% or higher, meaning at least 95 out of 100 emails reach the inbox (not spam). If you''re below 90%, you likely have authentication or reputation issues that need immediate attention.</p>

<h3>How often should I test my email deliverability?</h3>
<p>Test before every major campaign, and run a full domain check at least monthly. If you''re sending daily, weekly monitoring of your blocklist status and authentication records is essential.</p>

<h3>Does email authentication guarantee inbox placement?</h3>
<p>No. Authentication (SPF, DKIM, DMARC) is necessary but not sufficient. ISPs also consider your sender reputation, engagement history, and content quality. Think of authentication as the entry ticket — you still need a good reputation to get the best seat.</p>

<h3>How long does it take to fix a bad sender reputation?</h3>
<p>It depends on the severity. Minor issues (a few blocklist listings) can be resolved in days. Major reputation damage (high complaint rates, persistent blocklisting) can take 2-8 weeks of consistent good sending behavior to recover from.</p>

<h3>What''s the difference between inbox placement and delivery rate?</h3>
<p>Delivery rate measures whether the email was accepted by the receiving server (not bounced). Inbox placement measures whether it landed in the inbox vs. spam. You can have a 99% delivery rate but 40% inbox placement if your emails are being accepted but filtered to spam.</p>',
         'Learn why emails miss the inbox and how to fix it — domain authentication, sender reputation, content quality, and testing workflows for reliable email deliverability.',
         'Breaking into Your Customer''s Inbox: The Best Way to Ensure Email Deliverability',
         'Learn the three pillars of email deliverability — authentication, reputation, and content quality — plus a step-by-step testing workflow to ensure your emails reach the inbox.',
         '["email deliverability","SPF","DKIM","DMARC","inbox placement","sender reputation","spam filters"]',
         'published',
         'InbXr Team',
         8,
         'email deliverability',
         datetime('now'),
         datetime('now'),
         datetime('now')),

        ('How to Avoid Gmail''s Promotions Tab and Improve Email Deliverability',
         'how-to-avoid-gmails-promotions-tab-and-improve-email-deliverability',
         '<h2>Introduction to Gmail''s Promotions Tab</h2>
<p>Gmail''s Promotions Tab can be a major obstacle for email marketers. When your emails land in this tab, they are less likely to be seen by your subscribers, resulting in lower engagement and conversion rates. In this article, we will explore why emails end up in the Promotions Tab and provide tips on how to avoid it.</p>

<h2>Why Do Emails End Up in the Promotions Tab?</h2>
<p>Gmail uses algorithms to categorize emails into different tabs. These algorithms look for certain characteristics commonly associated with promotional content, such as keywords, links, and images. If your email contains too many of these characteristics, it may be flagged as promotional.</p>

<h3>Common Characteristics of Promotional Emails</h3>
<ul>
<li>Using keywords like ''sale'', ''discount'', or ''limited time offer''</li>
<li>Including multiple links or URLs</li>
<li>Using attention-grabbing images or graphics</li>
<li>Having a high keyword density</li>
</ul>

<h2>How to Avoid the Promotions Tab and Improve Email Deliverability</h2>
<p>To avoid the Promotions Tab, you need to make your emails look less promotional and more like personal emails.</p>

<h3>Personalize Your Emails</h3>
<p>Personalizing your emails can help them look less like promotional content. Use the subscriber''s name, reference their previous purchases or interactions, and use a more conversational tone.</p>

<h3>Use a Clear and Relevant Subject Line</h3>
<p>Your subject line should be clear, concise, and relevant to the content of your email. Avoid using misleading or attention-grabbing subject lines that may trigger Gmail''s algorithms. Use the <a href="/subject-scorer">Subject Line Scorer</a> to analyze and improve your subject lines.</p>

[CTA:/subject-scorer]

<h3>Optimize Your Email Content</h3>
<p>Make sure your email content is optimized for deliverability. This includes using a balanced mix of text and images, avoiding spam keywords, and using a clear call-to-action. Use the <a href="/">Email Test</a> to get a full checkup of your email and identify areas for improvement.</p>

[CTA:/]

<h3>Set Up Domain Authentication</h3>
<p>Setting up domain authentication can help improve your <strong>email deliverability</strong> and avoid the Promotions Tab. Use <a href="/sender">Sender Check</a> to verify your SPF, DKIM, and DMARC records and generate any missing ones.</p>

[CTA:/sender]

<h2>Conclusion</h2>
<p>Avoiding Gmail''s Promotions Tab requires a combination of personalized content, clear subject lines, and optimized email deliverability. By following these tips and using InbXr''s tools, you can improve your email deliverability and ensure your emails reach your customers'' primary inbox.</p>

<h2>FAQ</h2>
<h3>How do I know if my emails are going to the Promotions Tab?</h3>
<p>The easiest way is to run an <a href="/placement">inbox placement test</a> which sends your email to real seed accounts and shows you exactly which tab it lands in.</p>

<h3>Can I request Gmail to move my emails to the Primary Tab?</h3>
<p>You can''t force it, but you can ask subscribers to drag your email to Primary and click "Yes" when Gmail asks to do this for future messages. This trains the filter for that specific user.</p>

<h3>Does authentication help with the Promotions Tab?</h3>
<p>Authentication (SPF, DKIM, DMARC) helps with overall deliverability but doesn''t directly control tab placement. Tab sorting is based more on content signals and user engagement patterns.</p>',
         'Learn why emails end up in Gmail''s Promotions Tab and how to optimize your content, subject lines, and authentication to reach the primary inbox.',
         'How to Avoid Gmail''s Promotions Tab and Improve Email Deliverability',
         'Learn why emails land in Gmail''s Promotions Tab and actionable tips to improve email deliverability and reach your subscribers'' primary inbox.',
         '["email deliverability","Gmail","Promotions Tab","inbox placement","subject lines"]',
         'published',
         'InbXr Team',
         5,
         'email deliverability',
         datetime('now'),
         datetime('now'),
         datetime('now'))
        ;
    """),
    ("010_fix_blog_links", """
        UPDATE blog_posts SET content = REPLACE(content, 'href="/dns-generator"', 'href="/sender"')
            WHERE content LIKE '%href="/dns-generator"%';
        UPDATE blog_posts SET content = REPLACE(content, 'href="/domain-health"', 'href="/sender"')
            WHERE content LIKE '%href="/domain-health"%';
        UPDATE blog_posts SET content = REPLACE(content, 'href="/full-audit"', 'href="/sender"')
            WHERE content LIKE '%href="/full-audit"%';
        UPDATE blog_posts SET content = REPLACE(content, 'href="/email-test"', 'href="/"')
            WHERE content LIKE '%href="/email-test"%';
        UPDATE blog_posts SET content = REPLACE(content, "href='/dns-generator'", "href='/sender'")
            WHERE content LIKE "%href='/dns-generator'%";
        UPDATE blog_posts SET content = REPLACE(content, "href='/domain-health'", "href='/sender'")
            WHERE content LIKE "%href='/domain-health'%";
        UPDATE blog_posts SET content = REPLACE(content, "href='/full-audit'", "href='/sender'")
            WHERE content LIKE "%href='/full-audit'%";
        UPDATE blog_posts SET content = REPLACE(content, "href='/email-test'", "href='/'")
            WHERE content LIKE "%href='/email-test'%";
    """),
    ("008_blog_system", """
        CREATE TABLE IF NOT EXISTS blog_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            excerpt TEXT DEFAULT '',
            meta_title TEXT DEFAULT '',
            meta_description TEXT DEFAULT '',
            og_image TEXT DEFAULT '',
            featured_image TEXT DEFAULT '',
            category_id INTEGER REFERENCES blog_categories(id) ON DELETE SET NULL,
            tags TEXT DEFAULT '[]',
            status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'published')),
            author TEXT DEFAULT 'InbXr Team',
            read_time INTEGER DEFAULT 5,
            keyword_target TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            published_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug);
        CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status);
        CREATE INDEX IF NOT EXISTS idx_blog_posts_category ON blog_posts(category_id);
        CREATE INDEX IF NOT EXISTS idx_blog_posts_published ON blog_posts(published_at DESC);
    """),
    ("013_onboarding", """
        ALTER TABLE users ADD COLUMN onboarding_dismissed_at TEXT;
    """),
    ("014_blog_featured_images", """
        UPDATE blog_posts
        SET featured_image = '/static/images/blog/' || slug || '.png',
            og_image = '/static/images/blog/' || slug || '.png'
        WHERE (featured_image IS NULL OR featured_image = '')
          AND slug IS NOT NULL AND slug != '';
    """),
    ("015_framework_lab", """
        CREATE TABLE IF NOT EXISTS frameworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            acronym TEXT DEFAULT '',
            category TEXT DEFAULT 'foundational',
            steps_json TEXT NOT NULL DEFAULT '[]',
            description TEXT DEFAULT '',
            when_to_use TEXT DEFAULT '',
            deliverability_notes TEXT DEFAULT '',
            example_output TEXT DEFAULT '',
            decision_tree_tags TEXT DEFAULT '[]',
            is_builtin INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 100,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_frameworks_slug ON frameworks(slug);
        CREATE INDEX IF NOT EXISTS idx_frameworks_category ON frameworks(category);

        CREATE TABLE IF NOT EXISTS user_frameworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            steps_json TEXT NOT NULL DEFAULT '[]',
            base_framework_id INTEGER REFERENCES frameworks(id) ON DELETE SET NULL,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, slug)
        );
        CREATE INDEX IF NOT EXISTS idx_user_frameworks_user ON user_frameworks(user_id);

        CREATE TABLE IF NOT EXISTS framework_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            framework_id INTEGER REFERENCES frameworks(id) ON DELETE SET NULL,
            user_framework_id INTEGER REFERENCES user_frameworks(id) ON DELETE SET NULL,
            check_history_id INTEGER REFERENCES check_history(id) ON DELETE SET NULL,
            action TEXT DEFAULT 'rewrite',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_framework_usage_user ON framework_usage(user_id, created_at DESC);
    """),
    ("017_framework_favorites", """
        CREATE TABLE IF NOT EXISTS user_framework_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            framework_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, framework_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (framework_id) REFERENCES frameworks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_user_fw_favs_user ON user_framework_favorites(user_id);
    """),
    ("016_fix_c3po_plant_doubt", """
        UPDATE frameworks
        SET description = REPLACE(description, 'Plausibility', 'Plant Doubt'),
            steps_json = REPLACE(REPLACE(steps_json, '"Plausibility"', '"Plant Doubt"'), 'Prove it''s achievable. Use data, social proof, or a quick case study to make the picture believable.', 'Make them question what they think they know. Introduce a gap in their understanding \u2014 the thing they''re missing or getting wrong that''s holding them back.'),
            example_output = 'Subject: The inbox problem nobody''s talking about

Context: 83% of marketing emails never reach the inbox...
Picture: Imagine your next campaign hitting 98% inbox placement...
Plant Doubt: But what if everything you''ve been told about deliverability is wrong? What if the real problem isn''t your content?
Problem: Most senders are optimizing the wrong things while their authentication silently breaks...
Opportunity: Start your free InbXr audit today and see where you actually stand.'
        WHERE slug = 'c3po';
    """),
    ("018_lead_emails", """
        CREATE TABLE IF NOT EXISTS lead_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL COLLATE NOCASE,
            ip_address TEXT,
            source TEXT DEFAULT 'email_test_gate',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_lead_emails_email ON lead_emails(email);
    """),
]


def _seed_frameworks(conn):
    """Seed built-in copywriting frameworks. Skips if already seeded."""
    import json as _json
    existing = conn.execute("SELECT COUNT(*) as cnt FROM frameworks WHERE is_builtin = 1").fetchone()
    if existing and existing["cnt"] >= 16:
        return

    _frameworks = [
        {
            "name": "C3PO — The InbXr Method",
            "slug": "c3po",
            "acronym": "C3PO",
            "category": "master",
            "sort_order": 1,
            "description": "InbXr's proprietary 5-step framework for emails that convert. Context → Picture → Plant Doubt → Problem → Opportunity.",
            "when_to_use": "Use for any email where you need to move the reader from awareness to action. Works across industries and audience awareness levels.",
            "deliverability_notes": "Naturally avoids spam triggers because it leads with context and storytelling rather than hype.",
            "example_output": "Subject: The inbox problem nobody's talking about\n\nContext: 83% of marketing emails never reach the inbox...\nPicture: Imagine your next campaign hitting 98% inbox placement...\nPlant Doubt: But what if everything you've been told about deliverability is wrong? What if the real problem isn't your content?\nProblem: Most senders are optimizing the wrong things while their authentication silently breaks...\nOpportunity: Start your free InbXr audit today and see where you actually stand.",
            "steps_json": _json.dumps([
                {"key": "C", "label": "Context", "description": "Set the scene. Ground the reader in a relevant situation, stat, or shared experience they instantly recognize."},
                {"key": "P1", "label": "Picture", "description": "Paint the desired outcome. Help them vividly see what success looks like — make it tangible and emotional."},
                {"key": "P2", "label": "Plant Doubt", "description": "Make them question what they think they know. Introduce a gap in their understanding — the thing they're missing or getting wrong that's holding them back."},
                {"key": "P3", "label": "Problem", "description": "Name the obstacle. Identify the specific gap or mistake standing between them and the picture you painted."},
                {"key": "O", "label": "Opportunity", "description": "Present your solution as the bridge. Clear CTA that connects the problem to the desired outcome."}
            ]),
        },
        {
            "name": "AIDA",
            "slug": "aida",
            "acronym": "AIDA",
            "category": "foundational",
            "sort_order": 10,
            "description": "The classic marketing framework: grab Attention, build Interest, create Desire, drive Action.",
            "when_to_use": "Best for audiences with low awareness. Use when you need to introduce a concept from scratch and guide the reader step by step.",
            "deliverability_notes": "Watch the Attention step — avoid ALL CAPS or clickbait subject lines that trigger spam filters.",
            "example_output": "Attention: Your emails are landing in spam — and you don't even know it.\nInterest: 1 in 5 marketing emails never reaches the inbox.\nDesire: Imagine knowing exactly where every email lands before you hit send.\nAction: Try InbXr free — your first inbox placement test is on us.",
            "steps_json": _json.dumps([
                {"key": "A", "label": "Attention", "description": "Open with a bold hook — a surprising stat, provocative question, or pattern interrupt that stops the scroll."},
                {"key": "I", "label": "Interest", "description": "Build on the hook with relevant details. Show you understand their world and the stakes involved."},
                {"key": "D", "label": "Desire", "description": "Make them want the solution. Paint the benefit in emotional, outcome-focused language."},
                {"key": "A2", "label": "Action", "description": "Clear, specific CTA. Tell them exactly what to do next and make it frictionless."}
            ]),
        },
        {
            "name": "PAS",
            "slug": "pas",
            "acronym": "PAS",
            "category": "foundational",
            "sort_order": 11,
            "description": "Problem → Agitate → Solve. Identify a pain point, twist the knife, then present the relief.",
            "when_to_use": "Ideal for problem-aware audiences. Use when readers already feel the pain but haven't found a solution.",
            "deliverability_notes": "The Agitate step can tip into fear-mongering. Keep it empathetic, not alarmist, to avoid spam complaints.",
            "example_output": "Problem: Your bounce rate is climbing and you don't know why.\nAgitate: Every bounced email damages your sender reputation — and once ISPs flag you, recovery takes months.\nSolve: InbXr monitors your reputation 24/7 and alerts you before damage is done.",
            "steps_json": _json.dumps([
                {"key": "P", "label": "Problem", "description": "Identify the reader's pain point clearly. Be specific — vague problems don't resonate."},
                {"key": "A", "label": "Agitate", "description": "Amplify the pain. Show the consequences of inaction. Make them feel the urgency."},
                {"key": "S", "label": "Solve", "description": "Present your solution as the clear path to relief. Be direct about what it does and how to get it."}
            ]),
        },
        {
            "name": "FAB",
            "slug": "fab",
            "acronym": "FAB",
            "category": "value_logic",
            "sort_order": 20,
            "description": "Feature → Advantage → Benefit. Translate what your product does into why the reader should care.",
            "when_to_use": "Best for solution-aware audiences comparing options. Use when you need to differentiate features.",
            "deliverability_notes": "Feature-heavy emails can feel promotional. Balance with reader-focused benefit language.",
            "example_output": "Feature: Real-time blocklist monitoring across 110+ databases.\nAdvantage: You'll know within minutes if your domain gets listed — not days.\nBenefit: No more surprise drops in deliverability that tank your campaign ROI.",
            "steps_json": _json.dumps([
                {"key": "F", "label": "Feature", "description": "State the feature or capability clearly and concisely."},
                {"key": "A", "label": "Advantage", "description": "Explain what this feature enables — the functional improvement over alternatives."},
                {"key": "B", "label": "Benefit", "description": "Connect to the emotional outcome. Answer: 'So what? Why does this matter to ME?'"}
            ]),
        },
        {
            "name": "4 Ps",
            "slug": "4ps",
            "acronym": "4Ps",
            "category": "value_logic",
            "sort_order": 21,
            "description": "Promise → Picture → Proof → Push. Lead with a bold promise, visualize the outcome, prove it, then push to action.",
            "when_to_use": "Great for launches and promotions where you have strong social proof to back up a bold claim.",
            "deliverability_notes": "Bold promises can trigger spam filters. Back them with data and avoid superlatives like 'best ever' or 'guaranteed'.",
            "example_output": "Promise: Get 95%+ inbox placement on your next campaign.\nPicture: Your open rates climb, revenue follows, and you stop worrying about spam.\nProof: 2,400 senders improved placement by an average of 31% in their first month.\nPush: Start your free audit now — see your real inbox rate in 60 seconds.",
            "steps_json": _json.dumps([
                {"key": "P1", "label": "Promise", "description": "Lead with a specific, compelling promise. Make it measurable if possible."},
                {"key": "P2", "label": "Picture", "description": "Help the reader visualize life after the promise is fulfilled."},
                {"key": "P3", "label": "Proof", "description": "Back it up with data, testimonials, case studies, or credentials."},
                {"key": "P4", "label": "Push", "description": "Drive to action with urgency or a clear next step."}
            ]),
        },
        {
            "name": "BAB",
            "slug": "bab",
            "acronym": "BAB",
            "category": "story_transformation",
            "sort_order": 30,
            "description": "Before → After → Bridge. Show the current state, the desired state, then bridge the gap with your solution.",
            "when_to_use": "Perfect for transformation narratives. Use when the gap between current and desired state is clear and emotional.",
            "deliverability_notes": "Transformation language is natural and conversational — low spam risk.",
            "example_output": "Before: You're sending 50K emails a month but only 60% reach the inbox.\nAfter: Every email lands where it belongs. Open rates double. Revenue follows.\nBridge: InbXr's deliverability suite finds and fixes the gaps. Start free.",
            "steps_json": _json.dumps([
                {"key": "B1", "label": "Before", "description": "Describe the reader's current painful reality. Be specific and empathetic."},
                {"key": "A", "label": "After", "description": "Paint the transformed state. Make it vivid and desirable."},
                {"key": "B2", "label": "Bridge", "description": "Position your product/solution as the bridge between Before and After."}
            ]),
        },
        {
            "name": "Star-Story-Solution",
            "slug": "star-story-solution",
            "acronym": "SSS",
            "category": "story_transformation",
            "sort_order": 31,
            "description": "Introduce a Star (character), tell their Story (struggle), reveal the Solution. Narrative-driven persuasion.",
            "when_to_use": "Use when you have a compelling case study or customer story. Great for building emotional connection.",
            "deliverability_notes": "Story-driven emails read like personal messages — excellent for inbox placement.",
            "example_output": "Star: Meet Sarah, an email marketer at a 50-person SaaS company.\nStory: Her campaigns were getting 12% open rates. She spent weeks tweaking subject lines, but the real problem was 40% of her emails were going to spam.\nSolution: After running InbXr's audit, she fixed 3 DNS issues in 10 minutes. Open rates jumped to 28% within two weeks.",
            "steps_json": _json.dumps([
                {"key": "S1", "label": "Star", "description": "Introduce a relatable character — could be a customer, the reader themselves, or even you."},
                {"key": "S2", "label": "Story", "description": "Tell their struggle. Make it specific and relatable. Show the obstacles they faced."},
                {"key": "S3", "label": "Solution", "description": "Reveal how they solved it (with your product). Show the result."}
            ]),
        },
        {
            "name": "PAPA",
            "slug": "papa",
            "acronym": "PAPA",
            "category": "trust_proof",
            "sort_order": 40,
            "description": "Problem → Advantage → Proof → Action. Similar to PAS but replaces agitation with proof-based advantage.",
            "when_to_use": "Use when your audience is skeptical and needs evidence more than emotional agitation.",
            "deliverability_notes": "Proof-heavy emails feel credible. Include specific numbers rather than vague claims.",
            "example_output": "Problem: Email authentication is confusing and easy to get wrong.\nAdvantage: InbXr checks SPF, DKIM, DMARC, MTA-STS, BIMI, and DANE in one scan — and generates fix records.\nProof: 15,000+ domains audited. Average setup time: 8 minutes.\nAction: Run your free sender check now.",
            "steps_json": _json.dumps([
                {"key": "P1", "label": "Problem", "description": "State the problem clearly and specifically."},
                {"key": "A", "label": "Advantage", "description": "Present your unique advantage — what makes your approach different."},
                {"key": "P2", "label": "Proof", "description": "Back it up with hard evidence: numbers, testimonials, case studies."},
                {"key": "A2", "label": "Action", "description": "Clear call to action with low friction."}
            ]),
        },
        {
            "name": "APP",
            "slug": "app",
            "acronym": "APP",
            "category": "trust_proof",
            "sort_order": 41,
            "description": "Agree → Promise → Preview. Start by agreeing with the reader's worldview, promise a solution, preview what's coming.",
            "when_to_use": "Great for content marketing emails and newsletters. Builds trust before making the ask.",
            "deliverability_notes": "Agreement-first framing feels personal and non-salesy — great for deliverability.",
            "example_output": "Agree: You already know email authentication matters — that's not the hard part.\nPromise: The hard part is knowing if your setup actually works. We'll show you in 60 seconds.\nPreview: Enter your domain below and get a full 6-protocol audit with copy-paste fix records.",
            "steps_json": _json.dumps([
                {"key": "A1", "label": "Agree", "description": "Start with something the reader already believes. Build rapport through shared understanding."},
                {"key": "P", "label": "Promise", "description": "Promise to solve the next problem — the thing they haven't figured out yet."},
                {"key": "P2", "label": "Preview", "description": "Give a taste of what's coming. Tease the value to drive clicks."}
            ]),
        },
        {
            "name": "5 Cs",
            "slug": "5cs",
            "acronym": "5Cs",
            "category": "refinement",
            "sort_order": 50,
            "description": "Clear → Concise → Compelling → Credible → Call to Action. A quality checklist framework for polishing email copy.",
            "when_to_use": "Use as a refinement pass on any email. Works as a scoring rubric for copy quality.",
            "deliverability_notes": "Following the 5 Cs naturally produces clean, spam-filter-friendly copy.",
            "example_output": "Clear: One idea per email. No jargon.\nConcise: Under 200 words. Short paragraphs.\nCompelling: Lead with the reader's outcome, not your feature.\nCredible: Include one specific proof point.\nCall to Action: One button, one action, clear language.",
            "steps_json": _json.dumps([
                {"key": "C1", "label": "Clear", "description": "Is the core message immediately obvious? One idea per email."},
                {"key": "C2", "label": "Concise", "description": "Can anything be cut without losing meaning? Trim ruthlessly."},
                {"key": "C3", "label": "Compelling", "description": "Does the reader care? Is it focused on their outcome?"},
                {"key": "C4", "label": "Credible", "description": "Is there proof? Specifics beat generalities."},
                {"key": "C5", "label": "Call to Action", "description": "Is there one clear next step? Is it easy to take?"}
            ]),
        },
        {
            "name": "4 Us",
            "slug": "4us",
            "acronym": "4Us",
            "category": "refinement",
            "sort_order": 51,
            "description": "Useful → Urgent → Unique → Ultra-specific. A framework for writing subject lines and headlines that get opened.",
            "when_to_use": "Best for subject lines, headlines, and CTAs. Score each element 1-4 to optimize.",
            "deliverability_notes": "Ultra-specific language avoids vague spam triggers. Urgency should be genuine, not manufactured.",
            "example_output": "Useful: 'Fix your SPF record' (solves a real problem)\nUrgent: 'before your next campaign' (time-bound)\nUnique: 'the 3-minute method' (differentiated approach)\nUltra-specific: '3 DNS records, 1 copy-paste fix' (concrete detail)",
            "steps_json": _json.dumps([
                {"key": "U1", "label": "Useful", "description": "Does it solve a real problem or provide clear value?"},
                {"key": "U2", "label": "Urgent", "description": "Is there a genuine reason to act now? Create real, not manufactured, urgency."},
                {"key": "U3", "label": "Unique", "description": "What makes this different from everything else in their inbox?"},
                {"key": "U4", "label": "Ultra-specific", "description": "Is it concrete? Numbers, names, and specifics beat vague promises."}
            ]),
        },
        {
            "name": "4 Es",
            "slug": "4es",
            "acronym": "4Es",
            "category": "refinement",
            "sort_order": 52,
            "description": "Engage → Educate → Excite → Encourage. A nurture-focused framework for building relationships over time.",
            "when_to_use": "Use for welcome sequences, newsletters, and nurture emails where the goal is relationship over immediate conversion.",
            "deliverability_notes": "Nurture-style emails get high engagement, which boosts sender reputation long-term.",
            "example_output": "Engage: Quick question — do you know your current inbox placement rate?\nEducate: Most senders assume 90%+ reaches the inbox. The real average is closer to 79%.\nExcite: The good news? The fixes are usually simple — and you can find them in under 2 minutes.\nEncourage: Try a free test right now and see where you actually stand.",
            "steps_json": _json.dumps([
                {"key": "E1", "label": "Engage", "description": "Open with a question, story, or hook that pulls the reader in."},
                {"key": "E2", "label": "Educate", "description": "Share something valuable they didn't know. Build authority."},
                {"key": "E3", "label": "Excite", "description": "Show them what's possible. Create anticipation."},
                {"key": "E4", "label": "Encourage", "description": "Gentle nudge to take action. Supportive, not pushy."}
            ]),
        },
        {
            "name": "SLAP",
            "slug": "slap",
            "acronym": "SLAP",
            "category": "niche",
            "sort_order": 60,
            "description": "Stop → Look → Act → Purchase. Interrupt-driven framework for high-urgency promotions.",
            "when_to_use": "Use for flash sales, limited-time offers, and high-urgency announcements. Not for everyday emails.",
            "deliverability_notes": "High-urgency language can trigger spam filters. Use sparingly and back urgency with real deadlines.",
            "example_output": "Stop: Wait — before you send another campaign.\nLook: Your domain just appeared on 2 new blocklists.\nAct: Check your status now (takes 10 seconds).\nPurchase: Upgrade to Pro for 24/7 automated monitoring.",
            "steps_json": _json.dumps([
                {"key": "S", "label": "Stop", "description": "Pattern interrupt. Stop the reader mid-scroll with something unexpected."},
                {"key": "L", "label": "Look", "description": "Direct their attention to the key information or offer."},
                {"key": "A", "label": "Act", "description": "Tell them exactly what to do right now."},
                {"key": "P", "label": "Purchase", "description": "Close with the specific purchase or conversion action."}
            ]),
        },
        {
            "name": "ACCA",
            "slug": "acca",
            "acronym": "ACCA",
            "category": "niche",
            "sort_order": 61,
            "description": "Awareness → Comprehension → Conviction → Action. A methodical framework for complex or technical products.",
            "when_to_use": "Best for B2B, technical products, or when the reader needs education before they can evaluate your offer.",
            "deliverability_notes": "Educational content builds trust and engagement — ISPs reward this with better placement.",
            "example_output": "Awareness: Email authentication has 6 protocols — most senders only know 3.\nComprehension: SPF, DKIM, and DMARC are table stakes. MTA-STS, DANE, and BIMI are the new standard.\nConviction: Senders with full auth see 23% higher inbox rates on average.\nAction: Check all 6 protocols in one scan — free, no signup required.",
            "steps_json": _json.dumps([
                {"key": "A1", "label": "Awareness", "description": "Introduce the problem or opportunity. Make the reader aware of something they're missing."},
                {"key": "C", "label": "Comprehension", "description": "Help them understand the details. Educate without overwhelming."},
                {"key": "C2", "label": "Conviction", "description": "Build belief that this matters and that your solution works. Use proof."},
                {"key": "A2", "label": "Action", "description": "Clear next step. Make it easy and low-risk."}
            ]),
        },
        {
            "name": "PRUNE",
            "slug": "prune",
            "acronym": "PRUNE",
            "category": "niche",
            "sort_order": 62,
            "description": "Preview → Restate → Underline → Nudge → End. A framework for follow-up and reminder emails.",
            "when_to_use": "Use for follow-up sequences, abandoned cart, re-engagement, and reminder emails.",
            "deliverability_notes": "Follow-up emails to engaged contacts perform well. Avoid sending to unengaged segments.",
            "example_output": "Preview: Remember that deliverability audit you started?\nRestate: Your domain had 3 critical issues that could be hurting your inbox rate.\nUnderline: Every day those issues stay unfixed, more of your emails miss the inbox.\nNudge: It takes 5 minutes to fix. Here's your saved report.\nEnd: Fix it now → [link]",
            "steps_json": _json.dumps([
                {"key": "P", "label": "Preview", "description": "Reference the previous interaction or context. Jog their memory."},
                {"key": "R", "label": "Restate", "description": "Restate the key value or finding from before."},
                {"key": "U", "label": "Underline", "description": "Emphasize what's at stake. Why should they act now?"},
                {"key": "N", "label": "Nudge", "description": "Gentle push toward action. Make it feel easy."},
                {"key": "E", "label": "End", "description": "One clear CTA. Keep it simple."}
            ]),
        },
        {
            "name": "3 Reasons Why",
            "slug": "3-reasons-why",
            "acronym": "3RW",
            "category": "niche",
            "sort_order": 63,
            "description": "Answer three questions: Why this? Why you? Why now? Simple framework for overcoming objections.",
            "when_to_use": "Use when the reader is considering but hasn't committed. Great for mid-funnel emails.",
            "deliverability_notes": "Objection-handling emails feel helpful, not salesy — good for engagement.",
            "example_output": "Why this: Your email deliverability directly controls your revenue.\nWhy us: InbXr is the only tool that checks all 6 auth protocols in one scan.\nWhy now: Gmail's February 2024 sender requirements mean non-compliant domains get throttled.",
            "steps_json": _json.dumps([
                {"key": "W1", "label": "Why This", "description": "Why does this problem/solution matter? Establish relevance."},
                {"key": "W2", "label": "Why You", "description": "Why is your solution the right one? Differentiate from alternatives."},
                {"key": "W3", "label": "Why Now", "description": "Why should they act today? Create genuine urgency or timeliness."}
            ]),
        },
    ]

    for fw in _frameworks:
        existing_fw = conn.execute(
            "SELECT id FROM frameworks WHERE slug = ?", (fw["slug"],)
        ).fetchone()
        if existing_fw:
            continue
        conn.execute(
            """INSERT INTO frameworks
               (name, slug, acronym, category, steps_json, description,
                when_to_use, deliverability_notes, example_output, sort_order, is_builtin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (fw["name"], fw["slug"], fw["acronym"], fw["category"],
             fw["steps_json"], fw["description"], fw["when_to_use"],
             fw["deliverability_notes"], fw["example_output"], fw["sort_order"])
        )
    conn.commit()


def _fix_cta_markers(conn):
    """Replace [CTA:/path] markers in blog post content with actual URLs."""
    import re as _re
    rows = conn.execute(
        "SELECT id, content FROM blog_posts WHERE content LIKE '%[CTA:%'"
    ).fetchall()
    for row in rows:
        content = row["content"]
        # Replace href="[CTA:/path]" with href="/path"
        content = _re.sub(r'href="\[CTA:(/[^\]]*)\]"', r'href="\1"', content)
        content = _re.sub(r"href='\[CTA:(/[^\]]*)\]'", r"href='\1'", content)
        # Replace standalone [CTA:/path] markers with nothing (already linked)
        content = _re.sub(r'\[CTA:/[^\]]*\]', '', content)
        # Fix /email-test links to /
        content = content.replace('href="/email-test"', 'href="/"')
        conn.execute("UPDATE blog_posts SET content=? WHERE id=?", (content, row["id"]))
    if rows:
        conn.commit()


def _fix_blog_image_paths(conn):
    """Migrate old /static/images/blog/ paths to /blog-images/ served from persistent volume."""
    rows = conn.execute(
        "SELECT id, slug, featured_image FROM blog_posts WHERE featured_image LIKE '/static/images/blog/%'"
    ).fetchall()
    for row in rows:
        new_path = f"/blog-images/{row['slug']}.png"
        conn.execute("UPDATE blog_posts SET featured_image=?, og_image=? WHERE id=?",
                     (new_path, new_path, row["id"]))
    if rows:
        conn.commit()
        import logging
        logging.getLogger('inbxr.database').info("Migrated %d blog image paths to /blog-images/", len(rows))
