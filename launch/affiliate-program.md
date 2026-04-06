---
title: InbXr Affiliate Program — Landing Page Copy + Terms
status: draft
target_audience: email marketers, agency consultants, growth bloggers, ESP consultants
payout: 30% recurring on Pro/Agency subscriptions + flat fee per AppSumo code redeemed
notes: |
  Draft of the public-facing affiliate program page and the terms.
  Requires a referral tracking system (not yet built — see "What we need to build" section).
---

# InbXr Affiliate Program

## Public landing page copy

### Hero

**Earn 30% recurring on every InbXr customer you refer.**

InbXr reads the 7 inbox signals every email list is broadcasting — bounce exposure, MPP-adjusted engagement, dormancy, authentication standing, and 3 more — and gives list owners one Signal Score. If you work with email marketers, agencies, or senders who care about deliverability, this is a tool they will thank you for sending them to.

[Apply to the program →](#apply)

---

### Why InbXr affiliates earn more than most SaaS referrals

**30% recurring.** Not first-month. Not first-year. As long as the customer you referred is paying InbXr, you're earning 30% of their subscription.

**$50+ average lifetime value per referral.** Pro is $49/mo and Agency is $129/mo. A single Agency referral who sticks for 12 months is $464 to you.

**No caps. No tiers. No clawbacks.** One flat 30% rate. Forever.

**AppSumo bonus.** For the lifetime of our AppSumo listing, affiliates who refer paying customers *outside* AppSumo get an extra $10 flat fee on top of the 30% recurring. This keeps the program worth running during the AppSumo promotion period.

---

### What makes InbXr easy to recommend

Most deliverability tools sell features. InbXr sells a mechanism: "read the 7 signals your list is broadcasting." That's easy to explain in one tweet, one email, or one conversation. You don't have to become an InbXr expert to refer a customer — you just have to agree with the framing.

And the underlying tool backs up the pitch:

- Free Signal Score via CSV upload (so you can tell prospects "try it before you even sign up")
- MPP detection that actually works (User-Agent + Apple IP + timing, not just the iCloud domain check that most competitors use)
- Microsoft May 2025 DMARC compliance check built into Inboxer Sender Check
- AI-generated Recovery Sequences for re-engagement
- Signal Rules with dry-run mode by default (so customers don't nuke their lists by accident)

---

### Who this program is built for

- **Email marketing consultants** — refer your clients to a tool that continuously monitors what you diagnosed once
- **Deliverability agencies** — white-label the Signal Score reports for your own engagement (Agency tier only)
- **Growth and marketing bloggers** — write one article, earn for years
- **ESP resellers and Mailchimp/ActiveCampaign consultants** — add InbXr to your standard onboarding for new clients
- **Email geeks with audiences** — Substack, Twitter/X, LinkedIn, Indie Hackers, Superpath

This is **not** a good fit for generic "deals" affiliate blogs or coupon sites. We won't approve applications from those.

---

### How payouts work

- Tracked via [your chosen referral tracking tool] — unique link per affiliate
- 60-day cookie window
- Monthly payouts via Stripe Connect or Wise (your choice at signup)
- Minimum payout threshold: $50
- First payout 30 days after first referred customer's first paid month (refund protection)

---

### Apply to the program

The program is invite-only for the first 50 affiliates. Apply by emailing **partners@inbxr.us** with:

- Your name + the URL where you'd promote InbXr (website, newsletter, YouTube, podcast, etc.)
- Your audience size and how you'd position the tool to them
- One InbXr feature you're most excited to write about

Applications are reviewed weekly. Approvals are manual — we're looking for fit, not volume.

---

## Internal FAQ (not published on public page)

**Why 30% not 40%?**

30% recurring is already above the SaaS affiliate median (which is 20-25% recurring). Going higher cuts into the runway we need to actually deliver the product. 30% keeps the program sustainable at scale.

**Why no cookie longer than 60 days?**

60 days is standard. Extending to 90+ days creates attribution conflicts when customers compare us during a multi-month research phase. Clean cutoff, clean relationship.

**Why invite-only for the first 50?**

Because we need to hand-pick the initial cohort to establish the program's reputation. A single bad affiliate posting coupon spam can damage the program's search reputation (Google penalizes affiliate-heavy backlink patterns when they're suspicious). First 50 should be people whose audiences are genuinely aligned.

---

## What we need to build before this launches

This page is a draft — the underlying infrastructure doesn't exist yet. Before publishing:

### 1. Referral tracking system (XS-M effort)

Options:
- **Simplest:** FirstPromoter, Rewardful, or Tolt (hosted SaaS, ~$50/mo, Stripe integration included)
- **Middle:** Build a lightweight tracker in-app — `users.referred_by_affiliate_id` column, unique affiliate URLs, dashboard for affiliates to see their referrals
- **DIY:** UTM + manual reconciliation (works for first 10 affiliates, doesn't scale)

Recommendation: **Tolt or FirstPromoter for $50/mo**. Do not build this in-house on $0 revenue.

### 2. Affiliate dashboard

Minimum features:
- Their unique referral link
- List of referred users (masked email, signup date, current tier)
- Pending + paid commission totals
- Payout history

If using Tolt/FirstPromoter, this comes out of the box.

### 3. Stripe Connect integration for payouts

If using Tolt/FirstPromoter: handled automatically.

If building in-house: add Stripe Connect onboarding flow + monthly payout scheduler job.

### 4. Terms of Service + Affiliate Agreement

Draft legal doc covering: payout terms, prohibited promotion methods (no bidding on "InbXr" search terms, no cookie stuffing, no fake claims), termination conditions, refund-triggered clawback language.

Template: https://termly.io/resources/templates/affiliate-agreement/

### 5. Tracking pixel on thank-you page

Required for Tolt/FirstPromoter to register the conversion. Needs to fire after successful Stripe Checkout redirect to `/dashboard?welcome=1`.

### 6. Copy for affiliate onboarding email sequence

3 emails:
- Welcome + here's your link + here's how to promote honestly
- Day 7: "Here are 3 article angles that perform well"
- Day 30: "Your first 30 days — here's what worked for other affiliates"

---

## Launch sequencing

**DO NOT publish this page until:**

1. Phase 6a engine work is live in production
2. AppSumo listing is submitted (so referrers have something specific to promote)
3. Pillar post is published and indexed (so referrers have something to link to)
4. Referral tracking infrastructure is wired up
5. First 10 invite-only affiliates have been hand-picked and approached privately

**Then:** soft-launch the public page to the invite-only cohort first, let them test the links and flow, then open public applications 2 weeks later.
