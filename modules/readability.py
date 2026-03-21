"""
InbXr — Email Readability Analyzer
Flesch-Kincaid scoring, sentence analysis, passive voice detection.
Zero external dependencies — pure Python.
"""

import re
import math

# ── Common passive voice patterns ────────────────────
_BE_FORMS = r"(?:is|are|was|were|be|been|being|am)"
_PASSIVE_RE = re.compile(
    rf"\b{_BE_FORMS}\s+(?:\w+\s+){{0,3}}(?:\w+ed|built|broken|chosen|done|drawn|driven|"
    r"eaten|fallen|felt|found|given|gone|grown|held|hidden|hit|kept|known|laid|led|left|"
    r"lost|made|meant|met|paid|put|read|run|said|seen|sent|set|shown|shut|spoken|spent|"
    r"stood|taken|taught|thought|told|understood|won|worn|written|brought|bought|caught|"
    r"cut|dealt|dug|fed|fought|forgot|forgiven|frozen|got|gotten|hung|hurt|knelt|lent|"
    r"lit|overcome|ridden|risen|shaken|shot|shrunk|slid|slung|spun|stolen|stricken|"
    r"struck|stuck|stung|sunk|swept|swollen|sworn|swum|thrown|torn|woken|wound|woven|"
    r"wrung)\b",
    re.IGNORECASE,
)

# ── Complex word exceptions (common 3+ syllable words that aren't "hard") ──
_EASY_LONG_WORDS = {
    "everything", "everyone", "another", "together", "important", "beautiful",
    "different", "following", "interested", "understand", "interested", "however",
    "already", "usually", "remember", "probably", "companies", "businesses",
    "customer", "customers", "because", "continue", "idea", "area",
    "anywhere", "whatever", "somebody", "everyday", "afternoon", "tomorrow",
    "subscribe", "unsubscribe", "newsletter",
}

# ── HTML tag stripper ────────────────────────────────
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"[.!?]+(?:\s|$)")


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = _HTML_TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def _count_syllables(word: str) -> int:
    """Estimate syllable count for an English word."""
    word = word.lower().strip()
    if len(word) <= 2:
        return 1

    # Remove trailing e (silent e)
    if word.endswith("e") and not word.endswith("le"):
        word = word[:-1]

    # Count vowel groups
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel

    # Common suffixes that add syllables
    if word.endswith("tion") or word.endswith("sion"):
        pass  # already counted
    elif word.endswith("le") and len(word) > 2 and word[-3] not in vowels:
        count += 1
    elif word.endswith("ed") and len(word) > 3:
        # "ed" is usually silent unless preceded by t or d
        if word[-3] in ("t", "d"):
            count += 0  # already counted the vowel before
        # else ed is silent, don't add

    return max(1, count)


def _get_sentences(text: str) -> list:
    """Split text into sentences."""
    parts = _SENTENCE_RE.split(text)
    return [s.strip() for s in parts if s.strip() and len(s.strip()) > 2]


def _get_words(text: str) -> list:
    """Extract words from text."""
    return re.findall(r"[a-zA-Z']+", text)


def analyze_readability(body: str, subject: str = "") -> dict:
    """Analyze email text readability. Returns scores, stats, and recommendations."""
    plain = _strip_html(body)

    # Combine subject + body for full analysis
    full_text = f"{subject}. {plain}" if subject else plain

    words = _get_words(full_text)
    sentences = _get_sentences(full_text)

    word_count = len(words)
    sentence_count = max(len(sentences), 1)

    if word_count < 10:
        return {
            "score": None,
            "grade_level": None,
            "label": "Too Short",
            "color": "blue",
            "summary": "Not enough text to analyze readability (minimum 10 words).",
            "stats": {},
            "issues": [],
            "recommendations": [],
        }

    # ── Syllable analysis ────────────────────────────
    syllable_counts = [_count_syllables(w) for w in words]
    total_syllables = sum(syllable_counts)
    avg_syllables = total_syllables / word_count

    # Complex words (3+ syllables, excluding easy exceptions)
    complex_words = [
        w for w, sc in zip(words, syllable_counts)
        if sc >= 3 and w.lower() not in _EASY_LONG_WORDS
    ]
    complex_pct = (len(complex_words) / word_count) * 100

    # ── Sentence analysis ────────────────────────────
    sentence_lengths = []
    for s in sentences:
        s_words = _get_words(s)
        if s_words:
            sentence_lengths.append(len(s_words))

    avg_sentence_len = sum(sentence_lengths) / max(len(sentence_lengths), 1)
    max_sentence_len = max(sentence_lengths) if sentence_lengths else 0
    long_sentences = [l for l in sentence_lengths if l > 25]

    # ── Flesch-Kincaid Reading Ease ──────────────────
    # Higher = easier. 60-70 is ideal for email.
    fk_ease = 206.835 - (1.015 * avg_sentence_len) - (84.6 * avg_syllables)
    fk_ease = max(0, min(100, fk_ease))

    # ── Flesch-Kincaid Grade Level ───────────────────
    fk_grade = (0.39 * avg_sentence_len) + (11.8 * avg_syllables) - 15.59
    fk_grade = max(0, min(20, fk_grade))

    # ── Gunning Fog Index ────────────────────────────
    fog = 0.4 * (avg_sentence_len + complex_pct)
    fog = max(0, min(20, fog))

    # ── Passive voice ────────────────────────────────
    passive_matches = _PASSIVE_RE.findall(full_text)
    passive_count = len(passive_matches)
    passive_pct = (passive_count / sentence_count) * 100 if sentence_count > 0 else 0

    # ── Paragraph analysis ───────────────────────────
    paragraphs = [p.strip() for p in plain.split("\n") if p.strip()]
    long_paragraphs = [p for p in paragraphs if len(_get_words(p)) > 60]

    # ── Score and label ──────────────────────────────
    # Email-optimized scoring (emails should be easier to read than general text)
    if fk_ease >= 60:
        label = "Easy to Read"
        color = "green"
    elif fk_ease >= 45:
        label = "Moderate"
        color = "yellow"
    elif fk_ease >= 30:
        label = "Difficult"
        color = "orange"
    else:
        label = "Very Difficult"
        color = "red"

    # Normalize to 0-100 score (higher = more readable = better for email)
    score = round(fk_ease)

    # ── Build summary ────────────────────────────────
    grade_str = f"{fk_grade:.1f}"
    if fk_grade <= 6:
        audience = "general audience"
    elif fk_grade <= 8:
        audience = "most adults"
    elif fk_grade <= 10:
        audience = "high school level"
    elif fk_grade <= 12:
        audience = "college-educated readers"
    else:
        audience = "advanced/technical readers"

    summary = f"Grade level {grade_str} — readable by {audience}. Emails perform best at grades 5-8."

    # ── Issues ───────────────────────────────────────
    issues = []
    if fk_grade > 10:
        issues.append({
            "severity": "high",
            "item": f"Reading grade level is {grade_str} — too complex for most email audiences",
            "category": "Readability",
        })
    elif fk_grade > 8:
        issues.append({
            "severity": "medium",
            "item": f"Reading grade level {grade_str} is above the ideal range (5-8) for email",
            "category": "Readability",
        })

    if avg_sentence_len > 20:
        issues.append({
            "severity": "high" if avg_sentence_len > 25 else "medium",
            "item": f"Average sentence length is {avg_sentence_len:.0f} words (ideal: under 20)",
            "category": "Sentence Length",
        })

    if long_sentences:
        issues.append({
            "severity": "medium",
            "item": f"{len(long_sentences)} sentence{'s' if len(long_sentences) != 1 else ''} exceed{'s' if len(long_sentences) == 1 else ''} 25 words",
            "category": "Sentence Length",
        })

    if complex_pct > 15:
        issues.append({
            "severity": "high" if complex_pct > 25 else "medium",
            "item": f"{complex_pct:.0f}% of words are complex (3+ syllables) — aim for under 15%",
            "category": "Word Complexity",
        })

    if passive_pct > 15:
        issues.append({
            "severity": "high" if passive_pct > 25 else "medium",
            "item": f"{passive_pct:.0f}% passive voice — active voice is more direct and engaging",
            "category": "Passive Voice",
        })

    if long_paragraphs:
        issues.append({
            "severity": "medium",
            "item": f"{len(long_paragraphs)} paragraph{'s' if len(long_paragraphs) != 1 else ''} exceed{'s' if len(long_paragraphs) == 1 else ''} 60 words — break them up for scanability",
            "category": "Paragraph Length",
        })

    # ── Recommendations ──────────────────────────────
    recommendations = []

    if fk_grade > 8:
        recommendations.append("Simplify vocabulary — replace complex words with everyday alternatives")
    if avg_sentence_len > 20:
        recommendations.append("Break long sentences into shorter ones (aim for 15-20 words per sentence)")
    if passive_pct > 10:
        recommendations.append("Convert passive voice to active: 'Your order was shipped' → 'We shipped your order'")
    if complex_pct > 15:
        recommendations.append("Replace multi-syllable words: 'utilize' → 'use', 'purchase' → 'buy', 'commence' → 'start'")
    if long_paragraphs:
        recommendations.append("Break long paragraphs into 2-3 sentences each for better scanability on mobile")
    if max_sentence_len > 30:
        recommendations.append(f"Your longest sentence is {max_sentence_len} words — consider splitting it")
    if fk_ease >= 60 and passive_pct <= 10 and not issues:
        recommendations.append("Your readability is excellent — keep using this conversational style")

    return {
        "score": score,
        "grade_level": round(fk_grade, 1),
        "fog_index": round(fog, 1),
        "label": label,
        "color": color,
        "summary": summary,
        "stats": {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_length": round(avg_sentence_len, 1),
            "max_sentence_length": max_sentence_len,
            "avg_syllables_per_word": round(avg_syllables, 2),
            "complex_word_pct": round(complex_pct, 1),
            "passive_voice_pct": round(passive_pct, 1),
            "passive_voice_count": passive_count,
            "paragraph_count": len(paragraphs),
        },
        "issues": issues,
        "recommendations": recommendations,
    }
