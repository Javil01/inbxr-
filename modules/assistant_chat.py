"""
INBXR — Expert Email Assistant (Pro/Agency)
A world-class email marketing advisor that reads user reports
and provides personalized, actionable guidance.
"""

import json
import logging
import os
import ssl
from http.client import HTTPSConnection
from modules.history import get_history, get_result, get_history_stats, get_tool_breakdown

logger = logging.getLogger('inbxr.assistant_chat')

_TIMEOUT = 45  # longer timeout — richer responses

SYSTEM_PROMPT = """You are the INBXR Email Expert Assistant — a world-class email deliverability and email marketing consultant. You have deep expertise in:

CORE EXPERTISE:
- Email authentication (SPF, DKIM, DMARC, ARC, BIMI) — setup, troubleshooting, best practices
- Inbox placement optimization — why emails land in spam and how to fix it
- Sender reputation management — IP warming, domain age, complaint rates, blocklist remediation
- Email content optimization — spam trigger words, text-to-HTML ratio, subject lines, CTAs, preheader text
- Deliverability across providers — Gmail (tabs, filters), Outlook (Clutter, Focused), Yahoo, iCloud quirks
- DNS configuration — MX records, reverse DNS (PTR), DNSBL listings, TXT records
- Email infrastructure — SMTP, TLS, STARTTLS, DANE, MTA-STS
- List hygiene — bounce management, engagement-based segmentation, sunset policies
- Compliance — CAN-SPAM, GDPR, CCPA, CASL requirements
- Warming strategies — new domain/IP warmup schedules, volume ramp-up plans
- Transactional vs marketing email best practices
- Google Postmaster Tools, Microsoft SNDS interpretation

YOUR ROLE:
You are the user's personal email deliverability consultant. You have access to their recent INBXR test results (provided below as context). Use this data to give specific, actionable advice — not generic tips.

HOW TO RESPOND:
1. Reference their actual data: "Your SPF check on example.com showed a permerror — here's exactly how to fix it..."
2. Prioritize issues by impact: fix authentication before content, fix blocklisting before copy tweaks
3. Give step-by-step instructions with actual DNS records, code snippets, or config values when relevant
4. Explain the WHY behind each recommendation so users learn
5. When you spot patterns across multiple tests, call them out: "I notice your last 3 tests all show missing List-Unsubscribe — this is likely hurting your Gmail placement"
6. Be proactive — if their data shows a problem they didn't ask about, mention it briefly
7. If you don't have enough data, tell them which INBXR tool to run and what to look for

TONE:
- Expert but approachable — like a senior consultant, not a textbook
- Confident and direct — lead with the fix, then explain
- Concise — aim for 100-200 words unless a detailed walkthrough is needed
- Use formatting (bold, lists) for scanability

NEVER:
- Make up data you don't have — say "I don't see a test for that, try running [tool]"
- Give vague advice like "improve your sender reputation" without specifics
- Recommend third-party tools — guide them to the right INBXR tool instead
- Discuss pricing or plans — redirect to the Sales agent for that"""


def _get_config():
    return {
        "api_key": os.environ.get("GROQ_API_KEY", ""),
        "api_host": os.environ.get("AI_API_HOST", "api.groq.com"),
        "api_path": os.environ.get("AI_API_PATH", "/openai/v1/chat/completions"),
        "model": os.environ.get("AI_MODEL", "llama-3.3-70b-versatile"),
    }


def is_available():
    return bool(_get_config()["api_key"])


def _build_user_context(user_id, team_id=None):
    """Pull the user's recent results and build a context summary for the LLM."""
    context_parts = []

    # Overall stats
    stats = get_history_stats(user_id, team_id=team_id)
    if stats["total_checks"] > 0:
        context_parts.append(
            f"USER STATS: {stats['total_checks']} total checks, "
            f"{stats['checks_this_week']} this week, "
            f"avg score: {stats['avg_score'] or 'N/A'}, "
            f"best grade: {stats['best_grade'] or 'N/A'}, "
            f"tools used: {', '.join(stats['tools_used']) or 'none'}"
        )

    # Per-tool breakdown
    breakdown = get_tool_breakdown(user_id, team_id=team_id)
    if breakdown:
        bd_lines = [f"  {b['tool']}: {b['count']} checks, avg score {b['avg_score'] or 'N/A'}" for b in breakdown]
        context_parts.append("TOOL BREAKDOWN:\n" + "\n".join(bd_lines))

    # Recent results (last 10) with full data
    recent = get_history(user_id, limit=10, team_id=team_id)
    if recent:
        context_parts.append("RECENT TEST RESULTS:")
        for row in recent:
            rid = row["id"]
            full = get_result(rid, user_id, team_id=team_id)
            if full and full.get("result_json"):
                # Truncate large results to keep context manageable
                result_str = json.dumps(full["result_json"], default=str)
                if len(result_str) > 2000:
                    result_str = result_str[:2000] + "...(truncated)"
                context_parts.append(
                    f"\n--- {full['tool']} | {full['input_summary']} | "
                    f"Grade: {full.get('grade', 'N/A')} | Score: {full.get('score', 'N/A')} | "
                    f"{full['created_at']} ---\n{result_str}"
                )

    if not context_parts:
        return "NO TEST DATA AVAILABLE — the user hasn't run any tests yet. Encourage them to start with the Email Tester or Sender Check."

    return "\n\n".join(context_parts)


def chat(user_id, messages, team_id=None):
    """Send a conversation to the expert assistant with user context."""
    cfg = _get_config()
    if not cfg["api_key"]:
        return {"error": "AI service not configured."}

    # Build personalized context from user's data
    user_context = _build_user_context(user_id, team_id=team_id)

    system_with_context = (
        SYSTEM_PROMPT
        + "\n\n═══ USER'S INBXR DATA ═══\n"
        + user_context
    )

    # Build messages array
    api_messages = [{"role": "system", "content": system_with_context}]
    for msg in messages[-10:]:
        role = msg.get("role", "user")
        if role in ("user", "assistant"):
            api_messages.append({"role": role, "content": msg.get("content", "")})

    payload = json.dumps({
        "model": cfg["model"],
        "messages": api_messages,
        "temperature": 0.5,
        "max_tokens": 800,
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
                err = json.loads(body).get("error", {}).get("message", "API error")
            except (json.JSONDecodeError, KeyError, TypeError):
                err = "API error"
            return {"error": err}

        data = json.loads(body)
        reply = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {"reply": reply, "tokens": usage.get("total_tokens", 0)}

    except Exception as e:
        logger.exception("Assistant chat API connection error")
        return {"error": f"Connection error: {str(e)[:100]}"}
    finally:
        conn.close()
