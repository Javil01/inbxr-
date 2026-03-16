"""
INBXR — DNS Authentication Monitor
Checks SPF, DKIM, DMARC for monitored domains and alerts on issues/changes.
"""

import json
import logging
import dns.resolver

from modules.database import execute, fetchone, fetchall

logger = logging.getLogger('inbxr.dns_monitor')

# Common DKIM selectors to check
DKIM_SELECTORS = ['default', 'google', 'selector1', 'selector2', 'mail',
                  'brevo1._domainkey', 'brevo2._domainkey', 'k1']


def check_spf(domain):
    """Check SPF record for a domain. Returns dict with record and issues."""
    issues = []
    record = None
    try:
        answers = dns.resolver.resolve(domain, 'TXT')
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith('v=spf1'):
                record = txt
                break
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        pass
    except Exception as e:
        logger.debug("SPF lookup error for %s: %s", domain, e)

    if not record:
        issues.append({"type": "spf_missing", "severity": "high",
                        "message": f"No SPF record found for {domain}"})
    else:
        if '+all' in record:
            issues.append({"type": "spf_permissive", "severity": "high",
                            "message": "SPF uses +all (allows anyone to send)"})
        elif '?all' in record:
            issues.append({"type": "spf_neutral", "severity": "medium",
                            "message": "SPF uses ?all (neutral — consider ~all or -all)"})
        # Count DNS lookups (includes are ~1 each)
        includes = record.count('include:') + record.count('redirect=')
        if includes > 8:
            issues.append({"type": "spf_too_many_lookups", "severity": "medium",
                            "message": f"SPF has {includes} includes (max 10 DNS lookups allowed)"})

    return {"record": record, "issues": issues}


def check_dkim(domain):
    """Check if any common DKIM selectors resolve. Returns dict."""
    valid = False
    for selector in DKIM_SELECTORS:
        try:
            qname = f"{selector}.{domain}" if '._domainkey' in selector else f"{selector}._domainkey.{domain}"
            answers = dns.resolver.resolve(qname, 'TXT')
            if answers:
                valid = True
                break
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            continue
        except Exception:
            continue

    # Also try CNAME (Brevo-style)
    if not valid:
        for selector in DKIM_SELECTORS:
            try:
                qname = f"{selector}.{domain}" if '._domainkey' in selector else f"{selector}._domainkey.{domain}"
                answers = dns.resolver.resolve(qname, 'CNAME')
                if answers:
                    valid = True
                    break
            except Exception:
                continue

    issues = []
    if not valid:
        issues.append({"type": "dkim_missing", "severity": "high",
                        "message": f"No DKIM record found for {domain} (checked common selectors)"})

    return {"valid": valid, "issues": issues}


def check_dmarc(domain):
    """Check DMARC record. Returns dict with record, policy, and issues."""
    record = None
    policy = None
    issues = []

    try:
        answers = dns.resolver.resolve(f"_dmarc.{domain}", 'TXT')
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith('v=DMARC1'):
                record = txt
                break
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        pass
    except Exception as e:
        logger.debug("DMARC lookup error for %s: %s", domain, e)

    if not record:
        issues.append({"type": "dmarc_missing", "severity": "high",
                        "message": f"No DMARC record found for {domain}"})
    else:
        # Extract policy
        for part in record.split(';'):
            part = part.strip()
            if part.startswith('p='):
                policy = part[2:].strip()
                break

        if policy == 'none':
            issues.append({"type": "dmarc_none", "severity": "low",
                            "message": "DMARC policy is 'none' (monitoring only, no enforcement)"})
        elif not policy:
            issues.append({"type": "dmarc_no_policy", "severity": "medium",
                            "message": "DMARC record found but no policy tag (p=) set"})

        # Check for rua (reporting)
        if 'rua=' not in record:
            issues.append({"type": "dmarc_no_reporting", "severity": "low",
                            "message": "DMARC has no rua= tag (no aggregate reports will be received)"})

    return {"record": record, "policy": policy, "issues": issues}


def scan_domain_dns(domain):
    """Full DNS auth scan for a domain. Returns combined results."""
    spf = check_spf(domain)
    dkim = check_dkim(domain)
    dmarc = check_dmarc(domain)

    all_issues = spf["issues"] + dkim["issues"] + dmarc["issues"]

    return {
        "domain": domain,
        "spf": spf,
        "dkim": dkim,
        "dmarc": dmarc,
        "issues": all_issues,
        "issue_count": len(all_issues),
        "has_critical": any(i["severity"] == "high" for i in all_issues),
    }


def save_dns_snapshot(monitor_id, scan_result):
    """Store a DNS scan snapshot and return it."""
    execute(
        """INSERT INTO dns_monitor_snapshots
           (monitor_id, spf_record, dkim_valid, dmarc_record, dmarc_policy, issues)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            monitor_id,
            scan_result["spf"]["record"],
            int(scan_result["dkim"]["valid"]),
            scan_result["dmarc"]["record"],
            scan_result["dmarc"]["policy"],
            json.dumps(scan_result["issues"]),
        ),
    )


def get_previous_snapshot(monitor_id):
    """Get the most recent DNS snapshot for comparison."""
    row = fetchone(
        """SELECT * FROM dns_monitor_snapshots
           WHERE monitor_id = ? ORDER BY scanned_at DESC LIMIT 1""",
        (monitor_id,),
    )
    if row and row.get("issues"):
        row["issues"] = json.loads(row["issues"])
    return row


def detect_dns_changes(prev_snapshot, new_scan):
    """Compare previous snapshot with new scan results. Returns changes dict."""
    if not prev_snapshot:
        return {"changed": False, "new_issues": new_scan["issues"], "resolved_issues": []}

    prev_issues = prev_snapshot.get("issues", [])
    prev_types = {i["type"] for i in prev_issues}
    new_types = {i["type"] for i in new_scan["issues"]}

    new_issue_types = new_types - prev_types
    resolved_types = prev_types - new_types

    new_issues = [i for i in new_scan["issues"] if i["type"] in new_issue_types]
    resolved_issues = [i for i in prev_issues if i["type"] in resolved_types]

    # Also check if SPF/DMARC record content changed
    record_changed = (
        prev_snapshot.get("spf_record") != new_scan["spf"]["record"]
        or prev_snapshot.get("dmarc_record") != new_scan["dmarc"]["record"]
        or bool(prev_snapshot.get("dkim_valid")) != new_scan["dkim"]["valid"]
    )

    return {
        "changed": bool(new_issues or resolved_issues or record_changed),
        "new_issues": new_issues,
        "resolved_issues": resolved_issues,
        "record_changed": record_changed,
    }


def scan_all_monitored_dns():
    """Scan DNS auth for all monitored domains of paid users. Create alerts for changes."""
    from modules.alerts import create_alert, get_alert_preferences
    from modules.tiers import has_feature

    monitors = fetchall("""
        SELECT um.id, um.user_id, um.domain, u.tier, u.email
        FROM user_monitors um
        JOIN users u ON u.id = um.user_id
        WHERE u.tier IN ('pro', 'agency', 'api')
    """)

    logger.info("[DNS_MONITOR] Scanning DNS auth for %d monitors", len(monitors))
    scanned = 0
    alerted = 0

    for mon in monitors:
        try:
            if not has_feature(mon["tier"], "email_alerts"):
                continue

            prefs = get_alert_preferences(mon["user_id"])
            if not prefs.get("dns_auth_alerts", True):
                continue

            prev = get_previous_snapshot(mon["id"])
            scan_result = scan_domain_dns(mon["domain"])
            save_dns_snapshot(mon["id"], scan_result)
            scanned += 1

            changes = detect_dns_changes(prev, scan_result)
            if changes["changed"] and (changes["new_issues"] or changes["resolved_issues"]):
                # Build alert message
                parts = []
                for issue in changes["new_issues"]:
                    parts.append(f"NEW: {issue['message']}")
                for issue in changes["resolved_issues"]:
                    parts.append(f"RESOLVED: {issue['message']}")

                title = f"DNS auth change detected for {mon['domain']}"
                message = " | ".join(parts) if parts else f"DNS records changed for {mon['domain']}"

                create_alert(
                    mon["user_id"],
                    "dns_auth_change",
                    title,
                    message,
                    data={
                        "domain": mon["domain"],
                        "new_issues": changes["new_issues"],
                        "resolved_issues": changes["resolved_issues"],
                    },
                )
                alerted += 1

                # Send email if instant + email enabled
                if prefs.get("digest_frequency") == "instant" and prefs.get("email_notifications"):
                    _send_dns_alert_email(mon["email"], mon["domain"], changes)

        except Exception:
            logger.exception("[DNS_MONITOR] Error scanning DNS for %s", mon.get("domain"))

    logger.info("[DNS_MONITOR] Scanned %d, alerted %d", scanned, alerted)
    return {"scanned": scanned, "alerted": alerted}


def _send_dns_alert_email(to_email, domain, changes):
    """Send an email notification about DNS auth changes."""
    from modules.mailer import _send, BASE_URL

    rows_html = ""
    for issue in changes.get("new_issues", []):
        color = "#dc2626" if issue["severity"] == "high" else "#f59e0b"
        rows_html += f'<tr><td style="padding:6px 12px;color:{color};font-weight:600;">NEW ISSUE</td><td style="padding:6px 12px;">{issue["message"]}</td></tr>'
    for issue in changes.get("resolved_issues", []):
        rows_html += f'<tr><td style="padding:6px 12px;color:#16a34a;font-weight:600;">RESOLVED</td><td style="padding:6px 12px;">{issue["message"]}</td></tr>'

    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
      <h2 style="color:#0c1a3a;margin:0 0 8px;">DNS Auth Alert: {domain}</h2>
      <p style="color:#334155;font-size:15px;line-height:1.6;">
        We detected changes in the email authentication setup for <strong>{domain}</strong>.
      </p>
      <table style="width:100%;border-collapse:collapse;margin:16px 0;">
        <thead><tr style="background:#f1f5f9;">
          <th style="padding:8px 12px;text-align:left;font-size:13px;">Status</th>
          <th style="padding:8px 12px;text-align:left;font-size:13px;">Detail</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
      <a href="{BASE_URL}/monitors" style="display:inline-block;background:#16a34a;color:#fff;padding:10px 24px;border-radius:999px;text-decoration:none;font-weight:600;font-size:14px;margin:12px 0;">View Monitors</a>
      <p style="color:#94a3b8;font-size:12px;margin-top:24px;">INBXR — Email Authentication Monitoring</p>
    </div>
    """
    parts = []
    for i in changes.get("new_issues", []):
        parts.append(f"NEW: {i['message']}")
    for i in changes.get("resolved_issues", []):
        parts.append(f"RESOLVED: {i['message']}")
    text = f"DNS Auth Alert: {domain}\n\n" + "\n".join(parts)

    _send(to_email, f"DNS Auth Alert: {domain}", html, text)
