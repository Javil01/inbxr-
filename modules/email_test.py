"""
InbXr — Email Test Analyzer
Fetches a real received email via IMAP, parses headers comprehensively,
and runs all analysis modules against the actual content.
"""

import logging
import re
import time
import imaplib
import email as email_lib
from email import policy as email_policy
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger('inbxr.email_test')

from modules.inbox_placement import (
    load_seed_accounts, generate_token, check_rate_limit,
    _PROVIDER_DEFAULTS, _SPAM_FOLDERS, _TRASH_FOLDERS,
    _GMAIL_TAB_PATTERNS, _IMAP_CONNECT_TIMEOUT, _IMAP_OPERATION_TIMEOUT,
)


# ══════════════════════════════════════════════════════
#  EMAIL FETCHER
# ══════════════════════════════════════════════════════

class EmailTestFetcher:
    """Connect to a seed mailbox via IMAP, find a test email by token,
    and return the full raw RFC822 message bytes."""

    def __init__(self, token: str, seed_email: str = None):
        self.token = token
        self.seed_email = seed_email
        self.accounts = load_seed_accounts()

    def _get_target_account(self) -> dict:
        """Get the target seed account (specific email or first available)."""
        if self.seed_email:
            for acc in self.accounts:
                if acc["email"].lower() == self.seed_email.lower():
                    return acc
        return self.accounts[0] if self.accounts else None

    def fetch(self) -> dict:
        """Fetch the raw email. Returns dict with status, raw_bytes, placement info."""
        account = self._get_target_account()
        if not account:
            return {"status": "error", "error": "No seed account configured."}

        provider = account["provider"]
        defaults = _PROVIDER_DEFAULTS.get(provider, {})
        host = account.get("imap_host", defaults.get("host", ""))
        port = account.get("imap_port", defaults.get("port", 993))

        if not host:
            return {"status": "error", "error": "No IMAP host configured for seed account."}

        start = time.time()
        imap = None
        try:
            imap = imaplib.IMAP4_SSL(host, port, timeout=_IMAP_CONNECT_TIMEOUT)
            imap.socket().settimeout(_IMAP_OPERATION_TIMEOUT)
            imap.login(account["username"], account["password"])

            # Search folders in order: INBOX, spam, trash
            folders_to_check = [
                ("INBOX", "inbox"),
            ] + [
                (f, "spam") for f in _SPAM_FOLDERS.get(provider, ["Spam", "Junk"])
            ] + [
                (f, "trash") for f in _TRASH_FOLDERS.get(provider, ["Trash"])
            ]

            for folder_name, placement in folders_to_check:
                result = self._search_and_fetch(imap, folder_name, provider)
                if result:
                    raw_bytes, tab = result
                    elapsed = round((time.time() - start) * 1000)
                    return {
                        "status": "found",
                        "raw_bytes": raw_bytes,
                        "placement": placement,
                        "folder": folder_name,
                        "tab": tab,
                        "provider": provider,
                        "seed_email": account["email"],
                        "elapsed_ms": elapsed,
                    }

            elapsed = round((time.time() - start) * 1000)
            return {"status": "not_found", "elapsed_ms": elapsed}

        except Exception as e:
            logger.exception("Email test fetch failed")
            elapsed = round((time.time() - start) * 1000)
            return {"status": "error", "error": str(e)[:200], "elapsed_ms": elapsed}
        finally:
            if imap:
                try:
                    imap.logout()
                except Exception:
                    pass  # Cleanup — safe to ignore

    def _search_and_fetch(self, imap, folder: str, provider: str):
        """Search folder for token, fetch full raw message. Returns (raw_bytes, tab) or None."""
        try:
            status, _ = imap.select(f'"{folder}"', readonly=True)
            if status != "OK":
                return None

            status, msg_ids = imap.search(None, f'(SUBJECT "{self.token}")')
            if status != "OK" or not msg_ids[0]:
                return None

            # Get the most recent match
            msg_id = msg_ids[0].split()[-1]

            # Fetch full RFC822 message
            status, data = imap.fetch(msg_id, "(BODY.PEEK[])")
            if status != "OK" or not data or not data[0]:
                return None

            raw_bytes = data[0][1] if isinstance(data[0], tuple) else data[0]
            if not isinstance(raw_bytes, bytes):
                return None

            # Detect Gmail tab
            tab = None
            if provider == "gmail" and folder == "INBOX":
                tab = self._detect_gmail_tab(imap, msg_id)

            return raw_bytes, tab

        except imaplib.IMAP4.error:
            return None
        except OSError:
            return None

    def _detect_gmail_tab(self, imap, msg_id):
        """Detect Gmail tab using X-GM-LABELS."""
        try:
            status, data = imap.fetch(msg_id, "(X-GM-LABELS)")
            if status != "OK" or not data or not data[0]:
                return "primary"
            raw = data[0][1] if isinstance(data[0], tuple) else data[0]
            labels_str = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            for pattern, tab_name in _GMAIL_TAB_PATTERNS:
                if pattern.search(labels_str):
                    return tab_name
            return "primary"
        except Exception:
            return None


# ══════════════════════════════════════════════════════
#  HEADER PARSER
# ══════════════════════════════════════════════════════

def parse_email_headers(raw_bytes: bytes) -> dict:
    """Parse raw email into comprehensive header analysis."""
    msg = email_lib.message_from_bytes(raw_bytes, policy=email_policy.compat32)

    result = {
        "authentication": _parse_auth_results(msg),
        "transport": _parse_transport(msg),
        "identity": _parse_identity(msg),
        "list_unsubscribe": _parse_list_unsubscribe(msg),
        "dkim_signature": _parse_dkim_signature(msg),
        "arc": _parse_arc(msg),
        "mime": _parse_mime_structure(msg),
        "spam_headers": _parse_spam_headers(msg),
        "all_headers": _get_header_summary(msg),
    }
    return result


def _parse_auth_results(msg) -> dict:
    """Parse Authentication-Results header into structured verdicts."""
    auth_header = str(msg.get("Authentication-Results", "") or "")
    if not auth_header:
        # Try ARC-Authentication-Results
        auth_header = str(msg.get("ARC-Authentication-Results", "") or "")

    result = {
        "raw": auth_header[:500] if auth_header else None,
        "spf": {"verdict": "none", "detail": None},
        "dkim": {"verdict": "none", "detail": None},
        "dmarc": {"verdict": "none", "detail": None},
    }

    if not auth_header:
        return result

    # Parse SPF
    spf_match = re.search(r'\bspf=(pass|fail|softfail|neutral|none|temperror|permerror)\b', auth_header, re.IGNORECASE)
    if spf_match:
        result["spf"]["verdict"] = spf_match.group(1).lower()
        # Extract domain
        spf_domain = re.search(r'smtp\.mailfrom=([^\s;]+)', auth_header, re.IGNORECASE)
        if spf_domain:
            result["spf"]["detail"] = spf_domain.group(1).strip()

    # Parse DKIM
    dkim_match = re.search(r'\bdkim=(pass|fail|neutral|none|temperror|permerror)\b', auth_header, re.IGNORECASE)
    if dkim_match:
        result["dkim"]["verdict"] = dkim_match.group(1).lower()
        dkim_domain = re.search(r'header\.d=([^\s;]+)', auth_header, re.IGNORECASE)
        if dkim_domain:
            result["dkim"]["detail"] = dkim_domain.group(1).strip()

    # Parse DMARC
    dmarc_match = re.search(r'\bdmarc=(pass|fail|none|bestguesspass)\b', auth_header, re.IGNORECASE)
    if dmarc_match:
        result["dmarc"]["verdict"] = dmarc_match.group(1).lower()
        dmarc_domain = re.search(r'header\.from=([^\s;]+)', auth_header, re.IGNORECASE)
        if dmarc_domain:
            result["dmarc"]["detail"] = dmarc_domain.group(1).strip()

    return result


def _parse_transport(msg) -> dict:
    """Parse Received headers for transport info: TLS, hops, sender IP."""
    received_headers = msg.get_all("Received") or []
    hops = []
    sender_ip = None
    tls_used = False
    tls_version = None
    tls_cipher = None

    for i, hdr in enumerate(received_headers):
        hdr_str = str(hdr)
        hop = {"index": i, "raw": hdr_str[:300]}

        # Extract IP from "from" clause
        ip_match = re.search(r'\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]', hdr_str)
        if ip_match:
            hop["ip"] = ip_match.group(1)
            if i == len(received_headers) - 1 or (i > 0 and not sender_ip):
                # Last received header (first hop) typically has the sender IP
                pass
            if not sender_ip and not ip_match.group(1).startswith(("10.", "172.", "192.168.", "127.")):
                sender_ip = ip_match.group(1)

        # Extract "from" hostname
        from_match = re.search(r'from\s+([\w.\-]+)', hdr_str, re.IGNORECASE)
        if from_match:
            hop["from_host"] = from_match.group(1)

        # Extract "by" hostname
        by_match = re.search(r'by\s+([\w.\-]+)', hdr_str, re.IGNORECASE)
        if by_match:
            hop["by_host"] = by_match.group(1)

        # Check for TLS
        tls_match = re.search(r'(TLSv[\d.]+|TLS\d+|ESMTPS|with\s+SMTP[SE]+)', hdr_str, re.IGNORECASE)
        if tls_match:
            tls_used = True
            ver = re.search(r'(TLSv[\d.]+)', hdr_str, re.IGNORECASE)
            if ver:
                tls_version = ver.group(1)
            cipher_match = re.search(r'cipher=([^\s;)]+)', hdr_str, re.IGNORECASE)
            if cipher_match:
                tls_cipher = cipher_match.group(1)

        if "ESMTPS" in hdr_str or "TLS" in hdr_str.upper():
            hop["encrypted"] = True
        else:
            hop["encrypted"] = False

        hops.append(hop)

    # Try to get sender IP from first received header (outermost hop = last in list)
    if not sender_ip and hops:
        for hop in reversed(hops):
            if "ip" in hop and not hop["ip"].startswith(("10.", "172.", "192.168.", "127.")):
                sender_ip = hop["ip"]
                break

    return {
        "hops": hops[:10],  # Cap at 10
        "hop_count": len(received_headers),
        "sender_ip": sender_ip,
        "tls_used": tls_used,
        "tls_version": tls_version,
        "tls_cipher": tls_cipher,
    }


def _parse_identity(msg) -> dict:
    """Parse sender identity headers."""
    from_header = str(msg.get("From", "") or "")
    return_path = str(msg.get("Return-Path", "") or "").strip("<>").strip()
    message_id = str(msg.get("Message-ID", "") or "")
    x_mailer = str(msg.get("X-Mailer", "") or "") or str(msg.get("User-Agent", "") or "")
    reply_to = str(msg.get("Reply-To", "") or "")
    precedence = str(msg.get("Precedence", "") or "")
    x_priority = str(msg.get("X-Priority", "") or "")

    # Check From vs Return-Path alignment
    from_domain = _extract_domain(from_header)
    rp_domain = _extract_domain(return_path)
    aligned = from_domain and rp_domain and (from_domain == rp_domain or rp_domain.endswith(f".{from_domain}") or from_domain.endswith(f".{rp_domain}"))

    return {
        "from": from_header,
        "return_path": return_path,
        "from_domain": from_domain,
        "return_path_domain": rp_domain,
        "aligned": aligned,
        "message_id": message_id,
        "x_mailer": x_mailer[:100] if x_mailer else None,
        "reply_to": reply_to or None,
        "precedence": precedence or None,
        "x_priority": x_priority or None,
    }


def _parse_list_unsubscribe(msg) -> dict:
    """Parse List-Unsubscribe and List-Unsubscribe-Post headers."""
    lu = str(msg.get("List-Unsubscribe", "") or "")
    lu_post = str(msg.get("List-Unsubscribe-Post", "") or "")

    result = {
        "present": bool(lu.strip()),
        "raw": lu[:300] if lu else None,
        "mailto": None,
        "url": None,
        "one_click": False,
    }

    if not lu:
        return result

    # Extract mailto
    mailto_match = re.search(r'<mailto:([^>]+)>', lu, re.IGNORECASE)
    if mailto_match:
        result["mailto"] = mailto_match.group(1)

    # Extract URL
    url_match = re.search(r'<(https?://[^>]+)>', lu, re.IGNORECASE)
    if url_match:
        result["url"] = url_match.group(1)

    # RFC 8058 one-click
    if lu_post and "List-Unsubscribe=One-Click" in lu_post:
        result["one_click"] = True

    return result


def _parse_dkim_signature(msg) -> dict:
    """Parse DKIM-Signature header."""
    dkim_hdr = str(msg.get("DKIM-Signature", "") or "")

    result = {
        "present": bool(dkim_hdr.strip()),
        "domain": None,
        "selector": None,
        "algorithm": None,
        "headers_signed": [],
        "raw": dkim_hdr[:400] if dkim_hdr else None,
    }

    if not dkim_hdr:
        return result

    # d= domain
    d_match = re.search(r'\bd=([^;\s]+)', dkim_hdr)
    if d_match:
        result["domain"] = d_match.group(1).strip()

    # s= selector
    s_match = re.search(r'\bs=([^;\s]+)', dkim_hdr)
    if s_match:
        result["selector"] = s_match.group(1).strip()

    # a= algorithm
    a_match = re.search(r'\ba=([^;\s]+)', dkim_hdr)
    if a_match:
        result["algorithm"] = a_match.group(1).strip()

    # h= signed headers
    h_match = re.search(r'\bh=([^;]+)', dkim_hdr)
    if h_match:
        headers = [h.strip() for h in h_match.group(1).split(":") if h.strip()]
        result["headers_signed"] = headers

    return result


def _parse_arc(msg) -> dict:
    """Parse ARC (Authenticated Received Chain) headers."""
    arc_seal = msg.get_all("ARC-Seal") or []
    arc_auth = msg.get_all("ARC-Authentication-Results") or []
    arc_msg_sig = msg.get_all("ARC-Message-Signature") or []

    present = bool(arc_seal or arc_auth or arc_msg_sig)

    chain = []
    for i, auth in enumerate(arc_auth):
        entry = {"index": i + 1, "raw": str(auth)[:300]}
        # Extract verdict
        cv_match = re.search(r'\bcv=(pass|fail|none)\b', str(arc_seal[i]) if i < len(arc_seal) else "", re.IGNORECASE)
        if cv_match:
            entry["chain_validation"] = cv_match.group(1).lower()
        chain.append(entry)

    return {
        "present": present,
        "chain_length": len(arc_auth),
        "chain": chain[:5],  # Cap display
    }


def _parse_mime_structure(msg) -> dict:
    """Walk MIME tree and catalog structure."""
    parts = []
    has_plain = False
    has_html = False

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", "") or "")
            is_attachment = "attachment" in cd

            parts.append({
                "content_type": ct,
                "is_attachment": is_attachment,
                "filename": part.get_filename(),
                "charset": part.get_content_charset(),
            })

            if ct == "text/plain" and not is_attachment:
                has_plain = True
            elif ct == "text/html" and not is_attachment:
                has_html = True
    else:
        ct = msg.get_content_type()
        parts.append({"content_type": ct, "is_attachment": False, "filename": None, "charset": msg.get_content_charset()})
        if ct == "text/plain":
            has_plain = True
        elif ct == "text/html":
            has_html = True

    return {
        "parts": parts[:20],  # Cap
        "part_count": len(parts),
        "has_plain_text": has_plain,
        "has_html": has_html,
        "multipart": msg.is_multipart(),
        "content_type": msg.get_content_type(),
    }


def _parse_spam_headers(msg) -> dict:
    """Extract spam-related headers."""
    result = {
        "x_spam_status": None,
        "x_spam_score": None,
        "x_gm_message_state": None,
        "x_google_smtp_source": None,
        "delivered_to": None,
    }

    for key in ("X-Spam-Status", "X-Spam-Flag", "X-Spam-Report"):
        val = msg.get(key)
        if val:
            result["x_spam_status"] = str(val)[:200]
            break

    score = msg.get("X-Spam-Score")
    if score:
        result["x_spam_score"] = str(score).strip()

    gm_state = msg.get("X-Gm-Message-State")
    if gm_state:
        result["x_gm_message_state"] = "present"

    smtp_src = msg.get("X-Google-Smtp-Source")
    if smtp_src:
        result["x_google_smtp_source"] = "present"

    delivered = msg.get("Delivered-To")
    if delivered:
        result["delivered_to"] = str(delivered)

    return result


def _get_header_summary(msg) -> list:
    """Get a summary list of all header names (for display)."""
    seen = set()
    headers = []
    for key in msg.keys():
        k = key.lower()
        if k not in seen:
            seen.add(k)
            headers.append(key)
    return headers


def _extract_domain(addr: str) -> str:
    """Extract domain from an email address string."""
    match = re.search(r'[\w.+-]+@([\w.-]+)', addr)
    return match.group(1).lower().rstrip(".") if match else None


# ══════════════════════════════════════════════════════
#  BODY EXTRACTION
# ══════════════════════════════════════════════════════

def extract_email_content(raw_bytes: bytes) -> dict:
    """Extract subject, sender, and body from raw email for analysis modules."""
    msg = email_lib.message_from_bytes(raw_bytes, policy=email_policy.compat32)

    subject = str(msg.get("Subject", "") or "")
    from_addr = str(msg.get("From", "") or "")
    # Extract just the email from "Name <email>" format
    email_match = re.search(r'<([^>]+)>', from_addr)
    sender_email = email_match.group(1) if email_match else from_addr.strip()

    # Extract body
    html_body = None
    plain_body = None

    def _decode_part(part):
        payload = part.get_payload(decode=True)
        if not payload:
            return str(part.get_payload() or "")
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", "") or "")
            if "attachment" in cd:
                continue
            if ct == "text/html" and html_body is None:
                html_body = _decode_part(part)
            elif ct == "text/plain" and plain_body is None:
                plain_body = _decode_part(part)
    else:
        ct = msg.get_content_type()
        decoded = _decode_part(msg)
        if ct == "text/html":
            html_body = decoded
        else:
            plain_body = decoded

    body = html_body or plain_body or ""

    # Extract preheader (first ~100 chars of plain text)
    preheader = ""
    if plain_body:
        preheader = plain_body.strip()[:150]
    elif html_body:
        # Strip tags for preheader
        stripped = re.sub(r'<[^>]+>', ' ', html_body)
        stripped = re.sub(r'\s+', ' ', stripped).strip()
        preheader = stripped[:150]

    return {
        "subject": subject,
        "sender_email": sender_email,
        "from_header": from_addr,
        "body": body,
        "preheader": preheader,
        "has_html": html_body is not None,
        "has_plain": plain_body is not None,
    }


# ══════════════════════════════════════════════════════
#  FULL ANALYSIS ORCHESTRATOR
# ══════════════════════════════════════════════════════

def run_full_analysis(raw_bytes: bytes, placement: str, folder: str,
                      tab: str, provider: str, seed_email: str) -> dict:
    """Run comprehensive analysis on a fetched email.

    Parses headers, extracts content, and runs all analysis modules.
    Returns a unified report.
    """
    t0 = time.monotonic()

    # 1. Parse headers
    headers = parse_email_headers(raw_bytes)

    # 2. Extract content for analysis modules
    content = extract_email_content(raw_bytes)
    subject = content["subject"]
    body = content["body"]
    sender_email = content["sender_email"]

    # Remove test token from subject for cleaner analysis
    clean_subject = re.sub(r'\s*InbXr-[A-F0-9]{8}\s*', '', subject).strip()

    # 3. Extract domain for reputation checks
    domain = _extract_domain(sender_email)

    # 4. Auto-detect CTAs from body
    cta_urls = list(set(re.findall(r'https?://[^\s<>"\')\]]+', body)))[:20]
    cta_texts = []
    for pattern in [
        r'<a[^>]*>([^<]{3,60})</a>',
        r'\[([^\]]{3,50})\]\(https?://[^\)]+\)',
        r'(?i)((?:click|get|start|claim|grab|download|try|join|sign up|register|book|schedule|access|unlock|discover|buy|shop|order)\s[^.!?\n]{3,50})',
    ]:
        cta_texts.extend(re.findall(pattern, body, re.IGNORECASE)[:3])
    cta_texts = list(set(cta_texts))[:10]

    # Determine email type from headers
    is_transactional = bool((headers["identity"].get("precedence") or "").lower() in ("bulk", "list"))
    is_plain_text = not content["has_html"]

    # 5. Run analysis modules in parallel where possible
    result = {
        "headers": headers,
        "placement": {
            "folder": folder,
            "placement": placement,
            "tab": tab,
            "provider": provider,
            "seed_email": seed_email,
        },
        "content": {
            "subject": subject,
            "clean_subject": clean_subject,
            "sender_email": sender_email,
            "from_header": content["from_header"],
            "has_html": content["has_html"],
            "has_plain": content["has_plain"],
            "body_html": body if content["has_html"] else "",
            "body_snippet": body[:500] if not content["has_html"] else "",
        },
    }

    # Run spam + copy analysis
    try:
        from modules.spam_analyzer import SpamAnalyzer
        spam = SpamAnalyzer(
            subject=clean_subject, preheader=content["preheader"], body=body,
            sender_email=sender_email, cta_urls=cta_urls, cta_texts=cta_texts,
            is_transactional=is_transactional, is_plain_text=is_plain_text,
            industry="Other",
        )
        result["spam"] = spam.analyze()
    except Exception:
        logger.exception("Non-fatal: spam analysis failed in email test")

    try:
        from modules.copy_analyzer import CopyAnalyzer
        copy = CopyAnalyzer(
            subject=clean_subject, preheader=content["preheader"], body=body,
            sender_email=sender_email, cta_urls=cta_urls, cta_texts=cta_texts,
            is_transactional=is_transactional, is_plain_text=is_plain_text,
            industry="Other",
        )
        result["copy"] = copy.analyze()
    except Exception:
        logger.exception("Non-fatal: copy analysis failed in email test")

    try:
        from modules.swipe_risk_detector import SwipeRiskDetector
        swipe = SwipeRiskDetector(
            subject=clean_subject, body=body,
            is_cold_email=False, is_plain_text=is_plain_text,
        )
        result["swipe_risk"] = swipe.analyze()
    except Exception:
        logger.exception("Non-fatal: swipe risk analysis failed in email test")

    # Readability
    try:
        from modules.readability import analyze_readability
        result["readability"] = analyze_readability(body=body, subject=clean_subject)
    except Exception:
        logger.exception("Non-fatal: readability analysis failed in email test")

    # Link & image validation
    if body:
        try:
            from modules.link_image_validator import validate_links_and_images
            result["link_image"] = validate_links_and_images(body)
        except Exception:
            logger.exception("Non-fatal: link/image validation failed in email test")

    # Reputation check (DNS-based)
    if domain:
        try:
            from modules.reputation_checker import ReputationChecker
            # Use sender IP from headers if available
            sender_ip = headers["transport"].get("sender_ip")
            checker = ReputationChecker(domain=domain, sender_ip=sender_ip)
            result["reputation"] = checker.analyze()
        except Exception:
            logger.exception("Non-fatal: reputation check failed in email test")

        # BIMI
        try:
            from modules.bimi_validator import validate_bimi
            result["bimi"] = validate_bimi(domain)
        except Exception:
            logger.exception("Non-fatal: BIMI validation failed in email test")

    # Benchmarks
    try:
        from modules.benchmarks import get_benchmarks
        result["benchmarks"] = get_benchmarks(
            industry="Other",
            spam_score=result.get("spam", {}).get("score"),
            copy_score=result.get("copy", {}).get("score"),
            readability_score=result.get("readability", {}).get("score"),
            subject_length=len(clean_subject),
            body_word_count=len(re.findall(r"\b\w+\b", body)),
        )
    except Exception:
        logger.exception("Non-fatal: benchmarks failed in email test")

    # Pre-send audit
    try:
        from modules.presend_audit import generate_audit
        result["audit"] = generate_audit(result)
    except Exception:
        logger.exception("Non-fatal: pre-send audit failed in email test")

    # Header-specific grades
    result["header_grades"] = _grade_headers(headers, body)

    result["meta"] = {
        "subject_length": len(clean_subject),
        "body_word_count": len(re.findall(r"\b\w+\b", body)),
        "elapsed_ms": round((time.monotonic() - t0) * 1000),
    }

    return result


def _grade_headers(headers: dict, body: str = "") -> dict:
    """Grade header-derived signals into pass/warn/fail."""
    grades = []

    # ── Authentication verdicts (SPF / DKIM / DMARC) ──
    auth = headers.get("authentication", {})

    _auth_fix = {
        "spf": {
            "fail": (
                "Your sending server's IP is not authorized by your SPF record. "
                "Fix: Log into your DNS provider and add your ESP's include (e.g. "
                "include:_spf.google.com or include:sendgrid.net) to the TXT record "
                "at your domain. Most ESPs list the exact value in their setup docs."
            ),
            "softfail": (
                "SPF returned ~all (softfail) instead of -all. This means your "
                "record exists but isn't strict. Fix: Update your SPF TXT record to "
                "end with -all instead of ~all for a hard fail policy, or ensure your "
                "ESP's sending IP is included."
            ),
            "none": (
                "No SPF record found for your sending domain. Fix: Add a TXT record "
                "at your domain like: v=spf1 include:_spf.google.com ~all (replace "
                "with your ESP's include). Without SPF, any server can spoof your domain."
            ),
            "temperror": (
                "SPF lookup had a temporary DNS error. This is usually transient — "
                "re-test in a few minutes. If persistent, check that your SPF record "
                "doesn't exceed 10 DNS lookups (the SPF specification limit)."
            ),
            "permerror": (
                "Your SPF record has a syntax error or exceeds the 10-lookup limit. "
                "Fix: Use an SPF flattening tool or remove unnecessary includes. "
                "Validate your record at mxtoolbox.com/spf.aspx."
            ),
        },
        "dkim": {
            "fail": (
                "DKIM signature verification failed — the message may have been "
                "altered in transit, or the public key in DNS doesn't match. Fix: "
                "Re-publish your DKIM public key in DNS. In most ESPs (Mailchimp, "
                "SendGrid, Postmark, etc.), go to Settings → Authentication → DKIM "
                "and follow the CNAME/TXT setup steps."
            ),
            "none": (
                "No DKIM signature found. Your emails aren't cryptographically signed, "
                "which hurts trust with receiving servers. Fix: Enable DKIM in your ESP's "
                "authentication settings and add the required DNS records (usually a "
                "CNAME or TXT at selector._domainkey.yourdomain.com)."
            ),
        },
        "dmarc": {
            "fail": (
                "DMARC failed — neither SPF nor DKIM aligned with your From domain. "
                "Fix: Ensure your SPF record includes your sending server AND your DKIM "
                "signing domain matches your From domain. Then publish a DMARC record: "
                "v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com at _dmarc.yourdomain.com."
            ),
            "none": (
                "No DMARC policy found. Without DMARC, anyone can spoof your domain and "
                "Gmail/Yahoo may deprioritize your mail. Fix: Add a TXT record at "
                "_dmarc.yourdomain.com with: v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com "
                "— start with p=none to monitor, then move to p=quarantine or p=reject."
            ),
        },
    }

    for proto in ("spf", "dkim", "dmarc"):
        verdict = auth.get(proto, {}).get("verdict", "none")
        detail = auth.get(proto, {}).get("detail")
        if verdict == "pass":
            status = "pass"
        elif verdict in ("fail", "softfail", "permerror"):
            status = "fail"
        else:
            status = "warning"

        # Add actionable recommendation for non-pass
        if status != "pass":
            fix = _auth_fix.get(proto, {}).get(verdict)
            if fix:
                detail = (detail + " | " if detail else "") + fix

        grades.append({
            "label": proto.upper(),
            "category": "Authentication",
            "status": status,
            "verdict": verdict,
            "detail": detail,
        })

    # ── TLS ──
    transport = headers.get("transport", {})
    tls_used = transport.get("tls_used")
    tls_ver = transport.get("tls_version", "none")
    tls_cipher = transport.get("tls_cipher", "")
    tls_status = "pass" if tls_used else "fail"
    tls_detail = f"{transport.get('hop_count', 0)} hop(s)"
    if not tls_used:
        tls_detail += (
            " | Your email was transmitted without TLS encryption, meaning it could "
            "be read in transit. Fix: Ensure your mail server or ESP supports STARTTLS "
            "(most modern ESPs do by default). If you run your own server, enable TLS in "
            "your MTA config (Postfix: smtpd_tls_security_level=may). Also consider "
            "publishing an MTA-STS policy to require TLS from senders."
        )
    elif tls_ver and "1.0" in tls_ver:
        tls_status = "warning"
        tls_detail += (
            " | TLS 1.0 is deprecated and considered insecure. Fix: Update your mail "
            "server to support TLS 1.2 or 1.3. Most ESPs already use TLS 1.2+."
        )
    elif tls_ver and "1.1" in tls_ver:
        tls_status = "warning"
        tls_detail += (
            " | TLS 1.1 is deprecated. Fix: Update your mail server to support "
            "TLS 1.2 or 1.3 for stronger encryption."
        )
    grades.append({
        "label": "TLS",
        "category": "Transport",
        "status": tls_status,
        "verdict": f"{tls_ver}" + (f" ({tls_cipher})" if tls_cipher else ""),
        "detail": tls_detail,
    })

    # ── From / Return-Path alignment ──
    identity = headers.get("identity", {})
    align_status = "pass" if identity.get("aligned") else "warning"
    from_dom = identity.get("from_domain", "?")
    rp_dom = identity.get("return_path_domain", "?")
    align_detail = f"From: {from_dom} / Return-Path: {rp_dom}"
    if not identity.get("aligned"):
        align_detail += (
            " | Your From domain and Return-Path (envelope sender) domain don't match. "
            "This can cause DMARC alignment failures. Fix: In your ESP settings, look for "
            "'Custom Return-Path' or 'Envelope Sender' and set it to match your From domain. "
            "In SendGrid, this is under Settings → Sender Authentication → Link Branding. "
            "In Mailchimp/Postmark/etc., enable custom domain authentication."
        )
    grades.append({
        "label": "Alignment",
        "category": "Identity",
        "status": align_status,
        "verdict": "From and Return-Path domains match" if identity.get("aligned") else "From and Return-Path domains differ",
        "detail": align_detail,
    })

    # ── List-Unsubscribe ──
    lu = headers.get("list_unsubscribe", {})
    lu_detail = None
    if lu.get("present"):
        if lu.get("one_click"):
            lu_status = "pass"
            lu_verdict = "Present with RFC 8058 one-click"
        elif lu.get("mailto") and lu.get("url"):
            lu_status = "pass"
            lu_verdict = "Present (mailto + URL)"
        elif lu.get("mailto") or lu.get("url"):
            lu_status = "warning"
            lu_verdict = "Present but missing " + ("URL" if lu.get("mailto") else "mailto")
            missing = "URL" if lu.get("mailto") else "mailto"
            lu_detail = (
                f"Your List-Unsubscribe header has a {('mailto' if lu.get('mailto') else 'URL')} "
                f"but is missing the {missing} component. Best practice is to include both. "
                "Also add a List-Unsubscribe-Post: List-Unsubscribe=One-Click header to "
                "support RFC 8058 one-click unsubscribe, which Gmail shows as a prominent "
                "button. Most ESPs add this automatically when you enable 'one-click unsubscribe'."
            )
        else:
            lu_status = "warning"
            lu_verdict = "Present but could not parse endpoints"
            lu_detail = (
                "The List-Unsubscribe header exists but we couldn't extract a valid mailto "
                "or URL from it. Check the header format — it should look like: "
                "List-Unsubscribe: <mailto:unsub@yourdomain.com>, <https://yourdomain.com/unsub>"
            )
    else:
        # Check if there's an unsubscribe link in the email body
        has_body_unsub = bool(re.search(
            r'(?i)(unsubscribe|opt[\s-]?out|manage\s+preferences|email\s+preferences)',
            body
        )) if body else False
        if has_body_unsub:
            lu_status = "warning"
            lu_verdict = "Header missing — body unsubscribe link found"
            lu_detail = (
                "Your email has an unsubscribe link in the body (good for CAN-SPAM), but "
                "is missing the List-Unsubscribe header that Gmail and Yahoo require for bulk "
                "senders since February 2024. Fix: Most ESPs add this header automatically — "
                "check your platform's settings:\n"
                "• Mailchimp: Enabled by default on authenticated domains\n"
                "• SendGrid: Settings → Tracking → Subscription Tracking → ON\n"
                "• Postmark: Automatic on broadcast Message Streams\n"
                "• ActiveCampaign/HubSpot/Klaviyo: Automatic when domain is authenticated\n"
                "• Kartra/Keap/GoHighLevel: Check Settings → Email → Authentication\n"
                "• Custom SMTP: Add headers manually — List-Unsubscribe: <mailto:unsub@yourdomain.com>, "
                "<https://yourdomain.com/unsub> and List-Unsubscribe-Post: List-Unsubscribe=One-Click"
            )
        else:
            lu_status = "fail"
            lu_verdict = "Not present — no header or body unsubscribe found"
            lu_detail = (
                "Your email has no unsubscribe mechanism at all. This violates CAN-SPAM law "
                "and Gmail/Yahoo's bulk sender requirements. Fix:\n"
                "1. Add a visible unsubscribe link in your email footer (required by CAN-SPAM)\n"
                "2. Add the List-Unsubscribe header (required by Gmail/Yahoo for 5,000+ daily sends)\n"
                "Most ESPs handle both automatically — enable domain authentication and "
                "subscription tracking in your platform's settings. If using custom SMTP, add: "
                "List-Unsubscribe: <mailto:unsub@yourdomain.com>, <https://yourdomain.com/unsub>"
            )
    grades.append({
        "label": "List-Unsubscribe",
        "category": "Compliance",
        "status": lu_status,
        "verdict": lu_verdict,
        "detail": lu_detail,
    })

    # ── DKIM Signature details ──
    dkim_sig = headers.get("dkim_signature", {})
    if dkim_sig.get("present"):
        algo = dkim_sig.get("algorithm") or "unknown"
        if "rsa-sha256" in algo.lower() or "ed25519" in algo.lower():
            dk_status = "pass"
        elif "rsa-sha1" in algo.lower():
            dk_status = "warning"
        else:
            dk_status = "pass"
        dk_detail = f"{len(dkim_sig.get('headers_signed', []))} headers signed"
        if dk_status == "warning":
            dk_detail += (
                " | rsa-sha1 is deprecated and some providers may reject it. "
                "Fix: Regenerate your DKIM key using rsa-sha256 (2048-bit) or ed25519. "
                "In your ESP, look for DKIM key rotation or regeneration in the "
                "authentication settings."
            )
        grades.append({
            "label": "DKIM Signature",
            "category": "Authentication",
            "status": dk_status,
            "verdict": f"Signed by {dkim_sig.get('domain', '?')} (s={dkim_sig.get('selector', '?')}, a={algo})",
            "detail": dk_detail,
        })
    else:
        grades.append({
            "label": "DKIM Signature",
            "category": "Authentication",
            "status": "fail",
            "verdict": "No DKIM signature found",
            "detail": (
                "Your email was not signed with DKIM. This means receiving servers can't verify "
                "the message hasn't been tampered with. Fix: Enable DKIM signing in your ESP "
                "and add the public key DNS records. Common setup locations:\n"
                "• Google Workspace: Admin → Apps → Gmail → Authenticate Email → Generate DKIM\n"
                "• Microsoft 365: Defender → Email auth → DKIM → Enable\n"
                "• SendGrid: Settings → Sender Authentication → Authenticate Domain\n"
                "• Mailchimp: Website → Domains → Authenticate\n"
                "• Custom servers: Generate a key pair with opendkim-genkey and publish the TXT record"
            ),
        })

    # ── MIME structure ──
    mime = headers.get("mime", {})
    if mime.get("has_html") and mime.get("has_plain_text"):
        mime_status = "pass"
        mime_verdict = "Multipart: HTML + plain text (best practice)"
        mime_detail = f"{mime.get('part_count', 0)} MIME part(s)"
    elif mime.get("has_html") and not mime.get("has_plain_text"):
        mime_status = "warning"
        mime_verdict = "HTML only — missing plain text alternative"
        mime_detail = (
            f"{mime.get('part_count', 0)} MIME part(s) | Emails should include both HTML and "
            "plain text versions (multipart/alternative). The plain text version is used by "
            "screen readers, Apple Watch, and some email clients. It also reduces spam risk. "
            "Fix: Most ESPs auto-generate a plain text part — check your 'Plain Text' or "
            "'Text Version' settings. If using custom SMTP, set Content-Type to "
            "multipart/alternative and include both text/plain and text/html parts."
        )
    elif mime.get("has_plain_text") and not mime.get("has_html"):
        mime_status = "pass"
        mime_verdict = "Plain text only"
        mime_detail = f"{mime.get('part_count', 0)} MIME part(s)"
    else:
        mime_status = "warning"
        mime_verdict = "Could not determine content structure"
        mime_detail = (
            f"{mime.get('part_count', 0)} MIME part(s) | We couldn't parse the MIME structure. "
            "Ensure your email has a proper Content-Type header (text/html, text/plain, or "
            "multipart/alternative)."
        )
    grades.append({
        "label": "MIME Structure",
        "category": "Content",
        "status": mime_status,
        "verdict": mime_verdict,
        "detail": mime_detail,
    })

    return grades
