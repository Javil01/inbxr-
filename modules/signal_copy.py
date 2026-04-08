"""
InbXr Signal Intelligence. Copy Constants

All user-facing copy for the 7 Inbox Signals system lives here.
Reference: SIGNAL_SPEC.md for locked decisions.

Key rules applied:
- "Spam Trap Exposure" (display name; internal id stays 'dormancy_risk')
- Trend language only (no "30 days before" predictive claims)
- Free tier weights normalized to 100 (not capped at 60)
- MPP adjustment is market-first but honest about per-ESP accuracy
"""

# ── 1. Signal Weights by Tier ──────────────────────────

# Pro/Agency tier: full 7 signals summing to 100
PRO_SIGNAL_WEIGHTS = {
    'bounce_exposure': 25,
    'engagement_trajectory': 25,
    'acquisition_quality': 15,
    'domain_reputation': 15,
    'dormancy_risk': 10,
    'authentication_standing': 5,
    'decay_velocity': 5,
}

# Free tier: 5 signals normalized to 100 (signals 02 + 03 locked)
# Ratio preserved from Pro weights: 25 + 15 + 10 + 5 + 5 = 60 → scale by (100/60)
FREE_SIGNAL_WEIGHTS = {
    'bounce_exposure': 42,      # 25 * 100/60 ≈ 41.67
    'domain_reputation': 25,    # 15 * 100/60 = 25.0
    'dormancy_risk': 17,        # 10 * 100/60 ≈ 16.67
    'authentication_standing': 8,  # 5 * 100/60 ≈ 8.33
    'decay_velocity': 8,        # 5 * 100/60 ≈ 8.33
}

# Signals locked for free tier (shown as upgrade cards)
FREE_TIER_LOCKED_SIGNALS = {'engagement_trajectory', 'acquisition_quality'}


def get_weights_for_tier(tier):
    """Return the signal weight map for a given tier."""
    if tier == 'free':
        return FREE_SIGNAL_WEIGHTS
    return PRO_SIGNAL_WEIGHTS


# ── 2. Grade Thresholds & Copy ─────────────────────────

GRADE_THRESHOLDS = {
    'A': 90,
    'B': 75,
    'C': 60,
    'D': 45,
    'F': 0,
}


def get_grade(score):
    """Convert 0-100 score to letter grade A/B/C/D/F."""
    if score >= GRADE_THRESHOLDS['A']:
        return 'A'
    elif score >= GRADE_THRESHOLDS['B']:
        return 'B'
    elif score >= GRADE_THRESHOLDS['C']:
        return 'C'
    elif score >= GRADE_THRESHOLDS['D']:
        return 'D'
    return 'F'


SIGNAL_GRADE_COPY = {
    'A': {
        'label': 'Excellent',
        'color': 'success',
        'description': 'Your list is in strong condition. Signal Watch is monitoring for drift.',
        'cta': 'Maintain your score. Set Signal Recommendations to stay here automatically.',
    },
    'B': {
        'label': 'Good',
        'color': 'success',
        'description': 'Healthy but one or two signals need attention. See recommended actions below.',
        'cta': 'Fix your weakest signal to reach Excellent.',
    },
    'C': {
        'label': 'Fair',
        'color': 'warning',
        'description': 'Multiple signals are weak. Act before your next send.',
        'cta': 'Run Recovery Sequences on your at-risk segment before your next campaign.',
    },
    'D': {
        'label': 'At Risk',
        'color': 'warning',
        'description': 'Your list health is degrading. Run Recovery Sequences on your dormant segment now.',
        'cta': 'Do not send to your full list. Target Active segment only.',
    },
    'F': {
        'label': 'Danger',
        'color': 'danger',
        'description': 'Do not send to this full list. Fix Authentication Standing and suppress dormant contacts first.',
        'cta': 'Fix Authentication Standing first. Then run Recovery Sequences.',
    },
}


# ── 3. Signal Dimension Copy ──────────────────────────
#
# Each signal has:
# - name: display name
# - number: "01"-"07" for UI pills
# - weight: Pro tier weight (free tier is normalized at runtime)
# - note: short positioning phrase for homepage pills
# - tooltip: full explanation for hover state
# - what_it_reads: bullet-list of inputs
# - market_first: whether it's positioned as market-first
# - market_first_label: the claim itself (only shown if market_first=True)
# - free_tier_locked: whether free users see this signal or an upgrade card
#

SIGNAL_DIMENSION_COPY = {
    'bounce_exposure': {
        'name': 'Bounce Exposure',
        'number': '01',
        'weight': 25,
        'note': 'Predictive, not historical',
        'tooltip': 'Predictive bounce risk. Not just past bounces, but how many valid-today addresses will bounce in the next 30–60 days.',
        'what_it_reads': 'Domain aging · MX record changes · catch-all probability · role address concentration · disposable domain detection',
        'market_first': False,
        'free_tier_locked': False,
    },
    'engagement_trajectory': {
        'name': 'Engagement Trajectory',
        'number': '02',
        'weight': 25,
        'note': 'MPP-adjusted · Market-first',
        'tooltip': 'The direction your real human engagement is moving. With Apple MPP machine opens removed where detectable.',
        'what_it_reads': 'Click signals · reply signals · real opens (MPP removed) · 30/60/90 day trends',
        'market_first': True,
        'market_first_label': 'MPP-adjusted · Detection accuracy varies by ESP',
        'free_tier_locked': True,
    },
    'acquisition_quality': {
        'name': 'Acquisition Quality',
        'number': '03',
        'weight': 15,
        'note': 'Inferred from behaviour · Market-first',
        'tooltip': 'How your contacts were acquired. Inferred from their day-1 engagement patterns, not declared by you.',
        'what_it_reads': 'Day-1 engagement rate per import cohort · engagement onset patterns · cohort vs cohort drift',
        'market_first': True,
        'market_first_label': 'Inferred from behaviour · No other tool reads this',
        'free_tier_locked': True,
    },
    'domain_reputation': {
        'name': 'Domain Reputation',
        'number': '04',
        'weight': 15,
        'note': 'Sender and recipient side',
        'tooltip': 'Your sending domain AND the receiving domains in your list. Both sides of the reputation equation.',
        'what_it_reads': 'Sender blacklist status · recipient domain concentration · Yahoo/AOL risk · free-email ratio',
        'market_first': False,
        'free_tier_locked': False,
    },
    'dormancy_risk': {
        # Display name: "Spam Trap Exposure" (marketing decision, April 2026).
        # Internal Python identifier stays 'dormancy_risk' to avoid renaming
        # the entire signal pipeline. Formula calculates spam trap PROBABILITY
        # from the conditions that produce trap hits (dormancy depth, list age,
        # acquisition source pattern). Framed as "probabilistic risk scoring".
        'name': 'Spam Trap Exposure',
        'number': '05',
        'weight': 10,
        'note': 'Probabilistic risk scoring',
        'tooltip': 'Probabilistic spam trap risk based on the conditions that produce trap hits. Dormancy depth, list age, and acquisition source pattern. Cannot confirm a trap without hitting one, so we score the probability before you send.',
        'what_it_reads': 'Dormancy depth (180+ days, 365+ days) · list age · acquisition source pattern',
        'market_first': False,
        'free_tier_locked': False,
    },
    'authentication_standing': {
        'name': 'Authentication Standing',
        'number': '06',
        'weight': 5,
        'note': 'Scored vs 2025 ISP mandates',
        'tooltip': 'Your full authentication posture scored against 2024–2025 ISP enforcement requirements (Gmail, Yahoo, Microsoft).',
        'what_it_reads': 'SPF · DKIM · DMARC policy strength · List-Unsubscribe header · 2025 Microsoft enforcement status',
        'market_first': False,
        'free_tier_locked': False,
    },
    'decay_velocity': {
        'name': 'Decay Velocity',
        'number': '07',
        'weight': 5,
        'note': 'Rate and direction of list degradation',
        'tooltip': 'How fast your list is changing. Expressed as a direction (improving / stable / declining) and a rate. No specific day predictions.',
        'what_it_reads': 'Weekly segment migration rate · Active/At-Risk/Dormant ratio trends · Signal Score history',
        'market_first': False,
        'free_tier_locked': False,
    },
}


# ── 4. Action Recommendations (per weakest signal) ────

ACTION_RECOMMENDATIONS = {
    'bounce_exposure': {
        'label': 'Run List Verification to identify high-risk addresses',
        'url': '/bulk-email-verification',
        'feature': 'List Verification',
    },
    'engagement_trajectory': {
        'label': 'Run Recovery Sequences on your declining segment',
        'url': '/recovery-sequences',
        'feature': 'Recovery Sequences',
    },
    'acquisition_quality': {
        'label': 'Set Signal Recommendations to flag cold-acquisition contacts',
        'url': '/signal-rules',
        'feature': 'Signal Recommendations',
    },
    'domain_reputation': {
        'label': 'Check Domain Reputation in Inboxer Sender Check',
        'url': '/sender',
        'feature': 'Inboxer Sender Check',
    },
    'dormancy_risk': {
        'label': 'Suppress dormant contacts with Signal Recommendations',
        'url': '/signal-rules',
        'feature': 'Signal Recommendations',
    },
    'authentication_standing': {
        'label': 'Fix authentication issues in Inboxer Sender Check',
        'url': '/sender',
        'feature': 'Inboxer Sender Check',
    },
    'decay_velocity': {
        'label': 'Run Recovery Sequences before trajectory reaches danger',
        'url': '/recovery-sequences',
        'feature': 'Recovery Sequences',
    },
}


# ── 5. Trend Language (replaces predictive claims) ────

TRAJECTORY_DIRECTION_LABELS = {
    'improving': 'Improving',
    'stable': 'Stable',
    'declining': 'Declining',
    'unknown': 'Not enough data yet',
}

TRAJECTORY_DIRECTION_MESSAGES = {
    'improving': 'Your Signal Score is trending up. Real engagement is growing week-over-week.',
    'stable': 'Your Signal Score is holding steady. Signal Watch will alert you if that changes.',
    'declining': 'Your Signal Score is trending down. Act before your next send to reverse the trajectory.',
    'unknown': 'InbXr needs at least 2 Signal Watch scans before it can show trajectory.',
}


# ── 6. MPP Detection Accuracy Labels ──────────────────

MPP_ACCURACY_LABELS = {
    'high': {
        'label': 'High accuracy',
        'description': 'Full User-Agent + IP range detection. ~90% of real MPP opens detected.',
        'badge_color': 'green',
    },
    'medium': {
        'label': 'Medium accuracy',
        'description': 'Timing heuristic + iCloud domain fallback. ~40–60% of real MPP opens detected.',
        'badge_color': 'yellow',
    },
    'low': {
        'label': 'Low accuracy',
        'description': 'Domain-only detection. ~15% of real MPP opens detected.',
        'badge_color': 'yellow',
    },
    'none': {
        'label': 'Not adjusted',
        'description': 'ESP data does not support MPP detection. Engagement Trajectory shows raw opens.',
        'badge_color': 'gray',
    },
}

# Which ESP gets which accuracy level
ESP_MPP_ACCURACY = {
    'mailgun': 'high',          # User-Agent + IP available on events API
    'mailchimp': 'medium',      # Timing heuristic only
    'activecampaign': 'medium', # Timing heuristic only
    'aweber': 'medium',         # Timing heuristic only
    'instantly': 'none',        # No per-contact engagement data
    'smartlead': 'none',        # No per-contact engagement data
    'gohighlevel': 'none',      # Limited per-contact data
}


# ── 7. Contact Segment Copy ───────────────────────────

SEGMENT_LABELS = {
    'active': {
        'label': 'Active',
        'days_range': '≤30 days',
        'description': 'Engaged with your emails in the last 30 days. Safe to send to.',
        'color': 'green',
    },
    'warm': {
        'label': 'Warm',
        'days_range': '31–90 days',
        'description': 'Engaged 1–3 months ago. Still safe but watch for decay.',
        'color': 'blue',
    },
    'at_risk': {
        'label': 'At-Risk',
        'days_range': '91–180 days',
        'description': 'No engagement in 3–6 months. Run Recovery Sequences before sending to this segment.',
        'color': 'yellow',
    },
    'dormant': {
        'label': 'Dormant',
        'days_range': '180+ days',
        'description': 'No engagement for 6+ months. High deliverability risk. Suppress or re-permission.',
        'color': 'red',
    },
    'unknown': {
        'label': 'Unknown',
        'days_range': 'No data',
        'description': 'No engagement history recorded yet.',
        'color': 'gray',
    },
}


# ── 8. Signal Rule Pre-Built Templates ────────────────

# Pre-built templates users can enable with one click.
# All default to dry-run mode. User must explicitly flip to live.

PRE_BUILT_RULE_TEMPLATES = [
    {
        'template_id': 'suppress_180_dormant',
        'rule_name': 'Suppress 180-day dormant contacts',
        'description': 'Automatically suppress contacts with no engagement for 180+ days. Protects your Spam Trap Exposure and Engagement Trajectory signals.',
        'condition_signal': 'days_since_engagement',
        'condition_operator': 'greater_than',
        'condition_value': 180,
        'condition_duration_days': 180,
        'action_type': 'suppress',
        'action_target': 'dormant',
        'action_esp_sync': 1,
        'action_dry_run': 1,
    },
    {
        'template_id': 'flag_cold_acquisition',
        'rule_name': 'Flag cold acquisition imports',
        'description': 'Tag contacts from import cohorts with no day-1 engagement as cold acquisition. Improves Acquisition Quality signal.',
        'condition_signal': 'acquisition_quality',
        'condition_operator': 'equals',
        'condition_value': 0,
        'condition_duration_days': None,
        'action_type': 'tag',
        'action_target': 'cold-acquisition',
        'action_esp_sync': 1,
        'action_dry_run': 1,
    },
    {
        'template_id': 'alert_bounce_exposure',
        'rule_name': 'Alert when Bounce Exposure drops below 15',
        'description': 'Fires an Early Warning alert when Bounce Exposure signal score falls below 15/25 (elevated risk).',
        'condition_signal': 'bounce_exposure_score',
        'condition_operator': 'less_than',
        'condition_value': 15,
        'condition_duration_days': None,
        'action_type': 'notify',
        'action_target': None,
        'action_esp_sync': 0,
        'action_dry_run': 1,
    },
    {
        'template_id': 'suppress_hard_bounces',
        'rule_name': 'Auto-suppress hard bounces immediately',
        'description': 'Suppress contacts flagged as hard bounces. Standard list hygiene.',
        'condition_signal': 'is_hard_bounce',
        'condition_operator': 'equals',
        'condition_value': 1,
        'condition_duration_days': None,
        'action_type': 'suppress',
        'action_target': 'hard_bounce',
        'action_esp_sync': 1,
        'action_dry_run': 1,
    },
    {
        'template_id': 'move_90_day_atrisk',
        'rule_name': 'Move 90-day inactive to At-Risk segment',
        'description': 'Automatically classify 90-day inactive contacts as At-Risk for targeted re-engagement campaigns.',
        'condition_signal': 'days_since_engagement',
        'condition_operator': 'greater_than',
        'condition_value': 90,
        'condition_duration_days': 90,
        'action_type': 'move_segment',
        'action_target': 'at_risk',
        'action_esp_sync': 1,
        'action_dry_run': 1,
    },
    {
        'template_id': 'alert_engagement_declining',
        'rule_name': 'Alert when Engagement Trajectory is declining',
        'description': 'Fires an Early Warning when Engagement Trajectory signal score drops below 15/25.',
        'condition_signal': 'engagement_trajectory_score',
        'condition_operator': 'less_than',
        'condition_value': 15,
        'condition_duration_days': None,
        'action_type': 'notify',
        'action_target': None,
        'action_esp_sync': 0,
        'action_dry_run': 1,
    },
    {
        'template_id': 'flag_catch_all',
        'rule_name': 'Flag catch-all domain addresses for review',
        'description': 'Tags contacts on catch-all domains (high bounce risk) for manual review.',
        'condition_signal': 'is_catch_all',
        'condition_operator': 'equals',
        'condition_value': 1,
        'condition_duration_days': None,
        'action_type': 'tag',
        'action_target': 'catch-all-review',
        'action_esp_sync': 1,
        'action_dry_run': 1,
    },
    {
        'template_id': 'suppress_disposable',
        'rule_name': 'Suppress disposable email addresses',
        'description': 'Automatically suppress contacts with disposable/temporary email domains.',
        'condition_signal': 'is_disposable',
        'condition_operator': 'equals',
        'condition_value': 1,
        'condition_duration_days': None,
        'action_type': 'suppress',
        'action_target': 'disposable',
        'action_esp_sync': 1,
        'action_dry_run': 1,
    },
    {
        'template_id': 'alert_dormancy_risk',
        'rule_name': 'Alert when Spam Trap Exposure is medium or higher',
        'description': 'Fires an alert when Spam Trap Exposure signal score drops below 7/10.',
        'condition_signal': 'dormancy_risk_score',
        'condition_operator': 'less_than',
        'condition_value': 7,
        'condition_duration_days': None,
        'action_type': 'notify',
        'action_target': None,
        'action_esp_sync': 0,
        'action_dry_run': 1,
    },
    {
        'template_id': 'block_send_danger',
        'rule_name': 'Block send when Signal Score drops below 45',
        'description': 'Fires a Pre-send Check alert if total Signal Score drops below 45 (D/F grade). You decide whether to send.',
        'condition_signal': 'total_signal_score',
        'condition_operator': 'less_than',
        'condition_value': 45,
        'condition_duration_days': None,
        'action_type': 'notify',
        'action_target': 'send_block',
        'action_esp_sync': 0,
        'action_dry_run': 1,
    },
]


# ── 9. Constants for CSV upload path ──────────────────

CSV_EXPECTED_COLUMNS = {
    'email': ['email', 'Email', 'EMAIL', 'email_address', 'Email Address'],
    'last_open_date': ['last_open', 'Last Open', 'last_opened', 'last_open_date'],
    'last_click_date': ['last_click', 'Last Click', 'last_clicked', 'last_click_date'],
    'acquisition_date': ['acquisition_date', 'date_added', 'Date Added', 'signup_date', 'subscribe_date', 'joined'],
}


def find_csv_column(row_dict, field):
    """Given a parsed CSV row dict and a logical field, return the matching column value or None."""
    for candidate in CSV_EXPECTED_COLUMNS.get(field, []):
        if candidate in row_dict and row_dict[candidate]:
            return row_dict[candidate]
    return None


# ── 10. Helper: Signal labels for homepage/marketing ──

def get_homepage_signal_pills():
    """Return ordered list of signal pills for homepage mechanism section."""
    order = ['bounce_exposure', 'engagement_trajectory', 'acquisition_quality',
             'domain_reputation', 'dormancy_risk', 'authentication_standing', 'decay_velocity']
    return [
        {
            'number': SIGNAL_DIMENSION_COPY[s]['number'],
            'name': SIGNAL_DIMENSION_COPY[s]['name'],
            'note': SIGNAL_DIMENSION_COPY[s]['note'],
            'market_first': SIGNAL_DIMENSION_COPY[s]['market_first'],
        }
        for s in order
    ]
