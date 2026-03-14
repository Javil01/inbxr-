"""
INBXR — Inbox Placement Tester
Checks seed mailboxes via IMAP to determine inbox vs spam vs promotions placement.
Uses Python stdlib imaplib — zero external dependencies.
"""

import imaplib
import json
import logging
import os
import re
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

logger = logging.getLogger('inbxr.inbox_placement')

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "seed_accounts.json")

# ── Timeouts ─────────────────────────────────────────
_IMAP_CONNECT_TIMEOUT = 10   # seconds
_IMAP_OPERATION_TIMEOUT = 15  # seconds per folder operation

# ── Rate limiting ────────────────────────────────────
_rate_lock = Lock()
_rate_log = []              # timestamps of recent checks
_RATE_LIMIT = 10            # max checks per window
_RATE_WINDOW = 60           # window in seconds

# ── Default IMAP settings per provider ───────────────
_PROVIDER_DEFAULTS = {
    "gmail":   {"host": "imap.gmail.com",       "port": 993},
    "outlook": {"host": "outlook.office365.com", "port": 993},
    "yahoo":   {"host": "imap.mail.yahoo.com",  "port": 993},
    "icloud":  {"host": "imap.mail.me.com",     "port": 993},
    "aol":     {"host": "imap.aol.com",         "port": 993},
    "zoho":    {"host": "imap.zoho.com",        "port": 993},
}

# ── Spam folder names per provider ───────────────────
_SPAM_FOLDERS = {
    "gmail":   ["[Gmail]/Spam"],
    "outlook": ["Junk"],
    "yahoo":   ["Bulk Mail", "Bulk"],
    "icloud":  ["Junk"],
    "aol":     ["Spam"],
    "zoho":    ["Spam"],
}

_TRASH_FOLDERS = {
    "gmail":   ["[Gmail]/Trash"],
    "outlook": ["Deleted Items", "Deleted", "Trash"],
    "yahoo":   ["Trash"],
    "icloud":  ["Trash", "Deleted Messages"],
    "aol":     ["Trash"],
    "zoho":    ["Trash"],
}

# ── Gmail X-GM-LABELS category patterns ──────────────
_GMAIL_TAB_PATTERNS = [
    (re.compile(r"\\?Category[_/\\]?Promotions", re.IGNORECASE), "promotions"),
    (re.compile(r"\\?Category[_/\\]?Social",     re.IGNORECASE), "social"),
    (re.compile(r"\\?Category[_/\\]?Updates",    re.IGNORECASE), "updates"),
    (re.compile(r"\\?Category[_/\\]?Forums",     re.IGNORECASE), "forums"),
    # Fallback: bare label names (some IMAP responses use these)
    (re.compile(r"\bPromotions\b", re.IGNORECASE), "promotions"),
    (re.compile(r"\bSocial\b",     re.IGNORECASE), "social"),
    (re.compile(r"\bUpdates\b",    re.IGNORECASE), "updates"),
    (re.compile(r"\bForums\b",     re.IGNORECASE), "forums"),
]

_MAX_RETRIES = 1  # one retry on transient IMAP failures


# ══════════════════════════════════════════════════════
#  RATE LIMITING
# ══════════════════════════════════════════════════════

def check_rate_limit() -> bool:
    """Returns True if within rate limit, False if exceeded."""
    now = time.time()
    with _rate_lock:
        # Prune old entries
        cutoff = now - _RATE_WINDOW
        _rate_log[:] = [t for t in _rate_log if t > cutoff]
        if len(_rate_log) >= _RATE_LIMIT:
            return False
        _rate_log.append(now)
        return True


# ══════════════════════════════════════════════════════
#  CONFIG & HELPERS
# ══════════════════════════════════════════════════════

def load_seed_accounts():
    """Load seed accounts from config file or SEED_ACCOUNTS env var."""
    # Try env var first (for Railway/production where config file is gitignored)
    env_seeds = os.environ.get("SEED_ACCOUNTS", "")
    if env_seeds:
        try:
            return json.loads(env_seeds)
        except (json.JSONDecodeError, ValueError):
            logger.error("Failed to parse SEED_ACCOUNTS env var")
            return []
    # Fall back to config file (local development)
    if not os.path.exists(CONFIG_PATH):
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def get_seed_info():
    """Return public seed info (email + provider) without credentials."""
    return [
        {
            "email": a["email"],
            "provider": a["provider"],
            "label": a.get("label", a["provider"].title()),
        }
        for a in load_seed_accounts()
    ]


def generate_token():
    """Generate a unique test token for subject-line matching."""
    return f"INBXR-{uuid.uuid4().hex[:8].upper()}"


# ══════════════════════════════════════════════════════
#  SEED HEALTH CHECK
# ══════════════════════════════════════════════════════

def check_seed_health() -> list:
    """Test IMAP connectivity for all seed accounts. Returns health status per seed."""
    accounts = load_seed_accounts()
    if not accounts:
        return []

    results = []
    for acc in accounts:
        provider = acc["provider"]
        defaults = _PROVIDER_DEFAULTS.get(provider, {})
        host = acc.get("imap_host", defaults.get("host", ""))
        port = acc.get("imap_port", defaults.get("port", 993))

        status = {
            "provider": provider,
            "label": acc.get("label", provider.title()),
            "email": acc["email"],
            "healthy": False,
            "error": None,
            "latency_ms": None,
        }

        if not host:
            status["error"] = "No IMAP host configured"
            results.append(status)
            continue

        start = time.time()
        imap = None
        try:
            imap = imaplib.IMAP4_SSL(host, port, timeout=_IMAP_CONNECT_TIMEOUT)
            imap.login(acc["username"], acc["password"])
            imap.select("INBOX", readonly=True)
            status["healthy"] = True
            status["latency_ms"] = round((time.time() - start) * 1000)
        except Exception as e:
            logger.exception("Seed health check failed for %s", acc["email"])
            status["error"] = str(e)[:120]
            status["latency_ms"] = round((time.time() - start) * 1000)
        finally:
            if imap:
                try:
                    imap.logout()
                except Exception:
                    pass  # Cleanup — safe to ignore

        results.append(status)
    return results


# ══════════════════════════════════════════════════════
#  SEED CLEANUP
# ══════════════════════════════════════════════════════

def cleanup_seeds(keep_token: str = None) -> dict:
    """Delete old INBXR test emails from all seed inboxes.
    Optionally keep emails matching keep_token."""
    accounts = load_seed_accounts()
    summary = {"accounts": 0, "deleted": 0, "errors": []}

    for acc in accounts:
        provider = acc["provider"]
        defaults = _PROVIDER_DEFAULTS.get(provider, {})
        host = acc.get("imap_host", defaults.get("host", ""))
        port = acc.get("imap_port", defaults.get("port", 993))

        if not host:
            continue

        imap = None
        try:
            imap = imaplib.IMAP4_SSL(host, port, timeout=_IMAP_CONNECT_TIMEOUT)
            imap.login(acc["username"], acc["password"])
            summary["accounts"] += 1

            # Search all standard folders for INBXR test emails
            folders_to_clean = ["INBOX"] + \
                _SPAM_FOLDERS.get(provider, []) + \
                _TRASH_FOLDERS.get(provider, [])

            for folder in folders_to_clean:
                try:
                    status, _ = imap.select(f'"{folder}"')
                    if status != "OK":
                        continue

                    status, msg_ids = imap.search(None, '(SUBJECT "INBXR-")')
                    if status != "OK" or not msg_ids[0]:
                        continue

                    for msg_id in msg_ids[0].split():
                        # If keep_token specified, check if this email matches
                        if keep_token:
                            st, hdr = imap.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                            if st == "OK" and hdr and hdr[0]:
                                raw = hdr[0][1] if isinstance(hdr[0], tuple) else hdr[0]
                                subj = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                                if keep_token in subj:
                                    continue

                        imap.store(msg_id, "+FLAGS", "\\Deleted")
                        summary["deleted"] += 1

                    imap.expunge()
                except Exception:
                    logger.exception("Failed to clean folder %s for %s", folder, acc["email"])

        except Exception as e:
            logger.exception("Seed cleanup failed for %s", acc["email"])
            summary["errors"].append(f"{acc['email']}: {str(e)[:80]}")
        finally:
            if imap:
                try:
                    imap.logout()
                except Exception:
                    pass  # Cleanup — safe to ignore

    return summary


# ══════════════════════════════════════════════════════
#  INBOX PLACEMENT TESTER
# ══════════════════════════════════════════════════════

class InboxPlacementTester:
    """Check seed mailboxes via IMAP for a test email identified by token."""

    def __init__(self, token: str):
        self.token = token
        self.accounts = load_seed_accounts()

    def check_all(self) -> list:
        """Check all seed accounts concurrently. Returns list of results."""
        if not self.accounts:
            return []

        results = []
        workers = min(len(self.accounts), 6)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._check_with_retry, acc): acc
                for acc in self.accounts
            }
            for f in as_completed(futures):
                results.append(f.result())

        results.sort(key=lambda r: r["provider"])
        return results

    # ── Retry wrapper ────────────────────────────────
    def _check_with_retry(self, account: dict) -> dict:
        """Check account with retry on transient failure."""
        last_result = None
        for attempt in range(_MAX_RETRIES + 1):
            result = self._check_account(account)
            if result["error"] is None:
                return result
            last_result = result
            if attempt < _MAX_RETRIES:
                time.sleep(1)  # brief pause before retry
        return last_result

    # ── Single-account check ─────────────────────────
    def _check_account(self, account: dict) -> dict:
        provider = account["provider"]
        defaults = _PROVIDER_DEFAULTS.get(provider, {})
        host = account.get("imap_host", defaults.get("host", ""))
        port = account.get("imap_port", defaults.get("port", 993))

        result = {
            "provider": provider,
            "label": account.get("label", provider.title()),
            "email": account["email"],
            "placement": "not_found",
            "folder": None,
            "tab": None,
            "error": None,
            "check_time_ms": None,
        }

        if not host:
            result["error"] = "No IMAP host configured"
            return result

        start = time.time()
        imap = None
        try:
            # Connect with timeout
            imap = imaplib.IMAP4_SSL(host, port, timeout=_IMAP_CONNECT_TIMEOUT)
            imap.socket().settimeout(_IMAP_OPERATION_TIMEOUT)
            imap.login(account["username"], account["password"])

            # 1. Check INBOX
            found, tab = self._search_folder(imap, "INBOX", provider)
            if found:
                result["placement"] = "inbox"
                result["folder"] = "INBOX"
                result["tab"] = tab
                result["check_time_ms"] = round((time.time() - start) * 1000)
                return result

            # 2. Check spam / junk
            for folder in _SPAM_FOLDERS.get(provider, ["Spam", "Junk"]):
                found, _ = self._search_folder(imap, folder, provider)
                if found:
                    result["placement"] = "spam"
                    result["folder"] = folder
                    result["check_time_ms"] = round((time.time() - start) * 1000)
                    return result

            # 3. Check trash
            for folder in _TRASH_FOLDERS.get(provider, ["Trash"]):
                found, _ = self._search_folder(imap, folder, provider)
                if found:
                    result["placement"] = "trash"
                    result["folder"] = folder
                    result["check_time_ms"] = round((time.time() - start) * 1000)
                    return result

        except socket.timeout:
            result["error"] = f"Connection to {host} timed out after {_IMAP_CONNECT_TIMEOUT}s"
        except imaplib.IMAP4.error as e:
            err_str = str(e)[:120]
            if b"AUTHENTICATIONFAILED" in getattr(e, "args", (b"",))[0] if isinstance(getattr(e, "args", (None,))[0], bytes) else "AUTHENTICATIONFAILED" in err_str:
                result["error"] = f"Authentication failed for {account['email']} — app password may be expired"
            else:
                result["error"] = err_str
        except ConnectionError as e:
            result["error"] = f"Connection refused by {host}: {str(e)[:80]}"
        except OSError as e:
            result["error"] = f"Network error reaching {host}: {str(e)[:80]}"
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)[:100]}"
        finally:
            result["check_time_ms"] = round((time.time() - start) * 1000)
            if imap:
                try:
                    imap.logout()
                except Exception:
                    pass

        return result

    # ── Folder search ────────────────────────────────
    def _search_folder(self, imap, folder: str, provider: str):
        """Search folder for email with the test token. Returns (found, tab)."""
        try:
            status, _ = imap.select(f'"{folder}"', readonly=True)
            if status != "OK":
                return False, None

            status, msg_ids = imap.search(None, f'(SUBJECT "{self.token}")')
            if status != "OK" or not msg_ids[0]:
                return False, None

            # Detect Gmail tab if in INBOX
            tab = None
            if provider == "gmail" and folder == "INBOX":
                tab = self._detect_gmail_tab(imap, msg_ids[0].split()[-1])

            return True, tab

        except imaplib.IMAP4.error:
            return False, None
        except OSError:
            return False, None

    # ── Gmail tab detection via X-GM-LABELS ──────────
    def _detect_gmail_tab(self, imap, msg_id):
        """Detect which Gmail tab the email landed in using X-GM-LABELS."""
        try:
            # Try X-GM-LABELS first (Gmail-specific IMAP extension)
            status, data = imap.fetch(msg_id, "(X-GM-LABELS)")
            if status != "OK" or not data or not data[0]:
                return "primary"

            raw = data[0][1] if isinstance(data[0], tuple) else data[0]
            labels_str = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)

            # Match against known Gmail category patterns
            for pattern, tab_name in _GMAIL_TAB_PATTERNS:
                if pattern.search(labels_str):
                    return tab_name

            return "primary"

        except imaplib.IMAP4.error:
            # X-GM-LABELS not supported (non-Gmail server), not an error
            return None
        except Exception:
            return None


# ══════════════════════════════════════════════════════
#  RECOMMENDATIONS ENGINE
# ══════════════════════════════════════════════════════

def generate_recommendations(results: list, summary: dict) -> list:
    """Generate actionable recommendations based on placement results."""
    recs = []
    total = summary["total"]
    inbox = summary["inbox"]
    spam = summary["spam"]
    not_found = summary["not_found"]

    if total == 0:
        return recs

    inbox_pct = (inbox / total) * 100

    # ── Check for IMAP errors ────────────────────────
    error_results = [r for r in results if r.get("error")]
    if error_results:
        auth_errors = [r for r in error_results if "Authentication" in (r["error"] or "") or "expired" in (r["error"] or "")]
        timeout_errors = [r for r in error_results if "timed out" in (r["error"] or "")]

        if auth_errors:
            recs.append({
                "severity": "critical",
                "title": f"Seed Account Authentication Failed ({len(auth_errors)} account{'s' if len(auth_errors) != 1 else ''})",
                "text": f"Failed accounts: {', '.join(r['label'] for r in auth_errors)}. The app password may have been revoked or expired.",
                "actions": [
                    "Generate a new app password for the affected account(s)",
                    "Update config/seed_accounts.json with the new password",
                    "Restart the application",
                ],
            })
        if timeout_errors:
            recs.append({
                "severity": "warning",
                "title": f"IMAP Connection Timeout ({len(timeout_errors)} account{'s' if len(timeout_errors) != 1 else ''})",
                "text": f"Timed out: {', '.join(r['label'] for r in timeout_errors)}. The mail server may be slow or unreachable.",
                "actions": [
                    "Re-check in a few minutes — this is often transient",
                    "Verify your internet connection is stable",
                ],
            })

    # ── All not found ────────────────────────────────
    if not_found == total:
        recs.append({
            "severity": "warning",
            "title": "Email Not Detected in Any Mailbox",
            "text": "Your email was not found in any seed mailbox. This could mean it hasn't arrived yet (wait 1-2 minutes and re-check), it was silently dropped by the receiving server, or the sending failed entirely.",
            "actions": [
                "Wait 60 seconds and click Re-check — email delivery can take up to 2 minutes",
                "Verify the email was actually sent from your system (check outbox/sent folder)",
                "Confirm you included the test token in the subject line exactly as shown",
                "Check your sending server's bounce/delivery logs for rejections",
                "Confirm SPF, DKIM, and DMARC are properly configured for your sending domain",
            ],
        })
        return recs

    # ── All inbox ────────────────────────────────────
    if inbox == total and spam == 0:
        promo_results = [r for r in results if r.get("tab") == "promotions"]
        social_results = [r for r in results if r.get("tab") == "social"]
        updates_results = [r for r in results if r.get("tab") == "updates"]
        non_primary = promo_results + social_results + updates_results

        if promo_results:
            recs.append({
                "severity": "info",
                "title": "Delivered to Inbox — But Landing in Promotions Tab",
                "text": f"Your email reached the inbox on all {total} seeds, but {len(promo_results)} landed in Gmail's Promotions tab instead of Primary. Promotions tab emails see 50-70% lower open rates.",
                "actions": [
                    "Reduce HTML complexity — simpler emails are more likely to hit Primary",
                    "Remove or minimize images and heavy formatting",
                    "Avoid multiple CTAs and links — keep it to 1-2 max",
                    "Write in a conversational, personal tone (like a 1-on-1 email)",
                    "Avoid promotional language: 'buy now', 'limited offer', 'click here'",
                    "Use the recipient's first name and reference past interactions",
                    "Send from a personal name (e.g. 'Sarah from Acme') not a brand name",
                    "Ask engaged subscribers to drag your email to Primary (trains Gmail's filter)",
                ],
            })
        elif social_results:
            recs.append({
                "severity": "info",
                "title": f"{len(social_results)} Gmail Account(s) Sorted to Social Tab",
                "text": "Gmail categorized your email under Social. This typically happens with notification-style emails from platforms.",
                "actions": [
                    "Avoid notification-style subject lines ('X commented on your post')",
                    "Write with direct, personal language rather than platform-generated copy",
                    "Reduce social media links and sharing buttons",
                ],
            })
        elif updates_results:
            recs.append({
                "severity": "info",
                "title": f"{len(updates_results)} Gmail Account(s) Sorted to Updates Tab",
                "text": "Gmail categorized your email as an update (confirmations, receipts, bills). This is normal for transactional emails.",
                "actions": [
                    "For marketing emails: make subject lines less transactional",
                    "For transactional emails: Updates tab placement is acceptable",
                ],
            })
        elif not non_primary:
            recs.append({
                "severity": "pass",
                "title": "Excellent — All Emails Delivered to Inbox",
                "text": f"Your email landed in the primary inbox across all {total} seed accounts. Your sender reputation and email content are performing well.",
                "actions": [
                    "Continue monitoring placement periodically — reputation can change over time",
                    "Maintain consistent sending volume to preserve sender reputation",
                    "Keep your list clean — remove bounces and unengaged subscribers regularly",
                ],
            })
        return recs

    # ── Some or all spam ─────────────────────────────
    if spam > 0:
        if spam == total:
            recs.append({
                "severity": "critical",
                "title": f"All Emails Landed in Spam ({spam}/{total})",
                "text": "Every seed mailbox filtered your email to spam. This indicates a serious deliverability problem that needs immediate attention.",
                "actions": [
                    "Run INBXR's Sender Check to verify SPF, DKIM, and DMARC are configured correctly",
                    "Check if your sending IP or domain is on any blocklists (use Sender Check)",
                    "Run your email through INBXR's Email Analyzer to identify spam trigger words",
                    "Review your email for excessive links, images, or ALL CAPS text",
                    "If using a shared IP (common with ESPs), contact your provider about IP reputation",
                    "If your domain is new (< 30 days), start a warmup campaign with small, engaged segments",
                    "Check if you have a valid unsubscribe mechanism (required by CAN-SPAM and GDPR)",
                ],
            })
        else:
            spam_providers = [r["label"] for r in results if r["placement"] == "spam"]
            inbox_providers = [r["label"] for r in results if r["placement"] == "inbox"]
            recs.append({
                "severity": "warning",
                "title": f"Mixed Results — {spam} of {total} Landed in Spam",
                "text": f"Inbox: {', '.join(inbox_providers)}. Spam: {', '.join(spam_providers)}. Different providers filter differently, which suggests borderline reputation or content issues.",
                "actions": [
                    "Run INBXR's Sender Check to verify authentication records are correct",
                    "Run your email through the Email Analyzer to identify content-based spam triggers",
                    "Check blocklists — you may be listed on a provider-specific list",
                    "Reduce the number of links and images in your email",
                    "Ensure you have a visible, working unsubscribe link",
                    "Check if the spam-flagging providers have specific requirements (e.g. Yahoo requires DMARC)",
                ],
            })

    # ── Promotions tab (when mixed with spam/not_found) ──
    promo_results = [r for r in results if r.get("tab") == "promotions"]
    if promo_results and spam > 0:
        recs.append({
            "severity": "info",
            "title": f"Additionally, {len(promo_results)} Gmail Account(s) Sorted to Promotions",
            "text": "Beyond the spam issue, some Gmail seeds placed your email in Promotions rather than Primary.",
            "actions": [
                "Fix the spam placement issues first — that's the higher priority",
                "Once inbox delivery improves, simplify your email format to target Primary tab",
            ],
        })

    # ── Some not found (partial delivery) ────────────
    if not_found > 0 and not_found < total:
        missing = [r for r in results if r["placement"] == "not_found" and not r.get("error")]
        if missing:
            recs.append({
                "severity": "warning",
                "title": f"Email Not Found on {len(missing)} of {total} Seeds",
                "text": f"Not detected: {', '.join(r['label'] for r in missing)}. The email may still be in transit, or it was silently rejected.",
                "actions": [
                    "Wait 1-2 minutes and click Re-check — delivery can be delayed",
                    "Check your sending server logs for bounces or rejections from these providers",
                    "Verify your SPF record includes your sending server's IP",
                    "Some providers silently drop emails from domains with no DMARC policy",
                ],
            })

    # ── Trash placement ──────────────────────────────
    trash_results = [r for r in results if r["placement"] == "trash"]
    if trash_results:
        trash_providers = [r["label"] for r in trash_results]
        recs.append({
            "severity": "critical",
            "title": f"Email Found in Trash on {len(trash_results)} Seed(s)",
            "text": f"Trash: {', '.join(trash_providers)}. The email was delivered but immediately trashed, indicating aggressive filtering or a prior spam report.",
            "actions": [
                "This seed account may have previously marked similar emails as spam — the provider learned to auto-delete",
                "Check if your domain has been reported to abuse lists",
                "Try a different seed account for this provider to confirm it's not account-specific",
            ],
        })

    # ── General tips when not perfect ────────────────
    if 0 < inbox_pct < 100:
        recs.append({
            "severity": "info",
            "title": "General Deliverability Tips",
            "text": f"Your inbox placement rate is {inbox_pct:.0f}%. Here are steps to improve it across all providers.",
            "actions": [
                "Use INBXR's Email Analyzer to check your content for spam triggers before sending",
                "Use INBXR's Sender Check to verify your full authentication setup",
                "Warm up new sending domains gradually — start with small, engaged segments",
                "Maintain a consistent sending schedule and volume (avoid big spikes)",
                "Remove hard bounces and unengaged recipients from your list",
                "Include a plain-text version alongside HTML for better compatibility",
                "Monitor placement regularly — run this test before every major campaign",
            ],
        })

    return recs
