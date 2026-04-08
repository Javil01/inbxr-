"""
InbXr — Public signal marketing routes.

Public-facing (no auth) pages that support the 7 Inbox Signals positioning:

- /insights                    Aggregate stats from the Signal Engine
- /methodology                 How each signal is calculated
- /<slug>-alternative          Competitor comparison pages (SEO)
- /why-am-i-in-spam            Unified spam diagnostic
- /inherited-list-first-aid    CSV triage (Remove / Re-engage / Keep)

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
    """CUT IN V1. The quiz is replaced by Domain Signal Score as the lead magnet.
    Redirect to /signal-score which is the stronger front door."""
    from flask import redirect
    return redirect("/signal-score", code=301)


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
            "name": "Spam Trap Exposure",
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


# ── Competitor comparison pages ─────────────────────────
#
# Each entry below renders as /<slug>-alternative (e.g. /zerobounce-alternative).
# The tone is respectful: we give each competitor credit for what they do well,
# honestly describe which of the 7 Inbox Signals they cover, and show what they
# miss. No trash talk. Buyers who search "[competitor] alternative" are usually
# frustrated with that tool; the worst move is to pile on and look petty.
#
# Signal coverage key:
#   01 Bounce Exposure       25 pts
#   02 Engagement Trajectory 25 pts
#   03 Acquisition Quality   15 pts
#   04 Domain Reputation     15 pts
#   05 Spam Trap Exposure    10 pts
#   06 Authentication        5 pts
#   07 Decay Velocity        5 pts

COMPETITORS = {
    "zerobounce": {
        "name": "ZeroBounce",
        "slug": "zerobounce",
        "category": "Email list verification",
        "tagline": "ZeroBounce verifies. InbXr watches.",
        "intro": (
            "ZeroBounce is one of the most widely used email list verifiers in the market. "
            "Upload a list, and it tells you which addresses are valid, invalid, role-based, "
            "disposable, or catch-all. If you need a one-time list clean before a big send, "
            "it does that job well."
        ),
        "what_they_do_well": [
            "High-accuracy syntax and MX validation",
            "Catch-all and disposable domain detection",
            "Honeypot and abuse flag identification",
            "Bulk upload with fast turnaround",
        ],
        "signal_coverage": "Signal 01 · Bounce Exposure (partial)",
        "signals_covered_pct": 25,
        "what_they_miss": [
            "Signal 02 · Engagement Trajectory (no MPP-adjusted reading)",
            "Signal 03 · Acquisition Quality (no cohort analysis)",
            "Signal 04 · Domain Reputation (no blacklist monitoring)",
            "Signal 05 · Spam Trap Exposure (dormancy patterns)",
            "Signal 06 · Authentication Standing (SPF/DKIM/DMARC vs 2025 mandates)",
            "Signal 07 · Decay Velocity (trajectory of your score over time)",
        ],
        "snapshot_vs_continuous": (
            "ZeroBounce gives you a snapshot. Valid on the day you ran the scan. "
            "Thirty days later, your list has shifted again. The ones you kept are now "
            "aging into dormancy. The ones you added are a new unknown. That's where "
            "the gap lives and InbXr fills it: continuous 6-hour reading across all 7 "
            "signals, not one scan against one signal."
        ),
        "when_zerobounce_is_enough": (
            "If you only send cold outreach once a quarter and don't care about "
            "engagement patterns or sender reputation drift, ZeroBounce alone is fine."
        ),
        "when_you_need_inbxr": (
            "If you send campaigns weekly, manage an agency, or watch open rates for "
            "signs of trouble, one signal isn't enough. The other 6 are where your "
            "deliverability actually lives."
        ),
        "comparison_rows": [
            ("List verification (validity)", True, True),
            ("Continuous monitoring (not one-shot)", False, True),
            ("Engagement trajectory (MPP-adjusted)", False, True),
            ("Acquisition cohort analysis", False, True),
            ("Blacklist monitoring (continuous)", False, True),
            ("DMARC compliance vs 2025 ISP mandates", False, True),
            ("Pre-send status check (green/amber/red)", False, True),
            ("Signal history and trajectory", False, True),
            ("Recovery Sequence copy generation", False, True),
        ],
    },

    "mail-tester": {
        "name": "Mail-Tester",
        "slug": "mail-tester",
        "category": "Email authentication score",
        "tagline": "Mail-Tester checks your headers. InbXr watches your entire list.",
        "intro": (
            "Mail-Tester gives you a spam score out of 10 by analyzing a single email you "
            "send to a test address. It reads SPF, DKIM, DMARC, message content, and a few "
            "content-based spam rules, then tells you whether that one email would hit the "
            "inbox. Simple, free, useful for setup verification."
        ),
        "what_they_do_well": [
            "SPF, DKIM, and DMARC header inspection",
            "Spam score computation from content",
            "Clear, single-page verdict",
            "Free for quick one-off checks",
        ],
        "signal_coverage": "Signal 06 · Authentication Standing (partial)",
        "signals_covered_pct": 5,
        "what_they_miss": [
            "Signal 01 · Bounce Exposure (no list verification)",
            "Signal 02 · Engagement Trajectory (no MPP detection)",
            "Signal 03 · Acquisition Quality (no cohort reading)",
            "Signal 04 · Domain Reputation (no DNSBL continuous monitoring)",
            "Signal 05 · Spam Trap Exposure (no dormancy reading)",
            "Signal 07 · Decay Velocity (no score history)",
        ],
        "snapshot_vs_continuous": (
            "Mail-Tester reads one email at one moment. InbXr reads your entire list and "
            "watches it continuously. A single email passing Mail-Tester doesn't tell you "
            "that your list has 1,200 contacts who haven't opened in 180 days, or that "
            "your blended engagement is masking a 40% cold acquisition cohort."
        ),
        "when_mail_tester_is_enough": (
            "If you're setting up a new sending domain and want to verify your auth records "
            "are configured before the first send, Mail-Tester gets you to green quickly."
        ),
        "when_you_need_inbxr": (
            "If you're already sending and want to know what your list is actually broadcasting "
            "beyond the headers, authentication is only 5 of the 100 points. InbXr reads the "
            "other 95."
        ),
        "comparison_rows": [
            ("SPF/DKIM/DMARC header check", True, True),
            ("Content-based spam score", True, False),
            ("Continuous authentication monitoring", False, True),
            ("List-level bounce prediction", False, True),
            ("MPP-adjusted engagement reading", False, True),
            ("Blacklist monitoring", False, True),
            ("List cohort and trajectory analysis", False, True),
            ("Pre-send status check (green/amber/red)", False, True),
            ("Recovery Sequence copy generation", False, True),
        ],
    },

    "mxtoolbox": {
        "name": "MXToolbox",
        "slug": "mxtoolbox",
        "category": "DNS and blacklist diagnostics",
        "tagline": "MXToolbox looks up. InbXr reads.",
        "intro": (
            "MXToolbox is the go-to reference for DNS lookups, MX records, blacklist checks, "
            "and SMTP diagnostics. If you need to look up a single domain's SPF record or "
            "check which blocklists a specific IP appears on, it's the cleanest free tool "
            "for the job."
        ),
        "what_they_do_well": [
            "DNS record inspection (A, MX, TXT, SPF, DMARC)",
            "Multi-blacklist lookups against 100+ DNSBLs",
            "SMTP path tracing",
            "Free tier covers most one-off lookups",
        ],
        "signal_coverage": "Signal 04 · Domain Reputation + Signal 06 · Authentication (partial, lookup-only)",
        "signals_covered_pct": 20,
        "what_they_miss": [
            "Signal 01 · Bounce Exposure (no list verification)",
            "Signal 02 · Engagement Trajectory (no ESP integration)",
            "Signal 03 · Acquisition Quality (no cohort reading)",
            "Signal 05 · Spam Trap Exposure (no list dormancy)",
            "Signal 07 · Decay Velocity (no score history)",
            "Continuous monitoring (you have to look things up manually)",
        ],
        "snapshot_vs_continuous": (
            "MXToolbox answers a question you ask. InbXr answers questions you didn't know "
            "to ask. Asking 'is my domain blacklisted today' is useful. Knowing that your "
            "engagement trajectory is declining, your acquisition quality from one channel "
            "is dragging down your blended rate, and your DMARC policy is about to break "
            "Microsoft's 2025 enforcement window, is a different class of answer."
        ),
        "when_mxtoolbox_is_enough": (
            "If you need to diagnose a specific DNS or blacklist question once, MXToolbox "
            "gives you the fastest answer in the category."
        ),
        "when_you_need_inbxr": (
            "If you want the tool to tell YOU when something changes, not wait for you to "
            "remember to check, you need continuous monitoring. InbXr watches all the DNS "
            "and blacklist data MXToolbox shows plus the 5 signals they don't cover."
        ),
        "comparison_rows": [
            ("DNS record lookup (on demand)", True, True),
            ("Blacklist lookup (on demand)", True, True),
            ("Continuous blacklist monitoring", False, True),
            ("Continuous DMARC change detection", False, True),
            ("List-level bounce prediction", False, True),
            ("MPP-adjusted engagement reading", False, True),
            ("Acquisition cohort analysis", False, True),
            ("Pre-send status check (green/amber/red)", False, True),
            ("Signal history and trajectory", False, True),
        ],
    },

    "glockapps": {
        "name": "GlockApps",
        "slug": "glockapps",
        "category": "Inbox placement testing",
        "tagline": "GlockApps tests placement. InbXr reads the list that caused it.",
        "intro": (
            "GlockApps runs seed-list placement tests: it sends a test email to a group of "
            "seed addresses across major ISPs and reports which ones landed in the inbox, "
            "spam folder, or were rejected. If you want to know how one specific email is "
            "placing right now, GlockApps gives you a clean answer."
        ),
        "what_they_do_well": [
            "Seed-list testing across Gmail, Yahoo, Outlook, and more",
            "Placement breakdown by ISP",
            "Sender score aggregation",
            "Content-based spam trigger analysis",
        ],
        "signal_coverage": "Signal 04 · Domain Reputation (partial, seed-based)",
        "signals_covered_pct": 15,
        "what_they_miss": [
            "Signal 01 · Bounce Exposure (no list verification)",
            "Signal 02 · Engagement Trajectory (no MPP detection)",
            "Signal 03 · Acquisition Quality (no cohort reading)",
            "Signal 05 · Spam Trap Exposure (no dormancy reading)",
            "Signal 06 · Authentication Standing (surface-level only)",
            "Signal 07 · Decay Velocity (no score history)",
        ],
        "snapshot_vs_continuous": (
            "GlockApps answers 'where did this one email land today?' InbXr answers 'what is "
            "happening to my list that determines where every future email will land?' "
            "Placement is the outcome. The 7 signals are the upstream causes. If you only "
            "measure the outcome, you can't fix the cause."
        ),
        "when_glockapps_is_enough": (
            "If you want a single-send placement report before launching a big campaign, "
            "GlockApps gives you the definitive answer in minutes."
        ),
        "when_you_need_inbxr": (
            "If you want to know WHY a campaign placed the way it did, and what to fix so "
            "the next one doesn't have the same problem, placement alone isn't actionable. "
            "The 7 signals tell you which upstream condition caused the placement you saw."
        ),
        "comparison_rows": [
            ("Seed-list inbox placement test", True, False),
            ("List-level bounce prediction", False, True),
            ("MPP-adjusted engagement reading", False, True),
            ("Continuous blacklist monitoring", False, True),
            ("Acquisition cohort analysis", False, True),
            ("List dormancy reading", False, True),
            ("DMARC compliance vs 2025 ISP mandates", False, True),
            ("Pre-send status check (green/amber/red)", False, True),
            ("Recovery Sequence copy generation", False, True),
        ],
    },

    "warmy": {
        "name": "Warmy",
        "slug": "warmy",
        "category": "Automated inbox warmup",
        "tagline": "Warmy warms inboxes. InbXr reads the list you're warming for.",
        "intro": (
            "Warmy automates the warmup process for new sending domains and cold email "
            "infrastructure. It sends and replies to emails across a network of seed inboxes "
            "to build sender reputation over time. If you're setting up a new domain or "
            "rehabilitating a burned one, Warmy is the category leader."
        ),
        "what_they_do_well": [
            "Automated warmup send and reply loops",
            "Sender reputation ramp-up over weeks",
            "Integrations with cold email platforms",
            "Warmup score tracking over time",
        ],
        "signal_coverage": "Not a signal reader. Warmy is an action tool, not a diagnostic layer.",
        "signals_covered_pct": 0,
        "what_they_miss": [
            "Signal 01 · Bounce Exposure (no list verification)",
            "Signal 02 · Engagement Trajectory (no MPP detection on your list)",
            "Signal 03 · Acquisition Quality (no cohort reading)",
            "Signal 04 · Domain Reputation (partial, sender-side only)",
            "Signal 05 · Spam Trap Exposure (no dormancy reading)",
            "Signal 06 · Authentication Standing (surface-level)",
            "Signal 07 · Decay Velocity (no score history)",
        ],
        "snapshot_vs_continuous": (
            "Warmy and InbXr don't really overlap. Warmy warms. InbXr watches. Warmy is the "
            "gym; InbXr is the annual physical. You can use both. In fact, if you're running "
            "Warmy, you almost certainly need InbXr to tell you whether the list you're "
            "warming for is going to receive the warmed-up sends well."
        ),
        "when_warmy_is_enough": (
            "If you're a cold email operator building up a new domain for outbound, Warmy "
            "handles the reputation ramp well. Keep it."
        ),
        "when_you_need_inbxr": (
            "Warming your domain doesn't matter if the list you're sending to is already "
            "broken. Before and during warmup, you need to know which contacts will "
            "bounce, which will report spam, and which signals are trending toward "
            "deliverability collapse. That's what InbXr reads."
        ),
        "comparison_rows": [
            ("Automated warmup send/reply loops", True, False),
            ("Sender reputation ramp-up", True, False),
            ("List-level bounce prediction", False, True),
            ("MPP-adjusted engagement reading", False, True),
            ("Continuous blacklist monitoring", False, True),
            ("Acquisition cohort analysis", False, True),
            ("DMARC compliance vs 2025 ISP mandates", False, True),
            ("Pre-send status check (green/amber/red)", False, True),
            ("Recovery Sequence copy generation", False, True),
        ],
    },
}


@public_signal_bp.route("/<slug>-alternative")
def competitor_alternative(slug):
    """Render a respectful competitor comparison page.

    Unknown slugs fall through to a 404 so we don't accidentally serve this
    template for arbitrary /<anything>-alternative URLs.
    """
    from flask import abort
    comp = COMPETITORS.get(slug)
    if not comp:
        abort(404)

    return render_template(
        "public/comparison.html",
        competitor=comp,
        competitors=COMPETITORS,
        allow_index=True,
        title=f"{comp['name']} Alternative · InbXr",
        meta_description=f"Considering an alternative to {comp['name']}? {comp['tagline']} See what {comp['name']} covers, what it misses, and where InbXr reads the other signals.",
    )


# ── /why-am-i-in-spam — unified spam diagnostic ──────────
#
# SEO hero feature. Buyers searching "why are my emails going to spam"
# land here, fill the form with their domain (+ optional subject/body),
# and get the top 3 ranked reasons in one screen. No signup required.
# Built as a GET landing page + POST JSON endpoint so the JS can run
# the diagnostic inline without a full page reload.


@public_signal_bp.route("/why-am-i-in-spam")
def why_am_i_in_spam_page():
    """Render the landing page. Empty state on first load; JS fills
    results inline via /why-am-i-in-spam/run."""
    return render_template(
        "public/why_am_i_in_spam.html",
        allow_index=True,
        title="Why Are My Emails Going to Spam? · Free Diagnostic · InbXr",
        meta_description=(
            "Find out in 30 seconds why your emails are going to spam. "
            "InbXr runs SPF/DKIM/DMARC checks, blacklist monitoring, and "
            "content analysis in parallel, then tells you the 3 most likely "
            "reasons with specific fixes. Free. No signup."
        ),
    )


@public_signal_bp.route("/why-am-i-in-spam/run", methods=["POST"])
def why_am_i_in_spam_run():
    """Execute the diagnostic. Accepts JSON or form-encoded:
        domain      required (the sending domain)
        subject     optional (one subject line to analyze)
        body        optional (one email body to analyze)
    Returns the structured result dict from modules.spam_diagnostic.
    Rate-limited via client IP at the Flask level (implicit — existing
    global rate limiter applies)."""
    from modules.spam_diagnostic import run_diagnostic

    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    domain = (data.get("domain") or "").strip().lower()
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()

    # Minimal defensive cap: prevent someone pasting a 5 MB body
    if len(subject) > 500:
        subject = subject[:500]
    if len(body) > 20000:
        body = body[:20000]

    if not domain and not subject and not body:
        return jsonify({
            "ok": False,
            "error": "Provide a sending domain, or a subject and body to analyze.",
        }), 400

    try:
        result = run_diagnostic(domain=domain, subject=subject, body=body)
    except Exception:
        logger.exception("[SPAM_DIAGNOSTIC] run failed")
        return jsonify({"ok": False, "error": "Diagnostic failed. Please try again."}), 500

    return jsonify(result)


# ── /inherited-list-first-aid — CSV triage flow ─────────
#
# Signature flow for buyers with an inherited list. Upload CSV, get a
# 3-column triage (Remove / Re-engage / Keep) with reason codes and a
# downloadable suppression CSV. No signup required. No data stored
# server-side past the request lifecycle. Works entirely on the content
# the user pasted in, which matters because inherited-list owners
# typically don't have ESP access to the underlying system.

_MAX_TRIAGE_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


@public_signal_bp.route("/inherited-list-first-aid")
def inherited_list_first_aid_page():
    """Render the landing page with upload form."""
    return render_template(
        "public/inherited_list_first_aid.html",
        allow_index=True,
        title="Inherited List First Aid · Free CSV Triage · InbXr",
        meta_description=(
            "Inherited a list and don't know what's in it? Upload your CSV and "
            "InbXr classifies every contact into Remove, Re-engage, or Keep "
            "with specific reason codes. Download a suppression file that "
            "drops into any ESP. Free. No signup."
        ),
    )


@public_signal_bp.route("/inherited-list-first-aid/run", methods=["POST"])
def inherited_list_first_aid_run():
    """Accept an uploaded CSV and return the triage report as JSON.
    The raw CSV is held in memory only for the duration of this
    request — we do not persist it to disk or the database."""
    from modules.list_triage import triage_list

    # Support both multipart upload and pasted-content POST for flexibility
    csv_content = None

    if "file" in request.files and request.files["file"].filename:
        upload = request.files["file"]
        raw = upload.read(_MAX_TRIAGE_UPLOAD_BYTES + 1)
        if len(raw) > _MAX_TRIAGE_UPLOAD_BYTES:
            return jsonify({
                "ok": False,
                "error": f"CSV must be smaller than {_MAX_TRIAGE_UPLOAD_BYTES // 1024 // 1024} MB.",
            }), 400
        try:
            csv_content = raw.decode("utf-8", errors="replace")
        except Exception:
            return jsonify({"ok": False, "error": "Could not decode CSV. Save as UTF-8 and try again."}), 400
    else:
        csv_content = (request.form.get("csv_content") or "").strip()
        if len(csv_content.encode("utf-8")) > _MAX_TRIAGE_UPLOAD_BYTES:
            return jsonify({
                "ok": False,
                "error": f"CSV must be smaller than {_MAX_TRIAGE_UPLOAD_BYTES // 1024 // 1024} MB.",
            }), 400

    if not csv_content:
        return jsonify({
            "ok": False,
            "error": "Upload a CSV file or paste CSV content to triage.",
        }), 400

    try:
        result = triage_list(csv_content)
    except Exception:
        logger.exception("[LIST_TRIAGE] triage failed")
        return jsonify({"ok": False, "error": "Triage failed. Please try again."}), 500

    if not result.get("ok"):
        return jsonify(result), 400

    # Stash the full remove bucket in the session so the export route
    # can build the suppression CSV without re-running the triage.
    # For lists over 5k the emails list can get chunky, so we only
    # stash email addresses, not full objects.
    from flask import session as _session
    remove_emails = [(c["email"], c["reason_label"]) for c in result["_full_buckets"]["remove"]]
    _session["_triage_remove"] = remove_emails

    # Strip the internal _full_buckets before returning JSON
    del result["_full_buckets"]
    return jsonify(result)


@public_signal_bp.route("/inherited-list-first-aid/suppression.csv")
def inherited_list_first_aid_export():
    """Download the remove bucket as a suppression CSV. Reads from the
    session, not the DB — this means the user must still have the tab
    open with the previous triage result. After a hard refresh the
    export is gone, which is fine because re-running the triage is
    fast and keeps us from persisting user data."""
    from modules.list_triage import build_suppression_csv
    from flask import session as _session

    remove_emails = _session.get("_triage_remove") or []
    if not remove_emails:
        return jsonify({"ok": False, "error": "No triage result in this session."}), 404

    # Rebuild the minimal shape build_suppression_csv expects
    remove_contacts = [{"email": e, "reason_label": r} for e, r in remove_emails]
    csv_body = build_suppression_csv(remove_contacts)

    from flask import Response
    return Response(
        csv_body,
        mimetype="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="inbxr-suppression-list.csv"',
            "Cache-Control": "no-store",
        },
    )
