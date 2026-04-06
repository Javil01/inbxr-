# INBXR Signal Intelligence — Build Spec

**Status:** Phase 1 complete. Phase 2+ in progress.
**Target:** Transform INBXR into a deliverability intelligence platform built around The 7 Inbox Signals framework.
**Timeline:** 3-5 months realistic from Phase 0 (skipped) through Phase 6 launch.

This document is the canonical reference for the engineering phases. All decisions here are **locked** unless explicitly revisited. Do not deviate without updating this file.

---

## The 7 Inbox Signals (Locked Definitions)

| # | Signal | Weight | Data requirement | What it measures |
|---|---|---|---|---|
| 01 | **Bounce Exposure** | 25 | Per-contact verification flags + historical bounces | Predictive bounce risk — valid-today contacts likely to bounce in 30-60 days |
| 02 | **Engagement Trajectory** (MPP-adjusted) | 25 | Per-contact last_open/click/reply dates + MPP detection | Real human engagement direction, with Apple MPP machine opens removed (hybrid detection per ESP) |
| 03 | **Acquisition Quality** | 15 | Per-contact acquisition_date + first-30-day engagement | Inferred from day-1 engagement cohort rates — organic vs cold |
| 04 | **Domain Reputation** | 15 | Sender blacklist status + recipient domain distribution | Both sides of the reputation equation |
| 05 | **Dormancy Risk** (renamed from "Spam Trap Exposure") | 10 | Per-contact engagement timeline | Age-weighted risk from dormant contacts (not actual traps) |
| 06 | **Authentication Standing** | 5 | SPF/DKIM/DMARC policy + List-Unsubscribe, scored vs 2025 ISP mandates | Compliance posture against Gmail 2024 + Microsoft May 2025 enforcement |
| 07 | **Decay Velocity** | 5 | Signal score history (2+ snapshots) | Rate and direction of list degradation — trend language only |

**Total: 100 points → Signal Score → Grade A/B/C/D/F**

**Grade thresholds:** A ≥ 90, B ≥ 75, C ≥ 60, D ≥ 45, F < 45

---

## Locked Decisions (Phase 1 output)

### 1. MPP Detection — Hybrid per-ESP

Use the best-available method per ESP based on what data each exposes:

| ESP | Method | Accuracy | Implementation |
|---|---|---|---|
| **Mailgun** | User-Agent string parsing + Apple IP range check (17.0.0.0/8) | High (~90%) | Parse `user-agent` header from events API + check source IP |
| **Mailchimp** | Timing heuristic (<2s after send = machine) + iCloud domain fallback | Medium (~40-60%) | Timestamp delta + domain check |
| **ActiveCampaign** | Timing heuristic + iCloud domain fallback | Medium (~40-60%) | Same as Mailchimp |
| **AWeber** | Timing heuristic + iCloud domain fallback | Medium (~40-60%) | Same as Mailchimp |

**UI:** Each connected ESP shows an "MPP accuracy: High / Medium" badge. Signal Score dashboard explains that MPP adjustment quality varies by ESP data source.

**Code contract:** `detect_mpp_open(contact, event, esp_type)` → returns `(is_mpp_likely: bool, confidence: str)` where confidence is `"high"`, `"medium"`, or `"low"`.

### 2. Predictive Claim — Dropped, replaced with trend language

**Never ship:** "Tells you 30 days before it costs you", "projected_danger_days", hardcoded day-count predictions.

**Ship instead:** Trend language showing rate + direction:
- "Trending toward danger"
- "Declining trajectory"
- "At-risk contacts growing 8%/week"
- "Engagement trajectory: declining"

**Decay Velocity signal copy:** "Rate and direction of list degradation"

**Homepage hero subhead:** "Your email list broadcasts 7 signals about what's happening to your deliverability. InbXr reads all 7 — including two no other platform measures — and tells you what's changing, not just what broke."

**Code contract:** Signal Score result includes `trajectory_direction: "improving" | "stable" | "declining"` and `velocity_rate: float` (weekly change %). **Never includes `projected_days`.**

### 3. Feature Name Collisions — Functional / distinct scheme

| Old name | New name |
|---|---|
| Email Analyzer | **Copy Intelligence** |
| AI Copy Rewriter | **Copy Rewriter** |
| Email Test | **Inboxer Send Test** |
| Inbox Placement | **Inboxer Placement Test** |
| Framework Lab (existing page) | **Framework Lab** (unchanged) |
| AI Framework Rewriter | **Framework Rewriter** |

### 4. Spam Trap Exposure → Dormancy Risk

The formula (dormancy depth calculation) is unchanged. The name is changed to be honest. Real spam traps are Spamhaus/Abusix honeypots — we don't detect those. We detect dormancy, so we call it Dormancy Risk.

All references in UI, docstrings, system prompts, email copy, and database column names use `dormancy_risk` not `spam_trap_exposure`.

### 5. Free Tier Math — Normalized to 100

Free tier sees 5 of 7 signals. Weights are normalized so a free user with a perfect list can reach A grade (not capped at C).

**Free tier normalized weights:**

| Signal | Free weight | (Pro weight for reference) |
|---|---|---|
| 01 Bounce Exposure | 42 | 25 |
| 04 Domain Reputation | 25 | 15 |
| 05 Dormancy Risk | 17 | 10 |
| 06 Authentication Standing | 8 | 5 |
| 07 Decay Velocity | 8 | 5 |
| **Total** | **100** | 60 |

Signals 02 (Engagement Trajectory MPP-adj) and 03 (Acquisition Quality) show as **locked cards with "Unlock with Pro" CTA**. Free users see the name and tooltip but not a score.

**Code contract:** `calculate_signal_score(contact_data, auth_data, tier='pro')` returns either Pro weights or normalized free weights based on tier parameter.

### 6. ESP Scope

**Per-contact sync (4 ESPs — Phase 2 scope):**
- **Mailchimp** — `/lists/{id}/members` + `/reports/{campaign_id}/email-activity`
- **ActiveCampaign** — `/api/3/contacts` + `/api/3/activities`
- **Mailgun** — `/v3/{domain}/events` streaming
- **AWeber** — `/accounts/{id}/lists/{id}/subscribers` (OAuth, slower)

**Aggregate-only with "limited signal coverage" badge:**
- **Instantly** — no per-contact engagement API
- **Smartlead** — no per-contact engagement API
- **GoHighLevel** — limited per-contact engagement

Users on these ESPs see Signals 04 and 06 calculated correctly, other signals marked "Requires per-contact data — upload CSV for full reading."

**Not integrated:** Klaviyo. Not in scope for Phase 1-6. Can be added later if paying ecommerce customers specifically request it.

### 7. Code Patterns (Engineering Rules)

**Database:**
- Raw SQLite via `modules/database.py` helpers: `execute()`, `fetchone()`, `fetchall()`
- Migrations added to `_MIGRATIONS` list at end of `modules/database.py`
- JSON stored as TEXT columns (parse in Python)
- Use `WAL` mode (already enabled)
- **NEVER use SQLAlchemy ORM** — no `Model.query.filter_by()`, no `db.session.add()`, no `models/` imports

**Auth:**
- Session-based auth via `modules/auth.py`: `get_current_user()`, `@login_required`, `@tier_required("pro", "agency", "api")`
- **NEVER use Flask-Login** — no `current_user.id`, no `@login_required` from `flask_login`

**Blueprints:**
- New routes go in `blueprints/signal_routes.py` (Phase 3+)
- Register in `app.py` following existing pattern

**Alerts:**
- **Reuse** existing `alerts` table — add columns via migration:
  - `signal_dimension TEXT` (which of 7 signals)
  - `projected_impact_days INTEGER` (deprecated per decision 2 but keep for future)
  - `recommended_action TEXT`
  - `action_url TEXT`
- **NEVER** create parallel `signal_alerts` table

**Scheduler:**
- **Extend** existing `_scheduled_esp_sync` job in `modules/scheduler.py`
- **NEVER** add parallel `signal_watch` job — same data, same 6-hour interval
- Signal calculation happens after ESP data sync in the same job

**Homepage:**
- **Preserve** the existing free email test cinema animation as secondary acquisition funnel
- Add mechanism section + pain points + comparison cards
- Do NOT replace hero entirely — keep the email test as the primary in-page action

**AI/Groq:**
- Reuse pattern from `modules/ai_rewriter.py`
- Signal Advisor context-aware prompt: inject current Signal Score data before every chat
- Recovery Sequences generator: reuse Groq call pattern

---

## Files to Create (engineering tracker)

| File | Purpose | Phase | Status |
|---|---|---|---|
| `modules/signal_copy.py` | All copy constants (dimension names, grades, actions, tier weights) | 2 | pending |
| `modules/signal_score.py` | 7-signal calculation engine (pure functions) | 3 | pending |
| `modules/esp_contact_sync.py` | Per-contact sync for 4 ESPs with pagination + rate limits | 2 | pending |
| `modules/signal_rules.py` | Rules engine with dry-run default | 4 | pending |
| `modules/early_warning.py` | Alert condition matching | 4 | pending |
| `blueprints/signal_routes.py` | All new routes (/signal-score, /signal-map, /signal-rules, /send-readiness, /recovery-sequences) | 3-4 | pending |
| `templates/signal/dashboard.html` | Signal Score Dashboard | 4 | pending |
| `templates/signal/map.html` | Signal Map segment view | 4 | pending |
| `templates/signal/rules.html` | Signal Rules CRUD + templates | 4 | pending |
| `templates/signal/send_readiness.html` | Pre-campaign gate | 4 | pending |
| `templates/signal/recovery_sequences.html` | Recovery sequence generator | 4 | pending |

## Files to Modify

| File | Change | Phase |
|---|---|---|
| `modules/database.py` | Add migration `021_signal_intelligence_system` | 2 |
| `modules/scheduler.py` | Extend `_scheduled_esp_sync` to call signal engine after sync | 3 |
| `modules/tiers.py` | Add signal feature flags per tier | 4 |
| `modules/alerts.py` | Add signal-specific alert creation helpers | 4 |
| `modules/ai_rewriter.py` | Add Signal Advisor context injection function | 4 |
| `blueprints/auth_routes.py` | Add CSV upload endpoint for free tier signal reading | 3 |
| `templates/auth/deliverability.html` | Evolve into Signal Score Dashboard | 5 |
| `templates/sections/index_hero.html` | Add mechanism framing (preserve email test cinema) | 5 |
| `templates/sections/index_marketing.html` | Replace with 7 signal pills + pain points + comparison | 5 |
| `app.py` | Register `signal_routes` blueprint | 3 |

## Files to NOT Modify

- `modules/blog_ai.py` — keep blog system separate
- `modules/esp_sync.py` — keep aggregate sync as fallback for non-Phase-2 ESPs
- `modules/email_test.py` — current email test tool must keep working unchanged
- Any of the existing 9 testing tools' backend modules

---

## Phase Status

| Phase | Description | Status |
|---|---|---|
| Phase 0 | Mechanism validation (landing + outreach + ads) | **SKIPPED** per user decision |
| Phase 1 | Spec cleanup (decisions locked) | **✅ COMPLETE** |
| Phase 2 | Data foundation (migration + per-contact sync) | in progress |
| Phase 3 | Signal engine + CSV path | pending |
| Phase 4 | Intelligence layer (Advisor, Rules, Recovery, Send Readiness) | pending |
| Phase 5 | Rebrand + polish (homepage, onboarding, nav) | pending |
| Phase 6 | Launch | pending |

---

## Reference: Critical Existing Files

- `modules/database.py` — last migration `020_esp_integrations_and_snapshots`
- `modules/esp_sync.py` — aggregate ESP sync, `_compute_health()` function is the template for signal math
- `modules/dns_monitor.py` + `dns_monitor_snapshots` table — Authentication Standing data source
- `modules/monitoring.py` + `monitor_scans` table — sender blacklist data for Domain Reputation
- `modules/scheduler.py` — `_scheduled_esp_sync` (every 6hr) + `_scheduled_weekly_digest`
- `modules/ai_rewriter.py` — Groq integration pattern
- `modules/tiers.py` — feature flag + limit pattern
- `modules/auth.py` — `get_current_user()`, `@login_required`, `@tier_required`
- `modules/alerts.py` + `alerts` table — existing alert system to extend
- `blueprints/integration_routes.py` — `ESP_PROVIDERS` dict (7 providers, no Klaviyo)
- `blueprints/billing_routes.py` — HMAC signature verification pattern (reuse for Mailchimp webhook)
- `templates/auth/deliverability.html` — existing dashboard to evolve

## Reference: Current Tier Configuration

| Tier | Name | Price | ESP integrations |
|---|---|---|---|
| free | Free | $0 | 0 (will change to CSV upload path) |
| pro | Pro | $29 | 1 |
| agency | Agency | $79 | 10 |
| api | API | usage-based | 10 |

**Note:** Pricing changes are explicitly out of scope per user decision. Current Stripe price IDs stay active.

---

## Glossary (used in code and UI)

- **Signal Score:** 0-100 composite of the 7 signals, rounded to integer
- **Signal Grade:** A/B/C/D/F letter grade mapped from Signal Score
- **Signal Watch:** The 6-hour background recalculation job
- **Early Warning:** Alerts triggered when a signal crosses a threshold
- **Signal Rules:** User-defined automation rules with dry-run default
- **Recovery Sequences:** Groq-generated multi-email re-engagement flow
- **Send Readiness:** Composite green/amber/red pre-campaign gate
- **Signal Map:** Contact segmentation view (Active/Warm/At-Risk/Dormant)
- **Dormancy Risk:** Signal 05 (renamed from Spam Trap Exposure)
- **Active contact:** Engaged in last ≤30 days
- **Warm contact:** Engaged 31-90 days ago
- **At-Risk contact:** Engaged 91-180 days ago
- **Dormant contact:** No engagement 180+ days OR never engaged
