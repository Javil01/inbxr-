---
title: Microsoft's May 2025 DMARC Enforcement — What Changed and How to Fix It in 30 Minutes
slug: microsoft-dmarc-2025-enforcement
target_keyword: dmarc 2025 microsoft requirements
secondary_keywords:
  - microsoft bulk sender 2025
  - dmarc p=none rejected
  - spf dkim dmarc outlook 2025
  - dmarc policy fix
meta_description: As of May 2025, Microsoft rejects mail from bulk senders with DMARC p=none. Here's what changed, how to check your current policy, and a step-by-step fix you can complete in under 30 minutes.
canonical_url: https://inbxr.us/blog/microsoft-dmarc-2025-enforcement
publish_status: draft
estimated_word_count: 1600
---

# Microsoft's May 2025 DMARC Enforcement — What Changed and How to Fix It in 30 Minutes

On May 1, 2025, Microsoft rolled out the bulk sender requirements it announced in late 2024. The headline rule: **senders of more than 5,000 emails per day to Outlook, Hotmail, and Live addresses must have SPF, DKIM, *and* DMARC, and the DMARC policy must be `quarantine` or `reject` — not `none`.**

If you're sending to Microsoft mailboxes with a DMARC policy of `p=none` in 2026, you are out of compliance. Microsoft's enforcement is real — not a warning, not a soft-fail, but actual routing decisions against your mail before the content is even scored.

This post breaks down what changed, how to check where you stand in 30 seconds, and exactly what DNS edits to make. Budget 30 minutes.

---

## What Microsoft's requirements actually say

Here's the one-paragraph version of the Microsoft Defender for Office 365 bulk sender enforcement, effective May 1, 2025:

> Senders of more than 5,000 messages per day to Outlook.com, Hotmail.com, or Live.com mailboxes must authenticate with SPF, DKIM, and DMARC. The DMARC policy must be set to `p=quarantine` or `p=reject`. A policy of `p=none` will be treated as unauthenticated, and messages may be rejected or marked as spam.

Unpacking the important details:

1. **"5,000 messages per day" is the bulk-sender threshold.** If you send fewer than 5,000/day to Microsoft addresses, the strict rule technically doesn't apply — but Microsoft reserves the right to enforce it earlier for any sender showing signs of abuse.
2. **`p=none` is now treated as unauthenticated.** This is the biggest change. Before May 2025, `p=none` at least meant "report to me, don't block." After May 2025, at Microsoft, it means "Microsoft will treat this mail as if you have no DMARC at all."
3. **One-click List-Unsubscribe (RFC 8058) is also required.** Any modern ESP handles this for you, but if you're sending from a custom system, add `List-Unsubscribe-Post: List-Unsubscribe=One-Click` to your headers.

This is not a Microsoft-specific pattern. Gmail and Yahoo did the same thing in February 2024. All three major providers are now aligned on the same rule set.

---

## How to check where you stand in 30 seconds

You need to know three things:

1. Is SPF present and valid?
2. Is DKIM present and valid?
3. What is your DMARC policy?

The fastest way to check all three at once is to run [Inboxer Sender Check](https://inbxr.us/sender) against your sending domain. It's free, takes about 30 seconds, and returns a pass/fail on each requirement with the exact DNS record to look at.

If you'd rather check manually, here's the command-line version:

```bash
# SPF — look for "v=spf1" in TXT record
dig TXT yourdomain.com +short

# DKIM — depends on your selector (often "default._domainkey" or "selector1._domainkey")
dig TXT default._domainkey.yourdomain.com +short

# DMARC — always "_dmarc" subdomain
dig TXT _dmarc.yourdomain.com +short
```

A passing DMARC record looks something like:

```
v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com; pct=100; adkim=s; aspf=s
```

A failing DMARC record looks like either:

```
v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com   # FAILS Microsoft
```

Or worse, no DMARC record at all.

---

## The 30-minute fix — going from `p=none` to `p=quarantine`

If you have `p=none` today and want to get compliant, here's the step-by-step.

### Step 1: Verify SPF and DKIM are both passing (10 minutes)

Before tightening DMARC, make sure your legitimate mail is passing SPF *or* DKIM alignment. DMARC only works if at least one of these passes. Tightening DMARC on top of a broken SPF/DKIM setup will cause your own mail to be rejected.

Send a test email to yourself (preferably an address you can read the raw headers from — Gmail's "Show original" is fine). Look for these header lines:

```
Authentication-Results: ...;
    spf=pass smtp.mailfrom=mail.yourdomain.com;
    dkim=pass header.d=yourdomain.com;
    dmarc=pass header.from=yourdomain.com
```

If SPF and DKIM both say `pass`, you're safe to move to Step 2. If either one says `fail` or `none`, fix that first — tightening DMARC won't help.

### Step 2: Add or update your DMARC record (5 minutes)

Log into your DNS provider (GoDaddy, Cloudflare, Route 53, etc.) and find the TXT record at `_dmarc.yourdomain.com`.

If there's no DMARC record, create a new TXT record:

- **Host/Name:** `_dmarc`
- **Type:** `TXT`
- **Value:** `v=DMARC1; p=quarantine; pct=10; rua=mailto:you@yourdomain.com; sp=quarantine; adkim=r; aspf=r`

Key things about this record:

- **`p=quarantine`** — DMARC policy, meets Microsoft's requirement
- **`pct=10`** — percentage of mail subject to the policy. Starting at 10% gives you a safe rollout window to catch misconfigurations before they affect your whole send volume
- **`rua=mailto:...`** — receives daily aggregate reports so you can see what's passing and failing
- **`sp=quarantine`** — applies the policy to subdomains too
- **`adkim=r` and `aspf=r`** — relaxed alignment (more forgiving than strict)

### Step 3: Wait 24-48 hours and read the aggregate reports (variable)

DMARC aggregate reports land in your `rua` mailbox daily. They show which sending sources passed and which failed. If something legitimate is failing (e.g., your transactional ESP that you forgot to include in SPF), fix it now before you scale up `pct`.

Tools like [Dmarcian](https://dmarcian.com) or [Postmark's free DMARC monitor](https://dmarc.postmarkapp.com) can parse the XML reports into a readable dashboard.

### Step 4: Scale up from `pct=10` to `pct=100` (over 1-2 weeks)

Once you've verified nothing legitimate is being caught, increase `pct` in steps:

- Day 1-3: `pct=10`
- Day 4-7: `pct=25`
- Day 8-10: `pct=50`
- Day 11+: `pct=100`

If aggregate reports stay clean at each step, keep going.

### Step 5: Consider moving from `quarantine` to `reject` (optional)

`p=quarantine` meets Microsoft's bulk sender requirement. `p=reject` is stricter and gives you slightly better protection against spoofing, but it's also less forgiving if you make a DNS change later. Most senders should stay at `p=quarantine` unless they have a compelling spoofing concern.

---

## Common mistakes that cause this fix to fail

1. **Multiple `v=spf1` records on the same domain.** DMARC-aware receivers will fail SPF if they see more than one SPF record. Consolidate them into one.
2. **Forgetting to include your ESP's sending IPs in SPF.** If you send through Mailchimp, ActiveCampaign, Mailgun, AWeber, or Brevo, you need to include their SPF mechanism (e.g., `include:mailgun.org`). Your ESP's docs will tell you the exact string.
3. **DKIM selector not configured.** Some ESPs require you to publish DKIM keys in DNS as part of domain verification. If you skipped this step, DKIM will fail silently.
4. **Catch-all DMARC forwarding.** If you set `rua=mailto:someone-else@someone-else.com`, that other domain needs an MX record + inbox that accepts XML attachments. Easiest to use a dedicated aggregator service.
5. **Changing DMARC before verifying alignment.** SPF and DKIM must be *aligned* with the From: domain, not just passing. Check Authentication-Results headers carefully.

---

## How to verify you're now compliant

After making the change, run these checks:

1. **[Inboxer Sender Check](https://inbxr.us/sender)** on your domain — should show DMARC `p=quarantine` or `p=reject`
2. **Send a test to outlook.com and hotmail.com addresses** you control — check headers for `dmarc=pass`
3. **Wait 24 hours and read the first aggregate report** — should show mostly `dmarc=pass` from your sending IPs

If all three check out, you're compliant with Microsoft's May 2025 bulk sender requirements. (And Gmail's, and Yahoo's — all three providers use equivalent rules.)

---

## Where this fits in the 7-signal framework

Authentication Standing is Signal 06 of the [7 Inbox Signals](./pillar-post-7-inbox-signals.md). It's weighted at 5 points out of 100 on the composite Signal Score — the lowest weight of any signal, but only because it's a *gating* signal rather than a scaling one.

What this means in practice: a broken Authentication Standing doesn't just cost you 5 points. It costs you the *entire Signal Score*, because providers route your mail to spam before the other 6 signals even get evaluated.

Fix this first. Every other signal improvement is downstream.

---

## FAQ

**Do I need DMARC if I send fewer than 5,000 emails/day to Microsoft?**

Technically no, but you should have it anyway. Gmail and Yahoo's February 2024 rules apply at the same threshold, and Microsoft reserves the right to enforce earlier for senders that look abusive. The cost of adding DMARC is 30 minutes. The cost of not having it can be months of recovering from a deliverability incident.

**What if I use a shared sending IP from my ESP?**

DMARC operates at the domain level, not the IP level. Shared IPs are fine as long as your ESP signs with DKIM using your domain and your SPF includes your ESP's sending infrastructure.

**My domain has DMARC `p=none` because I'm still in "monitoring mode." When can I safely move to `p=quarantine`?**

When your aggregate reports show >95% of mail passing DMARC alignment for 2 weeks straight. If you're not reading your aggregate reports, you're not actually monitoring — you're just hoping.

**I switched to `p=quarantine` and now my own mail is going to spam at Outlook. What happened?**

One of two things: (a) something in your sending path is not aligned (check Authentication-Results headers), or (b) you moved too fast and didn't scale `pct` gradually. Roll back to `pct=10` and diagnose.

---

*Want an automatic read on whether you're compliant with Microsoft, Gmail, and Yahoo's 2024-2025 requirements? [Run Inboxer Sender Check →](https://inbxr.us/sender)*
