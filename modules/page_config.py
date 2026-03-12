"""
INBXR — Page Configuration Manager
Loads/saves section order and editable text content from a JSON file.
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "page_config.json")


def _default_config():
    return {
        "analyzer": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "hero",
                    "type": "index_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "The Inbox Checkup",
                        "heading": "Will This Email Land?",
                        "description": "Paste your copy. Get a spam risk score, copy effectiveness grade, readability check, and AI-powered rewrites \u2014 before you hit send. No account. No cost. No sending required.",
                        "chips": ["Spam Risk Score", "Copy Effectiveness", "AI Rewrites", "Readability Check", "Link Safety", "Inbox Preview"]
                    }
                },
                {
                    "id": "tool",
                    "type": "index_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "index_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Free email intelligence. Results are advisory \u2014 actual deliverability depends on sender reputation, content, and provider filtering."
                    }
                }
            ]
        },
        "sender": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "sender_hero",
                    "type": "sender_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Domain Checkup",
                        "heading": "Will Your Domain Land?",
                        "description": "6 auth protocols. 110 blocklists. One report with an A\u2013F grade and copy-paste DNS records to fix every issue. Other tools charge for this \u2014 or only check half.",
                        "detail_1_title": "6 Auth Protocols",
                        "detail_1_text": "SPF, DKIM, DMARC, BIMI, MTA-STS, and TLS-RPT \u2014 checked in parallel. MXToolbox covers 3. GlockApps charges $45/mo.",
                        "detail_2_title": "110 Blocklists",
                        "detail_2_text": "Spamhaus, Barracuda, Abusix, Sender Score, and 100+ more. One listing can block your email overnight.",
                        "detail_3_title": "Fix It, Don\u2019t Just Find It",
                        "detail_3_text": "Every issue comes with a ready-to-paste DNS record. Copy, paste, re-check \u2014 ready to land."
                    }
                },
                {
                    "id": "sender_tool",
                    "type": "sender_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "sender_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Live DNS checks. 110 blocklists scanned per request. Results may differ from ESP-specific reputation systems."
                    }
                }
            ]
        },
        "dashboard": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "dashboard_hero",
                    "type": "dashboard_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Your Inbox Scorecard",
                        "heading": "Watch Your Scores Improve.",
                        "description": "Every checkup auto-saves. Track your spam risk, copy scores, and domain health over time \u2014 no account needed."
                    }
                },
                {
                    "id": "dashboard_tool",
                    "type": "dashboard_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                }
            ]
        },
        "subject_scorer": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "subject_hero",
                    "type": "subject_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Subject Line Checkup",
                        "heading": "Which Subject Line Lands?",
                        "description": "Test up to 5 variations. INBXR ranks them on deliverability, spam safety, clarity, and emotional pull \u2014 send the winner, not a guess."
                    }
                },
                {
                    "id": "subject_tool",
                    "type": "subject_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "subject_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Scores reflect deliverability heuristics and engagement best practices. Actual open rates vary by audience and timing."
                    }
                }
            ]
        },
        "email_test": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "email_test_hero",
                    "type": "email_test_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "The Complete Inbox Checkup",
                        "heading": "Break Into The Inbox.",
                        "description": "One send. Full checkup. Get back real auth verdicts, spam scoring, copy analysis, AI rewrites, and a 110-blocklist scan \u2014 with a prioritized fix plan to land. Other tools charge $30\u2013129/mo. INBXR is free."
                    }
                },
                {
                    "id": "et_value_strip",
                    "type": "et_value_strip",
                    "order": 2,
                    "draggable": True,
                    "editable_fields": {}
                },
                {
                    "id": "et_how_it_works",
                    "type": "et_how_it_works",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {}
                },
                {
                    "id": "email_test_tool",
                    "type": "email_test_tool",
                    "order": 4,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "et_comparison",
                    "type": "et_comparison",
                    "order": 5,
                    "draggable": True,
                    "editable_fields": {}
                },
                {
                    "id": "et_other_tools",
                    "type": "et_other_tools",
                    "order": 6,
                    "draggable": True,
                    "editable_fields": {}
                },
                {
                    "id": "et_final_cta",
                    "type": "et_final_cta",
                    "order": 7,
                    "draggable": True,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "email_test_footer",
                    "order": 8,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Auth verdicts come from real received headers, not DNS record checks. Results reflect what the mail server actually evaluated."
                    }
                }
            ]
        },
        "dns_generator": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "dns_generator_hero",
                    "type": "dns_generator_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Land-Ready in Minutes",
                        "heading": "Generate All 5 DNS Records.",
                        "description": "Pick your ESP, set your policy, copy-paste. SPF, DKIM, DMARC, MTA-STS, and TLS-RPT \u2014 no other free tool generates all five."
                    }
                },
                {
                    "id": "dns_generator_tool",
                    "type": "dns_generator_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "dns_generator_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Records are generated from known ESP include mechanisms. Always verify in your DNS provider after adding."
                    }
                }
            ]
        },
        "bimi": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "bimi_hero",
                    "type": "bimi_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Brand Checkup",
                        "heading": "Land With Your Logo Showing.",
                        "description": "Validate your BIMI record, SVG logo, VMC certificate, and DMARC prerequisites in one scan. Most tools only check DNS \u2014 INBXR validates the full chain."
                    }
                },
                {
                    "id": "bimi_tool",
                    "type": "bimi_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "bimi_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Full-chain BIMI validation: DNS, SVG logo, VMC certificate, and DMARC policy. VMC requires DigiCert or Entrust."
                    }
                }
            ]
        },
        "placement": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "placement_hero",
                    "type": "placement_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Placement Checkup",
                        "heading": "Did Your Email Land?",
                        "description": "Inbox, spam, or promotions? See exactly where your email lands across Gmail, Outlook, Yahoo, iCloud, AOL, and Zoho. GlockApps charges $79/mo. INBXR is free."
                    }
                },
                {
                    "id": "placement_tool",
                    "type": "placement_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "placement_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Real mailbox results at scan time. Placement varies by reputation, content, and ISP filtering."
                    }
                }
            ]
        },
        "blacklist_monitor": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "blacklist_monitor_hero",
                    "type": "blacklist_monitor_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Blocklist Checkup",
                        "heading": "Is Something Blocking You?",
                        "description": "Scan up to 5 domains against 110 blocklists. Track your listing history over time. MXToolbox charges $129/mo \u2014 INBXR gives you on-demand scans with history, free."
                    }
                },
                {
                    "id": "blacklist_monitor_tool",
                    "type": "blacklist_monitor_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "blacklist_monitor_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 110 blocklists checked via live DNS. Listings may change between scans. Delisting steps vary by operator."
                    }
                }
            ]
        },
        "header_analyzer": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "header_analyzer_hero",
                    "type": "header_analyzer_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Header Checkup",
                        "heading": "What Happened to Your Email in Transit?",
                        "description": "Paste raw headers. Get auth verdicts, TLS status, routing hops, delay analysis, and DKIM details \u2014 decoded into plain English."
                    }
                },
                {
                    "id": "header_analyzer_tool",
                    "type": "header_analyzer_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "header_analyzer_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Headers parsed server-side. No content stored or shared."
                    }
                }
            ]
        },
        "domain_health": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "domain_health_hero",
                    "type": "domain_health_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Redirects to Sender Check",
                        "heading": "Domain Health Report",
                        "description": "This tool has been merged into Sender Check for a single, comprehensive report."
                    }
                },
                {
                    "id": "domain_health_tool",
                    "type": "domain_health_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "domain_health_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Domain health scores are computed from live DNS lookups, blocklist scans, and protocol checks at the time of analysis. Results may change as your configuration evolves."
                    }
                }
            ]
        },
        "full_audit": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "full_audit_hero",
                    "type": "full_audit_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Redirects to Sender Check",
                        "heading": "Full Audit",
                        "description": "This tool has been merged into Sender Check for a single, comprehensive report."
                    }
                },
                {
                    "id": "full_audit_tool",
                    "type": "full_audit_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "full_audit_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Full audit results are computed from live DNS lookups, blocklist scans, BIMI validation, and protocol checks. Fix records are generated based on detected issues and your email service provider."
                    }
                }
            ]
        },
        "email_verifier": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "email_verifier_hero",
                    "type": "email_verifier_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Address Checkup",
                        "heading": "Is That Address Even Real?",
                        "description": "Syntax, MX, disposable detection (150+), catch-all, and live SMTP mailbox check \u2014 in one click. ZeroBounce charges per verification. INBXR is free."
                    }
                },
                {
                    "id": "email_verifier_tool",
                    "type": "email_verifier_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "email_verifier_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Live DNS + SMTP mailbox probing. Some servers may block verification via greylisting."
                    }
                }
            ]
        },
        "warmup": {
            "sections": [
                {
                    "id": "header",
                    "type": "header",
                    "order": 0,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "warmup_hero",
                    "type": "warmup_hero",
                    "order": 1,
                    "draggable": True,
                    "editable_fields": {
                        "eyebrow": "Warm-Up Checkup",
                        "heading": "Build Your Reputation Before You Blast.",
                        "description": "30-day volume ramp, daily send logging, and placement health tracking. Know exactly when you\u2019re ready to land at full volume."
                    }
                },
                {
                    "id": "warmup_tool",
                    "type": "warmup_tool",
                    "order": 2,
                    "draggable": False,
                    "editable_fields": {}
                },
                {
                    "id": "footer",
                    "type": "warmup_footer",
                    "order": 3,
                    "draggable": True,
                    "editable_fields": {
                        "text": "INBXR \u2014 Warm-up schedules are guidelines. Actual ramp depends on domain age, list quality, and ESP policies."
                    }
                }
            ]
        }
    }


def load_config():
    """Load config from JSON file, or return default if missing/corrupt."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = _default_config()
        save_config(cfg)
        return cfg

    # Merge any new pages from defaults into existing config
    defaults = _default_config()
    changed = False
    for page_name, page_data in defaults.items():
        if page_name not in cfg:
            cfg[page_name] = page_data
            changed = True
    if changed:
        save_config(cfg)
    return cfg


def save_config(config):
    """Write config to JSON file atomically."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    # Atomic rename (works on Windows if target doesn't exist or same volume)
    if os.path.exists(CONFIG_PATH):
        os.replace(tmp, CONFIG_PATH)
    else:
        os.rename(tmp, CONFIG_PATH)


def get_page_sections(page_name):
    """Return sections for a page, sorted by order."""
    cfg = load_config()
    page = cfg.get(page_name, {})
    sections = page.get("sections", [])
    return sorted(sections, key=lambda s: s.get("order", 0))


def update_section_order(page_name, ordered_ids):
    """Reorder sections by a list of section IDs."""
    cfg = load_config()
    page = cfg.get(page_name)
    if not page:
        return False
    id_map = {s["id"]: s for s in page["sections"]}
    for i, sid in enumerate(ordered_ids):
        if sid in id_map:
            id_map[sid]["order"] = i
    save_config(cfg)
    return True


def update_section_content(page_name, section_id, field, value):
    """Update an editable field in a section."""
    cfg = load_config()
    page = cfg.get(page_name)
    if not page:
        return False
    for s in page["sections"]:
        if s["id"] == section_id:
            s["editable_fields"][field] = value
            save_config(cfg)
            return True
    return False


def update_inline_override(page_name, section_id, field_key, value):
    """Store a text override for any element in a section."""
    cfg = load_config()
    page = cfg.get(page_name)
    if not page:
        # Auto-create page entry
        cfg[page_name] = {"sections": []}
        page = cfg[page_name]

    for s in page["sections"]:
        if s["id"] == section_id:
            if "inline_overrides" not in s:
                s["inline_overrides"] = {}
            s["inline_overrides"][field_key] = value
            save_config(cfg)
            return True

    # Section not in config yet — create a stub and save the override
    new_section = {
        "id": section_id,
        "type": section_id,
        "order": len(page["sections"]),
        "draggable": True,
        "editable_fields": {},
        "inline_overrides": {field_key: value},
    }
    page["sections"].append(new_section)
    save_config(cfg)
    return True


def update_element_styles(page_name, section_id, selector, styles):
    """Store CSS style overrides for an element."""
    cfg = load_config()
    page = cfg.get(page_name)
    if not page:
        cfg[page_name] = {"sections": [], "styles": {}}
        page = cfg[page_name]
    if "styles" not in page:
        page["styles"] = {}
    key = section_id + "::" + selector
    page["styles"][key] = styles
    save_config(cfg)
    return True


def get_page_styles(page_name):
    """Get all custom style overrides for a page."""
    cfg = load_config()
    page = cfg.get(page_name, {})
    return page.get("styles", {})


def get_inline_overrides(page_name):
    """Get all inline text overrides for a page as {section_id::selector: value}."""
    cfg = load_config()
    page = cfg.get(page_name, {})
    result = {}
    for s in page.get("sections", []):
        for key, val in s.get("inline_overrides", {}).items():
            result[s["id"] + "::" + key] = val
    return result


def update_global_theme(variable, value):
    """Update a global CSS custom property."""
    cfg = load_config()
    if "_global_styles" not in cfg:
        cfg["_global_styles"] = {}
    cfg["_global_styles"][variable] = value
    save_config(cfg)
    return True


def get_global_theme():
    """Get all global CSS custom property overrides."""
    cfg = load_config()
    return cfg.get("_global_styles", {})


def add_section_to_page(page_name, section_type, position):
    """Add a section from the library to a page at a given position."""
    cfg = load_config()
    page = cfg.get(page_name)
    if not page:
        return False

    section_id = section_type + "_" + str(int(__import__("time").time()))
    new_section = {
        "id": section_id,
        "type": section_type,
        "order": position,
        "draggable": True,
        "editable_fields": {},
        "inline_overrides": {},
    }

    for s in page["sections"]:
        if s.get("order", 0) >= position:
            s["order"] = s.get("order", 0) + 1

    page["sections"].append(new_section)
    save_config(cfg)
    return section_id


def remove_section_from_page(page_name, section_id):
    """Remove a section from a page."""
    cfg = load_config()
    page = cfg.get(page_name)
    if not page:
        return False
    original_len = len(page["sections"])
    page["sections"] = [s for s in page["sections"] if s["id"] != section_id]
    if len(page["sections"]) < original_len:
        save_config(cfg)
        return True
    return False


def get_section_library():
    """Return list of available section templates."""
    import glob as _glob
    sections_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "sections")
    files = _glob.glob(os.path.join(sections_dir, "*.html"))
    library = []
    for f in sorted(files):
        name = os.path.basename(f).replace(".html", "")
        if name in ("header",):
            continue
        label = name.replace("_", " ").replace("-", " ").title()
        library.append({"type": name, "label": label})
    return library


def save_builder_data(page_name, html, css):
    """Store GrapesJS builder HTML and CSS for a page."""
    cfg = load_config()
    if page_name not in cfg:
        cfg[page_name] = {"sections": []}
    cfg[page_name]["builder"] = {"html": html, "css": css}
    save_config(cfg)
    return True


def get_builder_data(page_name):
    """Get stored builder HTML/CSS for a page, or None."""
    cfg = load_config()
    page = cfg.get(page_name, {})
    builder = page.get("builder")
    if builder and builder.get("html"):
        return builder
    return None


def clear_builder_data(page_name):
    """Remove builder override, reverting to section-based rendering."""
    cfg = load_config()
    page = cfg.get(page_name, {})
    if "builder" in page:
        del page["builder"]
        save_config(cfg)
        return True
    return False


def save_uploaded_image(file_storage):
    """Save an uploaded image to static/uploads/. Returns the URL path."""
    import time as _time

    ALLOWED = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    filename = file_storage.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED:
        return None

    safe_name = f"{int(_time.time())}_{filename.replace(' ', '_')}"
    path = os.path.join(upload_dir, safe_name)
    file_storage.save(path)
    return f"/static/uploads/{safe_name}"
