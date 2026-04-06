"""
InbXr Signal Intelligence — Signal Alerts & Early Warning

Creates signal-specific alerts in the existing `alerts` table
(which was extended with signal_dimension, recommended_action, action_url,
severity, is_dismissed columns in migration 022).

Reference: SIGNAL_SPEC.md Phase 4 + Phase 1 decision to reuse existing
alerts table instead of creating a parallel signal_alerts table.

Early Warning Rules:
- Fired by Signal Watch after each Signal Score calculation
- Use trend language only (no predictive day counts per Phase 1 decision)
- Do not fire duplicate alerts within a 7-day window
"""

import logging
from datetime import datetime, timedelta

from modules.database import execute, fetchone, fetchall
from modules.signal_score import _utcnow

logger = logging.getLogger("inbxr.signal_alerts")


# ── Early Warning Rule Definitions ────────────────────
#
# Each rule has:
# - id: unique identifier for dedup
# - signal: which signal dimension triggers it
# - condition: lambda(signal_result) -> bool
# - severity: 'info' | 'warning' | 'danger' | 'critical'
# - title: alert title
# - message_fn: lambda(signal_result) -> str (formatted message)
# - recommended_action: suggested next step
# - action_url: where to act
#
# No predictive day counts per Phase 1 decision. Use trend language only.

EARLY_WARNING_RULES = [
    {
        'id': 'engagement_declining',
        'signal': 'engagement_trajectory',
        'condition': lambda r: (
            r.get('metadata', {}).get('engagement_trajectory', {}).get('trajectory') == 'declining'
            and r.get('metadata', {}).get('engagement_trajectory', {}).get('real_engagement_30d', 100) < 10
        ),
        'severity': 'warning',
        'title': 'Engagement Trajectory is declining',
        'message_fn': lambda r: (
            f"Real human engagement (MPP-adjusted) dropped to "
            f"{r.get('metadata', {}).get('engagement_trajectory', {}).get('real_engagement_30d', 0)}% "
            f"over the last 30 days. Trajectory is {r.get('trajectory_direction', 'unknown')}. "
            f"Real engagement is your leading deliverability indicator."
        ),
        'recommended_action': 'Run Recovery Sequences on your declining segment',
        'action_url': '/recovery-sequences',
    },
    {
        'id': 'bounce_exposure_high',
        'signal': 'bounce_exposure',
        'condition': lambda r: (
            r.get('metadata', {}).get('bounce_exposure', {}).get('bounce_rate', 0) > 5
            or r.get('metadata', {}).get('bounce_exposure', {}).get('predictive_risk', 0) > 8
        ),
        'severity': 'warning',
        'title': 'Bounce Exposure is elevated',
        'message_fn': lambda r: (
            f"Bounce Exposure is elevated — "
            f"{r.get('metadata', {}).get('bounce_exposure', {}).get('bounce_rate', 0)}% historical bounces + "
            f"{r.get('metadata', {}).get('bounce_exposure', {}).get('predictive_risk', 0)}% predictive risk. "
            f"Suppress high-risk contacts before your next send."
        ),
        'recommended_action': 'Review high-risk contacts in Signal Map or run List Verification',
        'action_url': '/signal-map',
    },
    {
        'id': 'authentication_failing',
        'signal': 'authentication_standing',
        'condition': lambda r: (
            'none' in r.get('metadata', {}).get('authentication_standing', {}).get('dmarc', '').lower()
            or 'missing' in r.get('metadata', {}).get('authentication_standing', {}).get('dmarc', '').lower()
        ),
        'severity': 'warning',
        'title': 'Authentication Standing below 2025 threshold',
        'message_fn': lambda r: (
            f"Your DMARC policy is {r.get('metadata', {}).get('authentication_standing', {}).get('dmarc', 'unknown')}. "
            f"Microsoft's May 2025 bulk sender requirements reject DMARC p=none. "
            f"Fix your DMARC policy before you hit Microsoft's enforcement cutoff."
        ),
        'recommended_action': 'Fix DMARC policy in Inboxer Sender Check',
        'action_url': '/sender',
    },
    {
        'id': 'acquisition_quality_cold',
        'signal': 'acquisition_quality',
        'condition': lambda r: (
            r.get('metadata', {}).get('acquisition_quality', {}).get('assessment') == 'cold'
        ),
        'severity': 'info',
        'title': 'Cold acquisition pattern detected',
        'message_fn': lambda r: (
            f"Acquisition Quality is cold — "
            f"{r.get('metadata', {}).get('acquisition_quality', {}).get('cold_cohorts', 0)} "
            f"recent import cohorts show under 15% day-1 engagement. "
            f"This segment carries elevated deliverability risk."
        ),
        'recommended_action': 'Run Recovery Sequences before sending to cold cohorts',
        'action_url': '/recovery-sequences',
    },
    {
        'id': 'dormancy_risk_high',
        'signal': 'dormancy_risk',
        'condition': lambda r: (
            r.get('metadata', {}).get('dormancy_risk', {}).get('risk_level') == 'high'
        ),
        'severity': 'warning',
        'title': 'Dormancy Risk is high',
        'message_fn': lambda r: (
            f"Dormancy Risk is high — "
            f"{r.get('metadata', {}).get('dormancy_risk', {}).get('very_old_inactive_rate', 0)}% "
            f"of contacts have been inactive for 365+ days. Long-dormant contacts are the most likely "
            f"to become hard bounces, spam complaints, or trap hits."
        ),
        'recommended_action': 'Apply Signal Rule to suppress 180-day dormant contacts',
        'action_url': '/signal-rules',
    },
    {
        'id': 'decay_trajectory_declining',
        'signal': 'decay_velocity',
        'condition': lambda r: (
            r.get('trajectory_direction') == 'declining'
            and r.get('total_signal_score', 100) < 60
        ),
        'severity': 'danger',
        'title': 'Signal Score is declining toward danger',
        'message_fn': lambda r: (
            f"Your Signal Score is trending down. Current: "
            f"{r.get('total_signal_score', 0):.0f}/100 ({r.get('signal_grade', '?')}). "
            f"Act before your next send to reverse the trajectory."
        ),
        'recommended_action': 'Run Recovery Sequences + review Signal Map',
        'action_url': '/signal-score',
    },
    {
        'id': 'domain_reputation_yahoo_aol',
        'signal': 'domain_reputation',
        'condition': lambda r: (
            r.get('metadata', {}).get('domain_reputation', {}).get('yahoo_aol_risk') == 'high'
        ),
        'severity': 'warning',
        'title': 'High Yahoo/AOL concentration',
        'message_fn': lambda r: (
            f"{r.get('metadata', {}).get('domain_reputation', {}).get('yahoo_aol_rate', 0)}% "
            f"of your list is on Yahoo/AOL. Post-April 2024 enforcement, these providers "
            f"are more aggressive with filtering. Watch your bounce + complaint rates closely."
        ),
        'recommended_action': 'Verify authentication passes Yahoo/AOL mandates',
        'action_url': '/sender',
    },
    {
        'id': 'domain_reputation_blacklisted',
        'signal': 'domain_reputation',
        'condition': lambda r: (
            r.get('metadata', {}).get('domain_reputation', {}).get('blacklisted', False)
        ),
        'severity': 'critical',
        'title': 'Sender is on a blocklist',
        'message_fn': lambda r: (
            f"Your sending domain is listed on "
            f"{r.get('metadata', {}).get('domain_reputation', {}).get('blacklists_count', 1)} blocklist(s). "
            f"Deliverability will be severely impacted. Address this immediately."
        ),
        'recommended_action': 'Check Reputation Watch for delisting options',
        'action_url': '/blacklist-monitor',
    },
]


# ── Duplicate suppression ──────────────────────────────

ALERT_DEDUP_WINDOW_DAYS = 7


def _alert_exists_recently(user_id, rule_title, window_days=ALERT_DEDUP_WINDOW_DAYS):
    """Check if the same early warning title fired in the last N days."""
    since = (_utcnow() - timedelta(days=window_days)).isoformat()
    existing = fetchone(
        """SELECT id FROM alerts
           WHERE user_id = ? AND alert_type = 'early_warning'
           AND title = ?
           AND is_dismissed = 0
           AND created_at >= ?
           LIMIT 1""",
        (user_id, rule_title, since),
    )
    return existing is not None


# ── Main entry point ───────────────────────────────────

def check_early_warning_conditions(user_id, signal_result):
    """
    Check all Early Warning rules against a Signal Score result.
    Creates alerts (in the existing `alerts` table) for any rules that fire,
    unless the same rule already fired in the last 7 days (dedup).

    Called by Signal Watch scheduler job after each calculate_signal_score().

    Returns a dict of:
    - rules_evaluated: count of rules checked
    - alerts_created: count of new alerts
    - skipped_duplicate: count of rules that would fire but were deduped
    """
    import json

    summary = {
        'rules_evaluated': 0,
        'alerts_created': 0,
        'skipped_duplicate': 0,
        'errors': [],
    }

    for rule in EARLY_WARNING_RULES:
        summary['rules_evaluated'] += 1

        try:
            # Evaluate the condition
            if not rule['condition'](signal_result):
                continue

            # Dedup check (by title — each rule has a unique title)
            if _alert_exists_recently(user_id, rule['title']):
                summary['skipped_duplicate'] += 1
                continue

            # Fire the alert
            message = rule['message_fn'](signal_result)
            data_json = json.dumps({
                'rule_id': rule['id'],
                'signal_dimension': rule['signal'],
                'signal_score': signal_result.get('total_signal_score'),
                'signal_grade': signal_result.get('signal_grade'),
                'trajectory': signal_result.get('trajectory_direction'),
            })

            execute(
                """INSERT INTO alerts (
                    user_id, alert_type, title, message, data_json, is_read,
                    signal_dimension, recommended_action, action_url, severity, is_dismissed
                ) VALUES (?, 'early_warning', ?, ?, ?, 0, ?, ?, ?, ?, 0)""",
                (
                    user_id,
                    rule['title'],
                    message,
                    data_json,
                    rule['signal'],
                    rule['recommended_action'],
                    rule['action_url'],
                    rule['severity'],
                ),
            )

            summary['alerts_created'] += 1
            logger.info(f'Early Warning fired: {rule["id"]} for user {user_id}')

        except Exception as e:
            logger.exception(f'Early Warning rule {rule["id"]} error')
            summary['errors'].append(f'{rule["id"]}: {type(e).__name__}')

    return summary


# ── Alert retrieval helpers ────────────────────────────

def get_signal_alerts(user_id, include_dismissed=False, limit=20):
    """Get signal-related alerts for a user."""
    sql = """SELECT * FROM alerts
             WHERE user_id = ?
             AND (alert_type IN ('early_warning', 'signal_rule', 'threshold')
                  OR signal_dimension IS NOT NULL)"""
    if not include_dismissed:
        sql += " AND is_dismissed = 0"
    sql += " ORDER BY created_at DESC LIMIT ?"

    return fetchall(sql, (user_id, limit))


def dismiss_alert(user_id, alert_id):
    """Dismiss an alert (soft delete)."""
    execute(
        "UPDATE alerts SET is_dismissed = 1 WHERE id = ? AND user_id = ?",
        (alert_id, user_id),
    )
    return {'ok': True}


def get_unread_signal_alert_count(user_id):
    """Count unread signal alerts for the nav badge."""
    result = fetchone(
        """SELECT COUNT(*) as cnt FROM alerts
           WHERE user_id = ? AND is_read = 0 AND is_dismissed = 0
           AND (alert_type IN ('early_warning', 'signal_rule', 'threshold')
                OR signal_dimension IS NOT NULL)""",
        (user_id,),
    )
    return result['cnt'] if result else 0
