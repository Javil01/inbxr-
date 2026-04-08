"""
InbXr — Public Domain Leaderboard
─────────────────────────────────
Every time the Domain Signal Score engine runs, it logs the result
to the domain_leaderboard table. The public /leaderboard page reads
from this table to show:

    - Top N scoring domains (bragging board)
    - Total domains scanned (social proof)
    - Aggregate grade distribution (category health snapshot)

The leaderboard is fully anonymized. We only store:
    domain, total_score, grade, auth_score, rep_score,
    scan_count, first_scanned_at, last_scanned_at

No user IDs, no email lists, no per-contact data. This means:
  (a) we can publish it without privacy headaches
  (b) the data compounds forever with every Domain Signal Score scan
  (c) one domain = one row (UNIQUE constraint), most recent scan wins

The leaderboard is a compounding asset. Every visitor who types a
domain into the homepage contributes to it. Every Chrome extension
install will add more. Every embed badge check will add more. By
month 6 it's the biggest anonymized deliverability dataset in the
category, which is the V3 moat the original research brief pointed at.
"""

import logging
import re
from modules.database import execute, fetchone, fetchall

logger = logging.getLogger(__name__)


# Obvious well-known domains we don't want to clutter the leaderboard
# with because they skew the top of the list and aren't actionable for
# real buyers. We still compute scores for them; we just don't show them.
_EXCLUDED_FROM_PUBLIC = {
    "localhost",
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "domain.com",
    "email.com",
}


def _normalize(domain):
    """Lowercase, strip whitespace, remove protocol/path if present."""
    if not domain:
        return ""
    d = domain.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"/.*$", "", d)
    d = d.split(":")[0]  # strip port
    return d


def upsert_leaderboard_entry(domain, total_score, grade, auth_score=None, rep_score=None):
    """Insert or update a leaderboard row for this domain. Called
    every time calculate_domain_signal_score() runs. Safe to call
    repeatedly — the UNIQUE constraint on domain ensures one row
    per domain with the most recent score winning."""
    normalized = _normalize(domain)
    if not normalized or "." not in normalized:
        return

    try:
        execute(
            """INSERT INTO domain_leaderboard
                (domain, total_score, grade, auth_score, rep_score,
                 scan_count, first_scanned_at, last_scanned_at)
               VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))
               ON CONFLICT(domain) DO UPDATE SET
                 total_score = excluded.total_score,
                 grade = excluded.grade,
                 auth_score = excluded.auth_score,
                 rep_score = excluded.rep_score,
                 scan_count = domain_leaderboard.scan_count + 1,
                 last_scanned_at = datetime('now')
            """,
            (normalized, int(round(total_score)), grade, auth_score, rep_score),
        )
    except Exception:
        logger.exception("[LEADERBOARD] upsert failed for %s", normalized)


def get_top_domains(limit=50, grade_filter=None):
    """Top N domains sorted by score descending, then recency. Public
    leaderboard page renders this. Excludes the well-known/example
    domains so the top of the list is interesting and real."""
    excluded_placeholders = ",".join("?" * len(_EXCLUDED_FROM_PUBLIC))
    params = list(_EXCLUDED_FROM_PUBLIC)

    where_clauses = [f"domain NOT IN ({excluded_placeholders})"]
    if grade_filter and grade_filter in ("A", "B", "C", "D", "F"):
        where_clauses.append("grade = ?")
        params.append(grade_filter)

    where_sql = " AND ".join(where_clauses)
    params.append(limit)

    try:
        return fetchall(
            f"""SELECT domain, total_score, grade, auth_score, rep_score,
                       scan_count, last_scanned_at
                FROM domain_leaderboard
                WHERE {where_sql}
                ORDER BY total_score DESC, last_scanned_at DESC
                LIMIT ?""",
            tuple(params),
        )
    except Exception:
        logger.exception("[LEADERBOARD] fetch top domains failed")
        return []


def get_leaderboard_stats():
    """Aggregate stats for the leaderboard header: total scanned,
    grade distribution, average score. Used for the social proof line
    at the top of the page."""
    try:
        total_row = fetchone(
            "SELECT COUNT(*) AS n, "
            "AVG(total_score) AS avg_score, "
            "SUM(scan_count) AS total_scans "
            "FROM domain_leaderboard",
            (),
        )
        if not total_row:
            return {
                "total_domains": 0,
                "total_scans": 0,
                "avg_score": 0,
                "grade_distribution": {},
            }

        grade_rows = fetchall(
            "SELECT grade, COUNT(*) AS n FROM domain_leaderboard GROUP BY grade",
            (),
        )
        distribution = {row["grade"]: row["n"] for row in grade_rows}

        # Ensure all grades exist in the distribution so the template
        # doesn't have to defensively check
        for g in ("A", "B", "C", "D", "F"):
            distribution.setdefault(g, 0)

        return {
            "total_domains": total_row.get("n") or 0,
            "total_scans": total_row.get("total_scans") or 0,
            "avg_score": round(total_row.get("avg_score") or 0, 1),
            "grade_distribution": distribution,
        }
    except Exception:
        logger.exception("[LEADERBOARD] stats fetch failed")
        return {
            "total_domains": 0,
            "total_scans": 0,
            "avg_score": 0,
            "grade_distribution": {},
        }


def get_domain_rank(domain):
    """Given a domain, return its current rank on the leaderboard
    (1-indexed) and score. Used by the /leaderboard page when a user
    arrives after scoring their own domain via the homepage.
    Returns None if the domain isn't on the board."""
    normalized = _normalize(domain)
    if not normalized:
        return None

    try:
        row = fetchone(
            "SELECT total_score, grade FROM domain_leaderboard WHERE domain = ?",
            (normalized,),
        )
        if not row:
            return None

        rank_row = fetchone(
            "SELECT COUNT(*) + 1 AS rank FROM domain_leaderboard "
            "WHERE total_score > ?",
            (row["total_score"],),
        )
        return {
            "domain": normalized,
            "score": row["total_score"],
            "grade": row["grade"],
            "rank": rank_row["rank"] if rank_row else None,
        }
    except Exception:
        logger.exception("[LEADERBOARD] get_domain_rank failed for %s", normalized)
        return None
