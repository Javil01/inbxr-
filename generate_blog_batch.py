"""
INBXR — Batch SEO Blog Post Generator
Generates 10 high-intent blog posts using the AI blog writer and saves them to the database.

Usage:
    python generate_blog_batch.py              # Generate all posts (skips existing slugs)
    python generate_blog_batch.py --dry-run    # Preview topics without generating
    python generate_blog_batch.py --start 3    # Start from topic #3 (1-indexed)
"""

import json
import os
import re
import sys
import time

# ── Ensure project root is on path ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Load .env ──
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass  # manual env vars

from modules import database as db
from modules.blog_ai import generate_blog_post_long, BlogAIError

# ── SEO Topic Batch ──
# High-intent keywords that drive organic traffic to INBXR tools.
# Ordered by search volume potential and conversion intent.

TOPICS = [
    {
        "topic": "Why Are My Emails Going to Spam? The Complete Fix Guide for 2026",
        "keyword": "emails going to spam",
        "category": "Deliverability",
    },
    {
        "topic": "How to Set Up SPF, DKIM, and DMARC Records (Step-by-Step)",
        "keyword": "how to set up SPF DKIM DMARC",
        "category": "Authentication",
    },
    {
        "topic": "Email Deliverability Checklist: 15 Things to Check Before You Hit Send",
        "keyword": "email deliverability checklist",
        "category": "Deliverability",
    },
    {
        "topic": "How to Check If Your Domain Is Blacklisted (And How to Get Delisted)",
        "keyword": "email blacklist check",
        "category": "Reputation",
    },
    {
        "topic": "DMARC Explained: What It Is, Why You Need It, and How to Set It Up",
        "keyword": "what is DMARC",
        "category": "Authentication",
    },
    {
        "topic": "Email Warm-Up Guide: How to Build Sender Reputation From Scratch",
        "keyword": "email warm up guide",
        "category": "Reputation",
    },
    {
        "topic": "Subject Lines That Trigger Spam Filters (50+ Words to Avoid)",
        "keyword": "spam trigger words in email",
        "category": "Content",
    },
    {
        "topic": "BIMI Setup Guide: How to Get Your Logo in Gmail and Apple Mail",
        "keyword": "BIMI setup guide",
        "category": "Authentication",
    },
    {
        "topic": "Cold Email Deliverability: How to Send at Scale Without Getting Blacklisted",
        "keyword": "cold email deliverability",
        "category": "Deliverability",
    },
    {
        "topic": "Free Email Deliverability Test: How to Check If Your Emails Reach the Inbox",
        "keyword": "free email deliverability test",
        "category": "Deliverability",
    },
]


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def get_existing_posts():
    """Fetch existing published posts for internal linking context."""
    rows = db.fetchall(
        "SELECT title, slug FROM blog_posts WHERE status='published' "
        "ORDER BY published_at DESC LIMIT 50"
    )
    return [{"title": r["title"], "slug": r["slug"]} for r in rows]


def get_or_create_category(name):
    """Get category ID by name, create if missing."""
    slug = slugify(name)
    row = db.fetchone("SELECT id FROM blog_categories WHERE slug=?", (slug,))
    if row:
        return row["id"]
    cur = db.execute(
        "INSERT INTO blog_categories (name, slug) VALUES (?, ?)",
        (name, slug)
    )
    return cur.lastrowid


def post_exists(slug):
    """Check if a post with this slug (or similar) already exists."""
    row = db.fetchone("SELECT id FROM blog_posts WHERE slug=?", (slug,))
    return row is not None


def save_post(data, category_id):
    """Save generated blog post to database as published."""
    tags_json = json.dumps(data.get("tags", []))
    word_count = len(re.sub(r'<[^>]+>', '', data.get("content", "")).split())
    read_time = max(1, round(word_count / 200))

    cur = db.execute(
        """INSERT INTO blog_posts
           (title, slug, content, excerpt, meta_title, meta_description,
            category_id, tags, status, author, read_time, keyword_target,
            published_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'published', 'INBXR Team', ?, ?,
                   datetime('now'))""",
        (
            data["title"],
            data["slug"],
            data.get("content", ""),
            data.get("excerpt", ""),
            data["title"],
            data.get("meta_description", ""),
            category_id,
            tags_json,
            read_time,
            data.get("keyword_target", ""),
        )
    )
    return cur.lastrowid


def main():
    dry_run = "--dry-run" in sys.argv
    start_idx = 0

    for i, arg in enumerate(sys.argv):
        if arg == "--start" and i + 1 < len(sys.argv):
            start_idx = int(sys.argv[i + 1]) - 1

    # Init DB
    db.init_db()

    if dry_run:
        print("\n=== DRY RUN — Topics to generate ===\n")
        for i, t in enumerate(TOPICS, 1):
            slug = slugify(t["topic"])
            exists = post_exists(slug)
            status = " [EXISTS — will skip]" if exists else ""
            print(f"  {i}. {t['topic']}")
            print(f"     Keyword: {t['keyword']}")
            print(f"     Category: {t['category']}{status}")
            print()
        return

    existing_posts = get_existing_posts()
    generated = 0
    skipped = 0
    failed = 0

    print(f"\n{'='*60}")
    print(f"  INBXR — Batch Blog Generator")
    print(f"  Generating {len(TOPICS) - start_idx} SEO blog posts")
    print(f"{'='*60}\n")

    for i, topic in enumerate(TOPICS[start_idx:], start_idx + 1):
        expected_slug = slugify(topic["topic"])

        if post_exists(expected_slug):
            print(f"[{i}/{len(TOPICS)}] SKIP (exists): {topic['topic'][:60]}...")
            skipped += 1
            continue

        print(f"[{i}/{len(TOPICS)}] Generating: {topic['topic'][:60]}...")
        print(f"           Keyword: {topic['keyword']}")

        try:
            data = generate_blog_post_long(
                topic=topic["topic"],
                target_keyword=topic["keyword"],
                existing_posts=existing_posts,
            )

            # Ensure slug doesn't collide
            if post_exists(data["slug"]):
                data["slug"] = data["slug"] + "-guide"

            category_id = get_or_create_category(topic["category"])
            data["keyword_target"] = topic["keyword"]
            post_id = save_post(data, category_id)

            # Add to existing posts for cross-linking in subsequent posts
            existing_posts.insert(0, {"title": data["title"], "slug": data["slug"]})

            word_count = len(re.sub(r'<[^>]+>', '', data.get("content", "")).split())
            print(f"           OK Saved (ID: {post_id}, {word_count} words, {data.get('elapsed_ms', 0)}ms)")
            print(f"           → /blog/{data['slug']}")
            generated += 1

            # Rate limit: Groq free tier = 30 req/min
            if i < len(TOPICS):
                print(f"           Waiting 8s (rate limit)...")
                time.sleep(8)

        except BlogAIError as e:
            print(f"           FAILED: {e}")
            failed += 1
            time.sleep(5)
        except Exception as e:
            print(f"           ERROR: {e}")
            failed += 1
            time.sleep(5)

    print(f"\n{'='*60}")
    print(f"  Done! Generated: {generated} | Skipped: {skipped} | Failed: {failed}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
