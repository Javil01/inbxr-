"""
InbXr — AppSumo LTD Redeem Flow
───────────────────────────────
Manages the AppSumo lifetime deal funnel. Separate from MRR:

    AppSumo buyers land on /appsumo, redeem their code(s), get lifetime
    Toolkit access. They can then optionally add Intelligence (the MRR
    subscription) on top without losing their lifetime Toolkit.

Tier structure based on stacked codes:

    T1  1 code   $59  5 domains   10 CSV scans/month   PDF basic
    T2  2 codes  $118 15 domains  50 CSV scans/month   PDF + 3 seats
    T3  3 codes  $199 50 domains  Unlimited scans      PDF white-label + 10 clients

The tier is derived at read time from COUNT(*) of appsumo_codes rows
where redeemed_by_user_id = user.id. The users.toolkit_tier_level
column caches this for fast reads on every page load.

When a user redeems a code:
  1. Validate the code exists and is unredeemed
  2. Mark it redeemed by this user
  3. Recalculate their toolkit_tier_level
  4. Set toolkit_ok = 1

When a user disconnects (future feature):
  1. Unmark the code
  2. Recalculate the tier level
  3. If 0 codes remain, set toolkit_ok = 0

Codes are imported from an AppSumo-provided CSV via the admin panel
(or a direct DB insert). Each code is a 12-character alphanumeric
string that AppSumo generates on their end.
"""

import logging
import re
from modules.database import fetchone, fetchall, execute

logger = logging.getLogger(__name__)


# ── Tier capacity table ─────────────────────────────────


TOOLKIT_TIERS = {
    0: {
        "label": "None",
        "price_usd": 0,
        "domains_monitored": 0,
        "csv_scans_per_month": 0,
        "pdf_white_label": False,
        "max_client_slots": 0,
        "team_seats": 1,
    },
    1: {
        "label": "Toolkit T1",
        "price_usd": 59,
        "domains_monitored": 5,
        "csv_scans_per_month": 10,
        "pdf_white_label": False,
        "max_client_slots": 0,
        "team_seats": 1,
    },
    2: {
        "label": "Toolkit T2",
        "price_usd": 118,
        "domains_monitored": 15,
        "csv_scans_per_month": 50,
        "pdf_white_label": False,
        "max_client_slots": 0,
        "team_seats": 3,
    },
    3: {
        "label": "Toolkit T3",
        "price_usd": 199,
        "domains_monitored": 50,
        "csv_scans_per_month": 9999,
        "pdf_white_label": True,
        "max_client_slots": 10,
        "team_seats": 5,
    },
}


def get_toolkit_tier(level):
    """Look up the capacity table for a level (0-3)."""
    return TOOLKIT_TIERS.get(max(0, min(3, level or 0)))


# ── Code helpers ────────────────────────────────────────


_CODE_RE = re.compile(r"^[A-Z0-9\-]{6,32}$")


def _normalize_code(code):
    if not code:
        return ""
    return str(code).strip().upper()


def code_exists(code):
    """Check if an unredeemed code exists."""
    clean = _normalize_code(code)
    if not clean:
        return False
    row = fetchone(
        "SELECT id, redeemed_by_user_id FROM appsumo_codes WHERE code = ?",
        (clean,),
    )
    return row is not None


def code_is_available(code):
    """True if the code exists AND has not been redeemed yet."""
    clean = _normalize_code(code)
    if not clean:
        return False
    row = fetchone(
        "SELECT id, redeemed_by_user_id FROM appsumo_codes WHERE code = ?",
        (clean,),
    )
    if not row:
        return False
    return row["redeemed_by_user_id"] is None


def get_user_code_count(user_id):
    """How many codes has this user stacked?"""
    row = fetchone(
        "SELECT COUNT(*) AS n FROM appsumo_codes WHERE redeemed_by_user_id = ?",
        (user_id,),
    )
    return row["n"] if row else 0


def get_user_codes(user_id):
    """Return all codes redeemed by this user with timestamps."""
    return fetchall(
        "SELECT code, batch_label, redeemed_at FROM appsumo_codes "
        "WHERE redeemed_by_user_id = ? ORDER BY redeemed_at",
        (user_id,),
    )


# ── Redeem flow ─────────────────────────────────────────


def redeem_code(user_id, code):
    """Redeem an AppSumo code for a user. Returns (ok: bool, result: dict).

    On success: result = {'ok': True, 'tier_level': N, 'tier_label': '...', 'codes_stacked': N}
    On failure: result = {'ok': False, 'error': '...'}
    """
    clean = _normalize_code(code)
    if not clean or not _CODE_RE.match(clean):
        return False, {"ok": False, "error": "Code format looks wrong. AppSumo codes are letters and numbers only."}

    row = fetchone(
        "SELECT id, code, redeemed_by_user_id FROM appsumo_codes WHERE code = ?",
        (clean,),
    )
    if not row:
        return False, {"ok": False, "error": "We don't recognize that code. Double-check and try again."}

    if row["redeemed_by_user_id"] is not None:
        if row["redeemed_by_user_id"] == user_id:
            return False, {"ok": False, "error": "You've already redeemed this code."}
        return False, {"ok": False, "error": "This code has already been redeemed by another account."}

    # Mark redeemed
    try:
        execute(
            "UPDATE appsumo_codes SET redeemed_by_user_id = ?, "
            "redeemed_at = datetime('now') WHERE id = ? AND redeemed_by_user_id IS NULL",
            (user_id, row["id"]),
        )
    except Exception:
        logger.exception("[APPSUMO] failed to mark code redeemed")
        return False, {"ok": False, "error": "Redemption failed. Please try again."}

    # Recalculate tier level and flip toolkit_ok on
    new_count = get_user_code_count(user_id)
    new_level = min(3, new_count)
    try:
        execute(
            "UPDATE users SET toolkit_tier_level = ?, toolkit_ok = 1 WHERE id = ?",
            (new_level, user_id),
        )
    except Exception:
        logger.exception("[APPSUMO] failed to update user toolkit level")
        # The code is redeemed in appsumo_codes; the user just won't have
        # their tier updated. This is recoverable via a resync call.

    tier = get_toolkit_tier(new_level)
    logger.info("[APPSUMO] user %s redeemed code %s → level %s", user_id, clean, new_level)
    return True, {
        "ok": True,
        "tier_level": new_level,
        "tier_label": tier["label"],
        "codes_stacked": new_count,
        "capacity": tier,
    }


def seed_test_codes(batch_label="test_batch", count=10):
    """Generate N random test codes so the /appsumo redeem form can be
    tested without waiting for real AppSumo codes. Idempotent — safe
    to call repeatedly; existing codes are preserved.

    Returns the list of codes seeded."""
    import secrets
    import string

    alphabet = string.ascii_uppercase + string.digits
    seeded = []

    for _ in range(count):
        code = "TEST-" + "".join(secrets.choice(alphabet) for _ in range(8))
        try:
            execute(
                "INSERT OR IGNORE INTO appsumo_codes (code, batch_label) VALUES (?, ?)",
                (code, batch_label),
            )
            seeded.append(code)
        except Exception:
            logger.exception("[APPSUMO] seed failed for %s", code)

    return seeded
