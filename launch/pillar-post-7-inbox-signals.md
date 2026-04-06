---
title: The 7 Inbox Signals Every Email List is Broadcasting (and How to Read Them)
slug: 7-inbox-signals-email-list-health
target_keyword: 7 inbox signals
secondary_keywords:
  - email list health score
  - email deliverability indicators
  - apple mail privacy protection adjusted engagement
  - dmarc 2025 microsoft enforcement
  - email list decay rate
meta_description: Every email list is constantly broadcasting 7 signals that determine whether your next campaign hits the inbox or the spam folder. Here's what they are, how to measure each one, and what to do when one drops.
canonical_url: https://inbxr.us/blog/7-inbox-signals-email-list-health
publish_status: draft
estimated_word_count: 2400
---

# The 7 Inbox Signals Every Email List is Broadcasting (and How to Read Them)

Most senders only check one signal before they hit send: **bounce rate**.

That's like checking your tire pressure before a road trip and ignoring the engine, the oil, the brakes, the alignment, the battery, the coolant, and the fuel. Bounce rate tells you if a few addresses are dead. It does not tell you whether the inbox providers think your list is alive.

Your list is broadcasting **seven signals** at all times. Every send is a stress test of all seven. Most senders only know how to read one of them, and that's why they get blindsided when a campaign that "looked fine on paper" lands in spam.

This post breaks down all seven signals — what they measure, how to read them, what a healthy reading looks like, and what to do when one drops below the line.

If you read nothing else, read **Signal 02**. It's the one almost nobody is measuring correctly in 2026, and it's the leading indicator for everything else.

---

## Why "deliverability" is a useless number on its own

When senders say "my deliverability is 97%," they usually mean:

- 97% of the addresses I sent to didn't hard-bounce, OR
- 97% of opens registered against my campaign, OR
- 97% of seed inboxes got a copy in their primary tab

None of these tell you what you actually want to know, which is: **is my list trending toward the spam folder, and how fast?**

Deliverability is an *outcome*. It's downstream of seven upstream signals that, taken together, predict where you're heading. If you only watch the outcome, you only find out after the damage is done.

The 7 signals exist *upstream* of deliverability. Read them right and you can fix things before the next send. Read them wrong (or not at all) and you find out from your unsubscribe rate.

---

## Signal 01 — Bounce Exposure

**What it measures:** the percentage of your list that is *likely to bounce on the next send*, factoring in known hard bounces, role addresses, disposable domains, and catch-all signals.

**Why it matters:** ESPs measure bounce rate per send. A spike above ~2% triggers throttling at Gmail and Yahoo. A spike above ~5% triggers blocks. But here's the trap: your bounce rate from your *last* send doesn't predict your *next* send. Bounce Exposure does.

**How to read it:**

| Reading | Status |
|---|---|
| <2% | Healthy. Send confidently. |
| 2-5% | Watch. One bad import will tip you over. |
| 5-10% | Risk. Suppress before next send. |
| >10% | Danger. Stop sending until cleaned. |

**The thing nobody tells you:** role addresses (`info@`, `support@`, `admin@`) are not the same as bounces, but they behave like them at the inbox provider level — they're often unattended mailboxes that mark mail as spam without opening it. If 8% of your list is role addresses, your bounce rate looks fine but your complaint rate is silently elevated.

**Fix it by:** running list verification, suppressing role/disposable/catch-all flags, and warming up new domains slowly.

---

## Signal 02 — Engagement Trajectory (Apple-MPP-adjusted)

**This is the signal nobody is measuring correctly.**

**What it measures:** real human engagement over the last 30 days, after subtracting Apple Mail Privacy Protection machine opens.

**Why it matters:** Since iOS 15 (September 2021), Apple Mail prefetches every email image on a relay server and registers an "open" before the user has even seen the message. By 2026, **Apple Mail accounts for roughly 60% of opens across most lists**. That means your reported open rate is wildly inflated, and your engagement-based segmentation is broken.

If your "active subscriber" list is half-full of people whose only "engagement" was Apple's prefetch bot, you are sending to a list that is *much colder* than your dashboard shows.

**The detection trap:** most "MPP-adjusted" features in deliverability tools just check if the recipient address ends in `@icloud.com`. **This catches about 15% of real MPP opens**, because MPP fires based on the *email client*, not the recipient mailbox. A Gmail user reading on their iPhone triggers MPP — but their address is `@gmail.com`.

**How to detect MPP correctly:**

1. **User-Agent string parsing** (Mailgun events): MPP opens come from `Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/...` with no human interaction signature
2. **Apple IP range check**: MPP relays come from Apple's `17.0.0.0/8` AS714 range
3. **Timing heuristic**: MPP opens fire within seconds of delivery — humans don't read in under 3 seconds
4. **iCloud domain fallback**: lowest-confidence catch for the ~15% of users on Apple-owned mailboxes

You need at least two of these to filter MPP reliably. One is not enough.

**How to read Engagement Trajectory:**

| Real engagement (30d) | Status |
|---|---|
| >25% | Healthy list. |
| 15-25% | Average. |
| 8-15% | Cold. Recovery needed before next promo. |
| <8% | Critical. List is unprofitable to send to. |

**Fix it by:** running a recovery sequence on at-risk segments before sending another bulk campaign, or suppressing dormant cohorts.

---

## Signal 03 — Acquisition Quality

**What it measures:** the day-1, day-7, and day-30 engagement of contacts grouped by their *acquisition cohort* (when they joined your list).

**Why it matters:** different acquisition channels produce different list health. A contact from an organic newsletter signup is worth roughly 4-6x a contact from a paid lead magnet, by lifetime engagement. A contact from a co-marketing webinar is worth even more. A contact from a list purchase is worth less than nothing.

You can't see this from your aggregate engagement number. You have to slice by cohort.

**How to read it:**

| Cohort day-1 engagement | Quality assessment |
|---|---|
| >25% | High intent, retain hard |
| 15-25% | Normal |
| 8-15% | Soft acquisition, run welcome series |
| <8% | Cold cohort, isolate from main list |

**The thing nobody tells you:** if your acquisition channel mix is 70% paid lead magnets and 30% organic, your *blended* engagement number is misleading. Two campaigns from now, the lead-magnet cohort drags everything down. You should be reporting Signal 03 by source, not in aggregate.

**Fix it by:** isolating cold cohorts into a separate list, running a 3-email welcome series before they ever see a promo, and pausing acquisition channels that produce <10% day-1 engagement.

---

## Signal 04 — Domain Reputation

**What it measures:** two things at once — the reputation of *your sending domain* with the major inbox providers, and the *concentration of recipient domains* on your list.

**Why it matters:** Sender reputation is the obvious half. The half nobody talks about is recipient concentration. If 40% of your list is on Yahoo/AOL, you live or die by Yahoo/AOL's filters. Post-April 2024 Yahoo enforcement, that's a much spikier risk than Gmail-heavy lists.

**Healthy distributions look roughly like:**

- Gmail: 35-50%
- Outlook/Hotmail: 15-25%
- Yahoo/AOL: 10-20%
- Other: balance

If any single provider is over 50%, you are concentrated, and a single policy change at that provider can wipe out your deliverability overnight. (This is what happened to a lot of fitness and nutrition lists when Yahoo/AOL tightened in 2024.)

**Check your sender side at:** [InbXr Inboxer Sender Check](https://inbxr.us/sender) — runs SPF/DKIM/DMARC + blocklist checks against your sending domain in 30 seconds.

**Fix it by:** authenticating properly (Signal 06), spreading sends across providers if you have control over acquisition, and watching the blocklist monitors religiously.

---

## Signal 05 — Dormancy Risk

**What it measures:** the percentage of your list that has been inactive for 180+ days and 365+ days.

**Why it matters:** Long-dormant contacts are the most likely to do four things, in order of severity:

1. Hard bounce (the address has been recycled)
2. Become a spam complaint (they don't remember signing up)
3. Hit a recycled spam trap (Gmail/Yahoo seed dormant addresses as honeypots)
4. Drag your overall sender reputation down passively

A 365-day-dormant contact is worth roughly **negative six** active contacts to your reputation. Sending to them costs you more than not sending to them.

**How to read it:**

| 180+ day dormant | 365+ day dormant | Status |
|---|---|---|
| <10% | <5% | Healthy |
| 10-25% | 5-15% | Watch — re-engagement needed |
| 25-40% | 15-30% | Risk — segment and isolate |
| >40% | >30% | Danger — suppress and rebuild |

**A note on "spam trap exposure":** some tools claim to measure spam trap density. Real spam traps are honeypot addresses seeded by Spamhaus, Abusix, Cloudmark, and the major inbox providers. **You cannot infer them from dormancy.** Anyone selling you a "spam trap exposure score" without integrating a paid trap data feed is showing you dormancy risk with a misleading label. Dormancy risk *is* worth measuring — just call it what it is.

**Fix it by:** running a 2-3 email re-engagement sequence on the 180+ day cohort, suppressing the 365+ day cohort, and setting a Signal Rule that auto-flags new dormants.

---

## Signal 06 — Authentication Standing

**What it measures:** how well your sending domain meets the 2024-2025 enforcement requirements from Gmail, Yahoo, and Microsoft.

**Why it matters:** Three policy changes have hit in the last two years:

1. **Gmail/Yahoo bulk sender requirements (February 2024):** SPF + DKIM + DMARC required for senders >5,000/day, plus one-click List-Unsubscribe headers
2. **Microsoft bulk sender enforcement (May 2025):** DMARC `p=none` no longer accepted; must move to `quarantine` or `reject`
3. **Apple/Yahoo content tightening (rolling 2024-2026):** stricter HTML rendering, link reputation, and image-to-text ratio enforcement

If your DMARC is missing or `p=none`, you are out of compliance with at least one major provider as of 2026. That's not a "soft" issue — it's a routing decision that happens before your content is even scored.

**How to read it:**

| Setup | Score |
|---|---|
| SPF + DKIM + DMARC `p=reject` + List-Unsubscribe | Full compliance |
| SPF + DKIM + DMARC `p=quarantine` + List-Unsubscribe | Mostly compliant |
| SPF + DKIM + DMARC `p=none` | Partially compliant — Microsoft will reject |
| Missing DMARC | Out of compliance with all three |
| Missing SPF or DKIM | Will fail authentication checks at scale |

**Fix it by:** running [Inboxer Sender Check](https://inbxr.us/sender) and following the remediation steps in the report. Most fixes are 30 minutes of DNS edits.

---

## Signal 07 — Decay Velocity

**What it measures:** the rate of change of your overall list health over time. Specifically, how fast your composite signal score is dropping (or rising).

**Why it matters:** A list with a Signal Score of 75 trending *down* 5 points/week is in worse shape than a list with a Signal Score of 60 trending *up*. Snapshot scores are misleading without trajectory.

**How to read it:**

| Trajectory | Status |
|---|---|
| +0.5 to +5/week | Improving — keep doing what you're doing |
| -0.5 to +0.5/week | Stable |
| -0.5 to -2/week | Slow decline — investigate the weakest signal |
| -2 to -5/week | Fast decline — pause large sends |
| <-5/week | Free fall — emergency triage |

**A note on predictive claims:** some tools will tell you "your list will hit the danger zone in 23 days." Most of those numbers are if-else logic dressed up as machine learning. If you don't have at least 6 months of historical signal scores from comparable senders, you can't make a real prediction. Trend language ("declining toward danger") is honest. Day-count predictions usually aren't.

**Fix it by:** identifying the weakest of the other 6 signals and addressing it. Decay is always downstream of one of the others.

---

## How the 7 signals combine into a Signal Score

Once you can read all 7 signals, you can combine them into a single composite **Signal Score** out of 100, weighted by impact on actual deliverability:

| Signal | Weight |
|---|---|
| 01 Bounce Exposure | 25 |
| 02 Engagement Trajectory (MPP-adjusted) | 25 |
| 03 Acquisition Quality | 15 |
| 04 Domain Reputation | 15 |
| 05 Dormancy Risk | 10 |
| 06 Authentication Standing | 5 |
| 07 Decay Velocity | 5 |
| **Total** | **100** |

A Signal Score of 80+ means your list is in shape to send. 60-80 means watch your weakest signal. Below 60, do not send a promotional campaign — run recovery first.

---

## What to do with this

If you take one thing from this post, it's this: **the next time you're about to send a campaign, don't just check your bounce rate.** Check your Engagement Trajectory adjusted for MPP. That single number will tell you more about whether the campaign will succeed than any other metric on your dashboard.

If you take two things, add Authentication Standing. It's the cheapest fix and the highest-leverage one — 30 minutes of DNS edits can stop your mail from being routed to spam by Microsoft entirely.

If you want to read all 7 signals against your own list automatically, that's what we built [InbXr](https://inbxr.us) to do. Connect your ESP (or upload a CSV) and you'll have a Signal Score in under 60 seconds, with a recommended action for the weakest of the 7.

---

## FAQ

**How is this different from a deliverability score from GlockApps or Mail-Tester?**

GlockApps and Mail-Tester run *seed list tests* — they send a copy of your email to a known set of inboxes and measure where it lands. That's a snapshot of one campaign at one point in time. The 7 Inbox Signals look at your *list itself*, before you've even drafted the next send. They're complementary: signals tell you whether you should send, seed tests tell you how the send performed.

**Can I read these signals without an ESP integration?**

Yes — five of the seven (Bounce Exposure, Acquisition Quality, Domain Reputation, Dormancy Risk, Authentication Standing) can be calculated from a CSV upload. The two that need an ESP connection are Engagement Trajectory (which requires per-contact open/click history) and Decay Velocity (which requires score history over time).

**My ESP doesn't expose per-contact engagement data. Now what?**

Mailchimp, ActiveCampaign, Mailgun, and AWeber expose enough per-contact data to read all 7 signals. Instantly, Smartlead, and GoHighLevel only expose aggregate stats — for those, you'll get reads on the 4 aggregate signals (Bounce Exposure, Domain Reputation, Authentication Standing, Decay Velocity) and the engagement-dependent signals will use ESP-aggregate fallbacks.

**How often should I check my Signal Score?**

Before every send for promotional campaigns. Weekly otherwise. The InbXr scheduler runs Signal Watch automatically every 6 hours for connected ESPs and emails you a weekly Signal Report.

---

*Want to read the 7 signals on your own list? [Get your Signal Score in 60 seconds →](https://inbxr.us/signal-score)*
