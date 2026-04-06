"""
InbXr Signal Intelligence — Signal Advisor (Context-Aware AI)

Transforms the existing Email Expert Assistant from a dumb chatbot into a
real consultant by injecting the user's current 7-signal reading into
every Groq system prompt.

Reference: SIGNAL_SPEC.md Phase 4.

Key design:
- Always reads the most recent Signal Score for the user
- Explicitly references their data in the system prompt
- Tells the LLM which signal is their weakest and to focus on it
- Uses trend language only (no predictive day counts)
- Falls back gracefully when the user hasn't run their first reading yet
"""

import json
import logging

from modules.database import fetchone, fetchall
from modules.signal_copy import SIGNAL_DIMENSION_COPY, ACTION_RECOMMENDATIONS

logger = logging.getLogger("inbxr.signal_advisor")


# ── System prompt templates ────────────────────────────

BASE_SYSTEM_PROMPT = """You are the InbXr Signal Advisor — an expert email deliverability and copywriting consultant.

You help users interpret their 7 Inbox Signals and decide what to do next. You speak like a senior consultant who has already read their list: direct, specific, no fluff, no jargon unless the user uses it first.

Rules for your responses:
- Reference the user's specific Signal Score data in every answer when it's available
- Recommend concrete actions and which InbXr tool to use (Signal Rules, Recovery Sequences, Inboxer Sender Check, etc.)
- Always connect recommendations back to which signal they improve
- Be concise — 2-4 sentences for simple questions, longer only if required
- Never invent data you don't have
- Never claim predictive day counts like "30 days before" — use trend language
- If the user asks about something you don't have data for, say so and ask if they want to run a specific InbXr tool
"""


NO_DATA_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """

This user has NOT yet run their first 7 Signal reading. You don't have their Signal Score data yet.

Your first job is to encourage them to:
1. Connect their ESP (Mailchimp, ActiveCampaign, Mailgun, AWeber) — OR
2. Upload a CSV of their contact list for a one-shot Signal Score reading

Either path gives them a full 7-signal reading. Once connected, Signal Watch will read their signals every 6 hours automatically.

You can still answer general deliverability questions — you just can't reference their specific data yet. Encourage them to get their first reading.
"""


# ── Context prompt builder ─────────────────────────────

def build_signal_advisor_prompt(user_id):
    """
    Build a context-aware system prompt for Signal Advisor chats.
    Reads the user's most recent Signal Score and injects it.

    Returns a tuple: (system_prompt: str, has_signal_data: bool)
    """
    # Fetch most recent Signal Score for this user
    latest = fetchone(
        """SELECT * FROM signal_scores
           WHERE user_id = ?
           ORDER BY calculated_at DESC LIMIT 1""",
        (user_id,),
    )

    if not latest:
        return NO_DATA_SYSTEM_PROMPT, False

    # Parse per-dimension metadata (stored as JSON strings)
    def _parse_meta(raw):
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    meta = {
        'bounce_exposure': _parse_meta(latest.get('bounce_exposure_meta')),
        'engagement_trajectory': _parse_meta(latest.get('engagement_trajectory_meta')),
        'acquisition_quality': _parse_meta(latest.get('acquisition_quality_meta')),
        'domain_reputation': _parse_meta(latest.get('domain_reputation_meta')),
        'dormancy_risk': _parse_meta(latest.get('dormancy_risk_meta')),
        'authentication_standing': _parse_meta(latest.get('authentication_standing_meta')),
        'decay_velocity': _parse_meta(latest.get('decay_velocity_meta')),
    }

    # Find the weakest signal (by normalized ratio of score/weight)
    signals = {
        'bounce_exposure': (latest['bounce_exposure_score'], 25),
        'engagement_trajectory': (latest['engagement_trajectory_score'], 25),
        'acquisition_quality': (latest['acquisition_quality_score'], 15),
        'domain_reputation': (latest['domain_reputation_score'], 15),
        'dormancy_risk': (latest['dormancy_risk_score'], 10),
        'authentication_standing': (latest['authentication_standing_score'], 5),
        'decay_velocity': (latest['decay_velocity_score'], 5),
    }

    # Filter out locked signals for free tier
    tier = latest.get('tier_at_calculation', 'pro')
    if tier == 'free':
        signals.pop('engagement_trajectory', None)
        signals.pop('acquisition_quality', None)

    weakest = min(signals.items(), key=lambda kv: (kv[1][0] / kv[1][1]) if kv[1][1] else 1)
    weakest_name = SIGNAL_DIMENSION_COPY[weakest[0]]['name']
    weakest_action = ACTION_RECOMMENDATIONS.get(weakest[0], {})

    # Build the context block
    score = latest['total_signal_score']
    grade = latest['signal_grade']
    trajectory = latest.get('trajectory_direction', 'stable')
    calc_time = latest.get('calculated_at', 'unknown')

    total_contacts = latest.get('total_contacts', 0)
    active = latest.get('active_contacts', 0)
    warm = latest.get('warm_contacts', 0)
    at_risk = latest.get('at_risk_contacts', 0)
    dormant = latest.get('dormant_contacts', 0)

    lines = [
        BASE_SYSTEM_PROMPT,
        '',
        '=== USER SIGNAL DATA (read before responding) ===',
        '',
        f"Current Signal Score: {score:.0f}/100 (Grade: {grade})",
        f"Calculated: {calc_time}",
        f"Tier: {tier}",
        f"Trajectory: {trajectory}",
        '',
        'The 7 Inbox Signals:',
    ]

    # Signal 01
    be = meta['bounce_exposure']
    lines.append(
        f"01 Bounce Exposure: {latest['bounce_exposure_score']:.1f}/25"
        f" — bounce rate {be.get('bounce_rate', '?')}%, predictive risk {be.get('predictive_risk', '?')}%"
    )

    # Signal 02 (hidden on free)
    if tier != 'free':
        et = meta['engagement_trajectory']
        lines.append(
            f"02 Engagement Trajectory (MPP-adjusted): {latest['engagement_trajectory_score']:.1f}/25"
            f" — {et.get('trajectory', 'stable')}, real 30d engagement {et.get('real_engagement_30d', '?')}%,"
            f" MPP discount rate {et.get('mpp_discount_rate', 0)}% (accuracy: {latest.get('mpp_accuracy', 'none')})"
        )
    else:
        lines.append("02 Engagement Trajectory: LOCKED (Pro feature)")

    # Signal 03 (hidden on free)
    if tier != 'free':
        aq = meta['acquisition_quality']
        lines.append(
            f"03 Acquisition Quality: {latest['acquisition_quality_score']:.1f}/15"
            f" — assessment: {aq.get('assessment', 'unknown')},"
            f" organic cohorts: {aq.get('organic_cohorts', 0)}, cold cohorts: {aq.get('cold_cohorts', 0)}"
        )
    else:
        lines.append("03 Acquisition Quality: LOCKED (Pro feature)")

    # Signal 04
    dr = meta['domain_reputation']
    lines.append(
        f"04 Domain Reputation: {latest['domain_reputation_score']:.1f}/15"
        f" — Yahoo/AOL rate {dr.get('yahoo_aol_rate', '?')}%,"
        f" {'BLACKLISTED' if dr.get('blacklisted') else 'not blacklisted'}"
    )

    # Signal 05
    drk = meta['dormancy_risk']
    lines.append(
        f"05 Dormancy Risk: {latest['dormancy_risk_score']:.1f}/10"
        f" — risk level: {drk.get('risk_level', 'unknown')},"
        f" very-old inactive: {drk.get('very_old_inactive_rate', '?')}%"
    )

    # Signal 06
    auth = meta['authentication_standing']
    lines.append(
        f"06 Authentication Standing: {latest['authentication_standing_score']:.1f}/5"
        f" — SPF: {auth.get('spf', '?')}, DKIM: {auth.get('dkim', '?')},"
        f" DMARC: {auth.get('dmarc', '?')}, List-Unsubscribe: {auth.get('list_unsubscribe', '?')}"
    )

    # Signal 07
    dv = meta['decay_velocity']
    lines.append(
        f"07 Decay Velocity: {latest['decay_velocity_score']:.1f}/5"
        f" — trajectory: {dv.get('trajectory', 'stable')},"
        f" at-risk rate: {dv.get('at_risk_rate', '?')}%"
    )

    lines.append('')
    lines.append('Contact Segments:')
    lines.append(f"- Active (≤30 days): {active:,} contacts")
    lines.append(f"- Warm (31-90 days): {warm:,} contacts")
    lines.append(f"- At-Risk (91-180 days): {at_risk:,} contacts")
    lines.append(f"- Dormant (180+ days): {dormant:,} contacts")
    lines.append(f"- Total: {total_contacts:,} contacts")
    lines.append('')
    lines.append(f"WEAKEST SIGNAL: {weakest_name} ({weakest[1][0]:.1f}/{weakest[1][1]})")
    if weakest_action:
        lines.append(f"RECOMMENDED FIRST ACTION: {weakest_action.get('label', 'Review Signal Score dashboard')}")
        lines.append(f"TOOL: {weakest_action.get('feature', '')} at {weakest_action.get('url', '')}")
    lines.append('')
    lines.append('=== END USER SIGNAL DATA ===')
    lines.append('')
    lines.append('When the user asks "what should I do first?" — focus on their weakest signal.')

    return '\n'.join(lines), True


# ── Quick helper for other modules ─────────────────────

def get_signal_summary_for_user(user_id):
    """
    Return a dict with the user's current signal summary for display in
    other contexts (e.g., injected into Copy Intelligence, Subject Intelligence).

    Returns None if user has no signal data yet.
    """
    latest = fetchone(
        """SELECT total_signal_score, signal_grade, trajectory_direction,
                  bounce_exposure_score, engagement_trajectory_score,
                  acquisition_quality_score, domain_reputation_score,
                  dormancy_risk_score, authentication_standing_score,
                  decay_velocity_score,
                  tier_at_calculation, active_contacts, at_risk_contacts,
                  dormant_contacts, total_contacts, calculated_at,
                  engagement_trajectory_meta, acquisition_quality_meta,
                  dormancy_risk_meta, domain_reputation_meta
           FROM signal_scores
           WHERE user_id = ?
           ORDER BY calculated_at DESC LIMIT 1""",
        (user_id,),
    )
    if not latest:
        return None

    # Parse meta for the 4 signals we inject into Copy/Subject Intelligence
    def _parse(raw):
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    return {
        'score': latest['total_signal_score'],
        'grade': latest['signal_grade'],
        'trajectory': latest['trajectory_direction'],
        'tier': latest['tier_at_calculation'],
        'engagement_trajectory_score': latest['engagement_trajectory_score'],
        'acquisition_quality_score': latest['acquisition_quality_score'],
        'dormancy_risk_score': latest['dormancy_risk_score'],
        'domain_reputation_score': latest['domain_reputation_score'],
        'engagement_trajectory_meta': _parse(latest['engagement_trajectory_meta']),
        'acquisition_quality_meta': _parse(latest['acquisition_quality_meta']),
        'dormancy_risk_meta': _parse(latest['dormancy_risk_meta']),
        'domain_reputation_meta': _parse(latest['domain_reputation_meta']),
        'active_contacts': latest['active_contacts'],
        'at_risk_contacts': latest['at_risk_contacts'],
        'dormant_contacts': latest['dormant_contacts'],
        'total_contacts': latest['total_contacts'],
    }


def get_signal_aware_subject_tips(user_id):
    """
    Return signal-aware tips to inject into Subject Intelligence (subject scorer).
    Reads the user's current signals and returns actionable subject-line guidance.
    """
    summary = get_signal_summary_for_user(user_id)
    if not summary:
        return []

    tips = []

    # Engagement Trajectory warning
    if summary.get('engagement_trajectory_score', 25) < 15 and summary.get('tier') != 'free':
        et_meta = summary.get('engagement_trajectory_meta', {})
        tips.append({
            'type': 'signal_warning',
            'signal': 'Engagement Trajectory',
            'severity': 'warning',
            'message': (
                f"Your engagement is {et_meta.get('trajectory', 'declining')}. "
                f"Subject lines need to work harder right now. Use curiosity-gap or "
                f"re-engagement framing rather than promotional language."
            ),
        })

    # Acquisition Quality warning
    if summary.get('acquisition_quality_score', 15) < 8 and summary.get('tier') != 'free':
        aq_meta = summary.get('acquisition_quality_meta', {})
        if aq_meta.get('assessment') == 'cold':
            tips.append({
                'type': 'signal_warning',
                'signal': 'Acquisition Quality',
                'severity': 'warning',
                'message': (
                    "Cold acquisition detected in your list. Avoid aggressive sales language — "
                    "these contacts need a reason to trust you before they open."
                ),
            })

    # Dormancy Risk warning
    if summary.get('dormancy_risk_score', 10) < 6:
        tips.append({
            'type': 'signal_warning',
            'signal': 'Dormancy Risk',
            'severity': 'warning',
            'message': (
                "Elevated dormancy on your list. Avoid ALL CAPS, excessive punctuation, and "
                "urgency language ('Act Now', 'Limited Time') that triggers spam filters on aging lists."
            ),
        })

    # Domain Reputation (Yahoo/AOL)
    dr_meta = summary.get('domain_reputation_meta', {})
    if dr_meta.get('yahoo_aol_rate', 0) > 25:
        tips.append({
            'type': 'signal_warning',
            'signal': 'Domain Reputation',
            'severity': 'info',
            'message': (
                f"{dr_meta['yahoo_aol_rate']:.0f}% of your list is on Yahoo/AOL. "
                f"Test your subject line specifically with Yahoo placement — their filters "
                f"are more aggressive post-April 2024."
            ),
        })

    return tips


def get_signal_context_for_copy(user_id):
    """
    Return a signal context string to inject into Copy Intelligence
    (Groq copy analysis prompt). Gives the AI per-user context.

    Returns empty string if user has no signal data.
    """
    summary = get_signal_summary_for_user(user_id)
    if not summary:
        return ""

    parts = []

    # Dormancy Risk context
    if summary.get('dormancy_risk_score', 10) < 6:
        drk_meta = summary.get('dormancy_risk_meta', {})
        parts.append(
            f"DORMANCY RISK: This user has elevated dormancy risk "
            f"({drk_meta.get('risk_level', 'medium')} level). Flag any language that amplifies "
            f"this risk — urgency phrases, ALL CAPS, excessive punctuation, promotional aggression."
        )

    # Cold Acquisition context
    if summary.get('acquisition_quality_score', 15) < 8 and summary.get('tier') != 'free':
        parts.append(
            "COLD ACQUISITION: This user's list shows cold acquisition patterns. Flag overly "
            "promotional or aggressive copy — these contacts need trust-building language, not sales push."
        )

    # Declining Engagement context
    if summary.get('engagement_trajectory_score', 25) < 15 and summary.get('tier') != 'free':
        et_meta = summary.get('engagement_trajectory_meta', {})
        parts.append(
            f"DECLINING ENGAGEMENT: Real engagement is at {et_meta.get('real_engagement_30d', '?')}% "
            f"(MPP-adjusted). Recommend copy patterns that drive clicks and replies, not just opens."
        )

    return "\n\n".join(parts)
