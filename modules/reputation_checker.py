"""
INBXR — Sender Reputation & Authentication Checker
Performs live DNS lookups for SPF, DKIM, DMARC, BIMI,
PTR / FCrDNS, parallel DNSBL checks, and SMTP diagnostics.
"""

import re
import socket
import smtplib
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
    # ── Critical (listing here = major delivery impact) ──
    {"zone": "zen.spamhaus.org",       "name": "Spamhaus ZEN",       "weight": "critical",
     "info": "Industry standard. Combines SBL (spam sources), XBL (exploited IPs), and PBL (policy block list)."},
    {"zone": "sbl.spamhaus.org",       "name": "Spamhaus SBL",       "weight": "critical",
     "info": "Spamhaus Block List — verified spam sources. Used by 80%+ of email providers."},
    {"zone": "xbl.spamhaus.org",       "name": "Spamhaus XBL",       "weight": "critical",
     "info": "Exploits Block List — hijacked PCs, botnet nodes, open proxies."},
    {"zone": "pbl.spamhaus.org",       "name": "Spamhaus PBL",       "weight": "critical",
     "info": "Policy Block List — dynamic/residential IPs that should not send mail directly."},
    {"zone": "bl.score.senderscore.com","name": "Sender Score RPBL",  "weight": "critical",
     "info": "Validity (formerly Return Path) reputation blocklist. Used by major mailbox providers worldwide."},
    # ── Major (widely used, significant impact) ──
    {"zone": "bl.spamcop.net",         "name": "SpamCop",            "weight": "major",
     "info": "User-reported spam. Aggressive but decays quickly (24–48 h)."},
    {"zone": "b.barracudacentral.org", "name": "Barracuda BRBL",     "weight": "major",
     "info": "Used by Barracuda Networks appliances worldwide."},
    {"zone": "cbl.abuseat.org",        "name": "CBL",                "weight": "major",
     "info": "Detects spambot behavior. Feeds into Spamhaus XBL."},
    {"zone": "truncate.gbudb.net",     "name": "GBUdb Truncate",     "weight": "major",
     "info": "Truncate list by Message Sniffer. Widely used in enterprise spam appliances."},
    {"zone": "dnsbl.justspam.org",     "name": "JustSpam",           "weight": "major",
     "info": "Spam-only blocklist. Does not list for policy reasons — only confirmed spam."},
    {"zone": "rbl.rbldns.ru",          "name": "RBLDNS.ru",          "weight": "major",
     "info": "Large Russian blocklist. Used widely across Eastern European mail servers."},
    {"zone": "dnsrbl.org",             "name": "DNSRBL",             "weight": "major",
     "info": "Real-time blocklist aggregating multiple spam trap feeds."},
    {"zone": "zen.bl.nszones.com",     "name": "NSZones ZEN",        "weight": "major",
     "info": "NSZones combined blocklist. Aggregates IP reputation data from multiple sources."},
    {"zone": "combined.mail.abusix.zone","name":"Abusix Combined",    "weight": "major",
     "info": "Abusix Mail Intelligence — combines black, exploit, and policy lists. Updated every minute."},
    {"zone": "black.mail.abusix.zone","name": "Abusix Blacklist",     "weight": "major",
     "info": "IPs sending spam to Abusix traps. Listings expire ~5 days after last activity."},
    {"zone": "exploit.mail.abusix.zone","name":"Abusix Exploit",      "weight": "major",
     "info": "Infected hosts, botnets, open proxies, VPN abuse, and Tor exit nodes."},
    # ── Moderate ──
    {"zone": "dnsbl-1.uceprotect.net", "name": "UCEPROTECT L1",      "weight": "moderate",
     "info": "Individual IP spam sender list."},
    {"zone": "dnsbl-2.uceprotect.net", "name": "UCEPROTECT L2",      "weight": "moderate",
     "info": "Netblock-level listing. Escalates from L1 if many IPs listed."},
    {"zone": "dnsbl-3.uceprotect.net", "name": "UCEPROTECT L3",      "weight": "moderate",
     "info": "ASN-level listing. Most aggressive tier — entire provider blocked."},
    {"zone": "psbl.surriel.com",       "name": "PSBL",               "weight": "moderate",
     "info": "Passive spam block list. Automated trap-based."},
    {"zone": "bl.mailspike.net",       "name": "Mailspike BL",       "weight": "moderate",
     "info": "Mailspike reputation blocklist. Used by many European providers."},
    {"zone": "z.mailspike.net",        "name": "Mailspike Z",        "weight": "moderate",
     "info": "Mailspike zero-hour reputation — catches new spam sources within minutes."},
    {"zone": "dnsbl.dronebl.org",      "name": "DroneBL",            "weight": "moderate",
     "info": "Lists IPs of compromised machines (drones/botnets) used for spam or attacks."},
    {"zone": "db.wpbl.info",           "name": "WPBL",               "weight": "moderate",
     "info": "Weighted Private Block List. Community-driven spam source list."},
    {"zone": "bl.blocklist.de",        "name": "Blocklist.de",       "weight": "moderate",
     "info": "German blocklist tracking attacks, spam, and abuse. Widely used in Europe."},
    {"zone": "bl.nordspam.com",        "name": "NordSpam BL",        "weight": "moderate",
     "info": "Nordic spam blocklist. Tracks spam sources targeting Scandinavian networks."},
    {"zone": "dnsbl.spfbl.net",        "name": "SPFBL DNSBL",        "weight": "moderate",
     "info": "Brazilian-origin blocklist. SPF-aware spam filtering."},
    {"zone": "hostkarma.junkemailfilter.com","name":"HostKarma JunkEmail","weight":"moderate",
     "info": "Junk Email Filter blocklist. Used by hosting providers and ISPs."},
    {"zone": "rbl.interserver.net",    "name": "InterServer RBL",    "weight": "moderate",
     "info": "InterServer real-time blocklist. Used across their hosting network."},
    {"zone": "ubl.unsubscore.com",     "name": "Lashback UBL",       "weight": "moderate",
     "info": "Tracks senders who email addresses harvested from unsubscribe links."},
    {"zone": "all.s5h.net",            "name": "S5H All",            "weight": "moderate",
     "info": "Comprehensive blocklist aggregating multiple spam sources."},
    {"zone": "rbl.megarbl.net",        "name": "MegaRBL",            "weight": "moderate",
     "info": "Aggregated RBL from multiple spam trap sources."},
    {"zone": "virus.rbl.jp",           "name": "RBL.JP Virus",       "weight": "moderate",
     "info": "Japanese blocklist focused on virus-sending IPs."},
    {"zone": "access.redhawk.org",     "name": "Redhawk",            "weight": "moderate",
     "info": "Redhawk access list. Used in academic and research networks."},
    {"zone": "rbl.schulte.org",        "name": "Schulte RBL",        "weight": "moderate",
     "info": "Independent RBL based on spam trap data."},
    {"zone": "dnsbl.kempt.net",        "name": "Kempt DNSBL",        "weight": "moderate",
     "info": "Kempt.net blocklist — spam trap driven, popular in Europe."},
    {"zone": "orvedb.aupads.org",      "name": "AUPADS ORVE",        "weight": "moderate",
     "info": "Australian ORVE blocklist. Tracks open relays and spam sources."},
    {"zone": "spam.dnsbl.anonmails.de","name": "AnonMails Spam",     "weight": "moderate",
     "info": "German spam blocklist focusing on anonymous/throwaway mail abuse."},
    {"zone": "dnsbl.calivent.com.pe",  "name": "Calivent DNSBL",     "weight": "moderate",
     "info": "South American blocklist. Tracks spam across Latin American networks."},
    {"zone": "rbl.efnetrbl.org",       "name": "EFnet RBL",          "weight": "moderate",
     "info": "EFnet IRC network blocklist. Tracks IPs engaged in network abuse."},
    {"zone": "bl.konstant.no",         "name": "Konstant BL",        "weight": "moderate",
     "info": "Norwegian blocklist. Tracks spam and abuse targeting Nordic infrastructure."},
    {"zone": "dnsbl.net.ua",           "name": "DNSBL Ukraine",      "weight": "moderate",
     "info": "Ukrainian blocklist. Tracks spam sources across CIS networks."},
    {"zone": "rbl.dns-servicios.com",  "name": "DNS-Servicios RBL",  "weight": "moderate",
     "info": "Spanish blocklist. Tracks spam targeting Spanish-language networks."},
    {"zone": "bl.scientificspam.net",  "name": "ScientificSpam",     "weight": "moderate",
     "info": "Scientific approach to spam detection using statistical analysis."},
    {"zone": "bl.suomispam.net",       "name": "SuomiSpam BL",       "weight": "moderate",
     "info": "Finnish blocklist. Tracks spam targeting Finnish networks."},
    {"zone": "dnsbl.openresolvers.org", "name": "OpenResolvers",      "weight": "moderate",
     "info": "Lists open DNS resolvers often exploited for DNS amplification attacks."},
    {"zone": "dnsbl.abyan.es",         "name": "Abyan DNSBL",        "weight": "moderate",
     "info": "Spanish blocklist. Trap-based spam detection."},
    {"zone": "rbl.lugh.ch",            "name": "Lugh RBL",           "weight": "moderate",
     "info": "Swiss blocklist. Independent spam trap network."},
    {"zone": "rbl.talkactive.net",     "name": "TalkActive RBL",     "weight": "moderate",
     "info": "Community-driven blocklist for spam and abuse."},
    {"zone": "ips.backscatterer.org",  "name": "Backscatterer",      "weight": "moderate",
     "info": "Lists IPs generating backscatter (misdirected bounces). Listings last 4 weeks."},
    {"zone": "policy.mail.abusix.zone","name": "Abusix Policy",      "weight": "moderate",
     "info": "Residential/dynamic IPs that should not send mail directly. Similar to Spamhaus PBL."},
    {"zone": "rep.mailspike.net",      "name": "Mailspike Reputation","weight": "moderate",
     "info": "IP reputation scoring from L5 (worst) to H5 (best). Used by European providers."},
    {"zone": "all.rbl.webiron.net",    "name": "WebIron Combined",    "weight": "moderate",
     "info": "Combined WebIron abuse list — covers active abuse, chronic abuse, and short-term abuse."},
    {"zone": "babl.rbl.webiron.net",   "name": "WebIron BABL",        "weight": "moderate",
     "info": "Bad Abuse Blacklist — IPs involved in active email abuse."},
    {"zone": "cabl.rbl.webiron.net",   "name": "WebIron CABL",        "weight": "moderate",
     "info": "Chronic Abuse Blacklist — IP ranges with unresolved abuse reports (30+ days)."},
    {"zone": "bb.barracudacentral.org","name": "Barracuda B2",        "weight": "moderate",
     "info": "Secondary Barracuda reputation list. Companion to the primary BRBL."},
    {"zone": "cbl.anti-spam.org.cn",   "name": "CASA CBL (China)",    "weight": "moderate",
     "info": "Chinese Anti-Spam Alliance blocklist. Significant coverage for China-originating spam."},
    # ── Minor ──
    {"zone": "noptr.spamrats.com",     "name": "SPAMRATS NoPtr",     "weight": "minor",
     "info": "Flags IPs with no valid PTR record."},
    {"zone": "dyna.spamrats.com",      "name": "SPAMRATS Dyna",      "weight": "minor",
     "info": "Flags IPs with dynamic/generic PTR records."},
    {"zone": "spam.spamrats.com",      "name": "SPAMRATS Spam",      "weight": "minor",
     "info": "IPs observed sending spam to SPAMRATS traps."},
    {"zone": "auth.spamrats.com",      "name": "SPAMRATS Auth",      "weight": "minor",
     "info": "IPs attempting AUTH brute-force attacks on mail servers."},
    {"zone": "backscatter.spameatingmonkey.net","name":"SEM Backscatter","weight":"minor",
     "info": "Detects IPs sending backscatter (bounces from forged senders)."},
    {"zone": "bl.spameatingmonkey.net","name": "SEM BL",             "weight": "minor",
     "info": "Spam Eating Monkey blocklist. Trap-based detection."},
    {"zone": "netbl.spameatingmonkey.net","name":"SEM NetBL",        "weight": "minor",
     "info": "Spam Eating Monkey netblock list."},
    {"zone": "bogons.cymru.com",       "name": "Cymru Bogons",       "weight": "minor",
     "info": "Lists bogon (unallocated/reserved) IP ranges. Should not originate mail."},
    {"zone": "bl.fivetensg.com",       "name": "5ten SG BL",         "weight": "minor",
     "info": "Five Ten Solutions Group blocklist."},
    {"zone": "blackholes.five-ten-sg.com","name":"5ten Blackholes",  "weight": "minor",
     "info": "Five Ten Solutions Group blackhole list."},
    {"zone": "csi.cloudmark.com",      "name": "Cloudmark CSI",      "weight": "minor",
     "info": "Cloudmark Sender Intelligence. Used by major ISPs including Comcast."},
    {"zone": "0spam.fusionzero.com",   "name": "0Spam",              "weight": "minor",
     "info": "Zero Spam blocklist. Trap-based with fast listings."},
    {"zone": "wormrbl.imp.ch",         "name": "IMP WORM RBL",       "weight": "minor",
     "info": "Swiss blocklist focused on worm/virus-sending IPs."},
    {"zone": "spamsources.fabel.dk",   "name": "Fabel SpamSources",  "weight": "minor",
     "info": "Danish spam source blocklist."},
    {"zone": "singular.ttk.pte.hu",    "name": "TTK Singular",       "weight": "minor",
     "info": "Hungarian blocklist from TTK network."},
    {"zone": "dnsbl.rv-soft.info",     "name": "RV-Soft DNSBL",      "weight": "minor",
     "info": "RV-Soft DNS blocklist."},
    {"zone": "rbl.fasthosts.co.uk",    "name": "Fasthosts RBL",      "weight": "minor",
     "info": "UK hosting provider blocklist."},
    {"zone": "dnsbl.anticaptcha.net",  "name": "AntiCaptcha DNSBL",  "weight": "minor",
     "info": "Blocklist targeting CAPTCHA-solving services used for spam automation."},
    {"zone": "rbl.zenon.net",          "name": "Zenon RBL",          "weight": "minor",
     "info": "Russian provider blocklist. Tracks abuse on Zenon network."},
    {"zone": "spam.pedantic.org",      "name": "Pedantic Spam",      "weight": "minor",
     "info": "Long-running independent spam blocklist."},
    {"zone": "bl.technovision.dk",     "name": "TechnoVision BL",    "weight": "minor",
     "info": "Danish blocklist from TechnoVision hosting."},
    {"zone": "rbl.abuse.ro",           "name": "Abuse.ro RBL",       "weight": "minor",
     "info": "Romanian abuse blocklist."},
    {"zone": "dnsbl.tornevall.org",    "name": "Tornevall DNSBL",    "weight": "minor",
     "info": "Swedish blocklist. Tracks Tor exit nodes and proxy abuse."},
    {"zone": "bl.drmx.org",            "name": "DrMX BL",            "weight": "minor",
     "info": "DrMX spam blocklist. Trap-based detection."},
    {"zone": "rbl.polspam.pl",         "name": "PolSpam RBL",        "weight": "minor",
     "info": "Polish blocklist. Tracks spam targeting Polish networks."},
    {"zone": "bl.ipv6.spameatingmonkey.net","name":"SEM IPv6 BL",    "weight": "minor",
     "info": "IPv6 spam blocklist from Spam Eating Monkey."},
    {"zone": "exitnodes.tor.dnsbl.sectoor.de","name":"Sectoor Tor",  "weight": "minor",
     "info": "Lists known Tor exit nodes. Mail from Tor is often blocked."},
    {"zone": "multi.rbl.dns-servicios.com","name":"DNS-Servicios Multi","weight":"minor",
     "info": "Multi-zone Spanish blocklist aggregation."},
    {"zone": "stabl.rbl.webiron.net",  "name": "WebIron STABL",      "weight": "minor",
     "info": "Short Time Abuse Blacklist — temporary listings for recent abuse activity."},
    {"zone": "all.rbl.jp",             "name": "RBL.JP",              "weight": "minor",
     "info": "Japanese regional DNSBL. Covers spam sources targeting/originating from Japan."},
    {"zone": "short.rbl.jp",           "name": "RBL.JP Short",        "weight": "minor",
     "info": "Short-duration listings from RBL.JP for temporary spam events."},
    {"zone": "cdl.anti-spam.org.cn",   "name": "CASA CDL (China)",    "weight": "minor",
     "info": "Chinese Anti-Spam Alliance domain list. Companion to the CASA CBL."},
    {"zone": "bl.nosolicitado.org",    "name": "NoSolicitado",        "weight": "minor",
     "info": "Spanish-language regional DNSBL for spam/abuse in Latin America."},
    {"zone": "dnsrbl.swinog.ch",       "name": "SwiNOG DNSBL",        "weight": "minor",
     "info": "Swiss Network Operators Group DNSBL. Regional list for Swiss IP space."},
    {"zone": "bl.rbl.scrolloutf1.com", "name": "ScrolloutF1",         "weight": "minor",
     "info": "Email gateway project blocklist. Community-driven spam source list."},
]

# ── Domain-based DNSBL zones ─────────────────────────
DOMAIN_DNSBLS = [
    # ── Critical ──
    {"zone": "dbl.spamhaus.org",        "name": "Spamhaus DBL",      "weight": "critical",
     "info": "Domain blocklist. Listed domains appear in spam campaigns."},
    # ── Major ──
    {"zone": "multi.surbl.org",         "name": "SURBL Multi",       "weight": "major",
     "info": "URI blocklist used by many spam filters to check links."},
    {"zone": "dbl.invaluement.com",     "name": "ivmSIP/24 DBL",    "weight": "major",
     "info": "Invaluement domain reputation list."},
    {"zone": "black.uribl.com",         "name": "URIBL Black",      "weight": "major",
     "info": "URI-based blocklist. Checks domains found in spam message bodies."},
    {"zone": "0spam-killlist.fusionzero.com","name":"0Spam Kill DBL", "weight": "major",
     "info": "Zero Spam domain kill list. Domains confirmed in active spam campaigns."},
    # ── Major ──
    {"zone": "dblack.mail.abusix.zone", "name": "Abusix Domain BL",  "weight": "major",
     "info": "Domains found in spam message bodies. Follows short URL redirects to detect final destinations."},
    # ── Moderate ──
    {"zone": "grey.uribl.com",          "name": "URIBL Grey",       "weight": "moderate",
     "info": "URI blocklist grey zone — domains seen in spam but not yet confirmed."},
    {"zone": "red.uribl.com",           "name": "URIBL Red",        "weight": "moderate",
     "info": "Domains found in confirmed phishing or malware campaigns."},
    {"zone": "uri.blacklist.woody.ch",  "name": "Woody URI BL",     "weight": "moderate",
     "info": "Swiss URI blocklist. Tracks domains used in spam campaigns."},
    {"zone": "dbl.nordspam.com",        "name": "NordSpam DBL",     "weight": "moderate",
     "info": "Nordic domain blocklist. Tracks domains in spam targeting Scandinavia."},
    {"zone": "rhsbl.zapbl.net",         "name": "ZapBL RHSBL",      "weight": "moderate",
     "info": "ZapBL right-hand-side blocklist for sending domains."},
    # ── Minor ──
    {"zone": "uribl.spameatingmonkey.net","name":"SEM URIBL",       "weight": "minor",
     "info": "Spam Eating Monkey URI blocklist. Domain-level spam detection."},
    {"zone": "fresh.spameatingmonkey.net","name":"SEM Fresh",        "weight": "minor",
     "info": "Recently registered domains — often used for spam. 5-day window."},
    {"zone": "fresh15.spameatingmonkey.net","name":"SEM Fresh15",    "weight": "minor",
     "info": "Domains registered in the last 15 days — higher spam probability."},
    {"zone": "fresh30.spameatingmonkey.net","name":"SEM Fresh30",    "weight": "minor",
     "info": "Domains registered in the last 30 days."},
    {"zone": "dnsbl.invaluement.com",   "name": "ivmURI",           "weight": "minor",
     "info": "Invaluement URI blocklist. Tracks domains in spam URIs."},
    {"zone": "dbl.tiopan.com",          "name": "Tiopan DBL",       "weight": "minor",
     "info": "Tiopan domain blocklist. Independent spam domain tracking."},
    {"zone": "dbl.suomispam.net",       "name": "SuomiSpam DBL",    "weight": "minor",
     "info": "Finnish domain blocklist for spam campaigns."},
]

# ── Scoring penalties ─────────────────────────────────
WEIGHT_PENALTY = {"critical": 30, "major": 20, "moderate": 12, "minor": 6}

# ── DNSBL false-positive keywords (found in TXT responses) ──
_DNSBL_FALSE_POSITIVE_KEYWORDS = (
    "query refused", "excessive number of queries", "not authorised",
    "open resolver", "v=spf1", "rbldns server", "not listed",
    "www.rbldns", "author vdv", "white listed", "whitelisted",
    "not blacklisted", "is clean",
)


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

    def _check_mta_sts(self) -> dict:
        """Check MTA-STS DNS record and policy file."""
        issues = []

        # 1. Check _mta-sts TXT record
        records, err = _get_txt(self.resolver, f"_mta-sts.{self.domain}")
        sts_record = next((r for r in records if r.startswith("v=STSv1")), None)

        if not sts_record:
            return {"status": "missing", "score": 0, "max": 10,
                    "record": None, "policy": None,
                    "issues": ["No MTA-STS record found (optional — enforces TLS for inbound mail)"]}

        # 2. Parse id from record
        id_match = re.search(r'\bid=(\S+)', sts_record)
        sts_id = id_match.group(1).rstrip(";") if id_match else None
        if not sts_id:
            issues.append("MTA-STS record missing id= tag")

        # 3. Try to fetch the policy file
        policy_result = self._fetch_mta_sts_policy()

        score = 5  # record exists
        if policy_result.get("fetched"):
            mode = policy_result.get("mode")
            if mode == "enforce":
                score = 10
            elif mode == "testing":
                score = 7
                issues.append("MTA-STS policy mode is 'testing' — upgrade to 'enforce' when ready")
            elif mode == "none":
                score = 3
                issues.append("MTA-STS policy mode is 'none' — no TLS enforcement active")

            mx_patterns = policy_result.get("mx", [])
            max_age = policy_result.get("max_age")
            if max_age and int(max_age) < 86400:
                issues.append(f"max_age={max_age}s is very short (recommended: 604800 or higher)")
        else:
            issues.append("Could not fetch policy file at https://mta-sts." + self.domain + "/.well-known/mta-sts.txt")
            policy_result = None

        status = "pass" if score >= 8 and not issues else ("warning" if score >= 3 else "missing")

        return {
            "status": status, "score": score, "max": 10,
            "record": sts_record, "sts_id": sts_id,
            "policy": policy_result, "issues": issues,
        }

    def _fetch_mta_sts_policy(self) -> dict:
        """Fetch and parse MTA-STS policy file over HTTPS."""
        import ssl
        from http.client import HTTPSConnection
        try:
            ctx = ssl.create_default_context()
            conn = HTTPSConnection(f"mta-sts.{self.domain}", 443, timeout=8, context=ctx)
            conn.request("GET", "/.well-known/mta-sts.txt", headers={
                "Host": f"mta-sts.{self.domain}",
                "User-Agent": "INBXR-MTA-STS-Checker/1.0",
            })
            resp = conn.getresponse()
            if resp.status != 200:
                return {"fetched": False, "error": f"HTTP {resp.status}"}
            body = resp.read(16384).decode("utf-8", errors="replace")
            conn.close()

            # Parse key: value lines
            mode = None
            mx_patterns = []
            max_age = None
            for line in body.strip().splitlines():
                line = line.strip()
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key, val = key.strip().lower(), val.strip()
                if key == "mode":
                    mode = val.lower()
                elif key == "mx":
                    mx_patterns.append(val)
                elif key == "max_age":
                    max_age = val

            return {"fetched": True, "mode": mode, "mx": mx_patterns,
                    "max_age": max_age, "raw": body[:500]}
        except Exception as e:
            return {"fetched": False, "error": str(e)[:100]}

    def _check_tls_rpt(self) -> dict:
        """Check TLS-RPT DNS record."""
        records, err = _get_txt(self.resolver, f"_smtp._tls.{self.domain}")
        tls_rpt = next((r for r in records if "v=TLSRPTv1" in r), None)

        if not tls_rpt:
            return {"status": "missing", "score": 0, "max": 10,
                    "record": None,
                    "issues": ["No TLS-RPT record found (optional — enables TLS failure reporting)"]}

        issues = []
        score = 5

        # Extract rua
        rua_match = re.search(r'\brua=(\S+)', tls_rpt)
        rua = rua_match.group(1).rstrip(";") if rua_match else None

        if not rua:
            issues.append("TLS-RPT record missing rua= reporting address")
        else:
            score = 10
            # Check reporting destinations
            destinations = [d.strip() for d in rua.split(",")]
            has_mailto = any(d.startswith("mailto:") for d in destinations)
            has_https = any(d.startswith("https://") for d in destinations)
            if not has_mailto and not has_https:
                issues.append("rua= should use mailto: or https:// reporting endpoints")
                score = 7

        status = "pass" if score >= 8 and not issues else ("warning" if score >= 3 else "missing")

        return {
            "status": status, "score": score, "max": 10,
            "record": tls_rpt, "rua": rua, "issues": issues,
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
            # Resolve IPs for primary MX server
            ips = []
            if records:
                try:
                    a_answers = self.resolver.resolve(records[0][1], "A")
                    ips = [str(r) for r in a_answers]
                except Exception:
                    pass
            return {"found": True, "records": records, "ips": ips}
        except Exception:
            return {"found": False, "records": [], "ips": []}

    def _check_domain_setup(self) -> dict:
        """Evaluate domain establishment by checking DNS record breadth."""
        record_types_found = 0
        details = []

        # Check A records
        try:
            self.resolver.resolve(self.domain, "A")
            record_types_found += 1
            details.append("A")
        except Exception:
            pass

        # Check MX
        try:
            self.resolver.resolve(self.domain, "MX")
            record_types_found += 1
            details.append("MX")
        except Exception:
            pass

        # Check NS
        try:
            self.resolver.resolve(self.domain, "NS")
            record_types_found += 1
            details.append("NS")
        except Exception:
            pass

        # Check TXT (SPF indicator)
        records, _ = _get_txt(self.resolver, self.domain)
        has_spf = any(r.startswith("v=spf1") for r in records)
        if records:
            record_types_found += 1
            details.append("TXT")

        # Check DMARC
        dmarc_records, _ = _get_txt(self.resolver, f"_dmarc.{self.domain}")
        has_dmarc = any(r.startswith("v=DMARC1") for r in dmarc_records)

        if record_types_found == 0:
            status = "fail"
            summary = "Domain has no DNS records"
        elif record_types_found < 3:
            status = "warning"
            summary = f"Limited DNS configuration ({', '.join(details)})"
        elif has_spf and has_dmarc and "MX" in details:
            status = "pass"
            summary = f"Well-established domain with full email setup ({', '.join(details)})"
        elif "MX" in details and (has_spf or has_dmarc):
            status = "pass"
            summary = f"Established domain with email configuration ({', '.join(details)})"
        else:
            status = "warning"
            summary = f"Domain exists but email setup may be incomplete ({', '.join(details)})"

        return {
            "status": status,
            "record_types": details,
            "record_count": record_types_found,
            "has_spf": has_spf,
            "has_dmarc": has_dmarc,
            "summary": summary,
        }

    def _check_abuse_contact(self) -> dict:
        """Check for abuse contact via TXT records and standard conventions."""
        records, _ = _get_txt(self.resolver, self.domain)

        # Look for abuse-related TXT records
        abuse_record = next(
            (r for r in records if "abuse" in r.lower() or "postmaster" in r.lower()),
            None,
        )

        if abuse_record:
            return {
                "status": "pass",
                "found": True,
                "detail": "Abuse contact configured in TXT records",
            }

        # If domain has MX records, standard abuse@domain is assumed available
        try:
            self.resolver.resolve(self.domain, "MX")
            return {
                "status": "pass",
                "found": True,
                "detail": f"Standard abuse contact available (abuse@{self.domain})",
            }
        except Exception:
            pass

        self._flags.append({
            "severity": "low", "category": "Reputation",
            "item": "No abuse contact found for domain",
            "recommendation": f"Ensure abuse@{self.domain} is a working address. Some providers check for abuse contacts as a trust signal.",
        })
        return {
            "status": "warning",
            "found": False,
            "detail": "No abuse contact found",
        }

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
                answers = r.resolve(query, "A")
                # Filter false positives: 127.0.0.1 = query refused / info
                response_ips = [rdata.address for rdata in answers]
                if all(ip in ("127.0.0.1", "127.255.255.255") for ip in response_ips):
                    result["listed"] = False
                    result["error"] = "query_refused"
                else:
                    result["listed"] = True
                try:
                    txts = r.resolve(query, "TXT")
                    for rdata in txts:
                        txt = "".join(
                            s.decode("utf-8", errors="replace") for s in rdata.strings
                        )
                        result["reason"] = txt
                        # Check TXT for refusal/rate-limit/false-positive indicators
                        lower = txt.lower()
                        if any(kw in lower for kw in _DNSBL_FALSE_POSITIVE_KEYWORDS):
                            result["listed"] = False
                            result["error"] = "query_refused"
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
                answers = r.resolve(query, "A")
                response_ips = [rdata.address for rdata in answers]
                if all(ip in ("127.0.0.1", "127.255.255.255") for ip in response_ips):
                    result["listed"] = False
                    result["error"] = "query_refused"
                else:
                    result["listed"] = True
                try:
                    txts = r.resolve(query, "TXT")
                    for rdata in txts:
                        txt = "".join(
                            s.decode("utf-8", errors="replace") for s in rdata.strings
                        )
                        result["reason"] = txt
                        lower = txt.lower()
                        if any(kw in lower for kw in _DNSBL_FALSE_POSITIVE_KEYWORDS):
                            result["listed"] = False
                            result["error"] = "query_refused"
                        break
                except Exception:
                    pass
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                result["listed"] = False
        except Exception as e:
            result["error"] = str(e)
        return result

    def _run_dnsbl_checks(self, check_ip: str = None) -> list:
        futures_map = {}
        results     = []
        ip_to_check = check_ip or self.sender_ip

        with ThreadPoolExecutor(max_workers=30) as pool:
            # IP blocklists (use provided IP, sender_ip, or MX-resolved IP)
            if ip_to_check:
                for entry in IP_DNSBLS:
                    f = pool.submit(self._query_ip_dnsbl, ip_to_check, entry)
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
    #  SMTP DIAGNOSTICS
    # ════════════════════════════════════════════════════

    def _smtp_diagnostics(self, mx_host: str, mx_ips: list) -> dict:
        """Connect to the primary MX server and run SMTP-level diagnostics."""
        result = {
            "checked": False,
            "host": mx_host,
            "ip": mx_ips[0] if mx_ips else None,
            "banner": None,
            "connect_time_ms": None,
            "supports_starttls": False,
            "open_relay": False,
            "open_relay_status": "not_checked",
            "errors": [],
        }

        target_ip = mx_ips[0] if mx_ips else None
        if not target_ip:
            # Try resolving the MX host ourselves
            try:
                target_ip = socket.gethostbyname(mx_host)
                result["ip"] = target_ip
            except Exception:
                result["errors"].append("Could not resolve MX host IP")
                return result

        # ── Connect and get banner ──
        try:
            t0 = time.monotonic()
            smtp = smtplib.SMTP(timeout=8)
            code, banner_bytes = smtp.connect(target_ip, 25)
            connect_ms = round((time.monotonic() - t0) * 1000)

            result["checked"] = True
            result["connect_time_ms"] = connect_ms
            result["banner"] = banner_bytes.decode("utf-8", errors="replace").strip()[:200]

            if connect_ms > 5000:
                self._flags.append({
                    "severity": "medium", "category": "SMTP",
                    "item": f"Slow SMTP response: {connect_ms}ms",
                    "recommendation": "SMTP connection took over 5 seconds. This may cause timeouts with impatient receiving servers. Check server load and network latency.",
                })

            # ── Check STARTTLS support ──
            try:
                smtp.ehlo_or_helo_if_needed()
                if smtp.has_extn("starttls"):
                    result["supports_starttls"] = True
                else:
                    result["supports_starttls"] = False
                    self._flags.append({
                        "severity": "medium", "category": "SMTP",
                        "item": "Mail server does not advertise STARTTLS",
                        "recommendation": "Enable STARTTLS on your mail server. Gmail, Yahoo, and Microsoft penalize servers that don't support encryption in transit.",
                    })
            except Exception:
                pass

            # ── Open Relay Test ──
            # Try to relay a message from a foreign domain to a foreign domain.
            # A properly configured server should reject this.
            try:
                smtp.ehlo_or_helo_if_needed()
                # Use clearly fake addresses that won't cause real delivery
                test_from = "openrelaytest@inbxr-test.example.com"
                test_to   = "openrelaytest@inbxr-verify.example.net"

                smtp.mail(test_from)
                code_rcpt, _ = smtp.rcpt(test_to)

                if code_rcpt < 400:
                    # Server accepted RCPT TO for a foreign domain — open relay!
                    result["open_relay"] = True
                    result["open_relay_status"] = "open"
                    self._flags.append({
                        "severity": "critical", "category": "SMTP",
                        "item": "OPEN RELAY DETECTED — server accepts mail for foreign domains",
                        "recommendation": "Your mail server is an open relay. This means anyone can send spam through it. Fix immediately: restrict relaying to authenticated users and authorized domains only.",
                    })
                else:
                    result["open_relay"] = False
                    result["open_relay_status"] = "closed"

                # Reset the SMTP session state
                smtp.rset()
            except smtplib.SMTPRecipientsRefused:
                result["open_relay"] = False
                result["open_relay_status"] = "closed"
            except smtplib.SMTPSenderRefused:
                result["open_relay"] = False
                result["open_relay_status"] = "closed"
            except Exception as e:
                result["open_relay_status"] = "error"
                result["errors"].append(f"Open relay test error: {str(e)[:80]}")

            smtp.quit()

        except smtplib.SMTPConnectError as e:
            result["errors"].append(f"SMTP connect refused: {str(e)[:80]}")
        except socket.timeout:
            result["errors"].append("SMTP connection timed out (8s)")
            self._flags.append({
                "severity": "high", "category": "SMTP",
                "item": "SMTP connection timed out",
                "recommendation": "Mail server did not respond on port 25 within 8 seconds. Check firewall rules and ensure SMTP is accessible.",
            })
        except OSError as e:
            result["errors"].append(f"Network error: {str(e)[:80]}")
        except Exception as e:
            result["errors"].append(f"SMTP error: {str(e)[:80]}")

        return result

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
        spf     = self._check_spf()
        dkim    = self._check_dkim()
        dmarc   = self._check_dmarc()
        bimi    = self._check_bimi()
        mta_sts = self._check_mta_sts()
        tls_rpt = self._check_tls_rpt()

        auth_score = spf["score"] + dkim["score"] + dmarc["score"] + bimi["score"] + mta_sts["score"] + tls_rpt["score"]
        auth_score = min(100, auth_score)
        auth_label, auth_color = self._auth_label(auth_score)

        auth_summary_parts = []
        for name, rec in [("SPF", spf), ("DKIM", dkim), ("DMARC", dmarc), ("BIMI", bimi), ("MTA-STS", mta_sts), ("TLS-RPT", tls_rpt)]:
            st = rec["status"]
            if st == "pass":
                auth_summary_parts.append(f"✓ {name}")
            elif st == "warning":
                auth_summary_parts.append(f"⚠ {name}")
            elif st == "missing":
                auth_summary_parts.append(f"✗ {name}")
            else:
                auth_summary_parts.append(f"✗ {name}")

        # ── Reputation checks (resolve MX first for IP blocklists) ──
        mx            = self._check_mx()
        mx_ip         = mx.get("ips", [None])[0] if mx.get("ips") else None
        dnsbl_results = self._run_dnsbl_checks(check_ip=mx_ip)
        ptr           = self._check_ptr()
        fcrdns        = self._check_fcrdns(ptr.get("hostname"))
        domain_setup  = self._check_domain_setup()
        abuse_contact = self._check_abuse_contact()

        # ── SMTP diagnostics (only if we have an MX host) ──
        smtp_diag = {"checked": False}
        if mx["found"] and mx["records"]:
            primary_mx_host = mx["records"][0][1]
            smtp_diag = self._smtp_diagnostics(primary_mx_host, mx.get("ips", []))

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

        # Domain setup penalty
        if domain_setup["status"] == "fail":
            rep_score -= 15
        elif domain_setup["status"] == "warning":
            rep_score -= 5

        # Abuse contact penalty
        if abuse_contact["status"] == "warning":
            rep_score -= 3

        # SMTP penalties
        if smtp_diag.get("open_relay"):
            rep_score -= 30
        if smtp_diag.get("checked") and not smtp_diag.get("supports_starttls"):
            rep_score -= 5

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
                    {**spf,     "label": "SPF"},
                    {**dkim,    "label": "DKIM"},
                    {**dmarc,   "label": "DMARC"},
                    {**bimi,    "label": "BIMI"},
                    {**mta_sts, "label": "MTA-STS"},
                    {**tls_rpt, "label": "TLS-RPT"},
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
                "domain_setup": domain_setup,
                "abuse_contact": abuse_contact,
                "smtp": smtp_diag,
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
