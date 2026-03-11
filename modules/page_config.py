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
                        "eyebrow": "Free Email Intelligence Tool",
                        "heading": "Analyze Your Email Before You Send.",
                        "description": "Paste your email copy and get instant scoring on spam risk, copy effectiveness, readability, link safety, and deliverability \u2014 with AI-powered rewrite suggestions. No sending required.",
                        "chips": ["Spam Risk Scoring", "Copy Effectiveness", "Rewrite Suggestions", "Readability Analysis", "Link Validation", "Inbox Preview"]
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
                        "eyebrow": "Complete Domain & Sender Intelligence",
                        "heading": "Full Sender Health Check",
                        "description": "Enter your domain and INBXR runs every check in parallel \u2014 SPF, DKIM, DMARC, BIMI, MTA-STS, TLS-RPT, 62+ blocklists, reverse DNS, SMTP diagnostics, and more. Add your sending IP for PTR, open relay, and STARTTLS checks. You get a single report with your overall grade, detected email provider, and copy-paste DNS records to fix every issue found.",
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
                        "eyebrow": "Your Email Intelligence",
                        "heading": "Score History & Trends",
                        "description": "Track your email quality over time. Every analysis is automatically saved to your browser \u2014 no account needed. See how your spam risk and copy scores improve as you iterate."
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
                        "eyebrow": "Subject Line Intelligence",
                        "heading": "Which Subject Line Wins?",
                        "description": "Enter 2-5 subject line variations and instantly see which one scores highest on deliverability, emotional pull, clarity, and engagement. Pick your winner before you hit send."
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
                        "text": "INBXR \u2014 Subject line scoring is based on deliverability heuristics and engagement best practices. Actual open rates depend on sender reputation, audience, and timing."
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
                        "eyebrow": "The Most Complete Free Email Test",
                        "heading": "One Email. Full Diagnosis.",
                        "description": "Send from your actual email system \u2014 ESP, mail server, or client \u2014 and we\u2019ll pull the real received message from our mailbox. You get SPF, DKIM, and DMARC pass/fail as the receiving server sees it, TLS encryption details, spam content analysis, copy scoring, readability, DNS reputation, blocklist scan, and a prioritized action plan. Everything GlockApps, Mail-Tester, and MXToolbox charge for \u2014 combined into one free test."
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
                        "text": "INBXR \u2014 Email test analysis uses real received headers from the mail server. Authentication verdicts reflect actual server-side verification at the time of delivery."
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
                        "eyebrow": "Email Authentication Made Easy",
                        "heading": "Generate Your DNS Records",
                        "description": "Select your email service providers, set your policies, and instantly generate production-ready SPF, DKIM, DMARC, MTA-STS, and TLS-RPT records. Copy and paste them into your DNS provider \u2014 no manual formatting required."
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
                        "text": "INBXR \u2014 Generated records are based on known ESP include mechanisms and best-practice defaults. Always verify records in your DNS provider after adding them."
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
                        "eyebrow": "Brand Indicators for Message Identification",
                        "heading": "Check Your BIMI Setup",
                        "description": "BIMI lets your brand logo appear next to your emails in Gmail, Yahoo, Apple Mail, and other supporting clients. Enter your domain to validate your BIMI DNS record, logo format, VMC certificate, and DMARC prerequisites \u2014 or generate a new BIMI record from scratch."
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
                        "text": "INBXR \u2014 BIMI validation checks DNS records, logo availability, and DMARC policy. VMC verification requires a certificate from a supported Certificate Authority (DigiCert or Entrust)."
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
                        "eyebrow": "Real Inbox Placement Testing",
                        "heading": "See Where Your Email Actually Lands",
                        "description": "Send your email to our seed accounts across Gmail, Outlook, Yahoo, and more \u2014 then see exactly whether it hit the inbox, spam folder, or promotions tab. No guesswork, no predictions \u2014 real placement results from real mailboxes."
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
                        "text": "INBXR \u2014 Inbox placement results reflect real mailbox checks at the time of scan. Placement may vary by sender reputation, content, and ISP filtering rules."
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
                        "eyebrow": "Ongoing Blocklist Surveillance",
                        "heading": "Monitor Your Blacklist Status",
                        "description": "Add up to 5 domains and track their status across 60+ email blocklists including Spamhaus, SpamCop, Barracuda, SORBS, and UCEPROTECT. Scan on demand, review history, and catch listings before they tank your deliverability."
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
                        "text": "INBXR \u2014 Blocklist data is checked in real time via DNS queries. Listing status may change between scans. Delisting procedures vary by blocklist operator."
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
                        "eyebrow": "Email Forensics Tool",
                        "heading": "Decode Your Email Headers",
                        "description": "Paste raw email headers and instantly see the full routing path, authentication verdicts, encryption status, DKIM signature details, and every hop your message took from sender to inbox. Understand exactly what happened to your email in transit."
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
                        "text": "INBXR \u2014 Header analysis is performed locally on the server. No email content is stored or shared. Results reflect the headers as parsed at the time of analysis."
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
                        "eyebrow": "Comprehensive Domain Assessment",
                        "heading": "Your Domain Health Report Card",
                        "description": "Get a complete health assessment for any sending domain. INBXR checks authentication records, scans blocklists, validates BIMI, verifies transport security, and inspects DNS health \u2014 then gives you a single letter grade with prioritized recommendations to fix what matters most."
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
                        "eyebrow": "One Domain. Every Check. Every Fix.",
                        "heading": "Domain Health Report",
                        "description": "Enter your domain and INBXR runs every check in parallel \u2014 SPF, DKIM, DMARC, BIMI, MTA-STS, TLS-RPT, blocklists, SSL, reverse DNS, and more. You get a single report with your overall grade, detected email provider, and copy-paste DNS records to fix every issue found."
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
                        "eyebrow": "Email Address Intelligence",
                        "heading": "Verify Any Email Address Instantly",
                        "description": "Enter an email address and INBXR checks syntax, DNS records, disposable domain status, catch-all detection, and mailbox existence via SMTP — all in one click. Know if an address is valid, risky, or fake before you hit send."
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
                        "text": "INBXR \u2014 Email verification uses live DNS lookups and SMTP mailbox probing. Results reflect server responses at the time of check. Some servers may block verification attempts via greylisting or rate limiting."
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
                        "eyebrow": "IP & Domain Warm-up Tracking",
                        "heading": "Warm Up Your Sending Reputation",
                        "description": "New domain or IP? Track your warm-up progress day by day. Follow a proven volume ramp schedule, log daily sends, monitor placement health, and know exactly when you\u2019re ready to send at full volume."
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
                        "text": "INBXR \u2014 Warm-up schedules are general guidelines. Actual ramp speed depends on your domain age, list quality, and ESP policies. Monitor bounces and complaints throughout."
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
