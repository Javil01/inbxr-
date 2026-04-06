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
from datetime import datetime, timedelta

from modules.database import execute, fetchone, fetchall

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

    now = datetime.utcnow()
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
        'started_at': datetime.utcnow().isoformat(),
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

                # Convert Mailchimp records to signal engine contact format
                batch = []
                for m in members:
                    email = m.get('email_address', '')
                    status = m.get('status', '')

                    # Mailchimp member stats don't give us last_open date directly —
                    # we need the activity feed for that. For now, use timestamps we have.
                    last_changed = m.get('last_changed')

                    batch.append({
                        'email': email,
                        'last_open_date': last_changed,  # Approximation — will be replaced with activity fetch
                        'last_click_date': None,
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

        # Step 3: Update last_synced_at on the integration
        execute(
            "UPDATE esp_integrations SET last_synced_at = datetime('now') WHERE id = ?",
            (integration_id,),
        )

        stats['finished_at'] = datetime.utcnow().isoformat()
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

    stats = {
        'events_processed': 0,
        'contacts_updated': 0,
        'errors': [],
    }

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

                for act in activity:
                    act_type = act.get('action')
                    act_ts = act.get('timestamp')
                    if not act_ts:
                        continue

                    if act_type == 'open':
                        if not last_open or act_ts > last_open:
                            last_open = act_ts
                    elif act_type == 'click':
                        if not last_click or act_ts > last_click:
                            last_click = act_ts

                # Update existing contact segment if present
                existing = fetchone(
                    """SELECT id, last_open_date, last_click_date
                       FROM contact_segments
                       WHERE user_id = ? AND esp_integration_id = ? AND email = ?""",
                    (user_id, integration_id, email),
                )

                if existing:
                    # Merge — keep the most recent across all campaigns
                    new_open = last_open or existing['last_open_date']
                    new_click = last_click or existing['last_click_date']

                    # Only update if something is newer
                    if last_open and (not existing['last_open_date'] or last_open > existing['last_open_date']):
                        new_open = last_open
                    if last_click and (not existing['last_click_date'] or last_click > existing['last_click_date']):
                        new_click = last_click

                    segment, days_since = _segment_from_engagement(new_open, new_click, None)

                    execute(
                        """UPDATE contact_segments SET
                            last_open_date = ?,
                            last_click_date = ?,
                            segment = ?,
                            days_since_engagement = ?,
                            updated_at = datetime('now')
                           WHERE id = ?""",
                        (new_open, new_click, segment, days_since, existing['id']),
                    )
                    stats['contacts_updated'] += 1

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

def sync_activecampaign_contacts(integration_id, api_key, server_prefix, since=None):
    """
    STUB: ActiveCampaign per-contact sync.
    To be implemented after Mailchimp validation.

    Target endpoints:
    - /api/3/contacts?limit=100&orders[cdate]=DESC (paginated)
    - /api/3/activities?contact=<id>&orders[tstamp]=DESC (per-contact, expensive)
    """
    logger.warning('sync_activecampaign_contacts: not yet implemented')
    return {
        'not_implemented': True,
        'message': 'ActiveCampaign per-contact sync is planned for Phase 2b',
    }


# ── Mailgun per-contact sync (STUB — Phase 2b) ─────────

def sync_mailgun_events(integration_id, api_key, domain, days_back=3):
    """
    STUB: Mailgun events API sync.
    To be implemented after Mailchimp validation.

    Target endpoint:
    - /v3/{domain}/events?begin=...&event=opened|clicked|bounced
    - Returns User-Agent + IP per event — enables HIGH ACCURACY MPP detection
    - Free plan has 3-day retention, paid has longer
    """
    logger.warning('sync_mailgun_events: not yet implemented')
    return {
        'not_implemented': True,
        'message': 'Mailgun per-event sync is planned for Phase 2b',
    }


# ── AWeber per-contact sync (STUB — Phase 2b) ──────────

def sync_aweber_subscribers(integration_id, access_token):
    """
    STUB: AWeber per-subscriber sync.
    To be implemented after Mailchimp validation.

    Target endpoints:
    - /1.0/accounts/{id}/lists (get lists)
    - /1.0/accounts/{id}/lists/{list_id}/subscribers (paginated subscribers)
    """
    logger.warning('sync_aweber_subscribers: not yet implemented')
    return {
        'not_implemented': True,
        'message': 'AWeber per-subscriber sync is planned for Phase 2b',
    }


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
