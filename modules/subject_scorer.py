"""
InbXr — Subject Line A/B Scorer
Scores multiple subject lines on deliverability + effectiveness dimensions.
Returns ranked results with per-subject breakdowns.
"""

import re
import math

# ── Spam trigger words (subset — high-confidence) ──────
_SPAM_WORDS = {
    "free", "winner", "congratulations", "urgent", "act now",
    "limited time", "buy now", "order now", "click here", "subscribe",
    "unsubscribe", "no obligation", "risk free", "100%", "guarantee",
    "cash", "earn money", "make money", "income", "profit",
    "viagra", "casino", "lottery", "prize", "claim",
    "double your", "triple your", "amazing", "incredible offer",
    "once in a lifetime", "exclusive deal", "apply now", "sign up free",
    "no cost", "no fees", "credit card", "debt", "loan",
    "cheap", "discount", "lowest price", "bargain", "clearance",
}

# ── Power words that boost open rates ──────────────────
_POWER_WORDS = {
    "new", "now", "today", "discover", "secret", "proven",
    "introducing", "finally", "breaking", "announcing",
    "revealed", "insider", "essential", "critical", "important",
    "update", "alert", "quick", "easy", "simple",
    "instant", "unlock", "boost", "transform", "master",
    "ultimate", "complete", "definitive", "exclusive",
}

# ── Emotional triggers ─────────────────────────────────
_EMOTION_WORDS = {
    # Curiosity
    "secret", "hidden", "surprising", "unexpected", "strange",
    "weird", "shocking", "unbelievable", "mystery", "revealed",
    # Urgency
    "now", "today", "hurry", "last chance", "deadline", "expires",
    "ending", "final", "running out", "don't miss",
    # Fear of missing out
    "exclusive", "limited", "only", "few left", "closing",
    "invitation", "selected", "private", "members",
    # Value
    "free", "save", "bonus", "gift", "reward",
}

# ── Personalization tokens ─────────────────────────────
_PERSONALIZATION = [
    r'\{first_?name\}', r'\{name\}', r'\{company\}',
    r'\[\[first_?name\]\]', r'\*\|FNAME\|\*', r'%FIRSTNAME%',
    r'\{city\}', r'\{location\}',
]


def score_subjects(subjects: list, industry: str = "Other") -> dict:
    """Score 1-10 subject lines and return ranked results."""
    results = []

    for subj in subjects[:10]:
        subj = subj.strip()
        if not subj:
            continue
        result = _score_one(subj, industry)
        results.append(result)

    # Rank by total score descending
    results.sort(key=lambda r: r["total_score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1
        if i == 0:
            r["badge"] = "Winner"
        elif i == 1 and len(results) > 2:
            r["badge"] = "Runner-up"
        else:
            r["badge"] = None

    winner = results[0] if results else None

    return {
        "results": results,
        "winner": winner["subject"] if winner else None,
        "winner_score": winner["total_score"] if winner else 0,
        "count": len(results),
    }


def _score_one(subject: str, industry: str) -> dict:
    """Score a single subject line across all dimensions."""
    lower = subject.lower()
    words = re.findall(r'\b\w+\b', lower)
    word_count = len(words)
    char_count = len(subject)

    dimensions = {}

    # 1. LENGTH (0-20)
    length_score = _score_length(char_count)
    dimensions["length"] = {
        "score": length_score,
        "max": 20,
        "label": "Length",
        "detail": f"{char_count} chars — {'optimal (30-55)' if 30 <= char_count <= 55 else 'too short' if char_count < 30 else 'too long (may truncate)'}",
    }

    # 2. SPAM RISK (0-20, inverted — 20 = no spam words)
    spam_found = [w for w in _SPAM_WORDS if w in lower]
    spam_score = max(0, 20 - len(spam_found) * 5)
    dimensions["spam_risk"] = {
        "score": spam_score,
        "max": 20,
        "label": "Spam Safety",
        "detail": f"{len(spam_found)} trigger words found" if spam_found else "Clean — no spam triggers",
        "flags": spam_found[:5],
    }

    # 3. POWER WORDS (0-15)
    power_found = [w for w in _POWER_WORDS if w in lower]
    power_score = min(15, len(power_found) * 5)
    dimensions["power_words"] = {
        "score": power_score,
        "max": 15,
        "label": "Power Words",
        "detail": f"{len(power_found)} power words" if power_found else "No power words — consider adding one",
        "words": power_found[:5],
    }

    # 4. EMOTIONAL PULL (0-15)
    emotion_found = [w for w in _EMOTION_WORDS if w in lower]
    emotion_score = min(15, len(emotion_found) * 5)
    dimensions["emotional_pull"] = {
        "score": emotion_score,
        "max": 15,
        "label": "Emotional Pull",
        "detail": f"{len(emotion_found)} emotional triggers" if emotion_found else "Flat tone — add curiosity or urgency",
        "words": emotion_found[:5],
    }

    # 5. CLARITY (0-10)
    clarity_score = _score_clarity(subject, words)
    dimensions["clarity"] = {
        "score": clarity_score,
        "max": 10,
        "label": "Clarity",
        "detail": _clarity_detail(clarity_score),
    }

    # 6. PERSONALIZATION (0-10)
    has_personalization = any(re.search(p, subject, re.IGNORECASE) for p in _PERSONALIZATION)
    has_number = bool(re.search(r'\d', subject))
    has_question = '?' in subject
    has_emoji = bool(re.search(r'[\U0001F600-\U0001F9FF\U00002700-\U000027BF\U0001F300-\U0001F5FF]', subject))

    pers_score = 0
    if has_personalization:
        pers_score += 5
    if has_number:
        pers_score += 2
    if has_question:
        pers_score += 2
    if has_emoji:
        pers_score += 1
    pers_score = min(10, pers_score)

    pers_details = []
    if has_personalization:
        pers_details.append("personalization token")
    if has_number:
        pers_details.append("number")
    if has_question:
        pers_details.append("question")
    if has_emoji:
        pers_details.append("emoji")

    dimensions["personalization"] = {
        "score": pers_score,
        "max": 10,
        "label": "Engagement Hooks",
        "detail": f"Uses: {', '.join(pers_details)}" if pers_details else "No hooks — try a number, question, or personalization",
    }

    # 7. UNIQUENESS (0-10) — penalize generic/overused patterns
    uniqueness_score = _score_uniqueness(subject, lower)
    dimensions["uniqueness"] = {
        "score": uniqueness_score,
        "max": 10,
        "label": "Uniqueness",
        "detail": "Feels original" if uniqueness_score >= 7 else "May feel generic — try a specific angle",
    }

    total = sum(d["score"] for d in dimensions.values())
    max_total = sum(d["max"] for d in dimensions.values())

    # Letter grade
    pct = (total / max_total) * 100 if max_total else 0
    if pct >= 85:
        grade, color = "A", "green"
    elif pct >= 70:
        grade, color = "B", "blue"
    elif pct >= 55:
        grade, color = "C", "yellow"
    elif pct >= 40:
        grade, color = "D", "orange"
    else:
        grade, color = "F", "red"

    # Generate tips
    tips = _generate_tips(dimensions, subject)

    return {
        "subject": subject,
        "total_score": total,
        "max_score": max_total,
        "percentage": round(pct),
        "grade": grade,
        "color": color,
        "dimensions": dimensions,
        "tips": tips,
        "rank": 0,
        "badge": None,
    }


def _score_length(chars: int) -> int:
    """Optimal length: 30-55 chars. Penalize outside range."""
    if 30 <= chars <= 55:
        return 20
    elif 20 <= chars < 30 or 55 < chars <= 70:
        return 14
    elif 10 <= chars < 20 or 70 < chars <= 90:
        return 8
    else:
        return 4


def _score_clarity(subject: str, words: list) -> int:
    """Score clarity based on word complexity and readability."""
    if not words:
        return 0

    # Average word length — shorter = clearer
    avg_word_len = sum(len(w) for w in words) / len(words)

    # Simple words ratio (<=6 chars)
    simple = sum(1 for w in words if len(w) <= 6)
    simple_ratio = simple / len(words) if words else 0

    score = 0
    if avg_word_len <= 5:
        score += 5
    elif avg_word_len <= 6:
        score += 3
    else:
        score += 1

    if simple_ratio >= 0.7:
        score += 5
    elif simple_ratio >= 0.5:
        score += 3
    else:
        score += 1

    return min(10, score)


def _clarity_detail(score: int) -> str:
    if score >= 8:
        return "Clear and scannable"
    elif score >= 5:
        return "Decent clarity — could simplify wording"
    else:
        return "Complex wording — simplify for better scannability"


def _score_uniqueness(subject: str, lower: str) -> int:
    """Penalize generic/overused subject line patterns."""
    generic_patterns = [
        r'^hey\b', r'^hi\b', r'^hello\b',
        r'^check this out', r'^don\'t miss',
        r'^newsletter', r'^update\b', r'^weekly\b',
        r'^monthly\b', r'^digest\b',
        r'^re:\s', r'^fw:\s', r'^fwd:\s',
    ]
    penalties = sum(1 for p in generic_patterns if re.search(p, lower))

    # ALL CAPS penalty
    if subject == subject.upper() and len(subject) > 5:
        penalties += 2

    # Excessive punctuation
    if subject.count('!') > 1 or subject.count('?') > 2:
        penalties += 1

    return max(0, 10 - penalties * 3)


def _generate_tips(dimensions: dict, subject: str) -> list:
    """Generate actionable tips based on scores."""
    tips = []

    length = dimensions["length"]
    if length["score"] < 14:
        chars = len(subject)
        if chars < 30:
            tips.append("Add more detail — aim for 30-55 characters for best open rates")
        else:
            tips.append("Shorten to under 55 characters to avoid truncation on mobile")

    spam = dimensions["spam_risk"]
    if spam["score"] < 15 and spam.get("flags"):
        tips.append(f"Remove or rephrase spam triggers: {', '.join(spam['flags'][:3])}")

    power = dimensions["power_words"]
    if power["score"] < 5:
        tips.append("Add a power word like 'new', 'proven', 'essential', or 'unlock'")

    emotion = dimensions["emotional_pull"]
    if emotion["score"] < 5:
        tips.append("Create curiosity or urgency — try 'discover', 'last chance', or 'secret'")

    pers = dimensions["personalization"]
    if pers["score"] < 3:
        tips.append("Add a number, question mark, or personalization token to boost engagement")

    unique = dimensions["uniqueness"]
    if unique["score"] < 5:
        tips.append("Make it more specific — generic subjects get ignored")

    # Always cap at 3 tips
    return tips[:3]
