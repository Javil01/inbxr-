"""
INBXR — Bulk Email Verification
Create, process, and manage bulk verification jobs.
"""

import json
import csv
import io
from datetime import datetime, timezone

from modules.database import execute, fetchone, fetchall
from modules.email_verifier import verify_email

MAX_EMAILS_PER_JOB = 10_000


def create_bulk_job(user_id, emails, filename=None, team_id=None):
    """Create a bulk verification job.

    Parameters
    ----------
    user_id : int
        The owner of the job.
    emails : list[str]
        List of email addresses to verify.
    filename : str, optional
        Original filename if uploaded from a file.
    team_id : int, optional
        Team ID if this is a team job.

    Returns
    -------
    int
        The job ID.

    Raises
    ------
    ValueError
        If the email list is empty or exceeds the maximum.
    """
    if not emails:
        raise ValueError("No emails provided.")
    if len(emails) > MAX_EMAILS_PER_JOB:
        raise ValueError(f"Maximum {MAX_EMAILS_PER_JOB:,} emails per job.")

    # Deduplicate and clean
    seen = set()
    clean = []
    for e in emails:
        e = e.strip().lower()
        if e and e not in seen:
            seen.add(e)
            clean.append(e)

    if not clean:
        raise ValueError("No valid emails after cleaning.")

    cur = execute(
        """INSERT INTO bulk_jobs (user_id, filename, total_emails, status, team_id)
           VALUES (?, ?, ?, 'pending', ?)""",
        (user_id, filename, len(clean), team_id),
    )
    job_id = cur.lastrowid

    # Insert all emails into bulk_results with NULL verdict (pending)
    for email in clean:
        execute(
            "INSERT INTO bulk_results (job_id, email) VALUES (?, ?)",
            (job_id, email),
        )

    return job_id


def process_bulk_job(job_id):
    """Process all emails in a bulk job sequentially.

    Calls verify_email() for each email, updating progress as it goes.
    Individual failures are caught so one bad email doesn't kill the batch.
    """
    job = fetchone("SELECT * FROM bulk_jobs WHERE id = ?", (job_id,))
    if not job:
        return

    execute(
        "UPDATE bulk_jobs SET status = 'processing' WHERE id = ?",
        (job_id,),
    )

    results = fetchall(
        "SELECT id, email FROM bulk_results WHERE job_id = ? ORDER BY id",
        (job_id,),
    )

    processed = 0
    summary = {"valid": 0, "invalid": 0, "risky": 0, "unknown": 0}

    for row in results:
        try:
            result = verify_email(row["email"])
            verdict = result.get("verdict", "unknown")
            score = result.get("score", 0)
            result_json = json.dumps(result)

            execute(
                """UPDATE bulk_results
                   SET verdict = ?, score = ?, result_json = ?
                   WHERE id = ?""",
                (verdict, score, result_json, row["id"]),
            )

            if verdict in summary:
                summary[verdict] += 1
            else:
                summary["unknown"] += 1

        except Exception:
            execute(
                """UPDATE bulk_results
                   SET verdict = 'unknown', score = 0,
                       result_json = ?
                   WHERE id = ?""",
                (json.dumps({"error": "Verification failed"}), row["id"]),
            )
            summary["unknown"] += 1

        processed += 1

        # Update progress every email
        execute(
            "UPDATE bulk_jobs SET processed = ? WHERE id = ?",
            (processed, job_id),
        )

    # Mark complete
    execute(
        """UPDATE bulk_jobs
           SET status = 'completed',
               summary_json = ?,
               completed_at = datetime('now')
           WHERE id = ?""",
        (json.dumps(summary), job_id),
    )


def get_job_status(job_id, user_id, team_id=None):
    """Get job status, verifying ownership.

    Returns
    -------
    dict or None
        Job info with status, counts, and summary. None if not found or not owned.
    """
    if team_id:
        job = fetchone(
            "SELECT * FROM bulk_jobs WHERE id = ? AND team_id = ?",
            (job_id, team_id),
        )
    else:
        job = fetchone(
            "SELECT * FROM bulk_jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        )
    if not job:
        return None

    result = {
        "id": job["id"],
        "filename": job["filename"],
        "total_emails": job["total_emails"],
        "processed": job["processed"],
        "status": job["status"],
        "created_at": job["created_at"],
        "completed_at": job["completed_at"],
        "summary": None,
    }

    if job["summary_json"]:
        try:
            result["summary"] = json.loads(job["summary_json"])
        except (json.JSONDecodeError, TypeError):
            result["summary"] = None

    return result


def get_job_results(job_id, user_id, limit=100, offset=0, team_id=None):
    """Get paginated results for a job, verifying ownership.

    Returns
    -------
    list[dict] or None
        List of result dicts. None if job not found or not owned.
    """
    if team_id:
        job = fetchone(
            "SELECT id FROM bulk_jobs WHERE id = ? AND team_id = ?",
            (job_id, team_id),
        )
    else:
        job = fetchone(
            "SELECT id FROM bulk_jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        )
    if not job:
        return None

    rows = fetchall(
        """SELECT email, verdict, score, result_json
           FROM bulk_results
           WHERE job_id = ?
           ORDER BY id
           LIMIT ? OFFSET ?""",
        (job_id, limit, offset),
    )

    results = []
    for row in rows:
        entry = {
            "email": row["email"],
            "verdict": row["verdict"],
            "score": row["score"],
        }

        if row["result_json"]:
            try:
                full = json.loads(row["result_json"])
                checks = full.get("checks", {})
                entry["reason"] = full.get("verdict_detail", "")
                entry["disposable"] = checks.get("disposable", {}).get("is_disposable", False)
                entry["free_provider"] = checks.get("free_provider", {}).get("is_free", False)
                entry["catch_all"] = checks.get("catch_all", {}).get("is_catch_all", False)
                entry["mx_valid"] = checks.get("domain", {}).get("pass", False)
            except (json.JSONDecodeError, TypeError):
                entry["reason"] = ""
                entry["disposable"] = False
                entry["free_provider"] = False
                entry["catch_all"] = False
                entry["mx_valid"] = False
        else:
            entry["reason"] = ""
            entry["disposable"] = False
            entry["free_provider"] = False
            entry["catch_all"] = False
            entry["mx_valid"] = False

        results.append(entry)

    return results


def get_user_jobs(user_id, team_id=None):
    """List all bulk jobs for a user (or team), newest first.

    Returns
    -------
    list[dict]
        List of job summary dicts.
    """
    if team_id:
        rows = fetchall(
            """SELECT id, filename, total_emails, processed, status,
                      summary_json, created_at, completed_at
               FROM bulk_jobs
               WHERE team_id = ?
               ORDER BY created_at DESC""",
            (team_id,),
        )
    else:
        rows = fetchall(
            """SELECT id, filename, total_emails, processed, status,
                      summary_json, created_at, completed_at
               FROM bulk_jobs
               WHERE user_id = ?
               ORDER BY created_at DESC""",
            (user_id,),
        )

    jobs = []
    for row in rows:
        job = dict(row)
        if job["summary_json"]:
            try:
                job["summary"] = json.loads(job["summary_json"])
            except (json.JSONDecodeError, TypeError):
                job["summary"] = None
        else:
            job["summary"] = None
        del job["summary_json"]
        jobs.append(job)

    return jobs


def generate_csv(job_id, user_id, team_id=None):
    """Generate a CSV string of results for a completed job.

    Returns
    -------
    str or None
        CSV content as a string. None if job not found or not owned.
    """
    if team_id:
        job = fetchone(
            "SELECT id FROM bulk_jobs WHERE id = ? AND team_id = ?",
            (job_id, team_id),
        )
    else:
        job = fetchone(
            "SELECT id FROM bulk_jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        )
    if not job:
        return None

    rows = fetchall(
        """SELECT email, verdict, score, result_json
           FROM bulk_results
           WHERE job_id = ?
           ORDER BY id""",
        (job_id,),
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "email", "verdict", "score", "reason",
        "disposable", "free_provider", "catch_all", "mx_valid",
    ])

    for row in rows:
        reason = ""
        disposable = False
        free_provider = False
        catch_all = False
        mx_valid = False

        if row["result_json"]:
            try:
                full = json.loads(row["result_json"])
                checks = full.get("checks", {})
                reason = full.get("verdict_detail", "")
                disposable = checks.get("disposable", {}).get("is_disposable", False)
                free_provider = checks.get("free_provider", {}).get("is_free", False)
                catch_all = checks.get("catch_all", {}).get("is_catch_all", False)
                mx_valid = checks.get("domain", {}).get("pass", False)
            except (json.JSONDecodeError, TypeError):
                pass

        writer.writerow([
            row["email"],
            row["verdict"] or "unknown",
            row["score"] if row["score"] is not None else 0,
            reason,
            disposable,
            free_provider,
            catch_all,
            mx_valid,
        ])

    return output.getvalue()
