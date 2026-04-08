"""
InbXr Dogfood Signal Score
──────────────────────────
Runs the Domain Signal Score engine against inbxr.us itself on a nightly
schedule and writes the result to the dogfood_score table. The homepage
dogfood badge reads from this table instead of showing hardcoded numbers,
so the claim "this score updates automatically" is actually true.

Only 2 of the 7 signals are computed (Authentication Standing and
Domain Reputation) because inbxr.us does not expose per-contact list data
to the engine in the same way a connected ESP would. The template renders
the remaining 5 signals as "pending list connection" rather than inventing
numbers for them.
"""

import logging
from modules.database import execute, fetchone

logger = logging.getLogger(__name__)

DOGFOOD_DOMAIN = "inbxr.us"


def refresh_dogfood_score():
    """Run the domain signal score engine against inbxr.us and persist.
    Safe to call from a scheduler job or manually from an admin endpoint.
    Returns the refreshed row as a dict, or None on failure."""
    from modules.signal_score import calculate_domain_signal_score

    try:
        result = calculate_domain_signal_score(DOGFOOD_DOMAIN)
    except Exception:
        logger.exception("[DOGFOOD] calculate_domain_signal_score failed")
        return None

    if not result or result.get("error"):
        logger.warning(
            "[DOGFOOD] refresh failed: %s",
            result.get("message") if result else "no result",
        )
        return None

    total = result.get("total_signal_score", 0)
    grade = result.get("signal_grade", "F")
    meta = result.get("metadata", {})
    auth_meta = meta.get("authentication_standing", {}) or {}
    rep_meta = meta.get("domain_reputation", {}) or {}
    auth_score = auth_meta.get("auth_score", 0)
    rep_score = rep_meta.get("rep_score", 0)

    try:
        execute(
            """
            INSERT INTO dogfood_score
                (id, domain, total_score, grade, auth_score, rep_score,
                 visible_signals, locked_signals, calculated_at)
            VALUES (1, ?, ?, ?, ?, ?, 2, 5, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                domain = excluded.domain,
                total_score = excluded.total_score,
                grade = excluded.grade,
                auth_score = excluded.auth_score,
                rep_score = excluded.rep_score,
                calculated_at = excluded.calculated_at
            """,
            (DOGFOOD_DOMAIN, total, grade, auth_score, rep_score),
        )
    except Exception:
        logger.exception("[DOGFOOD] failed to persist refreshed score")
        return None

    logger.info(
        "[DOGFOOD] refreshed: %s → %s (%s)",
        DOGFOOD_DOMAIN, total, grade,
    )
    return get_latest_dogfood_score()


def get_latest_dogfood_score():
    """Return the latest dogfood score row as a plain dict, or None if
    the table is empty (before the first scheduled refresh).
    Consumers (template context processors) should treat None as
    'not yet available' and render a graceful fallback."""
    try:
        row = fetchone(
            "SELECT domain, total_score, grade, auth_score, rep_score, "
            "visible_signals, locked_signals, calculated_at "
            "FROM dogfood_score WHERE id = 1"
        )
    except Exception:
        logger.exception("[DOGFOOD] failed to read dogfood_score row")
        return None

    if not row:
        return None

    return {
        "domain": row["domain"],
        "total": int(round(row["total_score"])),
        "grade": row["grade"],
        "auth_score": int(round(row["auth_score"])),
        "rep_score": int(round(row["rep_score"])),
        "visible_signals": row["visible_signals"],
        "locked_signals": row["locked_signals"],
        "calculated_at": row["calculated_at"],
    }
