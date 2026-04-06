"""
InbXr Signal Intelligence — Per-Contact ESP Sync

Pulls contact-level engagement data from 4 ESPs that support it:
- Mailchimp (complete)
- ActiveCampaign (stub, Phase 2b)
- Mailgun (stub, Phase 2b)
- AWeber (stub, Phase 2b)

Instantly, Smartlead, and GoHighLevel do NOT expose per-contact engagement
and are excluded from this module — users on those ESPs see "aggregate signal
coverage" in the UI and can use the CSV upload path for full signals.

All sync functions write to the contact_segments table via upsert.
Returns stats about the sync (contacts_pulled, contacts_new, contacts_updated,
errors, rate_limit_hits).

Reference: SIGNAL_SPEC.md Phase 2.
"""

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from modules.database import execute, fetchone, fetchall
from modules.signal_score import _utcnow

logger = logging.getLogger("inbxr.esp_contact_sync")


# ── Constants ──────────────────────────────────────────

# Per-ESP rate limits (requests per second)
RATE_LIMITS = {
    'mailchimp': 10,       # Mailchimp allows 10 simultaneous
    'activecampaign': 5,   # ActiveCampaign throttles aggressively
    'mailgun': 20,         # Mailgun is more generous
    'aweber': 3,           # AWeber is slow + OAuth
}

# Pagination sizes per ESP
PAGE_SIZES = {
    'mailchimp': 1000,      # Max for /lists/{id}/members
    'activecampaign': 100,  # Max for /contacts
    'mailgun': 300,         # Max for /events
    'aweber': 100,          # Max for /subscribers
}

# Sync batch size (rows per SQLite transaction)
SQLITE_BATCH_SIZE = 500

# Max contacts per list to sync (safety cap — can be adjusted per user)
MAX_CONTACTS_PER_LIST = 250_000

# Free email domains (for cached detection)
FREE_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com',
    'icloud.com', 'me.com', 'mac.com', 'live.com', 'msn.com', 'protonmail.com',
}

# Role address prefixes (for cached detection)
ROLE_PREFIXES = {
    'admin', 'administrator', 'info', 'contact', 'support', 'help',
    'sales', 'marketing', 'noreply', 'no-reply', 'postmaster', 'webmaster',
    'hostmaster', 'abuse', 'security', 'privacy', 'billing', 'hr',
    'careers', 'jobs', 'press', 'media', 'pr', 'legal', 'feedback',
    'hello', 'hi', 'mail', 'email', 'office', 'team',
}


# ── HTTP helpers ───────────────────────────────────────

def _api_request(url, headers=None, timeout=30, max_retries=2):
    """Make a GET request with retry on rate limit. Returns parsed JSON."""
    headers = headers or {}
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429:
                # Rate limited — exponential backoff
                wait = (attempt + 1) * 5
                logger.warning(f'Rate limited on {url}, waiting {wait}s (attempt {attempt + 1})')
                time.sleep(wait)
                continue
            if e.code in (500, 502, 503, 504):
                wait = (attempt + 1) * 3
                logger.warning(f'Server error {e.code} on {url}, waiting {wait}s')
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError as e:
            last_error = e
            time.sleep((attempt + 1) * 2)
            continue

    if last_error:
        raise last_error
    raise RuntimeError(f"Failed after {max_retries + 1} attempts: {url}")


def _rate_limit_sleep(esp_type):
    """Sleep to respect rate limit for a given ESP."""
    rps = RATE_LIMITS.get(esp_type, 5)
    time.sleep(1.0 / rps)


# ── Contact classification helpers ─────────────────────

def _classify_email_flags(email):
    """Quick heuristic flags for Bounce Exposure signal (without full verification)."""
    email = (email or '').lower().strip()
    local, _, domain = email.partition('@')

    is_role = any(local == prefix or local.startswith(prefix + '.') or local.startswith(prefix + '-')
                  for prefix in ROLE_PREFIXES)

    return {
        'is_role_address': is_role,
        'is_disposable': False,  # Requires proper disposable-domain list check (deferred)
        'is_catch_all': False,   # Requires MX probe check (deferred)
    }


def _segment_from_engagement(last_open, last_click, last_reply):
    """Classify contact into Active/Warm/At-Risk/Dormant from engagement dates."""
    dates = [d for d in [last_open, last_click, last_reply] if d]
    if not dates:
        return 'dormant', None

    latest = max(dates)
    if isinstance(latest, str):
        try:
            latest = datetime.fromisoformat(latest.replace('Z', '+00:00'))
        except ValueError:
            return 'dormant', None

    now = _utcnow()
    days_since = (now - latest).days

    if days_since <= 30:
        return 'active', days_since
    elif days_since <= 90:
        return 'warm', days_since
    elif days_since <= 180:
        return 'at_risk', days_since
    else:
        return 'dormant', days_since


# ── Contact upsert (batched) ───────────────────────────

def _upsert_contacts_batch(user_id, esp_integration_id, contacts):
    """
    Upsert a batch of contact records into contact_segments.
    Uses INSERT OR REPLACE via the UNIQUE(user_id, esp_integration_id, email) constraint.

    Each contact dict should have at minimum: email.
    Optional fields: last_open_date, last_click_date, last_reply_date,
    acquisition_date, is_hard_bounce, is_catch_all, is_role_address, is_disposable.
    """
    if not contacts:
        return {'new': 0, 'updated': 0}

    new_count = 0
    updated_count = 0

    for c in contacts:
        email = (c.get('email') or '').lower().strip()
        if not email or '@' not in email:
            continue

        segment, days_since = _segment_from_engagement(
            c.get('last_open_date'),
            c.get('last_click_date'),
            c.get('last_reply_date'),
        )

        flags = _classify_email_flags(email)

        # Check if exists — handle NULL esp_integration_id correctly
        if esp_integration_id is None:
            existing = fetchone(
                """SELECT id FROM contact_segments
                   WHERE user_id = ? AND esp_integration_id IS NULL AND email = ?""",
                (user_id, email),
            )
        else:
            existing = fetchone(
                """SELECT id FROM contact_segments
                   WHERE user_id = ? AND esp_integration_id = ? AND email = ?""",
                (user_id, esp_integration_id, email),
            )

        if existing:
            execute(
                """UPDATE contact_segments SET
                    segment = ?,
                    last_open_date = ?,
                    last_click_date = ?,
                    last_reply_date = ?,
                    acquisition_date = ?,
                    is_hard_bounce = ?,
                    is_catch_all = ?,
                    is_role_address = ?,
                    is_disposable = ?,
                    days_since_engagement = ?,
                    updated_at = datetime('now')
                   WHERE id = ?""",
                (
                    segment,
                    _iso(c.get('last_open_date')),
                    _iso(c.get('last_click_date')),
                    _iso(c.get('last_reply_date')),
                    _iso(c.get('acquisition_date')),
                    1 if c.get('is_hard_bounce') else 0,
                    1 if c.get('is_catch_all') or flags['is_catch_all'] else 0,
                    1 if c.get('is_role_address') or flags['is_role_address'] else 0,
                    1 if c.get('is_disposable') or flags['is_disposable'] else 0,
                    days_since,
                    existing['id'],
                ),
            )
            updated_count += 1
        else:
            execute(
                """INSERT INTO contact_segments (
                    user_id, esp_integration_id, email, segment,
                    last_open_date, last_click_date, last_reply_date,
                    acquisition_date, days_since_engagement,
                    is_hard_bounce, is_catch_all, is_role_address, is_disposable
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    esp_integration_id,
                    email,
                    segment,
                    _iso(c.get('last_open_date')),
                    _iso(c.get('last_click_date')),
                    _iso(c.get('last_reply_date')),
                    _iso(c.get('acquisition_date')),
                    days_since,
                    1 if c.get('is_hard_bounce') else 0,
                    1 if c.get('is_catch_all') or flags['is_catch_all'] else 0,
                    1 if c.get('is_role_address') or flags['is_role_address'] else 0,
                    1 if c.get('is_disposable') or flags['is_disposable'] else 0,
                ),
            )
            new_count += 1

    return {'new': new_count, 'updated': updated_count}


def _iso(value):
    """Coerce a date value to ISO string for SQLite storage, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# ── Mailchimp per-contact sync ─────────────────────────

def sync_mailchimp_contacts(
    integration_id,
    api_key,
    list_id=None,
    max_contacts=None,
    since_last_changed=None,
):
    """
    Pull per-contact engagement data from Mailchimp.

    Fetches /lists/{id}/members paginated at 1000/page.
    For each contact, extracts:
    - email, timestamp_signup, timestamp_opt, last_changed
    - stats.avg_open_rate, stats.avg_click_rate
    - member_activity (via separate call if needed — expensive)

    Returns a sync stats dict.

    If list_id is not provided, fetches the first available list for the account.
    """
    from blueprints.integration_routes import _decrypt_value

    # Get integration record for user_id
    integration = fetchone(
        "SELECT id, user_id FROM esp_integrations WHERE id = ? AND provider = 'mailchimp'",
        (integration_id,),
    )
    if not integration:
        return {'error': 'integration_not_found'}

    user_id = integration['user_id']

    # Mailchimp API key format: 'xxxxxxxx-usXX'
    if '-' not in api_key:
        return {'error': 'invalid_api_key_format'}
    dc = api_key.split('-')[-1]

    creds = base64.b64encode(f"anystring:{api_key}".encode()).decode()
    headers = {'Authorization': f'Basic {creds}'}
    base = f'https://{dc}.api.mailchimp.com/3.0'

    stats = {
        'contacts_pulled': 0,
        'contacts_new': 0,
        'contacts_updated': 0,
        'lists_processed': 0,
        'errors': [],
        'rate_limit_hits': 0,
        'started_at': _utcnow().isoformat(),
    }

    try:
        # Step 1: Get lists to sync
        if list_id:
            lists_to_sync = [{'id': list_id}]
        else:
            lists_resp = _api_request(f'{base}/lists?count=20&fields=lists.id,lists.name,lists.stats.member_count', headers=headers)
            lists_to_sync = lists_resp.get('lists', [])

        if not lists_to_sync:
            return {**stats, 'error': 'no_lists_found'}

        # Step 2: For each list, paginate through members
        for lst in lists_to_sync:
            lid = lst['id']
            logger.info(f'Mailchimp sync: starting list {lid} for integration {integration_id}')

            offset = 0
            page_size = PAGE_SIZES['mailchimp']
            list_total = 0

            while True:
                # Rate limit respect
                _rate_limit_sleep('mailchimp')

                # Build URL with since_last_changed if provided
                params = {
                    'count': page_size,
                    'offset': offset,
                    'fields': 'members.email_address,members.status,members.timestamp_signup,members.timestamp_opt,members.last_changed,members.stats,members.member_rating,total_items',
                }
                if since_last_changed:
                    params['since_last_changed'] = since_last_changed.isoformat() if isinstance(since_last_changed, datetime) else since_last_changed

                qs = urllib.parse.urlencode(params)
                url = f'{base}/lists/{lid}/members?{qs}'

                try:
                    page = _api_request(url, headers=headers)
                except urllib.error.HTTPError as e:
                    if e.code == 429:
                        stats['rate_limit_hits'] += 1
                    stats['errors'].append(f'list {lid} offset {offset}: HTTP {e.code}')
                    break
                except Exception as e:
                    stats['errors'].append(f'list {lid} offset {offset}: {type(e).__name__}')
                    break

                members = page.get('members', [])
                total_items = page.get('total_items', 0)

                if not members:
                    break

                # Convert Mailchimp records to signal engine contact format.
                # NOTE: last_open_date / last_click_date are NOT populated here —
                # they get filled in by sync_mailchimp_campaign_activity() in Step 3
                # (the activity feed gives real per-open / per-click timestamps).
                batch = []
                for m in members:
                    email = m.get('email_address', '')
                    status = m.get('status', '')

                    batch.append({
                        'email': email,
                        'last_open_date': None,    # Filled by activity sync
                        'last_click_date': None,   # Filled by activity sync
                        'last_reply_date': None,
                        'acquisition_date': m.get('timestamp_signup') or m.get('timestamp_opt'),
                        'is_hard_bounce': status == 'cleaned',
                        # Mailchimp doesn't tell us catch-all/role/disposable — defer to verifier
                    })

                # Batch upsert
                batch_stats = _upsert_contacts_batch(user_id, integration_id, batch)
                stats['contacts_new'] += batch_stats['new']
                stats['contacts_updated'] += batch_stats['updated']
                stats['contacts_pulled'] += len(batch)
                list_total += len(batch)

                # Safety cap
                if list_total >= (max_contacts or MAX_CONTACTS_PER_LIST):
                    logger.warning(f'Mailchimp sync: hit {list_total} cap for list {lid}')
                    break

                # Pagination — move to next page
                if len(members) < page_size:
                    break
                offset += page_size

                # Safety: stop if we've fetched everything the API reports
                if total_items and offset >= total_items:
                    break

            stats['lists_processed'] += 1
            logger.info(f'Mailchimp sync: finished list {lid}, pulled {list_total} members')

        # Step 3: Pull per-open/per-click activity for recent campaigns.
        # This is what populates last_open_date / last_click_date on contact_segments
        # and unlocks the timing-based MPP detection heuristic.
        try:
            campaigns_resp = _api_request(
                f'{base}/campaigns?status=sent&sort_field=send_time&sort_dir=DESC&count=10'
                '&fields=campaigns.id,campaigns.send_time,campaigns.settings.title,campaigns.recipients.list_id',
                headers=headers,
            )
            recent_campaigns = campaigns_resp.get('campaigns', [])
            stats['campaigns_processed'] = 0
            stats['activity_events_processed'] = 0
            stats['activity_contacts_updated'] = 0

            # Limit to last 5 campaigns to control API call volume
            for camp in recent_campaigns[:5]:
                camp_id = camp.get('id')
                if not camp_id:
                    continue
                _rate_limit_sleep('mailchimp')
                act_stats = sync_mailchimp_campaign_activity(
                    integration_id=integration_id,
                    api_key=api_key,
                    campaign_id=camp_id,
                    max_events=5_000,
                )
                if act_stats and not act_stats.get('error'):
                    stats['activity_events_processed'] += act_stats.get('events_processed', 0)
                    stats['activity_contacts_updated'] += act_stats.get('contacts_updated', 0)
                    stats['campaigns_processed'] += 1
                else:
                    stats['errors'].append(f'activity {camp_id}: {act_stats.get("error", "unknown")}')

            logger.info(
                f'Mailchimp activity sync: processed {stats["campaigns_processed"]} campaigns, '
                f'{stats["activity_events_processed"]} events, '
                f'updated {stats["activity_contacts_updated"]} contacts'
            )
        except Exception as e:
            logger.warning(f'Mailchimp campaign activity sync failed: {e}')
            stats['errors'].append(f'campaign_activity: {type(e).__name__}: {e}')

        # Step 4: Update last_synced_at on the integration
        execute(
            "UPDATE esp_integrations SET last_synced_at = datetime('now') WHERE id = ?",
            (integration_id,),
        )

        stats['finished_at'] = _utcnow().isoformat()
        return stats

    except Exception as e:
        logger.exception(f'Mailchimp contact sync failed for integration {integration_id}')
        stats['errors'].append(f'fatal: {type(e).__name__}: {e}')
        return stats


def sync_mailchimp_campaign_activity(
    integration_id,
    api_key,
    campaign_id,
    max_events=10_000,
):
    """
    Pull per-contact engagement events from a specific Mailchimp campaign.
    Uses /reports/{campaign_id}/email-activity.

    This is the source of last_open_date / last_click_date per contact.

    MPP detection: Mailchimp doesn't expose User-Agent, so we use the timing
    heuristic — opens within MPP_TIMING_THRESHOLD_SECONDS of campaign send_time
    are flagged as likely-MPP machine opens. The contact's likely_mpp_opener
    flag is set if ALL their opens for this campaign fall in the suspect window.

    Expensive — only run on recent campaigns (last 30 days) to populate
    engagement timelines.
    """
    if '-' not in api_key:
        return {'error': 'invalid_api_key_format'}

    dc = api_key.split('-')[-1]
    creds = base64.b64encode(f"anystring:{api_key}".encode()).decode()
    headers = {'Authorization': f'Basic {creds}'}
    base = f'https://{dc}.api.mailchimp.com/3.0'

    integration = fetchone(
        "SELECT user_id FROM esp_integrations WHERE id = ?",
        (integration_id,),
    )
    if not integration:
        return {'error': 'integration_not_found'}
    user_id = integration['user_id']

    # MPP timing threshold (seconds) — opens this fast after send are likely machine
    from modules.signal_score import MPP_TIMING_THRESHOLD_SECONDS

    stats = {
        'events_processed': 0,
        'contacts_updated': 0,
        'mpp_flagged': 0,
        'errors': [],
    }

    # Step A: get the campaign's send_time so we can do timing-based MPP detection
    campaign_send_time = None
    try:
        camp = _api_request(
            f'{base}/campaigns/{campaign_id}?fields=send_time',
            headers=headers,
        )
        send_time_str = camp.get('send_time')
        if send_time_str:
            try:
                # Mailchimp returns ISO 8601 with 'Z' suffix
                campaign_send_time = datetime.fromisoformat(send_time_str.replace('Z', '+00:00'))
                # Strip tzinfo to compare with naive timestamps
                campaign_send_time = campaign_send_time.replace(tzinfo=None)
            except (ValueError, TypeError):
                pass
    except Exception as e:
        logger.debug(f'Could not fetch send_time for campaign {campaign_id}: {e}')

    try:
        offset = 0
        page_size = 1000

        while offset < max_events:
            _rate_limit_sleep('mailchimp')

            url = f'{base}/reports/{campaign_id}/email-activity?count={page_size}&offset={offset}'
            try:
                page = _api_request(url, headers=headers)
            except urllib.error.HTTPError as e:
                stats['errors'].append(f'offset {offset}: HTTP {e.code}')
                break

            emails = page.get('emails', [])
            if not emails:
                break

            # Each email has an activity list with timestamps
            for entry in emails:
                email = entry.get('email_address', '').lower()
                if not email:
                    continue

                activity = entry.get('activity', [])
                last_open = None
                last_click = None
                total_opens = 0
                machine_opens = 0

                for act in activity:
                    act_type = act.get('action')
                    act_ts = act.get('timestamp')
                    if not act_ts:
                        continue

                    if act_type == 'open':
                        total_opens += 1
                        # Timing-based MPP detection
                        if campaign_send_time:
                            try:
                                open_dt = datetime.fromisoformat(
                                    act_ts.replace('Z', '+00:00')
                                ).replace(tzinfo=None)
                                delta = (open_dt - campaign_send_time).total_seconds()
                                if 0 <= delta <= MPP_TIMING_THRESHOLD_SECONDS:
                                    machine_opens += 1
                            except (ValueError, TypeError):
                                pass

                        if not last_open or act_ts > last_open:
                            last_open = act_ts
                    elif act_type == 'click':
                        if not last_click or act_ts > last_click:
                            last_click = act_ts

                # Flag as likely MPP if MAJORITY of opens were within timing window
                # (some real users do open within seconds, but if 100% of opens were
                # machine-fast, it's almost certainly MPP)
                is_mpp = (total_opens > 0 and machine_opens / total_opens >= 0.5)

                # Update existing contact segment if present
                existing = fetchone(
                    """SELECT id, last_open_date, last_click_date, likely_mpp_opener
                       FROM contact_segments
                       WHERE user_id = ? AND esp_integration_id = ? AND email = ?""",
                    (user_id, integration_id, email),
                )

                if existing:
                    # Merge — keep the most recent across all campaigns
                    new_open = last_open or existing['last_open_date']
                    new_click = last_click or existing['last_click_date']

                    if last_open and (not existing['last_open_date'] or last_open > existing['last_open_date']):
                        new_open = last_open
                    if last_click and (not existing['last_click_date'] or last_click > existing['last_click_date']):
                        new_click = last_click

                    # Sticky MPP flag: once flagged, stays flagged (it's a contact attribute)
                    new_mpp = 1 if (is_mpp or existing.get('likely_mpp_opener')) else 0

                    segment, days_since = _segment_from_engagement(new_open, new_click, None)

                    execute(
                        """UPDATE contact_segments SET
                            last_open_date = ?,
                            last_click_date = ?,
                            likely_mpp_opener = ?,
                            mpp_detection_method = ?,
                            segment = ?,
                            days_since_engagement = ?,
                            updated_at = datetime('now')
                           WHERE id = ?""",
                        (
                            new_open, new_click, new_mpp,
                            'mailchimp_timing' if is_mpp else (existing.get('mpp_detection_method') or None),
                            segment, days_since, existing['id'],
                        ),
                    )
                    stats['contacts_updated'] += 1
                    if is_mpp and not existing.get('likely_mpp_opener'):
                        stats['mpp_flagged'] += 1

                stats['events_processed'] += 1

            offset += page_size
            if len(emails) < page_size:
                break

        return stats

    except Exception as e:
        logger.exception(f'Mailchimp activity sync failed for campaign {campaign_id}')
        stats['errors'].append(f'fatal: {type(e).__name__}: {e}')
        return stats


# ── ActiveCampaign per-contact sync (STUB — Phase 2b) ──

def sync_activecampaign_contacts(
    integration_id,
    api_key,
    server_prefix,
    max_contacts=None,
    since=None,
):
    """
    Pull per-contact data from ActiveCampaign.

    Fetches /api/3/contacts paginated at 100/page (AC max).
    For each contact, extracts:
    - email, cdate (acquisition_date), udate, status
    - bounced_hard / bounced_soft / bounced_date

    Engagement timestamps (last_open / last_click) are NOT pulled in this pass.
    AC's engagement data lives behind /contactActivity which is per-contact and
    expensive. A future pass can populate it via campaignEvents joins. For now,
    Acquisition Quality + Bounce Exposure + Domain Reputation get real data;
    Engagement Trajectory falls back on aggregate stats.

    Returns a sync stats dict.
    """
    # Get integration record for user_id
    integration = fetchone(
        "SELECT id, user_id FROM esp_integrations WHERE id = ? AND provider = 'activecampaign'",
        (integration_id,),
    )
    if not integration:
        return {'error': 'integration_not_found'}

    user_id = integration['user_id']

    # Normalize server URL: accepts "yourname.api-us1.com" or full https://...
    base = (server_prefix or '').strip().rstrip('/')
    if not base:
        return {'error': 'missing_server_prefix'}
    if not base.startswith('http'):
        base = f'https://{base}'
    api_root = f'{base}/api/3'

    headers = {'Api-Token': api_key, 'Accept': 'application/json'}

    stats = {
        'contacts_pulled': 0,
        'contacts_new': 0,
        'contacts_updated': 0,
        'errors': [],
        'rate_limit_hits': 0,
        'started_at': _utcnow().isoformat(),
    }

    try:
        offset = 0
        page_size = PAGE_SIZES.get('activecampaign', 100)
        cap = max_contacts or MAX_CONTACTS_PER_LIST

        while stats['contacts_pulled'] < cap:
            _rate_limit_sleep('activecampaign')

            # AC paginates with limit/offset; orders[cdate]=DESC gives newest first
            params = {
                'limit': page_size,
                'offset': offset,
                'orders[cdate]': 'DESC',
            }
            if since:
                # AC supports filters[updated_after] (ISO 8601)
                if isinstance(since, datetime):
                    params['filters[updated_after]'] = since.isoformat()
                else:
                    params['filters[updated_after]'] = since

            qs = urllib.parse.urlencode(params)
            url = f'{api_root}/contacts?{qs}'

            try:
                page = _api_request(url, headers=headers)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    stats['rate_limit_hits'] += 1
                stats['errors'].append(f'offset {offset}: HTTP {e.code}')
                break
            except Exception as e:
                stats['errors'].append(f'offset {offset}: {type(e).__name__}')
                break

            contacts = page.get('contacts', [])
            if not contacts:
                break

            batch = []
            for c in contacts:
                email = (c.get('email') or '').lower().strip()
                if not email:
                    continue

                # AC bounce flags are strings: "0" or "1"
                bounced_hard = str(c.get('bounced_hard', '0')) == '1'
                bounced_soft = str(c.get('bounced_soft', '0')) == '1'

                batch.append({
                    'email': email,
                    'last_open_date': None,    # Deferred — needs campaignEvents join
                    'last_click_date': None,   # Deferred
                    'last_reply_date': None,
                    'acquisition_date': c.get('cdate'),
                    'is_hard_bounce': bounced_hard,
                    # AC doesn't directly tell us catch-all/role/disposable
                })

            batch_stats = _upsert_contacts_batch(user_id, integration_id, batch)
            stats['contacts_new'] += batch_stats['new']
            stats['contacts_updated'] += batch_stats['updated']
            stats['contacts_pulled'] += len(batch)

            # Pagination — stop if last page or hit cap
            if len(contacts) < page_size:
                break
            offset += page_size

        # Update last_synced_at on the integration
        execute(
            "UPDATE esp_integrations SET last_synced_at = datetime('now') WHERE id = ?",
            (integration_id,),
        )

        stats['finished_at'] = _utcnow().isoformat()
        logger.info(
            f'AC sync: integration {integration_id} pulled {stats["contacts_pulled"]} contacts '
            f'({stats["contacts_new"]} new, {stats["contacts_updated"]} updated)'
        )
        return stats

    except Exception as e:
        logger.exception(f'AC contact sync failed for integration {integration_id}')
        stats['errors'].append(f'fatal: {type(e).__name__}: {e}')
        return stats


# ── Mailgun per-contact sync (STUB — Phase 2b) ─────────

def sync_mailgun_events(integration_id, api_key, domain, days_back=3, max_events=10_000):
    """
    Pull engagement events from Mailgun.

    Mailgun is the high-accuracy MPP detection path: each event includes
    `client-info.user-agent` and `ip`, which detect_mpp_open() uses to flag
    Apple Mail Privacy Protection opens with confidence='high'.

    Pulls events of type: opened, clicked, failed (hard bounces),
    delivered (used to seed acquisition_date for new contacts).

    Mailgun events API:
    - GET /v3/{domain}/events?begin=...&end=...&event=opened
    - Pagination via `paging.next` URL (cursor-based, NOT offset-based)
    - Free plan retention is 3 days, paid is longer

    Returns a sync stats dict.
    """
    integration = fetchone(
        "SELECT id, user_id FROM esp_integrations WHERE id = ? AND provider = 'mailgun'",
        (integration_id,),
    )
    if not integration:
        return {'error': 'integration_not_found'}

    user_id = integration['user_id']

    if not domain:
        return {'error': 'missing_domain'}

    creds = base64.b64encode(f'api:{api_key}'.encode()).decode()
    headers = {'Authorization': f'Basic {creds}', 'Accept': 'application/json'}
    base = f'https://api.mailgun.net/v3/{domain}'

    # Time window: last N days (epoch seconds for Mailgun)
    begin_ts = (_utcnow() - timedelta(days=days_back)).timestamp()

    stats = {
        'events_processed': 0,
        'contacts_new': 0,
        'contacts_updated': 0,
        'mpp_flagged_high': 0,
        'mpp_flagged_low': 0,
        'opens_seen': 0,
        'clicks_seen': 0,
        'bounces_seen': 0,
        'errors': [],
        'started_at': _utcnow().isoformat(),
    }

    # Lazy-import to avoid circular import
    from modules.signal_score import detect_mpp_open

    # Aggregate events into per-contact records before upserting
    # Key: email, Value: dict of accumulated fields
    contact_buffer = {}

    def _record_event(email, event_type, timestamp_iso, event_payload):
        rec = contact_buffer.setdefault(email, {
            'email': email,
            'last_open_date': None,
            'last_click_date': None,
            'last_reply_date': None,
            'acquisition_date': None,
            'is_hard_bounce': False,
            'mpp_flag': None,        # None | 'high' | 'low'
        })
        if event_type == 'opened':
            stats['opens_seen'] += 1
            if not rec['last_open_date'] or timestamp_iso > rec['last_open_date']:
                rec['last_open_date'] = timestamp_iso
            # MPP detection — high accuracy via Mailgun event
            is_mpp, confidence = detect_mpp_open(
                {'email': email}, event=event_payload, esp_type='mailgun',
            )
            if is_mpp:
                if confidence == 'high':
                    rec['mpp_flag'] = 'high'
                elif rec['mpp_flag'] is None:
                    rec['mpp_flag'] = 'low'
        elif event_type == 'clicked':
            stats['clicks_seen'] += 1
            if not rec['last_click_date'] or timestamp_iso > rec['last_click_date']:
                rec['last_click_date'] = timestamp_iso
        elif event_type == 'failed':
            stats['bounces_seen'] += 1
            severity = (event_payload.get('severity') or '').lower()
            if severity == 'permanent':
                rec['is_hard_bounce'] = True
        elif event_type == 'delivered':
            # Use earliest delivered as a proxy for acquisition_date if we don't
            # already have one (Mailgun doesn't expose subscription date directly)
            if not rec['acquisition_date'] or timestamp_iso < rec['acquisition_date']:
                rec['acquisition_date'] = timestamp_iso

    try:
        # Fetch each event type. Mailgun's events endpoint is event-typed —
        # one query per event filter.
        event_types = ['opened', 'clicked', 'failed', 'delivered']

        for ev_type in event_types:
            if stats['events_processed'] >= max_events:
                break

            # Initial URL — use Mailgun's "begin" + ascending order
            params = {
                'begin': str(int(begin_ts)),
                'ascending': 'yes',
                'limit': 300,
                'event': ev_type,
            }
            qs = urllib.parse.urlencode(params)
            next_url = f'{base}/events?{qs}'
            page_count = 0

            while next_url and stats['events_processed'] < max_events:
                _rate_limit_sleep('mailgun')

                try:
                    page = _api_request(next_url, headers=headers)
                except urllib.error.HTTPError as e:
                    stats['errors'].append(f'{ev_type} page {page_count}: HTTP {e.code}')
                    break
                except Exception as e:
                    stats['errors'].append(f'{ev_type} page {page_count}: {type(e).__name__}')
                    break

                items = page.get('items', [])
                if not items:
                    break

                for ev in items:
                    # Mailgun event shape varies a bit by event type but
                    # `recipient` + `timestamp` are reliable
                    recipient = (ev.get('recipient') or '').lower().strip()
                    if not recipient or '@' not in recipient:
                        continue

                    ts = ev.get('timestamp')  # epoch seconds (float)
                    try:
                        ts_iso = (
                            datetime.fromtimestamp(float(ts), tz=timezone.utc)
                            .replace(tzinfo=None)
                            .isoformat()
                        ) if ts else None
                    except (ValueError, TypeError):
                        ts_iso = None
                    if not ts_iso:
                        continue

                    # Mailgun annotates the event with its own send timestamp;
                    # for MPP timing detection we want delivered_time vs open_time,
                    # but Mailgun doesn't surface delivered_time on the open event
                    # directly. The User-Agent + IP path doesn't need it anyway.
                    _record_event(recipient, ev_type, ts_iso, ev)
                    stats['events_processed'] += 1

                # Mailgun cursor pagination
                paging = page.get('paging', {}) or {}
                next_url = paging.get('next')
                # Mailgun returns 'next' even when empty — break if last page returned no items
                if len(items) < 300:
                    break
                page_count += 1
                if page_count > 50:  # safety
                    break

        # Flush buffer into contact_segments
        if contact_buffer:
            for email, rec in contact_buffer.items():
                # Use _upsert_contacts_batch for the standard fields
                batch_stats = _upsert_contacts_batch(
                    user_id, integration_id,
                    [{
                        'email': rec['email'],
                        'last_open_date': rec['last_open_date'],
                        'last_click_date': rec['last_click_date'],
                        'last_reply_date': None,
                        'acquisition_date': rec['acquisition_date'],
                        'is_hard_bounce': rec['is_hard_bounce'],
                    }],
                )
                stats['contacts_new'] += batch_stats['new']
                stats['contacts_updated'] += batch_stats['updated']

                # Then layer the MPP flag (with sticky-merge against existing)
                if rec['mpp_flag']:
                    existing = fetchone(
                        """SELECT id, likely_mpp_opener, mpp_detection_method
                           FROM contact_segments
                           WHERE user_id = ? AND esp_integration_id = ? AND email = ?""",
                        (user_id, integration_id, email),
                    )
                    if existing:
                        # 'high' always wins; otherwise stay sticky
                        new_method = (
                            'mailgun_useragent_ip'
                            if rec['mpp_flag'] == 'high'
                            else (existing.get('mpp_detection_method') or 'mailgun_domain_fallback')
                        )
                        execute(
                            """UPDATE contact_segments SET
                                likely_mpp_opener = 1,
                                mpp_detection_method = ?
                               WHERE id = ?""",
                            (new_method, existing['id']),
                        )
                        if rec['mpp_flag'] == 'high':
                            stats['mpp_flagged_high'] += 1
                        else:
                            stats['mpp_flagged_low'] += 1

        # Update last_synced_at
        execute(
            "UPDATE esp_integrations SET last_synced_at = datetime('now') WHERE id = ?",
            (integration_id,),
        )

        stats['finished_at'] = _utcnow().isoformat()
        stats['contacts_buffered'] = len(contact_buffer)
        logger.info(
            f'Mailgun sync: integration {integration_id} processed {stats["events_processed"]} events, '
            f'{len(contact_buffer)} contacts, {stats["mpp_flagged_high"]} high-conf MPP'
        )
        return stats

    except Exception as e:
        logger.exception(f'Mailgun events sync failed for integration {integration_id}')
        stats['errors'].append(f'fatal: {type(e).__name__}: {e}')
        return stats


# ── AWeber per-contact sync (STUB — Phase 2b) ──────────

def sync_aweber_subscribers(integration_id, access_token, max_contacts=None):
    """
    Pull per-subscriber data from AWeber.

    AWeber API uses Bearer auth + paginated collections:
    - GET /1.0/accounts                                  → account_id
    - GET /1.0/accounts/{id}/lists                       → list collection
    - GET /1.0/accounts/{id}/lists/{lid}/subscribers     → subscribers (100/page)

    Per-subscriber fields used:
    - email, subscribed_at (acquisition_date), last_followup_message_number_sent,
      misc_notes, status, custom_fields

    AWeber doesn't expose per-subscriber open/click timestamps via the
    public API (they live behind /sent_messages collections per subscriber,
    too expensive). Engagement dates stay None for now — Acquisition Quality
    + Bounce Exposure + Domain Reputation still get real data.

    Returns a sync stats dict.
    """
    integration = fetchone(
        "SELECT id, user_id FROM esp_integrations WHERE id = ? AND provider = 'aweber'",
        (integration_id,),
    )
    if not integration:
        return {'error': 'integration_not_found'}

    user_id = integration['user_id']

    if not access_token:
        return {'error': 'missing_access_token'}

    headers = {'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'}
    base = 'https://api.aweber.com/1.0'

    stats = {
        'contacts_pulled': 0,
        'contacts_new': 0,
        'contacts_updated': 0,
        'lists_processed': 0,
        'errors': [],
        'started_at': _utcnow().isoformat(),
    }

    cap = max_contacts or MAX_CONTACTS_PER_LIST

    try:
        # Step 1: Find account
        accounts_resp = _api_request(f'{base}/accounts', headers=headers)
        accounts = accounts_resp.get('entries', [])
        if not accounts:
            return {**stats, 'error': 'no_aweber_accounts'}
        account_id = accounts[0].get('id')

        # Step 2: List the lists
        _rate_limit_sleep('aweber')
        lists_resp = _api_request(
            f'{base}/accounts/{account_id}/lists?ws.size=20',
            headers=headers,
        )
        lists = lists_resp.get('entries', [])
        if not lists:
            return {**stats, 'error': 'no_aweber_lists'}

        # Step 3: Walk subscribers per list
        for lst in lists:
            list_id = lst.get('id')
            if not list_id:
                continue

            list_total = 0
            page = 1
            page_size = PAGE_SIZES.get('aweber', 100)

            while stats['contacts_pulled'] < cap:
                _rate_limit_sleep('aweber')

                # AWeber pagination uses ws.start + ws.size
                params = {
                    'ws.start': (page - 1) * page_size,
                    'ws.size': page_size,
                }
                qs = urllib.parse.urlencode(params)
                url = f'{base}/accounts/{account_id}/lists/{list_id}/subscribers?{qs}'

                try:
                    sub_resp = _api_request(url, headers=headers)
                except urllib.error.HTTPError as e:
                    stats['errors'].append(f'list {list_id} page {page}: HTTP {e.code}')
                    break
                except Exception as e:
                    stats['errors'].append(f'list {list_id} page {page}: {type(e).__name__}')
                    break

                entries = sub_resp.get('entries', [])
                if not entries:
                    break

                batch = []
                for sub in entries:
                    email = (sub.get('email') or '').lower().strip()
                    if not email:
                        continue

                    status = (sub.get('status') or '').lower()
                    is_hard_bounce = status in ('undeliverable', 'bounced')

                    batch.append({
                        'email': email,
                        'last_open_date': None,    # Not exposed via subscribers endpoint
                        'last_click_date': None,
                        'last_reply_date': None,
                        'acquisition_date': sub.get('subscribed_at'),
                        'is_hard_bounce': is_hard_bounce,
                    })

                batch_stats = _upsert_contacts_batch(user_id, integration_id, batch)
                stats['contacts_new'] += batch_stats['new']
                stats['contacts_updated'] += batch_stats['updated']
                stats['contacts_pulled'] += len(batch)
                list_total += len(batch)

                if len(entries) < page_size:
                    break
                page += 1
                if page > 1000:  # safety
                    break

            stats['lists_processed'] += 1
            logger.info(f'AWeber sync: list {list_id} pulled {list_total} subscribers')

        # Update last_synced_at
        execute(
            "UPDATE esp_integrations SET last_synced_at = datetime('now') WHERE id = ?",
            (integration_id,),
        )

        stats['finished_at'] = _utcnow().isoformat()
        return stats

    except Exception as e:
        logger.exception(f'AWeber sync failed for integration {integration_id}')
        stats['errors'].append(f'fatal: {type(e).__name__}: {e}')
        return stats


# ── Dispatcher ─────────────────────────────────────────

def sync_contacts_for_integration(integration_id):
    """
    Master dispatcher: given an ESP integration ID, decrypt the API key
    and call the appropriate per-contact sync function.

    Returns a stats dict or an error dict.
    """
    from blueprints.integration_routes import _decrypt_value

    integration = fetchone(
        """SELECT id, user_id, provider, api_key_encrypted, server_prefix, label
           FROM esp_integrations WHERE id = ? AND status = 'active'""",
        (integration_id,),
    )
    if not integration:
        return {'error': 'integration_not_found_or_inactive'}

    provider = integration['provider']
    api_key = _decrypt_value(integration['api_key_encrypted'])
    server_prefix = integration.get('server_prefix') or ''

    if provider == 'mailchimp':
        return sync_mailchimp_contacts(integration_id, api_key)

    elif provider == 'activecampaign':
        return sync_activecampaign_contacts(integration_id, api_key, server_prefix)

    elif provider == 'mailgun':
        return sync_mailgun_events(integration_id, api_key, server_prefix)

    elif provider == 'aweber':
        return sync_aweber_subscribers(integration_id, api_key)

    elif provider in ('instantly', 'smartlead', 'gohighlevel'):
        return {
            'not_supported': True,
            'provider': provider,
            'message': f'{provider} does not expose per-contact engagement data. Use CSV upload path instead.',
        }

    else:
        return {'error': f'unknown_provider: {provider}'}


# ── Contact retrieval for Signal Score calculation ────

def get_contacts_for_signal_score(user_id, esp_integration_id=None, limit=None):
    """
    Fetch contact records from contact_segments in the format expected
    by modules.signal_score.calculate_signal_score().

    Returns list of dicts with:
    - email, last_open_date, last_click_date, last_reply_date
    - acquisition_date
    - is_hard_bounce, is_catch_all, is_role_address, is_disposable
    - likely_mpp_opener
    """
    sql = """SELECT email, last_open_date, last_click_date, last_reply_date,
                    acquisition_date, is_hard_bounce, is_catch_all,
                    is_role_address, is_disposable, likely_mpp_opener
             FROM contact_segments
             WHERE user_id = ? AND is_suppressed = 0"""
    params = [user_id]

    if esp_integration_id is not None:
        sql += " AND esp_integration_id = ?"
        params.append(esp_integration_id)

    if limit:
        sql += f" LIMIT {int(limit)}"

    rows = fetchall(sql, tuple(params))

    # Convert SQLite rows to contact dicts with proper types
    contacts = []
    for r in rows:
        contacts.append({
            'email': r['email'],
            'last_open_date': r['last_open_date'],
            'last_click_date': r['last_click_date'],
            'last_reply_date': r['last_reply_date'],
            'acquisition_date': r['acquisition_date'],
            'is_hard_bounce': bool(r['is_hard_bounce']),
            'is_catch_all': bool(r['is_catch_all']),
            'is_role_address': bool(r['is_role_address']),
            'is_disposable': bool(r['is_disposable']),
            'likely_mpp_opener': bool(r['likely_mpp_opener']),
        })

    return contacts
