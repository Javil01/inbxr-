"""
INBXR — Blog Blueprint
Public blog pages, sitemap, and admin CRUD / AI writer endpoints.
"""

import re
import time
from datetime import datetime

from flask import (
    Blueprint, render_template, request, jsonify, session, abort,
    Response, url_for,
)

from modules.database import fetchall, fetchone, execute

blog_bp = Blueprint("blog", __name__)

_PER_PAGE = 12

# ── Tool map for CTA blocks ─────────────────────────────

_TOOL_MAP = {
    '/':                  ('Email Test',        'Send a real email and get a full deliverability checkup'),
    '/sender':            ('Sender Check',      'Verify your domain authentication and generate DNS records'),
    '/placement':         ('Inbox Placement',   'Test where your emails actually land'),
    '/subject-scorer':    ('Subject Line Scorer','Score your subject line for spam triggers'),
    '/bimi':              ('BIMI Checker',      'Validate your BIMI setup'),
    '/blacklist-monitor': ('Blacklist Monitor', 'Check if you\'re on any blocklists'),
    '/header-analyzer':   ('Header Analyzer',   'Parse and analyze email headers'),
    '/email-verifier':    ('Email Verifier',    'Verify email addresses before sending'),
    '/warmup':            ('Warm-up Tracker',   'Track your domain warm-up progress'),
}


def _process_ctas(content):
    """Replace [CTA:/tool-path] markers with HTML CTA blocks."""
    def replace_cta(match):
        path = match.group(1)
        tool = _TOOL_MAP.get(path)
        if not tool:
            return ''
        name, desc = tool
        return (
            f'<div class="blog-cta">'
            f'<p>{desc}</p>'
            f'<a href="{path}" class="blog-cta__btn">Try {name} Free \u2192</a>'
            f'</div>'
        )
    return re.sub(r'\[CTA:(\/[\w-]*)\]', replace_cta, content)


# Redirect URLs that should point to /sender
_LINK_REDIRECTS = {
    '/dns-generator': '/sender',
    '/domain-health': '/sender',
    '/full-audit': '/sender',
    '/email-test': '/',
}

def _fix_legacy_links(content):
    """Rewrite old redirect URLs in blog HTML to their canonical destinations."""
    for old, new in _LINK_REDIRECTS.items():
        content = content.replace(f'href="{old}"', f'href="{new}"')
        content = content.replace(f"href='{old}'", f"href='{new}'")
    return content


# ── Admin auth helper ────────────────────────────────────

def _is_admin():
    if not session.get("is_admin", False):
        return False
    admin_login_time = session.get("admin_login_at")
    if not admin_login_time:
        return False
    if time.time() - admin_login_time > 4 * 3600:
        return False
    return True


# ── Public routes ────────────────────────────────────────

@blog_bp.route("/blog")
def blog_index():
    """Blog listing page with optional category/tag filter and pagination."""
    category_slug = request.args.get("category", "").strip()
    tag_filter = request.args.get("tag", "").strip()
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * _PER_PAGE

    # Build query
    where_clauses = ["bp.status = 'published'"]
    params = []

    if category_slug:
        where_clauses.append("bc.slug = ?")
        params.append(category_slug)

    if tag_filter:
        where_clauses.append("bp.tags LIKE ?")
        params.append(f'%"{tag_filter}"%')

    where_sql = " AND ".join(where_clauses)

    # Count for pagination
    count_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM blog_posts bp
        LEFT JOIN blog_categories bc ON bp.category_id = bc.id
        WHERE {where_sql}
    """
    total = fetchone(count_sql, params)["cnt"]
    total_pages = max(1, (total + _PER_PAGE - 1) // _PER_PAGE)

    # Fetch posts
    posts_sql = f"""
        SELECT bp.*, bc.name AS category_name, bc.slug AS category_slug
        FROM blog_posts bp
        LEFT JOIN blog_categories bc ON bp.category_id = bc.id
        WHERE {where_sql}
        ORDER BY bp.published_at DESC
        LIMIT ? OFFSET ?
    """
    posts = fetchall(posts_sql, params + [_PER_PAGE, offset])

    # All categories for filter bar
    categories = fetchall("SELECT * FROM blog_categories ORDER BY name")

    return render_template(
        "blog/index.html",
        posts=posts,
        categories=categories,
        current_category=category_slug,
        current_tag=tag_filter,
        current_page=page,
        total_pages=total_pages,
        total_posts=total,
        active_page="blog",
        page_title="Blog — INBXR",
        page_description="Email deliverability tips, guides, and best practices from the INBXR team.",
        canonical_url="https://inbxr.us/blog",
    )


@blog_bp.route("/blog/<slug>")
def blog_post(slug):
    """Single blog post page."""
    post = fetchone(
        """SELECT bp.*, bc.name AS category_name, bc.slug AS category_slug
           FROM blog_posts bp
           LEFT JOIN blog_categories bc ON bp.category_id = bc.id
           WHERE bp.slug = ? AND bp.status = 'published'""",
        (slug,),
    )
    if not post:
        abort(404)

    # Related posts — same tags via LIKE, limit 3, exclude current
    related = []
    if post.get("tags") and post["tags"] != "[]":
        import json
        try:
            tag_list = json.loads(post["tags"])
        except (json.JSONDecodeError, TypeError):
            tag_list = []
        if tag_list:
            like_clauses = " OR ".join(["bp.tags LIKE ?" for _ in tag_list])
            like_params = [f'%"{t}"%' for t in tag_list]
            related = fetchall(
                f"""SELECT bp.id, bp.title, bp.slug, bp.excerpt, bp.featured_image,
                           bp.published_at, bp.read_time
                    FROM blog_posts bp
                    WHERE bp.status = 'published'
                      AND bp.id != ?
                      AND ({like_clauses})
                    ORDER BY bp.published_at DESC
                    LIMIT 3""",
                [post["id"]] + like_params,
            )

    # Process CTA markers and fix legacy links
    content = _process_ctas(post["content"] or "")
    content = _fix_legacy_links(content)

    return render_template(
        "blog/post.html",
        post=post,
        content=content,
        related=related,
        active_page="blog",
    )


@blog_bp.route("/sitemap.xml")
def sitemap():
    """XML sitemap for SEO — static pages + published blog posts."""
    static_pages = [
        "/", "/sender", "/placement", "/subject-scorer",
        "/bimi", "/blacklist-monitor", "/header-analyzer",
        "/email-verifier", "/warmup", "/blog", "/pricing",
        "/privacy", "/terms",
    ]

    posts = fetchall(
        "SELECT slug, updated_at, published_at FROM blog_posts WHERE status = 'published' ORDER BY published_at DESC"
    )

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    for path in static_pages:
        xml_parts.append(f"  <url><loc>https://inbxr.com{path}</loc></url>")

    for p in posts:
        lastmod = p.get("updated_at") or p.get("published_at") or ""
        if lastmod:
            lastmod_tag = f"<lastmod>{lastmod[:10]}</lastmod>"
        else:
            lastmod_tag = ""
        xml_parts.append(
            f"  <url><loc>https://inbxr.com/blog/{p['slug']}</loc>{lastmod_tag}</url>"
        )

    xml_parts.append("</urlset>")
    return Response("\n".join(xml_parts), content_type="application/xml")


# ── Admin page routes ────────────────────────────────────

@blog_bp.route("/admin/blog")
def admin_blog():
    """Blog manager page."""
    if not _is_admin():
        return redirect_admin_login()
    return render_template("admin_blog.html", active_page="admin_blog")


@blog_bp.route("/admin/blog/new")
def admin_blog_new():
    """New post editor."""
    if not _is_admin():
        return redirect_admin_login()
    return render_template("admin_blog_editor.html", post=None, active_page="admin_blog")


@blog_bp.route("/admin/blog/edit/<int:post_id>")
def admin_blog_edit(post_id):
    """Edit existing post."""
    if not _is_admin():
        return redirect_admin_login()
    post = fetchone("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    if not post:
        abort(404)
    return render_template("admin_blog_editor.html", post=post, active_page="admin_blog")


# ── Admin API routes ─────────────────────────────────────

@blog_bp.route("/admin/api/blog/posts", methods=["GET"])
def admin_list_posts():
    """List all posts with category names (JSON)."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 401
    posts = fetchall(
        """SELECT bp.*, bc.name AS category_name
           FROM blog_posts bp
           LEFT JOIN blog_categories bc ON bp.category_id = bc.id
           ORDER BY bp.created_at DESC"""
    )
    return jsonify({"ok": True, "posts": posts})


@blog_bp.route("/admin/api/blog/posts", methods=["POST"])
def admin_create_post():
    """Create a new blog post (JSON)."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "Title is required."}), 400

    slug = (data.get("slug") or "").strip()
    if not slug:
        slug = _slugify(title)

    content = data.get("content") or ""
    excerpt = (data.get("excerpt") or "").strip()
    meta_title = (data.get("meta_title") or "").strip()
    meta_description = (data.get("meta_description") or "").strip()
    og_image = (data.get("og_image") or "").strip()
    featured_image = (data.get("featured_image") or "").strip()
    category_id = data.get("category_id") or None
    tags = data.get("tags") or "[]"
    if isinstance(tags, list):
        import json
        tags = json.dumps(tags)
    status = data.get("status") or "draft"
    author = (data.get("author") or "INBXR Team").strip()
    keyword_target = (data.get("keyword_target") or "").strip()

    # Auto-generate featured image if none provided
    if not featured_image:
        try:
            from modules.blog_image import generate_blog_image
            cat_name = ""
            if category_id:
                cat_row = fetchone("SELECT name FROM blog_categories WHERE id = ?", (category_id,))
                cat_name = cat_row["name"] if cat_row else ""
            img_path = generate_blog_image(title, slug, category=cat_name, keyword=keyword_target)
            featured_image = img_path
            if not og_image:
                og_image = featured_image
        except Exception:
            pass

    read_time = max(1, len(content.split()) // 200)
    published_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if status == "published" else None

    cur = execute(
        """INSERT INTO blog_posts
           (title, slug, content, excerpt, meta_title, meta_description,
            og_image, featured_image, category_id, tags, status, author,
            read_time, keyword_target, published_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, slug, content, excerpt, meta_title, meta_description,
         og_image, featured_image, category_id, tags, status, author,
         read_time, keyword_target, published_at),
    )
    return jsonify({"ok": True, "id": cur.lastrowid}), 201


@blog_bp.route("/admin/api/blog/posts/<int:post_id>", methods=["PUT"])
def admin_update_post(post_id):
    """Update an existing blog post (JSON)."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 401

    post = fetchone("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    if not post:
        return jsonify({"ok": False, "error": "Post not found."}), 404

    data = request.get_json(force=True, silent=True) or {}

    title = (data.get("title") or post["title"]).strip()
    slug = (data.get("slug") or post["slug"]).strip()
    content = data.get("content") if data.get("content") is not None else post["content"]
    excerpt = (data.get("excerpt") or "").strip() if "excerpt" in data else post["excerpt"]
    meta_title = (data.get("meta_title") or "").strip() if "meta_title" in data else post["meta_title"]
    meta_description = (data.get("meta_description") or "").strip() if "meta_description" in data else post["meta_description"]
    og_image = (data.get("og_image") or "").strip() if "og_image" in data else post["og_image"]
    featured_image = (data.get("featured_image") or "").strip() if "featured_image" in data else post["featured_image"]
    category_id = data.get("category_id") if "category_id" in data else post["category_id"]
    tags = data.get("tags") if "tags" in data else post["tags"]
    if isinstance(tags, list):
        import json
        tags = json.dumps(tags)
    status = data.get("status") or post["status"]
    author = (data.get("author") or post["author"]).strip()
    keyword_target = (data.get("keyword_target") or "").strip() if "keyword_target" in data else post["keyword_target"]

    read_time = max(1, len(content.split()) // 200)

    # Set published_at if transitioning to published
    published_at = post.get("published_at")
    if status == "published" and not published_at:
        published_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    execute(
        """UPDATE blog_posts SET
           title = ?, slug = ?, content = ?, excerpt = ?,
           meta_title = ?, meta_description = ?, og_image = ?,
           featured_image = ?, category_id = ?, tags = ?,
           status = ?, author = ?, read_time = ?, keyword_target = ?,
           published_at = ?, updated_at = ?
           WHERE id = ?""",
        (title, slug, content, excerpt,
         meta_title, meta_description, og_image,
         featured_image, category_id, tags,
         status, author, read_time, keyword_target,
         published_at, now, post_id),
    )
    return jsonify({"ok": True})


@blog_bp.route("/admin/api/blog/posts/<int:post_id>", methods=["DELETE"])
def admin_delete_post(post_id):
    """Delete a blog post."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 401
    execute("DELETE FROM blog_posts WHERE id = ?", (post_id,))
    return jsonify({"ok": True})


@blog_bp.route("/admin/api/blog/generate", methods=["POST"])
def admin_generate_post():
    """AI-generate a blog post draft."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    topic = (data.get("topic") or "").strip()
    target_keyword = (data.get("target_keyword") or "").strip()

    if not topic:
        return jsonify({"ok": False, "error": "Topic is required."}), 400

    # Get existing published posts for internal linking context
    existing = fetchall(
        "SELECT title, slug FROM blog_posts WHERE status = 'published' ORDER BY published_at DESC LIMIT 50"
    )

    from modules.blog_ai import generate_blog_post
    result = generate_blog_post(topic, target_keyword, existing_posts=existing)

    # Auto-generate featured image
    try:
        from modules.blog_image import generate_blog_image
        img_path = generate_blog_image(result.get("title", topic),
                                       result.get("slug", ""),
                                       keyword=target_keyword)
        result["featured_image"] = img_path
        result["og_image"] = img_path
    except Exception:
        pass

    return jsonify({"ok": True, **result})


@blog_bp.route("/admin/api/blog/newsletter", methods=["POST"])
def admin_newsletter_rewrite():
    """Rewrite a blog post into newsletter format for Beehiiv."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    post_id = data.get("post_id")
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()

    # If post_id provided, load from DB
    if post_id and not content:
        post = fetchone("SELECT title, content FROM blog_posts WHERE id = ?", (post_id,))
        if not post:
            return jsonify({"ok": False, "error": "Post not found."}), 404
        title = title or post["title"]
        content = post["content"]

    if not content:
        return jsonify({"ok": False, "error": "Content is required."}), 400

    from modules.blog_ai import rewrite_for_newsletter
    result = rewrite_for_newsletter(title, content)
    return jsonify({"ok": True, **result})


# ── Category endpoints ───────────────────────────────────

@blog_bp.route("/admin/api/blog/categories", methods=["GET"])
def admin_list_categories():
    """List all blog categories."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 401
    categories = fetchall("SELECT * FROM blog_categories ORDER BY name")
    return jsonify({"ok": True, "categories": categories})


@blog_bp.route("/admin/api/blog/categories", methods=["POST"])
def admin_create_category():
    """Create a new blog category."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name is required."}), 400

    slug = _slugify(name)
    try:
        cur = execute(
            "INSERT INTO blog_categories (name, slug) VALUES (?, ?)",
            (name, slug),
        )
    except Exception:
        return jsonify({"ok": False, "error": "Category already exists."}), 409
    return jsonify({"ok": True, "id": cur.lastrowid, "slug": slug}), 201


@blog_bp.route("/admin/api/blog/categories/<int:cat_id>", methods=["DELETE"])
def admin_delete_category(cat_id):
    """Delete a blog category."""
    if not _is_admin():
        return jsonify({"error": "Unauthorized"}), 401
    execute("DELETE FROM blog_categories WHERE id = ?", (cat_id,))
    return jsonify({"ok": True})


# ── Helpers ──────────────────────────────────────────────

def _slugify(text):
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def redirect_admin_login():
    """Redirect to admin login page."""
    from flask import redirect
    return redirect("/admin/login")
