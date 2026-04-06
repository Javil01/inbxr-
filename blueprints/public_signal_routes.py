"""
InbXr — Public signal marketing routes.

Public-facing (no auth) pages that support the 7 Inbox Signals positioning:

- /insights       Aggregate stats from the Signal Score engine (data proof page)
- /methodology    How each signal is calculated + what we don't fake (trust page)
- /quiz           Pre-signup "What's your weakest signal?" 6-question quiz

All routes are indexable and designed to rank for positioning keywords.
"""

import logging

from flask import Blueprint, render_template, jsonify, request

from modules.database import fetchone, fetchall

logger = logging.getLogger("inbxr.public_signal_routes")

public_signal_bp = Blueprint("public_signal", __name__)


# ── /insights — aggregate data proof page ────────────────

@public_signal_bp.route("/insights")
def insights_page():
    """
    Public data proof page. Shows anonymous aggregate stats from the
    signal_scores and contact_segments tables so visitors can see that
    the 7 signals are being calculated against real data.

    Numbers are aggregate-only — no PII, no per-user breakdown.
    """
    stats = _compute_aggregate_insights()
    return render_template(
        "public/insights.html",
        stats=stats,
        allow_index=True,
        title="Email Deliverability Insights",
    )


def _compute_aggregate_insights():
    """Compute aggregate stats for the public insights page."""
    stats = {
        'total_lists_scored': 0,
        'avg_signal_score': 0,
        'grade_distribution': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0},
        'mpp_inflation_pct': 0,
        'dmarc_compliance_pct': 0,
        'dormancy_risk_avg_pct': 0,
        'total_contacts_analyzed': 0,
    }

    try:
        # Total lists scored + average + grade distribution
        agg = fetchone(
            """SELECT
                COUNT(*) as total,
                AVG(total_signal_score) as avg_score,
                SUM(total_contacts) as total_contacts
               FROM signal_scores"""
        )
        if agg and agg['total']:
            stats['total_lists_scored'] = agg['total'] or 0
            stats['avg_signal_score'] = round(agg['avg_score'] or 0, 1)
            stats['total_contacts_analyzed'] = agg['total_contacts'] or 0

        grades = fetchall(
            """SELECT signal_grade, COUNT(*) as cnt
               FROM signal_scores
               GROUP BY signal_grade"""
        )
        for g in grades or []:
            if g['signal_grade'] in stats['grade_distribution']:
                stats['grade_distribution'][g['signal_grade']] = g['cnt']

        # MPP-flagged contacts as % of total
        mpp_row = fetchone(
            """SELECT
                COUNT(CASE WHEN likely_mpp_opener = 1 THEN 1 END) as mpp_flagged,
                COUNT(*) as total
               FROM contact_segments"""
        )
        if mpp_row and mpp_row['total']:
            stats['mpp_inflation_pct'] = round(
                (mpp_row['mpp_flagged'] or 0) * 100.0 / mpp_row['total'], 1
            )

        # Dormancy: contacts with days_since_engagement > 180 as % of total
        dormancy_row = fetchone(
            """SELECT
                COUNT(CASE WHEN days_since_engagement > 180 THEN 1 END) as dormant,
                COUNT(*) as total
               FROM contact_segments
               WHERE days_since_engagement IS NOT NULL"""
        )
        if dormancy_row and dormancy_row['total']:
            stats['dormancy_risk_avg_pct'] = round(
                (dormancy_row['dormant'] or 0) * 100.0 / dormancy_row['total'], 1
            )

    except Exception:
        logger.exception("aggregate insights compute failed")

    return stats


# ── /methodology — trust page ────────────────────────────

@public_signal_bp.route("/methodology")
def methodology_page():
    """
    Public trust / methodology page. Walks through each signal's formula,
    explicitly calls out what InbXr does NOT claim (spam trap measurement,
    predictive day counts, etc.). This is the "honest competitive moat" —
    no competitor will be this transparent.
    """
    return render_template(
        "public/methodology.html",
        allow_index=True,
        title="How InbXr Calculates the 7 Signals",
    )


# ── /quiz — "What's your weakest signal?" lead magnet ────

# Static quiz definition. 6 questions, each maps answers to signal weights.
# Lowest scoring signal = the "weakest" one the user is told to focus on.

QUIZ_QUESTIONS = [
    {
        "id": "q1_bounces",
        "text": "When was the last time you ran a list verification pass on your email list?",
        "signal": "bounce_exposure",
        "options": [
            ("Within the last 30 days", 10),
            ("1-3 months ago", 7),
            ("3-12 months ago", 4),
            ("More than a year ago", 2),
            ("Never", 0),
        ],
    },
    {
        "id": "q2_mpp",
        "text": "How do you adjust your open rate for Apple Mail Privacy Protection?",
        "signal": "engagement_trajectory",
        "options": [
            ("I strip MPP opens using User-Agent or timing detection", 10),
            ("I filter out @icloud.com addresses", 3),
            ("I know it affects my numbers but I don't adjust", 5),
            ("I don't know what MPP is", 0),
        ],
    },
    {
        "id": "q3_acquisition",
        "text": "Do you track engagement by acquisition cohort (i.e., by where contacts came from)?",
        "signal": "acquisition_quality",
        "options": [
            ("Yes, I segment and report by source monthly", 10),
            ("Yes, but only for the biggest channels", 7),
            ("I have the data but don't segment it", 4),
            ("No, I look at blended list metrics only", 0),
        ],
    },
    {
        "id": "q4_domain",
        "text": "How often do you check your sending domain against blocklists?",
        "signal": "domain_reputation",
        "options": [
            ("Automated monitoring, alerts on hits", 10),
            ("Manual checks weekly or monthly", 6),
            ("Only when something goes wrong", 2),
            ("Never", 0),
        ],
    },
    {
        "id": "q5_dormancy",
        "text": "What percentage of your list has been inactive for 365+ days?",
        "signal": "dormancy_risk",
        "options": [
            ("Less than 5%", 10),
            ("5-15%", 7),
            ("15-30%", 3),
            ("More than 30%", 0),
            ("I don't know", 1),
        ],
    },
    {
        "id": "q6_auth",
        "text": "What's your current DMARC policy?",
        "signal": "authentication_standing",
        "options": [
            ("p=reject with alignment", 10),
            ("p=quarantine", 8),
            ("p=none", 3),
            ("I don't have DMARC", 0),
            ("I don't know", 0),
        ],
    },
]


@public_signal_bp.route("/quiz")
def quiz_page():
    """Public quiz page. Renders the 6 questions + collects answers via JS."""
    return render_template(
        "public/quiz.html",
        questions=QUIZ_QUESTIONS,
        allow_index=True,
        title="What's Your Weakest Inbox Signal? 60-second Quiz",
    )


@public_signal_bp.route("/quiz/score", methods=["POST"])
def quiz_score():
    """
    Score a completed quiz. Expects JSON: {answers: {q1_bounces: "...", ...}}
    Returns the weakest signal + a per-signal score summary.
    """
    data = request.get_json(silent=True) or {}
    answers = data.get("answers", {})

    scores = {}
    for q in QUIZ_QUESTIONS:
        user_choice = answers.get(q["id"], "")
        found = 0
        for option_text, option_score in q["options"]:
            if option_text == user_choice:
                found = option_score
                break
        scores[q["signal"]] = found

    # Weakest signal = lowest score
    if scores:
        weakest = min(scores.items(), key=lambda x: x[1])
        weakest_signal = weakest[0]
        weakest_score = weakest[1]
    else:
        weakest_signal = None
        weakest_score = 0

    # Composite quiz grade (out of 60, normalized to 100 for display)
    total = sum(scores.values())
    composite = round(total * 100 / 60, 1) if scores else 0

    signal_copy_map = {
        "bounce_exposure": {
            "name": "Bounce Exposure",
            "action": "Run list verification and suppress role/disposable/catch-all addresses before your next send.",
        },
        "engagement_trajectory": {
            "name": "Engagement Trajectory (MPP-adjusted)",
            "action": "Start stripping MPP opens from your engagement metrics. Your 'active' segment is probably much smaller than your dashboard shows.",
        },
        "acquisition_quality": {
            "name": "Acquisition Quality",
            "action": "Segment your engagement reporting by acquisition source. One of your channels is probably dragging the blended number down.",
        },
        "domain_reputation": {
            "name": "Domain Reputation",
            "action": "Set up automated blocklist monitoring and run Inboxer Sender Check on your domain right now.",
        },
        "dormancy_risk": {
            "name": "Dormancy Risk",
            "action": "Suppress contacts inactive for 365+ days and run a re-engagement sequence on the 180-day cohort.",
        },
        "authentication_standing": {
            "name": "Authentication Standing",
            "action": "Move your DMARC policy off p=none. Microsoft's May 2025 enforcement rejects p=none for bulk senders.",
        },
    }

    weakest_info = signal_copy_map.get(weakest_signal, {
        "name": "Unknown",
        "action": "Run a full Signal Score against your list to diagnose.",
    })

    return jsonify({
        "ok": True,
        "composite_score": composite,
        "signal_scores": scores,
        "weakest_signal": weakest_signal,
        "weakest_name": weakest_info["name"],
        "weakest_action": weakest_info["action"],
    })
