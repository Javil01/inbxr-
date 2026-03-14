"""
INBXR — AI Blog Writer
Uses Groq API to generate SEO-optimized blog posts about email deliverability.
"""

import json
import logging
import os
import re
import ssl
import time
from http.client import HTTPSConnection

logger = logging.getLogger('inbxr.blog_ai')

# ── Config (read at call time to allow .env loading) ──
def _get_config():
    return {
        "api_key": os.environ.get("GROQ_API_KEY", ""),
        "api_host": os.environ.get("AI_API_HOST", "api.groq.com"),
        "api_path": os.environ.get("AI_API_PATH", "/openai/v1/chat/completions"),
        "model": os.environ.get("AI_MODEL", "llama-3.3-70b-versatile"),
    }

_TIMEOUT = 60


class BlogAIError(Exception):
    pass


def generate_blog_post(topic: str, target_keyword: str,
                       existing_posts: list = None) -> dict:
    """Generate an AI-written blog post.

    Args:
        topic: The blog post topic/title idea
        target_keyword: Primary SEO keyword to target
        existing_posts: Optional list of dicts with 'title' and 'slug' for internal linking

    Returns dict with title, slug, meta_description, excerpt, content,
    tags, and faq.
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        raise BlogAIError("AI blog writer not available — GROQ_API_KEY not configured")

    internal_links_context = ""
    if existing_posts:
        links = "\n".join(f"- \"{p['title']}\" → /blog/{p['slug']}"
                          for p in existing_posts[:10])
        internal_links_context = f"\n\nExisting blog posts you can link to internally:\n{links}"

    system_msg = f"""You are an expert content writer for INBXR, an email deliverability platform.

INBXR offers these tools (use their URLs when relevant):
- Email Test (/) — send a real email, get a full checkup
- Sender Check (/sender) — verify domain authentication
- Inbox Placement (/placement) — test where emails land
- Subject Line Scorer (/subject-scorer) — AI subject line analysis
- DNS Generator (/dns-generator) — generate SPF/DKIM/DMARC records
- BIMI Checker (/bimi) — validate BIMI setup
- Blacklist Monitor (/blacklist-monitor) — check 100+ blocklists
- Header Analyzer (/header-analyzer) — parse email headers
- Domain Health (/domain-health) — full domain health check
- Email Verifier (/email-verifier) — verify email addresses
- Warm-up Tracker (/warmup) — track domain warmup
- Full Audit (/full-audit) — complete deliverability audit

Writing instructions:
- Write in plain English, no jargon or marketing fluff
- 1500-2000 words
- Structure: H1 title, intro paragraph with target keyword, H2/H3 sections, conclusion
- Formula: Problem → Why it happens → How to fix → CTA to relevant tool
- Insert [CTA:tool-path] markers (e.g. [CTA:/dns-generator]) where a call-to-action to a relevant INBXR tool makes sense
- Target keyword in title, first paragraph, one H2, and naturally 1-2% throughout
- Include an FAQ section at the end with 3-5 questions and answers
- Generate HTML output (h2, h3, p, ul, li, strong, a tags — no h1, the title is separate)
{internal_links_context}

IMPORTANT: Return ONLY valid JSON. No markdown, no code fences, no explanation outside the JSON.

Return a JSON object with exactly these keys:
{{
  "title": "Blog post title (include target keyword)",
  "slug": "url-friendly-slug",
  "meta_description": "150-160 character meta description with target keyword",
  "excerpt": "200 character excerpt for listing pages",
  "content": "Full HTML content of the blog post (h2, h3, p, ul, li, strong, a tags)",
  "tags": ["tag1", "tag2", "tag3"],
  "faq": [{{"q": "Question?", "a": "Answer."}}]
}}"""

    user_msg = f"Write a blog post about: {topic}\nTarget keyword: {target_keyword}"

    start = time.time()
    try:
        raw = _call_api(system_msg, user_msg, cfg)
        parsed = _parse_response(raw)
        parsed["elapsed_ms"] = round((time.time() - start) * 1000)
        parsed["model"] = cfg["model"]
        return parsed
    except BlogAIError:
        raise
    except Exception as e:
        logger.exception("Blog generation failed")
        raise BlogAIError(f"Blog generation failed: {str(e)[:100]}")


def _call_api(system_msg: str, user_msg: str, cfg: dict) -> str:
    """Call the Groq/OpenAI-compatible API."""
    payload = json.dumps({
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    })

    ctx = ssl.create_default_context()
    conn = HTTPSConnection(cfg["api_host"], 443, timeout=_TIMEOUT, context=ctx)

    try:
        conn.request("POST", cfg["api_path"], body=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        })
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")

        if resp.status != 200:
            try:
                err_data = json.loads(body)
                err_msg = err_data.get("error", {}).get("message", body[:200])
            except (json.JSONDecodeError, KeyError, TypeError):
                err_msg = body[:200]
            raise BlogAIError(f"API returned {resp.status}: {err_msg}")

        return body
    finally:
        conn.close()


def _parse_response(raw: str) -> dict:
    """Parse the API response and extract the blog post data."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise BlogAIError("Invalid JSON response from API")

    choices = data.get("choices", [])
    if not choices:
        raise BlogAIError("No choices in API response")

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise BlogAIError("Empty content in API response")

    # Parse the JSON content
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from the content (in case of markdown wrapping)
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                result = json.loads(json_match.group())
            except json.JSONDecodeError:
                raise BlogAIError("Could not parse blog JSON from API response")
        else:
            raise BlogAIError("No JSON found in API response")

    # Validate and set defaults for expected keys
    if "title" not in result or not result["title"]:
        raise BlogAIError("API response missing 'title'")

    result.setdefault("slug", re.sub(r'[^a-z0-9]+', '-',
                                     result["title"].lower()).strip('-'))
    result.setdefault("meta_description", "")
    result.setdefault("excerpt", "")
    result.setdefault("content", "")
    result.setdefault("tags", [])
    result.setdefault("faq", [])

    # Ensure lists are actually lists
    if isinstance(result["tags"], str):
        result["tags"] = [result["tags"]]
    if isinstance(result["faq"], str):
        result["faq"] = []

    # Token usage
    usage = data.get("usage", {})
    result["usage"] = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }

    return result


def suggest_topics() -> list:
    """Return a list of 10 high-potential blog topics for email deliverability."""
    return [
        {
            "topic": "Why Are My Emails Going to Spam? (Complete Fix Guide)",
            "keyword": "emails going to spam",
        },
        {
            "topic": "How to Set Up DMARC in 5 Minutes",
            "keyword": "how to set up dmarc",
        },
        {
            "topic": "Email Deliverability Checklist for 2026",
            "keyword": "email deliverability checklist",
        },
        {
            "topic": "SPF Record: What It Is and How to Create One",
            "keyword": "spf record",
        },
        {
            "topic": "DKIM Explained: How to Authenticate Your Emails",
            "keyword": "dkim email authentication",
        },
        {
            "topic": "How to Check If Your Email Is Blacklisted",
            "keyword": "email blacklist check",
        },
        {
            "topic": "Email Warm-Up Guide: How to Build Sender Reputation",
            "keyword": "email warm up",
        },
        {
            "topic": "Subject Lines That Trigger Spam Filters (And What to Use Instead)",
            "keyword": "spam trigger words",
        },
        {
            "topic": "BIMI Setup Guide: Get Your Logo in Gmail",
            "keyword": "bimi setup",
        },
        {
            "topic": "Cold Email Deliverability: How to Stay Out of Spam",
            "keyword": "cold email deliverability",
        },
    ]
