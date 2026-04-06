---
title: InbXr — Cold Outreach Email Sequence
status: draft
target_audience: ICPs (agency owners managing client lists, SaaS founders 10k+ list, ecommerce ops on AC/MC)
sequence_length: 4 emails over 14 days
sending_tool: Brevo (existing wired account)
notes: |
  Each email is <120 words. Plain text only — no images, no buttons, no HTML decoration.
  Subject lines optimized for B2B inbox curiosity, not click-bait.
  Each email has ONE call to action.
  Day-1 email is permission-asking, not selling. The sale is Email 3.
---

# Cold Outreach Email Sequence — InbXr Phase 6b Launch

## Sequence overview

| # | Day | Purpose | CTA |
|---|---|---|---|
| 1 | Day 0 | Curiosity + permission | Reply yes/no |
| 2 | Day 4 | Specific insight (re: their domain) | Reply with the answer |
| 3 | Day 7 | The pitch | Free Signal Score link |
| 4 | Day 14 | Soft breakup | Optional reply |

---

## Email 1 — Day 0 (Curiosity + permission)

**Subject:** quick read on {{company}}'s list?

Hey {{first_name}},

Quick one — I built a tool that reads 7 signals every email list is broadcasting (bounce exposure, MPP-adjusted engagement, dormancy buildup, authentication standing, etc.) and gives you a single score before you hit send.

I ran it against {{company}}'s sender domain on a hunch. The result was interesting enough that I wanted to ask before sharing — would it be useful if I sent over what I found?

Just reply "yes" or "no". No pitch, no automation chain. If you say no I'll go away.

— Joe
InbXr.us

---

## Email 2 — Day 4 (Insight delivery — only sent if Email 1 got "yes")

**Subject:** the one signal {{company}} is broadcasting

Hey {{first_name}},

As promised — here's what jumped out on {{company}}:

**{{insight}}** *(example: "Your DMARC is set to p=none. Microsoft's May 2025 enforcement rejects p=none for bulk senders, which means a chunk of your Outlook/Hotmail mail is getting routed to spam before content scoring even happens.")*

This is one of the 7 signals InbXr tracks. The fix is usually a 30-minute DNS edit, not a tool purchase. If you want, I can walk you through it on a 15-min call (no charge, no pitch — I just like fixing this one because it has the highest leverage of any signal in the framework).

Reply "walk me through it" if useful.

— Joe

---

## Email 2-alt — Day 4 (Insight delivery — for senders with no obvious SPF/DKIM/DMARC issue)

**Subject:** {{company}}'s engagement is cleaner than most

Hey {{first_name}},

Your authentication setup checks out — that puts {{company}} in the top ~30% of senders I've audited.

The signal I'd watch instead is **Engagement Trajectory adjusted for Apple Mail Privacy Protection**. By 2026, MPP accounts for ~60% of opens on most lists, which means your reported open rate is wildly inflated and your "active" segment is half-asleep.

Most tools that claim to handle MPP just check `@icloud.com` addresses — that catches about 15% of real MPP opens. The other 85% are Gmail users reading on iPhone.

If you want a free read on what your *real* engagement number looks like after stripping MPP, I can run it against a CSV export. Reply with one and I'll send back a Signal Score in 60 seconds.

— Joe

---

## Email 3 — Day 7 (The pitch)

**Subject:** the tool I built (InbXr)

Hey {{first_name}},

I've been replying out of a tool I built called **InbXr**. It reads all 7 inbox signals (the MPP-adjusted engagement, the DMARC compliance, the dormancy cohorts, the bounce exposure, etc.) and gives you a Signal Score out of 100 with a recommended action for the weakest signal.

It connects to Mailchimp, ActiveCampaign, Mailgun, and AWeber for automatic per-contact data, or runs against a CSV upload if you'd rather not connect.

If the conversation we've been having is the kind of thing you'd want a tool to do continuously instead of by hand:

→ Free Signal Score (60 seconds, no signup): https://inbxr.us/signal-score

If you sign up after the free read, the lifetime AppSumo deal is $59 for the first tier and there's a 60-day refund window. No subscription, no upsells, no surprise renewal emails.

— Joe

---

## Email 4 — Day 14 (Soft breakup)

**Subject:** closing the loop on {{company}}

Hey {{first_name}},

This is the last one — I won't keep emailing if we never connect.

If the 7-signals framing was useful and you just haven't had time, no pressure. The free Signal Score link is still good (https://inbxr.us/signal-score) and the AppSumo deal will be live for the next ~30 days.

If the framing wasn't useful or doesn't fit how you think about deliverability, I'd love a one-line reply telling me what was off — that's worth more to me than a sale.

Either way, thanks for reading.

— Joe
InbXr.us

---

## Targeting notes

### ICP 1 — Email marketing agency owners (5-50 client lists)
- **Source:** LinkedIn Sales Navigator filter "Email Marketing Manager" + "Agency" in company description
- **Volume:** 200/week
- **Hook:** Signal Rules + multi-client dashboard pitch in Email 3
- **Insight angle (Email 2):** "Your client {{client_name}}'s domain DMARC is broken — that affects every campaign you send for them"

### ICP 2 — SaaS founders with 10k+ lists
- **Source:** Public ProductHunt + Indie Hackers profiles, anyone with a published email count
- **Volume:** 100/week
- **Hook:** Signal Score + automated weekly report pitch in Email 3
- **Insight angle (Email 2):** "Your engagement number is probably 40% inflated by MPP"

### ICP 3 — Ecommerce ops on Mailchimp/ActiveCampaign
- **Source:** Mailchimp Experts directory, ActiveCampaign Certified Consultants directory
- **Volume:** 100/week
- **Hook:** ESP integration + Signal Map pitch in Email 3
- **Insight angle (Email 2):** "Your acquisition cohort from Black Friday is dragging your overall engagement down"

---

## Per-prospect research checklist (do this BEFORE sending Email 1)

- [ ] Pull their sender domain from a recent newsletter
- [ ] Run Inboxer Sender Check against it
- [ ] Note SPF/DKIM/DMARC status
- [ ] Check Reputation Watch for any blocklist hits
- [ ] Note their probable ESP (header analysis)
- [ ] Find one specific thing to mention in Email 2

If you can't find anything specific to say in Email 2, **don't send Email 1 to that prospect.** Cold outreach without a real insight is spam. The whole point of this sequence is that Email 2 earns the right to send Email 3.

---

## Reply handling triage

| Reply type | Response |
|---|---|
| "Yes, send it" | Send Email 2 within 24h |
| "No" | Stop sequence. Add to Brevo "do_not_email" list. |
| "What's InbXr?" | Send Email 3 directly (skip Email 2). |
| "How much?" | Reply with the AppSumo deal + free Signal Score link. |
| Out of office / autoresponder | Hold sequence, resume Day +7 from OOO end. |
| Bounce / unsubscribe | Honor immediately. Update Brevo. |

---

## Compliance notes

- All cold outreach goes through a separate Brevo sub-account from the main InbXr transactional traffic, so any complaints don't poison the product domain reputation.
- Sender domain is `outreach.inbxr.us` (subdomain) with its own SPF/DKIM/DMARC.
- One-click unsubscribe on every email (Brevo handles this automatically).
- B2B addresses only — no consumer email outreach.
- US CAN-SPAM and EU GDPR-compliant: physical address in footer, opt-out honored within 24h.
