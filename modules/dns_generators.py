"""
InbXr — DNS Record Generators
Generates copy-paste SPF, DKIM, and DMARC TXT records.
Uses existing auth check results to suggest fixes, or builds from scratch.
"""

# ── Common ESP include mechanisms ─────────────────────
ESP_INCLUDES = {
    "google":       "include:_spf.google.com",
    "gmail":        "include:_spf.google.com",
    "microsoft365": "include:spf.protection.outlook.com",
    "outlook":      "include:spf.protection.outlook.com",
    "office365":    "include:spf.protection.outlook.com",
    "sendgrid":     "include:sendgrid.net",
    "mailchimp":    "include:servers.mcsv.net",
    "mailgun":      "include:mailgun.org",
    "ses":          "include:amazonses.com",
    "amazon_ses":   "include:amazonses.com",
    "postmark":     "include:spf.mtasv.net",
    "sparkpost":    "include:sparkpostmail.com",
    "sendinblue":   "include:sendinblue.com",
    "brevo":        "include:sendinblue.com",
    "klaviyo":      "include:_spf.klaviyo.com",
    "convertkit":   "include:_spf.convertkit.com",
    "hubspot":      "include:spf.hubspot.com",
    "zoho":         "include:zoho.com",
    "activecampaign": "include:emsd1.com",
    "campaignmonitor": "include:cmail1.com",
    "constantcontact": "include:spf.constantcontact.com",
    "drip":         "include:_spf.getdrip.com",
    "aweber":       "include:_spf.aweber.com",
    "godaddy":      "include:secureserver.net",
    "hostgator":    "include:websitewelcome.com",
    "bluehost":     "include:bluehost.com",
    "namecheap":    "include:privateemail.com",
}

# ── Common DKIM selectors by ESP ──────────────────────
ESP_DKIM_SELECTORS = {
    "google":       ["google"],
    "gmail":        ["google"],
    "microsoft365": ["selector1", "selector2"],
    "outlook":      ["selector1", "selector2"],
    "sendgrid":     ["s1", "s2", "smtpapi"],
    "mailchimp":    ["k1", "k2", "k3"],
    "mailgun":      ["smtp", "mailo", "mg"],
    "ses":          [],
    "postmark":     ["20200831", "pm"],
    "sparkpost":    ["sparkpost"],
    "klaviyo":      ["kl", "kl2"],
    "hubspot":      ["hs1", "hs2"],
    "zoho":         ["zoho"],
}

# ── DMARC policy descriptions ────────────────────────
DMARC_POLICIES = {
    "none":       "Monitor only — no enforcement. Good starting point.",
    "quarantine": "Failing emails sent to spam. Recommended after monitoring period.",
    "reject":     "Failing emails blocked entirely. Strongest protection.",
}


# ── MX hostname → ESP mapping for auto-detection ──────
MX_ESP_MAP = {
    "google.com":              "Google Workspace",
    "googlemail.com":          "Google Workspace",
    "aspmx.l.google.com":      "Google Workspace",
    "protection.outlook.com":  "Microsoft 365",
    "outlook.com":             "Microsoft 365",
    "pphosted.com":            "Proofpoint",
    "mimecast.com":            "Mimecast",
    "barracudanetworks.com":   "Barracuda",
    "messagelabs.com":         "Broadcom (Symantec)",
    "secureserver.net":        "GoDaddy",
    "zoho.com":                "Zoho Mail",
    "mailgun.org":             "Mailgun",
    "sendgrid.net":            "SendGrid",
    "amazonaws.com":           "Amazon SES",
    "mcsv.net":                "Mailchimp",
    "mandrillapp.com":         "Mailchimp / Mandrill",
    "mtasv.net":               "Postmark",
    "sparkpostmail.com":       "SparkPost",
    "hover.com":               "Hover",
    "emailsrvr.com":           "Rackspace",
    "hostgator.com":           "HostGator",
    "bluehost.com":            "Bluehost",
    "namecheap.com":           "Namecheap",
    "privateemail.com":        "Namecheap",
    "protonmail.ch":           "Proton Mail",
    "tutanota.de":             "Tuta",
    "fastmail.com":            "Fastmail",
    "icloud.com":              "Apple iCloud",
    "yahoodns.net":            "Yahoo",
}

# Map ESP display names to ESP_INCLUDES keys for fix generation
ESP_NAME_TO_KEY = {
    "Google Workspace": "google",
    "Microsoft 365":    "microsoft365",
    "Mailgun":          "mailgun",
    "SendGrid":         "sendgrid",
    "Amazon SES":       "ses",
    "Mailchimp":        "mailchimp",
    "Mailchimp / Mandrill": "mailchimp",
    "Postmark":         "postmark",
    "SparkPost":        "sparkpost",
    "Zoho Mail":        "zoho",
    "GoDaddy":          "godaddy",
    "Bluehost":         "bluehost",
    "Namecheap":        "namecheap",
    "HostGator":        "hostgator",
}


def detect_esp_from_mx(mx_records):
    """Detect the Email Service Provider from MX records.

    Args:
        mx_records: List of dicts with 'host' key, or list of (priority, host) tuples.

    Returns dict with detected, esp_name, esp_key, mx_host.
    """
    if not mx_records:
        return {"detected": False}

    for rec in mx_records:
        # Handle both dict format and tuple format
        if isinstance(rec, dict):
            host = (rec.get("host") or rec.get("exchange") or "").lower().rstrip(".")
        elif isinstance(rec, (list, tuple)) and len(rec) >= 2:
            host = str(rec[1]).lower().rstrip(".")
        else:
            continue

        # Try exact match first, then suffix match
        for pattern, esp_name in MX_ESP_MAP.items():
            if host == pattern or host.endswith("." + pattern):
                esp_key = ESP_NAME_TO_KEY.get(esp_name)
                return {
                    "detected": True,
                    "esp_name": esp_name,
                    "esp_key": esp_key,
                    "mx_host": host,
                }

    return {"detected": False}


def generate_spf(domain: str, esps: list = None, extra_ips: list = None,
                 extra_includes: list = None, mechanism: str = "-all") -> dict:
    """Generate an SPF TXT record.

    Args:
        domain: The domain name
        esps: List of ESP keys (e.g. ["google", "sendgrid"])
        extra_ips: Additional IP addresses to authorize
        extra_includes: Additional include: domains
        mechanism: Final mechanism (-all, ~all, ?all)

    Returns dict with record, host, explanation, warnings.
    """
    parts = ["v=spf1"]
    includes_used = []
    warnings = []
    lookup_count = 0

    # Add ESP includes
    for esp in (esps or []):
        key = esp.lower().strip().replace(" ", "").replace("-", "")
        inc = ESP_INCLUDES.get(key)
        if inc and inc not in includes_used:
            parts.append(inc)
            includes_used.append(inc)
            lookup_count += 1

    # Add extra includes
    for inc in (extra_includes or []):
        inc = inc.strip()
        if not inc:
            continue
        if not inc.startswith("include:"):
            inc = f"include:{inc}"
        if inc not in includes_used:
            parts.append(inc)
            includes_used.append(inc)
            lookup_count += 1

    # Add IP addresses
    for ip in (extra_ips or []):
        ip = ip.strip()
        if not ip:
            continue
        if ":" in ip:
            parts.append(f"ip6:{ip}")
        else:
            parts.append(f"ip4:{ip}")

    # Validate mechanism
    if mechanism not in ("-all", "~all", "?all"):
        mechanism = "-all"

    parts.append(mechanism)

    record = " ".join(parts)

    # Warnings
    if lookup_count > 10:
        warnings.append(f"SPF has {lookup_count} DNS lookups — the limit is 10. Remove unused includes or flatten nested lookups.")
    elif lookup_count > 7:
        warnings.append(f"SPF uses {lookup_count}/10 DNS lookups. Leave room for future additions.")

    if len(record) > 255:
        warnings.append(f"Record is {len(record)} characters — some DNS providers split records over 255 chars. Test with your provider.")

    if mechanism == "~all":
        warnings.append("~all (softfail) is less strict than -all (hardfail). Use -all once you've confirmed all legitimate senders are included.")
    elif mechanism == "?all":
        warnings.append("?all (neutral) provides almost no protection. Use -all for best deliverability.")

    if not esps and not extra_ips and not extra_includes:
        warnings.append("No senders specified — this record will block all email. Add your ESP or mail server.")

    mech_labels = {"-all": "Hard fail (recommended)", "~all": "Soft fail", "?all": "Neutral (not recommended)"}

    return {
        "record": record,
        "host": f"{domain}",
        "dns_name": f"{domain}",
        "dns_type": "TXT",
        "explanation": f"Authorizes {len(includes_used)} service(s) to send email for {domain}. "
                       f"Final policy: {mech_labels.get(mechanism, mechanism)}.",
        "lookup_count": lookup_count,
        "warnings": warnings,
    }


def generate_dmarc(domain: str, policy: str = "none", subdomain_policy: str = None,
                   rua_email: str = None, ruf_email: str = None,
                   pct: int = 100, alignment_spf: str = "r",
                   alignment_dkim: str = "r") -> dict:
    """Generate a DMARC TXT record.

    Args:
        domain: The domain name
        policy: "none", "quarantine", or "reject"
        subdomain_policy: Override for subdomains (optional)
        rua_email: Aggregate report email (optional)
        ruf_email: Forensic report email (optional)
        pct: Percentage of messages to apply policy to (1-100)
        alignment_spf: "r" (relaxed) or "s" (strict)
        alignment_dkim: "r" (relaxed) or "s" (strict)
    """
    if policy not in ("none", "quarantine", "reject"):
        policy = "none"

    parts = [f"v=DMARC1; p={policy}"]

    if subdomain_policy and subdomain_policy in ("none", "quarantine", "reject"):
        parts.append(f"sp={subdomain_policy}")

    if rua_email:
        rua = rua_email.strip()
        if not rua.startswith("mailto:"):
            rua = f"mailto:{rua}"
        parts.append(f"rua={rua}")

    if ruf_email:
        ruf = ruf_email.strip()
        if not ruf.startswith("mailto:"):
            ruf = f"mailto:{ruf}"
        parts.append(f"ruf={ruf}")

    if pct != 100 and 1 <= pct <= 99:
        parts.append(f"pct={pct}")

    if alignment_spf == "s":
        parts.append("aspf=s")

    if alignment_dkim == "s":
        parts.append("adkim=s")

    record = "; ".join(parts)
    warnings = []

    if policy == "none" and not rua_email:
        warnings.append("With p=none and no rua, you won't receive any reports. Add a rua email to collect data.")

    if policy == "none":
        warnings.append("p=none is monitoring only — it won't prevent spoofing. Move to quarantine after 2-4 weeks of clean reports.")

    if rua_email and not rua_email.endswith(f"@{domain}"):
        ext_domain = rua_email.split("@")[-1] if "@" in rua_email else ""
        if ext_domain:
            warnings.append(f"External report address ({ext_domain}) requires a DNS authorization record: "
                            f"{domain}._report._dmarc.{ext_domain} TXT \"v=DMARC1\"")

    return {
        "record": record,
        "host": f"_dmarc.{domain}",
        "dns_name": f"_dmarc.{domain}",
        "dns_type": "TXT",
        "explanation": f"DMARC policy for {domain}: {DMARC_POLICIES.get(policy, policy)}",
        "policy": policy,
        "warnings": warnings,
    }


def generate_dkim_instructions(domain: str, esp: str = None, selector: str = None) -> dict:
    """Generate DKIM setup instructions and expected record format.

    DKIM keys are generated by the ESP — we provide the setup guidance.
    """
    esp_key = (esp or "").lower().strip().replace(" ", "").replace("-", "")
    selectors = ESP_DKIM_SELECTORS.get(esp_key, [])

    if selector:
        selectors = [selector] + [s for s in selectors if s != selector]

    instructions = []
    record_example = None
    host_example = None

    if esp_key in ("google", "gmail"):
        instructions = [
            "In Google Admin Console, go to Apps > Google Workspace > Gmail > Authenticate Email",
            "Click 'Generate New Record' — choose 2048-bit key length",
            "Google generates the DKIM key — copy the TXT record value",
            f"Add a TXT record at: google._domainkey.{domain}",
            "Return to Google Admin and click 'Start Authentication'",
            "Allow 24-48 hours for DNS propagation",
        ]
        host_example = f"google._domainkey.{domain}"
        record_example = f"v=DKIM1; k=rsa; p=<your-public-key-from-google-admin>"

    elif esp_key in ("microsoft365", "outlook", "office365"):
        instructions = [
            "In Microsoft 365 Defender, go to Email & Collaboration > Policies > Threat Policies > Email Authentication",
            "Select your domain and click 'Create DKIM keys'",
            "Microsoft generates two CNAME records (selector1 and selector2)",
            f"Add CNAME: selector1._domainkey.{domain} → selector1-{domain.replace('.', '-')}._domainkey.<tenant>.onmicrosoft.com",
            f"Add CNAME: selector2._domainkey.{domain} → selector2-{domain.replace('.', '-')}._domainkey.<tenant>.onmicrosoft.com",
            "Return to Microsoft 365 and enable DKIM signing",
        ]
        host_example = f"selector1._domainkey.{domain}"
        record_example = "CNAME → selector1-yourdomain-com._domainkey.yourtenant.onmicrosoft.com"

    elif esp_key == "sendgrid":
        instructions = [
            "In SendGrid dashboard, go to Settings > Sender Authentication > Domain Authentication",
            "Enter your domain and complete the wizard",
            "SendGrid provides 3 CNAME records to add to your DNS",
            f"Add CNAMEs for s1._domainkey.{domain} and s2._domainkey.{domain}",
            "Return to SendGrid and click 'Verify'",
        ]
        host_example = f"s1._domainkey.{domain}"
        record_example = "CNAME → s1.domainkey.u12345.wl.sendgrid.net"

    elif esp_key in ("mailchimp",):
        instructions = [
            "In Mailchimp, go to Website > Domains > Manage > Authentication",
            "Click 'Enable DKIM' for your domain",
            "Mailchimp provides a CNAME record to add",
            f"Add CNAME for k1._domainkey.{domain}",
            "Return to Mailchimp and verify",
        ]
        host_example = f"k1._domainkey.{domain}"
        record_example = "CNAME → dkim.mcsv.net"

    elif esp_key in ("mailgun",):
        instructions = [
            "In Mailgun dashboard, go to Sending > Domains > your domain > DNS Records",
            "Mailgun shows the exact TXT or CNAME records needed",
            f"Add the DKIM record at the selector._domainkey.{domain} host",
            "Click 'Verify DNS Settings' in Mailgun",
        ]
        host_example = f"smtp._domainkey.{domain}"

    elif esp_key in ("ses", "amazon_ses"):
        instructions = [
            "In AWS SES Console, go to Verified Identities > your domain",
            "Under Authentication tab, click 'Generate DKIM' (Easy DKIM)",
            "SES provides 3 CNAME records to add to your DNS",
            "Add all 3 CNAME records exactly as shown",
            "SES automatically starts signing once DNS propagates",
        ]
        host_example = f"<token>._domainkey.{domain}"
        record_example = "CNAME → <token>.dkim.amazonses.com"

    else:
        instructions = [
            "Check your email provider's documentation for DKIM setup",
            "Your ESP will generate the DKIM key pair — you cannot create it manually",
            "You'll need to add a TXT or CNAME record at <selector>._domainkey." + domain,
            "Common selectors: " + (", ".join(selectors[:5]) if selectors else "default, mail, selector1"),
            "After adding the DNS record, enable DKIM signing in your ESP dashboard",
        ]
        sel = selectors[0] if selectors else "default"
        host_example = f"{sel}._domainkey.{domain}"
        record_example = f"v=DKIM1; k=rsa; p=<public-key-from-your-esp>"

    return {
        "selector": selectors[0] if selectors else None,
        "selectors": selectors,
        "host_example": host_example,
        "record_example": record_example,
        "dns_type": "TXT (or CNAME depending on ESP)",
        "instructions": instructions,
        "explanation": f"DKIM digitally signs your emails so receivers can verify they weren't altered in transit. "
                       f"Your ESP ({esp or 'email provider'}) generates the signing key — you add the public key to DNS.",
        "warnings": [
            "DKIM keys are generated by your ESP — you cannot create them manually here.",
            "If you switch ESPs, you'll need to set up DKIM again with the new provider's keys.",
        ],
    }


def generate_mta_sts(domain: str, mode: str = "testing",
                     mx_patterns: list = None, max_age: int = 604800) -> dict:
    """Generate MTA-STS DNS record and policy file content.

    Args:
        domain: The domain name
        mode: "testing", "enforce", or "none"
        mx_patterns: MX hostname patterns (e.g. ["mail.example.com", "*.example.com"])
        max_age: Policy cache lifetime in seconds (default 7 days)
    """
    import time

    if mode not in ("testing", "enforce", "none"):
        mode = "testing"

    # Generate a unique policy ID based on timestamp
    sts_id = str(int(time.time()))

    dns_record = f"v=STSv1; id={sts_id}"
    warnings = []

    if not mx_patterns:
        mx_patterns = [f"*.{domain}"]
        warnings.append("Using wildcard MX pattern — replace with your actual MX hostnames for tighter security.")

    # Build the policy file content
    policy_lines = [f"version: STSv1", f"mode: {mode}"]
    for mx in mx_patterns:
        policy_lines.append(f"mx: {mx}")
    policy_lines.append(f"max_age: {max_age}")
    policy_text = "\n".join(policy_lines)

    if mode == "testing":
        warnings.append("mode: testing will report failures but not reject mail. Switch to 'enforce' once confirmed working.")

    if max_age < 86400:
        warnings.append(f"max_age={max_age}s is very short. Recommended minimum: 86400 (1 day), ideal: 604800 (1 week).")

    return {
        "dns_record": dns_record,
        "dns_host": f"_mta-sts.{domain}",
        "dns_type": "TXT",
        "policy_text": policy_text,
        "policy_url": f"https://mta-sts.{domain}/.well-known/mta-sts.txt",
        "policy_host": f"mta-sts.{domain}",
        "mode": mode,
        "sts_id": sts_id,
        "mx_patterns": mx_patterns,
        "max_age": max_age,
        "warnings": warnings,
        "explanation": ("MTA-STS enforces TLS encryption for inbound email. "
                        "Receiving servers that support MTA-STS will refuse to deliver mail over unencrypted connections. "
                        "Requires both a DNS TXT record AND a policy file hosted at the policy URL."),
        "setup_steps": [
            f"1. Add a TXT record at _mta-sts.{domain} with value: {dns_record}",
            f"2. Create a web server at mta-sts.{domain} (can be a subdomain with an A/CNAME record)",
            f"3. Host the policy file at https://mta-sts.{domain}/.well-known/mta-sts.txt",
            "4. The policy file must be served over HTTPS with a valid certificate",
            "5. Start with mode: testing, then switch to mode: enforce after confirming no issues",
        ],
    }


def generate_tls_rpt(domain: str, rua_email: str = None,
                     rua_https: str = None) -> dict:
    """Generate a TLS-RPT DNS record.

    Args:
        domain: The domain name
        rua_email: Email address for TLS failure reports (mailto:)
        rua_https: HTTPS endpoint for TLS failure reports (optional)
    """
    warnings = []
    destinations = []

    if rua_email:
        email = rua_email.strip()
        if not email.startswith("mailto:"):
            email = f"mailto:{email}"
        destinations.append(email)
    if rua_https:
        url = rua_https.strip()
        if not url.startswith("https://"):
            warnings.append("HTTPS reporting endpoint must use https://")
        destinations.append(url)

    if not destinations:
        destinations.append(f"mailto:tls-reports@{domain}")
        warnings.append(f"Using default report address tls-reports@{domain} — ensure this mailbox exists.")

    rua_value = ",".join(destinations)
    record = f"v=TLSRPTv1; rua={rua_value}"

    if rua_email and not rua_email.endswith(f"@{domain}"):
        ext_domain = rua_email.split("@")[-1] if "@" in rua_email else ""
        if ext_domain:
            warnings.append(f"External report address ({ext_domain}) — the receiving domain must accept reports for {domain}.")

    return {
        "record": record,
        "host": f"_smtp._tls.{domain}",
        "dns_name": f"_smtp._tls.{domain}",
        "dns_type": "TXT",
        "rua": rua_value,
        "warnings": warnings,
        "explanation": ("TLS-RPT enables receiving servers to send you reports when TLS connections to your domain fail. "
                        "This helps you detect and fix encryption issues before they cause delivery failures. "
                        "Works best alongside MTA-STS."),
    }


def generate_from_auth_results(domain: str, auth_categories: list,
                               sender_email: str = None) -> dict:
    """Smart generator: analyze existing auth results and suggest fixes.

    Takes the auth.categories from a ReputationChecker result and generates
    records for anything that's missing or misconfigured.
    """
    suggestions = []
    report_email = sender_email or f"dmarc-reports@{domain}"

    # Index categories by label
    cats = {c.get("label", "").upper(): c for c in (auth_categories or [])}

    # ── SPF ───────────────────────────────────────────
    spf = cats.get("SPF", {})
    spf_status = spf.get("status", "missing")

    if spf_status == "missing":
        result = generate_spf(domain, mechanism="-all")
        result["_action"] = "create"
        result["_title"] = "Create SPF Record"
        result["_description"] = "No SPF record found. Add this TXT record to authorize your sending servers."
        result["_note"] = "Replace the includes with your actual email service providers (Google, SendGrid, etc.)"
        suggestions.append({"type": "spf", **result})

    elif spf_status in ("warning", "fail"):
        existing = spf.get("record", "")
        issues = spf.get("issues", [])
        mechanism = spf.get("mechanism", "~all")

        notes = []
        if "+all" in str(mechanism):
            notes.append("CRITICAL: Change +all to -all — +all authorizes the entire internet to send as you")
        elif "~all" in str(mechanism):
            notes.append("Upgrade ~all to -all for stricter enforcement")
        for issue in issues:
            notes.append(str(issue))

        suggestions.append({
            "type": "spf",
            "_action": "fix",
            "_title": "Fix SPF Record",
            "_description": "Your current SPF record has issues that hurt deliverability.",
            "current_record": existing,
            "issues": notes,
            "host": domain,
            "dns_name": domain,
            "dns_type": "TXT",
            "warnings": notes,
        })

    # ── DKIM ──────────────────────────────────────────
    dkim = cats.get("DKIM", {})
    dkim_status = dkim.get("status", "missing")

    if dkim_status in ("missing", "fail"):
        result = generate_dkim_instructions(domain)
        result["_action"] = "create" if dkim_status == "missing" else "fix"
        result["_title"] = "Set Up DKIM" if dkim_status == "missing" else "Fix DKIM Configuration"
        result["_description"] = ("No DKIM record found. DKIM signing must be enabled through your ESP."
                                  if dkim_status == "missing"
                                  else "DKIM record found but not valid. Reconfigure through your ESP.")
        suggestions.append({"type": "dkim", **result})

    # ── DMARC ─────────────────────────────────────────
    dmarc = cats.get("DMARC", {})
    dmarc_status = dmarc.get("status", "missing")

    if dmarc_status == "missing":
        result = generate_dmarc(
            domain, policy="none", rua_email=report_email,
        )
        result["_action"] = "create"
        result["_title"] = "Create DMARC Record"
        result["_description"] = ("No DMARC record found. Start with p=none to monitor, "
                                  "then upgrade to quarantine/reject after reviewing reports.")
        suggestions.append({"type": "dmarc", **result})

    elif dmarc_status == "warning":
        policy = dmarc.get("policy", "none")
        has_rua = dmarc.get("has_rua", False)
        issues = dmarc.get("issues", [])

        if policy == "none":
            # Suggest upgrading to quarantine
            result = generate_dmarc(
                domain, policy="quarantine",
                rua_email=report_email if not has_rua else None,
            )
            result["_action"] = "upgrade"
            result["_title"] = "Upgrade DMARC Policy"
            result["_description"] = ("Your DMARC is set to p=none (monitoring only). "
                                      "Upgrade to quarantine to start filtering spoofed emails.")
            result["current_record"] = dmarc.get("record", "")
            suggestions.append({"type": "dmarc", **result})

        elif not has_rua:
            result = generate_dmarc(
                domain, policy=policy, rua_email=report_email,
            )
            result["_action"] = "fix"
            result["_title"] = "Add DMARC Reporting"
            result["_description"] = "Your DMARC record has no report address (rua). Add one to receive aggregate reports."
            result["current_record"] = dmarc.get("record", "")
            suggestions.append({"type": "dmarc", **result})

    # ── MTA-STS ────────────────────────────────────────
    mta_sts = cats.get("MTA-STS", {})
    mta_sts_status = mta_sts.get("status", "missing")

    if mta_sts_status == "missing":
        result = generate_mta_sts(domain, mode="testing")
        result["_action"] = "create"
        result["_title"] = "Set Up MTA-STS"
        result["_description"] = ("No MTA-STS record found. MTA-STS enforces TLS encryption for inbound mail, "
                                  "preventing downgrade attacks.")
        suggestions.append({"type": "mta_sts", **result})
    elif mta_sts_status == "warning":
        policy = mta_sts.get("policy", {})
        if policy and policy.get("mode") == "testing":
            result = generate_mta_sts(domain, mode="enforce")
            result["_action"] = "upgrade"
            result["_title"] = "Upgrade MTA-STS to Enforce"
            result["_description"] = ("MTA-STS is in testing mode. Upgrade to enforce mode "
                                      "to actively require TLS for inbound mail.")
            suggestions.append({"type": "mta_sts", **result})

    # ── TLS-RPT ───────────────────────────────────────
    tls_rpt = cats.get("TLS-RPT", {})
    tls_rpt_status = tls_rpt.get("status", "missing")

    if tls_rpt_status == "missing":
        result = generate_tls_rpt(domain, rua_email=report_email)
        result["_action"] = "create"
        result["_title"] = "Set Up TLS-RPT"
        result["_description"] = ("No TLS-RPT record found. TLS-RPT lets you receive reports about "
                                  "TLS delivery failures, helping you detect encryption issues.")
        suggestions.append({"type": "tls_rpt", **result})

    return {
        "domain": domain,
        "suggestions": suggestions,
        "has_suggestions": len(suggestions) > 0,
    }
