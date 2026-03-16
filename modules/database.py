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
    _seed_blog_posts(conn)
    _fix_cta_markers(conn)


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
                        featured = f"/static/{img_path}"
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
                        p.get("status", "published"), p.get("author", "INBXR Team"),
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
         'INBXR Team',
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
<p>Avoiding Gmail''s Promotions Tab requires a combination of personalized content, clear subject lines, and optimized email deliverability. By following these tips and using INBXR''s tools, you can improve your email deliverability and ensure your emails reach your customers'' primary inbox.</p>

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
         'INBXR Team',
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
            author TEXT DEFAULT 'INBXR Team',
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
]


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
