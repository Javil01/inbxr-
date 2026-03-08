"""
INBXR — Page Configuration Manager
Loads/saves section order and editable text content from a JSON file.
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "page_config.json")


def _default_config():
    return {
        "index": {
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
                        "eyebrow": "Free Email Intelligence Tool",
                        "heading": "Know Before You Send.",
                        "description": "Spam filters evaluate over 200 signals before deciding where your email lands. INBXR scans your subject line, body copy, links, and CTAs against the same heuristics used by Gmail, Outlook, and Yahoo \u2014 then scores your copy for conversion effectiveness and delivers actionable rewrites.",
                        "chips": ["Spam Risk Scoring", "Copy Effectiveness", "Rewrite Suggestions", "Subject Line Analysis"]
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
                        "text": "INBXR \u2014 Free email copy intelligence. Heuristic-based analysis does not guarantee inbox placement. Results are advisory and intended to help you improve your email deliverability."
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
                        "eyebrow": "Real-Time DNS Intelligence",
                        "heading": "Diagnose Your Email Infrastructure",
                        "description": "Misconfigured authentication is the #1 reason emails land in spam. INBXR performs live DNS lookups to verify your SPF, DKIM, DMARC, and BIMI records, scans your sending IP and domain against 13 industry blocklists including Spamhaus, SpamCop, and Barracuda, and checks your reverse DNS and forward-confirmed rDNS \u2014 giving you a complete sender health report in seconds.",
                        "detail_1_title": "Authentication Protocols",
                        "detail_1_text": "SPF validates which servers can send on your behalf. DKIM cryptographically signs your messages to prove they haven\u2019t been altered. DMARC ties them together with an enforcement policy. BIMI displays your brand logo in supported inboxes like Gmail, Yahoo, and Apple Mail.",
                        "detail_2_title": "Blocklist Scanning",
                        "detail_2_text": "Your sending IP and domain are checked against Spamhaus ZEN, SpamCop, Barracuda BRBL, CBL, SORBS, UCEPROTECT, Invaluement, SURBL, and more. A single listing on a major blocklist can cause widespread delivery failures across mailbox providers.",
                        "detail_3_title": "Reputation Signals",
                        "detail_3_text": "Beyond authentication, we verify your PTR (reverse DNS) record and forward-confirmed rDNS \u2014 checks that major providers like Gmail and Microsoft use to evaluate sender trustworthiness before accepting your mail."
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
                        "text": "INBXR \u2014 Real-time DNS-based checks. Blocklist data refreshes on every scan. Results may vary from ESP-specific reputation systems."
                    }
                }
            ]
        }
    }


def load_config():
    """Load config from JSON file, or return default if missing/corrupt."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = _default_config()
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
