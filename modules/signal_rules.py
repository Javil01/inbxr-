"""
InbXr Signal Intelligence — Signal Rules Engine

Evaluates and executes user-defined automation rules against contact data
and signal scores. All rules default to dry-run mode (action_dry_run=1)
and must be explicitly flipped to live by the user.

Phase 4 scope: LOCAL EXECUTION ONLY.
- Local actions: notify (alert), tag (update contact_segments), move_segment, suppress
- ESP writeback (sync to Mailchimp/ActiveCampaign/etc.) is deferred to later phase

Reference: SIGNAL_SPEC.md Phase 4 + signal_copy.PRE_BUILT_RULE_TEMPLATES.
"""

import json
import logging
from datetime import datetime

from modules.database import execute, fetchone, fetchall
from modules.signal_copy import PRE_BUILT_RULE_TEMPLATES
from modules.signal_score import _utcnow

logger = logging.getLogger("inbxr.signal_rules")


# ── Operator evaluators ────────────────────────────────

def _check_condition(value, operator, threshold):
    """Return True if `value` satisfies `operator threshold`."""
    try:
        v = float(value) if value is not None else 0
        t = float(threshold)
    except (ValueError, TypeError):
        return False

    if operator == 'greater_than':
        return v > t
    elif operator == 'less_than':
        return v < t
    elif operator == 'equals':
        return v == t
    elif operator == 'greater_than_or_equal':
        return v >= t
    elif operator == 'less_than_or_equal':
        return v <= t
    return False


# ── Rule evaluation ────────────────────────────────────

def evaluate_rule_against_contacts(rule, contacts, signal_result):
    """
    Return the list of contacts that match a rule's condition.
    Does NOT execute any action — just evaluation.

    Used by both dry-run preview and live execution.
    """
    signal = rule['condition_signal']
    op = rule.get('condition_operator', 'greater_than')
    value = rule['condition_value']

    matched = []

    # Signal-score-wide conditions (not per-contact)
    scores = signal_result.get('scores', {}) if signal_result else {}
    total_score = signal_result.get('total_signal_score', 0) if signal_result else 0

    signal_score_map = {
        'bounce_exposure_score': scores.get('bounce_exposure', 0),
        'engagement_trajectory_score': scores.get('engagement_trajectory', 0),
        'acquisition_quality_score': scores.get('acquisition_quality', 0),
        'domain_reputation_score': scores.get('domain_reputation', 0),
        'dormancy_risk_score': scores.get('dormancy_risk', 0),
        'authentication_standing_score': scores.get('authentication_standing', 0),
        'decay_velocity_score': scores.get('decay_velocity', 0),
        'total_signal_score': total_score,
    }

    # If the condition is on a signal-wide score, check once and either
    # match all contacts or none.
    if signal in signal_score_map:
        if _check_condition(signal_score_map[signal], op, value):
            return list(contacts)
        return []

    # Per-contact conditions
    now = _utcnow()
    for c in contacts:
        matches = False

        if signal == 'days_since_engagement':
            # Find the most recent engagement date
            from modules.signal_score import _parse_date
            dates = [
                _parse_date(c.get('last_open_date')),
                _parse_date(c.get('last_click_date')),
                _parse_date(c.get('last_reply_date')),
            ]
            latest = max([d for d in dates if d], default=None)
            days = 999 if not latest else (now - latest).days
            matches = _check_condition(days, op, value)

        elif signal == 'is_hard_bounce':
            matches = _check_condition(1 if c.get('is_hard_bounce') else 0, op, value)

        elif signal == 'is_catch_all':
            matches = _check_condition(1 if c.get('is_catch_all') else 0, op, value)

        elif signal == 'is_role_address':
            matches = _check_condition(1 if c.get('is_role_address') else 0, op, value)

        elif signal == 'is_disposable':
            matches = _check_condition(1 if c.get('is_disposable') else 0, op, value)

        elif signal == 'acquisition_quality':
            # Special: check acquisition_quality_flag field
            flag = c.get('acquisition_quality_flag', 'unknown')
            # Map: organic=2, mixed=1, cold=0, unknown=None
            flag_val = {'organic': 2, 'mixed': 1, 'cold': 0}.get(flag, -1)
            matches = _check_condition(flag_val, op, value)

        if matches:
            matched.append(c)

    return matched


def preview_signal_rule(user_id, rule_id, contacts, signal_result):
    """
    Dry-run: show what a rule WOULD do without executing it.
    Returns: {'affected_count', 'total_list_size', 'percentage_affected', 'sample_emails'}
    """
    rule = fetchone(
        "SELECT * FROM signal_rules WHERE id = ? AND user_id = ?",
        (rule_id, user_id),
    )
    if not rule:
        return {'error': 'rule_not_found'}

    affected = evaluate_rule_against_contacts(rule, contacts, signal_result)
    total = len(contacts)

    # Store preview count for display in UI
    execute(
        "UPDATE signal_rules SET last_preview_count = ? WHERE id = ?",
        (len(affected), rule_id),
    )

    return {
        'affected_count': len(affected),
        'total_list_size': total,
        'percentage_affected': round((len(affected) / total * 100) if total else 0, 2),
        'sample_emails': [c.get('email') for c in affected[:10]],
        'rule_name': rule['rule_name'],
        'action_type': rule['action_type'],
        'action_target': rule.get('action_target'),
    }


# ── Rule execution (local only — Phase 4 scope) ───────

def execute_signal_rules(user_id, esp_integration_id, signal_result, contacts):
    """
    Evaluate and execute all active NON-dry-run rules for a user.
    Called by the Signal Watch scheduler job after each Signal Score calculation.

    Actions supported (Phase 4):
    - notify: create an alert
    - tag: update contact_segments tag/segment
    - move_segment: reclassify contact segment
    - suppress: mark contact as suppressed (LOCAL ONLY — no ESP writeback in Phase 4)

    ESP writeback (action_esp_sync=1) is deferred to a later phase.
    For now, rules with action_esp_sync=1 still execute locally and log a
    "esp_sync_status='skipped'" record so users can see what WOULD have happened.
    """
    active_rules = fetchall(
        """SELECT * FROM signal_rules
           WHERE user_id = ? AND is_active = 1 AND action_dry_run = 0""",
        (user_id,),
    )

    if not active_rules:
        return {'rules_evaluated': 0, 'rules_fired': 0}

    summary = {
        'rules_evaluated': 0,
        'rules_fired': 0,
        'contacts_affected_total': 0,
        'errors': [],
    }

    for rule in active_rules:
        summary['rules_evaluated'] += 1

        try:
            affected = evaluate_rule_against_contacts(rule, contacts, signal_result)
            if not affected:
                continue

            # Execute the action
            action_type = rule['action_type']
            action_target = rule.get('action_target')
            action_esp_sync = bool(rule.get('action_esp_sync'))

            if action_type == 'notify':
                _action_notify(user_id, rule, affected, signal_result)
            elif action_type == 'tag':
                _action_tag(user_id, esp_integration_id, rule, affected)
            elif action_type == 'move_segment':
                _action_move_segment(user_id, esp_integration_id, rule, affected)
            elif action_type == 'suppress':
                _action_suppress(user_id, esp_integration_id, rule, affected)
            else:
                logger.warning(f'Unknown action_type: {action_type} on rule {rule["id"]}')
                continue

            # Update rule stats
            execute(
                """UPDATE signal_rules SET
                    times_fired = times_fired + 1,
                    last_fired_at = datetime('now')
                   WHERE id = ?""",
                (rule['id'],),
            )

            # Log execution
            sync_status = 'skipped' if action_esp_sync else 'success'
            execute(
                """INSERT INTO signal_rule_log (
                    rule_id, user_id, was_dry_run, contacts_affected,
                    action_taken, esp_sync_status
                ) VALUES (?, ?, 0, ?, ?, ?)""",
                (
                    rule['id'],
                    user_id,
                    len(affected),
                    f'{action_type}: {action_target or ""}',
                    sync_status,
                ),
            )

            summary['rules_fired'] += 1
            summary['contacts_affected_total'] += len(affected)

        except Exception as e:
            logger.exception(f'Signal Rule {rule["id"]} execution error')
            summary['errors'].append(f'rule {rule["id"]}: {type(e).__name__}')

    return summary


# ── Action handlers (local-only) ───────────────────────

def _action_notify(user_id, rule, affected, signal_result):
    """Create an alert in the existing alerts table."""
    from modules.signal_copy import SIGNAL_DIMENSION_COPY

    signal_dim = rule['condition_signal'].replace('_score', '')
    dim_info = SIGNAL_DIMENSION_COPY.get(signal_dim, {})
    dim_name = dim_info.get('name', signal_dim)

    title = f'Signal Rule fired: {rule["rule_name"]}'
    message = (
        f'{len(affected)} contact{"s" if len(affected) != 1 else ""} matched your rule condition.\n'
        f'Signal: {dim_name}\n'
        f'Action: {rule["action_type"]}\n'
    )
    if rule.get('action_target') == 'send_block':
        message += '\nRecommended: do not send to your full list until this is resolved.'

    execute(
        """INSERT INTO alerts (
            user_id, alert_type, title, message, is_read,
            signal_dimension, recommended_action, action_url, severity
        ) VALUES (?, 'signal_rule', ?, ?, 0, ?, ?, ?, ?)""",
        (
            user_id,
            title,
            message,
            signal_dim,
            'Review affected contacts in Signal Map',
            '/signal-map',
            'warning',
        ),
    )


def _find_contact_row(user_id, esp_integration_id, email):
    """Find a contact_segments row, handling NULL esp_integration_id correctly."""
    if esp_integration_id is None:
        return fetchone(
            """SELECT id FROM contact_segments
               WHERE user_id = ? AND esp_integration_id IS NULL AND email = ?""",
            (user_id, email),
        )
    return fetchone(
        """SELECT id FROM contact_segments
           WHERE user_id = ? AND esp_integration_id = ? AND email = ?""",
        (user_id, esp_integration_id, email),
    )


def _action_tag(user_id, esp_integration_id, rule, affected):
    """Tag affected contacts locally (contact_segments.segment field)."""
    target = rule.get('action_target', 'tagged')
    for c in affected:
        email = c.get('email')
        if not email:
            continue
        existing = _find_contact_row(user_id, esp_integration_id, email)
        if existing:
            execute(
                """UPDATE contact_segments SET
                    acquisition_quality_flag = ?,
                    updated_at = datetime('now')
                   WHERE id = ?""",
                (target if target in ('organic', 'cold', 'unknown') else 'unknown', existing['id']),
            )


def _action_move_segment(user_id, esp_integration_id, rule, affected):
    """Reclassify contact segments."""
    target_segment = rule.get('action_target', 'at_risk')
    if target_segment not in ('active', 'warm', 'at_risk', 'dormant'):
        target_segment = 'at_risk'

    for c in affected:
        email = c.get('email')
        if not email:
            continue
        existing = _find_contact_row(user_id, esp_integration_id, email)
        if existing:
            execute(
                """UPDATE contact_segments SET
                    segment = ?,
                    updated_at = datetime('now')
                   WHERE id = ?""",
                (target_segment, existing['id']),
            )


def _action_suppress(user_id, esp_integration_id, rule, affected):
    """Mark contacts as suppressed in InbXr's local DB AND push the
    suppression to the connected ESP when the rule is live.

    Safety rules:
      1. Local suppression always happens (it's the source of truth
         for the Signal Engine's future scoring).
      2. ESP write-back only fires when rule.action_dry_run == 0 AND
         the rule has an esp_integration_id to push to. Dry-run rules
         never touch the ESP — they only mark local contacts.
      3. Write-back failures do NOT abort the local suppression.
         They are logged to esp_writeback_log for the user to review.
    """
    reason = rule.get('action_target') or 'signal_rule'
    is_live = not rule.get('action_dry_run', 1)
    should_writeback = is_live and esp_integration_id is not None

    for c in affected:
        email = c.get('email')
        if not email:
            continue

        # 1. Local suppression (always)
        existing = _find_contact_row(user_id, esp_integration_id, email)
        if existing:
            execute(
                """UPDATE contact_segments SET
                    is_suppressed = 1,
                    suppressed_at = datetime('now'),
                    suppression_reason = ?,
                    suppression_rule_id = ?,
                    updated_at = datetime('now')
                   WHERE id = ?""",
                (reason, rule['id'], existing['id']),
            )

        # 2. ESP write-back (only when live and integration-linked)
        if should_writeback:
            try:
                from modules.esp_writeback import suppress_contact as _esp_suppress
                ok, msg = _esp_suppress(
                    user_id=user_id,
                    esp_integration_id=esp_integration_id,
                    email=email,
                    reason=reason,
                )
                if not ok:
                    logger.warning(
                        "[SIGNAL_RULES] ESP write-back failed for %s (rule %s): %s",
                        email, rule.get('id'), msg,
                    )
            except Exception:
                logger.exception(
                    "[SIGNAL_RULES] ESP write-back crashed for %s (rule %s)",
                    email, rule.get('id'),
                )


# ── Rule CRUD ──────────────────────────────────────────

def create_rule_from_template(user_id, template_id, esp_integration_id=None):
    """Create a new signal rule from a pre-built template."""
    template = next((t for t in PRE_BUILT_RULE_TEMPLATES if t['template_id'] == template_id), None)
    if not template:
        return {'error': 'template_not_found'}

    execute(
        """INSERT INTO signal_rules (
            user_id, esp_integration_id, rule_name, is_active, is_template, template_id,
            condition_signal, condition_operator, condition_value, condition_duration_days,
            action_type, action_target, action_esp_sync, action_dry_run
        ) VALUES (?, ?, ?, 1, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            esp_integration_id,
            template['rule_name'],
            template['template_id'],
            template['condition_signal'],
            template['condition_operator'],
            template['condition_value'],
            template.get('condition_duration_days'),
            template['action_type'],
            template.get('action_target'),
            template['action_esp_sync'],
            template['action_dry_run'],  # Always 1 from PRE_BUILT_RULE_TEMPLATES
        ),
    )

    new_rule = fetchone(
        """SELECT * FROM signal_rules
           WHERE user_id = ? AND template_id = ?
           ORDER BY id DESC LIMIT 1""",
        (user_id, template_id),
    )
    return {'rule': new_rule}


def create_custom_rule(user_id, rule_data):
    """Create a custom signal rule from user input."""
    required = ['rule_name', 'condition_signal', 'condition_value', 'action_type']
    for field in required:
        if field not in rule_data:
            return {'error': f'missing_field: {field}'}

    execute(
        """INSERT INTO signal_rules (
            user_id, esp_integration_id, rule_name, is_active, is_template,
            condition_signal, condition_operator, condition_value, condition_duration_days,
            action_type, action_target, action_esp_sync, action_dry_run
        ) VALUES (?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            rule_data.get('esp_integration_id'),
            rule_data['rule_name'],
            rule_data['condition_signal'],
            rule_data.get('condition_operator', 'greater_than'),
            rule_data['condition_value'],
            rule_data.get('condition_duration_days'),
            rule_data['action_type'],
            rule_data.get('action_target'),
            1 if rule_data.get('action_esp_sync') else 0,
            1 if rule_data.get('action_dry_run', True) else 0,  # Default dry-run TRUE
        ),
    )

    return {'ok': True}


def toggle_rule(user_id, rule_id):
    """Enable or disable a rule. Returns new is_active state."""
    rule = fetchone(
        "SELECT is_active FROM signal_rules WHERE id = ? AND user_id = ?",
        (rule_id, user_id),
    )
    if not rule:
        return {'error': 'rule_not_found'}

    new_state = 0 if rule['is_active'] else 1
    execute(
        "UPDATE signal_rules SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
        (new_state, rule_id),
    )
    return {'is_active': new_state}


def flip_dry_run(user_id, rule_id):
    """Flip a rule from dry-run to live (or vice versa). Requires explicit user action."""
    rule = fetchone(
        "SELECT action_dry_run FROM signal_rules WHERE id = ? AND user_id = ?",
        (rule_id, user_id),
    )
    if not rule:
        return {'error': 'rule_not_found'}

    new_state = 0 if rule['action_dry_run'] else 1
    execute(
        "UPDATE signal_rules SET action_dry_run = ?, updated_at = datetime('now') WHERE id = ?",
        (new_state, rule_id),
    )
    return {'action_dry_run': new_state}


def delete_rule(user_id, rule_id):
    """Delete a rule. Cascade deletes its log entries."""
    result = execute(
        "DELETE FROM signal_rules WHERE id = ? AND user_id = ?",
        (rule_id, user_id),
    )
    return {'deleted': result.rowcount if hasattr(result, 'rowcount') else True}


def get_user_rules(user_id):
    """List all rules for a user."""
    return fetchall(
        """SELECT * FROM signal_rules
           WHERE user_id = ?
           ORDER BY is_active DESC, created_at DESC""",
        (user_id,),
    )


def get_rule_log(user_id, limit=50):
    """Get recent rule firing log."""
    return fetchall(
        """SELECT rl.*, sr.rule_name, sr.action_type
           FROM signal_rule_log rl
           JOIN signal_rules sr ON sr.id = rl.rule_id
           WHERE rl.user_id = ?
           ORDER BY rl.fired_at DESC
           LIMIT ?""",
        (user_id, limit),
    )
