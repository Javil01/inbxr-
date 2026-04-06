---
title: InbXr — LinkedIn Ad Creative Variants
status: draft
budget: $200-500 paid test
targeting: email marketers, growth marketers, agency owners, SaaS founders with lists
notes: |
  All variants designed for LinkedIn's 150-char headline + 600-char intro format.
  Headlines lead with curiosity or specific pain, not features or benefits.
  CTA goes to /signal-score with UTM params, not the homepage.
---

# LinkedIn Ad Variants — InbXr Phase 6b Paid Test

## Test structure

Run 3 ad variants in a single Campaign Manager campaign (Website Conversions objective). $50-75 spend per variant over 7-10 days. Kill variants that don't hit <$15 CPA on waitlist signup. Double down on the winner.

Targeting:
- Job title: Email Marketing Manager, Growth Marketer, Head of Growth, Email Marketing Specialist
- Seniority: Manager, Director, VP, C-Level
- Company size: 11-200 (avoiding enterprise)
- Industries: SaaS, E-commerce, Marketing Agency, Digital Media
- Excluded: students, entry-level, intern
- Geography: US, UK, Canada, Australia (English)

---

## Variant A — The "MPP is lying to you" hook

**Headline (150 char max):**
Your email open rate is lying to you. Here's how to read the real one.

**Intro text (600 char max):**
By 2026, Apple Mail Privacy Protection accounts for ~60% of reported opens on most email lists. Most "MPP-adjusted" tools just check if the recipient is on iCloud — which catches about 15% of real MPP opens.

InbXr reads 7 inbox signals your list is broadcasting, including real engagement *after* proper MPP detection (User-Agent + Apple IP + timing heuristics, not just domain matching).

Get your Signal Score in 60 seconds. Connect your ESP or upload a CSV. Free.

**CTA:** Get Your Signal Score

**Image concept:** Split screen. Left: "Your open rate: 42%" in big numbers. Right: "Real engagement: 17%" with a smaller, honest-looking annotation. InbXr wordmark bottom-right.

---

## Variant B — The Microsoft DMARC 2025 urgency hook

**Headline (150 char max):**
Microsoft's May 2025 DMARC rule rejected your `p=none` — did you notice?

**Intro text (600 char max):**
On May 1, 2025, Microsoft rolled out its bulk sender enforcement. Senders with DMARC policy set to `p=none` now get routed as unauthenticated at Outlook, Hotmail, and Live addresses — regardless of content quality.

If your DMARC is still `p=none`, a portion of your Microsoft-bound mail is silently going to spam. The fix is a 30-minute DNS edit.

InbXr's Inboxer Sender Check runs against your sending domain in 30 seconds and tells you exactly what to change. Free.

**CTA:** Run Inboxer Sender Check

**Image concept:** A clean DNS record snippet on dark background:
`v=DMARC1; p=none; ...` with red strikethrough
`v=DMARC1; p=quarantine; ...` with green checkmark
Caption: "The 30-minute fix."

---

## Variant C — The "7 signals" framework hook

**Headline (150 char max):**
Your email list is broadcasting 7 signals. Most senders only read one.

**Intro text (600 char max):**
Every email marketer checks bounce rate before they send. That's one signal. Your list is broadcasting six more: MPP-adjusted engagement, acquisition cohort quality, dormancy risk, domain reputation concentration, authentication standing, and decay velocity.

InbXr reads all 7 and gives you one Signal Score out of 100. Connect an ESP (Mailchimp, ActiveCampaign, Mailgun, AWeber) or upload a CSV. 60 seconds to your first read.

**CTA:** Read All 7 Signals

**Image concept:** 7 signal pills in a row with scores — e.g., "Bounce Exposure: 85", "Engagement Trajectory: 62", "Acquisition Quality: 71", etc. One pill in red to show a weakness. "Signal Score: 73 (B)" overlaid prominently.

---

## Landing page requirements

All 3 variants should land on `/signal-score?utm_source=linkedin&utm_campaign=phase6b&utm_content={variant_letter}` — not the homepage.

The `/signal-score` page needs to handle the anonymous case cleanly:
- Show the empty-state hero with "Connect ESP / Upload CSV / Sign up free"
- Gate the full dashboard behind signup
- Capture email before showing the first result (existing email gate infrastructure)

**Check:** verify the empty-state on `/signal-score` renders cleanly for unauthenticated users before launching ads. Today it redirects to login — may need a public-facing variant.

---

## Tracking setup

- LinkedIn Insight Tag installed on `/signal-score` and `/signal-score/calculate` (conversion event)
- UTM parameters persist through signup flow into `users.acquisition_source` column
- Weekly CPA review — kill variants >$15 CPA by day 5, scale variants <$10 CPA
- A/B test results logged in `launch/ad-results.md` (create after first spend cycle)

---

## Post-launch analysis template

After each variant has received $50+ in spend:

```
Variant: [A/B/C]
Spend: $____
Impressions: ____
Clicks: ____
CTR: ____
Landing page visits: ____
Signups: ____
Signal Scores calculated: ____
CPA (signup): $____
CPA (first Signal Score): $____

Kill / Keep / Scale: _____
Notes: _____
```

---

## What NOT to do

- Don't use stock photos of people looking at laptops
- Don't promise "explode your open rate" or similar BS — the whole positioning is honesty
- Don't lead with features (dashboard screenshots underperform copy-first ads on LinkedIn)
- Don't send to the homepage — always `/signal-score` with UTMs
- Don't run more than 3 variants at once on $500 budget — you'll split the data too thin to learn from
