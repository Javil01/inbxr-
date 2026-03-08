"""
INBXR — Sender Reputation & Authentication Checker
Performs live DNS lookups for SPF, DKIM, DMARC, BIMI,
PTR / FCrDNS, and parallel DNSBL checks.
"""

import re
import ipaddress
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import dns.resolver
import dns.exception
import dns.reversename

# ── DKIM selectors to try when none is specified ──────
COMMON_SELECTORS = [
    # Generic
    "default", "mail", "dkim", "email", "key1", "key2",
    # Google Workspace
    "google",
    # Microsoft 365
    "selector1", "selector2",
    # Mailchimp / Mandrill
    "k1", "k2", "k3",
    # SendGrid
    "s1", "s2", "s3", "em", "sm",
    # Amazon SES
    "amazonses",
    # AWeber
    "aweber_key_a", "aweber_key_b", "aweber_key_c", "aweber_key_d",
    # Klaviyo
    "klaviyo",
    # HubSpot
    "hs1", "hs2",
    # ActiveCampaign
    "ac",
    # ConvertKit
    "ck1", "ck2",
    # Constant Contact
    "cc",
    # Brevo / Sendinblue
    "brevo", "sendinblue",
    # Campaign Monitor
    "cm",
    # Marketo
    "mkt", "marketo",
    # Drip
    "drip",
    # Mailgun
    "mg", "pic",
    # Postmark
    "pm",
    # Proton
    "protonmail",
    # Other common patterns
    "dkim1", "dkim2", "smtp", "outbound",
]

# ── IP-based DNSBL zones ──────────────────────────────
IP_DNSBLS = [
    {"zone": "zen.spamhaus.org",       "name": "Spamhaus ZEN",    "weight": "critical",
     "info": "Industry standard. Combines SBL (spam sources), XBL (exploited IPs), and PBL (policy block list)."},
    {"zone": "bl.spamcop.net",         "name": "SpamCop",         "weight": "major",
     "info": "User-reported spam. Aggressive but decays quickly (24–48 h)."},
    {"zone": "b.barracudacentral.org", "name": "Barracuda BRBL",  "weight": "major",
     "info": "Used by Barracuda Networks appliances worldwide."},
    {"zone": "cbl.abuseat.org",        "name": "CBL",             "weight": "major",
     "info": "Detects spambot behavior. Feeds into Spamhaus XBL."},
    {"zone": "dnsbl.sorbs.net",        "name": "SORBS",           "weight": "moderate",
     "info": "Spam and Open Relay Blocking System."},
    {"zone": "spam.dnsbl.sorbs.net",   "name": "SORBS Spam",      "weight": "moderate",
     "info": "IPs that sent spam to SORBS honeypots."},
    {"zone": "dnsbl-1.uceprotect.net", "name": "UCEPROTECT L1",   "weight": "moderate",
     "info": "Individual IP spam sender list."},
    {"zone": "psbl.surriel.com",       "name": "PSBL",            "weight": "moderate",
     "info": "Passive spam block list. Automated trap-based."},
    {"zone": "ix.dnsbl.manitu.net",    "name": "NiX Spam",        "weight": "moderate",
     "info": "Widely used in Europe. Fast decay on good behavior."},
    {"zone": "noptr.spamrats.com",     "name": "SPAMRATS NoPtr",  "weight": "minor",
     "info": "Flags IPs with no valid PTR record."},
]

# ── Domain-based DNSBL zones ─────────────────────────
DOMAIN_DNSBLS = [
    {"zone": "dbl.spamhaus.org",   "name": "Spamhaus DBL",  "weight": "critical",
     "info": "Domain blocklist. Listed domains appear in spam campaigns."},
    {"zone": "multi.surbl.org",    "name": "SURBL Multi",   "weight": "major",
     "info": "URI blocklist used by many spam filters to check links."},
    {"zone": "dbl.invaluement.com","name": "ivmSIP/24 DBL", "weight": "minor",
     "info": "Invaluement domain reputation list."},
]

# ── Scoring penalties ─────────────────────────────────
WEIGHT_PENALTY = {"critical": 30, "major": 20, "moderate": 12, "minor": 6}


def _make_resolver() -> dns.resolver.Resolver:
    """Return a resolver pointed at public DNS — required for Windows reliability."""
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = ["8.8.8.8", "1.1.1.1", "8.8.4.4"]
    r.timeout  = 2.5
    r.lifetime = 5.0
    return r


def _get_txt(resolver, name: str) -> tuple[list[str], str | None]:
    """Return (records, error_code). records is a list of decoded TXT strings."""
    try:
        answers = resolver.resolve(name, "TXT")
        result = []
        for rdata in answers:
            txt = "".join(s.decode("utf-8", errors="replace") for s in rdata.strings)
            result.append(txt)
        return result, None
    except dns.resolver.NXDOMAIN:
        return [], "NXDOMAIN"
    except dns.resolver.NoAnswer:
        return [], "NoAnswer"
    except dns.exception.Timeout:
        return [], "Timeout"
    except Exception as e:
        return [], str(e)


class ReputationChecker:
    def __init__(self, domain: str, sender_ip: str = None, dkim_selector: str = None):
        self.domain        = domain.lower().strip().rstrip(".")
        self.sender_ip     = sender_ip.strip() if sender_ip else None
        self.dkim_selector = dkim_selector.strip().lower() if dkim_selector else None
        self.resolver      = _make_resolver()
        self._flags        = []   # {severity, category, item, recommendation}

    # ════════════════════════════════════════════════════
    #  AUTH CHECKS
    # ════════════════════════════════════════════════════

    def _check_spf(self) -> dict:
        records, err = _get_txt(self.resolver, self.domain)
        spf = next((r for r in records if r.startswith("v=spf1")), None)

        if not spf:
            self._flags.append({
                "severity": "high", "category": "SPF",
                "item": "No SPF record found",
                "recommendation": (
                    "Add a TXT record to your DNS: "
                    "v=spf1 include:your-esp.com ~all  "
                    "Replace 'your-esp.com' with your email provider's SPF include."
                ),
            })
            return {"status": "missing", "score": 0, "max": 25, "record": None, "issues": []}

        issues = []
        score  = 10  # base for having any SPF record

        # Determine the all mechanism
        if "+all" in spf:
            issues.append("+all allows any server to send as you — extremely dangerous")
            self._flags.append({
                "severity": "critical", "category": "SPF",
                "item": "SPF uses +all (pass all senders)",
                "recommendation": "Change +all to -all immediately. +all negates the purpose of SPF and lets anyone spoof your domain.",
            })
        elif "-all" in spf:
            score += 10
        elif "~all" in spf:
            score += 6
            issues.append("~all (soft fail) is configured — consider upgrading to -all for strict enforcement")
            self._flags.append({
                "severity": "medium", "category": "SPF",
                "item": "SPF uses ~all (soft fail)",
                "recommendation": "Upgrade to -all (hard fail) once you've confirmed all sending sources are in your SPF record.",
            })
        elif "?all" in spf:
            issues.append("?all (neutral) provides no enforcement — equivalent to having no SPF")
            self._flags.append({
                "severity": "high", "category": "SPF",
                "item": "SPF uses ?all (neutral)",
                "recommendation": "Replace ?all with -all or at minimum ~all to give receiving servers enforcement guidance.",
            })

        # Count DNS lookup mechanisms (RFC 7208 limit: 10)
        lookup_mechanisms = re.findall(r'\b(include:|a[: ]|mx[: ]|ptr[: ]|exists:|redirect=)', spf)
        if len(lookup_mechanisms) > 10:
            score = max(0, score - 5)
            issues.append(f"SPF has {len(lookup_mechanisms)} DNS lookups — exceeds the RFC 7208 limit of 10 (causes PermError)")
            self._flags.append({
                "severity": "high", "category": "SPF",
                "item": f"SPF exceeds 10 DNS lookup limit ({len(lookup_mechanisms)} found)",
                "recommendation": "Flatten your SPF record using a tool like dmarcian.com/spf-survey to reduce DNS lookups below 10.",
            })
        elif len(lookup_mechanisms) >= 8:
            issues.append(f"Approaching the 10 DNS lookup limit ({len(lookup_mechanisms)}/10)")

        # Award remaining points for valid structure
        if "-all" in spf or "~all" in spf:
            score += 5  # well-formed all

        status = "pass" if score >= 20 else ("warning" if score >= 10 else "fail")
        return {
            "status": status, "score": min(25, score), "max": 25,
            "record": spf, "issues": issues,
            "mechanism": "-all" if "-all" in spf else ("~all" if "~all" in spf else ("?all" if "?all" in spf else ("+all" if "+all" in spf else "none"))),
        }

    def _check_dkim(self) -> dict:
        selectors_to_try = (
            [self.dkim_selector] if self.dkim_selector
            else COMMON_SELECTORS
        )
        tried = []

        for selector in selectors_to_try:
            name = f"{selector}._domainkey.{self.domain}"
            records, err = _get_txt(self.resolver, name)
            tried.append(selector)

            dkim_rec = next((r for r in records if "v=DKIM1" in r or "p=" in r), None)
            if not dkim_rec:
                continue

            # Check if key is revoked (empty p=)
            p_match = re.search(r'p=([^;]*)', dkim_rec)
            key_value = p_match.group(1).strip() if p_match else ""

            if not key_value:
                return {
                    "status": "fail", "score": 5, "max": 25,
                    "record": dkim_rec[:120], "selector": selector,
                    "selectors_tried": tried, "issues": ["DKIM key is revoked (p= is empty)"],
                }

            return {
                "status": "pass", "score": 25, "max": 25,
                "record": (dkim_rec[:80] + "…") if len(dkim_rec) > 80 else dkim_rec,
                "selector": selector, "selectors_tried": tried, "issues": [],
            }

        self._flags.append({
            "severity": "high", "category": "DKIM",
            "item": f"No DKIM record found (tried: {', '.join(tried[:6])})",
            "recommendation": (
                "Generate a DKIM key pair in your ESP and publish the TXT record at "
                "{selector}._domainkey." + self.domain + ". "
                "Gmail and Yahoo now require DKIM for bulk senders."
            ),
        })
        return {
            "status": "missing", "score": 0, "max": 25,
            "record": None, "selector": None,
            "selectors_tried": tried, "issues": ["No DKIM record found on common selectors"],
        }

    def _check_dmarc(self) -> dict:
        records, err = _get_txt(self.resolver, f"_dmarc.{self.domain}")
        dmarc = next((r for r in records if r.startswith("v=DMARC1")), None)

        if not dmarc:
            self._flags.append({
                "severity": "critical", "category": "DMARC",
                "item": "No DMARC record found",
                "recommendation": (
                    "Add a TXT record at _dmarc." + self.domain + ": "
                    "v=DMARC1; p=quarantine; rua=mailto:dmarc@" + self.domain + "; pct=100  "
                    "Start with p=none to monitor, then move to quarantine/reject."
                ),
            })
            return {"status": "missing", "score": 0, "max": 30, "record": None,
                    "policy": None, "pct": None, "issues": []}

        issues = []
        score  = 8  # base for having a DMARC record

        p_match = re.search(r'\bp=(\w+)', dmarc)
        policy  = p_match.group(1).lower() if p_match else "none"

        if policy == "reject":
            score += 17
        elif policy == "quarantine":
            score += 12
            issues.append("Policy is 'quarantine' — consider upgrading to p=reject for full enforcement")
        elif policy == "none":
            score += 4
            issues.append("Policy is 'none' (monitor-only) — no protection against spoofing")
            self._flags.append({
                "severity": "high", "category": "DMARC",
                "item": "DMARC policy is p=none (no enforcement)",
                "recommendation": "Move from p=none → p=quarantine → p=reject gradually. p=none provides no protection against domain spoofing.",
            })

        pct_match = re.search(r'\bpct=(\d+)', dmarc)
        pct       = int(pct_match.group(1)) if pct_match else 100
        if pct < 100 and policy != "none":
            issues.append(f"pct={pct} — DMARC policy only applies to {pct}% of messages")
            score = max(0, score - 3)

        has_rua = bool(re.search(r'\brua=', dmarc))
        has_ruf = bool(re.search(r'\bruf=', dmarc))
        if has_rua:
            score += 3
        else:
            issues.append("No aggregate report URI (rua=) — you won't receive DMARC reports")
            self._flags.append({
                "severity": "medium", "category": "DMARC",
                "item": "DMARC is missing rua= (aggregate reporting)",
                "recommendation": f"Add rua=mailto:dmarc@{self.domain} to your DMARC record to receive weekly aggregate reports.",
            })

        if has_ruf:
            score += 2

        status = "pass" if score >= 22 else ("warning" if score >= 12 else "fail")
        return {
            "status": status, "score": min(30, score), "max": 30,
            "record": dmarc, "policy": policy, "pct": pct,
            "has_rua": has_rua, "has_ruf": has_ruf, "issues": issues,
        }

    def _check_bimi(self) -> dict:
        records, err = _get_txt(self.resolver, f"default._bimi.{self.domain}")
        bimi = next((r for r in records if r.startswith("v=BIMI1")), None)

        if not bimi:
            # BIMI is optional / advanced — only flag as info
            return {"status": "missing", "score": 0, "max": 20,
                    "record": None, "issues": ["BIMI not configured (optional — requires p=quarantine or p=reject DMARC)"]}

        has_logo = bool(re.search(r'\bl=https?://', bimi))
        has_vmc  = bool(re.search(r'\ba=https?://', bimi))
        score    = 10 if has_logo else 5
        if has_vmc:
            score = 20

        return {
            "status": "pass", "score": score, "max": 20,
            "record": bimi, "has_logo": has_logo, "has_vmc": has_vmc, "issues": [],
        }

    # ════════════════════════════════════════════════════
    #  REPUTATION CHECKS
    # ════════════════════════════════════════════════════

    def _check_ptr(self) -> dict:
        if not self.sender_ip:
            return {"checked": False, "hostname": None, "found": False}
        try:
            rev_name = dns.reversename.from_address(self.sender_ip)
            answers  = self.resolver.resolve(rev_name, "PTR")
            hostname = str(answers[0]).rstrip(".")
            return {"checked": True, "hostname": hostname, "found": True}
        except dns.resolver.NXDOMAIN:
            self._flags.append({
                "severity": "medium", "category": "Reputation",
                "item": f"No PTR (reverse DNS) record for {self.sender_ip}",
                "recommendation": "Ask your hosting provider or ISP to set a PTR record for your sending IP. Many receiving servers check for this.",
            })
            return {"checked": True, "hostname": None, "found": False}
        except Exception:
            return {"checked": True, "hostname": None, "found": False, "error": "lookup failed"}

    def _check_fcrdns(self, ptr_hostname: str) -> dict:
        if not ptr_hostname or not self.sender_ip:
            return {"valid": False, "checked": False}
        try:
            answers  = self.resolver.resolve(ptr_hostname, "A")
            resolved = [str(r) for r in answers]
            valid    = self.sender_ip in resolved
            if not valid:
                self._flags.append({
                    "severity": "medium", "category": "Reputation",
                    "item": f"FCrDNS mismatch: PTR points to {ptr_hostname} but forward lookup returned {resolved}",
                    "recommendation": "Ensure your PTR record hostname resolves back to the same IP. This bidirectional check is required by many spam filters.",
                })
            return {"valid": valid, "checked": True, "resolved": resolved}
        except Exception:
            return {"valid": False, "checked": True, "resolved": []}

    def _check_mx(self) -> dict:
        try:
            answers = self.resolver.resolve(self.domain, "MX")
            records = sorted(
                [(r.preference, str(r.exchange).rstrip(".")) for r in answers],
                key=lambda x: x[0]
            )
            return {"found": True, "records": records}
        except Exception:
            return {"found": False, "records": []}

    def _query_ip_dnsbl(self, ip_str: str, entry: dict) -> dict:
        result = {"zone": entry["zone"], "name": entry["name"],
                  "type": "ip", "weight": entry["weight"],
                  "info": entry["info"], "listed": False, "reason": None, "error": None}
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj.version == 4:
                rev = ".".join(reversed(ip_str.split(".")))
            else:
                expanded = ip_obj.exploded.replace(":", "")
                rev = ".".join(reversed(expanded))

            query = f"{rev}.{entry['zone']}"
            r = _make_resolver()  # own resolver per thread
            try:
                r.resolve(query, "A")
                result["listed"] = True
                try:
                    txts = r.resolve(query, "TXT")
                    for rdata in txts:
                        result["reason"] = "".join(
                            s.decode("utf-8", errors="replace") for s in rdata.strings
                        )
                        break
                except Exception:
                    pass
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                result["listed"] = False
        except Exception as e:
            result["error"] = str(e)
        return result

    def _query_domain_dnsbl(self, domain: str, entry: dict) -> dict:
        result = {"zone": entry["zone"], "name": entry["name"],
                  "type": "domain", "weight": entry["weight"],
                  "info": entry["info"], "listed": False, "reason": None, "error": None}
        try:
            query = f"{domain}.{entry['zone']}"
            r = _make_resolver()
            try:
                r.resolve(query, "A")
                result["listed"] = True
                try:
                    txts = r.resolve(query, "TXT")
                    for rdata in txts:
                        result["reason"] = "".join(
                            s.decode("utf-8", errors="replace") for s in rdata.strings
                        )
                        break
                except Exception:
                    pass
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                result["listed"] = False
        except Exception as e:
            result["error"] = str(e)
        return result

    def _run_dnsbl_checks(self) -> list:
        futures_map = {}
        results     = []

        with ThreadPoolExecutor(max_workers=14) as pool:
            # IP blocklists (only if IP provided)
            if self.sender_ip:
                for entry in IP_DNSBLS:
                    f = pool.submit(self._query_ip_dnsbl, self.sender_ip, entry)
                    futures_map[f] = entry

            # Domain blocklists (always)
            for entry in DOMAIN_DNSBLS:
                f = pool.submit(self._query_domain_dnsbl, self.domain, entry)
                futures_map[f] = entry

            for future in as_completed(futures_map, timeout=18):
                try:
                    results.append(future.result())
                except Exception:
                    entry = futures_map[future]
                    results.append({"zone": entry["zone"], "name": entry["name"],
                                    "type": "?", "weight": entry["weight"],
                                    "info": entry["info"], "listed": False,
                                    "reason": None, "error": "timed out"})

        # Sort: listed first, then by weight severity
        weight_order = {"critical": 0, "major": 1, "moderate": 2, "minor": 3}
        results.sort(key=lambda x: (0 if x["listed"] else 1, weight_order.get(x["weight"], 4)))
        return results

    # ════════════════════════════════════════════════════
    #  SCORING
    # ════════════════════════════════════════════════════

    def _auth_label(self, score: int) -> tuple[str, str]:
        if score >= 85: return "Excellent", "green"
        if score >= 70: return "Good",      "blue"
        if score >= 50: return "Fair",      "yellow"
        if score >= 25: return "Poor",      "orange"
        return "Critical", "red"

    def _rep_label(self, score: int) -> tuple[str, str]:
        if score >= 95: return "Excellent", "green"
        if score >= 80: return "Clean",     "blue"
        if score >= 60: return "Caution",   "yellow"
        if score >= 40: return "Poor",      "orange"
        return "Blocklisted", "red"

    def _combined_label(self, score: int) -> tuple[str, str]:
        if score >= 90: return "Excellent",     "green"
        if score >= 75: return "Good Standing", "blue"
        if score >= 60: return "Fair",          "yellow"
        if score >= 40: return "Needs Work",    "orange"
        return "Severe Issues", "red"

    # ════════════════════════════════════════════════════
    #  PUBLIC ENTRY POINT
    # ════════════════════════════════════════════════════

    def analyze(self) -> dict:
        t0 = time.monotonic()

        # ── Auth checks (sequential — build on each other) ──
        spf   = self._check_spf()
        dkim  = self._check_dkim()
        dmarc = self._check_dmarc()
        bimi  = self._check_bimi()

        auth_score = spf["score"] + dkim["score"] + dmarc["score"] + bimi["score"]
        auth_score = min(100, auth_score)
        auth_label, auth_color = self._auth_label(auth_score)

        auth_summary_parts = []
        for name, rec in [("SPF", spf), ("DKIM", dkim), ("DMARC", dmarc), ("BIMI", bimi)]:
            st = rec["status"]
            if st == "pass":
                auth_summary_parts.append(f"✓ {name}")
            elif st == "warning":
                auth_summary_parts.append(f"⚠ {name}")
            elif st == "missing":
                auth_summary_parts.append(f"✗ {name}")
            else:
                auth_summary_parts.append(f"✗ {name}")

        # ── Reputation checks (DNSBL parallel + PTR/FCrDNS) ──
        dnsbl_results = self._run_dnsbl_checks()
        ptr           = self._check_ptr()
        fcrdns        = self._check_fcrdns(ptr.get("hostname"))
        mx            = self._check_mx()

        # Reputation scoring: start at 100, deduct penalties
        rep_score = 100
        listed_critical = [r for r in dnsbl_results if r["listed"] and r["weight"] == "critical"]
        listed_major    = [r for r in dnsbl_results if r["listed"] and r["weight"] == "major"]
        listed_moderate = [r for r in dnsbl_results if r["listed"] and r["weight"] == "moderate"]
        listed_minor    = [r for r in dnsbl_results if r["listed"] and r["weight"] == "minor"]

        for r in listed_critical:
            rep_score -= WEIGHT_PENALTY["critical"]
            self._flags.append({
                "severity": "critical", "category": "Blocklist",
                "item": f"Listed on {r['name']} ({r['zone']})" + (f": {r['reason']}" if r.get("reason") else ""),
                "recommendation": f"Request removal at {r['zone']}. {r['info']}",
            })
        for r in listed_major:
            rep_score -= WEIGHT_PENALTY["major"]
            self._flags.append({
                "severity": "high", "category": "Blocklist",
                "item": f"Listed on {r['name']} ({r['zone']})",
                "recommendation": f"Request removal. {r['info']}",
            })
        for r in listed_moderate:
            rep_score -= WEIGHT_PENALTY["moderate"]
        for r in listed_minor:
            rep_score -= WEIGHT_PENALTY["minor"]

        if ptr["checked"] and not ptr["found"]:
            rep_score -= 10
        if ptr.get("found") and not fcrdns.get("valid"):
            rep_score -= 8

        rep_score = max(0, min(100, rep_score))
        rep_label, rep_color = self._rep_label(rep_score)
        total_listed = len(listed_critical) + len(listed_major) + len(listed_moderate) + len(listed_minor)

        # ── Combined score ──
        combined_score = round(auth_score * 0.45 + rep_score * 0.55)
        combined_label, combined_color = self._combined_label(combined_score)

        # Sort & deduplicate flags
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        self._flags.sort(key=lambda x: sev_order.get(x.get("severity", "low"), 4))

        # Build recommendations (clean list)
        recommendations = [
            {"category": f["category"], "severity": f["severity"],
             "item": f["item"], "recommendation": f["recommendation"]}
            for f in self._flags
        ]

        elapsed_ms = round((time.monotonic() - t0) * 1000)

        return {
            "auth": {
                "score":   auth_score,
                "label":   auth_label,
                "color":   auth_color,
                "summary": "  ".join(auth_summary_parts),
                "categories": [
                    {**spf,   "label": "SPF"},
                    {**dkim,  "label": "DKIM"},
                    {**dmarc, "label": "DMARC"},
                    {**bimi,  "label": "BIMI"},
                ],
            },
            "reputation": {
                "score":        rep_score,
                "label":        rep_label,
                "color":        rep_color,
                "listed_count": total_listed,
                "dnsbl":        dnsbl_results,
                "ptr":          ptr,
                "fcrdns":       fcrdns,
                "mx":           mx,
            },
            "combined": {
                "score": combined_score,
                "label": combined_label,
                "color": combined_color,
            },
            "recommendations": recommendations,
            "meta": {
                "domain":        self.domain,
                "sender_ip":     self.sender_ip,
                "dkim_selector": dkim.get("selector"),
                "checks_run":    len(dnsbl_results) + 4,
                "elapsed_ms":    elapsed_ms,
            },
        }
