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

    system_msg = f"""You are the writer behind InBoXr — an email deliverability platform and newsletter read by email marketers.

VOICE & STYLE (match this exactly):
- Open with a gut-punch hook. Drop the reader into a pain point or story immediately. No "Welcome" or "In this post." Start with tension.
- Ultra-short paragraphs. 1-3 sentences max. Tons of whitespace. Every paragraph earns its place.
- Use "you" constantly. Make it personal and conversational — like talking to a smart friend over coffee.
- Confident, slightly edgy, helpful. You tell hard truths. ("Here's the hard truth most marketers don't want to admit:")
- Bold claims backed by specifics. Use real numbers, percentages, and examples. ("Emails with a single CTA increase clicks by over 300%.")
- No corporate speak. No filler. No "In today's digital landscape" garbage. Every sentence must pull the reader forward.
- Use <strong> tags for emphasis on key phrases — like highlighting with a marker.
- Formula: Hook (pain point) → Why it matters → The fix (actionable steps) → Wrap-up with INBXR tool CTA
- Section headers should be bold and punchy, not generic. ("The 4 Key Factors That Determine If You Get Opened" not "Factors Affecting Open Rates")
- End with a confident wrap-up and sign off: "Cheers,<br/>The InBoXer Team"

INBXR tools (link using standard <a href="/path"> tags):
- Email Test (/) — send a real email, get a full deliverability checkup
- Sender Check (/sender) — verify SPF/DKIM/DMARC, generate DNS records, audit domain health
- Inbox Placement (/placement) — test where emails actually land (inbox vs spam)
- Subject Line Scorer (/subject-scorer) — AI subject line analysis across 7 dimensions
- BIMI Checker (/bimi) — validate BIMI record, SVG logo, and VMC certificate
- Blacklist Monitor (/blacklist-monitor) — check 100+ blocklists for your domain/IP
- Header Analyzer (/header-analyzer) — parse raw email headers for auth verdicts and routing
- Email Verifier (/email-verifier) — verify email addresses before sending
- Warm-up Tracker (/warmup) — track IP/domain warm-up campaigns

STRUCTURE:
- CRITICAL: The post MUST be 1500-2000 words. Each H2 section 200-300 words minimum.
- Start with a hook/intro (no heading) — 100+ words, drop reader into the problem
- 5-7 H2 sections with punchy headers, detailed actionable content
- Link to 3+ relevant INBXR tools using standard HTML anchor tags. Do NOT use [CTA:] markers.
- Target keyword in title, first paragraph, one H2, and naturally throughout
- FAQ section at the end with 3-5 Q&A pairs (each answer 50+ words)
- HTML output only (h2, h3, p, ul, ol, li, strong, em, a tags — no h1)
- Include real examples, specific stats, and step-by-step instructions
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


def _call_api(system_msg: str, user_msg: str, cfg: dict,
              max_tokens: int = 8192, json_mode: bool = True) -> str:
    """Call the Groq/OpenAI-compatible API."""
    body_dict = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body_dict["response_format"] = {"type": "json_object"}
    payload = json.dumps(body_dict)

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


def generate_blog_post_long(topic: str, target_keyword: str,
                            existing_posts: list = None) -> dict:
    """Two-pass blog generation for longer posts (1200+ words).

    Pass 1: Generate metadata (title, slug, meta, tags, FAQ) as JSON.
    Pass 2: Generate full HTML content without JSON constraints for longer output.
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        raise BlogAIError("AI blog writer not available — GROQ_API_KEY not configured")

    internal_links_context = ""
    if existing_posts:
        links = "\n".join(f"- \"{p['title']}\" -> /blog/{p['slug']}"
                          for p in existing_posts[:10])
        internal_links_context = f"\n\nExisting blog posts you can link to internally:\n{links}"

    # ── Pass 1: Metadata ──
    meta_system = f"""You are an SEO content strategist for INBXR, an email deliverability platform.
Generate metadata for a blog post. Return ONLY valid JSON.

Return a JSON object with exactly these keys:
{{
  "title": "SEO-optimized blog post title with target keyword",
  "slug": "url-friendly-slug-with-keyword",
  "meta_description": "150-160 character meta description with target keyword",
  "excerpt": "200 character excerpt for listing pages",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "faq": [
    {{"q": "Detailed question about the topic?", "a": "Comprehensive 50-80 word answer with actionable advice."}},
    {{"q": "Another question?", "a": "Another detailed answer."}},
    {{"q": "Third question?", "a": "Third detailed answer."}},
    {{"q": "Fourth question?", "a": "Fourth detailed answer."}}
  ],
  "outline": ["H2 Section 1 Title", "H2 Section 2 Title", "H2 Section 3 Title", "H2 Section 4 Title", "H2 Section 5 Title", "H2 Section 6 Title"]
}}"""

    meta_user = f"Topic: {topic}\nTarget keyword: {target_keyword}"

    start = time.time()
    try:
        raw_meta = _call_api(meta_system, meta_user, cfg, max_tokens=2048)
        meta = _parse_response(raw_meta)
    except Exception as e:
        raise BlogAIError(f"Metadata generation failed: {str(e)[:100]}")

    outline = meta.get("outline", [])
    outline_text = "\n".join(f"- {s}" for s in outline) if outline else "Use 6 logical H2 sections"

    # ── Pass 2: Full HTML content ──
    content_system = f"""You are the writer behind InBoXr — an email deliverability platform and newsletter.
Write a COMPLETE, LONG blog post in HTML. This is the FULL article — write every section in detail.

VOICE & STYLE (match this exactly):
- Open with a gut-punch hook. Drop the reader right into the pain point. No preamble, no "In this article."
- Ultra-short paragraphs. 1-3 sentences max. Tons of whitespace between ideas.
- Use "you" constantly. Conversational, like talking to a smart friend.
- Confident, slightly edgy, helpful. Tell hard truths. Use phrases like "Here's the hard truth:", "Let's break it down.", "And that's the most common blind spot."
- Bold key phrases with <strong> tags for emphasis.
- Include real numbers, stats, and specific examples — not generic advice.
- Section headers should be punchy and specific, not academic. Good: "Why No One's Opening Your Emails". Bad: "Understanding Email Open Rates".
- End sections with a forward-looking hook that pulls into the next section.
- Wrap up with a confident conclusion and "Cheers,<br/>The InBoXer Team"

INBXR tools (link using standard <a href="/path"> tags):
- Email Test (/) — send a real email, get a full deliverability checkup
- Sender Check (/sender) — verify SPF/DKIM/DMARC, generate DNS records, audit domain
- Inbox Placement (/placement) — test inbox vs spam landing
- Subject Line Scorer (/subject-scorer) — AI subject line analysis
- BIMI Checker (/bimi) — validate BIMI record and VMC
- Blacklist Monitor (/blacklist-monitor) — check 100+ blocklists
- Header Analyzer (/header-analyzer) — parse raw email headers
- Email Verifier (/email-verifier) — verify email addresses
- Warm-up Tracker (/warmup) — track warm-up campaigns
{internal_links_context}

REQUIREMENTS:
- Output ONLY HTML tags: h2, h3, p, ul, ol, li, strong, em, a. No h1, no divs, no classes.
- Write 1500-2000 words MINIMUM. Each H2 section must be 200+ words.
- Start with a hook/intro (no heading) — drop the reader into the problem immediately. 100+ words.
- Include 6+ H2 sections with detailed, actionable content.
- Link to 3-4 relevant INBXR tools using standard HTML anchor tags. Do NOT use [CTA:] markers.
- End with a wrap-up H2 section.
- Target keyword "{target_keyword}" in the intro and at least 2 H2 headings.
- Do NOT wrap in markdown code fences. Output raw HTML only."""

    content_user = f"""Write the full blog post for: "{meta.get('title', topic)}"
Target keyword: {target_keyword}

Follow this outline:
{outline_text}

IMPORTANT: 1500-2000 words minimum. Write in the InBoXr voice — punchy, direct, conversational. Short paragraphs. Bold key phrases. Real examples and stats. Drop the reader into the problem from line one."""

    try:
        raw_content = _call_api(content_system, content_user, cfg,
                                max_tokens=8192, json_mode=False)
        # Extract content from non-JSON response
        data = json.loads(raw_content)
        choices = data.get("choices", [])
        if not choices:
            raise BlogAIError("No choices in content response")
        html_content = choices[0].get("message", {}).get("content", "")
        if not html_content:
            raise BlogAIError("Empty content response")

        # Clean up any markdown code fences
        html_content = re.sub(r'^```html?\s*', '', html_content.strip())
        html_content = re.sub(r'\s*```$', '', html_content.strip())

        # Token usage from content pass
        usage = data.get("usage", {})
    except BlogAIError:
        raise
    except Exception as e:
        raise BlogAIError(f"Content generation failed: {str(e)[:100]}")

    result = {
        "title": meta.get("title", topic),
        "slug": meta.get("slug", re.sub(r'[^a-z0-9]+', '-', topic.lower()).strip('-')),
        "meta_description": meta.get("meta_description", ""),
        "excerpt": meta.get("excerpt", ""),
        "content": html_content,
        "tags": meta.get("tags", []),
        "faq": meta.get("faq", []),
        "elapsed_ms": round((time.time() - start) * 1000),
        "model": cfg["model"],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }
    return result


def rewrite_for_newsletter(title: str, html_content: str) -> dict:
    """Rewrite a blog post into newsletter format matching the InBoXr Beehiiv style.

    Returns dict with subject, preview_text, and body (HTML).
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        raise BlogAIError("AI not available — GROQ_API_KEY not configured")

    # Strip HTML tags to get plain text for the AI
    import re as _re
    plain = _re.sub(r'<[^>]+>', '', html_content)
    plain = _re.sub(r'\s+', ' ', plain).strip()

    system_msg = """You are the writer behind InBoXr, an email marketing newsletter on Beehiiv.

VOICE & STYLE (study these real InBoXr examples and match the tone exactly):

Example openings:
- "You've seen it a thousand times. Another email lands in your inbox. The subject line isn't terrible, so you click. And then it begins: 'Hi [Name], hope you're well...' And your brain whispers: 'Next.'"
- "You're excited about your email. It's packed with great content, new blog posts, an event reminder, a product launch. But when you check your click-through rates? Crickets."
- "They'll never tell you this. But open rates are where most businesses lose the sale. Before the click. Before the conversion. Before your story ever gets heard."
- "Ever wonder why some offers explode while others die a quiet, lonely death in the inbox?"

Style rules:
- Open with a gut-punch hook that drops the reader into a pain point. No "Hi" or "Welcome."
- Ultra-short paragraphs. 1-3 sentences MAX. Tons of whitespace.
- Use "you" constantly. Make it deeply personal and conversational.
- Confident, slightly edgy, helpful. Tell hard truths. Challenge assumptions.
- Bold key phrases with <strong> tags for emphasis.
- Use emoji sparingly as section headers when it fits naturally.
- Formula: Hook → "Let's break it down" → Actionable sections → Wrap-up
- End with: "Cheers<br/><strong>The InBoXer Team</strong>"
- Aim for 500-800 words. Shorter than the blog post but meatier than a quick tip.
- No corporate speak. No filler. Every sentence pulls the reader forward.

INBXR tool links (pick the most relevant 1-2):
- https://www.inbxr.us/ — Email Test
- https://www.inbxr.us/sender — Sender Check (auth, DNS, audit)
- https://www.inbxr.us/placement — Inbox Placement
- https://www.inbxr.us/subject-scorer — Subject Line Scorer
- https://www.inbxr.us/blacklist-monitor — Blacklist Monitor
- https://www.inbxr.us/email-verifier — Email Verifier
- https://www.inbxr.us/bimi — BIMI Checker

Format: simple HTML for Beehiiv (p, strong, a, br, ul, li tags only — no h1/h2/h3, no divs, no classes).

IMPORTANT: Return ONLY valid JSON. No markdown fences, no explanation.

Return a JSON object with exactly these keys:
{
  "subject": "Newsletter subject line — punchy, curiosity-driven, under 50 chars. Examples: 'This kills 93% of email campaigns', 'Where Emails Come To Die', 'This might sting... but it's costing you clicks.'",
  "preview_text": "Preview text that opens a loop — 40-90 chars",
  "body": "Full newsletter HTML body"
}"""

    user_msg = f"Rewrite this blog post for the InBoXr newsletter:\n\nTitle: {title}\n\nContent:\n{plain[:3000]}"

    start = time.time()
    try:
        raw = _call_api(system_msg, user_msg, cfg)
        parsed = _parse_response(raw)
        # Only keep the newsletter fields
        result = {
            "subject": parsed.get("subject", title),
            "preview_text": parsed.get("preview_text", ""),
            "body": parsed.get("body", parsed.get("content", "")),
            "elapsed_ms": round((time.time() - start) * 1000),
        }
        return result
    except BlogAIError:
        raise
    except Exception as e:
        logger.exception("Newsletter rewrite failed")
        raise BlogAIError(f"Newsletter rewrite failed: {str(e)[:100]}")


def generate_topic(existing_titles: list = None) -> dict:
    """Use AI to generate a fresh blog topic that doesn't overlap with existing posts.

    Returns dict with 'topic' and 'keyword' keys.
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        raise BlogAIError("AI not available — GROQ_API_KEY not configured")

    existing_context = ""
    if existing_titles:
        titles = "\n".join(f"- {t}" for t in existing_titles[:30])
        existing_context = f"\n\nExisting blog posts (DO NOT repeat these topics):\n{titles}"

    system_msg = f"""You are an SEO strategist for INBXR, an email deliverability platform.

Generate ONE new blog topic targeting a high-search-volume keyword in the email marketing/deliverability space.

The topic should be:
- Actionable and specific (not generic)
- Targeting a keyword people actually search for
- Relevant to email deliverability, authentication, inbox placement, sender reputation, or email marketing
- Different from any existing posts listed below
{existing_context}

IMPORTANT: Return ONLY valid JSON. No markdown, no explanation.

Return a JSON object with exactly these keys:
{{
  "topic": "Full blog post title idea",
  "keyword": "target SEO keyword (2-4 words)"
}}"""

    raw = _call_api(system_msg, "Generate one new blog topic.", cfg, max_tokens=256)
    # Parse manually since _parse_response expects blog post fields
    try:
        data = json.loads(raw)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        result = json.loads(content)
    except (json.JSONDecodeError, IndexError, KeyError):
        raise BlogAIError("Failed to parse topic response")
    return {
        "topic": result.get("topic", result.get("title", "")),
        "keyword": result.get("keyword", result.get("target_keyword", "")),
    }


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
