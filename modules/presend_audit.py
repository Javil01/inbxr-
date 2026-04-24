"""
InbXr — Pre-Send Audit Checklist
Aggregates results from all analysis modules into a unified pass/fail
checklist with an overall send readiness score.
"""


def generate_audit(analysis_data: dict) -> dict:
    """Generate a pre-send audit checklist from analysis results.

    Args:
        analysis_data: The full /analyze response dict containing:
            spam, copy, readability, link_image, reputation, bimi, dns_suggestions

    Returns a structured audit with categories, checks, overall verdict.
    """
    checks = []
    categories = []

    spam = analysis_data.get("spam", {})
    copy = analysis_data.get("copy", {})
    readability = analysis_data.get("readability", {})
    link_image = analysis_data.get("link_image", {})
    reputation = analysis_data.get("reputation", {})
    bimi = analysis_data.get("bimi", {})
    swipe = analysis_data.get("swipe_risk", {})
    meta = analysis_data.get("meta", {})

    # ══════════════════════════════════════════════════
    #  1. CONTENT & DELIVERABILITY
    # ══════════════════════════════════════════════════
    content_checks = []

    # Spam score
    spam_score = spam.get("score", 0)
    if spam_score is not None:
        if spam_score <= 25:
            content_checks.append(_check("pass", "Spam Risk", f"Score {spam_score}/100 — low risk", "spam"))
        elif spam_score <= 50:
            content_checks.append(_check("warn", "Spam Risk", f"Score {spam_score}/100 — moderate risk, review flagged items", "spam"))
        else:
            content_checks.append(_check("fail", "Spam Risk", f"Score {spam_score}/100 — high risk, fix before sending", "spam"))

    # High-risk spam elements
    high_risk = spam.get("high_risk_elements", [])
    if high_risk:
        content_checks.append(_check("fail", "Spam Triggers", f"{len(high_risk)} high-risk element{'s' if len(high_risk) != 1 else ''} detected", "spam"))
    else:
        content_checks.append(_check("pass", "Spam Triggers", "No high-risk spam triggers found", "spam"))

    # Subject line
    subj_len = meta.get("subject_length", 0)
    if subj_len == 0:
        content_checks.append(_check("fail", "Subject Line", "Missing — every email needs a subject", "content"))
    elif 30 <= subj_len <= 60:
        content_checks.append(_check("pass", "Subject Line", f"{subj_len} chars — ideal length", "content"))
    elif subj_len < 30:
        content_checks.append(_check("warn", "Subject Line", f"{subj_len} chars — could be longer (aim for 30-60)", "content"))
    else:
        content_checks.append(_check("warn", "Subject Line", f"{subj_len} chars — may get truncated on mobile (aim for under 60)", "content"))

    # Body word count
    word_count = meta.get("body_word_count", 0)
    if word_count < 50:
        content_checks.append(_check("warn", "Body Length", f"{word_count} words — very short, may look suspicious to filters", "content"))
    elif word_count > 800:
        content_checks.append(_check("warn", "Body Length", f"{word_count} words — long email, consider trimming for engagement", "content"))
    else:
        content_checks.append(_check("pass", "Body Length", f"{word_count} words — good length", "content"))

    # Swipe-file / originality risk
    if swipe:
        swipe_score = swipe.get("score")
        if swipe_score is not None:
            cliche_count = len(swipe.get("cliche_hits", []))
            snippet_count = len(swipe.get("matched_snippets", []))
            extra = []
            if snippet_count:
                extra.append(f"{snippet_count} template match{'es' if snippet_count != 1 else ''}")
            if cliche_count:
                extra.append(f"{cliche_count} cliché{'s' if cliche_count != 1 else ''}")
            detail_suffix = f" — {', '.join(extra)}" if extra else ""
            if swipe_score <= 25:
                content_checks.append(_check("pass", "Originality", f"Score {swipe_score}/100 — copy reads as original", "swipe"))
            elif swipe_score <= 50:
                content_checks.append(_check("warn", "Originality", f"Swipe risk {swipe_score}/100{detail_suffix}", "swipe"))
            else:
                content_checks.append(_check("fail", "Originality", f"Swipe risk {swipe_score}/100{detail_suffix} — ESPs fingerprint reused copy", "swipe"))

    categories.append({
        "name": "Content & Deliverability",
        "icon": "shield",
        "checks": content_checks,
        "pass_count": sum(1 for c in content_checks if c["status"] == "pass"),
        "total": len(content_checks),
    })

    # ══════════════════════════════════════════════════
    #  2. COPY EFFECTIVENESS
    # ══════════════════════════════════════════════════
    copy_checks = []

    copy_score = copy.get("score", 0)
    if copy_score is not None:
        if copy_score >= 70:
            copy_checks.append(_check("pass", "Copy Score", f"{copy_score}/100 — strong copy", "copy"))
        elif copy_score >= 45:
            copy_checks.append(_check("warn", "Copy Score", f"{copy_score}/100 — room for improvement", "copy"))
        else:
            copy_checks.append(_check("fail", "Copy Score", f"{copy_score}/100 — needs significant work", "copy"))

    # Strengths vs weaknesses
    strengths = copy.get("strengths", [])
    weaknesses = copy.get("weaknesses", [])
    if weaknesses and len(weaknesses) > len(strengths):
        copy_checks.append(_check("warn", "Copy Balance", f"{len(weaknesses)} weaknesses vs {len(strengths)} strengths", "copy"))
    elif strengths:
        copy_checks.append(_check("pass", "Copy Balance", f"{len(strengths)} strengths identified", "copy"))

    categories.append({
        "name": "Copy Effectiveness",
        "icon": "target",
        "checks": copy_checks,
        "pass_count": sum(1 for c in copy_checks if c["status"] == "pass"),
        "total": len(copy_checks),
    })

    # ══════════════════════════════════════════════════
    #  3. READABILITY
    # ══════════════════════════════════════════════════
    read_checks = []

    if readability and readability.get("score") is not None:
        r_score = readability["score"]
        grade = readability.get("grade_level", 0)

        if r_score >= 60:
            read_checks.append(_check("pass", "Readability Score", f"{r_score}/100 — easy to read", "readability"))
        elif r_score >= 45:
            read_checks.append(_check("warn", "Readability Score", f"{r_score}/100 — moderate difficulty", "readability"))
        else:
            read_checks.append(_check("fail", "Readability Score", f"{r_score}/100 — too complex for email", "readability"))

        if grade <= 8:
            read_checks.append(_check("pass", "Grade Level", f"Grade {grade} — accessible to most readers", "readability"))
        elif grade <= 10:
            read_checks.append(_check("warn", "Grade Level", f"Grade {grade} — slightly above ideal (aim for 5-8)", "readability"))
        else:
            read_checks.append(_check("fail", "Grade Level", f"Grade {grade} — too advanced for email (aim for 5-8)", "readability"))

        stats = readability.get("stats", {})
        passive_pct = stats.get("passive_voice_pct", 0)
        if passive_pct > 15:
            read_checks.append(_check("warn", "Passive Voice", f"{passive_pct}% — use more active voice", "readability"))
        else:
            read_checks.append(_check("pass", "Passive Voice", f"{passive_pct}% — good use of active voice", "readability"))

    if read_checks:
        categories.append({
            "name": "Readability",
            "icon": "book",
            "checks": read_checks,
            "pass_count": sum(1 for c in read_checks if c["status"] == "pass"),
            "total": len(read_checks),
        })

    # ══════════════════════════════════════════════════
    #  4. LINKS & IMAGES
    # ══════════════════════════════════════════════════
    li_checks = []

    if link_image:
        li_summary = link_image.get("summary", {})

        # Broken links
        broken = li_summary.get("links_broken", 0)
        if broken > 0:
            li_checks.append(_check("fail", "Broken Links", f"{broken} broken link{'s' if broken != 1 else ''}", "links"))
        else:
            total_links = li_summary.get("links_total", 0)
            if total_links > 0:
                li_checks.append(_check("pass", "Links", f"All {total_links} links working", "links"))

        # Shorteners
        shorteners = li_summary.get("links_shortener", 0)
        if shorteners > 0:
            li_checks.append(_check("fail", "URL Shorteners", f"{shorteners} shortener{'s' if shorteners != 1 else ''} — replace with direct URLs", "links"))

        # HTTP links
        http_links = li_summary.get("links_http", 0)
        if http_links > 0:
            li_checks.append(_check("warn", "HTTPS Links", f"{http_links} link{'s' if http_links != 1 else ''} use HTTP — upgrade to HTTPS", "links"))
        elif li_summary.get("links_total", 0) > 0:
            li_checks.append(_check("pass", "HTTPS Links", "All links use HTTPS", "links"))

        # Broken images
        broken_imgs = li_summary.get("images_broken", 0)
        if broken_imgs > 0:
            li_checks.append(_check("fail", "Broken Images", f"{broken_imgs} broken image{'s' if broken_imgs != 1 else ''}", "images"))
        elif li_summary.get("images_total", 0) > 0:
            li_checks.append(_check("pass", "Images", f"All {li_summary['images_total']} images loading", "images"))

        # Alt text
        no_alt = li_summary.get("images_no_alt", 0)
        if no_alt > 0:
            li_checks.append(_check("warn", "Alt Text", f"{no_alt} image{'s' if no_alt != 1 else ''} missing alt text", "images"))
        elif li_summary.get("images_total", 0) > 0:
            li_checks.append(_check("pass", "Alt Text", "All images have alt text", "images"))

    if li_checks:
        categories.append({
            "name": "Links & Images",
            "icon": "link",
            "checks": li_checks,
            "pass_count": sum(1 for c in li_checks if c["status"] == "pass"),
            "total": len(li_checks),
        })

    # ══════════════════════════════════════════════════
    #  5. SENDER AUTHENTICATION
    # ══════════════════════════════════════════════════
    auth_checks = []

    if reputation:
        auth_data = reputation.get("auth", {})
        auth_cats = auth_data.get("categories", [])

        for cat in auth_cats:
            label = cat.get("label", "")
            status = cat.get("status", "missing")
            score = cat.get("score", 0)
            max_score = cat.get("max", 1)

            if label == "BIMI":
                continue  # handled separately

            if status == "pass":
                auth_checks.append(_check("pass", label, f"Configured ({score}/{max_score})", "auth"))
            elif status == "warning":
                auth_checks.append(_check("warn", label, f"Needs improvement ({score}/{max_score})", "auth"))
            else:
                auth_checks.append(_check("fail", label, f"Missing or failed ({score}/{max_score})", "auth"))

        # Blocklists
        rep_data = reputation.get("reputation", {})
        listed_count = rep_data.get("listed_count", 0)
        if listed_count > 0:
            auth_checks.append(_check("fail", "Blocklists", f"Listed on {listed_count} blocklist{'s' if listed_count != 1 else ''}", "auth"))
        else:
            auth_checks.append(_check("pass", "Blocklists", "Clean — not on any blocklists", "auth"))

    if auth_checks:
        categories.append({
            "name": "Sender Authentication",
            "icon": "lock",
            "checks": auth_checks,
            "pass_count": sum(1 for c in auth_checks if c["status"] == "pass"),
            "total": len(auth_checks),
        })

    # ══════════════════════════════════════════════════
    #  6. BIMI / BRAND
    # ══════════════════════════════════════════════════
    brand_checks = []

    if bimi:
        bimi_status = bimi.get("status", "missing")
        bimi_score = bimi.get("score", 0)

        if bimi_status == "pass":
            brand_checks.append(_check("pass", "BIMI", f"Fully configured ({bimi_score}/100)", "brand"))
        elif bimi_status == "partial":
            brand_checks.append(_check("warn", "BIMI", f"Partially set up ({bimi_score}/100)", "brand"))
        else:
            brand_checks.append(_check("info", "BIMI", "Not configured (optional — displays brand logo in inbox)", "brand"))

    if brand_checks:
        categories.append({
            "name": "Brand Identity",
            "icon": "badge",
            "checks": brand_checks,
            "pass_count": sum(1 for c in brand_checks if c["status"] == "pass"),
            "total": len(brand_checks),
        })

    # ══════════════════════════════════════════════════
    #  OVERALL VERDICT
    # ══════════════════════════════════════════════════
    all_checks = []
    for cat in categories:
        all_checks.extend(cat["checks"])

    total = len(all_checks)
    passes = sum(1 for c in all_checks if c["status"] == "pass")
    warns = sum(1 for c in all_checks if c["status"] == "warn")
    fails = sum(1 for c in all_checks if c["status"] == "fail")
    infos = sum(1 for c in all_checks if c["status"] == "info")

    # Calculate percentage (info items don't count against you)
    scored = total - infos
    pass_pct = round((passes / scored) * 100) if scored > 0 else 100

    if fails == 0 and warns == 0:
        verdict = "ready"
        verdict_label = "Ready to Send"
        verdict_summary = "All checks passed. Your email is ready to go."
        color = "green"
    elif fails == 0 and warns <= 2:
        verdict = "mostly_ready"
        verdict_label = "Mostly Ready"
        verdict_summary = f"{warns} minor issue{'s' if warns != 1 else ''} to consider, but safe to send."
        color = "blue"
    elif fails == 0:
        verdict = "review"
        verdict_label = "Review Recommended"
        verdict_summary = f"{warns} warnings found. Review before sending for best results."
        color = "yellow"
    elif fails <= 2:
        verdict = "fix_needed"
        verdict_label = "Fixes Needed"
        verdict_summary = f"{fails} critical issue{'s' if fails != 1 else ''} to fix before sending."
        color = "orange"
    else:
        verdict = "not_ready"
        verdict_label = "Not Ready"
        verdict_summary = f"{fails} critical issues found. Fix these before sending."
        color = "red"

    return {
        "verdict": verdict,
        "verdict_label": verdict_label,
        "verdict_summary": verdict_summary,
        "color": color,
        "pass_pct": pass_pct,
        "counts": {
            "total": total,
            "pass": passes,
            "warn": warns,
            "fail": fails,
            "info": infos,
        },
        "categories": categories,
    }


def _check(status: str, label: str, detail: str, group: str) -> dict:
    """Create a single audit check item."""
    return {
        "status": status,   # pass | warn | fail | info
        "label": label,
        "detail": detail,
        "group": group,
    }
