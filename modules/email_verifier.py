"""
Email Verifier Module
=====================
Verifies if an email address is valid, deliverable, and safe to send to.

Performs syntax validation, domain checks, disposable/free provider detection,
MX record lookup, catch-all detection, and mailbox verification via raw SMTP.
"""

import re
import socket
import random
import string

import dns.resolver


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FREE_PROVIDERS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com",
    "icloud.com", "protonmail.com", "proton.me", "mail.com", "zoho.com",
    "yandex.com", "gmx.com", "gmx.net", "live.com", "msn.com",
    "inbox.com", "fastmail.com", "tutanota.com", "tuta.com", "hey.com",
    "me.com", "mac.com", "att.net", "sbcglobal.net", "bellsouth.net",
    "cox.net", "verizon.net", "comcast.net", "charter.net",
    "earthlink.net", "juno.com", "lycos.com", "rediffmail.com",
    "yahoo.co.uk", "yahoo.co.in", "yahoo.ca", "yahoo.com.au",
    "hotmail.co.uk", "outlook.co.uk", "live.co.uk",
    "gmail.co.uk",  # sometimes seen
    "mail.ru", "rambler.ru", "list.ru",
}

DISPOSABLE_DOMAINS = {
    # --- well-known disposable / temp-mail services (150+) ---
    "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
    "yopmail.com", "10minutemail.com", "trashmail.com", "sharklasers.com",
    "guerrillamailblock.com", "grr.la", "dispostable.com", "mailnesia.com",
    "maildrop.cc", "temp-mail.org", "fakeinbox.com", "emailondeck.com",
    "getnada.com", "burnermail.io", "mohmal.com", "minutemail.com",
    "tempr.email", "discard.email", "mailcatch.com", "tempail.com",
    "spam4.me", "harakirimail.com", "mailsac.com", "mytemp.email",
    "safetymail.info", "crazymailing.com",
    # additional domains
    "guerrillamail.info", "guerrillamail.net", "guerrillamail.org",
    "guerrillamail.de", "guerrillamailblock.com",
    "tempinbox.com", "tempmailaddress.com", "tmpmail.net", "tmpmail.org",
    "binkmail.com", "bobmail.info", "chammy.info", "devnullmail.com",
    "letthemeatspam.com", "mailexpire.com", "mailmoat.com", "mailnull.com",
    "mailshell.com", "mailzilla.com", "nomail.xl.cx", "nospam.ze.tc",
    "trashymail.com", "uggsrock.com", "spamfree24.org", "spamgourmet.com",
    "spamhereplease.com", "spamhole.com", "spaml.com", "spammotel.com",
    "spamspot.com", "spamthis.co.uk", "speed.1s.fr",
    "getairmail.com", "filzmail.com", "inboxalias.com",
    "jetable.org", "link2mail.net", "meltmail.com", "mt2015.com",
    "nospamfor.us", "objectmail.com", "owlpic.com",
    "proxymail.eu", "rcpt.at", "reallymymail.com",
    "recode.me", "regbypass.com", "safersignup.de",
    "saynotospams.com", "selfdestructingmail.com",
    "sendspamhere.com", "shiftmail.com", "skeefmail.com",
    "slaskpost.se", "sogetthis.com", "soodonims.com",
    "spambob.com", "spambob.net", "spambob.org",
    "spambog.com", "spambog.de", "spambog.ru",
    "spamcannon.com", "spamcannon.net", "spamcero.com",
    "spamcon.org", "spamcorptastic.com", "spamcowboy.com",
    "spamcowboy.net", "spamcowboy.org", "spamday.com",
    "spamex.com", "spamfighter.cf", "spamfighter.ga",
    "spamfighter.gq", "spamfighter.ml", "spamfighter.tk",
    "throwam.com", "tmail.ws", "tmailinator.com",
    "toiea.com", "trashmail.at", "trashmail.io",
    "trashmail.me", "trashmail.net", "trashmailer.com",
    "trbvm.com", "trbvn.com", "trickmail.net",
    "tafmail.com", "trash-mail.com", "trash-mail.de",
    "trashdevil.com", "trashdevil.de",
    "bugmenot.com", "bumpymail.com",
    "casualdx.com", "centermail.com", "centermail.net",
    "chogmail.com", "choicemail1.com", "clrmail.com",
    "cuvox.de", "dacoolest.com", "dandikmail.com",
    "dayrep.com", "dcemail.com", "deadaddress.com",
    "despam.it", "despammed.com", "devnullmail.com",
    "dfgh.net", "digitalsanctuary.com", "discardmail.com",
    "discardmail.de", "disposableaddress.com",
    "disposableemailaddresses.emailmiser.com",
    "disposableinbox.com", "dispose.it",
    "dodgeit.com", "dodgit.com", "dodgit.org",
    "dontreg.com", "dontsendmespam.de", "drdrb.com",
    "dump-email.info", "dumpandjunk.com", "dumpmail.de",
    "dumpyemail.com", "e4ward.com", "easytrashmail.com",
    "emailgo.de", "emailias.com", "emailigo.de",
    "emailinfive.com", "emailable.rocks", "emailmiser.com",
    "emailsensei.com", "emailtemporario.com.br",
    "emailwarden.com", "emailx.at.hm", "emailxfer.com",
    "emz.net", "enterto.com", "ephemail.net",
    "etranquil.com", "etranquil.net", "etranquil.org",
    "evopo.com", "explodemail.com", "express.net.ua",
    "eyepaste.com", "fastacura.com", "filzmail.com",
    "fixmail.tk", "flyspam.com",
}

# ---------------------------------------------------------------------------
# Spamtrap & honeypot patterns
# ---------------------------------------------------------------------------
# Known spamtrap local parts used by major blocklist operators and ISPs.
# These are addresses that were either never real or were recycled after
# prolonged inactivity.  Sending to them signals list-buying or poor hygiene.

SPAMTRAP_LOCAL_PARTS = {
    # Generic honeypot patterns
    "abuse", "spam", "spamtrap", "spam-trap", "honeypot", "honey-pot",
    "trap", "antispam", "anti-spam", "nospam", "no-spam", "junk",
    "spambox", "spamfighter", "spamkiller",
    # Postmaster / role addresses repurposed as traps
    "postmaster", "mailer-daemon", "noreply", "no-reply", "donotreply",
    "do-not-reply", "nobody", "devnull", "null", "void", "blackhole",
    # Common recycled-address patterns
    "test", "test1", "test123", "testing", "asdf", "qwerty",
    "aaa", "aaaa", "abc", "abcd", "1234", "123456",
    "sample", "example", "demo", "default", "temp", "tmp",
    "foo", "bar", "baz", "user", "admin", "root", "info",
    # Patterns used by Spamhaus, SURBL, Abusix, and ISP traps
    "spamhaus", "lashback", "spamcop",
}

# Domain-level spamtrap indicators — domains operated entirely as traps
SPAMTRAP_DOMAINS = {
    "spamtrap.email", "spamtraps.net", "trapmail.net", "honeypot.email",
    "trap.email", "spamtrap.io", "honeypots.email", "blackhole.email",
    "spamtrap.com", "trapzone.com", "project-honeypot.org",
    "lashback.com",  # Unsubscribe spamtrap operator
}

# Suspicious patterns in local part that suggest a spamtrap or seeded address
_SPAMTRAP_PATTERNS = [
    re.compile(r"^trap[.\-_]", re.IGNORECASE),
    re.compile(r"[.\-_]trap$", re.IGNORECASE),
    re.compile(r"^honey[.\-_]?pot", re.IGNORECASE),
    re.compile(r"^spam[.\-_]?trap", re.IGNORECASE),
    re.compile(r"^seed[.\-_]?\d", re.IGNORECASE),      # seed1, seed-2, etc.
    re.compile(r"^(?:test|fake|junk)[.\-_]\d+$", re.IGNORECASE),  # test.1, fake-23
]


def _check_spamtrap(local_part: str, domain: str) -> dict:
    """Check if an email looks like a spamtrap or honeypot.

    Returns dict with: is_spamtrap (bool), confidence (high/medium/low), detail (str).
    """
    local_lower = local_part.lower()

    # Domain-level traps — highest confidence
    if domain in SPAMTRAP_DOMAINS:
        return {
            "is_spamtrap": True,
            "confidence": "high",
            "detail": "Known spamtrap domain",
        }

    # Exact local part match
    if local_lower in SPAMTRAP_LOCAL_PARTS:
        return {
            "is_spamtrap": True,
            "confidence": "high",
            "detail": f"Known spamtrap address pattern: {local_lower}",
        }

    # Regex pattern match
    for pattern in _SPAMTRAP_PATTERNS:
        if pattern.search(local_lower):
            return {
                "is_spamtrap": True,
                "confidence": "medium",
                "detail": f"Address matches spamtrap pattern: {local_lower}",
            }

    # All-numeric local parts (common recycled traps)
    if re.match(r"^\d{5,}$", local_lower):
        return {
            "is_spamtrap": True,
            "confidence": "low",
            "detail": "All-numeric address — commonly recycled as spamtrap",
        }

    return {
        "is_spamtrap": False,
        "confidence": "none",
        "detail": "No spamtrap indicators detected",
    }


EHLO_HOSTNAME = "inbxr.com"
SMTP_TIMEOUT = 10  # seconds
VERIFY_FROM = "verify@inbxr.com"

# Email syntax regex — RFC-5321 simplified
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_response(sock: socket.socket) -> tuple[int, str]:
    """Read a full SMTP response, handling multi-line replies.

    Returns (code, full_text).  Returns (0, error_message) on failure.
    """
    data = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            # SMTP multi-line: "250-..." continues, "250 ..." is final
            lines = data.decode("utf-8", errors="replace").splitlines()
            if lines and len(lines[-1]) >= 4 and lines[-1][3:4] == " ":
                break
    except (socket.timeout, OSError) as exc:
        return 0, str(exc)

    text = data.decode("utf-8", errors="replace").strip()
    try:
        code = int(text[:3])
    except (ValueError, IndexError):
        code = 0
    return code, text


def _send_command(sock: socket.socket, command: str) -> tuple[int, str]:
    """Send an SMTP command and return the response."""
    try:
        sock.sendall((command + "\r\n").encode())
    except (socket.timeout, OSError) as exc:
        return 0, str(exc)
    return _read_response(sock)


def _random_local_part(length: int = 20) -> str:
    chars = string.ascii_lowercase + string.digits
    return "inbxr-test-" + "".join(random.choices(chars, k=length))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_email(email: str) -> dict:
    """Verify an email address and return a detailed result dictionary.

    Checks performed in order:
      1. Syntax validation
      2. Domain extraction
      3. Free-provider detection
      4. Disposable-domain detection
      5. MX record lookup (with A-record fallback)
      6. Catch-all detection via SMTP
      7. Mailbox existence verification via SMTP

    Parameters
    ----------
    email : str
        The email address to verify.

    Returns
    -------
    dict
        A result dictionary with keys: email, domain, valid_syntax, checks,
        verdict, verdict_detail, risk_factors, score.
    """

    result: dict = {
        "email": email.strip(),
        "domain": "",
        "valid_syntax": False,
        "checks": {
            "syntax": {"pass": False, "detail": ""},
            "domain": {"pass": False, "detail": ""},
            "mx_records": [],
            "disposable": {"pass": True, "is_disposable": False, "detail": ""},
            "spamtrap": {"is_spamtrap": False, "confidence": "none", "detail": "Not checked"},
            "free_provider": {"is_free": False, "detail": ""},
            "catch_all": {"is_catch_all": False, "detail": "Not checked"},
            "mailbox": {"exists": None, "detail": "Not checked", "smtp_code": None},
        },
        "verdict": "unknown",
        "verdict_detail": "",
        "risk_factors": [],
        "score": 100,
    }

    email = email.strip()

    # ------------------------------------------------------------------
    # 1. Syntax check
    # ------------------------------------------------------------------
    if not _EMAIL_RE.match(email):
        result["checks"]["syntax"] = {"pass": False, "detail": "Invalid email format"}
        result["valid_syntax"] = False
        result["score"] = 0
        result["verdict"] = "invalid"
        result["verdict_detail"] = "Email address has invalid syntax"
        return result

    result["checks"]["syntax"] = {"pass": True, "detail": "Valid email format"}
    result["valid_syntax"] = True

    # ------------------------------------------------------------------
    # 2. Extract domain
    # ------------------------------------------------------------------
    domain = email.rsplit("@", 1)[1].lower()
    result["domain"] = domain

    # ------------------------------------------------------------------
    # 3. Free provider detection
    # ------------------------------------------------------------------
    if domain in FREE_PROVIDERS:
        result["checks"]["free_provider"] = {
            "is_free": True,
            "detail": "Free email provider",
        }
        result["score"] -= 5
    else:
        result["checks"]["free_provider"] = {
            "is_free": False,
            "detail": "Business domain",
        }

    # ------------------------------------------------------------------
    # 4. Disposable domain detection
    # ------------------------------------------------------------------
    if domain in DISPOSABLE_DOMAINS:
        result["checks"]["disposable"] = {
            "pass": False,
            "is_disposable": True,
            "detail": "Disposable / temporary email domain",
        }
        result["risk_factors"].append("disposable_domain")
        result["score"] -= 40
    else:
        result["checks"]["disposable"] = {
            "pass": True,
            "is_disposable": False,
            "detail": "Not a disposable domain",
        }

    # ------------------------------------------------------------------
    # 5. Spamtrap detection
    # ------------------------------------------------------------------
    local_part = email.rsplit("@", 1)[0]
    spamtrap = _check_spamtrap(local_part, domain)
    result["checks"]["spamtrap"] = spamtrap

    if spamtrap["is_spamtrap"]:
        result["risk_factors"].append("spamtrap")
        if spamtrap["confidence"] == "high":
            result["score"] -= 50
        elif spamtrap["confidence"] == "medium":
            result["score"] -= 30
        else:
            result["score"] -= 15

    # ------------------------------------------------------------------
    # 6. MX record lookup
    # ------------------------------------------------------------------
    mx_hosts: list[tuple[int, str]] = []  # (priority, host)

    try:
        answers = dns.resolver.resolve(domain, "MX")
        for rdata in answers:
            host = str(rdata.exchange).rstrip(".")
            mx_hosts.append((rdata.preference, host))
        mx_hosts.sort(key=lambda x: x[0])
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
            dns.resolver.NoNameservers, dns.exception.Timeout,
            Exception):
        mx_hosts = []

    # A-record fallback
    if not mx_hosts:
        try:
            dns.resolver.resolve(domain, "A")
            # Domain itself can accept mail
            mx_hosts = [(0, domain)]
        except Exception:
            pass

    if mx_hosts:
        result["checks"]["mx_records"] = [
            {"priority": p, "host": h} for p, h in mx_hosts
        ]
        result["checks"]["domain"] = {
            "pass": True,
            "detail": "Domain exists with MX records",
        }
    else:
        result["checks"]["mx_records"] = []
        result["checks"]["domain"] = {
            "pass": False,
            "detail": "No MX or A records found for domain",
        }
        result["score"] = max(result["score"] - 100, 0)
        result["verdict"] = "invalid"
        result["verdict_detail"] = "Domain has no mail server records"
        return result

    # ------------------------------------------------------------------
    # 7 & 8. Catch-all detection + Mailbox verification (single session)
    # ------------------------------------------------------------------
    mx_host = mx_hosts[0][1]
    sock = None
    catch_all_checked = False
    mailbox_checked = False

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SMTP_TIMEOUT)
        sock.connect((mx_host, 25))

        # Read banner
        code, text = _read_response(sock)
        if code == 0:
            raise ConnectionError(f"No SMTP banner: {text}")

        # EHLO
        code, text = _send_command(sock, f"EHLO {EHLO_HOSTNAME}")
        if code == 0:
            # Try HELO as fallback
            code, text = _send_command(sock, f"HELO {EHLO_HOSTNAME}")

        # MAIL FROM
        code, text = _send_command(sock, f"MAIL FROM:<{VERIFY_FROM}>")
        if code < 200 or code >= 300:
            raise ConnectionError(f"MAIL FROM rejected ({code}): {text}")

        # ---- Catch-all check ----
        random_addr = f"{_random_local_part()}@{domain}"
        code, text = _send_command(sock, f"RCPT TO:<{random_addr}>")
        catch_all_checked = True

        if 200 <= code < 300:
            result["checks"]["catch_all"] = {
                "is_catch_all": True,
                "detail": "Server accepts unknown recipients (catch-all)",
            }
            result["risk_factors"].append("catch_all")
            result["score"] -= 20
        elif 400 <= code < 500:
            # Greylisting on random address — inconclusive for catch-all
            result["checks"]["catch_all"] = {
                "is_catch_all": False,
                "detail": "Greylisted on random probe; catch-all status inconclusive",
            }
        else:
            result["checks"]["catch_all"] = {
                "is_catch_all": False,
                "detail": "Server rejects unknown recipients",
            }

        # We need a fresh MAIL FROM for the real RCPT TO because some
        # servers only allow one RCPT per transaction, or the previous
        # RCPT rejection may taint the session.  Issue RSET first.
        _send_command(sock, "RSET")
        code, text = _send_command(sock, f"MAIL FROM:<{VERIFY_FROM}>")
        if code < 200 or code >= 300:
            raise ConnectionError(f"MAIL FROM rejected after RSET ({code})")

        # ---- Mailbox verification ----
        code, text = _send_command(sock, f"RCPT TO:<{email}>")
        mailbox_checked = True

        if 200 <= code < 300:
            result["checks"]["mailbox"] = {
                "exists": True,
                "detail": "Mailbox exists",
                "smtp_code": code,
            }
        elif code in (550, 551, 552, 553):
            result["checks"]["mailbox"] = {
                "exists": False,
                "detail": "Mailbox does not exist",
                "smtp_code": code,
            }
            result["score"] = max(result["score"] - 80, 0)
        elif 450 <= code <= 452:
            result["checks"]["mailbox"] = {
                "exists": None,
                "detail": "Temporarily unavailable (greylisting)",
                "smtp_code": code,
            }
            result["risk_factors"].append("greylisted")
            result["score"] -= 10
        else:
            result["checks"]["mailbox"] = {
                "exists": None,
                "detail": f"Unexpected SMTP response ({code})",
                "smtp_code": code,
            }

    except (socket.timeout, socket.gaierror, ConnectionError, OSError) as exc:
        error_detail = f"SMTP connection failed: {exc}"
        if not catch_all_checked:
            result["checks"]["catch_all"] = {
                "is_catch_all": False,
                "detail": error_detail,
            }
        if not mailbox_checked:
            result["checks"]["mailbox"] = {
                "exists": None,
                "detail": error_detail,
                "smtp_code": None,
            }
    finally:
        if sock is not None:
            try:
                _send_command(sock, "QUIT")
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Clamp score
    # ------------------------------------------------------------------
    result["score"] = max(result["score"], 0)

    # ------------------------------------------------------------------
    # Verdict
    # ------------------------------------------------------------------
    mailbox = result["checks"]["mailbox"]
    disposable = result["checks"]["disposable"]["is_disposable"]
    spamtrap_hit = result["checks"]["spamtrap"]["is_spamtrap"]
    spamtrap_conf = result["checks"]["spamtrap"]["confidence"]
    catch_all = result["checks"]["catch_all"]["is_catch_all"]
    greylisted = "greylisted" in result.get("risk_factors", [])

    if mailbox.get("smtp_code") in (550, 551, 552, 553):
        result["verdict"] = "invalid"
        result["verdict_detail"] = "Mailbox does not exist on the server"
    elif spamtrap_hit and spamtrap_conf == "high":
        result["verdict"] = "risky"
        result["verdict_detail"] = f"Likely spamtrap — {result['checks']['spamtrap']['detail']}"
    elif disposable:
        result["verdict"] = "risky"
        result["verdict_detail"] = "Disposable / temporary email domain"
    elif spamtrap_hit:
        result["verdict"] = "risky"
        result["verdict_detail"] = f"Possible spamtrap — {result['checks']['spamtrap']['detail']}"
    elif catch_all and mailbox.get("exists") is not False:
        result["verdict"] = "risky"
        result["verdict_detail"] = (
            "Domain is catch-all; individual mailbox cannot be confirmed"
        )
    elif greylisted:
        result["verdict"] = "risky"
        result["verdict_detail"] = "Server temporarily rejected the request (greylisting)"
    elif mailbox.get("exists") is True:
        result["verdict"] = "valid"
        result["verdict_detail"] = "Email address is valid and deliverable"
    elif mailbox.get("exists") is None and mailbox.get("smtp_code") is None:
        result["verdict"] = "unknown"
        result["verdict_detail"] = "Could not connect to mail server to verify"
    else:
        result["verdict"] = "unknown"
        result["verdict_detail"] = "Verification inconclusive"

    return result
