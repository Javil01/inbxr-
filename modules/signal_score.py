"""
InbXr Signal Intelligence — Signal Score Engine

Pure calculation functions for The 7 Inbox Signals.
No ESP coupling, no database writes — just math on contact data + auth data.

All signals return (score: float, metadata: dict).
The master function calculate_signal_score() composes them into a result dict
that save_signal_score() (in this module) persists to the database.

Reference: SIGNAL_SPEC.md for locked decisions.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from modules.database import execute, fetchone, fetchall


def _utcnow():
    """Return naive UTC datetime, matching the storage format used across the engine.

    Replaces deprecated _utcnow() (Python 3.12+ deprecation warning).
    Stays naive so comparisons with parsed-from-string datetimes still work
    without breaking existing code.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
from modules.signal_copy import (
    PRO_SIGNAL_WEIGHTS,
    FREE_SIGNAL_WEIGHTS,
    FREE_TIER_LOCKED_SIGNALS,
    ESP_MPP_ACCURACY,
    get_grade,
    get_weights_for_tier,
)

logger = logging.getLogger("inbxr.signal_score")


# ── Thresholds and constants ───────────────────────────

# Apple MPP domain fallback (low-accuracy catch)
APPLE_DOMAIN_HEURISTIC = {
    'icloud.com', 'me.com', 'mac.com',
    'apple.com', 'privaterelay.appleid.com',
}

# Apple IP range (17.0.0.0/8) — for Mailgun high-accuracy MPP detection
APPLE_IP_PREFIX = '17.'

# Timing heuristic: opens within this many seconds of send are likely machine
MPP_TIMING_THRESHOLD_SECONDS = 2

# Acquisition cohort: <15% day-1 engagement = cold acquisition signal
COLD_ACQUISITION_THRESHOLD = 0.15

# Free domain list for Domain Reputation signal
FREE_EMAIL_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'aol.com', 'icloud.com', 'me.com', 'mac.com',
    'live.com', 'msn.com', 'protonmail.com', 'gmx.com',
}

# Yahoo/AOL risk domains (post-April 2024 enforcement)
YAHOO_AOL_DOMAINS = {
    'yahoo.com', 'aol.com', 'ymail.com', 'yahoo.co.uk',
    'yahoo.ca', 'yahoo.com.au', 'yahoo.de', 'yahoo.fr',
    'rocketmail.com',
}

# Segment day ranges
SEGMENT_ACTIVE_MAX_DAYS = 30
SEGMENT_WARM_MAX_DAYS = 90
SEGMENT_AT_RISK_MAX_DAYS = 180


# ── Date parsing helper ────────────────────────────────

def _parse_date(value):
    """Safely parse a date value to datetime. Returns None if invalid.

    Handles:
    - datetime objects (returned as-is)
    - ISO 8601 strings
    - 'YYYY-MM-DD HH:MM:SS' strings
    - None / empty string
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        # Try ISO 8601 first
        s = str(value).strip()
        if not s:
            return None
        # Handle trailing Z
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            # Try common SQLite format without T
            if ' ' in s:
                return datetime.strptime(s.split('.')[0], '%Y-%m-%d %H:%M:%S')
            return datetime.strptime(s[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


# ── MPP Detection (hybrid per-ESP) ────────────────────

def detect_mpp_open(contact, event=None, esp_type=None):
    """
    Detect whether an open event was likely an Apple MPP machine open.

    Returns (is_mpp_likely: bool, confidence: str) where confidence is:
    - "high": Mailgun User-Agent + IP detection OR AC webhook UA detection
    - "medium": timing heuristic OR iCloud domain fallback
    - "low": iCloud domain only
    - "none": no detection possible

    Hybrid per-ESP model:
        Mailgun        High via events API (UA + IP)
        ActiveCampaign High via webhook open events (hardware/os/browser).
                       Baseline medium via timing heuristic on sync.
        Mailchimp      Medium via timing heuristic (no UA exposed)
        AWeber         Medium via timing heuristic
    """
    email = (contact.get('email') or '').lower()
    email_domain = email.split('@')[-1] if '@' in email else ''
    is_apple_domain = email_domain in APPLE_DOMAIN_HEURISTIC

    # Sticky high-confidence: contact already flagged via webhook UA detection
    # (set by blueprints/webhook_routes.py _handle_ac_open). Once promoted,
    # the contact stays high-confidence regardless of esp_type.
    if contact.get('mpp_detection_method') == 'ua_webhook':
        return bool(contact.get('likely_mpp_opener')), 'high'

    # Mailgun high-accuracy path (User-Agent + IP on events API)
    if esp_type == 'mailgun' and event:
        user_agent = (event.get('client-info', {}).get('user-agent', '') or '').lower()
        client_ip = event.get('ip', '') or ''

        # Apple IP range
        if client_ip.startswith(APPLE_IP_PREFIX):
            return True, 'high'

        # User-Agent patterns for Apple Mail
        if 'applemail' in user_agent or 'mail/' in user_agent and 'apple' in user_agent:
            return True, 'high'

        # Fall through to lower-accuracy checks even for Mailgun
        if is_apple_domain:
            return True, 'low'
        return False, 'high'  # Confident it's NOT MPP

    # ActiveCampaign webhook open events carry hardware/os/browser fields
    if esp_type == 'activecampaign' and event:
        blob = " ".join([
            (event.get('hardware') or '').lower(),
            (event.get('os') or '').lower(),
            (event.get('browser') or '').lower(),
            (event.get('user_agent') or '').lower(),
        ])
        if blob.strip():
            # Apple patterns
            apple_patterns = ('applemail', 'mac os', 'macos', 'iphone', 'ipad', 'ios')
            if any(p in blob for p in apple_patterns):
                return True, 'high'
            # UA data was present but didn't match Apple — confident non-MPP
            if is_apple_domain:
                return True, 'low'
            return False, 'high'

    # Timing heuristic (for Mailchimp/ActiveCampaign/AWeber without UA data)
    if event and event.get('send_time') and event.get('open_time'):
        send_dt = _parse_date(event['send_time'])
        open_dt = _parse_date(event['open_time'])
        if send_dt and open_dt:
            delta_seconds = (open_dt - send_dt).total_seconds()
            if 0 <= delta_seconds <= MPP_TIMING_THRESHOLD_SECONDS:
                return True, 'medium'

    # Domain fallback (lowest accuracy)
    if is_apple_domain:
        return True, 'low'

    return False, 'none'


def get_esp_mpp_accuracy(esp_type):
    """Return the accuracy level ('high' | 'medium' | 'low' | 'none') for a given ESP."""
    return ESP_MPP_ACCURACY.get(esp_type, 'medium')


# ── Signal 01: Bounce Exposure (0-25) ──────────────────

def calculate_bounce_exposure(contacts):
    """
    Signal 01 — Bounce Exposure (0-25 points Pro, 0-42 Free normalized).
    Predictive risk from verification flags + historical bounces.
    """
    if not contacts:
        return 12.5, {
            'reason': 'no_data',
            'bounce_rate': 0,
            'predictive_risk': 0,
            'catch_all_rate': 0,
            'total_contacts': 0,
        }

    total = len(contacts)
    hard_bounced = sum(1 for c in contacts if c.get('is_hard_bounce'))
    catch_all_risk = sum(1 for c in contacts if c.get('is_catch_all'))
    role_addresses = sum(1 for c in contacts if c.get('is_role_address'))
    disposable = sum(1 for c in contacts if c.get('is_disposable'))

    # Bounce rate (historical)
    bounce_rate = hard_bounced / total if total > 0 else 0

    # Predictive risk composite
    risk_rate = 0
    if total > 0:
        risk_rate = (catch_all_risk * 0.3 + role_addresses * 0.5 + disposable) / total

    # Combined exposure
    exposure = bounce_rate * 0.6 + risk_rate * 0.4

    # Invert: 0 exposure = 25 pts, 20%+ exposure = 0 pts
    score = max(0, 25 * (1 - min(exposure / 0.20, 1)))

    return round(score, 1), {
        'bounce_rate': round(bounce_rate * 100, 2),
        'catch_all_rate': round((catch_all_risk / total * 100) if total > 0 else 0, 2),
        'role_rate': round((role_addresses / total * 100) if total > 0 else 0, 2),
        'disposable_rate': round((disposable / total * 100) if total > 0 else 0, 2),
        'predictive_risk': round(risk_rate * 100, 2),
        'total_contacts': total,
    }


# ── Signal 02: Engagement Trajectory MPP-adjusted (0-25) ──

def calculate_engagement_trajectory(contacts, esp_type=None):
    """
    Signal 02 — Engagement Trajectory (0-25 points).
    MPP-adjusted engagement direction.

    Note: free tier doesn't see this signal (it's locked).
    """
    if not contacts:
        return 12.5, {
            'reason': 'no_data',
            'mpp_adjusted': False,
            'mpp_accuracy': 'none',
            'trajectory': 'unknown',
        }

    total = len(contacts)
    now = _utcnow()
    accuracy = get_esp_mpp_accuracy(esp_type) if esp_type else 'medium'

    real_openers_30d = 0
    real_openers_90d = 0
    clickers_30d = 0
    clickers_90d = 0
    repliers_30d = 0
    mpp_discounted = 0

    for c in contacts:
        # Parse dates
        last_open = _parse_date(c.get('last_open_date'))
        last_click = _parse_date(c.get('last_click_date'))
        last_reply = _parse_date(c.get('last_reply_date'))

        # MPP detection at contact level (per-open event detection happens in sync layer)
        is_likely_mpp = c.get('likely_mpp_opener', False)
        if not is_likely_mpp:
            # Fallback: check email domain (lowest accuracy)
            email_domain = (c.get('email') or '').lower().split('@')[-1]
            is_likely_mpp = email_domain in APPLE_DOMAIN_HEURISTIC

        # Count real opens (non-MPP)
        if last_open:
            days_since = (now - last_open).days
            if is_likely_mpp:
                mpp_discounted += 1
            else:
                if days_since <= 30:
                    real_openers_30d += 1
                if days_since <= 90:
                    real_openers_90d += 1

        if last_click:
            days_since = (now - last_click).days
            if days_since <= 30:
                clickers_30d += 1
            if days_since <= 90:
                clickers_90d += 1

        if last_reply:
            days_since = (now - last_reply).days
            if days_since <= 30:
                repliers_30d += 1

    # Weight clicks and replies higher (real human signals)
    engagement_30d = 0
    engagement_90d = 0
    if total > 0:
        engagement_30d = (
            (real_openers_30d * 0.4) +
            (clickers_30d * 0.4) +
            (repliers_30d * 0.2)
        ) / total
        engagement_90d = (
            (real_openers_90d * 0.5) +
            (clickers_90d * 0.5)
        ) / total

    # Trajectory direction (no day predictions — trend language only)
    trajectory = 'stable'
    if engagement_30d > engagement_90d * 1.1:
        trajectory = 'improving'
    elif engagement_30d < engagement_90d * 0.85:
        trajectory = 'declining'

    # Score: base on recent engagement, modify by trajectory
    base = min(engagement_30d * 2.5, 1.0)
    modifier = 1.1 if trajectory == 'improving' else (0.85 if trajectory == 'declining' else 1.0)
    score = min(25, 25 * base * modifier)

    mpp_rate = (mpp_discounted / total * 100) if total > 0 else 0

    return round(score, 1), {
        'mpp_adjusted': True,
        'mpp_accuracy': accuracy,
        'mpp_discounted_opens': mpp_discounted,
        'mpp_discount_rate': round(mpp_rate, 2),
        'real_engagement_30d': round(engagement_30d * 100, 2),
        'real_engagement_90d': round(engagement_90d * 100, 2),
        'click_rate_30d': round((clickers_30d / total * 100) if total > 0 else 0, 2),
        'reply_rate_30d': round((repliers_30d / total * 100) if total > 0 else 0, 2),
        'trajectory': trajectory,
    }


# ── Signal 03: Acquisition Quality (0-15) ────────────

def calculate_acquisition_quality(contacts):
    """
    Signal 03 — Acquisition Quality (0-15 points).
    Inferred from day-1 engagement cohort patterns.

    Note: free tier doesn't see this signal (it's locked).
    """
    if not contacts:
        return 7.5, {'reason': 'no_data', 'assessment': 'unknown'}

    cohorts = {}
    for c in contacts:
        acq_date = _parse_date(c.get('acquisition_date'))
        if not acq_date:
            continue

        cohort_key = acq_date.strftime('%Y-%m')
        if cohort_key not in cohorts:
            cohorts[cohort_key] = {'total': 0, 'engaged_early': 0}
        cohorts[cohort_key]['total'] += 1

        # Did this contact engage in the first 30 days after acquisition?
        last_open = _parse_date(c.get('last_open_date'))
        last_click = _parse_date(c.get('last_click_date'))

        first_engagement = None
        if last_click and last_open:
            first_engagement = min(last_click, last_open)
        else:
            first_engagement = last_click or last_open

        if first_engagement:
            days_to_engage = (first_engagement - acq_date).days
            if 0 <= days_to_engage <= 30:
                cohorts[cohort_key]['engaged_early'] += 1

    if not cohorts:
        return 7.5, {
            'reason': 'no_acquisition_dates',
            'assessment': 'unknown',
            'organic_cohorts': 0,
            'cold_cohorts': 0,
            'organic_ratio': 0,
        }

    # Evaluate cohort quality
    cold_cohorts = 0
    organic_cohorts = 0
    for cohort_key, data in cohorts.items():
        if data['total'] < 10:  # Skip tiny cohorts
            continue
        early_rate = data['engaged_early'] / data['total']
        if early_rate < COLD_ACQUISITION_THRESHOLD:
            cold_cohorts += 1
        else:
            organic_cohorts += 1

    total_evaluable = cold_cohorts + organic_cohorts
    if total_evaluable == 0:
        return 10, {
            'reason': 'insufficient_cohort_data',
            'assessment': 'unknown',
            'organic_cohorts': 0,
            'cold_cohorts': 0,
            'organic_ratio': 0,
        }

    organic_ratio = organic_cohorts / total_evaluable
    score = 15 * organic_ratio

    if organic_ratio > 0.7:
        assessment = 'organic'
    elif organic_ratio > 0.4:
        assessment = 'mixed'
    else:
        assessment = 'cold'

    return round(score, 1), {
        'organic_cohorts': organic_cohorts,
        'cold_cohorts': cold_cohorts,
        'organic_ratio': round(organic_ratio * 100, 2),
        'assessment': assessment,
    }


# ── Signal 04: Domain Reputation (0-15) ──────────────

def calculate_domain_reputation(contacts, auth_data):
    """
    Signal 04 — Domain Reputation (0-15 points).
    Sender-side (blacklist) + recipient-side (domain distribution).
    """
    score = 15  # Start full, deduct
    metadata = {
        'blacklisted': False,
        'blacklists_count': 0,
        'yahoo_aol_rate': 0,
        'yahoo_aol_risk': 'normal',
        'free_email_rate': 0,
    }

    # Recipient side
    if contacts:
        total = len(contacts)

        # Yahoo/AOL concentration
        yahoo_aol_count = sum(
            1 for c in contacts
            if (c.get('email') or '').lower().split('@')[-1] in YAHOO_AOL_DOMAINS
        )
        yahoo_aol_rate = yahoo_aol_count / total if total > 0 else 0
        metadata['yahoo_aol_rate'] = round(yahoo_aol_rate * 100, 2)

        if yahoo_aol_rate > 0.40:
            score -= 4
            metadata['yahoo_aol_risk'] = 'high'
        elif yahoo_aol_rate > 0.25:
            score -= 2
            metadata['yahoo_aol_risk'] = 'elevated'

        # Free-email ratio
        free_count = sum(
            1 for c in contacts
            if (c.get('email') or '').lower().split('@')[-1] in FREE_EMAIL_DOMAINS
        )
        free_rate = free_count / total if total > 0 else 0
        metadata['free_email_rate'] = round(free_rate * 100, 2)

        if free_rate > 0.80:
            score -= 2  # Heavy consumer list = higher complaint risk

    # Sender side
    if auth_data:
        blacklisted = auth_data.get('blacklisted', False)
        blacklists_count = auth_data.get('blacklists_count', 0)
        if blacklisted or blacklists_count > 0:
            score -= 6
            metadata['blacklisted'] = True
            metadata['blacklists_count'] = blacklists_count

    return round(max(0, score), 1), metadata


# ── Signal 05: Dormancy Risk (0-10) ───────────────────
# Renamed from "Spam Trap Exposure" per Phase 1 decision

def calculate_dormancy_risk(contacts):
    """
    Signal 05 — Dormancy Risk (0-10 points).
    Age-weighted scoring of dormant contacts.

    This was renamed from "Spam Trap Exposure" in v2 because the formula
    measures dormancy depth, not actual Spamhaus/Abusix trap seeding.
    Honest naming: Dormancy Risk.
    """
    if not contacts:
        return 5, {'reason': 'no_data', 'risk_level': 'unknown'}

    total = len(contacts)
    now = _utcnow()

    very_old_inactive = 0  # 365+ days
    old_inactive = 0       # 180-364 days

    for c in contacts:
        last_engagement_dates = [
            _parse_date(c.get('last_open_date')),
            _parse_date(c.get('last_click_date')),
            _parse_date(c.get('last_reply_date')),
        ]
        last_any = max([d for d in last_engagement_dates if d], default=None)

        if last_any:
            days_inactive = (now - last_any).days
            if days_inactive >= 365:
                very_old_inactive += 1
            elif days_inactive >= 180:
                old_inactive += 1
        else:
            # No engagement data = treat as very old
            very_old_inactive += 1

    very_old_rate = very_old_inactive / total if total > 0 else 0
    old_rate = old_inactive / total if total > 0 else 0

    trap_risk = (very_old_rate * 0.7) + (old_rate * 0.3)

    # Invert: 0 risk = 10 pts, 30%+ risk = 0 pts
    score = max(0, 10 * (1 - min(trap_risk / 0.30, 1)))

    if trap_risk > 0.20:
        risk_level = 'high'
    elif trap_risk > 0.10:
        risk_level = 'medium'
    else:
        risk_level = 'low'

    return round(score, 1), {
        'very_old_inactive_rate': round(very_old_rate * 100, 2),
        'old_inactive_rate': round(old_rate * 100, 2),
        'very_old_inactive_count': very_old_inactive,
        'old_inactive_count': old_inactive,
        'risk_level': risk_level,
    }


# ── Signal 06: Authentication Standing (0-5) ─────────

def calculate_authentication_standing(auth_data):
    """
    Signal 06 — Authentication Standing (0-5 points).
    Scored against 2024-2025 ISP mandates from isp_compliance_requirements table.
    """
    if not auth_data:
        return 2, {
            'reason': 'no_auth_data',
            'spf': 'unknown',
            'dkim': 'unknown',
            'dmarc': 'unknown',
            'list_unsubscribe': 'unknown',
        }

    score = 0
    details = {}

    # SPF (1 pt)
    if auth_data.get('spf_valid'):
        score += 1
        details['spf'] = 'pass'
    else:
        details['spf'] = 'fail'

    # DKIM (1 pt)
    if auth_data.get('dkim_valid'):
        score += 1
        details['dkim'] = 'pass'
    else:
        details['dkim'] = 'fail'

    # DMARC — scored by policy strength (2 pts)
    dmarc_policy = (auth_data.get('dmarc_policy') or 'none').lower()
    if dmarc_policy == 'reject':
        score += 2
        details['dmarc'] = 'reject (full credit — passes all 2025 mandates)'
    elif dmarc_policy == 'quarantine':
        score += 1.5
        details['dmarc'] = 'quarantine (partial credit — passes Microsoft 2025)'
    elif dmarc_policy == 'none':
        score += 0.5
        details['dmarc'] = 'none (fails Microsoft May 2025 enforcement — passes Gmail/Yahoo only)'
    else:
        details['dmarc'] = 'missing (fails all 2025 mandates)'

    # List-Unsubscribe header (1 pt for full credit)
    if auth_data.get('list_unsubscribe'):
        score += 1
        details['list_unsubscribe'] = 'present'
    else:
        details['list_unsubscribe'] = 'missing (Gmail/Yahoo 2024 requirement)'

    return round(min(5, score), 1), details


# ── Signal 07: Decay Velocity (0-5) ───────────────────

def calculate_decay_velocity(user_id, esp_integration_id, contacts):
    """
    Signal 07 — Decay Velocity (0-5 points).
    Rate and direction of list degradation.

    Uses Signal Score history when available for actual trajectory.
    Falls back to segment composition for first reading.

    NOTE: per Phase 1 decision, no projected_days / no predictive claim.
    Returns trajectory_direction + velocity_rate only.
    """
    if not contacts:
        return 2.5, {
            'reason': 'no_data',
            'trajectory': 'unknown',
            'velocity_rate': 0,
        }

    segments = segment_contacts(contacts)
    total = segments['total']
    if total == 0:
        return 2.5, {'reason': 'no_contacts', 'trajectory': 'unknown'}

    at_risk_rate = segments['at_risk'] / total
    dormant_rate = segments['dormant'] / total

    decay_index = (at_risk_rate * 0.6) + (dormant_rate * 0.4)
    score = max(0, 5 * (1 - min(decay_index / 0.40, 1)))

    # Trajectory from history if available
    trajectory = 'stable'
    velocity_rate = 0

    try:
        # Get last 4 historical scores for trend
        history = fetchall(
            """SELECT total_signal_score, recorded_at
               FROM signal_score_history
               WHERE user_id = ?
               AND (esp_integration_id = ? OR esp_integration_id IS NULL)
               ORDER BY recorded_at DESC
               LIMIT 4""",
            (user_id, esp_integration_id),
        )
        if len(history) >= 2:
            latest = history[0]['total_signal_score']
            oldest = history[-1]['total_signal_score']
            delta = latest - oldest

            # Simple trajectory
            if delta > 3:
                trajectory = 'improving'
            elif delta < -3:
                trajectory = 'declining'

            # Weekly rate — crude estimate from available data
            velocity_rate = round(delta / len(history), 2)
    except Exception as e:
        logger.debug(f'Decay velocity history lookup failed: {e}')

    # If no history, use composition as fallback trajectory signal
    if trajectory == 'stable' and not at_risk_rate == 0:
        if at_risk_rate > 0.25:
            trajectory = 'declining'
        elif at_risk_rate < 0.10:
            trajectory = 'improving'

    return round(score, 1), {
        'trajectory': trajectory,
        'velocity_rate': velocity_rate,
        'at_risk_rate': round(at_risk_rate * 100, 2),
        'dormant_rate': round(dormant_rate * 100, 2),
    }


# ── Segment classification ─────────────────────────────

def segment_contacts(contacts):
    """Classify contacts into Active / Warm / At-Risk / Dormant."""
    if not contacts:
        return {'active': 0, 'warm': 0, 'at_risk': 0, 'dormant': 0, 'total': 0}

    now = _utcnow()
    segments = {'active': 0, 'warm': 0, 'at_risk': 0, 'dormant': 0, 'total': len(contacts)}

    for c in contacts:
        dates = [
            _parse_date(c.get('last_open_date')),
            _parse_date(c.get('last_click_date')),
            _parse_date(c.get('last_reply_date')),
        ]
        last_any = max([d for d in dates if d], default=None)

        if not last_any:
            segments['dormant'] += 1
            continue

        days = (now - last_any).days
        if days <= SEGMENT_ACTIVE_MAX_DAYS:
            segments['active'] += 1
        elif days <= SEGMENT_WARM_MAX_DAYS:
            segments['warm'] += 1
        elif days <= SEGMENT_AT_RISK_MAX_DAYS:
            segments['at_risk'] += 1
        else:
            segments['dormant'] += 1

    return segments


# ── Master calculation function ────────────────────────

def calculate_signal_score(
    user_id,
    esp_integration_id=None,
    contact_data=None,
    auth_data=None,
    esp_type=None,
    tier='pro',
    data_source='esp_sync',
):
    """
    Master function. Calculate all 7 signals and compose into result dict.

    Returns dict with:
    - scores: dict of 7 individual signal scores
    - total_signal_score: 0-100 composite
    - signal_grade: A/B/C/D/F
    - metadata: per-dimension detailed metadata
    - segments: contact segment counts
    - trajectory_direction: improving/stable/declining/unknown
    - velocity_rate: weekly change (no day predictions)
    - mpp_accuracy: high/medium/low/none (per ESP)
    - tier: the tier this was calculated for

    For free tier, signals 02 + 03 are marked as locked and their scores
    are not included in the composite. The remaining 5 signals are
    normalized to sum to 100.
    """
    contacts = contact_data or []

    scores = {}
    metadata = {}

    # Signal 01 — Bounce Exposure
    scores['bounce_exposure'], metadata['bounce_exposure'] = \
        calculate_bounce_exposure(contacts)

    # Signal 02 — Engagement Trajectory (Pro only, but calculated for Pro/Agency)
    if tier != 'free':
        scores['engagement_trajectory'], metadata['engagement_trajectory'] = \
            calculate_engagement_trajectory(contacts, esp_type=esp_type)
    else:
        scores['engagement_trajectory'] = 0
        metadata['engagement_trajectory'] = {'locked': True, 'reason': 'free_tier'}

    # Signal 03 — Acquisition Quality (Pro only)
    if tier != 'free':
        scores['acquisition_quality'], metadata['acquisition_quality'] = \
            calculate_acquisition_quality(contacts)
    else:
        scores['acquisition_quality'] = 0
        metadata['acquisition_quality'] = {'locked': True, 'reason': 'free_tier'}

    # Signal 04 — Domain Reputation
    scores['domain_reputation'], metadata['domain_reputation'] = \
        calculate_domain_reputation(contacts, auth_data)

    # Signal 05 — Dormancy Risk
    scores['dormancy_risk'], metadata['dormancy_risk'] = \
        calculate_dormancy_risk(contacts)

    # Signal 06 — Authentication Standing
    scores['authentication_standing'], metadata['authentication_standing'] = \
        calculate_authentication_standing(auth_data)

    # Signal 07 — Decay Velocity
    scores['decay_velocity'], metadata['decay_velocity'] = \
        calculate_decay_velocity(user_id, esp_integration_id, contacts)

    # Compose total based on tier
    if tier == 'free':
        # Free tier: use normalized weights for the 5 visible signals
        total = _compose_free_tier_score(scores)
    else:
        # Pro/Agency: signals already sum to 100 with Pro weights
        total = sum(scores.values())

    grade = get_grade(total)
    segments = segment_contacts(contacts)

    # Extract trajectory from engagement_trajectory metadata
    trajectory_direction = metadata.get('engagement_trajectory', {}).get('trajectory', 'stable')
    if tier == 'free':
        # Free tier uses decay_velocity metadata since engagement_trajectory is locked
        trajectory_direction = metadata.get('decay_velocity', {}).get('trajectory', 'stable')

    velocity_rate = metadata.get('decay_velocity', {}).get('velocity_rate', 0)

    mpp_accuracy = metadata.get('engagement_trajectory', {}).get('mpp_accuracy', 'none')
    mpp_discount_rate = metadata.get('engagement_trajectory', {}).get('mpp_discount_rate', 0)

    return {
        'scores': scores,
        'total_signal_score': round(total, 1),
        'signal_grade': grade,
        'metadata': metadata,
        'segments': segments,
        'trajectory_direction': trajectory_direction,
        'velocity_rate': velocity_rate,
        'mpp_adjusted': tier != 'free',
        'mpp_accuracy': mpp_accuracy,
        'mpp_discount_rate': mpp_discount_rate,
        'tier': tier,
        'data_source': data_source,
        'calculated_at': _utcnow().isoformat(),
    }


def _compose_free_tier_score(scores):
    """Normalize free tier 5-signal scores to sum to 100.

    Pro weights for the 5 free signals = 25 + 15 + 10 + 5 + 5 = 60
    We scale each by (100/60) ≈ 1.667 so max possible = 100
    """
    scale_factor = 100 / 60
    free_signals = {
        'bounce_exposure': scores.get('bounce_exposure', 0),
        'domain_reputation': scores.get('domain_reputation', 0),
        'dormancy_risk': scores.get('dormancy_risk', 0),
        'authentication_standing': scores.get('authentication_standing', 0),
        'decay_velocity': scores.get('decay_velocity', 0),
    }
    return sum(free_signals.values()) * scale_factor


# ── Persistence ────────────────────────────────────────

def save_signal_score(user_id, esp_integration_id, result):
    """
    Persist a Signal Score calculation to signal_scores + signal_score_history.
    Uses raw SQLite via modules/database.py (not SQLAlchemy).
    """
    scores = result['scores']
    metadata = result['metadata']
    segments = result['segments']

    # Serialize per-dimension metadata as JSON
    meta_json = {
        dim: json.dumps(metadata.get(dim, {}))
        for dim in [
            'bounce_exposure', 'engagement_trajectory', 'acquisition_quality',
            'domain_reputation', 'dormancy_risk', 'authentication_standing',
            'decay_velocity',
        ]
    }

    # Upsert current score (one row per user+integration)
    existing = fetchone(
        """SELECT id FROM signal_scores
           WHERE user_id = ? AND
                 (esp_integration_id = ? OR
                  (esp_integration_id IS NULL AND ? IS NULL))
           ORDER BY calculated_at DESC LIMIT 1""",
        (user_id, esp_integration_id, esp_integration_id),
    )

    params = (
        user_id,
        esp_integration_id,
        result.get('data_source', 'esp_sync'),
        scores.get('bounce_exposure', 0),
        scores.get('engagement_trajectory', 0),
        scores.get('acquisition_quality', 0),
        scores.get('domain_reputation', 0),
        scores.get('dormancy_risk', 0),
        scores.get('authentication_standing', 0),
        scores.get('decay_velocity', 0),
        result['total_signal_score'],
        result['signal_grade'],
        result.get('tier', 'pro'),
        1 if result.get('mpp_adjusted') else 0,
        result.get('mpp_accuracy', 'none'),
        result.get('mpp_discount_rate', 0),
        result.get('trajectory_direction', 'stable'),
        result.get('velocity_rate', 0),
        segments['active'],
        segments['warm'],
        segments['at_risk'],
        segments['dormant'],
        segments['total'],
        meta_json['bounce_exposure'],
        meta_json['engagement_trajectory'],
        meta_json['acquisition_quality'],
        meta_json['domain_reputation'],
        meta_json['dormancy_risk'],
        meta_json['authentication_standing'],
        meta_json['decay_velocity'],
    )

    if existing:
        execute(
            """UPDATE signal_scores SET
                data_source = ?,
                bounce_exposure_score = ?,
                engagement_trajectory_score = ?,
                acquisition_quality_score = ?,
                domain_reputation_score = ?,
                dormancy_risk_score = ?,
                authentication_standing_score = ?,
                decay_velocity_score = ?,
                total_signal_score = ?,
                signal_grade = ?,
                tier_at_calculation = ?,
                mpp_adjusted = ?,
                mpp_accuracy = ?,
                mpp_discount_rate = ?,
                trajectory_direction = ?,
                velocity_rate = ?,
                active_contacts = ?,
                warm_contacts = ?,
                at_risk_contacts = ?,
                dormant_contacts = ?,
                total_contacts = ?,
                bounce_exposure_meta = ?,
                engagement_trajectory_meta = ?,
                acquisition_quality_meta = ?,
                domain_reputation_meta = ?,
                dormancy_risk_meta = ?,
                authentication_standing_meta = ?,
                decay_velocity_meta = ?,
                calculated_at = datetime('now')
               WHERE id = ?""",
            params[2:] + (existing['id'],),
        )
    else:
        execute(
            """INSERT INTO signal_scores (
                user_id, esp_integration_id, data_source,
                bounce_exposure_score, engagement_trajectory_score, acquisition_quality_score,
                domain_reputation_score, dormancy_risk_score, authentication_standing_score,
                decay_velocity_score, total_signal_score, signal_grade,
                tier_at_calculation, mpp_adjusted, mpp_accuracy, mpp_discount_rate,
                trajectory_direction, velocity_rate,
                active_contacts, warm_contacts, at_risk_contacts, dormant_contacts, total_contacts,
                bounce_exposure_meta, engagement_trajectory_meta, acquisition_quality_meta,
                domain_reputation_meta, dormancy_risk_meta, authentication_standing_meta,
                decay_velocity_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            params,
        )

    # Always append to history
    execute(
        """INSERT INTO signal_score_history (
            user_id, esp_integration_id,
            total_signal_score, signal_grade,
            bounce_exposure_score, engagement_trajectory_score, acquisition_quality_score,
            domain_reputation_score, dormancy_risk_score, authentication_standing_score,
            decay_velocity_score,
            active_contacts, warm_contacts, at_risk_contacts, dormant_contacts, total_contacts,
            event_type, event_label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            esp_integration_id,
            result['total_signal_score'],
            result['signal_grade'],
            scores.get('bounce_exposure', 0),
            scores.get('engagement_trajectory', 0),
            scores.get('acquisition_quality', 0),
            scores.get('domain_reputation', 0),
            scores.get('dormancy_risk', 0),
            scores.get('authentication_standing', 0),
            scores.get('decay_velocity', 0),
            segments['active'],
            segments['warm'],
            segments['at_risk'],
            segments['dormant'],
            segments['total'],
            'score_calculated',
            f"Score: {result['total_signal_score']:.0f} ({result['signal_grade']})",
        ),
    )

    logger.info(
        f"Signal Score saved for user {user_id} (integration {esp_integration_id}): "
        f"{result['total_signal_score']:.0f} ({result['signal_grade']}), tier={result.get('tier')}"
    )


def get_latest_signal_score(user_id, esp_integration_id=None):
    """Fetch the most recent Signal Score for a user/integration."""
    return fetchone(
        """SELECT * FROM signal_scores
           WHERE user_id = ? AND
                 (esp_integration_id = ? OR
                  (esp_integration_id IS NULL AND ? IS NULL))
           ORDER BY calculated_at DESC LIMIT 1""",
        (user_id, esp_integration_id, esp_integration_id),
    )


def get_signal_history(user_id, esp_integration_id=None, limit=90):
    """Fetch signal score history for trend charts."""
    return fetchall(
        """SELECT * FROM signal_score_history
           WHERE user_id = ? AND
                 (esp_integration_id = ? OR
                  (esp_integration_id IS NULL AND ? IS NULL))
           ORDER BY recorded_at DESC LIMIT ?""",
        (user_id, esp_integration_id, esp_integration_id, limit),
    )


# ── CSV Upload Path ────────────────────────────────────

CSV_MAX_ROWS = 50000  # hard cap to prevent OOM / slow scoring on huge lists


def parse_csv_contacts(csv_content, max_rows=CSV_MAX_ROWS):
    """
    Parse a CSV string into a list of contact dicts for the signal engine.

    Expected columns (flexible header naming):
    - email / Email / email_address
    - last_open / Last Open / last_opened
    - last_click / Last Click / last_clicked
    - acquisition_date / date_added / signup_date / joined

    Returns (contacts, skipped_no_email, truncated_at) where truncated_at is
    the row index where parsing stopped due to max_rows, or None if all
    rows were consumed.
    """
    import csv
    import io

    from modules.signal_copy import find_csv_column

    reader = csv.DictReader(io.StringIO(csv_content))
    contacts = []
    skipped_no_email = 0
    truncated_at = None

    for row_idx, row in enumerate(reader, start=1):
        if len(contacts) >= max_rows:
            truncated_at = row_idx
            break
        email = find_csv_column(row, 'email')
        if not email or '@' not in str(email):
            skipped_no_email += 1
            continue

        contact = {
            'email': str(email).strip().lower(),
            'last_open_date': _parse_date(find_csv_column(row, 'last_open_date')),
            'last_click_date': _parse_date(find_csv_column(row, 'last_click_date')),
            'last_reply_date': None,
            'acquisition_date': _parse_date(find_csv_column(row, 'acquisition_date')),
            'is_hard_bounce': False,
            'is_catch_all': False,
            'is_role_address': False,
            'is_disposable': False,
            'likely_mpp_opener': False,
        }
        contacts.append(contact)

    return contacts, skipped_no_email, truncated_at


def calculate_signal_score_from_csv(
    user_id,
    csv_content,
    auth_data=None,
    tier='pro',
):
    """
    Calculate Signal Score from an uploaded CSV.
    Entry point for users without a connected ESP, or for users on
    Instantly/Smartlead/GoHighLevel who want a full 7-signal reading.

    Returns the same result dict format as calculate_signal_score(),
    plus CSV-specific metadata (rows_parsed, rows_skipped).
    """
    contacts, skipped, truncated_at = parse_csv_contacts(csv_content)

    if not contacts:
        return {
            'error': 'no_valid_contacts',
            'message': 'Could not parse any contacts from the uploaded CSV. Check that it has an "email" column.',
            'rows_parsed': 0,
            'rows_skipped': skipped,
        }

    result = calculate_signal_score(
        user_id=user_id,
        esp_integration_id=None,
        contact_data=contacts,
        auth_data=auth_data,
        esp_type=None,
        tier=tier,
        data_source='csv_upload',
    )

    result['rows_parsed'] = len(contacts)
    result['rows_skipped'] = skipped
    result['truncated_at'] = truncated_at
    return result


# ── Domain Signal Score (anonymous, no list required) ──
#
# Calculates a *partial* Signal Score from a sending domain alone.
# Reads 2 of 7 signals using public DNS data only:
#   - Authentication Standing (SPF/DKIM/DMARC + 2025 ISP enforcement)
#   - Domain Reputation (DNSBL listings + sender reputation)
#
# The other 5 signals require list data and are returned as locked cards.
# Composite score is normalized to 100 from the 2 visible signals weighted
# by their full-model importance (15 + 5 = 20 → scaled to 100).
#
# This is the lowest-friction Signal Score entry point. 30 seconds, no signup,
# no CSV. Type a domain. Get a real score. The 5 locked signals are the
# upsell that funnels visitors into signup.

def _validate_domain(domain):
    """Validate a domain string. Returns normalized domain or None."""
    if not domain or not isinstance(domain, str):
        return None
    d = domain.strip().lower().rstrip('.')
    # Strip protocol if present
    if d.startswith('http://'):
        d = d[7:]
    if d.startswith('https://'):
        d = d[8:]
    # Strip trailing path
    d = d.split('/')[0]
    # Strip port
    d = d.split(':')[0]
    # Strip @ prefix (someone might paste an email)
    if '@' in d:
        d = d.split('@')[-1]
    # Basic format check
    if not d or '.' not in d or len(d) > 253:
        return None
    if any(c for c in d if not (c.isalnum() or c in '.-')):
        return None
    return d


def calculate_domain_signal_score(domain):
    """
    Calculate a partial Signal Score from a domain alone.
    Returns the same result dict shape as calculate_signal_score(), with:
      - 2 signals filled in: authentication_standing, domain_reputation
      - 5 signals marked locked={'reason': 'needs_list_data'}
      - total_signal_score: composite of the 2 visible signals (normalized 0-100)
      - is_partial: True
      - visible_signals: 2
      - locked_signals: 5
    """
    normalized = _validate_domain(domain)
    if not normalized:
        return {
            'error': 'invalid_domain',
            'message': 'Please enter a valid sending domain (e.g. yourcompany.com).',
        }

    # Run the existing reputation analyzer for SPF/DKIM/DMARC + DNSBL data
    try:
        from modules.reputation_checker import ReputationChecker
        rc = ReputationChecker(domain=normalized)
        rep = rc.analyze()
    except Exception as e:
        logger.exception(f'Domain Signal Score: ReputationChecker failed for {normalized}')
        return {
            'error': 'analysis_failed',
            'message': f'Could not analyze {normalized}. {type(e).__name__}',
        }

    # ── Signal 06: Authentication Standing (0-100 from rep.auth.score) ──
    auth_score_100 = rep.get('auth', {}).get('score', 0)
    auth_categories = rep.get('auth', {}).get('categories', [])
    spf_status = next((c['status'] for c in auth_categories if c.get('label') == 'SPF'), 'unknown')
    dkim_status = next((c['status'] for c in auth_categories if c.get('label') == 'DKIM'), 'unknown')
    dmarc_cat = next((c for c in auth_categories if c.get('label') == 'DMARC'), {})
    dmarc_status = dmarc_cat.get('status', 'unknown')
    dmarc_policy = dmarc_cat.get('policy', 'none')

    # ── Signal 04: Domain Reputation (0-100 from rep.reputation.score) ──
    rep_score_100 = rep.get('reputation', {}).get('score', 0)
    listed_count = rep.get('reputation', {}).get('listed_count', 0)

    # ── Composite (weighted by full-model importance: auth=5, dom_rep=15) ──
    # Normalize: (auth*5 + rep*15) / 20 = auth*0.25 + rep*0.75
    composite = round(auth_score_100 * 0.25 + rep_score_100 * 0.75)

    # Letter grade from composite
    grade = _letter_grade(composite)

    # Pull recommendations (top 5 by severity) for the result page
    recommendations = rep.get('recommendations', [])[:5]

    # Log this scan to the public leaderboard (fire-and-forget, never
    # blocks the return to the caller).
    try:
        from modules.leaderboard import upsert_leaderboard_entry
        upsert_leaderboard_entry(
            domain=normalized,
            total_score=composite,
            grade=grade,
            auth_score=int(round(auth_score_100)),
            rep_score=int(round(rep_score_100)),
        )
    except Exception:
        logger.exception(f'Leaderboard upsert failed for {normalized}')

    return {
        'is_partial': True,
        'data_source': 'domain_only',
        'domain': normalized,
        'total_signal_score': composite,
        'signal_grade': grade,
        'visible_signals': 2,
        'locked_signals': 5,
        'scores': {
            'authentication_standing': round(auth_score_100 * 5 / 100, 1),
            'domain_reputation': round(rep_score_100 * 15 / 100, 1),
            'bounce_exposure': None,
            'engagement_trajectory': None,
            'acquisition_quality': None,
            'dormancy_risk': None,
            'decay_velocity': None,
        },
        'metadata': {
            'authentication_standing': {
                'spf': spf_status,
                'dkim': dkim_status,
                'dmarc': dmarc_status,
                'dmarc_policy': dmarc_policy,
                'auth_score': auth_score_100,
                'reason': 'computed_from_dns',
            },
            'domain_reputation': {
                'rep_score': rep_score_100,
                'listed_count': listed_count,
                'blacklisted': listed_count > 0,
                'reason': 'computed_from_dnsbl',
            },
            'bounce_exposure': {'locked': True, 'reason': 'needs_list_data'},
            'engagement_trajectory': {'locked': True, 'reason': 'needs_list_data'},
            'acquisition_quality': {'locked': True, 'reason': 'needs_list_data'},
            'dormancy_risk': {'locked': True, 'reason': 'needs_list_data'},
            'decay_velocity': {'locked': True, 'reason': 'needs_list_data'},
        },
        'recommendations': recommendations,
        'segments': {'total': 0, 'active': 0, 'warm': 0, 'at_risk': 0, 'dormant': 0},
        'trajectory_direction': 'unknown',
        'mpp_accuracy': 'none',
        'tier': 'anon',
    }


def _letter_grade(score):
    """Map a 0-100 score to an A-F letter grade."""
    if score >= 90:
        return 'A'
    if score >= 80:
        return 'B'
    if score >= 65:
        return 'C'
    if score >= 50:
        return 'D'
    return 'F'


# ── Public share token (schema-less HMAC) ──────────────
#
# Lets authenticated users share a read-only view of their Signal Score via
# a URL like /signal-score/public/<token>. The token is a tamper-proof
# encoding of the signal_scores row id, signed with the app SECRET_KEY so
# visitors can't enumerate other users' reports by incrementing an integer.

import base64
import hashlib
import hmac


def _share_secret():
    """Derive a stable secret for share-token HMAC."""
    import os
    return os.environ.get('SECRET_KEY') or 'inbxr-fallback-share-secret'


def make_share_token(row_id):
    """Generate a tamper-proof share token for a signal_scores row."""
    msg = str(row_id).encode()
    sig = hmac.new(_share_secret().encode(), msg, hashlib.sha256).hexdigest()[:12]
    raw = f"{row_id}.{sig}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def parse_share_token(token):
    """Verify a share token and return the signal_scores row id, or None."""
    try:
        padded = token + '=' * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        row_id_str, sig = decoded.split('.', 1)
        expected_sig = hmac.new(
            _share_secret().encode(), row_id_str.encode(), hashlib.sha256
        ).hexdigest()[:12]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return int(row_id_str)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


def get_signal_score_by_id(row_id):
    """Fetch a signal_scores row by its primary key (used by public share view)."""
    return fetchone(
        "SELECT * FROM signal_scores WHERE id = ?",
        (row_id,),
    )
