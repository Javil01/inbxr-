# InbXr — Bulletproof Marketing Plan

## The Core Thesis

InbXr is the only email tool that fixes deliverability AND copy. Every competitor stops at "your email has a problem." InbXr tells you what's wrong, rewrites it, and lets you test again. This is the angle for everything below.

**One-line pitch:** "The only tool that helps you land in the inbox and land the sale."

**Category we own:** Email Copy Intelligence (nobody else is in this space)

---

## PHASE 1: FOUNDATION (Week 1-2)
*Goal: Get the infrastructure right so every visitor counts.*

### 1.1 Analytics — DO THIS FIRST
Without analytics, everything below is wasted. You can't optimize what you can't measure.

**Action items:**
- [ ] Go to `/admin/settings` on inbxr.us
- [ ] Paste your GA4 Measurement ID (format: G-XXXXXXXXXX)
- [ ] If you don't have GA4: go to analytics.google.com → create account → create property → get the ID
- [ ] Set up these GA4 events as custom conversions:
  - `sign_up` — account creation
  - `upgrade_click` — clicked upgrade button
  - `test_run` — ran an email test
  - `framework_view` — visited Framework Lab
- [ ] Install Microsoft Clarity (free heatmaps + session recordings): clarity.microsoft.com — paste the script in admin settings

**Why first:** Every Reddit post, tweet, and PH launch drives traffic. Without analytics, you'll never know which channel converts. This takes 15 minutes and pays for itself immediately.

### 1.2 Stripe Verification
- [ ] Confirm these env vars are set in Railway:
  - `STRIPE_SECRET_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `STRIPE_PRICE_PRO`
  - `STRIPE_PRICE_AGENCY`
- [ ] Test the full upgrade flow: click Upgrade → Stripe Checkout → payment → redirect back
- [ ] Set up the webhook endpoint in Stripe Dashboard: `https://inbxr.us/billing/webhook`
- [ ] Test with Stripe test mode first, then switch to live

### 1.3 Email System
- [ ] Confirm `BREVO_API_KEY` is set in Railway
- [ ] Confirm `BASE_URL=https://inbxr.us` is set
- [ ] Test: sign up with a real email, verify the verification email arrives
- [ ] Test: password reset flow works end-to-end

---

## PHASE 2: LAUNCH WEEK (Week 2-3)
*Goal: Get your first 500-1,000 visitors and first 50 signups.*

### 2.1 Product Hunt Launch (Tuesday or Wednesday)

**Timing:** Schedule for 12:01 AM PT on a Tuesday or Wednesday. These are the highest-traffic days.

**Preparation (day before):**
- [ ] Create your Product Hunt maker profile if you don't have one
- [ ] Prepare 3-4 screenshots/GIFs:
  1. The 4-act hero animation (screen record it — Spam → Report → Fix → Primary)
  2. Framework Lab grid with the C3PO method visible
  3. A real report showing the copy score, fix plan, and framework detection
  4. The AI rewrite with before/after toggle showing PAS framework structure
- [ ] Use the listing copy from `LAUNCH_KIT.md`
- [ ] Have 5-10 people ready to upvote and comment in the first hour (friends, colleagues, anyone)

**Launch day:**
- [ ] Post at 12:01 AM PT
- [ ] Post the maker comment immediately
- [ ] Respond to every comment within 30 minutes
- [ ] Share the PH link on Twitter, LinkedIn, and any communities you're in
- [ ] Post on Indie Hackers: "I just launched InbXr on Product Hunt — here's why I built it"

**Expected results:** 200-2,000 visitors depending on upvotes. Even a modest launch (50 upvotes) gets you indexed on PH forever and drives long-tail traffic.

### 2.2 Reddit Campaign (3 posts over 3 days)

**Rules:**
- One post per day, different subreddits
- Never post all 3 the same day (looks like spam, gets flagged)
- Respond to every comment genuinely
- Don't delete and repost if it doesn't blow up — that gets you banned

**Schedule:**
- **Day 1 (same day as PH):** r/emailmarketing — copy intelligence angle
- **Day 2:** r/coldoutreach — deliverability angle
- **Day 3:** r/SaaS — builder story angle

All copy is ready in `LAUNCH_KIT.md`.

**Pro tips:**
- Post between 8-10 AM EST (peak Reddit traffic)
- Your Reddit account needs some karma first — spend a few days commenting genuinely on other posts before your launch week
- If a post gets traction, DO NOT edit in more links. Just respond to comments.

### 2.3 Twitter/X Threads (3 threads over the week)

**Schedule:**
- **Monday:** Thread 1 — "Your emails are going to spam" (deliverability hook)
- **Wednesday:** Thread 2 — "16 copywriting frameworks for email" (educational value)
- **Friday:** Thread 3 — "I built a tool that competes with Warmy" (builder story)

**Pro tips:**
- Tweet threads between 8-10 AM EST or 12-1 PM EST
- After posting the thread, quote-tweet the first tweet with a one-line summary
- Pin the best-performing thread to your profile
- Follow and engage with people in the email marketing / cold outreach space for a week before your launch

### 2.4 Directory Submissions (batch these in one sitting)

Submit to all of these in one 2-hour session. All copy is in `LAUNCH_KIT.md`.

**Free directories (do all of these):**
- [ ] AlternativeTo (alternative to Warmy, GlockApps, Mail-Tester)
- [ ] SaaSHub
- [ ] ToolPilot
- [ ] There's An AI For That
- [ ] SaaSWorthy
- [ ] StartupStash
- [ ] BetaList (if you position as early-stage)
- [ ] Indie Hackers product listing
- [ ] MicroLaunch

**Paid/review directories (do these later):**
- [ ] G2 (free to list, paid for featured placement)
- [ ] Capterra (free listing)
- [ ] GetApp

**Why this matters:** Directory listings are permanent backlinks. They drive long-tail SEO traffic for months. One afternoon of submissions pays off for years.

---

## PHASE 3: CONTENT ENGINE (Week 3-6)
*Goal: Build organic traffic that compounds. Every blog post is a landing page.*

### 3.1 SEO Blog Strategy

Your blog auto-generates posts, but you need **strategic** posts targeting high-intent keywords. Write (or have AI help draft) these specific posts:

**Tier 1 — Bottom-of-funnel (people ready to buy):**
1. "Best email deliverability tools 2026 (free + paid comparison)"
2. "Warmy alternatives: cheaper tools that do more"
3. "GlockApps vs InbXr: which email testing tool is better?"
4. "Free email deliverability test — no signup required"
5. "How to check if your emails are going to spam (free tool)"

**Tier 2 — Middle-of-funnel (people learning):**
6. "PAS framework for email: complete guide with 10 examples"
7. "AIDA email examples: templates that actually convert"
8. "How to write cold emails that don't go to spam"
9. "Email copy scoring: what it is and why it matters"
10. "16 copywriting frameworks every email marketer should know"

**Tier 3 — Top-of-funnel (awareness):**
11. "Why your emails land in Gmail's Promotions tab (and how to escape)"
12. "SPF, DKIM, DMARC explained in plain English"
13. "Email deliverability checklist for 2026"
14. "What is BIMI and does your brand need it?"
15. "How to warm up a new email domain (step-by-step)"

**Each post must include:**
- A CTA to the relevant InbXr tool (use the existing `[CTA:/tool-path]` system)
- Internal links to 2-3 other InbXr blog posts
- A "Try it free" CTA at the end
- Target keyword in the title, H1, meta description, and first paragraph

**Publishing schedule:** 2-3 posts per week. Your blog engine can auto-generate, but manually write the Tier 1 posts — those are the money pages.

### 3.2 Framework Lab as Content Marketing

The Framework Lab is your secret weapon for organic traffic. Each framework is a potential landing page.

**Create standalone pages or blog posts for:**
- "PAS Framework: Problem-Agitate-Solve for Email (with AI Examples)"
- "AIDA Framework for Email Marketing: Step-by-Step Guide"
- "The C3PO Method: InbXr's Proprietary Email Framework"
- "BAB Framework: Before-After-Bridge Email Templates"

Each page links to `/frameworks` and shows how InbXr detects and applies the framework. This captures search traffic from copywriters looking for framework guides — then converts them with the tool.

---

## PHASE 4: OUTBOUND (Week 4-8)
*Goal: Get paying customers through direct outreach.*

### 4.1 Agency Outreach

Email marketing agencies are your Agency tier ($79/mo) buyers. They manage multiple client domains and need tools that scale.

**Find targets:**
- Search LinkedIn for "email marketing agency" or "email deliverability consultant"
- Search Google for "email marketing agency [city]"
- Look at Clutch.co and UpCity agency directories
- Check who follows Warmy, GlockApps, and Mailchimp on Twitter

**Email template:**
```
Subject: Quick question about your client email audits

Hi [Name],

I noticed [Agency] manages email campaigns for multiple clients.
Quick question: how are you currently auditing deliverability
and copy quality across client domains?

I built InbXr — it does full deliverability audits (SPF, DKIM,
DMARC, 110+ blocklists) plus something no other tool does:
it scores email copy and detects which copywriting framework
the email follows. Your team can apply any of 16 frameworks
to AI rewrites and test the result instantly.

Agency plan is $79/mo for unlimited domains and team seats.
Worth a 5-minute look?

https://inbxr.us

— Jose
```

**Volume:** Send 10-15 personalized emails per day. Not bulk — personalized. Reference their actual clients or recent work.

### 4.2 Cold Outreach Community Presence

**LinkedIn:**
- Post 2-3x per week about email deliverability tips
- Share real insights (not product pitches) — "I checked 100 domains and 62% had misconfigured DMARC. Here's what they all had in common."
- Comment on posts from email marketing influencers
- Join LinkedIn groups: Email Marketing Professionals, Cold Email Outreach, B2B Sales

**Email marketing Slack/Discord communities:**
- Email Geeks (Slack)
- Demand Curve (community)
- RevGenius (Slack)
- Cold Email Outreach (Facebook group)

**Rule:** For every 1 self-promotional post, do 10 genuine helpful comments/answers. Build credibility first.

### 4.3 Partnership Outreach

**Who to partner with:**
- ESP platforms (Mailchimp, ConvertKit, Beehiiv) — "recommend InbXr as a deliverability companion"
- Cold outreach tools (Lemlist, Instantly, Smartlead) — "integrate InbXr as a pre-send check"
- Copywriting courses/communities — "use Framework Lab as a teaching tool"
- Email deliverability consultants — "white-label or recommend InbXr to your clients"

Start with 5 partnership conversations. Even one successful integration drives sustained traffic.

---

## PHASE 5: SOCIAL PROOF (Week 6-12)
*Goal: Get real testimonials, case studies, and reviews.*

### 5.1 Get Your First 10 Reviews

**Strategy:** Offer free 30-day Pro access to anyone who writes an honest review.

- [ ] Add a banner in the dashboard: "Love InbXr? Write a review on G2 and get 30 days of Pro free"
- [ ] Email your first 20 signups personally — ask for feedback, then ask if they'd review
- [ ] Post in r/emailmarketing: "I'm giving 30 days of Pro to anyone who reviews my tool (honest reviews only)"

**Where to get reviews:**
- G2 (most valuable for B2B credibility)
- Capterra
- Product Hunt (comments count as social proof)
- Trustpilot

### 5.2 Build Case Studies

Find 3 users who got measurable results and write up their story:

**Template:**
- **Before:** "Company X had 60% inbox placement and a D copy score"
- **What they did:** "Used InbXr to fix DMARC, applied PAS framework to their welcome sequence"
- **After:** "92% inbox placement, A copy score, 31% increase in open rates"

Even if the numbers are modest, real results beat no results. Ask early users if you can feature them.

### 5.3 Create a "Wall of Wins"

Add a section to the homepage or a `/customers` page that shows:
- Screenshot of a real report showing improvement
- Quote from a user
- Before/after metrics

Start collecting these from day one. Every support interaction is an opportunity to ask "did this help?"

---

## PHASE 6: PAID GROWTH (Month 2-3)
*Goal: Test paid channels once organic baseline is established.*

### 6.1 Google Ads (start here)

**Budget:** $10-20/day to start.

**Target keywords (high intent, low competition):**
- "email deliverability test free"
- "check if email goes to spam"
- "email copy analyzer"
- "SPF DKIM DMARC checker"
- "email spam score checker"

**Ad copy:**
```
Headline: Free Email Deliverability Test | InbXr
Description: Check SPF, DKIM, DMARC + 110 blocklists.
Score your copy. Get AI rewrites. No signup needed.
```

**Landing page:** Send to `/` (homepage) — the free test with no signup is your conversion machine.

### 6.2 Retargeting

Set up Facebook/Instagram retargeting pixel. Show ads to people who:
- Visited InbXr but didn't sign up
- Ran a free test but didn't create an account
- Created a free account but didn't upgrade

**Retargeting ad:** "You tested your email. Did you fix it? Your InbXr report is waiting — upgrade to Pro for AI rewrites and 16 copywriting frameworks."

### 6.3 Sponsor Email Newsletters

Find newsletters in the email marketing / SaaS space and sponsor a mention:
- TLDR Marketing ($$$)
- Email Monday (niche, cheaper)
- SaaS Weekly
- Indie Hackers newsletter

Budget: $100-500 per placement depending on the newsletter. One well-placed newsletter mention can drive 200-1,000 signups.

---

## TRACKING & METRICS

### What to track weekly:
| Metric | Target (Month 1) | Target (Month 3) |
|---|---|---|
| Website visitors | 2,000/mo | 10,000/mo |
| Free signups | 100/mo | 500/mo |
| Email test runs | 500/mo | 2,500/mo |
| Pro upgrades | 5-10 | 30-50 |
| MRR | $145-290 | $870-1,450 |
| Framework Lab visits | 200/mo | 1,000/mo |

### Channel attribution:
- Product Hunt: track with UTM `?ref=producthunt`
- Reddit: track with UTM `?ref=reddit`
- Twitter: track with UTM `?ref=twitter`
- Blog: track organic search traffic in GA4
- Directories: track with UTM per directory

---

## BUDGET SUMMARY

### Month 1 (Launch): $0-100
- Product Hunt: free
- Reddit: free
- Twitter: free
- Directory submissions: free
- Indie Hackers: free
- Time investment: ~20 hours

### Month 2 (Growth): $200-500
- Google Ads: $300-400
- Newsletter sponsorship: $100-200
- Everything else continues free

### Month 3 (Scale): $500-1,000
- Google Ads: $400-600
- Retargeting ads: $100-200
- Newsletter sponsorships: $200-400
- Partner outreach: free (time only)

---

## THE 30-DAY ACTION CALENDAR

### Week 1: Foundation
- Mon: Set up GA4 + Clarity
- Tue: Verify Stripe + test upgrade flow
- Wed: Verify email system (Brevo)
- Thu: Submit to 5 free directories
- Fri: Submit to 5 more directories

### Week 2: Launch
- Mon: Post Twitter thread #1
- Tue: Launch on Product Hunt + post on r/emailmarketing
- Wed: Post on r/coldoutreach + Twitter thread #2
- Thu: Post on r/SaaS
- Fri: Post on Indie Hackers + Twitter thread #3

### Week 3: Content
- Mon: Publish "Best email deliverability tools 2026" blog post
- Tue: Publish "PAS framework for email" blog post
- Wed: Send 10 agency outreach emails
- Thu: Publish "How to check if emails go to spam" blog post
- Fri: Send 10 more agency outreach emails

### Week 4: Momentum
- Mon: Publish "Warmy alternatives" blog post
- Tue: LinkedIn post + engage in 3 communities
- Wed: Send 10 agency outreach emails
- Thu: Ask first 10 users for reviews
- Fri: Publish "AIDA email examples" blog post + weekly metrics review

---

## THE ONE THING THAT MATTERS MOST

If you do nothing else from this plan, do this:

**Get 10 real people to use InbXr and tell you what they think.**

Not pageviews. Not signups. Real people who paste a real email, read their report, and tell you if it helped. That feedback will be worth more than every marketing tactic above combined — because it'll tell you what to say in your marketing, what to fix in your product, and whether the positioning actually resonates.

Find them on Reddit. DM them on Twitter. Ask them in Slack communities. Offer to run their email through InbXr live on a call. The first 10 users define everything that comes after.
