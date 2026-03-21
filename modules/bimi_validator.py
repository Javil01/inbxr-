"""
InbXr — BIMI Validator
Deep validation of Brand Indicators for Message Identification.
Checks DNS record, SVG logo, VMC certificate, and DMARC prerequisites.
Zero external dependencies beyond dnspython (already used by reputation_checker).
"""

import logging
import re
import ssl
import socket
import time
from urllib.parse import urlparse
from http.client import HTTPSConnection, HTTPConnection
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger('inbxr.bimi_validator')

# ── BIMI requirements ─────────────────────────────────
_BIMI_SELECTOR = "default"
_SVG_MAX_SIZE = 32 * 1024       # 32 KB max for BIMI SVG (spec recommendation)
_SVG_CONTENT_TYPES = {"image/svg+xml", "image/svg", "application/xml", "text/xml"}
_FETCH_TIMEOUT = 10
_MAX_REDIRECTS = 3

# ── SVG Tiny PS required elements ─────────────────────
# BIMI requires SVG Tiny 1.2 Portable/Secure profile
_SVG_TINY_CHECKS = [
    (r"<svg\b", "SVG root element"),
    (r'xmlns="http://www\.w3\.org/2000/svg"', "SVG namespace"),
]


def validate_bimi(domain: str, selector: str = "default") -> dict:
    """Full BIMI validation for a domain.

    Returns comprehensive validation results including:
    - DNS record check
    - DMARC prerequisite check
    - SVG logo validation (fetch + format check)
    - VMC certificate check
    - Overall status and recommendations
    """
    start = time.time()

    result = {
        "domain": domain,
        "selector": selector,
        "status": "missing",       # missing | invalid | partial | pass
        "score": 0,
        "max_score": 100,
        "record": None,
        "dns_host": f"{selector}._bimi.{domain}",
        "logo": None,
        "vmc": None,
        "dmarc": None,
        "issues": [],
        "recommendations": [],
        "elapsed_ms": 0,
    }

    # ── 1. Check BIMI DNS record ──────────────────────
    bimi_record = _fetch_bimi_record(domain, selector)
    result["record"] = bimi_record

    if not bimi_record["found"]:
        result["status"] = "missing"
        result["issues"].append({
            "severity": "high",
            "text": "No BIMI record found in DNS",
            "detail": f"No TXT record at {selector}._bimi.{domain}",
        })
        result["recommendations"] = _build_recommendations(result)
        result["elapsed_ms"] = round((time.time() - start) * 1000)
        return result

    # ── 2. Parse BIMI record ──────────────────────────
    raw = bimi_record["raw"]
    logo_url = _extract_bimi_tag(raw, "l")
    vmc_url = _extract_bimi_tag(raw, "a")

    # ── 3. Run parallel checks ────────────────────────
    futures = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        # Check DMARC prerequisite
        futures["dmarc"] = pool.submit(_check_dmarc_prerequisite, domain)

        # Validate logo
        if logo_url:
            futures["logo"] = pool.submit(_validate_logo, logo_url)

        # Check VMC
        if vmc_url:
            futures["vmc"] = pool.submit(_validate_vmc, vmc_url)

    # Collect results
    dmarc_result = futures["dmarc"].result() if "dmarc" in futures else None
    logo_result = futures["logo"].result() if "logo" in futures else _missing_logo()
    vmc_result = futures["vmc"].result() if "vmc" in futures else _missing_vmc()

    result["dmarc"] = dmarc_result
    result["logo"] = logo_result
    result["vmc"] = vmc_result

    # ── 4. Score and status ───────────────────────────
    score = 0
    issues = []

    # DMARC prerequisite (25 points)
    if dmarc_result and dmarc_result["meets_requirement"]:
        score += 25
    else:
        policy = dmarc_result["policy"] if dmarc_result else "none"
        issues.append({
            "severity": "high",
            "text": "DMARC policy does not meet BIMI requirement",
            "detail": f"Current policy: p={policy}. BIMI requires p=quarantine or p=reject.",
        })

    # Logo validation (40 points)
    if logo_result["valid"]:
        score += 40
    elif logo_url:
        for issue in logo_result.get("issues", []):
            issues.append({
                "severity": "medium",
                "text": f"Logo issue: {issue}",
                "detail": f"URL: {logo_url}",
            })
    else:
        issues.append({
            "severity": "high",
            "text": "No logo URL in BIMI record",
            "detail": "The l= tag is empty or missing.",
        })

    # VMC certificate (35 points)
    if vmc_result["valid"]:
        score += 35
    elif vmc_url:
        for issue in vmc_result.get("issues", []):
            issues.append({
                "severity": "medium",
                "text": f"VMC issue: {issue}",
                "detail": f"URL: {vmc_url}",
            })
    else:
        # VMC is optional but gives full points
        issues.append({
            "severity": "low",
            "text": "No VMC (Verified Mark Certificate) configured",
            "detail": "Without VMC, your logo may not display in Gmail, Apple Mail, and other strict clients.",
        })

    result["score"] = score
    result["issues"] = issues

    # Determine status
    if score >= 90:
        result["status"] = "pass"
    elif score >= 50:
        result["status"] = "partial"
    elif bimi_record["found"]:
        result["status"] = "invalid"
    else:
        result["status"] = "missing"

    result["recommendations"] = _build_recommendations(result)
    result["elapsed_ms"] = round((time.time() - start) * 1000)

    return result


# ══════════════════════════════════════════════════════
#  DNS RECORD FETCH
# ══════════════════════════════════════════════════════

def _fetch_bimi_record(domain: str, selector: str) -> dict:
    """Fetch BIMI TXT record from DNS."""
    host = f"{selector}._bimi.{domain}"
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5
        resolver.lifetime = 5
        answers = resolver.resolve(host, "TXT")
        for rdata in answers:
            txt = "".join(s.decode("utf-8", errors="replace") if isinstance(s, bytes) else s
                         for s in rdata.strings)
            if txt.strip().startswith("v=BIMI1"):
                return {"found": True, "raw": txt.strip(), "host": host, "error": None}
        return {"found": False, "raw": None, "host": host, "error": "No v=BIMI1 record found"}
    except Exception as e:
        err = str(e)
        if "NXDOMAIN" in err or "NoAnswer" in err or "NoNameservers" in err:
            return {"found": False, "raw": None, "host": host, "error": None}
        return {"found": False, "raw": None, "host": host, "error": str(e)[:120]}


def _extract_bimi_tag(record: str, tag: str) -> str:
    """Extract a tag value from BIMI record (e.g. l=, a=)."""
    match = re.search(rf'\b{tag}\s*=\s*(\S+)', record, re.IGNORECASE)
    if match:
        val = match.group(1).rstrip(";").strip()
        return val if val else None
    return None


# ══════════════════════════════════════════════════════
#  DMARC PREREQUISITE CHECK
# ══════════════════════════════════════════════════════

def _check_dmarc_prerequisite(domain: str) -> dict:
    """Check if DMARC policy meets BIMI requirement (quarantine or reject)."""
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5
        resolver.lifetime = 5
        answers = resolver.resolve(f"_dmarc.{domain}", "TXT")
        for rdata in answers:
            txt = "".join(s.decode("utf-8", errors="replace") if isinstance(s, bytes) else s
                         for s in rdata.strings)
            if txt.strip().startswith("v=DMARC1"):
                policy_match = re.search(r'\bp=(\w+)', txt, re.IGNORECASE)
                policy = policy_match.group(1).lower() if policy_match else "none"

                pct_match = re.search(r'\bpct=(\d+)', txt, re.IGNORECASE)
                pct = int(pct_match.group(1)) if pct_match else 100

                meets = policy in ("quarantine", "reject") and pct == 100
                return {
                    "found": True,
                    "record": txt.strip(),
                    "policy": policy,
                    "pct": pct,
                    "meets_requirement": meets,
                    "issue": None if meets else (
                        f"DMARC pct={pct} (must be 100)" if policy in ("quarantine", "reject") and pct != 100
                        else f"DMARC p={policy} (must be quarantine or reject)"
                    ),
                }
        return {"found": False, "record": None, "policy": "none", "pct": 0,
                "meets_requirement": False, "issue": "No DMARC record found"}
    except Exception:
        logger.exception("Failed to check DMARC prerequisite for %s", domain)
        return {"found": False, "record": None, "policy": "none", "pct": 0,
                "meets_requirement": False, "issue": "Could not query DMARC record"}


# ══════════════════════════════════════════════════════
#  LOGO VALIDATION
# ══════════════════════════════════════════════════════

def _validate_logo(url: str) -> dict:
    """Validate BIMI SVG logo by fetching and checking format."""
    result = {
        "url": url,
        "valid": False,
        "reachable": False,
        "content_type": None,
        "size_bytes": None,
        "is_svg": False,
        "is_https": False,
        "svg_checks": [],
        "issues": [],
    }

    # Check HTTPS
    parsed = urlparse(url)
    if parsed.scheme != "https":
        result["issues"].append("Logo URL must use HTTPS")
        return result
    result["is_https"] = True

    # Fetch the logo
    try:
        status, headers, body = _http_get(url)
    except Exception as e:
        result["issues"].append(f"Could not fetch logo: {str(e)[:80]}")
        return result

    if status != 200:
        result["issues"].append(f"Logo URL returned HTTP {status} (expected 200)")
        return result

    result["reachable"] = True
    ct = headers.get("content-type", "").split(";")[0].strip().lower()
    result["content_type"] = ct
    result["size_bytes"] = len(body)

    # Check content type
    if ct not in _SVG_CONTENT_TYPES:
        result["issues"].append(f"Content-Type is '{ct}' — expected image/svg+xml")

    # Check size
    if len(body) > _SVG_MAX_SIZE:
        result["issues"].append(f"Logo is {len(body):,} bytes — BIMI recommends under {_SVG_MAX_SIZE:,} bytes")

    # Check SVG content
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body

    if "<svg" in text.lower():
        result["is_svg"] = True
    else:
        result["issues"].append("Response does not contain SVG markup")
        return result

    # SVG Tiny PS checks
    for pattern, desc in _SVG_TINY_CHECKS:
        found = bool(re.search(pattern, text, re.IGNORECASE))
        result["svg_checks"].append({"check": desc, "pass": found})
        if not found:
            result["issues"].append(f"Missing: {desc}")

    # Check for script/interactive elements (forbidden in BIMI SVG)
    forbidden = [
        (r"<script\b", "Script elements are forbidden in BIMI SVG"),
        (r"<foreignObject\b", "foreignObject elements are forbidden"),
        (r"<animate\b", "Animation elements are not allowed"),
        (r"<set\b", "Set elements are not allowed"),
    ]
    for pattern, msg in forbidden:
        if re.search(pattern, text, re.IGNORECASE):
            result["issues"].append(msg)

    # Check viewBox (should be square)
    vb_match = re.search(r'viewBox\s*=\s*"([^"]+)"', text)
    if vb_match:
        parts = vb_match.group(1).strip().split()
        if len(parts) == 4:
            try:
                w, h = float(parts[2]), float(parts[3])
                if abs(w - h) > 0.01:
                    result["issues"].append(f"SVG viewBox is {w}x{h} — BIMI logos must be square (1:1 ratio)")
                result["svg_checks"].append({"check": "Square aspect ratio", "pass": abs(w - h) <= 0.01})
            except ValueError:
                pass

    result["valid"] = len(result["issues"]) == 0
    return result


def _missing_logo() -> dict:
    return {"url": None, "valid": False, "reachable": False, "issues": ["No logo URL specified in BIMI record"]}


# ══════════════════════════════════════════════════════
#  VMC VALIDATION
# ══════════════════════════════════════════════════════

def _validate_vmc(url: str) -> dict:
    """Validate VMC (Verified Mark Certificate) URL."""
    result = {
        "url": url,
        "valid": False,
        "reachable": False,
        "content_type": None,
        "size_bytes": None,
        "is_https": False,
        "is_pem": False,
        "issues": [],
    }

    parsed = urlparse(url)
    if parsed.scheme != "https":
        result["issues"].append("VMC URL must use HTTPS")
        return result
    result["is_https"] = True

    try:
        status, headers, body = _http_get(url)
    except Exception as e:
        result["issues"].append(f"Could not fetch VMC: {str(e)[:80]}")
        return result

    if status != 200:
        result["issues"].append(f"VMC URL returned HTTP {status} (expected 200)")
        return result

    result["reachable"] = True
    ct = headers.get("content-type", "").split(";")[0].strip().lower()
    result["content_type"] = ct
    result["size_bytes"] = len(body)

    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body

    # Check for PEM certificate markers
    if "-----BEGIN CERTIFICATE-----" in text:
        result["is_pem"] = True
    elif ct in ("application/pkix-cert", "application/x-pem-file", "application/pem-certificate-chain"):
        result["is_pem"] = True
    else:
        result["issues"].append("VMC does not appear to be a valid PEM certificate")

    result["valid"] = len(result["issues"]) == 0
    return result


def _missing_vmc() -> dict:
    return {"url": None, "valid": False, "reachable": False,
            "issues": ["No VMC (a= tag) in BIMI record — logo may not display in Gmail and Apple Mail"]}


# ══════════════════════════════════════════════════════
#  HTTP HELPER
# ══════════════════════════════════════════════════════

def _http_get(url: str, redirects: int = 0) -> tuple:
    """Simple HTTPS GET using stdlib. Returns (status, headers_dict, body_bytes)."""
    if redirects > _MAX_REDIRECTS:
        raise Exception("Too many redirects")

    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    if parsed.scheme == "https":
        ctx = ssl.create_default_context()
        conn = HTTPSConnection(host, port, timeout=_FETCH_TIMEOUT, context=ctx)
    else:
        conn = HTTPConnection(host, port, timeout=_FETCH_TIMEOUT)

    try:
        conn.request("GET", path, headers={
            "Host": host,
            "User-Agent": "INBXR-BIMI-Validator/1.0",
            "Accept": "*/*",
        })
        resp = conn.getresponse()
        status = resp.status
        headers = {k.lower(): v for k, v in resp.getheaders()}

        # Follow redirects
        if status in (301, 302, 303, 307, 308) and "location" in headers:
            loc = headers["location"]
            if loc.startswith("/"):
                loc = f"{parsed.scheme}://{host}{loc}"
            return _http_get(loc, redirects + 1)

        body = resp.read(256 * 1024)  # Max 256 KB
        return status, headers, body
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
#  RECOMMENDATIONS
# ══════════════════════════════════════════════════════

def _build_recommendations(result: dict) -> list:
    """Build actionable recommendations from validation results."""
    recs = []
    status = result["status"]

    if status == "missing":
        recs.append({
            "severity": "info",
            "title": "Set Up BIMI for Your Domain",
            "text": "BIMI displays your brand logo next to emails in Gmail, Apple Mail, Yahoo, and more. It builds trust and increases open rates.",
            "steps": [
                "Ensure DMARC is set to p=quarantine or p=reject (required)",
                "Create a square SVG logo in SVG Tiny 1.2 PS format",
                "Host the SVG at a publicly accessible HTTPS URL",
                "Optionally, purchase a VMC certificate from DigiCert or Entrust",
                f"Add a TXT record at {result['dns_host']}",
            ],
        })

        # Generate the BIMI record template
        recs.append({
            "severity": "info",
            "title": "BIMI Record Template",
            "text": "Add this TXT record to your DNS (replace the URLs with your actual logo and VMC):",
            "record": {
                "host": result["dns_host"],
                "type": "TXT",
                "value": "v=BIMI1; l=https://yourdomain.com/brand/logo.svg; a=https://yourdomain.com/brand/vmc.pem",
            },
        })

    if status == "pass":
        recs.append({
            "severity": "pass",
            "title": "BIMI is Fully Configured",
            "text": "Your BIMI record, logo, VMC, and DMARC policy all pass validation. Your brand logo should display in supported email clients.",
            "steps": [],
        })

    # DMARC issues
    dmarc = result.get("dmarc")
    if dmarc and not dmarc.get("meets_requirement"):
        policy = dmarc.get("policy", "none")
        if policy == "none":
            recs.append({
                "severity": "high",
                "title": "Upgrade DMARC to Enable BIMI",
                "text": f"Your DMARC policy is p={policy}. BIMI requires at least p=quarantine with pct=100.",
                "steps": [
                    "First run p=quarantine for 2-4 weeks while monitoring DMARC reports",
                    "Once confirmed, upgrade to p=reject for maximum protection and BIMI compatibility",
                    "Ensure pct=100 (or omit pct, which defaults to 100)",
                ],
            })
        elif dmarc.get("pct", 100) != 100:
            recs.append({
                "severity": "medium",
                "title": "Set DMARC pct=100 for BIMI",
                "text": f"Your DMARC pct is {dmarc['pct']}%. BIMI requires pct=100.",
                "steps": ["Update your DMARC record to remove the pct tag or set pct=100"],
            })

    # Logo issues
    logo = result.get("logo")
    if logo and not logo.get("valid") and logo.get("url"):
        recs.append({
            "severity": "medium",
            "title": "Fix Your BIMI Logo",
            "text": "Your logo was found but has issues that may prevent it from displaying.",
            "steps": [
                "Use SVG Tiny 1.2 Portable/Secure format (no scripts, animations, or foreignObject)",
                "Logo must be square (1:1 aspect ratio)",
                "Keep file size under 32 KB",
                "Host on HTTPS with correct Content-Type: image/svg+xml",
                "Test with the BIMI Group's SVG validator: https://bimigroup.org/bimi-generator/",
            ],
        })

    # VMC guidance
    vmc = result.get("vmc")
    if vmc and not vmc.get("valid") and not vmc.get("url"):
        recs.append({
            "severity": "low",
            "title": "Consider Adding a VMC Certificate",
            "text": "A Verified Mark Certificate (VMC) is required for your logo to display in Gmail. Without it, only Yahoo and some other clients will show your logo.",
            "steps": [
                "VMC certificates are issued by DigiCert and Entrust",
                "Your logo must be a registered trademark",
                "Cost is approximately $1,000-1,500/year",
                "If you're not ready for VMC, your BIMI record will still work with Yahoo Mail",
            ],
        })

    return recs


# ══════════════════════════════════════════════════════
#  BIMI RECORD GENERATOR
# ══════════════════════════════════════════════════════

def generate_bimi_record(domain: str, logo_url: str, vmc_url: str = "",
                         selector: str = "default") -> dict:
    """Generate a BIMI DNS record."""
    warnings = []

    if not logo_url or not logo_url.strip():
        return {"error": "Logo URL is required"}

    logo_url = logo_url.strip()
    if not logo_url.startswith("https://"):
        warnings.append("Logo URL must use HTTPS")

    if not logo_url.lower().endswith(".svg"):
        warnings.append("Logo URL should end with .svg")

    parts = [f"v=BIMI1; l={logo_url}"]
    if vmc_url and vmc_url.strip():
        vmc_url = vmc_url.strip()
        parts.append(f"a={vmc_url}")
        if not vmc_url.startswith("https://"):
            warnings.append("VMC URL must use HTTPS")
        if not vmc_url.lower().endswith(".pem"):
            warnings.append("VMC URL should end with .pem")
    else:
        parts.append("a=")

    record = "; ".join(parts)

    return {
        "record": record,
        "host": f"{selector}._bimi.{domain}",
        "dns_type": "TXT",
        "domain": domain,
        "selector": selector,
        "warnings": warnings,
        "explanation": "BIMI displays your brand logo in email clients. Requires DMARC p=quarantine or p=reject.",
    }
