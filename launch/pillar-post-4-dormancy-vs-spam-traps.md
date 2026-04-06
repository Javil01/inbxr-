---
title: Dormancy Risk vs Spam Trap Exposure — What You Can Actually Measure
slug: dormancy-risk-vs-spam-traps
target_keyword: email list dormancy risk
secondary_keywords:
  - spam trap detection
  - recycled spam trap
  - email list decay
  - dormant contact suppression
meta_description: Many deliverability tools advertise "spam trap exposure" scores calculated from dormancy depth. Real spam traps are seeded honeypots you can't infer from list data. Here's what dormancy risk actually tells you — and what it doesn't.
canonical_url: https://inbxr.us/blog/dormancy-risk-vs-spam-traps
publish_status: draft
estimated_word_count: 1500
---

# Dormancy Risk vs Spam Trap Exposure — What You Can Actually Measure

If you've shopped for deliverability tools in the last few years, you've probably seen "Spam Trap Exposure" or "Spam Trap Risk" as a feature. Some tools show you a percentage. Some show you a grade. A few claim to flag individual contacts as "likely spam traps."

Here's the uncomfortable truth: **almost none of those scores measure what they claim to measure.** Real spam traps are honeypot addresses seeded by Spamhaus, Abusix, Cloudmark, and the major inbox providers. You cannot infer them from list data. Anyone selling you a spam trap score calculated from dormancy depth is showing you *dormancy risk* with a misleading label.

That's not to say dormancy risk is useless — it's a real and important signal. It's just not the same thing as spam trap exposure, and conflating the two leads to wrong decisions.

This post breaks down what spam traps actually are, what dormancy risk actually measures, and why the distinction matters.

---

## What real spam traps actually are

Spam traps come in three flavors:

### 1. Pristine traps

Addresses that were never used by a real person. Spamhaus, Abusix, and Cloudmark create these specifically to trap senders who harvest email addresses or scrape the web. They plant them in obscure web directories, in whois records of seized domains, and in other places where no human would sign them up. If you send to a pristine trap, you almost certainly acquired the address through dirty means.

Pristine traps are the most damaging to sender reputation.

### 2. Typo/low-quality traps

Typo domains like `gmial.com`, `yaho.com`, `hotmial.com`. Some inbox providers operate these as traps to catch senders who don't validate input. If 2% of your signups are typos, you're hitting typo traps.

These are less damaging than pristine traps but still signal poor list hygiene.

### 3. Recycled traps

Addresses that *were* real users but have been abandoned for >12 months, then repurposed as traps by the inbox provider. Gmail, Yahoo, and Microsoft all do this at scale — they seed dormant addresses as traps and watch which senders still hit them.

Recycled traps are the category that dormancy-depth tools *almost* measure. The logic is: "if a contact hasn't engaged in 365+ days, they might have been converted to a trap." That's plausible but imprecise.

---

## Why you can't infer spam traps from list data

Here's the problem. All three trap types live inside address spaces you can't distinguish from normal addresses:

- **Pristine traps** look like ordinary `firstname@domain.com` addresses. They were created by hand or generated to look real.
- **Typo traps** look like typos because they *are* typos.
- **Recycled traps** look like any other dormant contact — because 12 months ago, they *were* any other dormant contact.

You cannot run a regex, a lookup table, or a machine learning model against your list and find the spam traps. The only way to know is:

1. Send to the list and watch for complaints / blocklist hits from Spamhaus, Abusix, Cloudmark
2. Hash-match against a paid spam trap data feed (these are expensive — enterprise-only)
3. Use a list verification service that has proprietary trap coverage (and even then, coverage is partial)

None of these are "run a calculation on your existing list data." If a tool is telling you a spam trap exposure score without doing one of the three above, they're showing you something else.

---

## What dormancy risk actually measures (and why it matters)

Dormancy risk is what most tools are actually calculating when they claim to measure spam traps. It's the percentage of your list that has been inactive for specific thresholds:

- **180+ days inactive:** at-risk contacts
- **365+ days inactive:** high-risk contacts

This is a legitimate signal. Long-dormant contacts are statistically more likely to:

1. **Hard bounce** — the address has been abandoned or recycled to a new user
2. **File spam complaints** — they don't remember signing up
3. **Drag your sender reputation down passively** — even without engagement, they count in the denominator
4. **Be converted to recycled spam traps** — the overlap with trap territory is real but partial

A 365-day-dormant contact is worth roughly **negative six** active contacts to your reputation. Sending to them costs you more than not sending to them.

**This is important and actionable.** You just shouldn't call it "spam trap exposure" because you're not measuring traps directly — you're measuring the pool from which traps are drawn.

---

## How to read Dormancy Risk correctly

| 180+ day dormant | 365+ day dormant | Status |
|---|---|---|
| <10% | <5% | Healthy |
| 10-25% | 5-15% | Watch — re-engagement needed |
| 25-40% | 15-30% | Risk — segment and isolate |
| >40% | >30% | Danger — suppress and rebuild |

**Fix it by:**

1. Running a 2-3 email re-engagement sequence on the 180+ day cohort
2. Suppressing the 365+ day cohort entirely (the math favors suppression over re-engagement past 365 days)
3. Setting a recurring rule that auto-flags new dormants as they cross the threshold

The [InbXr Signal Rules](https://inbxr.us/signal-rules) system has pre-built templates for this: "Suppress dormant 365+" and "Alert on 180+ dormancy rate > 25%." Both default to dry-run mode so you can preview the affected contacts before anything touches your live list.

---

## What to do if you actually need spam trap detection

If you genuinely need spam trap detection (not dormancy risk), you have three options, in order of cost:

### Option 1: Monitor Spamhaus / Abusix / Cloudmark listings proactively

Set up monitoring of all three public blocklists for your sending domain + IP. If any of them list you, investigate immediately. You won't know *which* specific contact was the trap, but you'll know *that* you hit one.

[Reputation Watch](https://inbxr.us/blacklist-monitor) in InbXr covers 110+ blocklists including the three majors, checked every 6 hours.

### Option 2: Use a list verification service with spam trap coverage

Some paid verification services (ZeroBounce Pro, DataValidation) claim partial spam trap coverage via proprietary hashed feeds. Their coverage is incomplete — typically single-digit percentages of real traps — but it's better than zero.

### Option 3: License a commercial trap data feed

Enterprise-only. Costs are measured in the thousands-per-month range. Vendors include Validity, Kickbox's enterprise tier, and a few others. This is the only path to real trap detection, and it's cost-prohibitive for most senders.

For senders in the small business to mid-market range, the right move is usually Option 1 (monitor blocklists) + aggressive dormancy suppression. You don't actually need to know *which* contact is the trap — you just need to not send to the population where traps live.

---

## How this fits the 7 Inbox Signals

In the [7 Inbox Signals framework](./pillar-post-7-inbox-signals.md), Signal 05 is **Dormancy Risk**, not "Spam Trap Exposure." That's a deliberate naming choice — call things what they are.

Dormancy Risk is weighted at 10 points out of 100 on the composite Signal Score, because it's a leading indicator for both complaints and hard bounces. If you suppress the 365+ day cohort and keep new dormants from accumulating, you raise this score by 8-10 points without touching any other signal.

---

## FAQ

**If I suppress my 365+ day dormant contacts, will my sender reputation improve?**

Yes, usually within 2-4 weeks. The mechanism is that removing low-engagement contacts raises your *engaged rate* as seen by inbox providers, which they use as a proxy for "do people actually want this mail." The effect is strongest at Gmail (which is heavily engagement-weighted) and Outlook (which is heavily complaint-weighted).

**What about the 180-day cohort? Should I re-engage or suppress?**

Re-engage. The math favors a 2-3 email re-engagement sequence for contacts in the 180-365 day range. Any contact who opens or clicks during the sequence goes back on the active list. Anyone who doesn't engage within 4 weeks of the sequence joins the 365+ suppress cohort.

**Does an unengaged contact become a spam trap automatically after 12 months?**

No. Recycled traps are created by inbox providers deliberately, and they pick specific abandoned addresses — not all dormant contacts. But you can't predict which ones, so the defensive move is to treat the whole dormant cohort as potentially risky.

**Does MPP prefetch count as "engagement" for dormancy calculation?**

It shouldn't. If you're calculating dormancy from ESP-reported opens without MPP adjustment (Signal 02), you're seeing 40-60% of contacts as "active" when they're actually dormant humans whose Apple Mail happened to prefetch a recent campaign. Real dormancy calculation requires MPP-adjusted engagement.

---

*Want a real read on your Dormancy Risk (and the other 6 signals, without the fake spam trap claim)? [Get your Signal Score →](https://inbxr.us/signal-score)*
