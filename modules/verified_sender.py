"""
InbXr — Verified Sender Certification
──────────────────────────────────────
Annual certification product. Brands pay $99-499/year to display
an InbXr Verified Sender badge on their website, footer, or email
signature. The badge links back to inbxr.us/verified/<domain>
where visitors can see the certification details.

Rules:
    - Certification requires a current Signal Score of 80+ (Grade B+)
    - Certifications last 365 days from the date of purchase
    - Re-certification requires the domain still scores 80+ at renewal
    - If the domain drops below 80 during the year, certification
      stays active until expiry (graceful, not punitive)
    - Badge clicks are tracked so the user can prove ROI

Tiers:
    standard  $99/yr   Basic badge, self-service
    pro       $299/yr  Priority review, custom copy on the /verified page
    elite     $499/yr  White-glove support, annual review call, press kit

V3 ships the infrastructure. Actual billing integration (Stripe
subscription + automated renewal) lands in V4 when there's customer
demand to justify the work. For now certification is manual-grant
via the admin panel or direct DB insert.
"""

import logging
from datetime import datetime, timedelta

from modules.database import execute, fetchone, fetchall

logger = logging.getLogger(__name__)

MIN_CERT_SCORE = 80

TIER_PRICING = {
    "standard": {"label": "Standard", "price_usd": 99, "features": [
        "InbXr Verified Sender badge",
        "Annual re-verification",
        "Public /verified/<domain> listing page",
        "Badge click tracking",
    ]},
    "pro": {"label": "Pro", "price_usd": 299, "features": [
        "Everything in Standard",
        "Priority score review within 24 hours",
        "Custom description on your listing page",
        "Quarterly re-verification report",
        "Featured in annual State of Email Deliverability",
    ]},
    "elite": {"label": "Elite", "price_usd": 499, "features": [
        "Everything in Pro",
        "Annual review call with the InbXr team",
        "Press kit with embeddable badge variants",
        "Your logo on the /verified-sender landing page",
        "White-glove certification support",
    ]},
}


def _normalize(domain):
    if not domain:
        return ""
    return str(domain).strip().lower().replace("https://", "").replace("http://", "").split("/")[0]


def get_certification(domain):
    """Return the verified_senders row for a domain, or None."""
    clean = _normalize(domain)
    if not clean:
        return None
    return fetchone(
        "SELECT * FROM verified_senders WHERE domain = ?",
        (clean,),
    )


def is_certified(domain):
    """True if the domain has an active, non-expired certification."""
    cert = get_certification(domain)
    if not cert:
        return False
    if cert["status"] != "active":
        return False
    # Check expiry
    try:
        expires = datetime.fromisoformat(cert["expires_at"])
        if expires < datetime.utcnow():
            return False
    except Exception:
        pass
    return True


def certify_domain(user_id, domain, tier="standard"):
    """Issue a certification for a domain. Verifies the domain currently
    scores 80+ before certifying. Returns (ok: bool, result: dict)."""
    clean = _normalize(domain)
    if not clean or "." not in clean:
        return False, {"ok": False, "error": "Invalid domain."}

    if tier not in TIER_PRICING:
        return False, {"ok": False, "error": f"Invalid tier: {tier}"}

    # Check current score
    try:
        from modules.signal_score import calculate_domain_signal_score
        score_result = calculate_domain_signal_score(clean)
    except Exception:
        logger.exception("[VERIFIED] score check failed")
        return False, {"ok": False, "error": "Could not verify current score. Try again."}

    if score_result.get("error"):
        return False, {"ok": False, "error": score_result.get("message", "Scoring failed.")}

    current_score = score_result.get("total_signal_score", 0)
    current_grade = score_result.get("signal_grade", "F")

    if current_score < MIN_CERT_SCORE:
        return False, {
            "ok": False,
            "error": (
                f"Your current Signal Score is {current_score} ({current_grade}). "
                f"Certification requires {MIN_CERT_SCORE}+ (Grade B or better). "
                "Fix the flagged signals first, then return to certify."
            ),
            "code": "score_too_low",
            "current_score": current_score,
            "required_score": MIN_CERT_SCORE,
        }

    # Insert or update the certification
    fee = TIER_PRICING[tier]["price_usd"]
    try:
        execute(
            """INSERT INTO verified_senders
                (user_id, domain, tier, annual_fee_usd, last_verified_score, last_verified_grade,
                 certified_at, expires_at, status)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now', '+365 days'), 'active')
               ON CONFLICT(domain) DO UPDATE SET
                 user_id = excluded.user_id,
                 tier = excluded.tier,
                 annual_fee_usd = excluded.annual_fee_usd,
                 last_verified_score = excluded.last_verified_score,
                 last_verified_grade = excluded.last_verified_grade,
                 certified_at = datetime('now'),
                 expires_at = datetime('now', '+365 days'),
                 status = 'active',
                 updated_at = datetime('now')
            """,
            (user_id, clean, tier, fee, int(current_score), current_grade),
        )
    except Exception:
        logger.exception("[VERIFIED] certify insert failed")
        return False, {"ok": False, "error": "Certification failed. Please try again."}

    return True, {
        "ok": True,
        "domain": clean,
        "tier": tier,
        "tier_label": TIER_PRICING[tier]["label"],
        "annual_fee": fee,
        "score": int(current_score),
        "grade": current_grade,
        "expires_in_days": 365,
    }


def increment_badge_clicks(domain):
    """Bump the badge click counter. Called every time the badge SVG
    is served. Best-effort; swallows errors since this must not block
    the badge response."""
    clean = _normalize(domain)
    if not clean:
        return
    try:
        execute(
            "UPDATE verified_senders SET badge_clicks = badge_clicks + 1, "
            "updated_at = datetime('now') WHERE domain = ? AND status = 'active'",
            (clean,),
        )
    except Exception:
        pass  # silent — click tracking is not critical


def get_all_verified(limit=100):
    """Public list of currently verified senders. Used by the
    /verified-sender landing page and the annual report."""
    return fetchall(
        "SELECT domain, tier, last_verified_score, last_verified_grade, "
        "certified_at, expires_at "
        "FROM verified_senders WHERE status = 'active' "
        "AND expires_at > datetime('now') "
        "ORDER BY tier DESC, last_verified_score DESC LIMIT ?",
        (limit,),
    )
