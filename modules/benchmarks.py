"""
InbXr — Industry Benchmarks
Hardcoded benchmark ranges based on email marketing performance data.
Returns percentile rankings and comparisons for analysis results.
"""

# ── Benchmark data per industry ────────────────────────
# Format: { metric: { "avg": average, "p25": 25th percentile, "p75": 75th percentile, "p90": 90th } }
# Spam: lower = better. Copy/Readability: higher = better.

_BENCHMARKS = {
    "SaaS": {
        "spam_score":        {"avg": 28, "p25": 38, "p75": 18, "p90": 10},
        "copy_score":        {"avg": 58, "p25": 45, "p75": 70, "p90": 82},
        "readability_score": {"avg": 62, "p25": 50, "p75": 74, "p90": 85},
        "subject_length":    {"avg": 44, "p25": 30, "p75": 55, "p90": 60},
        "body_word_count":   {"avg": 210, "p25": 120, "p75": 320, "p90": 450},
    },
    "Ecommerce": {
        "spam_score":        {"avg": 35, "p25": 48, "p75": 22, "p90": 12},
        "copy_score":        {"avg": 55, "p25": 40, "p75": 68, "p90": 78},
        "readability_score": {"avg": 68, "p25": 55, "p75": 78, "p90": 88},
        "subject_length":    {"avg": 40, "p25": 28, "p75": 52, "p90": 58},
        "body_word_count":   {"avg": 150, "p25": 80, "p75": 240, "p90": 350},
    },
    "Info Products": {
        "spam_score":        {"avg": 42, "p25": 55, "p75": 28, "p90": 16},
        "copy_score":        {"avg": 62, "p25": 48, "p75": 74, "p90": 85},
        "readability_score": {"avg": 58, "p25": 45, "p75": 70, "p90": 80},
        "subject_length":    {"avg": 48, "p25": 35, "p75": 60, "p90": 68},
        "body_word_count":   {"avg": 380, "p25": 200, "p75": 550, "p90": 750},
    },
    "Finance": {
        "spam_score":        {"avg": 22, "p25": 32, "p75": 14, "p90": 8},
        "copy_score":        {"avg": 52, "p25": 38, "p75": 64, "p90": 75},
        "readability_score": {"avg": 55, "p25": 42, "p75": 66, "p90": 76},
        "subject_length":    {"avg": 42, "p25": 30, "p75": 52, "p90": 58},
        "body_word_count":   {"avg": 190, "p25": 110, "p75": 280, "p90": 400},
    },
    "Health": {
        "spam_score":        {"avg": 38, "p25": 50, "p75": 25, "p90": 14},
        "copy_score":        {"avg": 56, "p25": 42, "p75": 68, "p90": 80},
        "readability_score": {"avg": 60, "p25": 48, "p75": 72, "p90": 82},
        "subject_length":    {"avg": 45, "p25": 32, "p75": 56, "p90": 64},
        "body_word_count":   {"avg": 250, "p25": 140, "p75": 380, "p90": 500},
    },
    "Local Services": {
        "spam_score":        {"avg": 30, "p25": 42, "p75": 20, "p90": 10},
        "copy_score":        {"avg": 50, "p25": 36, "p75": 62, "p90": 74},
        "readability_score": {"avg": 70, "p25": 58, "p75": 80, "p90": 90},
        "subject_length":    {"avg": 38, "p25": 26, "p75": 48, "p90": 55},
        "body_word_count":   {"avg": 130, "p25": 70, "p75": 200, "p90": 300},
    },
    "Political": {
        "spam_score":        {"avg": 45, "p25": 58, "p75": 30, "p90": 18},
        "copy_score":        {"avg": 60, "p25": 46, "p75": 72, "p90": 84},
        "readability_score": {"avg": 56, "p25": 44, "p75": 68, "p90": 78},
        "subject_length":    {"avg": 50, "p25": 36, "p75": 62, "p90": 70},
        "body_word_count":   {"avg": 280, "p25": 160, "p75": 420, "p90": 580},
    },
    "Other": {
        "spam_score":        {"avg": 32, "p25": 45, "p75": 20, "p90": 12},
        "copy_score":        {"avg": 54, "p25": 40, "p75": 66, "p90": 78},
        "readability_score": {"avg": 62, "p25": 50, "p75": 74, "p90": 84},
        "subject_length":    {"avg": 43, "p25": 30, "p75": 54, "p90": 62},
        "body_word_count":   {"avg": 200, "p25": 100, "p75": 320, "p90": 450},
    },
}


def get_benchmarks(industry: str, spam_score: int, copy_score: int,
                   readability_score: int = None,
                   subject_length: int = None,
                   body_word_count: int = None) -> dict:
    """Compare scores against industry benchmarks. Returns benchmark data with percentiles."""
    bench = _BENCHMARKS.get(industry, _BENCHMARKS["Other"])
    results = {}

    # Spam (lower is better — invert percentile logic)
    spam_b = bench["spam_score"]
    spam_pct = _calc_percentile_inverted(spam_score, spam_b)
    spam_vs = spam_b["avg"] - spam_score  # positive = better than avg
    results["spam"] = {
        "your_score": spam_score,
        "industry_avg": spam_b["avg"],
        "percentile": spam_pct,
        "vs_avg": spam_vs,
        "label": _pct_label(spam_pct),
        "detail": f"{'Lower' if spam_vs > 0 else 'Higher'} than {abs(spam_vs)} pts vs {industry} average"
            if spam_vs != 0 else f"Right at the {industry} average",
    }

    # Copy (higher is better)
    copy_b = bench["copy_score"]
    copy_pct = _calc_percentile(copy_score, copy_b)
    copy_vs = copy_score - copy_b["avg"]
    results["copy"] = {
        "your_score": copy_score,
        "industry_avg": copy_b["avg"],
        "percentile": copy_pct,
        "vs_avg": copy_vs,
        "label": _pct_label(copy_pct),
        "detail": f"{'Above' if copy_vs > 0 else 'Below'} {abs(copy_vs)} pts vs {industry} average"
            if copy_vs != 0 else f"Right at the {industry} average",
    }

    # Readability (higher is better)
    if readability_score is not None:
        read_b = bench["readability_score"]
        read_pct = _calc_percentile(readability_score, read_b)
        read_vs = readability_score - read_b["avg"]
        results["readability"] = {
            "your_score": readability_score,
            "industry_avg": read_b["avg"],
            "percentile": read_pct,
            "vs_avg": read_vs,
            "label": _pct_label(read_pct),
            "detail": f"{'Above' if read_vs > 0 else 'Below'} {abs(read_vs)} pts vs {industry} average"
                if read_vs != 0 else f"Right at the {industry} average",
        }

    # Subject length (closer to avg = better, informational)
    if subject_length is not None:
        subj_b = bench["subject_length"]
        results["subject_length"] = {
            "your_value": subject_length,
            "industry_avg": subj_b["avg"],
            "optimal_range": f"{subj_b['p25']}-{subj_b['p75']}",
            "in_range": subj_b["p25"] <= subject_length <= subj_b["p75"],
        }

    # Body word count (informational)
    if body_word_count is not None:
        body_b = bench["body_word_count"]
        results["body_word_count"] = {
            "your_value": body_word_count,
            "industry_avg": body_b["avg"],
            "optimal_range": f"{body_b['p25']}-{body_b['p75']}",
            "in_range": body_b["p25"] <= body_word_count <= body_b["p75"],
        }

    results["industry"] = industry

    return results


def _calc_percentile(score: int, bench: dict) -> int:
    """Calculate approximate percentile (higher is better)."""
    if score >= bench["p90"]:
        return min(99, 90 + int((score - bench["p90"]) / max(1, 100 - bench["p90"]) * 9))
    elif score >= bench["p75"]:
        return 75 + int((score - bench["p75"]) / max(1, bench["p90"] - bench["p75"]) * 15)
    elif score >= bench["avg"]:
        return 50 + int((score - bench["avg"]) / max(1, bench["p75"] - bench["avg"]) * 25)
    elif score >= bench["p25"]:
        return 25 + int((score - bench["p25"]) / max(1, bench["avg"] - bench["p25"]) * 25)
    else:
        return max(1, int(score / max(1, bench["p25"]) * 25))


def _calc_percentile_inverted(score: int, bench: dict) -> int:
    """Calculate approximate percentile for inverted metrics (lower is better)."""
    # For spam: p25=38 means 25th percentile has score 38 (worse), p90=10 means top 10% has score 10
    if score <= bench["p90"]:
        return min(99, 90 + int((bench["p90"] - score) / max(1, bench["p90"]) * 9))
    elif score <= bench["p75"]:
        return 75 + int((bench["p75"] - score) / max(1, bench["p75"] - bench["p90"]) * 15)
    elif score <= bench["avg"]:
        return 50 + int((bench["avg"] - score) / max(1, bench["avg"] - bench["p75"]) * 25)
    elif score <= bench["p25"]:
        return 25 + int((bench["p25"] - score) / max(1, bench["p25"] - bench["avg"]) * 25)
    else:
        return max(1, int((100 - score) / max(1, 100 - bench["p25"]) * 25))


def _pct_label(pct: int) -> str:
    """Human-readable percentile label."""
    if pct >= 90:
        return f"Top {100 - pct}%"
    elif pct >= 75:
        return f"Top {100 - pct}%"
    elif pct >= 50:
        return "Above average"
    elif pct >= 25:
        return "Below average"
    else:
        return f"Bottom {100 - pct}%"
