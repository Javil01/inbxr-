"""
InbXr — Link & Image Validator
Validates all links and images in an email body:
- Broken links (HTTP status)
- Redirect chains
- URL shorteners to sketchy domains
- Mixed content (HTTP links in email)
- Image loading, size, alt text
- Blocklisted / suspicious domains
Uses Python stdlib only (http.client, ssl, urllib).
"""

import logging
import re
import ssl
import time
from html.parser import HTMLParser
from http.client import HTTPSConnection, HTTPConnection
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger('inbxr.link_image_validator')

# ── Config ────────────────────────────────────────────
_FETCH_TIMEOUT = 8
_MAX_REDIRECTS = 5
_MAX_URLS = 50          # limit to prevent abuse
_MAX_WORKERS = 8
_IMAGE_MAX_SIZE = 1024 * 1024  # 1 MB warning threshold
_IMAGE_WARN_SIZE = 200 * 1024  # 200 KB suggestion threshold

# ── Known URL shorteners ──────────────────────────────
_SHORTENERS = {
    "bit.ly", "t.co", "goo.gl", "tinyurl.com", "ow.ly", "is.gd",
    "buff.ly", "adf.ly", "bl.ink", "lnkd.in", "db.tt", "qr.ae",
    "cur.lv", "rebrand.ly", "short.io", "tiny.cc", "clck.ru",
    "shorte.st", "linktr.ee", "rb.gy", "v.gd", "s.id",
}

# ── Suspicious TLDs ───────────────────────────────────
_SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".buzz", ".club", ".icu", ".cam", ".rest",
    ".surf", ".monster", ".wang", ".loan", ".click", ".gdn",
}

# ── Known tracking / safe redirect domains ────────────
_TRACKING_DOMAINS = {
    "click.", "track.", "links.", "email.", "t.", "go.", "e.",
    "trk.", "redirect.", "open.", "lnk.",
}


class _EmailHTMLParser(HTMLParser):
    """Extract links and images from HTML email body."""

    def __init__(self):
        super().__init__()
        self.links = []     # (url, text)
        self.images = []    # (src, alt, width, height)
        self._current_link = None
        self._link_text = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "a":
            href = attrs_dict.get("href", "").strip()
            if href and not href.startswith(("#", "mailto:", "tel:")):
                self._current_link = href
                self._link_text = ""
        elif tag == "img":
            src = attrs_dict.get("src", "").strip()
            alt = attrs_dict.get("alt", "").strip()
            width = attrs_dict.get("width", "")
            height = attrs_dict.get("height", "")
            if src:
                self.images.append({
                    "src": src,
                    "alt": alt,
                    "width": width,
                    "height": height,
                })

    def handle_data(self, data):
        if self._current_link is not None:
            self._link_text += data

    def handle_endtag(self, tag):
        if tag == "a" and self._current_link is not None:
            self.links.append({
                "url": self._current_link,
                "text": self._link_text.strip(),
            })
            self._current_link = None
            self._link_text = ""


def validate_links_and_images(body: str) -> dict:
    """Validate all links and images in an email HTML body.

    Returns comprehensive results with per-item status, issues, and summary.
    """
    start = time.time()

    # Parse HTML
    parser = _EmailHTMLParser()
    try:
        parser.feed(body)
    except Exception:
        logger.exception("Failed to parse HTML body for link/image extraction")

    raw_links = parser.links
    raw_images = parser.images

    # Also find bare URLs in text not already in <a> tags
    text_urls = re.findall(r'https?://[^\s<>"\']+', body, re.IGNORECASE)
    linked_urls = {l["url"] for l in raw_links}
    for url in text_urls:
        url = url.rstrip(".,;:)")
        if url not in linked_urls:
            raw_links.append({"url": url, "text": ""})
            linked_urls.add(url)

    # Deduplicate links by URL
    seen_urls = set()
    unique_links = []
    for link in raw_links:
        url = link["url"]
        if url not in seen_urls:
            seen_urls.add(url)
            unique_links.append(link)

    # Limit
    links_to_check = unique_links[:_MAX_URLS]
    images_to_check = raw_images[:_MAX_URLS]

    # ── Validate links concurrently ───────────────────
    link_results = []
    if links_to_check:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_validate_link, l["url"]): l
                for l in links_to_check
            }
            for f in as_completed(futures):
                link_info = futures[f]
                result = f.result()
                result["text"] = link_info.get("text", "")
                link_results.append(result)

    # ── Validate images concurrently ──────────────────
    image_results = []
    if images_to_check:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_validate_image, img["src"]): img
                for img in images_to_check
            }
            for f in as_completed(futures):
                img_info = futures[f]
                result = f.result()
                result["alt"] = img_info.get("alt", "")
                result["declared_width"] = img_info.get("width", "")
                result["declared_height"] = img_info.get("height", "")
                image_results.append(result)

    # ── Build summary and issues ──────────────────────
    summary = _build_summary(link_results, image_results, raw_images)
    issues = _build_issues(link_results, image_results, raw_images)
    recommendations = _build_recommendations(summary, issues)

    # Score (0-100, higher = better)
    score = _calculate_score(summary)

    elapsed = round((time.time() - start) * 1000)

    return {
        "score": score,
        "label": _score_label(score),
        "color": _score_color(score),
        "summary": summary,
        "links": {
            "total": len(link_results),
            "results": sorted(link_results, key=lambda r: r.get("status_code") or 999),
        },
        "images": {
            "total": len(image_results),
            "results": image_results,
        },
        "issues": issues,
        "recommendations": recommendations,
        "elapsed_ms": elapsed,
    }


# ══════════════════════════════════════════════════════
#  LINK VALIDATION
# ══════════════════════════════════════════════════════

def _validate_link(url: str) -> dict:
    """Validate a single URL. Returns status, redirects, final URL, issues."""
    result = {
        "url": url,
        "status": "unknown",    # ok | redirect | broken | error | shortener | suspicious
        "status_code": None,
        "final_url": url,
        "redirects": [],
        "is_https": url.startswith("https://"),
        "is_shortener": False,
        "is_suspicious": False,
        "domain": "",
        "issues": [],
        "check_time_ms": 0,
    }

    parsed = urlparse(url)
    domain = (parsed.hostname or "").lower()
    result["domain"] = domain

    # Check shortener
    if domain in _SHORTENERS or any(domain.endswith("." + s) for s in _SHORTENERS):
        result["is_shortener"] = True
        result["issues"].append("URL shortener detected — hides actual destination")

    # Check suspicious TLD
    for tld in _SUSPICIOUS_TLDS:
        if domain.endswith(tld):
            result["is_suspicious"] = True
            result["issues"].append(f"Suspicious TLD: {tld}")
            break

    # Check HTTP (non-secure)
    if not url.startswith("https://"):
        result["issues"].append("Uses HTTP instead of HTTPS — insecure link")

    # Follow the URL
    start = time.time()
    try:
        current_url = url
        for _ in range(_MAX_REDIRECTS):
            status, location, _ = _head_request(current_url)
            result["status_code"] = status

            if status is None:
                result["status"] = "error"
                result["issues"].append("Connection failed — server unreachable or timed out")
                break

            if 200 <= status < 300:
                result["status"] = "ok"
                result["final_url"] = current_url
                break

            if 300 <= status < 400 and location:
                # Resolve relative redirects
                if location.startswith("/"):
                    p = urlparse(current_url)
                    location = f"{p.scheme}://{p.hostname}{location}"
                result["redirects"].append({"from": current_url, "to": location, "status": status})
                current_url = location
                result["final_url"] = current_url
                result["status"] = "redirect"
            elif 400 <= status < 500:
                result["status"] = "broken"
                result["issues"].append(f"Client error: HTTP {status}")
                break
            elif status >= 500:
                result["status"] = "broken"
                result["issues"].append(f"Server error: HTTP {status}")
                break
            else:
                result["status"] = "error"
                result["issues"].append(f"Unexpected HTTP {status}")
                break
        else:
            result["status"] = "error"
            result["issues"].append(f"Too many redirects ({_MAX_REDIRECTS}+)")

    except Exception as e:
        result["status"] = "error"
        result["issues"].append(f"Error: {str(e)[:80]}")

    result["check_time_ms"] = round((time.time() - start) * 1000)

    # Check redirect chain length
    if len(result["redirects"]) > 2:
        result["issues"].append(f"Long redirect chain ({len(result['redirects'])} hops) — slows loading and hurts deliverability")

    # Check if shortener resolves to suspicious domain
    if result["is_shortener"] and result["final_url"] != url:
        final_domain = urlparse(result["final_url"]).hostname or ""
        for tld in _SUSPICIOUS_TLDS:
            if final_domain.endswith(tld):
                result["is_suspicious"] = True
                result["issues"].append(f"Shortener resolves to suspicious domain: {final_domain}")
                break

    # Categorize final status
    if result["is_shortener"] and result["status"] == "ok":
        result["status"] = "shortener"
    elif result["is_suspicious"]:
        result["status"] = "suspicious"

    return result


# ══════════════════════════════════════════════════════
#  IMAGE VALIDATION
# ══════════════════════════════════════════════════════

def _validate_image(src: str) -> dict:
    """Validate a single image URL."""
    result = {
        "src": src,
        "status": "unknown",   # ok | broken | error | oversized | insecure
        "status_code": None,
        "content_type": None,
        "size_bytes": None,
        "is_https": src.startswith("https://"),
        "is_tracking_pixel": False,
        "issues": [],
        "check_time_ms": 0,
    }

    # Skip data URIs
    if src.startswith("data:"):
        result["status"] = "ok"
        result["issues"].append("Inline data URI — increases email size")
        return result

    # Check HTTPS
    if src.startswith("http://"):
        result["issues"].append("Image uses HTTP — may not load in many email clients")

    start = time.time()
    try:
        status, headers, body_preview = _head_request(src, get_body_size=True)
        result["status_code"] = status

        if status is None:
            result["status"] = "error"
            result["issues"].append("Could not reach image server")
        elif 200 <= status < 300:
            result["status"] = "ok"
            ct = headers.get("content-type", "").split(";")[0].strip().lower() if headers else ""
            result["content_type"] = ct
            size = headers.get("content-length") if headers else None
            if size:
                result["size_bytes"] = int(size)

            # Check size
            if result["size_bytes"] and result["size_bytes"] > _IMAGE_MAX_SIZE:
                result["status"] = "oversized"
                result["issues"].append(f"Image is {result['size_bytes'] // 1024} KB — very large for email")
            elif result["size_bytes"] and result["size_bytes"] > _IMAGE_WARN_SIZE:
                result["issues"].append(f"Image is {result['size_bytes'] // 1024} KB — consider optimizing")

            # Detect tracking pixel (tiny image)
            if result["size_bytes"] and result["size_bytes"] < 200:
                result["is_tracking_pixel"] = True

            # Check content type
            if ct and not ct.startswith("image/"):
                result["issues"].append(f"Content-Type '{ct}' is not an image type")

        elif 400 <= status < 500:
            result["status"] = "broken"
            result["issues"].append(f"Image not found: HTTP {status}")
        elif status >= 500:
            result["status"] = "broken"
            result["issues"].append(f"Image server error: HTTP {status}")
        else:
            result["status"] = "error"

    except Exception as e:
        result["status"] = "error"
        result["issues"].append(f"Error loading image: {str(e)[:60]}")

    result["check_time_ms"] = round((time.time() - start) * 1000)
    return result


# ══════════════════════════════════════════════════════
#  HTTP HELPER
# ══════════════════════════════════════════════════════

def _head_request(url: str, get_body_size: bool = False):
    """Send HEAD request (or GET for body size). Returns (status, headers_dict, None)."""
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    if not host:
        return None, None, None

    try:
        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            conn = HTTPSConnection(host, port, timeout=_FETCH_TIMEOUT, context=ctx)
        else:
            conn = HTTPConnection(host, port, timeout=_FETCH_TIMEOUT)

        method = "GET" if get_body_size else "HEAD"
        conn.request(method, path, headers={
            "Host": host,
            "User-Agent": "InbXr-LinkChecker/1.0",
            "Accept": "*/*",
        })
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}

        # For HEAD that returns no content-length, try GET
        if get_body_size and "content-length" not in headers and 200 <= resp.status < 300:
            resp.read(1024)  # read small chunk
            # Some servers don't set content-length on HEAD

        return resp.status, headers, None
    except ssl.CertificateError:
        return None, None, None
    except Exception:
        return None, None, None
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ══════════════════════════════════════════════════════
#  SUMMARY, ISSUES, RECOMMENDATIONS
# ══════════════════════════════════════════════════════

def _build_summary(link_results: list, image_results: list, raw_images: list) -> dict:
    """Build counts summary."""
    link_ok = sum(1 for r in link_results if r["status"] == "ok")
    link_redirect = sum(1 for r in link_results if r["status"] == "redirect")
    link_broken = sum(1 for r in link_results if r["status"] == "broken")
    link_error = sum(1 for r in link_results if r["status"] == "error")
    link_shortener = sum(1 for r in link_results if r["is_shortener"])
    link_suspicious = sum(1 for r in link_results if r["is_suspicious"])
    link_http = sum(1 for r in link_results if not r["is_https"])
    long_chains = sum(1 for r in link_results if len(r["redirects"]) > 2)

    img_ok = sum(1 for r in image_results if r["status"] == "ok")
    img_broken = sum(1 for r in image_results if r["status"] == "broken")
    img_error = sum(1 for r in image_results if r["status"] == "error")
    img_oversized = sum(1 for r in image_results if r["status"] == "oversized")
    img_http = sum(1 for r in image_results if not r["is_https"] and not r["src"].startswith("data:"))
    img_no_alt = sum(1 for img in raw_images if not img.get("alt", "").strip())
    img_tracking = sum(1 for r in image_results if r.get("is_tracking_pixel"))

    return {
        "links_total": len(link_results),
        "links_ok": link_ok,
        "links_redirect": link_redirect,
        "links_broken": link_broken,
        "links_error": link_error,
        "links_shortener": link_shortener,
        "links_suspicious": link_suspicious,
        "links_http": link_http,
        "links_long_chains": long_chains,
        "images_total": len(image_results),
        "images_ok": img_ok,
        "images_broken": img_broken,
        "images_error": img_error,
        "images_oversized": img_oversized,
        "images_http": img_http,
        "images_no_alt": img_no_alt,
        "images_tracking": img_tracking,
    }


def _build_issues(link_results: list, image_results: list, raw_images: list) -> list:
    """Build top-level issues list."""
    issues = []

    broken_links = [r for r in link_results if r["status"] == "broken"]
    if broken_links:
        issues.append({
            "severity": "high",
            "category": "Broken Links",
            "text": f"{len(broken_links)} broken link{'s' if len(broken_links) != 1 else ''} detected",
            "detail": ", ".join(r["url"][:60] for r in broken_links[:3]),
        })

    error_links = [r for r in link_results if r["status"] == "error"]
    if error_links:
        issues.append({
            "severity": "medium",
            "category": "Unreachable Links",
            "text": f"{len(error_links)} link{'s' if len(error_links) != 1 else ''} could not be reached",
            "detail": "Server timeout or connection refused",
        })

    shortener_links = [r for r in link_results if r["is_shortener"]]
    if shortener_links:
        issues.append({
            "severity": "high",
            "category": "URL Shorteners",
            "text": f"{len(shortener_links)} URL shortener{'s' if len(shortener_links) != 1 else ''} — major spam signal",
            "detail": ", ".join(set(r["domain"] for r in shortener_links)),
        })

    suspicious = [r for r in link_results if r["is_suspicious"]]
    if suspicious:
        issues.append({
            "severity": "high",
            "category": "Suspicious Domains",
            "text": f"{len(suspicious)} link{'s' if len(suspicious) != 1 else ''} to suspicious domains",
            "detail": ", ".join(set(r["domain"] for r in suspicious)),
        })

    http_links = [r for r in link_results if not r["is_https"]]
    if http_links:
        issues.append({
            "severity": "medium",
            "category": "Mixed Content",
            "text": f"{len(http_links)} link{'s' if len(http_links) != 1 else ''} use HTTP instead of HTTPS",
            "detail": "Insecure links can trigger security warnings and hurt deliverability",
        })

    long_chains = [r for r in link_results if len(r["redirects"]) > 2]
    if long_chains:
        issues.append({
            "severity": "medium",
            "category": "Redirect Chains",
            "text": f"{len(long_chains)} link{'s' if len(long_chains) != 1 else ''} with long redirect chains (3+ hops)",
            "detail": "Slows load time and can trigger spam filters",
        })

    broken_imgs = [r for r in image_results if r["status"] == "broken"]
    if broken_imgs:
        issues.append({
            "severity": "high",
            "category": "Broken Images",
            "text": f"{len(broken_imgs)} broken image{'s' if len(broken_imgs) != 1 else ''} — will show as missing in inbox",
            "detail": ", ".join(r["src"][:50] for r in broken_imgs[:3]),
        })

    oversized_imgs = [r for r in image_results if r["status"] == "oversized"]
    if oversized_imgs:
        issues.append({
            "severity": "medium",
            "category": "Oversized Images",
            "text": f"{len(oversized_imgs)} image{'s' if len(oversized_imgs) != 1 else ''} over 1 MB",
            "detail": "Large images slow email loading and may be clipped by Gmail",
        })

    no_alt = [img for img in raw_images if not img.get("alt", "").strip()]
    if no_alt:
        sev = "high" if len(no_alt) > 3 else "medium" if len(no_alt) > 1 else "low"
        issues.append({
            "severity": sev,
            "category": "Missing Alt Text",
            "text": f"{len(no_alt)} image{'s' if len(no_alt) != 1 else ''} missing alt text",
            "detail": "Hurts accessibility and displays blank when images are blocked",
        })

    http_imgs = [r for r in image_results if not r["is_https"] and not r["src"].startswith("data:")]
    if http_imgs:
        issues.append({
            "severity": "medium",
            "category": "Insecure Images",
            "text": f"{len(http_imgs)} image{'s' if len(http_imgs) != 1 else ''} loaded over HTTP",
            "detail": "Many email clients block HTTP images by default",
        })

    if not issues:
        issues.append({
            "severity": "pass",
            "category": "All Clear",
            "text": "All links and images passed validation",
            "detail": "",
        })

    return issues


def _build_recommendations(summary: dict, issues: list) -> list:
    """Build actionable recommendations."""
    recs = []
    s = summary

    if s["links_broken"] > 0:
        recs.append("Fix or remove broken links — they damage credibility and trigger spam filters")

    if s["links_shortener"] > 0:
        recs.append("Replace URL shorteners (bit.ly, tinyurl, etc.) with full, direct URLs — shorteners are a top spam signal")

    if s["links_suspicious"] > 0:
        recs.append("Review links to suspicious domains — consider replacing with links to trusted, established domains")

    if s["links_http"] > 0:
        recs.append("Upgrade all HTTP links to HTTPS — insecure links can trigger security warnings in email clients")

    if s["links_long_chains"] > 0:
        recs.append("Reduce redirect chains — link directly to the final destination URL where possible")

    if s["images_broken"] > 0:
        recs.append("Fix broken images — verify all image URLs are publicly accessible and the hosting server is reliable")

    if s["images_oversized"] > 0:
        recs.append("Compress large images — use TinyPNG or similar tools, aim for under 200 KB per image")

    if s["images_no_alt"] > 0:
        recs.append("Add descriptive alt text to all images — critical for accessibility and for when images are blocked")

    if s["images_http"] > 0:
        recs.append("Serve all images over HTTPS — many email clients block HTTP images by default")

    total_issues = sum(1 for i in issues if i["severity"] in ("high", "medium"))
    if total_issues == 0:
        recs.append("All links and images look good — no action needed")

    return recs


def _calculate_score(summary: dict) -> int:
    """Calculate 0-100 score (higher = better)."""
    score = 100
    s = summary

    # Link penalties
    if s["links_total"] > 0:
        broken_pct = s["links_broken"] / s["links_total"]
        score -= min(30, int(broken_pct * 60))

    score -= min(15, s["links_shortener"] * 8)
    score -= min(15, s["links_suspicious"] * 10)
    score -= min(10, s["links_http"] * 3)
    score -= min(5, s["links_long_chains"] * 3)
    score -= min(5, s["links_error"] * 2)

    # Image penalties
    score -= min(15, s["images_broken"] * 8)
    score -= min(5, s["images_oversized"] * 3)
    score -= min(10, s["images_no_alt"] * 2)
    score -= min(5, s["images_http"] * 2)

    return max(0, min(100, score))


def _score_label(score: int) -> str:
    if score >= 90: return "Excellent"
    if score >= 70: return "Good"
    if score >= 50: return "Needs Work"
    if score >= 30: return "Poor"
    return "Critical"


def _score_color(score: int) -> str:
    if score >= 90: return "green"
    if score >= 70: return "blue"
    if score >= 50: return "yellow"
    if score >= 30: return "orange"
    return "red"
