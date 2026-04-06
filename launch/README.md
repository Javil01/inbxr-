# InbXr — Phase 6b Launch Artifacts

Drafted during Phase 6a buildout. None of these are live yet — they're ready
for review and execution once the engine work has shipped to production and
been smoke-tested in the wild.

## Contents

| File | Purpose | Owner action |
|---|---|---|
| `pillar-post-7-inbox-signals.md` | ~2,400 word SEO anchor. Targets "7 inbox signals". The conceptual sales piece + SEO root of the rebrand. | Publish first. |
| `pillar-post-2-apple-mpp-detection.md` | ~1,800 word secondary pillar. Targets "apple mail privacy protection detection". The "most tools get this wrong" angle. | Publish 1 week after post 1. |
| `pillar-post-3-dmarc-2025-microsoft.md` | ~1,600 word secondary pillar. Targets "dmarc 2025 microsoft requirements". The urgent fix angle. | Publish 1 week after post 2. |
| `pillar-post-4-dormancy-vs-spam-traps.md` | ~1,500 word secondary pillar. Targets "email list dormancy risk". The honesty angle (we don't fake spam trap scores). | Publish 1 week after post 3. |
| `appsumo-listing.md` | Full AppSumo listing copy: title, tagline, hero, features, comparison table, 3-tier pricing, FAQ, screenshot checklist. | Source-of-truth for the AppSumo submission form. |
| `cold-outreach-sequence.md` | 4-email cold outreach sequence (14 days) for 3 ICPs. | Set up separate Brevo sub-account on `outreach.inbxr.us`. |
| `linkedin-ad-variants.md` | 3 LinkedIn ad variants (MPP hook, DMARC hook, 7-signals hook) + $200-500 paid test plan. | Run after pillar post 1 is indexed. |
| `affiliate-program.md` | Public landing page draft + invite-only launch plan + infrastructure checklist. | Don't publish until tracking is wired up (Tolt or FirstPromoter). |

## Sequencing

These artifacts are designed to fire in a specific order:

1. **Pillar post first** — gives you a real URL to link to from cold outreach Email 3 and from the AppSumo listing's "learn more" section
2. **Cold outreach starts week 2** — gives the pillar post time to get indexed and to validate the mechanism on real prospects
3. **AppSumo submission week 4-6** — only after the cold outreach has produced 5+ paying signups so you can show traction in the submission

## What's shipped in code (not just content)

These are live in the codebase, not just in this folder:

- **Pricing page rewrite** — `templates/auth/pricing.html` refreshed with 7-signal framing, Signal Watch/Rules/Recovery/Send Readiness/Signal Map features, MPP detection callout, and a new "The 7 Inbox Signals" comparison table section
- **Onboarding email sequence** — `modules/onboarding_emails.py` + `modules/scheduler.py` + migration `023_onboarding_email_log`. 4-email signal-aware sequence (day 1 welcome, day 3 score nudge, day 7 rule nudge, day 14 check-in). Daily dispatch via APScheduler job at 14:00 UTC. Precondition SQL ensures nudge emails only fire when the user hasn't completed the thing you're nudging them toward.

## What's NOT in here yet (Phase 6d)

- Referral tracking infrastructure (Tolt or FirstPromoter integration — see affiliate-program.md for requirements)
- 3 more pillar posts (acquisition quality cohort analysis, bounce exposure validation, decay velocity trajectory)
- Substack-style newsletter opt-in for the blog
- ProductHunt launch asset pack (hunter outreach, maker comment, gallery screenshots)

## Open questions for the user

1. Are you keeping the existing Brevo account for transactional, or moving cold outreach to a separate provider like Instantly?
2. Pricing tiers in `appsumo-listing.md` are draft — confirm the contact caps + ESP integration counts before submission
3. The pillar post mentions "since iOS 15 (September 2021)" and "by 2026, ~60%" — confirm those numbers against latest data before publishing
4. Cold outreach Email 2 has two variants (with/without DMARC issue) — confirm this branching matches how you want to handle the insight delivery step
