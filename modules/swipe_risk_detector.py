"""
InbXr — Swipe File Risk Detector
Flags email copy that looks like a widely-reused template. This is a
Copy Intelligence sub-check, NOT an 8th Inbox Signal — see SIGNAL_SPEC.md.

Three layers:
  1. Shingle (7-gram) Jaccard similarity against a curated swipe corpus
  2. Regex scan for famous opener / closer / follow-up / urgency / LLM-filler clichés
  3. Optional Groq LLM originality rating (skipped if GROQ_API_KEY not set)

Composite score: 0 = fully original, 100 = essentially a copied swipe.
"""

import json
import logging
import os
import re
import ssl
import time
from http.client import HTTPSConnection

from bs4 import BeautifulSoup

from data.swipe_corpus import SWIPE_TEMPLATES, SWIPE_CLICHE_PATTERNS

logger = logging.getLogger("inbxr.swipe_risk")

_SHINGLE_N = 7
_MAX_BODY_CHARS_FOR_LLM = 3000
_LLM_TIMEOUT = 8  # was 20s — too long; analysis runs inline in the request path


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    if re.search(r"<[a-zA-Z][^>]*>", raw):
        return BeautifulSoup(raw, "lxml").get_text(separator=" ", strip=True)
    return raw


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\{[^}]+\}", " ", text)        # drop merge-tag placeholders
    text = re.sub(r"[^a-z0-9\s]", " ", text)      # strip punctuation
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _shingles(text: str, n: int = _SHINGLE_N) -> set:
    tokens = _normalize(text).split()
    if len(tokens) < n:
        return set()
    return {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    if not inter:
        return 0.0
    return len(inter) / len(a | b)


# Precompile corpus shingles + cliche regexes once at import time.
_CORPUS_SHINGLES = [
    {"id": t["id"], "source": t["source"], "text": t["text"], "shingles": _shingles(t["text"])}
    for t in SWIPE_TEMPLATES
]
_COMPILED_CLICHES = [(re.compile(pat), category) for pat, category in SWIPE_CLICHE_PATTERNS]


class SwipeRiskDetector:
    def __init__(self, subject: str, body: str, is_cold_email: bool = False,
                 is_plain_text: bool = False):
        self.subject = (subject or "").strip()
        self.raw_body = body or ""
        self.plain_body = _strip_html(self.raw_body)
        self.combined_text = f"{self.subject}\n{self.plain_body}".strip()
        self.is_cold_email = is_cold_email
        self.is_plain_text = is_plain_text

    # ── 1. Shingle match ────────────────────────────────
    def _shingle_match(self) -> dict:
        body_shingles = _shingles(self.plain_body)
        matches = []
        top_similarity = 0.0
        for entry in _CORPUS_SHINGLES:
            sim = _jaccard(body_shingles, entry["shingles"])
            if sim >= 0.15:  # 15% shingle overlap is meaningful
                matches.append({
                    "source": entry["source"],
                    "template_id": entry["id"],
                    "snippet": entry["text"][:180] + ("…" if len(entry["text"]) > 180 else ""),
                    "similarity": round(sim, 3),
                })
            if sim > top_similarity:
                top_similarity = sim
        matches.sort(key=lambda m: m["similarity"], reverse=True)
        # Convert top similarity to 0-100 sub-score (0.6 Jaccard ~= verbatim reuse)
        sub_score = min(100, round(top_similarity * 140))
        return {"sub_score": sub_score, "matched_snippets": matches[:5],
                "top_similarity": round(top_similarity, 3)}

    # ── 2. Cliche scan ──────────────────────────────────
    def _cliche_scan(self) -> dict:
        hits = []
        seen_categories = set()
        for pattern, category in _COMPILED_CLICHES:
            m = pattern.search(self.combined_text)
            if m:
                if category in seen_categories:
                    continue
                seen_categories.add(category)
                hits.append({"phrase": m.group(0).strip()[:80], "category": category})
        word_count = max(1, len(_normalize(self.combined_text).split()))
        density = len(hits) / (word_count / 100.0)  # hits per 100 words
        # 3 hits per 100 words ≈ saturated cliché density → 100 sub-score
        sub_score = min(100, round(density * 33))
        return {"sub_score": sub_score, "cliche_hits": hits, "density_per_100w": round(density, 2)}

    # ── 3. Groq originality rating (optional) ───────────
    def _groq_originality(self) -> dict | None:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return None

        sample = self.plain_body[:_MAX_BODY_CHARS_FOR_LLM]
        if not sample.strip():
            return None

        system_msg = (
            "You are an expert email copywriter evaluating how ORIGINAL a piece of email "
            "copy is. Give a freshness rating from 0 (entirely derivative, reads exactly "
            "like a copied swipe-file template) to 100 (distinctive voice, specific details, "
            "nothing formulaic). Identify up to 3 specific lines that read as templated. "
            "Return ONLY valid JSON, no markdown."
        )
        user_msg = (
            f"SUBJECT: {self.subject}\n\nBODY:\n{sample}\n\n"
            "Return JSON with keys:\n"
            "  \"freshness\" (int 0-100),\n"
            "  \"template_lines\" (array of up to 3 short strings copied verbatim from the body that sound templated),\n"
            "  \"reasoning\" (one short sentence, <200 chars)."
        )
        payload = json.dumps({
            "model": os.environ.get("AI_MODEL", "llama-3.3-70b-versatile"),
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.2,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        })

        host = os.environ.get("AI_API_HOST", "api.groq.com")
        path = os.environ.get("AI_API_PATH", "/openai/v1/chat/completions")
        ctx = ssl.create_default_context()
        conn = HTTPSConnection(host, 443, timeout=_LLM_TIMEOUT, context=ctx)
        try:
            conn.request("POST", path, body=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8", errors="replace")
            if resp.status != 200:
                logger.warning("Groq originality rating failed: HTTP %s", resp.status)
                return None
            outer = json.loads(raw)
            content = outer["choices"][0]["message"]["content"]
            data = json.loads(content)
            freshness = int(data.get("freshness", 50))
            freshness = max(0, min(100, freshness))
            return {
                "freshness": freshness,
                "template_lines": [str(s)[:200] for s in (data.get("template_lines") or [])[:3]],
                "reasoning": str(data.get("reasoning", ""))[:300],
            }
        except Exception as e:
            logger.info("Groq originality rating skipped: %s", e)
            return None
        finally:
            conn.close()

    # ── Compose ─────────────────────────────────────────
    def analyze(self) -> dict:
        t0 = time.monotonic()
        shingle = self._shingle_match()
        cliche = self._cliche_scan()
        originality = self._groq_originality()

        # Weighted composite: shingle 50%, cliche 30%, (100 - freshness) 20%.
        # When Groq is unavailable, redistribute to 60/40.
        if originality is not None:
            llm_risk = 100 - originality["freshness"]
            score = round(0.5 * shingle["sub_score"] + 0.3 * cliche["sub_score"] + 0.2 * llm_risk)
        else:
            score = round(0.6 * shingle["sub_score"] + 0.4 * cliche["sub_score"])
        score = max(0, min(100, score))

        if score >= 65:
            label = "High Swipe Risk"
        elif score >= 35:
            label = "Some Template Patterns"
        else:
            label = "Original"

        flags = []
        if shingle["top_similarity"] >= 0.4:
            flags.append(
                f"Body closely matches a known swipe-file template "
                f"(Jaccard similarity {shingle['top_similarity']:.2f})."
            )
        elif shingle["top_similarity"] >= 0.2:
            flags.append("Body partially overlaps with a known swipe-file template.")
        if cliche["cliche_hits"]:
            flags.append(
                f"{len(cliche['cliche_hits'])} cliché phrase{'s' if len(cliche['cliche_hits']) != 1 else ''} detected "
                f"({cliche['density_per_100w']} per 100 words)."
            )
        if originality and originality["freshness"] < 40:
            flags.append(f"Low originality rating ({originality['freshness']}/100) — reads as templated.")
        if self.is_cold_email and score >= 35:
            flags.append(
                "Cold outreach with reused copy carries extra deliverability risk — "
                "ESPs fingerprint bulk-reused content across senders."
            )

        recommendations = _build_recommendations(
            shingle, cliche, originality, self.is_cold_email, score
        )

        return {
            "score": score,
            "label": label,
            "flags": flags,
            "matched_snippets": shingle["matched_snippets"],
            "cliche_hits": cliche["cliche_hits"],
            "top_similarity": shingle["top_similarity"],
            "cliche_density_per_100w": cliche["density_per_100w"],
            "originality_rating": originality,
            "recommendations": recommendations,
            "meta": {
                "elapsed_ms": round((time.monotonic() - t0) * 1000),
                "corpus_size": len(_CORPUS_SHINGLES),
                "cliche_patterns": len(_COMPILED_CLICHES),
                "groq_used": originality is not None,
            },
        }


def _build_recommendations(shingle: dict, cliche: dict, originality: dict | None,
                           is_cold: bool, score: int) -> list[str]:
    recs = []
    if shingle["top_similarity"] >= 0.3 and shingle["matched_snippets"]:
        top = shingle["matched_snippets"][0]
        recs.append(
            f"Rewrite the passages that match '{top['source']}'. Use a specific detail "
            "only you could know — a customer's name, a concrete number, yesterday's event."
        )
    if cliche["cliche_hits"]:
        examples = ", ".join(f"\"{h['phrase']}\"" for h in cliche["cliche_hits"][:3])
        recs.append(
            f"Replace cliché phrases like {examples}. These trigger pattern-based filters and bore readers."
        )
    if originality and originality.get("template_lines"):
        tl = originality["template_lines"][0]
        recs.append(f"Rewrite this templated line with your own voice: \"{tl[:100]}\"")
    if is_cold and score >= 35:
        recs.append(
            "For cold outreach specifically: every 100 senders using the same swipe dilutes "
            "the content fingerprint's reputation. Make each send recognizably yours."
        )
    if score < 35:
        recs.append("Copy reads as original — keep it up.")
    return recs
