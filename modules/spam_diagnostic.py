"""
InbXr — "Why Am I in Spam?" Unified Diagnostic
──────────────────────────────────────────────
Takes a user's email (domain + optional subject/body) and returns the
3 most likely reasons they're landing in spam, ranked by impact.

This is a thin orchestrator. The actual analysis is done by existing
modules (ReputationChecker, SpamAnalyzer) that are already battle-tested
against thousands of real checks. The diagnostic's job is to run them in
parallel, merge their findings into one list, rank by severity, and
return the top 3 with actionable fix instructions.

Call sites:
- /why-am-i-in-spam public page (primary)
- Cold outreach SEO capture (long-tail query intent)
- Agent-driven support chats (future)

Usage:
    from modules.spam_diagnostic import run_diagnostic
    result = run_diagnostic(
        domain="example.com",
        subject="Your quarterly update",
        body="Hi there, ..."
    )
    # result = {
    #     "verdict": "high_risk" | "moderate_risk" | "low_risk",
    #     "top_reasons": [{rank, title, severity, evidence, fix}, ...],
    #     "categories_checked": ["authentication", "reputation", "content"],
    #     "domain": "example.com",
    #     "subject_provided": True,
    #     "body_provided": True,
    # }
"""

import logging

logger = logging.getLogger(__name__)


# Severity weights used to rank merged findings. Higher = worse.
_SEVERITY_WEIGHT = {
    "critical": 100,
    "high": 70,
    "medium": 40,
    "low": 15,
    "warning": 25,
    "info": 5,
}

# Map of source category → human label for the final output
_CATEGORY_LABELS = {
    "Authentication": "Authentication",
    "Blocklist": "Sender Reputation",
    "Subject Line": "Subject Line",
    "Subject Line Signals": "Subject Line",
    "Body Copy": "Email Body",
    "Body Copy Signals": "Email Body",
    "Link & CTA Signals": "Links &amp; CTAs",
    "Structure & Compliance": "Structure &amp; Compliance",
    "Sender Context": "Sender Setup",
    "DNS": "DNS Setup",
    "PTR": "DNS Setup",
    "FCrDNS": "DNS Setup",
    "Domain Setup": "Domain Setup",
}


def _severity_weight(sev):
    """Normalize a severity string to a numeric weight."""
    return _SEVERITY_WEIGHT.get((sev or "").lower(), 10)


def _run_reputation_check(domain):
    """Run the ReputationChecker against a domain. Returns flags in a
    normalized shape: [{severity, category, item, recommendation}, ...].
    Silently returns an empty list on failure so a broken check never
    blocks the rest of the diagnostic."""
    try:
        from modules.reputation_checker import ReputationChecker
        rc = ReputationChecker(domain=domain)
        result = rc.analyze()
    except Exception:
        logger.exception("[SPAM_DIAGNOSTIC] reputation check failed for %s", domain)
        return [], None

    # ReputationChecker populates ._flags internally but .analyze() may
    # not always expose them — pull from the object after analysis.
    flags = []
    try:
        raw_flags = getattr(rc, "_flags", []) or []
        for f in raw_flags:
            flags.append({
                "severity": f.get("severity", "medium"),
                "category": f.get("category", "Reputation"),
                "item": f.get("item", ""),
                "recommendation": f.get("recommendation", ""),
                "source": "reputation",
            })
    except Exception:
        logger.exception("[SPAM_DIAGNOSTIC] failed to extract reputation flags")

    # Also pull structured auth failures from the result payload so we
    # don't depend solely on flags (the auth section exposes its own).
    auth_data = (result or {}).get("auth", {}) or {}
    for cat in auth_data.get("categories", []) or []:
        status = cat.get("status")
        label = cat.get("label", "Auth")
        if status in ("missing", "fail"):
            flags.append({
                "severity": "high" if label in ("SPF", "DKIM", "DMARC") else "medium",
                "category": "Authentication",
                "item": f"{label} is {status}",
                "recommendation": cat.get("detail")
                    or f"Add or fix your {label} record. This is a baseline requirement for Gmail, Yahoo, and Microsoft.",
                "source": "reputation",
            })
        elif status == "warning":
            flags.append({
                "severity": "medium",
                "category": "Authentication",
                "item": f"{label}: {cat.get('detail', 'configuration warning')}",
                "recommendation": cat.get("detail") or f"Review your {label} setup.",
                "source": "reputation",
            })

    return flags, result


def _run_content_check(subject, body, sender_email=""):
    """Run the SpamAnalyzer against subject + body. Returns flags in the
    same normalized shape as _run_reputation_check. Returns an empty list
    if neither subject nor body is provided."""
    if not subject and not body:
        return [], None

    try:
        from modules.spam_analyzer import SpamAnalyzer
        analyzer = SpamAnalyzer(
            subject=subject or "",
            preheader="",
            body=body or "",
            sender_email=sender_email,
            cta_urls=[],
            cta_texts=[],
        )
        result = analyzer.analyze()
    except Exception:
        logger.exception("[SPAM_DIAGNOSTIC] content check failed")
        return [], None

    flags = []
    for rec in (result.get("top_recommendations") or []):
        flags.append({
            "severity": rec.get("severity", "medium"),
            "category": rec.get("category", "Content"),
            "item": rec.get("item", ""),
            "recommendation": rec.get("recommendation", ""),
            "source": "content",
        })

    return flags, result


def _dedupe_and_rank(flags):
    """Remove duplicate findings and rank by severity weight. Two flags
    are considered duplicates if their item text matches after normalizing
    whitespace and case. First occurrence wins."""
    seen = set()
    unique = []
    for f in flags:
        key = (f.get("item") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(f)

    unique.sort(key=lambda x: _severity_weight(x.get("severity")), reverse=True)
    return unique


def _verdict_for(ranked_flags):
    """Compute an overall verdict from the set of ranked flags."""
    if not ranked_flags:
        return {
            "code": "low_risk",
            "label": "Likely inboxing",
            "summary": "No major issues found. Your email should reach the inbox for most recipients.",
        }

    top_severity = ranked_flags[0].get("severity", "").lower()
    high_count = sum(1 for f in ranked_flags if f.get("severity", "").lower() in ("critical", "high"))

    if top_severity in ("critical",) or high_count >= 3:
        return {
            "code": "high_risk",
            "label": "High spam risk",
            "summary": "Multiple critical issues detected. Your email is likely being filtered to spam or rejected outright.",
        }
    if top_severity == "high" or high_count >= 1:
        return {
            "code": "moderate_risk",
            "label": "Moderate spam risk",
            "summary": "Real signals are pushing this email toward spam folders. Fix the top issues below to recover inbox placement.",
        }
    return {
        "code": "low_risk",
        "label": "Mostly inboxing, one or two signals to watch",
        "summary": "Your setup is mostly fine but a few minor issues could impact edge cases. Address them to maximize deliverability.",
    }


def _format_reason(rank, flag):
    """Shape a single top-3 finding into the structure the UI will render."""
    category = flag.get("category", "")
    category_label = _CATEGORY_LABELS.get(category, category or "Issue")
    return {
        "rank": rank,
        "title": flag.get("item", "").strip() or category_label,
        "severity": flag.get("severity", "medium").lower(),
        "category": category_label,
        "evidence": flag.get("item", "").strip(),
        "fix": flag.get("recommendation", "").strip() or "Review and address this issue in your sending configuration.",
        "source": flag.get("source", "diagnostic"),
    }


def run_diagnostic(domain=None, subject=None, body=None, sender_email=""):
    """Main entry point. Runs reputation + content checks, merges findings,
    returns the top 3 ranked reasons plus a verdict and metadata.

    At minimum one of (domain, subject, body) must be provided. If only
    subject/body is given we still return content findings but the
    verdict will be caveated.
    """
    domain = (domain or "").strip().lower()
    subject = (subject or "").strip()
    body = (body or "").strip()

    if not domain and not subject and not body:
        return {
            "error": "no_input",
            "message": "Provide at least a sending domain, or a subject line and body to analyze.",
        }

    all_flags = []
    rep_result = None
    content_result = None
    categories_checked = []

    if domain:
        rep_flags, rep_result = _run_reputation_check(domain)
        all_flags.extend(rep_flags)
        categories_checked.append("authentication")
        categories_checked.append("reputation")

    if subject or body:
        content_flags, content_result = _run_content_check(subject, body, sender_email)
        all_flags.extend(content_flags)
        categories_checked.append("content")

    ranked = _dedupe_and_rank(all_flags)
    verdict = _verdict_for(ranked)
    top_3 = [_format_reason(i + 1, f) for i, f in enumerate(ranked[:3])]

    return {
        "ok": True,
        "verdict": verdict,
        "top_reasons": top_3,
        "total_findings": len(ranked),
        "categories_checked": sorted(set(categories_checked)),
        "domain": domain or None,
        "subject_provided": bool(subject),
        "body_provided": bool(body),
        # Expose the underlying scores so the template can show detail
        "auth_score": (rep_result or {}).get("auth", {}).get("score") if rep_result else None,
        "reputation_score": (rep_result or {}).get("reputation", {}).get("score") if rep_result else None,
        "content_score": (content_result or {}).get("score") if content_result else None,
        "content_label": (content_result or {}).get("label") if content_result else None,
    }
