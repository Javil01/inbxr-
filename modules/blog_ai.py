"""
InbXr — AI Blog Writer
Uses Groq API to generate SEO-optimized blog posts about email deliverability.
"""

import json
import logging
import os
import re
import ssl
import time
from http.client import HTTPSConnection

from config.blog_knowledge_base import KNOWLEDGE_BASE

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

    system_msg = f"""You are the writer behind InBoXr — an email deliverability platform.
Your writing voice is modeled after Ian Stanley's style in "Just Fucking Send It" —
direct, story-driven, opinionated, and entertaining.

{KNOWLEDGE_BASE}

CRITICAL VOICE RULES — violating these makes the post unusable:
1. OPEN WITH A SPECIFIC STORY. Not "Picture this" or "Imagine" — drop us into a real
   scene with details. A sender, a number, a moment. Make the reader feel the gut-punch
   before you teach anything.
2. SHORT PARAGRAPHS ONLY. 1-3 sentences max. Single-sentence paragraphs for emphasis.
3. NO GENERIC ADVICE. Every claim needs a specific number, example, or before/after.
4. SECTION HEADERS ARE PUNCHY, NOT ACADEMIC. "Why Nobody Reads Past Your First Email"
   not "The Importance of Welcome Email Optimization."
5. BE OPINIONATED. Take a stance. Challenge something the reader believes.
6. Credit Ian Stanley by name when referencing his named frameworks.
7. End with: "Cheers,<br/>The InBoXer Team" then a PS that callbacks to the opening story.

InbXr tools (link naturally using <a href="/path"> tags, 3-4 per post):
- Email Test (/) — full deliverability checkup
- Sender Check (/sender) — SPF/DKIM/DMARC verification
- Inbox Placement (/placement) — inbox vs spam testing
- Subject Line Scorer (/subject-scorer) — AI subject line analysis
- BIMI Checker (/bimi) — BIMI record validation
- Blacklist Monitor (/blacklist-monitor) — 100+ blocklist check
- Header Analyzer (/header-analyzer) — email header parsing
- Email Verifier (/email-verifier) — address verification
- Warm-up Tracker (/warmup) — warm-up campaign tracking

STRUCTURE:
- 1500-2000 words. Each H2 section 200-300 words minimum.
- 5-7 H2 sections with punchy headers.
- Use the target keyword in the title and first paragraph. After that, use natural
  variations — never repeat the exact keyword more than 3-4 times total.
- FAQ section at the end with 3-5 Q&A pairs (each answer 50+ words).
- HTML only: h2, h3, p, ul, ol, li, strong, em, a tags. No h1, divs, or classes.
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
              max_tokens: int = 8192, json_mode: bool = True,
              temperature: float = 0.7, _retries: int = 3) -> str:
    """Call the Groq/OpenAI-compatible API with automatic retry on rate limits."""
    body_dict = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body_dict["response_format"] = {"type": "json_object"}
    payload = json.dumps(body_dict)

    for attempt in range(_retries):
        ctx = ssl.create_default_context()
        conn = HTTPSConnection(cfg["api_host"], 443, timeout=_TIMEOUT, context=ctx)

        try:
            conn.request("POST", cfg["api_path"], body=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg['api_key']}",
            })
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", errors="replace")

            if resp.status == 429 and attempt < _retries - 1:
                # Rate limited — parse retry delay or use exponential backoff
                wait = 10 * (attempt + 1)
                try:
                    err_data = json.loads(body)
                    err_msg = err_data.get("error", {}).get("message", "")
                    import re as _re
                    m = _re.search(r'try again in (\d+\.?\d*)s', err_msg)
                    if m:
                        wait = max(float(m.group(1)) + 1, wait)
                except Exception:
                    pass
                logger.warning(f"Rate limited (attempt {attempt+1}/{_retries}), waiting {wait:.0f}s")
                time.sleep(wait)
                continue

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

    raise BlogAIError("API rate limit exceeded after all retries")


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
    meta_system = f"""You are an SEO content strategist for InbXr, an email deliverability platform.
Generate metadata for a blog post. Return ONLY valid JSON.

Return a JSON object with exactly these keys:
{{
  "title": "Compelling blog post title (include target keyword naturally — don't force it)",
  "slug": "url-friendly-slug",
  "meta_description": "150-160 character meta description that reads naturally and includes the topic",
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

    # Respect Groq TPM limits between passes
    time.sleep(15)

    # ── Pass 2: Full HTML content ──
    # ── Shared voice context for all content chunks ──
    voice_system = f"""You are the writer behind InBoXr — an email deliverability platform.
Your writing voice is modeled after Ian Stanley's style in "Just Fucking Send It" —
direct, story-driven, opinionated, and entertaining.

{KNOWLEDGE_BASE}

CRITICAL VOICE RULES:
1. SHORT PARAGRAPHS ONLY. 1-3 sentences max. Single-sentence paragraphs for emphasis.
2. NO GENERIC ADVICE. Every claim needs a specific number, example, or before/after.
3. SECTION HEADERS ARE PUNCHY, NOT ACADEMIC.
4. BE OPINIONATED. Take a stance. Challenge something the reader believes.
5. NO corporate jargon — "leverage," "optimize," "utilize," "in today's landscape" are banned.
6. Credit Ian Stanley by name when referencing his frameworks.

InbXr tools (link naturally using <a href="/path"> tags):
- Email Test (/) — full deliverability checkup
- Sender Check (/sender) — SPF/DKIM/DMARC verification
- Inbox Placement (/placement) — inbox vs spam testing
- Subject Line Scorer (/subject-scorer) — AI subject line analysis
- BIMI Checker (/bimi) — BIMI record validation
- Blacklist Monitor (/blacklist-monitor) — 100+ blocklist check
- Header Analyzer (/header-analyzer) — email header parsing
- Email Verifier (/email-verifier) — address verification
- Warm-up Tracker (/warmup) — warm-up campaign tracking
{internal_links_context}

FORMAT: HTML only — h2, h3, p, ul, ol, li, strong, em, a tags. No h1, divs, classes.
Do NOT wrap in markdown code fences. Raw HTML only."""

    # ── Split outline into chunks for multiple API calls ──
    mid = len(outline) // 2
    chunk1_sections = outline[:mid] if outline else []
    chunk2_sections = outline[mid:] if outline else []
    chunk1_text = "\n".join(f"- {s}" for s in chunk1_sections) if chunk1_sections else "Use 3 logical H2 sections"
    chunk2_text = "\n".join(f"- {s}" for s in chunk2_sections) if chunk2_sections else "Use 3 logical H2 sections"

    title = meta.get('title', topic)
    html_chunks = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _extract_html(raw: str) -> tuple:
        """Extract HTML content and usage from API response."""
        data = json.loads(raw)
        choices = data.get("choices", [])
        if not choices:
            raise BlogAIError("No choices in response")
        html = choices[0].get("message", {}).get("content", "")
        if not html:
            raise BlogAIError("Empty content response")
        html = re.sub(r'^```html?\s*', '', html.strip())
        html = re.sub(r'\s*```$', '', html.strip())
        return html, data.get("usage", {})

    # ── Chunk 1: Intro story + first half of sections ──
    chunk1_user = f"""Write the OPENING of a blog post titled: "{title}"
Target keyword: {target_keyword}

Write these parts:
1. An intro (no heading) — 150+ words. Open with a REAL, specific story. Not "Picture this"
   or "Imagine." Drop us into a scene: a person, a number, a gut-punch moment.
2. Then write these sections fully (each 200-300 words with an H2 heading):
{chunk1_text}

Use the target keyword naturally in the intro. After that, vary your language.
Bold key phrases with <strong>. Link to 1-2 InbXr tools where relevant.
Be opinionated. Use specific numbers. Short paragraphs only (1-3 sentences).
Do NOT write a conclusion or sign-off — this is only the first half of the post."""

    try:
        raw1 = _call_api(voice_system, chunk1_user, cfg,
                         max_tokens=4096, json_mode=False, temperature=0.85)
        html1, usage1 = _extract_html(raw1)
        html_chunks.append(html1)
        for k in total_usage:
            total_usage[k] += usage1.get(k, 0)
    except BlogAIError:
        raise
    except Exception as e:
        raise BlogAIError(f"Content chunk 1 failed: {str(e)[:100]}")

    # Respect Groq TPM limits between chunks
    time.sleep(15)

    # ── Chunk 2: Second half of sections ──
    chunk2_user = f"""Continue writing a blog post titled: "{title}"
Target keyword: {target_keyword}

The intro and first sections are already written. Now write these remaining sections
(each 200-300 words with an H2 heading):
{chunk2_text}

Keep the same voice — punchy, opinionated, story-driven. Short paragraphs (1-3 sentences).
Bold key phrases with <strong>. Link to 1-2 InbXr tools where relevant.
Use natural language variations instead of repeating the exact target keyword.
Do NOT repeat the intro or rewrite earlier sections. Just continue from where we left off."""

    try:
        raw2 = _call_api(voice_system, chunk2_user, cfg,
                         max_tokens=4096, json_mode=False, temperature=0.85)
        html2, usage2 = _extract_html(raw2)
        html_chunks.append(html2)
        for k in total_usage:
            total_usage[k] += usage2.get(k, 0)
    except BlogAIError:
        raise
    except Exception as e:
        raise BlogAIError(f"Content chunk 2 failed: {str(e)[:100]}")

    # Respect Groq TPM limits between chunks
    time.sleep(15)

    # ── Chunk 3: Wrap-up + sign-off ──
    chunk3_user = f"""Write the CLOSING of a blog post titled: "{title}"
Target keyword: {target_keyword}

Write these parts:
1. A wrap-up H2 section (150-200 words) — tie the key insights together with conviction.
   No wishy-washy "in conclusion." Be direct and confident.
2. Sign off with: Cheers,<br/>The InBoXer Team
3. A PS paragraph that callbacks to the opening story with a resolution or delivers
   one final sharp insight. Format: <p><strong>PS:</strong> [content]</p>

Keep the same voice. Short paragraphs. Be opinionated. No generic filler."""

    try:
        raw3 = _call_api(voice_system, chunk3_user, cfg,
                         max_tokens=2048, json_mode=False, temperature=0.85)
        html3, usage3 = _extract_html(raw3)
        html_chunks.append(html3)
        for k in total_usage:
            total_usage[k] += usage3.get(k, 0)
    except BlogAIError:
        raise
    except Exception as e:
        raise BlogAIError(f"Content chunk 3 (closing) failed: {str(e)[:100]}")

    # ── Stitch chunks together ──
    html_content = "\n\n".join(html_chunks)
    usage = total_usage

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

InbXr tool links (pick the most relevant 1-2):
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

    system_msg = f"""You are an SEO strategist for InbXr, an email deliverability platform.

Generate ONE new blog topic targeting a high-search-volume keyword in the email marketing/deliverability space.

The topic should be:
- Actionable and specific (not generic)
- Targeting a keyword people actually search for
- Relevant to email deliverability, authentication, inbox placement, sender reputation, list hygiene, engagement optimization, or email marketing
- Use one of these proven headline formulas:
  * Story hook: "I Watched a [Person] [Dramatic Consequence] Because [Root Cause]"
  * Contrarian: Challenge conventional wisdom ("Stop Doing X!", "Why X Is Actually Hurting You")
  * Urgent warning: "[Platform] Just Changed [Thing] — Here's What to Do"
  * Specific results: "How to [Achieve Result] in [Timeframe]"
  * Curiosity gap: Question that the reader MUST answer
  * Named framework: "The [Name] Method to [Achieve Result]"
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
            "topic": "Your Emails Are Going to Spam — Here's Exactly Why (And How to Fix It Today)",
            "keyword": "emails going to spam",
        },
        {
            "topic": "How to Set Up DMARC in 5 Minutes (Before Gmail Blocks You)",
            "keyword": "how to set up dmarc",
        },
        {
            "topic": "The Email Deliverability Checklist That Saved a 200K-Subscriber Newsletter",
            "keyword": "email deliverability checklist",
        },
        {
            "topic": "Stop Guessing: SPF Records Explained So You Actually Get It Right",
            "keyword": "spf record",
        },
        {
            "topic": "DKIM Authentication: The One Setup Mistake That Tanks Your Inbox Rate",
            "keyword": "dkim email authentication",
        },
        {
            "topic": "You Might Be Blacklisted Right Now — Here's How to Find Out",
            "keyword": "email blacklist check",
        },
        {
            "topic": "The Warm-Up Method: How to Build Sender Reputation Without Getting Burned",
            "keyword": "email warm up",
        },
        {
            "topic": "These Subject Line Words Are Sending You Straight to Spam (The Full List)",
            "keyword": "spam trigger words",
        },
        {
            "topic": "BIMI Setup: How to Get Your Logo in Gmail (And Why It Matters More Than You Think)",
            "keyword": "bimi setup",
        },
        {
            "topic": "Cold Email Deliverability Is Broken — Here's What Actually Works in 2026",
            "keyword": "cold email deliverability",
        },
    ]
