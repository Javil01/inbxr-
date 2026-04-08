"""
InbXr — Inherited List First Aid
────────────────────────────────
Takes an uploaded CSV of contacts and classifies each row into one of
three buckets that map directly to action:

    REMOVE     — delete these now. They are damaging your sender reputation.
                 (hard bounces, role addresses, disposable domains, severely
                  dormant contacts, obviously invalid syntax)

    REENGAGE   — send a recovery sequence first. Only delete if the sequence
                 fails to get a response. These are borderline and worth
                 trying to save because they may still convert.
                 (at-risk dormant, moderately stale, weak-signal acquisition)

    KEEP       — your active core. Protect these. Do not touch.
                 (recent engagement, clean syntax, no risk flags)

The triage output is a structured dict that the /inherited-list-first-aid
route renders as a 3-column report the user can screenshot, export, or
act on directly. Remove lists can be exported as a suppression CSV that
drops straight into any ESP.

This is a content-agnostic diagnostic. It does not call any ESP API. It
operates entirely on the CSV the user gave us, which means it works for
any list from any source, including lists the user inherited from
someone else and has no ESP access to.
"""

import csv
import io
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ── Classification rules ────────────────────────────────
#
# Each rule returns a tuple: (bucket, reason_code, reason_label). The
# first rule that fires wins, so more severe rules are checked first.
# Reason labels are user-facing; reason codes are stable identifiers
# the UI can group on.

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

_ROLE_PREFIXES = {
    "info", "admin", "administrator", "sales", "support", "contact",
    "hello", "help", "service", "webmaster", "postmaster", "noreply",
    "no-reply", "mail", "mailer-daemon", "root", "abuse", "billing",
    "hostmaster", "office", "team", "feedback", "privacy", "legal",
    "marketing", "press", "jobs", "careers", "recruiting",
}

_DISPOSABLE_DOMAINS = {
    # Top offenders, not exhaustive — the engine flags these as-is and
    # a future revision can swap in a live disposable-domain list.
    "mailinator.com", "10minutemail.com", "guerrillamail.com",
    "throwaway.email", "tempmail.com", "temp-mail.org", "yopmail.com",
    "fakeinbox.com", "trashmail.com", "dispostable.com", "sharklasers.com",
    "mintemail.com", "maildrop.cc", "spam4.me", "getnada.com", "getairmail.com",
    "emailondeck.com", "mohmal.com", "mailcatch.com", "moakt.com",
    "burnermail.io", "temp-mail.io",
}

# Days since last engagement thresholds
_DORMANT_DAYS = 180
_SEVERE_DORMANT_DAYS = 365
_AT_RISK_DAYS = 91
_ACTIVE_DAYS = 30


def _now():
    return datetime.utcnow()


def _days_since(dt):
    """Days since an ISO datetime string or None."""
    if not dt:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
        except Exception:
            return None
    if not isinstance(dt, datetime):
        return None
    return (_now() - dt).days


def _last_engagement_days(contact):
    """Most recent engagement signal (open, click, reply) → days ago.
    Returns None if no engagement signal found."""
    candidates = []
    for key in ("last_open_date", "last_click_date", "last_reply_date"):
        d = _days_since(contact.get(key))
        if d is not None and d >= 0:
            candidates.append(d)
    return min(candidates) if candidates else None


def _is_role_address(email):
    local = email.split("@", 1)[0].lower().strip()
    return local in _ROLE_PREFIXES


def _is_disposable(email):
    domain = email.split("@", 1)[1].lower().strip()
    return domain in _DISPOSABLE_DOMAINS


def _is_valid_syntax(email):
    return bool(_EMAIL_RE.match(email))


def _classify(contact):
    """Apply the rule cascade. Return (bucket, reason_code, reason_label)."""
    email = (contact.get("email") or "").strip().lower()

    if not email or not _is_valid_syntax(email):
        return ("remove", "invalid_syntax", "Invalid email syntax")

    if contact.get("is_hard_bounce"):
        return ("remove", "hard_bounce", "Previously hard bounced")

    if _is_disposable(email):
        return ("remove", "disposable", "Disposable / temporary email domain")

    if _is_role_address(email):
        return ("remove", "role_address", "Role address (info@, admin@, etc.)")

    engagement_days = _last_engagement_days(contact)

    if engagement_days is not None and engagement_days >= _SEVERE_DORMANT_DAYS:
        return ("remove", "severe_dormant", f"No engagement in {engagement_days}+ days")

    if engagement_days is None:
        # Contact has never engaged at all — dangerous on an inherited list
        # because we can't distinguish a never-mailed contact from one that
        # has been mailed and ignored. Treat as reengage candidate.
        return ("reengage", "no_engagement_signal", "No engagement signal on record")

    if engagement_days >= _DORMANT_DAYS:
        return ("reengage", "dormant", f"Last engaged {engagement_days} days ago")

    if engagement_days >= _AT_RISK_DAYS:
        return ("reengage", "at_risk", f"Engaged {engagement_days} days ago, at risk of decay")

    if contact.get("is_catch_all"):
        return ("reengage", "catch_all", "Catch-all domain (delivery is probabilistic)")

    # Recent engagement = keep
    return ("keep", "recent_engagement", f"Engaged {engagement_days} days ago")


# ── CSV parsing ─────────────────────────────────────────


def _parse_date(value):
    """Parse a date field in a few common formats. Returns datetime or None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _find_csv_column(row, concept):
    """Match flexible CSV column names to the fields we care about."""
    aliases = {
        "email": ["email", "email_address", "e-mail", "mail"],
        "last_open_date": [
            "last_open", "last_opened", "last_open_date", "last_open_at",
            "last open date", "opened_at",
        ],
        "last_click_date": [
            "last_click", "last_clicked", "last_click_date", "last_click_at",
            "last click date", "clicked_at",
        ],
        "last_reply_date": [
            "last_reply", "last_replied", "last_reply_date", "replied_at",
        ],
        "acquisition_date": [
            "acquisition_date", "date_added", "signup_date", "joined",
            "created_at", "added_at", "signed_up",
        ],
    }
    wanted = aliases.get(concept, [concept])
    # Build a lowercase-stripped lookup of the row
    norm = {(k or "").strip().lower().replace(" ", "_"): v for k, v in row.items()}
    for alias in wanted:
        key = alias.lower().replace(" ", "_")
        if key in norm and norm[key] not in (None, ""):
            return norm[key]
    return None


def parse_csv_for_triage(csv_content):
    """Parse an uploaded CSV into normalized contact dicts ready for
    classification. Returns (contacts, skipped_count)."""
    try:
        reader = csv.DictReader(io.StringIO(csv_content))
    except Exception:
        logger.exception("[LIST_TRIAGE] CSV parse failed")
        return [], 0

    contacts = []
    skipped = 0

    for row in reader:
        email = _find_csv_column(row, "email")
        if not email or "@" not in str(email):
            skipped += 1
            continue

        contact = {
            "email": str(email).strip().lower(),
            "last_open_date": _parse_date(_find_csv_column(row, "last_open_date")),
            "last_click_date": _parse_date(_find_csv_column(row, "last_click_date")),
            "last_reply_date": _parse_date(_find_csv_column(row, "last_reply_date")),
            "acquisition_date": _parse_date(_find_csv_column(row, "acquisition_date")),
            "is_hard_bounce": False,
            "is_catch_all": False,
        }
        contacts.append(contact)

    return contacts, skipped


# ── Main triage entry point ─────────────────────────────


def triage_list(csv_content):
    """Parse CSV + classify every contact + return a structured triage
    report. Safe to call directly from a route handler on user-uploaded
    content. Size caps are enforced upstream.
    """
    contacts, skipped_invalid = parse_csv_for_triage(csv_content)

    if not contacts:
        return {
            "ok": False,
            "error": "no_contacts",
            "message": "We could not find any valid email addresses in your CSV. Make sure the file has an 'email' column.",
        }

    buckets = {"remove": [], "reengage": [], "keep": []}
    reason_counts = {}

    for contact in contacts:
        bucket, code, label = _classify(contact)
        buckets[bucket].append({
            "email": contact["email"],
            "reason_code": code,
            "reason_label": label,
        })
        reason_counts[code] = reason_counts.get(code, 0) + 1

    total = len(contacts)
    remove_n = len(buckets["remove"])
    reengage_n = len(buckets["reengage"])
    keep_n = len(buckets["keep"])

    # Headline per bucket — the one-liner summary
    remove_summary = _bucket_summary("remove", buckets["remove"])
    reengage_summary = _bucket_summary("reengage", buckets["reengage"])
    keep_summary = _bucket_summary("keep", buckets["keep"])

    return {
        "ok": True,
        "total_parsed": total,
        "skipped_invalid": skipped_invalid,
        "counts": {
            "remove": remove_n,
            "reengage": reengage_n,
            "keep": keep_n,
        },
        "percentages": {
            "remove": round(remove_n / total * 100, 1) if total else 0,
            "reengage": round(reengage_n / total * 100, 1) if total else 0,
            "keep": round(keep_n / total * 100, 1) if total else 0,
        },
        "summaries": {
            "remove": remove_summary,
            "reengage": reengage_summary,
            "keep": keep_summary,
        },
        # Cap the preview lists so the JSON response is reasonably sized.
        # Full lists are available via the suppression export route.
        "preview": {
            "remove": buckets["remove"][:50],
            "reengage": buckets["reengage"][:50],
            "keep": buckets["keep"][:50],
        },
        "reason_counts": reason_counts,
        # Raw bucketed lists so the suppression-export route can use them
        # without re-running the classifier.
        "_full_buckets": buckets,
    }


def _bucket_summary(bucket_name, contacts):
    """Human-readable summary for a bucket based on dominant reason."""
    if not contacts:
        return "Nothing matched this bucket."

    # Find dominant reason
    counts = {}
    for c in contacts:
        code = c.get("reason_code", "unknown")
        counts[code] = counts.get(code, 0) + 1

    dominant = max(counts.items(), key=lambda x: x[1])[0]

    headlines = {
        "remove": {
            "hard_bounce": "These contacts have already bounced. Keeping them will damage your sender reputation on the next send.",
            "disposable": "These contacts are on throwaway email domains. They will never engage.",
            "role_address": "These are role addresses (info@, admin@). They are typically spam-trap bait.",
            "severe_dormant": "These contacts have not engaged in over a year. The spam trap risk is high.",
            "invalid_syntax": "These addresses are malformed. They will bounce or fail delivery.",
        },
        "reengage": {
            "no_engagement_signal": "These contacts have no engagement history. Send one re-engagement email and remove if no response.",
            "dormant": "These contacts stopped engaging in the last 180 to 365 days. A well-crafted recovery sequence can win them back.",
            "at_risk": "These contacts are sliding toward dormancy. Intervene now before they cross into the remove bucket.",
            "catch_all": "Catch-all domain contacts. Delivery is probabilistic. Test with a smaller send first.",
        },
        "keep": {
            "recent_engagement": "Your active core. Protect these contacts. Send to them at your normal cadence.",
        },
    }

    return headlines.get(bucket_name, {}).get(
        dominant,
        f"{len(contacts)} contacts in this bucket.",
    )


# ── Suppression CSV export ──────────────────────────────


def build_suppression_csv(remove_contacts):
    """Produce a CSV of the remove bucket that drops straight into any
    ESP as a suppression import. Two columns: email, reason."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "reason"])
    for c in remove_contacts:
        writer.writerow([c["email"], c["reason_label"]])
    return buf.getvalue()
