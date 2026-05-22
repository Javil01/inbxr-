# Gumroad Setup — The Inbox Decay Rescue

The funnel:

```
inbxr.us/decay-rescue   →   Gumroad checkout   →   inbxr.us/decay-rescue/thank-you   →   /signup   →   Stripe Pro
   (sales page)             (payment + delivery)        (Pillar 7 pitch)              (email pre-filled)
```

Everything below is the one-time setup on the Gumroad side. The INBXR
side is already wired.

---

## 1. Create the Gumroad product

1. Sign in to Gumroad → **Products** → **+ New product**.
2. Product type: **Digital product**.
3. Name: `The Inbox Decay Rescue — The 6-Pillar Forensic Protocol`
4. Price: `$47` (or `$27` for the first-100-buyer launch — see pricing escalation plan).
5. **Upload the ZIP**: `The-Inbox-Decay-Rescue-Complete.zip` (the file already in `Downloads/`).
6. **Cover image / OG card**: use the same dark-navy + teal aesthetic as inbxr.us. Recommended 1280×720.

---

## 2. Product description (Gumroad's marketing copy)

Paste this into Gumroad's description field. Mirrors the landing page tone.

```
Most deliverability tools tell you what just broke.

The Inbox Decay Rescue is the 6-pillar forensic protocol agencies use to find the source — Domain, List, Copy, or Offer — BEFORE the next campaign goes out.

What you get:
• The Playbook PDF (277KB) — the methodology, end-to-end
• 30 worksheets, calculators, checklists, and templates
• 6 self-contained pillar folders — run them in order
• Lifetime access + all future updates
• 14-day no-questions refund

Built for:
• Agency owners running email for clients who need a defensible diagnosis when a campaign tanks
• Founders running cold outbound at scale who feel like they're flying blind
• Operators who've already tried "clean the list, change the subject, warm the domain" and need an actual methodology

Not for: senders who want a 30-second spam test, or someone unwilling to fill out a worksheet.

After purchase: you'll be redirected to inbxr.us where InbXr Pro is introduced as "Pillar 7 — Automation" — the same 6 pillars running on autopilot every 6 hours. The workbook is enough on its own. Pro is for when you start running this for 5+ client accounts.
```

---

## 3. Configure post-purchase redirect

This is the critical step. Gumroad's redirect sends buyers to the
thank-you page on inbxr.us with their email passed in the URL — which
the page reads and pre-fills into the `/signup` form.

**In Gumroad → product settings → "After purchase" / "Redirect URL":**

```
https://inbxr.us/decay-rescue/thank-you?email=$EMAIL
```

Gumroad supports variable substitution for `$EMAIL`, `$PURCHASE_ID`,
and `$FULL_NAME`. We only need `$EMAIL`. (If Gumroad's templating syntax
has changed, check their current docs — the variable might be
`{{purchase.email}}` or similar.)

**Verify**: do a test purchase (Gumroad has a $0 test mode). Confirm
the redirect lands at `/decay-rescue/thank-you` with the email visible
in the URL.

---

## 4. Swap the Gumroad URL on the landing page

After your Gumroad product is live, copy its public URL (looks like
`https://gumroad.com/l/somethingsomething` or
`https://yourname.gumroad.com/l/decay-rescue`).

Edit:

- **File**: `blueprints/public_signal_routes.py`
- **Constant**: `DECAY_RESCUE_GUMROAD_URL`
- **Replace**: `https://gumroad.com/l/REPLACE_WITH_GUMROAD_PRODUCT_SLUG`
- **With**: your live Gumroad URL

Commit + push. Railway redeploys in 1-3 minutes. Both CTA buttons on
`/decay-rescue` now point at Gumroad.

---

## 5. Build the post-purchase email sequence (Brevo)

Gumroad delivers the file automatically. Brevo handles the 7-day
nurture sequence that converts workbook buyers to InbXr Pro. Suggested
schedule (you'll need to author the bodies; subjects are placeholders):

| Day | Subject (placeholder) | Goal |
|-----|----------------------|------|
| 1   | Your Pillar 1 starter pack is inside | Get them to run the Real Engagement Calculator on one list |
| 3   | The 3 most common Pillar 2 verdicts (and what to do with each) | Walk through the diagnostic |
| 5   | "Which pillar do I run next?" — interpreting your Verdict | Help them pick their rescue |
| 7   | The agencies that don't churn clients all run Pillar 6 | Sell the monitoring rhythm — soft Pro mention |
| 14  | Most buyers upgrade by week 2. Here's why. | The Pro pitch — direct |
| 21  | Decay Velocity is the signal you can't read by hand | Re-engagement for non-upgraders |
| 30  | Last call: workbook → Pro 14-day trial | Final upgrade pitch |

**Triggering**: Gumroad sends a webhook on purchase. Wire it to a Brevo
list "Decay Rescue Buyers" via Zapier or a custom Gumroad webhook
endpoint on inbxr.us. (Future build — not in this iteration.)

---

## 6. Update the workbook itself (one-time, before publishing)

The workbook PDF currently doesn't reference InbXr. To convert better:

1. Add a one-page "Pillar 7 — Automation" insert at the end of the playbook PDF, mirroring the thank-you page pitch.
2. Add a small footer to each pillar's worksheets: `→ Or run this in InbXr Pro: [tool name]`.

These embedded references convert 3-5× better than separate
marketing. Worth a v1.1 release once you have time.

---

## 7. Track conversions

Once live, measure:

- **Workbook → Pro conversion within 30 days** (target: 8-15%)
- **Workbook → Agency conversion within 90 days** (target: 2-5%)
- **Which email in the sequence drives most upgrade clicks** (tells you which pillar's labor pain is sharpest)
- **Workbook-buyer LTV vs. cold-INBXR-signup LTV** (should be ≥2× higher)

InbXr admin already tracks user acquisition source via the
`?from=decay-rescue` URL param on `/signup` — those signups land in
the CRM with a clear attribution.

---

## What's NOT set up yet (deliberate, can build later)

- **Gumroad webhook → Brevo list automation** — for now, manually
  export buyers from Gumroad weekly and import into Brevo.
- **One-click upgrade with saved card** — the thank-you page sends
  buyers to `/signup` then Stripe. True one-click would require Stripe
  Link or a passwordless signup flow. Pre-filled email is the practical
  90% solution.
- **Agency cross-sell inside Pro dashboard** — a contextual banner
  shown to Pro users with 3+ monitored domains pitching Agency. Build
  this once Pro has real buyers.
