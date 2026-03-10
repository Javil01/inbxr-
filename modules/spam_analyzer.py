"""
Module 1: Spam Risk Probability Assessment
Evaluates email copy against deliverability heuristics and spam filter patterns.
Outputs a risk score from 0 (no risk) to 100 (near-certain spam).
"""

import re
import unicodedata
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from data.spam_words import (
    SPAM_TRIGGER_WORDS, HIGH_RISK_WORDS, URL_SHORTENERS,
    SUSPICIOUS_TLDS, HIGH_RISK_CTA_PHRASES, DECEPTIVE_SUBJECT_PATTERNS,
    URGENCY_MANIPULATION_PATTERNS, UNSUBSCRIBE_PATTERNS, ADDRESS_PATTERNS
)


def _extract_text_from_html(html: str) -> str:
    """Strip HTML tags and return plain text."""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)


def _count_emojis(text: str) -> int:
    count = 0
    for char in text:
        cat = unicodedata.category(char)
        cp = ord(char)
        if (cat.startswith("So") or cat.startswith("Sm") or
                (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF)):
            count += 1
    return count


def _extract_urls(text: str) -> list:
    url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+'
    return re.findall(url_pattern, text, re.IGNORECASE)


def _is_html(text: str) -> bool:
    return bool(re.search(r'<[a-zA-Z][^>]*>', text))


class SpamAnalyzer:
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

        self.is_html_body = _is_html(self.raw_body)
        self.body_text = _extract_text_from_html(self.raw_body) if self.is_html_body else self.raw_body
        self.body_soup = BeautifulSoup(self.raw_body, "lxml") if self.is_html_body else None

        # Combine all URLs found
        all_urls = _extract_urls(self.raw_body) + self.cta_urls
        self.all_urls = list(set(all_urls))

        self.flagged_items = []      # list of {category, item, severity, recommendation}
        self.category_scores = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Category A: Subject Line Spam Signals  (max risk: 25)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_subject(self):
        subject = self.subject
        risk = 0
        flags = []

        if not subject:
            return {"score": 0, "max": 25, "label": "Subject Line", "flags": []}

        subject_lower = subject.lower()
        words = subject_lower.split()

        # --- Spam trigger words (0-10) ---
        found_triggers = []
        for phrase in SPAM_TRIGGER_WORDS:
            if phrase in subject_lower:
                found_triggers.append(phrase)
        for word in HIGH_RISK_WORDS:
            if word in words and word not in found_triggers:
                found_triggers.append(word)

        trigger_count = len(found_triggers)
        trigger_risk = min(10, trigger_count * 3)
        risk += trigger_risk
        if found_triggers:
            flags.append({
                "severity": "high" if trigger_count >= 2 else "medium",
                "item": f"Spam trigger word(s): {', '.join(found_triggers[:5])}",
                "recommendation": f"Replace '{found_triggers[0]}' and similar words with natural language equivalents."
            })

        # --- Deceptive patterns (0-4) ---
        for pattern in DECEPTIVE_SUBJECT_PATTERNS:
            if re.search(pattern, subject):
                risk += 4
                flags.append({
                    "severity": "high",
                    "item": f"Deceptive phrasing pattern detected in subject",
                    "recommendation": "Remove misleading framing such as fake Re:/Fwd: prefixes or 'you've won' language."
                })
                break

        # --- Excessive capitalization (0-5) ---
        alpha_chars = [c for c in subject if c.isalpha()]
        if alpha_chars:
            caps_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
            if caps_ratio > 0.7:
                risk += 5
                flags.append({
                    "severity": "high",
                    "item": f"Subject is mostly ALL CAPS ({int(caps_ratio*100)}% uppercase)",
                    "recommendation": "Use sentence case or title case. All-caps triggers spam filters and feels aggressive."
                })
            elif caps_ratio > 0.4:
                risk += 2
                flags.append({
                    "severity": "medium",
                    "item": f"High capitalization ratio ({int(caps_ratio*100)}%)",
                    "recommendation": "Reduce capitalization to appear more natural and professional."
                })

        # --- Excessive punctuation (0-3) ---
        excl_count = subject.count("!")
        quest_count = subject.count("?")
        if excl_count >= 3 or quest_count >= 3:
            risk += 3
            flags.append({
                "severity": "high",
                "item": f"Excessive punctuation ({excl_count} '!', {quest_count} '?')",
                "recommendation": "Use at most one exclamation mark. Multiple !!! signals spam and reduces credibility."
            })
        elif excl_count >= 2 or quest_count >= 2:
            risk += 1
            flags.append({
                "severity": "low",
                "item": "Multiple exclamation/question marks",
                "recommendation": "Limit to one exclamation mark per subject line."
            })

        # --- Emoji usage (0-3) ---
        emoji_count = _count_emojis(subject)
        if emoji_count >= 4:
            risk += 3
            flags.append({
                "severity": "high",
                "item": f"{emoji_count} emojis in subject line",
                "recommendation": "Limit to 1–2 emojis max. Overuse triggers spam filters and looks unprofessional."
            })
        elif emoji_count >= 2:
            risk += 1
            flags.append({
                "severity": "low",
                "item": f"{emoji_count} emojis in subject line",
                "recommendation": "Consider reducing to one emoji for better deliverability."
            })

        # --- Length issues (0-2) ---
        char_count = len(subject)
        if char_count < 10:
            risk += 2
            flags.append({
                "severity": "medium",
                "item": f"Subject line is too short ({char_count} chars)",
                "recommendation": "Aim for 30–55 characters. Very short subjects often trigger spam filters."
            })
        elif char_count > 80:
            risk += 1
            flags.append({
                "severity": "low",
                "item": f"Subject line may be too long ({char_count} chars)",
                "recommendation": "Aim for 30–55 characters to avoid truncation and reduce spam signals."
            })

        risk = min(25, risk)
        self.flagged_items.extend([{**f, "category": "Subject Line"} for f in flags])
        return {"score": risk, "max": 25, "label": "Subject Line Signals", "flags": flags,
                "details": {"trigger_words": found_triggers, "char_count": char_count, "emoji_count": emoji_count}}

    # ─────────────────────────────────────────────────────────────────────────
    # Category B: Body Copy Spam Signals  (max risk: 30)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_body(self):
        body = self.body_text
        risk = 0
        flags = []

        if not body:
            return {"score": 0, "max": 30, "label": "Body Copy", "flags": []}

        body_lower = body.lower()
        words = re.findall(r'\b\w+\b', body_lower)
        word_count = len(words)

        # --- Spam trigger phrases (0-10) ---
        found_triggers = []
        for phrase in SPAM_TRIGGER_WORDS:
            if phrase in body_lower:
                found_triggers.append(phrase)

        # Also check HIGH_RISK_WORDS standalone
        for word in HIGH_RISK_WORDS:
            if re.search(r'\b' + re.escape(word) + r'\b', body_lower) and word not in found_triggers:
                found_triggers.append(word)

        trigger_density = (len(found_triggers) / max(word_count, 1)) * 100
        trigger_risk = min(10, int(trigger_density * 3) + (2 if len(found_triggers) > 0 else 0))
        risk += trigger_risk
        if found_triggers:
            flags.append({
                "severity": "high" if len(found_triggers) >= 5 else "medium",
                "item": f"{len(found_triggers)} spam trigger phrase(s) in body (e.g. {', '.join(found_triggers[:3])})",
                "recommendation": "Rewrite promotional phrases using natural, benefit-focused language. Avoid phrases like 'click here', 'act now', 'free money'."
            })

        # --- Repetitive keyword usage (0-5) ---
        if word_count > 20:
            word_freq = {}
            for w in words:
                if len(w) > 4:  # only meaningful words
                    word_freq[w] = word_freq.get(w, 0) + 1
            repeated = {w: c for w, c in word_freq.items() if (c / word_count) > 0.04 and c > 3}
            if repeated:
                top_repeated = sorted(repeated.items(), key=lambda x: -x[1])[:3]
                rep_risk = min(5, len(repeated) * 2)
                risk += rep_risk
                flags.append({
                    "severity": "medium",
                    "item": f"Keyword repetition: {', '.join([f'{w}({c}x)' for w, c in top_repeated])}",
                    "recommendation": "Vary your language. Repeating the same key terms signals keyword stuffing to spam filters."
                })

        # --- Over-promotional density (0-5) ---
        promo_patterns = [
            r"(?i)(buy now|order today|purchase now|shop now|order here|get yours)",
            r"(?i)(special (offer|deal|discount|price|promo))",
            r"(?i)(for (just|only)\s*\$[\d,]+)",
            r"(?i)(\d+%\s*off|save\s+\d+%|discount of\s+\d+%)",
            r"(?i)(best (deal|price|offer|value))",
        ]
        promo_matches = sum(1 for p in promo_patterns if re.search(p, body))
        promo_risk = min(5, promo_matches * 2)
        risk += promo_risk
        if promo_matches >= 2:
            flags.append({
                "severity": "medium",
                "item": f"High promotional density ({promo_matches} overtly promotional patterns)",
                "recommendation": "Lead with value and context before making offers. Heavy promotional density trips spam filters."
            })

        # --- Urgency manipulation (0-5) ---
        urgency_matches = []
        for pattern in URGENCY_MANIPULATION_PATTERNS:
            m = re.search(pattern, body)
            if m:
                urgency_matches.append(m.group(0))
        urgency_risk = min(5, len(urgency_matches) * 2)
        risk += urgency_risk
        if urgency_matches:
            flags.append({
                "severity": "medium",
                "item": f"Manipulative urgency pattern(s): e.g. \"{urgency_matches[0][:60]}\"",
                "recommendation": "Replace artificial urgency with genuine reasons or real deadlines. Manufactured pressure damages trust."
            })

        # --- ALL CAPS sections (0-3) ---
        caps_words = [w for w in words if w.isupper() and len(w) > 3]
        if len(caps_words) >= 5:
            risk += 3
            flags.append({
                "severity": "high",
                "item": f"{len(caps_words)} all-caps words in body",
                "recommendation": "Remove uppercase sections. ALL CAPS is a major spam signal and reduces readability."
            })
        elif len(caps_words) >= 2:
            risk += 1

        # --- Text-to-link ratio (0-2) ---
        link_count = len(self.all_urls)
        if link_count > 0 and word_count > 0:
            words_per_link = word_count / link_count
            if words_per_link < 25:
                risk += 2
                flags.append({
                    "severity": "medium",
                    "item": f"Low text-to-link ratio (~{int(words_per_link)} words per link)",
                    "recommendation": "Reduce the number of links or add more substantive content. Too many links relative to text is a spam signal."
                })

        risk = min(30, risk)
        self.flagged_items.extend([{**f, "category": "Body Copy"} for f in flags])
        return {"score": risk, "max": 30, "label": "Body Copy Signals", "flags": flags,
                "details": {"word_count": word_count, "trigger_count": len(found_triggers),
                            "trigger_density_pct": round(trigger_density, 1)}}

    # ─────────────────────────────────────────────────────────────────────────
    # Category C: Link & CTA Analysis  (max risk: 20)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_links(self):
        risk = 0
        flags = []
        urls = self.all_urls

        # --- Link count (0-5) ---
        link_count = len(urls)
        if link_count > 15:
            risk += 5
            flags.append({
                "severity": "high",
                "item": f"{link_count} links in email",
                "recommendation": "Reduce to 3–5 links max. Emails with many links are heavily penalized by spam filters."
            })
        elif link_count > 8:
            risk += 3
            flags.append({
                "severity": "medium",
                "item": f"{link_count} links in email",
                "recommendation": "Consider reducing links to under 8 for better deliverability."
            })
        elif link_count > 5:
            risk += 1

        # --- URL shorteners (0-5) ---
        shortener_urls = []
        for url in urls:
            parsed = urlparse(url if url.startswith("http") else "https://" + url)
            domain = parsed.netloc.lower().replace("www.", "")
            if any(domain == s or domain.endswith("." + s) for s in URL_SHORTENERS):
                shortener_urls.append(url)

        shortener_risk = min(5, len(shortener_urls) * 3)
        risk += shortener_risk
        if shortener_urls:
            flags.append({
                "severity": "high",
                "item": f"URL shortener(s) detected: {', '.join(shortener_urls[:2])}",
                "recommendation": "Replace shortened URLs with full, transparent links. Shorteners are a strong spam signal and hide destination."
            })

        # --- Suspicious TLDs (0-4) ---
        suspicious_found = []
        for url in urls:
            parsed = urlparse(url if url.startswith("http") else "https://" + url)
            domain = parsed.netloc.lower()
            for tld in SUSPICIOUS_TLDS:
                if domain.endswith(tld):
                    suspicious_found.append(url)
                    break

        if suspicious_found:
            risk += min(4, len(suspicious_found) * 2)
            flags.append({
                "severity": "high",
                "item": f"Suspicious TLD(s): {', '.join(suspicious_found[:2])}",
                "recommendation": "Use .com, .org, .net or established ccTLDs. Low-reputation TLDs dramatically increase spam score."
            })

        # --- Phishing / typosquat link detection (0-5) ---
        phishing_brand_patterns = [
            r'paypa[l1]', r'app[l1]e', r'amaz[o0]n', r'g[o0]{2}g[l1]e',
            r'micr[o0]s[o0]ft', r'faceb[o0]{2}k', r'netf[l1]ix',
        ]
        phishing_subdomain_patterns = [
            r'-secure\.', r'-verify\.', r'-account\.', r'-login\.', r'-update\.',
            r'login-\.', r'secure-\.', r'verify-\.', r'account-\.',
        ]
        all_phishing_patterns = phishing_brand_patterns + phishing_subdomain_patterns

        phishing_urls = []
        for url in urls:
            parsed = urlparse(url if url.startswith("http") else "https://" + url)
            hostname = parsed.netloc.lower()
            for pat in all_phishing_patterns:
                if re.search(pat, hostname, re.IGNORECASE):
                    phishing_urls.append(url)
                    break

        if phishing_urls:
            phishing_risk = min(5, len(phishing_urls) * 3)
            risk += phishing_risk
            flags.append({
                "severity": "high",
                "item": f"Possible phishing/typosquat URL(s): {', '.join(phishing_urls[:3])}",
                "recommendation": "Remove or replace suspicious URLs that mimic well-known brands. Typosquat and phishing links trigger aggressive spam filtering and erode recipient trust."
            })

        # --- Non-HTTPS URLs (0-3) ---
        http_only = [u for u in urls if u.startswith("http://")]
        if http_only:
            risk += min(3, len(http_only) * 2)
            flags.append({
                "severity": "medium",
                "item": f"{len(http_only)} non-HTTPS link(s)",
                "recommendation": "Use HTTPS for all links. Plain HTTP signals insecurity and can trigger spam filters."
            })

        # --- CTA phrasing risk (0-3) ---
        all_cta_text = " ".join(self.cta_texts).lower() if self.cta_texts else ""
        body_lower = self.body_text.lower()
        risky_ctas = [phrase for phrase in HIGH_RISK_CTA_PHRASES
                      if phrase in all_cta_text or phrase in body_lower]
        if risky_ctas:
            risk += min(3, len(risky_ctas) * 2)
            flags.append({
                "severity": "medium",
                "item": f"Risky CTA phrase(s): {', '.join(risky_ctas[:3])}",
                "recommendation": f"Replace '{risky_ctas[0]}' with action-specific, value-oriented language like 'Get Your Free Guide' or 'Start My Trial'."
            })

        risk = min(20, risk)
        self.flagged_items.extend([{**f, "category": "Links & CTAs"} for f in flags])
        return {"score": risk, "max": 20, "label": "Link & CTA Signals", "flags": flags,
                "details": {"link_count": link_count, "shortener_count": len(shortener_urls),
                            "suspicious_tld_count": len(suspicious_found)}}

    # ─────────────────────────────────────────────────────────────────────────
    # Category D: Structural & Compliance Signals  (max risk: 15)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_structure(self):
        risk = 0
        flags = []
        body_full = self.raw_body
        body_lower = body_full.lower()

        # --- Unsubscribe language (0-5) ---
        has_unsubscribe = any(re.search(p, body_full) for p in UNSUBSCRIBE_PATTERNS)
        if not has_unsubscribe and not self.is_transactional:
            risk += 5
            flags.append({
                "severity": "high",
                "item": "No unsubscribe option detected",
                "recommendation": "Add a clear unsubscribe link or opt-out mechanism. Required by CAN-SPAM, GDPR, and CASL — and missing one is a top spam signal."
            })
        elif not has_unsubscribe and self.is_transactional:
            risk += 2
            flags.append({
                "severity": "low",
                "item": "No unsubscribe option (transactional email)",
                "recommendation": "Even transactional emails benefit from preference management links."
            })

        # --- Physical mailing address (0-4) ---
        has_address = any(re.search(p, body_full, re.IGNORECASE) for p in ADDRESS_PATTERNS)
        if not has_address and not self.is_cold_email:
            risk += 4
            flags.append({
                "severity": "high",
                "item": "No physical mailing address detected",
                "recommendation": "Include a physical or P.O. Box address in the footer. Required by CAN-SPAM law for commercial emails."
            })

        # --- Plain-text readability (0-3) ---
        if self.is_html_body and self.body_soup:
            # Check image-to-text ratio
            images = self.body_soup.find_all('img')
            text_len = len(self.body_text.split())
            if images and text_len < 50:
                risk += 3
                flags.append({
                    "severity": "high",
                    "item": f"Very low text content relative to {len(images)} image(s)",
                    "recommendation": "Add meaningful text content. Image-heavy emails with little text are flagged heavily by spam filters."
                })
            elif len(images) > 5 and text_len < 100:
                risk += 2
                flags.append({
                    "severity": "medium",
                    "item": "Low text-to-image ratio",
                    "recommendation": "Balance images with substantive text. A 60/40 text-to-image ratio is ideal."
                })

            # Check for style-hidden text
            hidden_text_patterns = [
                r'(?i)(color:\s*#?fff(fff)?|color:\s*white)',
                r'(?i)(font-size:\s*0)',
                r'(?i)(display:\s*none)',
                r'(?i)(visibility:\s*hidden)',
            ]
            for p in hidden_text_patterns:
                if re.search(p, body_full):
                    risk += 3
                    flags.append({
                        "severity": "high",
                        "item": "Hidden/invisible text detected in HTML",
                        "recommendation": "Remove all hidden text. Invisible text is a black-hat spam technique that causes immediate filtering."
                    })
                    break

            # Check for form elements (phishing indicator)
            if re.search(r'(?i)<form|<input.*type=["\']password', body_full):
                risk += 3
                flags.append({
                    "severity": "high",
                    "item": "Form elements detected in email (common phishing indicator)",
                    "recommendation": "Remove all form elements. Legitimate emails link to web forms rather than embedding them. Forms in email are a major phishing signal."
                })

            # Check for JavaScript
            if re.search(r'(?i)<script|javascript:|on\w+=', body_full):
                risk += 3
                flags.append({
                    "severity": "high",
                    "item": "JavaScript detected in email HTML",
                    "recommendation": "Remove all JavaScript. Most email clients block scripts entirely, and their presence triggers spam filters."
                })

            # Check for iframes
            if re.search(r'(?i)<iframe', body_full):
                risk += 2
                flags.append({
                    "severity": "high",
                    "item": "Iframe element detected in email",
                    "recommendation": "Remove iframe elements. They are blocked by virtually all email clients and signal spam or phishing."
                })

            # Check for excessive base64 encoded images
            base64_count = len(re.findall(r'data:image/[^;]+;base64', body_full))
            if base64_count > 3:
                risk += 2
                flags.append({
                    "severity": "medium",
                    "item": f"{base64_count} base64 encoded images detected",
                    "recommendation": "Host images on your server instead of embedding base64 data. Excessive inline images increase email size and trigger spam filters."
                })

        # --- Very long lines in plain text (0-2) ---
        if not self.is_html_body:
            lines = self.raw_body.split('\n')
            long_lines = [l for l in lines if len(l) > 998]
            if long_lines:
                risk += 2
                flags.append({
                    "severity": "medium",
                    "item": f"{len(long_lines)} line(s) exceeding 998 characters",
                    "recommendation": "Wrap lines at 76–998 characters. Some mail servers reject or mangle emails with very long lines."
                })

        risk = min(15, risk)
        self.flagged_items.extend([{**f, "category": "Structure & Compliance"} for f in flags])
        return {"score": risk, "max": 15, "label": "Structure & Compliance", "flags": flags,
                "details": {"has_unsubscribe": has_unsubscribe, "has_address": has_address}}

    # ─────────────────────────────────────────────────────────────────────────
    # Category E: Sender Context Heuristics  (max risk: 10)
    # ─────────────────────────────────────────────────────────────────────────
    def _score_sender_context(self):
        risk = 0
        flags = []
        body_lower = self.body_text.lower()

        # --- Transactional vs promotional mismatch (0-5) ---
        if self.is_transactional:
            promo_density_patterns = [
                r"(?i)(special offer|discount|sale|promo|deal|buy now|shop now|order today)",
                r"(?i)(subscribe|newsletter|marketing|campaign)",
                r"(?i)(check out (our|these|the) (new|latest|best))",
            ]
            promo_count = sum(1 for p in promo_density_patterns if re.search(p, body_lower))
            if promo_count >= 2:
                risk += 5
                flags.append({
                    "severity": "high",
                    "item": "Promotional content in a transactional email",
                    "recommendation": "Keep transactional emails purely transactional. Mixing promotional content risks losing transactional email status and high deliverability."
                })
            elif promo_count == 1:
                risk += 2
                flags.append({
                    "severity": "low",
                    "item": "Slight promotional tone in transactional email",
                    "recommendation": "Minimize promotional language in transactional emails to protect deliverability."
                })

        # --- Cold email risk patterns (0-5) ---
        if self.is_cold_email:
            cold_risk_patterns = [
                (r"(?i)(dear (sir|madam|friend|email|recipient))", "Generic salutation for cold outreach"),
                (r"(?i)(to whom it may concern)", "Impersonal opener"),
                (r"(?i)(this is not spam|this is not junk|this is a legitimate)", "Claiming legitimacy proactively"),
                (r"(?i)(i (found|came across) your (email|contact|name|profile) online)", "Explains cold contact in risky way"),
            ]
            for pattern, description in cold_risk_patterns:
                if re.search(pattern, body_lower) or re.search(pattern, self.subject.lower()):
                    risk += 2
                    flags.append({
                        "severity": "medium",
                        "item": description,
                        "recommendation": "Cold emails perform better with personalized, research-based openers. Avoid generic intros."
                    })

        # --- Sender name vs content alignment ---
        if self.sender_email:
            domain = self.sender_email.split("@")[-1].lower() if "@" in self.sender_email else ""
            free_providers = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                              "aol.com", "protonmail.com", "icloud.com"]
            if domain in free_providers and not self.is_cold_email:
                risk += 2
                flags.append({
                    "severity": "medium",
                    "item": f"Sending from free email provider ({domain})",
                    "recommendation": "Use a custom domain email address for professional campaigns. Free providers signal lower sender reputation."
                })

        risk = min(10, risk)
        self.flagged_items.extend([{**f, "category": "Sender Context"} for f in flags])
        return {"score": risk, "max": 10, "label": "Sender Context", "flags": flags}

    # ─────────────────────────────────────────────────────────────────────────
    # Main analysis entry point
    # ─────────────────────────────────────────────────────────────────────────
    def analyze(self) -> dict:
        cat_a = self._score_subject()
        cat_b = self._score_body()
        cat_c = self._score_links()
        cat_d = self._score_structure()
        cat_e = self._score_sender_context()

        total = cat_a["score"] + cat_b["score"] + cat_c["score"] + cat_d["score"] + cat_e["score"]
        total = min(100, total)

        if total <= 20:
            label = "Very Low Risk"
            color = "green"
            summary = "This email has minimal spam signals. It should pass most spam filters without issue."
        elif total <= 40:
            label = "Low Risk"
            color = "blue"
            summary = "A few minor spam signals detected. Address the flagged items to maximize deliverability."
        elif total <= 60:
            label = "Moderate Risk"
            color = "yellow"
            summary = "Meaningful spam signals found. Several items need attention before sending to a large list."
        elif total <= 80:
            label = "High Risk"
            color = "orange"
            summary = "High spam risk. This email is likely to be filtered or placed in spam by major providers."
        else:
            label = "Very High Risk"
            color = "red"
            summary = "Extreme spam risk. Major restructuring of content, structure, and CTAs is required."

        # Sort flagged items by severity
        severity_order = {"high": 0, "medium": 1, "low": 2}
        sorted_flags = sorted(self.flagged_items, key=lambda x: severity_order.get(x.get("severity", "low"), 2))

        # Top recommendations (deduplicated)
        top_recs = []
        seen_recs = set()
        for flag in sorted_flags:
            rec = flag.get("recommendation", "")
            if rec and rec not in seen_recs:
                top_recs.append({
                    "category": flag.get("category", ""),
                    "severity": flag.get("severity", "low"),
                    "item": flag.get("item", ""),
                    "recommendation": rec
                })
                seen_recs.add(rec)

        return {
            "score": total,
            "label": label,
            "color": color,
            "summary": summary,
            "categories": [cat_a, cat_b, cat_c, cat_d, cat_e],
            "high_risk_elements": [f for f in sorted_flags if f.get("severity") == "high"],
            "top_recommendations": top_recs[:10],
        }
