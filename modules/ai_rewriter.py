"""
INBXR — AI Full Rewrite Engine
Uses Groq API (or compatible OpenAI-format API) to generate complete
alternative subject lines, body rewrites, and CTAs with tone matching.
"""

import json
import logging
import os
import re
import ssl
import time
from http.client import HTTPSConnection
from html.parser import HTMLParser

logger = logging.getLogger('inbxr.ai_rewriter')

# ── Config (read at call time to allow .env loading) ──
def _get_config():
    return {
        "api_key": os.environ.get("GROQ_API_KEY", ""),
        "api_host": os.environ.get("AI_API_HOST", "api.groq.com"),
        "api_path": os.environ.get("AI_API_PATH", "/openai/v1/chat/completions"),
        "model": os.environ.get("AI_MODEL", "llama-3.3-70b-versatile"),
    }

_TIMEOUT = 30
_MAX_BODY_CHARS = 4000  # truncate body to keep tokens manageable


class AIRewriteError(Exception):
    pass


def is_available() -> bool:
    """Check if AI rewrite is available (API key configured)."""
    return bool(_get_config()["api_key"])


def rewrite_email(subject: str, body: str, industry: str = "General",
                  tone: str = "professional", cta_texts: list = None,
                  issues: list = None) -> dict:
    """Generate AI-powered email rewrites.

    Args:
        subject: Original subject line
        body: Original email body (HTML or plain text)
        industry: Industry context
        tone: Desired tone (professional, friendly, urgent, casual, authoritative)
        cta_texts: Existing CTA button texts
        issues: Issues found by the analyzer (to focus the rewrite)

    Returns dict with subject_alternatives, body_rewrite, cta_alternatives,
    opening_hook, closing_rewrite, and tips.
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        raise AIRewriteError("AI rewrite not available — GROQ_API_KEY not configured")

    # Strip HTML from body for the prompt
    plain_body = _strip_html(body)
    if len(plain_body) > _MAX_BODY_CHARS:
        plain_body = plain_body[:_MAX_BODY_CHARS] + "..."

    # Build issue context
    issue_context = ""
    if issues:
        top_issues = issues[:5]
        issue_context = "\n".join(f"- {i}" for i in top_issues)

    cta_context = ", ".join(cta_texts[:3]) if cta_texts else "none provided"

    prompt = _build_prompt(subject, plain_body, industry, tone, cta_context, issue_context)

    start = time.time()
    try:
        raw = _call_api(prompt)
        parsed = _parse_response(raw)
        parsed["elapsed_ms"] = round((time.time() - start) * 1000)
        parsed["model"] = cfg["model"]
        parsed["tone"] = tone
        return parsed
    except AIRewriteError:
        raise
    except Exception as e:
        raise AIRewriteError(f"AI rewrite failed: {str(e)[:100]}")


def optimize_for_primary(subject: str, body: str) -> dict:
    """Rewrite email specifically to escape Gmail's Promotions tab.

    Returns dict with optimized_subject, optimized_body, changes_made, and tips.
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        raise AIRewriteError("AI rewrite not available — GROQ_API_KEY not configured")

    plain_body = _strip_html(body)
    if len(plain_body) > _MAX_BODY_CHARS:
        plain_body = plain_body[:_MAX_BODY_CHARS] + "..."

    system_msg = """You are an expert at getting emails past Gmail's Promotions tab filter and into the Primary inbox.
You know exactly what triggers Promotions tab classification: heavy HTML, multiple links, images, marketing language, brand-heavy sender names, promotional CTAs, and impersonal tone.
Your job is to rewrite emails so they read like a personal email from a real human — the kind Gmail routes to Primary.

IMPORTANT: Return ONLY valid JSON. No markdown, no code fences."""

    user_msg = f"""Rewrite this email to land in Gmail's PRIMARY tab instead of Promotions.

ORIGINAL SUBJECT: {subject}

ORIGINAL BODY:
{plain_body}

Rules for Primary inbox optimization:
1. Strip all heavy HTML — output should be plain text or minimal formatting
2. Maximum 1 link in the entire email (the most important one)
3. No images at all
4. Write like a real person sending to a friend — use "I", "you", first names
5. Remove ALL marketing buzzwords (exclusive, limited, deal, offer, discount, unbeatable, etc.)
6. No styled buttons — just a plain text link if needed
7. Short paragraphs (1-3 sentences each)
8. Conversational opening (no "Dear valued customer" or brand announcements)
9. Ask a question to encourage replies (Gmail's #1 engagement signal)
10. Keep it under 200 words if possible

Return a JSON object with exactly these keys:
{{
  "optimized_subject": "A rewritten subject line that sounds personal, not promotional (under 50 chars)",
  "optimized_body": "The complete rewritten email body as plain text — conversational, personal, one link max, no marketing language",
  "changes_made": ["List of 4-6 specific changes you made and why each helps escape Promotions"],
  "before_after": [
    {{"before": "original phrase or pattern", "after": "what you changed it to", "reason": "why"}},
    {{"before": "another example", "after": "replacement", "reason": "why"}}
  ],
  "primary_score": 85,
  "tips": ["2-3 additional tips for staying in Primary long-term"]
}}"""

    prompt_json = json.dumps({"system": system_msg, "user": user_msg})

    start = time.time()
    try:
        raw = _call_api(prompt_json)
        parsed = _parse_response_primary(raw)
        parsed["elapsed_ms"] = round((time.time() - start) * 1000)
        parsed["model"] = cfg["model"]
        return parsed
    except AIRewriteError:
        raise
    except Exception as e:
        raise AIRewriteError(f"Primary optimization failed: {str(e)[:100]}")


def _parse_response_primary(raw: str) -> dict:
    """Parse the API response for primary inbox optimization."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise AIRewriteError("Invalid JSON response from API")

    choices = data.get("choices", [])
    if not choices:
        raise AIRewriteError("No choices in API response")

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise AIRewriteError("Empty content in API response")

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                result = json.loads(json_match.group())
            except json.JSONDecodeError:
                raise AIRewriteError("Could not parse optimization JSON")
        else:
            raise AIRewriteError("No JSON found in API response")

    # Ensure expected keys
    for key in ("optimized_subject", "optimized_body"):
        if key not in result:
            result[key] = ""
    for key in ("changes_made", "before_after", "tips"):
        if key not in result or not isinstance(result[key], list):
            result[key] = []
    if "primary_score" not in result:
        result["primary_score"] = 0

    usage = data.get("usage", {})
    result["usage"] = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }

    return result


def _build_prompt(subject: str, body: str, industry: str, tone: str,
                  cta_context: str, issue_context: str) -> str:
    """Build the system + user prompt for the rewrite."""

    tone_desc = {
        "professional": "confident, clear, and professional — like a trusted advisor",
        "friendly": "warm, conversational, and approachable — like a helpful friend",
        "urgent": "direct, time-sensitive, and action-oriented — create genuine urgency without being spammy",
        "casual": "relaxed, personable, and easy-going — like texting a colleague",
        "authoritative": "expert, data-driven, and commanding — establish clear authority",
    }.get(tone, "professional and clear")

    system_msg = """You are an expert email copywriter who specializes in high-converting email marketing.
You write copy that lands in the primary inbox, gets opened, and drives action.
You never use spammy language, excessive punctuation, or ALL CAPS.
Your writing is clean, direct, and persuasive.

IMPORTANT: Return ONLY valid JSON. No markdown, no code fences, no explanation outside the JSON."""

    user_msg = f"""Rewrite this email to improve deliverability, engagement, and conversions.

ORIGINAL SUBJECT: {subject}

ORIGINAL BODY:
{body}

INDUSTRY: {industry}
DESIRED TONE: {tone_desc}
EXISTING CTAs: {cta_context}
{f"ISSUES FOUND BY ANALYZER:{chr(10)}{issue_context}" if issue_context else ""}

Return a JSON object with exactly these keys:
{{
  "subject_alternatives": ["5 alternative subject lines, each under 60 characters, varied approaches (curiosity, benefit, question, personal, urgency)"],
  "opening_hook": "A rewritten opening paragraph (2-3 sentences) that grabs attention immediately",
  "body_rewrite": "A complete rewritten email body (keep the same core message but improve clarity, flow, persuasion, and readability — use short paragraphs, 2-3 sentences each)",
  "closing_rewrite": "A strong closing paragraph with clear next step",
  "cta_alternatives": ["5 CTA button text alternatives that are specific and action-oriented"],
  "preheader_suggestion": "A compelling preheader text (40-80 chars) that complements the best subject line",
  "tips": ["3-5 specific tips explaining what was changed and why"]
}}"""

    return json.dumps({
        "system": system_msg,
        "user": user_msg,
    })


def _call_api(prompt_json: str) -> str:
    """Call the Groq/OpenAI-compatible API."""
    cfg = _get_config()
    prompt = json.loads(prompt_json)

    payload = json.dumps({
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
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
            # Try to extract error message
            try:
                err_data = json.loads(body)
                err_msg = err_data.get("error", {}).get("message", body[:200])
            except (json.JSONDecodeError, KeyError, TypeError):
                err_msg = body[:200]
            raise AIRewriteError(f"API returned {resp.status}: {err_msg}")

        return body
    finally:
        conn.close()


def _parse_response(raw: str) -> dict:
    """Parse the API response and extract the rewrite data."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise AIRewriteError("Invalid JSON response from API")

    # Extract content from OpenAI-format response
    choices = data.get("choices", [])
    if not choices:
        raise AIRewriteError("No choices in API response")

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise AIRewriteError("Empty content in API response")

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
                raise AIRewriteError("Could not parse rewrite JSON from API response")
        else:
            raise AIRewriteError("No JSON found in API response")

    # Validate expected keys
    expected = ["subject_alternatives", "opening_hook", "body_rewrite",
                "closing_rewrite", "cta_alternatives", "tips"]
    for key in expected:
        if key not in result:
            result[key] = [] if key in ("subject_alternatives", "cta_alternatives", "tips") else ""

    # Ensure lists are actually lists
    for key in ("subject_alternatives", "cta_alternatives", "tips"):
        if isinstance(result[key], str):
            result[key] = [result[key]]

    # Token usage
    usage = data.get("usage", {})
    result["usage"] = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }

    return result


# ── HTML stripper ─────────────────────────────────────

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True
        elif tag in ("br", "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        elif tag == "p":
            self.text.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data)


def _strip_html(html: str) -> str:
    """Strip HTML tags and return clean text."""
    stripper = _HTMLStripper()
    try:
        stripper.feed(html)
    except Exception:
        logger.exception("Failed to strip HTML content")
    text = "".join(stripper.text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()
