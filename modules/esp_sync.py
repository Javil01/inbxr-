"""
InbXr — ESP Data Sync
Pulls deliverability data from connected ESPs, normalizes it,
and stores snapshots for trend tracking + health scoring.
"""

import json
import base64
import logging
from datetime import datetime, timezone

from modules.database import execute, fetchone, fetchall

logger = logging.getLogger("inbxr.esp_sync")


# ── Normalized data structure ────────────────────────────
# Every provider sync returns this shape:
# {
#   "account_name": str,
#   "campaigns": [{ "name", "sent", "delivered", "opens", "clicks", "bounces", "complaints", "bounce_rate", "complaint_rate", "open_rate" }],
#   "totals": { "sent", "delivered", "bounces", "complaints", "opens", "clicks", "bounce_rate", "complaint_rate", "open_rate" },
#   "warmup": { "score": 0-100, "status": str, "emails_sent": int, "inbox_rate": float } | None,
#   "domains": [{ "domain", "spf", "dkim", "dmarc", "state" }] | None,
#   "isp_breakdown": [{ "isp", "sent", "delivered", "bounces", "opens" }] | None,
#   "health_score": 0-100,
#   "health_grade": "A"-"F",
# }


def _api_request(url, headers=None, timeout=15):
    """GET request returning parsed JSON."""
    import urllib.request
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _compute_health(totals, warmup=None):
    """Compute a 0-100 health score from deliverability metrics."""
    score = 100

    bounce_rate = totals.get("bounce_rate", 0)
    complaint_rate = totals.get("complaint_rate", 0)
    open_rate = totals.get("open_rate", 0)

    # Bounce penalty: >2% is bad, >5% is critical
    if bounce_rate > 5:
        score -= 40
    elif bounce_rate > 2:
        score -= 20
    elif bounce_rate > 1:
        score -= 10

    # Complaint penalty: >0.1% is bad, >0.3% is critical
    if complaint_rate > 0.3:
        score -= 35
    elif complaint_rate > 0.1:
        score -= 20
    elif complaint_rate > 0.05:
        score -= 10

    # Low open rate penalty (suggests inbox placement issues)
    if totals.get("sent", 0) > 100:
        if open_rate < 5:
            score -= 25
        elif open_rate < 10:
            score -= 15
        elif open_rate < 15:
            score -= 5

    # Warmup bonus/penalty
    if warmup and warmup.get("score") is not None:
        ws = warmup["score"]
        if ws >= 90:
            score = min(100, score + 5)
        elif ws < 50:
            score -= 15
        elif ws < 70:
            score -= 5

    score = max(0, min(100, score))

    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    return score, grade


def _safe_rate(numerator, denominator):
    """Calculate percentage safely."""
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


# ── Mailchimp sync ───────────────────────────────────────

def sync_mailchimp(api_key, server_prefix=""):
    """Pull recent campaign stats from Mailchimp."""
    if "-" not in api_key:
        raise ValueError("Invalid Mailchimp API key format")
    dc = api_key.split("-")[-1]
    creds = base64.b64encode(f"anystring:{api_key}".encode()).decode()
    auth = {"Authorization": f"Basic {creds}"}

    # Get account info
    acct = _api_request(f"https://{dc}.api.mailchimp.com/3.0/", headers=auth)
    account_name = acct.get("account_name", "Unknown")

    # Get recent campaigns (last 10 sent)
    camps_data = _api_request(
        f"https://{dc}.api.mailchimp.com/3.0/campaigns?status=sent&sort_field=send_time&sort_dir=DESC&count=10&fields=campaigns.id,campaigns.settings.title,campaigns.emails_sent,campaigns.report_summary",
        headers=auth,
    )

    campaigns = []
    total_sent = 0
    total_opens = 0
    total_clicks = 0
    total_bounces = 0
    total_complaints = 0

    for c in camps_data.get("campaigns", []):
        report = c.get("report_summary", {})
        sent = c.get("emails_sent", 0)
        opens = report.get("opens", 0)
        clicks = report.get("clicks", 0)
        # Mailchimp: hard_bounces + soft_bounces
        bounces = report.get("hard_bounces", 0) + report.get("soft_bounces", 0)
        complaints = report.get("abuse_reports", 0) if "abuse_reports" in report else 0

        campaigns.append({
            "name": c.get("settings", {}).get("title", "Untitled"),
            "sent": sent,
            "delivered": sent - bounces,
            "opens": opens,
            "clicks": clicks,
            "bounces": bounces,
            "complaints": complaints,
            "bounce_rate": _safe_rate(bounces, sent),
            "complaint_rate": _safe_rate(complaints, sent),
            "open_rate": _safe_rate(opens, sent),
        })

        total_sent += sent
        total_opens += opens
        total_clicks += clicks
        total_bounces += bounces
        total_complaints += complaints

    totals = {
        "sent": total_sent,
        "delivered": total_sent - total_bounces,
        "bounces": total_bounces,
        "complaints": total_complaints,
        "opens": total_opens,
        "clicks": total_clicks,
        "bounce_rate": _safe_rate(total_bounces, total_sent),
        "complaint_rate": _safe_rate(total_complaints, total_sent),
        "open_rate": _safe_rate(total_opens, total_sent),
    }

    # Try to get domain performance from most recent campaign
    isp_breakdown = None
    if campaigns and camps_data.get("campaigns"):
        try:
            camp_id = camps_data["campaigns"][0]["id"]
            domain_data = _api_request(
                f"https://{dc}.api.mailchimp.com/3.0/reports/{camp_id}/domain-performance",
                headers=auth,
            )
            isp_breakdown = []
            for d in domain_data.get("domains", [])[:10]:
                isp_breakdown.append({
                    "isp": d.get("domain", "unknown"),
                    "sent": d.get("emails_sent", 0),
                    "delivered": d.get("emails_sent", 0) - d.get("bounces", 0),
                    "bounces": d.get("bounces", 0),
                    "opens": d.get("opens", 0),
                })
        except Exception:
            pass

    # Get verified domains
    domains = None
    try:
        dom_data = _api_request(
            f"https://{dc}.api.mailchimp.com/3.0/verified-domains?count=20",
            headers=auth,
        )
        domains = []
        for d in dom_data.get("domains", []):
            domains.append({
                "domain": d.get("domain", ""),
                "spf": d.get("spf_verified", False),
                "dkim": d.get("dkim_verified", False),
                "dmarc": None,
                "state": "verified" if d.get("verified", False) else "unverified",
            })
    except Exception:
        pass

    health_score, health_grade = _compute_health(totals)

    return {
        "account_name": account_name,
        "campaigns": campaigns,
        "totals": totals,
        "warmup": None,
        "domains": domains,
        "isp_breakdown": isp_breakdown,
        "health_score": health_score,
        "health_grade": health_grade,
    }


# ── ActiveCampaign sync ─────────────────────────────────

def sync_activecampaign(api_key, server_prefix=""):
    """Pull campaign stats from ActiveCampaign."""
    base = server_prefix.rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"
    auth = {"Api-Token": api_key}

    # Account info
    user_data = _api_request(f"{base}/api/3/users/me", headers=auth)
    account_name = user_data.get("user", {}).get("firstName", "ActiveCampaign")

    # Recent campaigns
    camps_data = _api_request(
        f"{base}/api/3/campaigns?orders[sdate]=DESC&limit=10&filters[type]=single",
        headers=auth,
    )

    campaigns = []
    total_sent = 0
    total_opens = 0
    total_clicks = 0
    total_bounces = 0
    total_complaints = 0

    for c in camps_data.get("campaigns", []):
        sent = int(c.get("send_amt", 0) or 0)
        opens = int(c.get("uniqueopens", 0) or 0)
        clicks = int(c.get("uniquelinkclicks", 0) or 0)
        bounces = int(c.get("hardbounces", 0) or 0) + int(c.get("softbounces", 0) or 0)
        complaints = int(c.get("abusecomplaints", 0) or 0) if "abusecomplaints" in c else 0

        campaigns.append({
            "name": c.get("name", "Untitled"),
            "sent": sent,
            "delivered": sent - bounces,
            "opens": opens,
            "clicks": clicks,
            "bounces": bounces,
            "complaints": complaints,
            "bounce_rate": _safe_rate(bounces, sent),
            "complaint_rate": _safe_rate(complaints, sent),
            "open_rate": _safe_rate(opens, sent),
        })

        total_sent += sent
        total_opens += opens
        total_clicks += clicks
        total_bounces += bounces
        total_complaints += complaints

    totals = {
        "sent": total_sent,
        "delivered": total_sent - total_bounces,
        "bounces": total_bounces,
        "complaints": total_complaints,
        "opens": total_opens,
        "clicks": total_clicks,
        "bounce_rate": _safe_rate(total_bounces, total_sent),
        "complaint_rate": _safe_rate(total_complaints, total_sent),
        "open_rate": _safe_rate(total_opens, total_sent),
    }

    health_score, health_grade = _compute_health(totals)

    return {
        "account_name": account_name,
        "campaigns": campaigns,
        "totals": totals,
        "warmup": None,
        "domains": None,
        "isp_breakdown": None,
        "health_score": health_score,
        "health_grade": health_grade,
    }


# ── Mailgun sync ─────────────────────────────────────────

def sync_mailgun(api_key, server_prefix=""):
    """Pull delivery stats and domain health from Mailgun."""
    domain = server_prefix
    creds = base64.b64encode(f"api:{api_key}".encode()).decode()
    auth = {"Authorization": f"Basic {creds}"}

    account_name = domain or "Mailgun"

    # Get domain info (DNS status)
    domains = None
    try:
        dom_data = _api_request(
            f"https://api.mailgun.net/v3/domains/{domain}",
            headers=auth,
        )
        d = dom_data.get("domain", {})
        dns = dom_data.get("receiving_dns_records", [])
        sending = dom_data.get("sending_dns_records", [])

        spf_ok = any(r.get("record_type") == "TXT" and r.get("valid") == "valid"
                      for r in sending)
        dkim_ok = any(r.get("record_type") == "TXT" and r.get("valid") == "valid"
                      and "domainkey" in r.get("name", "")
                      for r in sending)

        domains = [{
            "domain": d.get("name", domain),
            "spf": spf_ok,
            "dkim": dkim_ok,
            "dmarc": None,
            "state": d.get("state", "unknown"),
        }]
    except Exception:
        pass

    # Get aggregate stats for last 7 days
    totals = {"sent": 0, "delivered": 0, "bounces": 0, "complaints": 0,
              "opens": 0, "clicks": 0, "bounce_rate": 0, "complaint_rate": 0, "open_rate": 0}
    campaigns = []

    try:
        stats = _api_request(
            f"https://api.mailgun.net/v3/{domain}/stats/total?event=delivered&event=failed&event=opened&event=clicked&event=complained&duration=7d",
            headers=auth,
        )
        s = stats.get("stats", [{}])
        # Mailgun returns daily aggregates; sum them
        for day in s:
            delivered = day.get("delivered", {})
            failed = day.get("failed", {})
            totals["delivered"] += delivered.get("total", 0) if isinstance(delivered, dict) else 0
            perm = failed.get("permanent", {}) if isinstance(failed, dict) else {}
            temp = failed.get("temporary", {}) if isinstance(failed, dict) else {}
            totals["bounces"] += (perm.get("total", 0) if isinstance(perm, dict) else 0) + \
                                 (temp.get("total", 0) if isinstance(temp, dict) else 0)
            opened = day.get("opened", {})
            clicked = day.get("clicked", {})
            complained = day.get("complained", {})
            totals["opens"] += opened.get("total", 0) if isinstance(opened, dict) else 0
            totals["clicks"] += clicked.get("total", 0) if isinstance(clicked, dict) else 0
            totals["complaints"] += complained.get("total", 0) if isinstance(complained, dict) else 0

        totals["sent"] = totals["delivered"] + totals["bounces"]
        totals["bounce_rate"] = _safe_rate(totals["bounces"], totals["sent"])
        totals["complaint_rate"] = _safe_rate(totals["complaints"], totals["sent"])
        totals["open_rate"] = _safe_rate(totals["opens"], totals["delivered"])
    except Exception as e:
        logger.warning("Mailgun stats fetch failed: %s", e)

    health_score, health_grade = _compute_health(totals)

    return {
        "account_name": account_name,
        "campaigns": campaigns,
        "totals": totals,
        "warmup": None,
        "domains": domains,
        "isp_breakdown": None,
        "health_score": health_score,
        "health_grade": health_grade,
    }


# ── GoHighLevel sync ────────────────────────────────────

def sync_gohighlevel(api_key, server_prefix=""):
    """Pull basic stats from GoHighLevel."""
    auth = {"Authorization": f"Bearer {api_key}"}
    account_name = "GoHighLevel"

    # GHL doesn't expose granular email stats easily via v1 API
    # Pull what we can from campaigns
    totals = {"sent": 0, "delivered": 0, "bounces": 0, "complaints": 0,
              "opens": 0, "clicks": 0, "bounce_rate": 0, "complaint_rate": 0, "open_rate": 0}

    try:
        data = _api_request(
            "https://rest.gohighlevel.com/v1/campaigns/",
            headers=auth,
        )
        camps = data.get("campaigns", [])
        account_name = f"GoHighLevel ({len(camps)} campaigns)"
    except Exception:
        pass

    health_score, health_grade = _compute_health(totals)

    return {
        "account_name": account_name,
        "campaigns": [],
        "totals": totals,
        "warmup": None,
        "domains": None,
        "isp_breakdown": None,
        "health_score": health_score,
        "health_grade": health_grade,
    }


# ── Instantly sync ───────────────────────────────────────

def sync_instantly(api_key, server_prefix=""):
    """Pull warmup scores and campaign stats from Instantly."""
    account_name = "Instantly"

    # Get sending accounts with warmup data
    warmup = None
    try:
        accounts = _api_request(
            f"https://api.instantly.ai/api/v1/account/list?api_key={api_key}&limit=100",
        )
        account_name = f"Instantly ({len(accounts)} accounts)"

        total_warmup_score = 0
        warmup_count = 0
        total_warmup_sent = 0

        for acct in accounts:
            # Get warmup stats per account
            try:
                ws = _api_request(
                    f"https://api.instantly.ai/api/v1/account/warmup/status?api_key={api_key}&email={acct.get('email', '')}",
                )
                score = ws.get("warmup_reputation", ws.get("score", 0))
                if score:
                    total_warmup_score += score
                    warmup_count += 1
                total_warmup_sent += ws.get("warmup_emails_sent_today", 0)
            except Exception:
                pass

        if warmup_count > 0:
            avg_score = round(total_warmup_score / warmup_count)
            warmup = {
                "score": avg_score,
                "status": "healthy" if avg_score >= 70 else "warming" if avg_score >= 40 else "cold",
                "emails_sent": total_warmup_sent,
                "inbox_rate": avg_score,  # Instantly score approximates inbox rate
                "accounts_count": len(accounts),
                "accounts_with_warmup": warmup_count,
            }
    except Exception as e:
        logger.warning("Instantly account fetch failed: %s", e)

    # Get campaign analytics
    campaigns = []
    totals = {"sent": 0, "delivered": 0, "bounces": 0, "complaints": 0,
              "opens": 0, "clicks": 0, "bounce_rate": 0, "complaint_rate": 0, "open_rate": 0}

    try:
        camp_data = _api_request(
            f"https://api.instantly.ai/api/v1/campaign/list?api_key={api_key}&limit=10",
        )
        for c in camp_data if isinstance(camp_data, list) else []:
            camp_id = c.get("id", "")
            if not camp_id:
                continue
            try:
                summary = _api_request(
                    f"https://api.instantly.ai/api/v1/analytics/campaign/summary?api_key={api_key}&campaign_id={camp_id}",
                )
                sent = summary.get("total_sent", 0)
                opens = summary.get("total_opened", 0)
                replies = summary.get("total_replied", 0)
                bounces = summary.get("total_bounced", 0)

                campaigns.append({
                    "name": c.get("name", "Untitled"),
                    "sent": sent,
                    "delivered": sent - bounces,
                    "opens": opens,
                    "clicks": replies,  # Instantly tracks replies, not clicks
                    "bounces": bounces,
                    "complaints": 0,
                    "bounce_rate": _safe_rate(bounces, sent),
                    "complaint_rate": 0,
                    "open_rate": _safe_rate(opens, sent),
                })

                totals["sent"] += sent
                totals["opens"] += opens
                totals["clicks"] += replies
                totals["bounces"] += bounces
            except Exception:
                pass

        totals["delivered"] = totals["sent"] - totals["bounces"]
        totals["bounce_rate"] = _safe_rate(totals["bounces"], totals["sent"])
        totals["open_rate"] = _safe_rate(totals["opens"], totals["sent"])
    except Exception as e:
        logger.warning("Instantly campaign fetch failed: %s", e)

    health_score, health_grade = _compute_health(totals, warmup)

    return {
        "account_name": account_name,
        "campaigns": campaigns,
        "totals": totals,
        "warmup": warmup,
        "domains": None,
        "isp_breakdown": None,
        "health_score": health_score,
        "health_grade": health_grade,
    }


# ── Smartlead sync ───────────────────────────────────────

def sync_smartlead(api_key, server_prefix=""):
    """Pull warmup stats and campaign data from Smartlead."""
    account_name = "Smartlead"

    # Get email accounts with warmup
    warmup = None
    try:
        accounts = _api_request(
            f"https://server.smartlead.ai/api/v1/email-accounts?api_key={api_key}&limit=100",
        )
        account_name = f"Smartlead ({len(accounts)} accounts)"

        total_warmup_score = 0
        warmup_count = 0

        for acct in accounts if isinstance(accounts, list) else []:
            rep = acct.get("warmup_reputation", acct.get("reputation", 0))
            if rep:
                total_warmup_score += rep
                warmup_count += 1

        if warmup_count > 0:
            avg_score = round(total_warmup_score / warmup_count)
            warmup = {
                "score": avg_score,
                "status": "healthy" if avg_score >= 70 else "warming" if avg_score >= 40 else "cold",
                "emails_sent": 0,
                "inbox_rate": avg_score,
                "accounts_count": len(accounts) if isinstance(accounts, list) else 0,
                "accounts_with_warmup": warmup_count,
            }
    except Exception as e:
        logger.warning("Smartlead accounts fetch failed: %s", e)

    # Get campaign stats
    campaigns = []
    totals = {"sent": 0, "delivered": 0, "bounces": 0, "complaints": 0,
              "opens": 0, "clicks": 0, "bounce_rate": 0, "complaint_rate": 0, "open_rate": 0}

    try:
        camp_data = _api_request(
            f"https://server.smartlead.ai/api/v1/campaigns?api_key={api_key}&limit=10",
        )
        for c in camp_data if isinstance(camp_data, list) else []:
            camp_id = c.get("id", "")
            if not camp_id:
                continue
            try:
                stats = _api_request(
                    f"https://server.smartlead.ai/api/v1/campaigns/{camp_id}/statistics?api_key={api_key}",
                )
                sent = stats.get("sent", 0)
                opens = stats.get("opened", 0)
                replies = stats.get("replied", 0)
                bounces = stats.get("bounced", 0)
                clicks = stats.get("clicked", 0)

                campaigns.append({
                    "name": c.get("name", "Untitled"),
                    "sent": sent,
                    "delivered": sent - bounces,
                    "opens": opens,
                    "clicks": clicks or replies,
                    "bounces": bounces,
                    "complaints": 0,
                    "bounce_rate": _safe_rate(bounces, sent),
                    "complaint_rate": 0,
                    "open_rate": _safe_rate(opens, sent),
                })

                totals["sent"] += sent
                totals["opens"] += opens
                totals["clicks"] += (clicks or replies)
                totals["bounces"] += bounces
            except Exception:
                pass

        totals["delivered"] = totals["sent"] - totals["bounces"]
        totals["bounce_rate"] = _safe_rate(totals["bounces"], totals["sent"])
        totals["open_rate"] = _safe_rate(totals["opens"], totals["sent"])
    except Exception as e:
        logger.warning("Smartlead campaign fetch failed: %s", e)

    health_score, health_grade = _compute_health(totals, warmup)

    return {
        "account_name": account_name,
        "campaigns": campaigns,
        "totals": totals,
        "warmup": warmup,
        "domains": None,
        "isp_breakdown": None,
        "health_score": health_score,
        "health_grade": health_grade,
    }


# ── AWeber sync ──────────────────────────────────────────

def sync_aweber(api_key, server_prefix=""):
    """Pull basic stats from AWeber."""
    auth = {"Authorization": f"Bearer {api_key}"}
    account_name = "AWeber"

    try:
        acct_data = _api_request(
            "https://api.aweber.com/1.0/accounts",
            headers=auth,
        )
        entries = acct_data.get("entries", [])
        if entries:
            account_name = f"AWeber (Account {entries[0].get('id', '')})"
    except Exception:
        pass

    totals = {"sent": 0, "delivered": 0, "bounces": 0, "complaints": 0,
              "opens": 0, "clicks": 0, "bounce_rate": 0, "complaint_rate": 0, "open_rate": 0}

    health_score, health_grade = _compute_health(totals)

    return {
        "account_name": account_name,
        "campaigns": [],
        "totals": totals,
        "warmup": None,
        "domains": None,
        "isp_breakdown": None,
        "health_score": health_score,
        "health_grade": health_grade,
    }


# ── Dispatcher ───────────────────────────────────────────

_SYNC_FNS = {
    "mailchimp": sync_mailchimp,
    "activecampaign": sync_activecampaign,
    "mailgun": sync_mailgun,
    "gohighlevel": sync_gohighlevel,
    "instantly": sync_instantly,
    "smartlead": sync_smartlead,
    "aweber": sync_aweber,
}


def sync_integration(integration_id):
    """Sync a single integration. Decrypts creds, calls provider, stores snapshot."""
    from blueprints.integration_routes import _decrypt_value

    row = fetchone("SELECT * FROM esp_integrations WHERE id = ?", (integration_id,))
    if not row:
        return None

    provider = row["provider"]
    sync_fn = _SYNC_FNS.get(provider)
    if not sync_fn:
        return None

    api_key = _decrypt_value(row["api_key_encrypted"])
    server_prefix = row.get("server_prefix") or ""

    try:
        data = sync_fn(api_key, server_prefix)

        # Store snapshot
        execute(
            """INSERT INTO esp_sync_snapshots
               (integration_id, health_score, health_grade, totals_json, warmup_json, data_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                integration_id,
                data["health_score"],
                data["health_grade"],
                json.dumps(data["totals"]),
                json.dumps(data["warmup"]) if data["warmup"] else None,
                json.dumps(data),
            ),
        )

        # Update integration status
        execute(
            """UPDATE esp_integrations
               SET status = 'active', status_message = ?, last_synced_at = datetime('now'),
                   sync_data_json = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (
                f"Health: {data['health_grade']} ({data['health_score']}/100)",
                json.dumps(data),
                integration_id,
            ),
        )

        logger.info("Synced integration %s (%s): score=%s grade=%s",
                     integration_id, provider, data["health_score"], data["health_grade"])
        return data

    except Exception as e:
        logger.exception("Sync failed for integration %s (%s)", integration_id, provider)
        execute(
            "UPDATE esp_integrations SET status = 'error', status_message = ?, updated_at = datetime('now') WHERE id = ?",
            (f"Sync failed: {str(e)[:200]}", integration_id),
        )
        return None


def sync_all_for_user(user_id):
    """Sync all active integrations for a user. Returns list of results."""
    integrations = fetchall(
        "SELECT id FROM esp_integrations WHERE user_id = ? AND status IN ('active', 'pending')",
        (user_id,),
    )
    results = []
    for row in integrations:
        data = sync_integration(row["id"])
        results.append({"integration_id": row["id"], "data": data})
    return results


def sync_all_active():
    """Sync all active integrations across all users. Used by scheduler."""
    integrations = fetchall(
        "SELECT id, user_id, provider FROM esp_integrations WHERE status IN ('active', 'pending')",
    )
    logger.info("[ESP_SYNC] Syncing %d active integrations", len(integrations))
    synced = 0
    errors = 0
    for row in integrations:
        result = sync_integration(row["id"])
        if result:
            synced += 1
        else:
            errors += 1
    logger.info("[ESP_SYNC] Done: %d synced, %d errors", synced, errors)
    return {"synced": synced, "errors": errors, "total": len(integrations)}


def get_sync_history(integration_id, limit=30):
    """Get recent sync snapshots for an integration."""
    return fetchall(
        """SELECT id, health_score, health_grade, totals_json, warmup_json, synced_at
           FROM esp_sync_snapshots
           WHERE integration_id = ?
           ORDER BY synced_at DESC LIMIT ?""",
        (integration_id, limit),
    )


def get_user_health_summary(user_id):
    """Get aggregated health data across all integrations for a user."""
    integrations = fetchall(
        """SELECT i.id, i.provider, i.label, i.status, i.last_synced_at, i.sync_data_json
           FROM esp_integrations i
           WHERE i.user_id = ? AND i.status = 'active'
           ORDER BY i.created_at""",
        (user_id,),
    )

    summary = {
        "integrations": [],
        "overall_score": 0,
        "overall_grade": "—",
        "total_sent": 0,
        "total_bounces": 0,
        "total_complaints": 0,
        "total_opens": 0,
        "avg_bounce_rate": 0,
        "avg_complaint_rate": 0,
        "avg_open_rate": 0,
        "warmup_accounts": [],
        "has_data": False,
    }

    scores = []
    for intg in integrations:
        data = json.loads(intg["sync_data_json"]) if intg.get("sync_data_json") else None
        if not data:
            continue

        summary["has_data"] = True
        totals = data.get("totals", {})

        entry = {
            "id": intg["id"],
            "provider": intg["provider"],
            "label": intg["label"],
            "account_name": data.get("account_name", ""),
            "health_score": data.get("health_score", 0),
            "health_grade": data.get("health_grade", "—"),
            "totals": totals,
            "warmup": data.get("warmup"),
            "last_synced": intg["last_synced_at"],
            "campaigns": data.get("campaigns", [])[:5],
            "domains": data.get("domains"),
            "isp_breakdown": data.get("isp_breakdown"),
        }
        summary["integrations"].append(entry)
        scores.append(data.get("health_score", 0))

        summary["total_sent"] += totals.get("sent", 0)
        summary["total_bounces"] += totals.get("bounces", 0)
        summary["total_complaints"] += totals.get("complaints", 0)
        summary["total_opens"] += totals.get("opens", 0)

        if data.get("warmup"):
            summary["warmup_accounts"].append({
                "provider": intg["provider"],
                "label": intg["label"],
                **data["warmup"],
            })

    if scores:
        avg = round(sum(scores) / len(scores))
        summary["overall_score"] = avg
        if avg >= 90:
            summary["overall_grade"] = "A"
        elif avg >= 75:
            summary["overall_grade"] = "B"
        elif avg >= 60:
            summary["overall_grade"] = "C"
        elif avg >= 40:
            summary["overall_grade"] = "D"
        else:
            summary["overall_grade"] = "F"

    if summary["total_sent"]:
        summary["avg_bounce_rate"] = _safe_rate(summary["total_bounces"], summary["total_sent"])
        summary["avg_complaint_rate"] = _safe_rate(summary["total_complaints"], summary["total_sent"])
        summary["avg_open_rate"] = _safe_rate(summary["total_opens"], summary["total_sent"])

    return summary
