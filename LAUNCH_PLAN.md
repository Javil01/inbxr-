# INBXR Launch Plan — March 2026

## Target Audiences
1. **Cold email operators** (Instantly, Smartlead, Lemlist users) — fastest to revenue
2. **Newsletter operators** (Beehiiv, ConvertKit, Mailchimp) — largest audience, viral potential
3. **Freelance email consultants** — agency tier upsell

---

## WEEK 1 — Soft Launch (Community Seeding)

### Reddit (3-4 posts across subreddits)

**r/coldemail** — Post as a value-first share:
```
Title: I built a free tool to check if your cold emails are landing in spam

Been burning through domains and wanted a quick way to check sender reputation,
blacklists, and inbox placement without paying $55+/mo for GlockApps.

So I built INBXR (inbxr.us) — free email deliverability toolkit:

- Send a test email → see if it hits inbox, spam, or promotions (Gmail/Yahoo/Outlook)
- Sender reputation check — SPF/DKIM/DMARC + 100 blocklists in one scan
- Warm-up tracker — log your daily volumes and track progress
- Blacklist monitor — get alerts if your domain gets listed
- Email verifier — check if addresses are valid before sending
- Subject line scorer — A/B test subject lines across 7 dimensions

Everything works without signing up. Free accounts get 50 checks/day.

Would love feedback from anyone running cold outreach — what's missing?
```

**r/emailmarketing** — Position as alternative:
```
Title: Free alternative to GlockApps / Mail-Tester / MXToolbox — looking for feedback

I built inbxr.us because I was tired of paying $100+/mo across 3 different
deliverability tools. INBXR combines:

- Spam risk scoring (paste your email copy, get a 0-100 risk score)
- Sender reputation (SPF/DKIM/DMARC + 100+ blocklists)
- Inbox placement testing (send a real email, see where it lands)
- DNS record generator (SPF, DKIM, DMARC fix records with copy-paste)
- Subject line A/B testing
- Email verification
- Blacklist monitoring with alerts

It's free to use — no credit card, no trial expiration.

What would make this more useful for your workflow?
```

**r/SaaS** or **r/indiehackers** — Build in public angle:
```
Title: Launched my first SaaS — free email deliverability toolkit (inbxr.us)

Built this as a solo dev. Stack: Flask + vanilla JS + SQLite on Railway.
No React, no Tailwind, no TypeScript — just Python and plain CSS.

INBXR checks your email deliverability: spam risk, sender reputation,
inbox placement, blacklist monitoring, and more. 10 tools, all free.

Competing against GlockApps ($55-129/mo), MXToolbox ($129-399/mo), and
Litmus ($500/mo). My angle: give away the core tools free, charge for
monitoring, alerts, AI insights, and team features.

Currently at $0 MRR, 0 users. Would love brutally honest feedback.

https://inbxr.us
```

---

### Twitter/X (daily posts for 2 weeks)

**Launch thread:**
```
I just launched INBXR — free email deliverability tools.

Here's what it does and why I built it (thread):

1/ If you send cold emails or newsletters, your #1 enemy is spam folders.

But checking deliverability costs $55-500/mo across tools like GlockApps,
MXToolbox, Mail-Tester, and Litmus.

That's insane for solo operators.

2/ So I built inbxr.us — 10 free tools in one:

- Email Test (send → see inbox vs spam)
- Sender Check (SPF/DKIM/DMARC + 100 blocklists)
- Spam Risk Scorer
- Inbox Placement Test
- Subject Line A/B Tester
- Email Verifier
- Blacklist Monitor
- Warm-up Tracker
- BIMI Checker
- Header Analyzer

3/ The best part: everything works without signing up.

No credit card. No 7-day trial. No "contact sales."

Just paste your email, enter your domain, or send a test — get results.

4/ Free accounts get 50 checks/day.

Pro ($29/mo) adds alerts, PDF reports, AI rewrite suggestions, and trend tracking.

Agency ($79/mo) adds team workspaces and bulk verification.

5/ Try it: https://inbxr.us

If your emails are going to spam, you'll know why in 30 seconds.

Feedback welcome — I'm building this in public.
```

**Daily post ideas (rotate these):**

```
Post 1 (problem):
"Your welcome emails are going to spam and you don't know it.

Most SaaS founders never check.

Free tool to find out in 30 seconds: inbxr.us"

Post 2 (comparison):
"GlockApps: $55/mo
MXToolbox: $129/mo
Mail-Tester: $9.90/mo
Litmus: $500/mo

INBXR: Free.

Same checks. No credit card. inbxr.us"

Post 3 (pain point):
"If you're doing cold outreach and NOT monitoring your domains,
you're burning money.

One blacklist = 30% drop in deliverability.

Check your domains free: inbxr.us/sender"

Post 4 (social proof / milestone):
"X domains checked on INBXR this week.

Most common issue: missing DMARC record (68% of scans).

Took 30 seconds to fix. Check yours: inbxr.us/sender"

Post 5 (tip + CTA):
"Quick deliverability checklist before your next send:

[ ] SPF record set
[ ] DKIM signing active
[ ] DMARC policy published
[ ] Not on any blocklists
[ ] Subject line scores 70+

Check all 5 in one scan: inbxr.us"

Post 6 (cold email specific):
"Warming up a new domain for cold email?

Track your daily send volumes and know exactly when you're ready to scale.

Free warm-up tracker: inbxr.us/warmup"

Post 7 (newsletter specific):
"Your newsletter open rate dropped.

Before you blame the subject line, check if your domain got blacklisted.

Takes 10 seconds: inbxr.us/sender"
```

---

### LinkedIn (2-3 posts)

**Post 1:**
```
I spent 6 months building a free alternative to GlockApps and MXToolbox.

Here's why:

Email deliverability tools are overpriced. If you're a solo founder,
freelancer, or small agency, paying $100-500/mo just to check if your
emails land in the inbox is ridiculous.

So I built INBXR (inbxr.us):

→ Send a test email, see if it hits inbox or spam
→ Check sender reputation across 100+ blocklists
→ Get SPF/DKIM/DMARC fix records with one click
→ Score your email copy for spam triggers
→ A/B test subject lines
→ Verify email addresses
→ Monitor domains for blacklist changes

It's free. No trial. No credit card.

If you send cold emails, newsletters, or transactional email — give it a try
and tell me what's missing.

https://inbxr.us

#emailmarketing #deliverability #SaaS #buildinpublic
```

---

## WEEK 2 — Product Hunt Launch

### Product Hunt Listing

**Tagline:** Free email deliverability toolkit — replace 4 paid tools with one

**Description:**
```
INBXR is a free suite of 10 email deliverability tools:

🔍 Email Test — Send a real email, see where it lands (inbox, spam, promotions)
🛡️ Sender Check — SPF/DKIM/DMARC auth + 100+ blocklist scan + DNS fix records
📊 Spam Risk Scorer — Paste email copy, get 0-100 risk score with trigger breakdown
📬 Inbox Placement — Multi-provider inbox vs spam detection
✍️ Subject Line Scorer — A/B test up to 10 subjects across 7 dimensions
✅ Email Verifier — Syntax, MX, disposable, catch-all, SMTP mailbox check
📡 Blacklist Monitor — Track up to 5 domains against 100+ DNSBLs with alerts
🔥 Warm-up Tracker — Log daily volumes for IP/domain warm-up campaigns
🏷️ BIMI Checker — Validate BIMI records, SVG logos, and VMC certificates
📋 Header Analyzer — Paste raw headers, get auth verdicts and routing analysis

Built for cold emailers, newsletter operators, and email consultants who are
tired of paying $55-500/mo for GlockApps, MXToolbox, Mail-Tester, or Litmus.

Everything works without signing up. Free accounts get 50 checks/day.
Pro ($29/mo) adds alerts, PDF reports, and AI-powered rewrite suggestions.
```

**First Comment (maker comment):**
```
Hey PH! 👋

I built INBXR because I was spending $200+/mo across GlockApps, MXToolbox,
and Mail-Tester just to monitor email deliverability for a few domains.

The core insight: 90% of deliverability checks can be done with DNS lookups,
DNSBL queries, and IMAP checks — no reason to charge $100/mo for that.

So I built a free toolkit that does it all:
- Spam risk scoring
- Full sender authentication audit
- Real inbox placement testing
- Blacklist monitoring
- And 6 more tools

The free tier is genuinely useful (50 checks/day). Pro adds power features
like automated alerts, PDF reports, and AI rewrite suggestions.

I'm a solo dev — built this with Flask, vanilla JS, and SQLite. No React,
no Tailwind, no VC funding. Just a useful tool.

Would love your feedback on what to build next!
```

---

## WEEK 3-4 — SEO + Content Marketing

### Target Keywords (high intent, low competition)

| Keyword | Monthly Volume | Difficulty | Target Page |
|---------|---------------|------------|-------------|
| glockapps alternative | 200 | Low | /pricing or blog post |
| email deliverability test free | 500 | Medium | / (homepage) |
| check if email goes to spam | 1,200 | Medium | / (homepage) |
| spf dkim dmarc checker | 800 | Medium | /sender |
| email blacklist check | 1,500 | Medium | /sender |
| email subject line tester | 900 | Medium | /subject-scorer |
| bimi record checker | 300 | Low | /bimi |
| email warm up tracker | 200 | Low | /warmup |
| email header analyzer | 600 | Medium | /header-analyzer |
| verify email address free | 2,000 | High | /email-verifier |
| mxtoolbox alternative | 150 | Low | blog post |
| mail tester alternative | 100 | Low | blog post |

### Blog Posts to Write (SEO-focused)

1. "GlockApps vs INBXR: Free Alternative for Email Deliverability Testing"
2. "How to Check If Your Emails Are Going to Spam (Free Tool)"
3. "SPF, DKIM, and DMARC Explained: Set Up in 10 Minutes"
4. "Best Free Email Deliverability Tools in 2026 (Compared)"
5. "How to Warm Up a New Email Domain for Cold Outreach"
6. "Why Your Newsletter Open Rates Dropped (And How to Fix It)"
7. "Email Blacklist Check: How to Find and Remove Listings"
8. "MXToolbox vs INBXR: Which Email Tool Should You Use?"

---

## WEEK 4+ — Outreach & Partnerships

### Cold Outreach to Newsletter Operators

**Subject:** Your newsletter might be hitting spam — free check

```
Hey [Name],

I read [Newsletter Name] — love your stuff on [topic].

Quick heads up: I built a free tool (inbxr.us) that checks email
deliverability. Ran your sending domain through it and noticed
[specific finding if you pre-checked, e.g., "no DMARC record" or
"listed on 1 minor blocklist"].

Not a sales pitch — the tool is free. Just thought you'd want to know.

If you find it useful, I'd love a mention or share. But no pressure either way.

Cheers,
[Your name]
```

### YouTube / Newsletter Sponsorship Targets

- Cold email YouTube channels (list the top 10 cold email YouTubers)
- Email marketing newsletters (Email Geeks, Really Good Emails, etc.)
- SaaS review sites (SaaShub, Product Hunt alternatives pages)

### Directory Submissions (free listings)

1. **AlternativeTo** — list as alternative to GlockApps, MXToolbox, Mail-Tester, Litmus
2. **G2** — create vendor profile
3. **Capterra** — free listing
4. **SaaSHub** — submit product
5. **BetaList** — submit as launch
6. **Hacker News (Show HN)** — post during weekday morning EST
7. **Indie Hackers** — product listing + build in public updates
8. **ToolFinder** — free SaaS directory
9. **SaaSWorthy** — comparison site listing
10. **There's An AI For That** — list AI rewrite feature

---

## Metrics to Track

| Metric | Week 1 Target | Month 1 Target |
|--------|--------------|----------------|
| Signups | 50 | 500 |
| Daily active checks | 100 | 1,000 |
| Reddit post upvotes | 20+ | — |
| Product Hunt upvotes | — | 100+ |
| First paying customer | — | 5-10 |
| Organic search clicks | — | 200/week |

---

## Quick Wins (Do Today)

- [ ] Post on r/coldemail (highest conversion potential)
- [ ] Post on r/emailmarketing
- [ ] Tweet launch thread
- [ ] Submit to AlternativeTo (free, takes 5 min)
- [ ] Submit to SaaSHub (free, takes 5 min)
- [ ] Google Search Console — submit sitemap.xml
- [ ] Set up Google Analytics via admin panel (/admin/settings)
