"""
Module 2: Marketing, Sales & Branding Effectiveness Assessment
Evaluates email copy against direct-response copywriting best practices.
Outputs an effectiveness score from 0 (weak) to 100 (exceptional).
"""

import re
from bs4 import BeautifulSoup

from data.power_words import (
    STRONG_CTA_VERBS, WEAK_CTA_VERBS, EMOTIONAL_POWER_WORDS,
    BENEFIT_WORDS, FEATURE_WORDS, SOCIAL_PROOF_PATTERNS,
    RISK_REVERSAL_PATTERNS, PATTERN_INTERRUPT_PHRASES,
    PAIN_AWARE_PHRASES, SOLUTION_PHRASES
)


def _extract_text(raw: str) -> str:
    if re.search(r'<[a-zA-Z][^>]*>', raw):
        return BeautifulSoup(raw, "lxml").get_text(separator=" ", strip=True)
    return raw


def _sentences(text: str) -> list:
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def _paragraphs(text: str) -> list:
    return [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r'\b\w+\b', text))


def _count_pronoun_ratio(text: str) -> dict:
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    total = len(words)
    you_count = sum(1 for w in words if w in ("you", "your", "yours", "yourself", "you're", "you'll", "you've"))
    we_count = sum(1 for w in words if w in ("we", "our", "us", "ours", "we're", "we'll", "we've",
                                              "i", "my", "mine", "i'm", "i'll", "i've"))
    return {
        "you": you_count,
        "we_i": we_count,
        "ratio": round(you_count / max(we_count, 1), 2),
        "you_pct": round(you_count / max(total, 1) * 100, 1)
    }


def _readability_score(text: str) -> dict:
    """Simplified Flesch-Kincaid approximation."""
    sentences = _sentences(text)
    words = re.findall(r'\b\w+\b', text)
    if not sentences or not words:
        return {"grade": 0, "level": "N/A", "avg_sentence_len": 0}

    avg_sentence_len = len(words) / len(sentences)
    # Simplified syllable count (approximation)
    syllable_count = sum(max(1, len(re.findall(r'[aeiouAEIOU]', w))) for w in words)
    avg_syllables = syllable_count / len(words)

    fk_score = 206.835 - (1.015 * avg_sentence_len) - (84.6 * avg_syllables)
    fk_score = max(0, min(100, fk_score))

    if fk_score >= 70:
        level = "Easy (7th grade)"
    elif fk_score >= 50:
        level = "Standard (10th grade)"
    elif fk_score >= 30:
        level = "Difficult (College)"
    else:
        level = "Very Difficult (Professional)"

    return {
        "score": round(fk_score, 1),
        "level": level,
        "avg_sentence_len": round(avg_sentence_len, 1)
    }


class CopyAnalyzer:
    def __init__(self, subject, preheader, body, sender_email="",
                 cta_urls=None, cta_texts=None, is_transactional=False,
                 is_cold_email=False, is_plain_text=False, industry="Other"):
        self.subject = subject or ""
        self.preheader = preheader or ""
        self.raw_body = body or ""
        self.sender_email = sender_email or ""
        self.cta_urls = cta_urls or []
        self.cta_texts = cta_texts or []
        self.is_transactional = is_transactional
        self.is_cold_email = is_cold_email
        self.is_plain_text = is_plain_text
        self.industry = industry

        self.body_text = _extract_text(self.raw_body)
        self.all_text = f"{self.subject} {self.preheader} {self.body_text}"

        self.strengths = []
        self.weaknesses = []

    # ─────────────────────────────────────────────────────────────────────────
    # Category A: Subject Line Strength  (max: 20)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_subject_strength(self):
        subject = self.subject
        score = 0
        flags = []
        positives = []

        if not subject:
            return {"score": 0, "max": 20, "label": "Subject Line Strength",
                    "flags": [{"item": "No subject line provided", "impact": "high"}], "positives": []}

        subject_lower = subject.lower()
        words = re.findall(r'\b\w+\b', subject_lower)
        char_count = len(subject)

        # --- Value clarity (0-5) ---
        value_score = 0
        benefit_found = [w for w in BENEFIT_WORDS if w in subject_lower]
        if benefit_found:
            value_score += 2
            positives.append(f"Benefit-oriented language: '{benefit_found[0]}'")
        if re.search(r'\b\d+\b', subject):
            value_score += 1
            positives.append("Specific number/stat increases credibility")
        if re.search(r'\byou\b', subject_lower):
            value_score += 1
            positives.append("'You' focus makes it reader-centric")
        if not re.search(r'(?i)(check this out|just wanted|update|fyi|newsletter)', subject_lower):
            value_score += 1
        score += min(5, value_score)

        # --- Curiosity/intrigue (0-5) ---
        curiosity_score = 0
        curiosity_patterns = [
            r'(?i)(how to|why|what|the secret|revealed|the truth)',
            r'(?i)(you\'?re? (doing|making|missing|leaving))',
            r'(?i)(\d+ (ways?|reasons?|mistakes?|things?|tips?|steps?|secrets?))',
            r'(?i)(what (happened|works?|most people|nobody))',
            r'(?i)(\?$)',  # ends with question
        ]
        curiosity_matches = [p for p in curiosity_patterns if re.search(p, subject)]
        curiosity_score = min(4, len(curiosity_matches) * 2)
        if curiosity_score > 0:
            positives.append("Subject creates curiosity or open loop")
        # Deduct for clickbait without substance
        if re.search(r'(?i)(you won\'?t believe|this is insane|mind.?blown)', subject_lower):
            curiosity_score = max(0, curiosity_score - 2)
            flags.append({"item": "Clickbait phrasing reduces trust", "impact": "medium",
                          "recommendation": "Use curiosity that is genuine — tease the benefit, not just shock value."})
        score += curiosity_score

        # --- Emotional pull (0-4) ---
        emotion_score = 0
        emotion_found = [w for w in EMOTIONAL_POWER_WORDS if w in subject_lower]
        if emotion_found:
            emotion_score += 2
            positives.append(f"Emotional power word: '{emotion_found[0]}'")
        pain_match = re.search(r'(?i)(tired of|frustrated|struggling|stop|avoid|fix|solve|eliminate)', subject_lower)
        if pain_match:
            emotion_score += 2
            positives.append("Addresses a pain point — high relevance trigger")
        score += min(4, emotion_score)

        # --- Specificity (0-3) ---
        specific_score = 0
        if re.search(r'\b\d[\d,]*\b', subject):
            specific_score += 2
            positives.append("Specific numbers increase open rates")
        if not re.search(r'(?i)^(hi|hello|hey|good morning|update|news|info)', subject_lower):
            specific_score += 1
        score += min(3, specific_score)

        # --- Length optimization (0-3) ---
        if 30 <= char_count <= 50:
            score += 3
            positives.append(f"Optimal subject length ({char_count} chars) — great for mobile and desktop")
        elif 20 <= char_count <= 60:
            score += 2
        elif char_count <= 70:
            score += 1
        else:
            flags.append({"item": f"Subject is {char_count} chars — may be truncated on mobile",
                          "impact": "medium",
                          "recommendation": "Aim for 30–50 characters. Front-load the most important words."})

        score = min(20, score)
        if score < 8:
            self.weaknesses.append("Subject line lacks clarity, specificity, or emotional pull")
        elif score >= 15:
            self.strengths.append("Strong subject line with clear value and curiosity")

        return {"score": score, "max": 20, "label": "Subject Line Strength",
                "flags": flags, "positives": positives,
                "details": {"char_count": char_count, "word_count": len(words)}}

    # ─────────────────────────────────────────────────────────────────────────
    # Category B: Opening & Hook  (max: 15)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_opening(self):
        body = self.body_text
        score = 0
        flags = []
        positives = []

        if not body or _word_count(body) < 10:
            return {"score": 0, "max": 15, "label": "Opening & Hook",
                    "flags": [{"item": "Insufficient body content to evaluate", "impact": "high"}], "positives": []}

        sentences = _sentences(body)
        first_sentence = sentences[0] if sentences else ""
        first_para = " ".join(sentences[:3])
        first_lower = first_sentence.lower()

        # --- First sentence engagement (0-5) ---
        eng_score = 0
        # Doesn't start with "I" or company name
        if not re.search(r'^(i |we |our |my )', first_lower):
            eng_score += 1
        else:
            flags.append({"item": "Opens with 'I', 'We', or 'Our' — company-centric framing",
                          "impact": "medium",
                          "recommendation": "Start with the reader in mind. Lead with their situation, pain, or desired outcome."})
        if re.search(r'\?$', first_sentence):
            eng_score += 2
            positives.append("Opening question pulls the reader in immediately")
        elif any(re.search(p, first_sentence, re.IGNORECASE) for p in PATTERN_INTERRUPT_PHRASES):
            eng_score += 2
            positives.append("Pattern interrupt opening — breaks reader autopilot")
        word_count_fs = _word_count(first_sentence)
        if word_count_fs <= 12:
            eng_score += 2
            positives.append(f"Short, punchy first sentence ({word_count_fs} words)")
        elif word_count_fs <= 20:
            eng_score += 1
        else:
            flags.append({"item": f"First sentence is {word_count_fs} words — too long",
                          "impact": "low",
                          "recommendation": "Trim your opening sentence to under 15 words. Short sentences create momentum."})
        score += min(5, eng_score)

        # --- Context speed (0-4) ---
        para_sentences = sentences[:3]
        para_text = " ".join(para_sentences).lower()
        solution_found = any(re.search(p, para_text) for p in SOLUTION_PHRASES)
        pain_found = any(re.search(p, para_text) for p in PAIN_AWARE_PHRASES)

        if solution_found or pain_found:
            score += 4
            positives.append("Gets to the point or identifies pain within first 3 sentences")
        elif len(sentences) >= 3:
            score += 2
            flags.append({"item": "Takes more than 3 sentences to establish value/context",
                          "impact": "medium",
                          "recommendation": "Lead with the reader's problem or your core benefit in the first 1–2 sentences."})
        else:
            score += 1

        # --- You-centric framing (0-3) ---
        pronoun_data = _count_pronoun_ratio(first_para)
        if pronoun_data["ratio"] >= 3:
            score += 3
            positives.append(f"Strong reader focus: {pronoun_data['ratio']}:1 you-to-we ratio")
        elif pronoun_data["ratio"] >= 1.5:
            score += 2
            positives.append("Good reader-centric framing")
        elif pronoun_data["ratio"] >= 1:
            score += 1
        else:
            flags.append({"item": "Low 'you' ratio — feels company-centric",
                          "impact": "medium",
                          "recommendation": f"Opening uses more 'we/I' than 'you'. Reframe around the reader's perspective."})

        # --- Pattern interruption (0-3) ---
        interrupt_found = any(re.search(p, first_para, re.IGNORECASE) for p in PATTERN_INTERRUPT_PHRASES)
        story_pattern = re.search(r'(?i)((last|this) (week|month|year)|when i|i remember|it was|picture this|imagine)', first_para)
        if interrupt_found:
            score += 2
        if story_pattern:
            score += 1
            positives.append("Story or scene-setting creates relatability")

        score = min(15, score)
        if score < 6:
            self.weaknesses.append("Opening hook is weak — reader may disengage before reaching the offer")
        elif score >= 11:
            self.strengths.append("Strong opening that immediately engages the reader")

        return {"score": score, "max": 15, "label": "Opening & Hook",
                "flags": flags, "positives": positives,
                "details": {"first_sentence": first_sentence[:120], "pronoun_ratio": pronoun_data}}

    # ─────────────────────────────────────────────────────────────────────────
    # Category C: Core Message & Offer Clarity  (max: 25)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_core_message(self):
        body = self.body_text
        score = 0
        flags = []
        positives = []

        if not body:
            return {"score": 0, "max": 25, "label": "Core Message & Offer", "flags": [], "positives": []}

        word_count = _word_count(body)
        paragraphs = _paragraphs(body)
        sentences = _sentences(body)
        body_lower = body.lower()

        # --- Single dominant idea focus (0-7) ---
        cta_count = len(self.cta_urls) + len(self.cta_texts)
        cta_phrases_in_body = len(re.findall(
            r'(?i)(click here|learn more|get started|sign up|buy now|shop now|download|register|book|schedule|call now|contact us)',
            body
        ))

        if cta_phrases_in_body <= 2:
            score += 5
            positives.append("Focused message — single or minimal call-to-action")
        elif cta_phrases_in_body <= 4:
            score += 3
            flags.append({"item": f"{cta_phrases_in_body} different CTA phrases — slightly fragmented",
                          "impact": "low",
                          "recommendation": "Simplify to one primary CTA. Multiple asks dilute conversion intent."})
        else:
            score += 1
            flags.append({"item": f"{cta_phrases_in_body} CTA phrases — too many competing actions",
                          "impact": "high",
                          "recommendation": "Choose ONE primary action. Remove or downgrade all secondary CTAs. Readers who face too many choices take no action."})

        # Unique topics count (rough heuristic via heading/section patterns)
        heading_count = len(re.findall(r'\n[A-Z][A-Z\s]+\n|\*\*[^*]+\*\*', body))
        if heading_count <= 3:
            score += 2
        elif heading_count <= 6:
            score += 1
        else:
            flags.append({"item": f"Email has {heading_count} sections — may feel like a newsletter, not a message",
                          "impact": "medium",
                          "recommendation": "Keep focused emails to 1–3 sections max. Information overload kills action."})

        # --- Benefit clarity (0-7) ---
        benefit_count = sum(1 for w in BENEFIT_WORDS if w in body_lower)
        feature_count = sum(1 for w in FEATURE_WORDS if w in body_lower)
        benefit_score = 0
        if benefit_count >= 3:
            benefit_score += 4
            positives.append(f"Benefit-rich copy ({benefit_count} benefit phrases found)")
        elif benefit_count >= 1:
            benefit_score += 2
        else:
            flags.append({"item": "No clear benefit language detected",
                          "impact": "high",
                          "recommendation": "Reframe around outcomes: what does the reader GET, SAVE, AVOID, or ACHIEVE? Features tell, benefits sell."})

        if benefit_count > feature_count:
            benefit_score += 2
            positives.append("Benefits outweigh features — strong copy orientation")
        elif feature_count > benefit_count * 2:
            flags.append({"item": "Feature-heavy copy (more features than benefits)",
                          "impact": "medium",
                          "recommendation": "For each feature, add a 'which means...' or 'so you can...' to translate it into a benefit."})

        score += min(7, benefit_score)

        # --- Pain-solution alignment (0-6) ---
        pain_found = any(re.search(p, body, re.IGNORECASE) for p in PAIN_AWARE_PHRASES)
        solution_found = any(re.search(p, body, re.IGNORECASE) for p in SOLUTION_PHRASES)

        if pain_found and solution_found:
            score += 6
            positives.append("Strong problem-solution arc — highly effective copy structure")
        elif pain_found:
            score += 3
            flags.append({"item": "Identifies pain but solution isn't clearly articulated",
                          "impact": "medium",
                          "recommendation": "After establishing the problem, explicitly state your solution and the outcome it creates."})
        elif solution_found:
            score += 3
            flags.append({"item": "Solution-focused but doesn't clearly identify the problem",
                          "impact": "low",
                          "recommendation": "Name the problem before offering the solution. Readers need to see themselves in the pain first."})
        else:
            flags.append({"item": "No clear problem-solution structure detected",
                          "impact": "high",
                          "recommendation": "Structure your email: Problem → Agitation → Solution. Start by speaking to what's frustrating or costing your reader."})

        # --- Scannability (0-5) ---
        scan_score = 0
        avg_para_sentences = len(sentences) / max(len(paragraphs), 1)
        if avg_para_sentences <= 3:
            scan_score += 2
            positives.append("Short paragraphs make scanning easy")
        elif avg_para_sentences > 5:
            flags.append({"item": f"Long paragraphs (avg {avg_para_sentences:.1f} sentences each)",
                          "impact": "medium",
                          "recommendation": "Break paragraphs at 2–3 sentences. White space improves readability and engagement."})

        has_bullets = bool(re.search(r'(?m)^[\s]*[-•*]\s', body) or re.search(r'(?m)^\d+\.\s', body))
        if has_bullets:
            scan_score += 2
            positives.append("Bullet points improve scannability")
        elif word_count > 150:
            flags.append({"item": "Long copy without bullet points",
                          "impact": "low",
                          "recommendation": "Add 3–5 bullet points to highlight key benefits or features. Most readers scan before they read."})

        if word_count > 50:
            scan_score += 1
        score += min(5, scan_score)

        score = min(25, score)
        if score < 10:
            self.weaknesses.append("Core message lacks clarity, benefit focus, or structure")
        elif score >= 18:
            self.strengths.append("Clear, well-structured message with strong benefit orientation")

        readability = _readability_score(body)
        return {"score": score, "max": 25, "label": "Core Message & Offer Clarity",
                "flags": flags, "positives": positives,
                "details": {"word_count": word_count, "paragraph_count": len(paragraphs),
                            "has_bullets": has_bullets, "readability": readability}}

    # ─────────────────────────────────────────────────────────────────────────
    # Category D: CTA Effectiveness  (max: 20)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_cta(self):
        body = self.body_text
        score = 0
        flags = []
        positives = []
        body_lower = body.lower()

        # Collect all CTAs
        cta_sample = []
        if self.cta_texts:
            cta_sample.extend([t.lower() for t in self.cta_texts])
        # Also detect inline CTA phrases
        inline_cta = re.findall(
            r'(?i)(?:click|tap|get|start|claim|grab|download|try|join|sign up|register|book|schedule|access|unlock|discover|see|learn|buy|shop|order)[^.!?]{0,60}',
            body
        )
        cta_sample.extend([c.lower() for c in inline_cta[:3]])

        has_cta = bool(cta_sample)
        if not has_cta:
            flags.append({"item": "No clear CTA detected",
                          "impact": "high",
                          "recommendation": "Every email needs at least one clear call-to-action. Tell the reader exactly what to do next."})
            return {"score": 0, "max": 20, "label": "CTA Effectiveness",
                    "flags": flags, "positives": positives}

        # --- Clarity of action (0-6) ---
        clarity_score = 0
        action_verbs_found = [v for v in STRONG_CTA_VERBS if any(v in cta for cta in cta_sample)]
        weak_verbs_found = [v for v in WEAK_CTA_VERBS if any(v in cta for cta in cta_sample)]

        if action_verbs_found and not weak_verbs_found:
            clarity_score += 4
            positives.append(f"Strong CTA verb: '{action_verbs_found[0]}' — action-oriented")
        elif action_verbs_found:
            clarity_score += 2
        elif weak_verbs_found:
            flags.append({"item": f"Weak CTA verb: '{weak_verbs_found[0]}'",
                          "impact": "medium",
                          "recommendation": f"Replace '{weak_verbs_found[0]}' with an action verb that implies value: 'Get', 'Start', 'Claim', 'Unlock', 'Discover'."})

        # Check specificity
        vague_ctas = ["click here", "learn more", "read more", "find out more", "more info"]
        specific_ctas_found = not any(v in " ".join(cta_sample) for v in vague_ctas)
        if specific_ctas_found:
            clarity_score += 2
            positives.append("CTA is specific — readers know what they're clicking")
        else:
            flags.append({"item": "Generic CTA detected (e.g. 'click here', 'learn more')",
                          "impact": "medium",
                          "recommendation": "Make your CTA button text describe the outcome: 'Get My Free Report', 'Start My 14-Day Trial', 'Yes, Show Me How'."})
        score += min(6, clarity_score)

        # --- Friction level (0-5) ---
        friction_score = 0
        low_friction = ["free", "no credit card", "no commitment", "no obligation",
                        "cancel anytime", "try", "preview", "demo"]
        high_friction = ["purchase", "buy", "pay", "checkout", "subscribe", "sign a", "contract"]

        low_f = any(lf in body_lower for lf in low_friction)
        high_f = any(hf in " ".join(cta_sample) for hf in high_friction)

        if low_f and not high_f:
            friction_score += 3
            positives.append("Low-friction positioning — reduces hesitation")
        elif high_f and not low_f:
            flags.append({"item": "High-friction CTA without risk-reducing language",
                          "impact": "medium",
                          "recommendation": "Add friction reducers near your CTA: 'No credit card required', 'Cancel anytime', 'Free to try'."})
        else:
            friction_score += 1

        # Single primary CTA
        explicit_cta_count = len(re.findall(r'(?i)(click here|tap here|get started|sign up|buy now|order now|download now|register now|book now|schedule now)', body))
        if explicit_cta_count <= 2:
            friction_score += 2
            if explicit_cta_count == 1:
                positives.append("Single CTA — focused and unconditional")
        elif explicit_cta_count >= 4:
            flags.append({"item": f"{explicit_cta_count} competing CTAs in body",
                          "impact": "high",
                          "recommendation": "Remove secondary CTAs. One primary action per email maximizes click-through rates."})
        score += min(5, friction_score)

        # --- Urgency quality (0-4) ---
        ethical_urgency = re.search(
            r'(?i)(today only|this week|limited spots?|offer ends|sale ends|by [a-z]+ \d+|before\s+\w+\s+\d+)',
            body
        )
        manufactured_urgency = re.search(
            r'(?i)(act now|don\'?t wait|hurry|limited time \(always\)|rush|asap)',
            body
        )

        if ethical_urgency and not manufactured_urgency:
            score += 4
            positives.append("Genuine urgency with specific deadline — boosts conversion without damaging trust")
        elif ethical_urgency and manufactured_urgency:
            score += 2
            flags.append({"item": "Mixes genuine and manufactured urgency",
                          "impact": "low",
                          "recommendation": "Stick to genuine deadlines. Manufactured urgency ('act now', 'hurry') alongside real ones feels dishonest."})
        elif not ethical_urgency:
            score += 1
            flags.append({"item": "No urgency or reason to act now",
                          "impact": "medium",
                          "recommendation": "Add a legitimate reason to act: time-limited offer, enrollment deadline, price increase date, or limited spots."})

        # --- CTA text strength (0-5) ---
        value_cta_pattern = re.search(
            r'(?i)(get (my|your|free|instant|the)|claim (my|your|free|the)|start (my|your|free)|yes[,!]?\s+\w)',
            " ".join(cta_sample)
        )
        if value_cta_pattern:
            score += 5
            positives.append("Value-oriented CTA text (e.g. 'Get My Free...', 'Yes, I Want...') — high converting")
        else:
            generic_check = any(v in " ".join(cta_sample) for v in ["submit", "go", "continue", "next", "send"])
            if generic_check:
                flags.append({"item": "Generic CTA button text (submit/go/send)",
                              "impact": "high",
                              "recommendation": "Write CTA text from the reader's perspective: 'Yes, Send My Guide', 'I Want In', 'Get Instant Access'. First-person CTAs convert 90% better."})
            else:
                score += 3

        score = min(20, score)
        if score < 8:
            self.weaknesses.append("CTA is weak, generic, or absent — conversion potential is limited")
        elif score >= 15:
            self.strengths.append("CTA is clear, specific, and low-friction — strong conversion setup")

        return {"score": score, "max": 20, "label": "CTA Effectiveness",
                "flags": flags, "positives": positives,
                "details": {"ctas_found": cta_sample[:3], "has_urgency": bool(ethical_urgency)}}

    # ─────────────────────────────────────────────────────────────────────────
    # Category E: Brand & Trust Signals  (max: 10)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_brand_trust(self):
        body = self.body_text
        score = 0
        flags = []
        positives = []
        body_lower = body.lower()

        if not body:
            return {"score": 0, "max": 10, "label": "Brand & Trust", "flags": [], "positives": []}

        # --- Tone consistency (0-4) ---
        tone_score = 0
        # Check for tone inconsistency (mixing formal/casual)
        formal_markers = len(re.findall(r'(?i)\b(hereby|herewith|pursuant|aforementioned|whereas|notwithstanding)\b', body))
        casual_markers = len(re.findall(r'(?i)\b(hey|yo|lol|omg|kinda|wanna|gonna|dunno|btw|tbh)\b', body))

        if formal_markers > 2 and casual_markers > 2:
            flags.append({"item": "Mixed formal and casual tone — inconsistent voice",
                          "impact": "medium",
                          "recommendation": "Pick one voice and stay consistent. Mixing 'hereby' with 'hey!' signals lack of professional polish."})
        else:
            tone_score += 2
            positives.append("Consistent tone throughout")

        # Not overly salesy
        hype_words = len(re.findall(
            r'(?i)\b(amazing|incredible|unbelievable|jaw-dropping|mind-blowing|never seen before|game changer|revolutionary|breakthrough)\b',
            body
        ))
        if hype_words > 3:
            flags.append({"item": f"{hype_words} hyperbolic phrases reduce credibility",
                          "impact": "medium",
                          "recommendation": "Replace hyperbole with specifics. 'Increased revenue by 43%' beats 'amazing results' every time."})
        else:
            tone_score += 2
            if hype_words == 0:
                positives.append("Claims feel credible — no excessive hyperbole")
        score += min(4, tone_score)

        # --- Credibility indicators (0-3) ---
        cred_score = 0
        if re.search(r'\b\d[\d,]*\b', body):
            cred_score += 1
            positives.append("Specific numbers add credibility")
        if re.search(r'(?i)(study|research|data|report|survey|according to|found that)', body):
            cred_score += 1
            positives.append("References to data or research build authority")
        if re.search(r'(?i)(case study|client|customer|our team|our company|founded|years? (of experience|in business))', body):
            cred_score += 1
        score += min(3, cred_score)

        # --- Transparency (0-3) ---
        trans_score = 0
        if self.sender_email and "@" in self.sender_email:
            domain = self.sender_email.split("@")[-1]
            free_providers = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com"]
            if domain not in free_providers:
                trans_score += 1
                positives.append("Custom domain sender address adds professionalism")
        else:
            trans_score += 1  # Can't evaluate, don't penalize

        if not re.search(r'(?i)(guarantee results|100% guarantee|promise you will)', body):
            trans_score += 1
            positives.append("Avoids over-promising — maintains credibility")
        if re.search(r'(?i)(our (team|company|product) (has|was|is)|we (founded|started|built|created))', body):
            trans_score += 1
        score += min(3, trans_score)

        score = min(10, score)
        if score < 4:
            self.weaknesses.append("Email lacks trust signals — readers may question credibility")
        elif score >= 8:
            self.strengths.append("Strong trust and credibility signals throughout")

        return {"score": score, "max": 10, "label": "Brand & Trust Signals",
                "flags": flags, "positives": positives}

    # ─────────────────────────────────────────────────────────────────────────
    # Category F: Conversion Psychology  (max: 10)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_conversion_psychology(self):
        body = self.body_text
        score = 0
        flags = []
        positives = []

        if not body:
            return {"score": 0, "max": 10, "label": "Conversion Psychology", "flags": [], "positives": []}

        body_lower = body.lower()

        # --- Social proof (0-3) ---
        proof_found = [p for p in SOCIAL_PROOF_PATTERNS if re.search(p, body)]
        if len(proof_found) >= 2:
            score += 3
            positives.append("Strong social proof (testimonials, numbers, trust logos)")
        elif len(proof_found) == 1:
            score += 2
            positives.append("Some social proof present")
        else:
            flags.append({"item": "No social proof detected",
                          "impact": "high",
                          "recommendation": "Add at least one proof element: a quote with a name and result, a customer count, or a recognizable logo/publication."})

        # --- Risk reversal (0-3) ---
        reversal_found = [p for p in RISK_REVERSAL_PATTERNS if re.search(p, body, re.IGNORECASE)]
        if reversal_found:
            score += 3
            positives.append("Risk reversal present — lowers psychological barrier to action")
        else:
            if not self.is_transactional:
                flags.append({"item": "No risk reversal language",
                              "impact": "medium",
                              "recommendation": "Add a guarantee, free trial, or cancellation policy near your CTA. Risk reversal can increase conversions by 30%+."})
            score += 1  # transactional emails don't always need this

        # --- Decision clarity (0-4) ---
        clarity_score = 0
        # Simple next step
        next_step_pattern = re.search(
            r'(?i)(here\'?s? (what|how) (happens?|to) next|your next step|all you (need to|have to) do|it\'?s? (simple|easy|fast))',
            body
        )
        if next_step_pattern:
            clarity_score += 2
            positives.append("Clear 'next step' framing reduces decision friction")

        # Avoids cognitive overload (not too many choices)
        choice_words = len(re.findall(r'(?i)\b(option|choice|plan|tier|package|version|either|or you can|alternatively)\b', body))
        if choice_words <= 2:
            clarity_score += 2
            positives.append("Simple decision structure — minimal choice overload")
        elif choice_words >= 5:
            flags.append({"item": f"{choice_words} option/choice references — potential decision paralysis",
                          "impact": "medium",
                          "recommendation": "Present one recommended path clearly. Too many options cause readers to choose nothing. Use 'most popular' or 'recommended' to guide."})
        else:
            clarity_score += 1
        score += min(4, clarity_score)

        score = min(10, score)
        if score < 4:
            self.weaknesses.append("Weak conversion psychology — missing proof, risk reversal, or decision clarity")
        elif score >= 8:
            self.strengths.append("Excellent conversion psychology — proof, risk reversal, and clear path to action")

        return {"score": score, "max": 10, "label": "Conversion Psychology",
                "flags": flags, "positives": positives}

    # ─────────────────────────────────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────────────────────────────────
    def analyze(self) -> dict:
        cat_a = self._score_subject_strength()
        cat_b = self._score_opening()
        cat_c = self._score_core_message()
        cat_d = self._score_cta()
        cat_e = self._score_brand_trust()
        cat_f = self._score_conversion_psychology()

        total = (cat_a["score"] + cat_b["score"] + cat_c["score"] +
                 cat_d["score"] + cat_e["score"] + cat_f["score"])
        total = min(100, total)

        if total <= 30:
            label = "Weak"
            color = "red"
            summary = "This email has significant copy issues. Core elements like benefit clarity, hook strength, and CTA effectiveness need major work."
        elif total <= 50:
            label = "Below Average"
            color = "orange"
            summary = "The email has a foundation but is missing key conversion elements. Focus on the flagged areas to meaningfully lift performance."
        elif total <= 70:
            label = "Solid"
            color = "yellow"
            summary = "Decent copy with room to improve. Strengthening the weakest areas could meaningfully lift open and click rates."
        elif total <= 85:
            label = "Strong"
            color = "blue"
            summary = "Well-crafted email. A few targeted refinements could push performance further."
        else:
            label = "Exceptional"
            color = "green"
            summary = "High-quality email copy following best practices across all dimensions. Ready to send."

        # Build rewrite suggestions
        rewrites = self._generate_rewrites(cat_a, cat_b, cat_c, cat_d)

        # Aggregate all flags across categories
        all_flags = []
        for cat in [cat_a, cat_b, cat_c, cat_d, cat_e, cat_f]:
            for flag in cat.get("flags", []):
                all_flags.append({**flag, "category": cat["label"]})

        all_positives = []
        for cat in [cat_a, cat_b, cat_c, cat_d, cat_e, cat_f]:
            for pos in cat.get("positives", []):
                all_positives.append({"item": pos, "category": cat["label"]})

        severity_order = {"high": 0, "medium": 1, "low": 2}
        all_flags.sort(key=lambda x: severity_order.get(x.get("impact", "low"), 2))

        return {
            "score": total,
            "label": label,
            "color": color,
            "summary": summary,
            "categories": [cat_a, cat_b, cat_c, cat_d, cat_e, cat_f],
            "strengths": list(set(self.strengths)),
            "weaknesses": list(set(self.weaknesses)),
            "all_flags": all_flags[:12],
            "all_positives": all_positives[:10],
            "rewrites": rewrites,
        }

    def _generate_rewrites(self, cat_a, cat_b, cat_c, cat_d) -> dict:
        """Generate specific rewrite examples based on the email content."""
        rewrites = {}
        subject = self.subject
        body = self.body_text

        # Subject line rewrites
        if cat_a["score"] < 15 and subject:
            rewrites["subject_alternatives"] = self._suggest_subjects(subject)

        # Opening paragraph rewrite suggestion
        if cat_b["score"] < 10 and body:
            sentences = _sentences(body)
            if sentences:
                rewrites["opening_suggestion"] = {
                    "original": " ".join(sentences[:2]),
                    "tip": "Start with the reader's problem or a bold statement. Lead with 'you', not 'we'."
                }

        # CTA rewrite
        if cat_d["score"] < 12:
            rewrites["cta_examples"] = [
                "Get Instant Access →",
                "Yes, Show Me How →",
                "Start My Free Trial →",
                "Claim My Spot →",
                "Get the [Specific Outcome] →",
            ]

        return rewrites

    def _suggest_subjects(self, subject: str) -> list:
        """Generate subject line improvement templates based on original."""
        suggestions = []

        # Extract the core topic
        topic_words = [w for w in subject.split() if len(w) > 3 and w.lower() not in
                       ("this", "that", "with", "from", "your", "will", "have", "been")]
        topic = " ".join(topic_words[:3]) if topic_words else "your goal"

        suggestions = [
            f"How to {topic} in [X] steps (without [common pain])",
            f"The [#] biggest mistakes people make with {topic}",
            f"Why most people fail at {topic} — and how to fix it",
            f"[Specific result] in [timeframe]: Here's exactly how",
            f"You're leaving [money/time/results] on the table with {topic}",
        ]
        return suggestions[:4]
