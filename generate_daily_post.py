"""
InbXr — Daily Blog Post Generator
Generates a fresh blog post using AI and publishes it to the live site via API.

Usage:
    python generate_daily_post.py           # Generate 1 post
    python generate_daily_post.py --count 2 # Generate N posts
"""

import json
import os
import re
import ssl
import sys
import time
from http.client import HTTPSConnection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from modules.blog_ai import generate_blog_post_long, generate_topic, BlogAIError

# ── Config ──
LIVE_HOST = "www.inbxr.us"
BLOG_API_KEY = os.environ.get("BLOG_API_KEY", "")


def _api_post(path, data):
    """POST JSON to the live site's admin API."""
    payload = json.dumps(data)
    ctx = ssl.create_default_context()
    conn = HTTPSConnection(LIVE_HOST, 443, timeout=30, context=ctx)
    try:
        conn.request("POST", path, body=payload, headers={
            "Content-Type": "application/json",
            "X-Blog-Api-Key": BLOG_API_KEY,
        })
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, json.loads(body) if body else {}
    finally:
        conn.close()


def _api_get(path):
    """GET from the live site's admin API."""
    ctx = ssl.create_default_context()
    conn = HTTPSConnection(LIVE_HOST, 443, timeout=30, context=ctx)
    try:
        conn.request("GET", path, headers={
            "X-Blog-Api-Key": BLOG_API_KEY,
        })
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, json.loads(body) if body else {}
    finally:
        conn.close()


def get_existing_posts():
    """Fetch published posts from the live site."""
    status, data = _api_get("/admin/api/blog/posts")
    if status != 200 or not data.get("ok"):
        print(f"  Warning: Could not fetch existing posts ({status})")
        return []
    posts = data.get("posts", [])
    return [{"title": p["title"], "slug": p["slug"]}
            for p in posts if p.get("status") == "published"][:50]


def get_category_id(name):
    """Get category ID from the live site."""
    status, data = _api_get("/admin/api/blog/categories")
    if status != 200:
        return None
    for cat in data.get("categories", []):
        if cat["name"].lower() == name.lower():
            return cat["id"]
    # Create it if missing
    status, data = _api_post("/admin/api/blog/categories", {"name": name})
    if status in (200, 201) and data.get("ok"):
        return data.get("id")
    return None


def publish_post(data, category_id):
    """Publish a generated post to the live site."""
    payload = {
        "title": data["title"],
        "slug": data["slug"],
        "content": data.get("content", ""),
        "excerpt": data.get("excerpt", ""),
        "meta_title": data["title"],
        "meta_description": data.get("meta_description", ""),
        "category_id": category_id,
        "tags": data.get("tags", []),
        "status": "published",
        "author": "InbXr Team",
        "keyword_target": data.get("keyword_target", ""),
    }
    status, resp = _api_post("/admin/api/blog/posts", payload)
    if status in (200, 201) and resp.get("ok"):
        return resp.get("id")
    raise RuntimeError(f"API returned {status}: {resp}")


def generate_one_post(existing_posts):
    """Generate and publish a single fresh blog post."""
    existing_titles = [p["title"] for p in existing_posts]
    print("  Finding fresh topic...")
    topic_data = generate_topic(existing_titles)
    topic = topic_data["topic"]
    keyword = topic_data["keyword"]
    print(f"  Topic: {topic}")
    print(f"  Keyword: {keyword}")

    # Determine category from keyword
    keyword_lower = keyword.lower()
    if any(w in keyword_lower for w in ["spf", "dkim", "dmarc", "bimi", "auth"]):
        category = "Authentication"
    elif any(w in keyword_lower for w in ["blacklist", "reputation", "warm"]):
        category = "Reputation"
    elif any(w in keyword_lower for w in ["subject", "content", "copy", "trigger"]):
        category = "Content"
    else:
        category = "Deliverability"

    print(f"  Category: {category}")
    print("  Generating long-form post (2-pass)...")

    data = generate_blog_post_long(
        topic=topic,
        target_keyword=keyword,
        existing_posts=existing_posts,
    )

    data["keyword_target"] = keyword
    category_id = get_category_id(category)

    print("  Publishing to live site...")
    post_id = publish_post(data, category_id)

    word_count = len(re.sub(r'<[^>]+>', '', data.get("content", "")).split())
    print(f"  Published (ID: {post_id}, {word_count} words)")
    print(f"  -> https://www.inbxr.us/blog/{data['slug']}")

    return {"title": data["title"], "slug": data["slug"]}


def main():
    if not BLOG_API_KEY:
        print("ERROR: BLOG_API_KEY not set in .env")
        sys.exit(1)

    count = 1
    for i, arg in enumerate(sys.argv):
        if arg == "--count" and i + 1 < len(sys.argv):
            count = int(sys.argv[i + 1])

    existing_posts = get_existing_posts()

    print(f"\n{'='*50}")
    print(f"  InbXr — Daily Blog Generator ({count} post(s))")
    print(f"  Target: {LIVE_HOST}")
    print(f"{'='*50}\n")

    generated = 0
    for i in range(count):
        print(f"[{i+1}/{count}] Generating post...")
        try:
            new_post = generate_one_post(existing_posts)
            existing_posts.insert(0, new_post)
            generated += 1
            if i < count - 1:
                print("  Waiting 20s between posts (rate limit)...")
                time.sleep(20)
        except BlogAIError as e:
            print(f"  FAILED: {e}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\n{'='*50}")
    print(f"  Done! Generated: {generated}/{count}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
