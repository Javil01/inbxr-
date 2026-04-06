# INBXR Signal Intelligence — Build Status

**Last updated:** 2026-04-06 (overnight autonomous session)
**Reference:** `SIGNAL_SPEC.md` for locked decisions and conventions.

---

## TL;DR

Overnight session completed Phase 1 decisions + most of Phases 2, 3, and 4. The Signal Intelligence system now has a working engine, persistence, rule evaluation, early warning alerts, tier gating, scheduler wiring, Flask routes, and all dashboard templates.

**Nothing has been pushed to production.** All work is local on `master` branch with uncommitted changes. Everything is validated against a copy of the production SQLite DB and imports/renders cleanly in a Flask test harness.

**What needs your decisions in the morning:** ESP API credential testing, git commit message review, and the "ready to deploy?" go/no-go call.

---

## What Shipped (ready to review)

### Phase 1 — Spec Cleanup ✅
- **`SIGNAL_SPEC.md`** — canonical reference doc at project root
- All locked decisions documented (MPP hybrid detection, trend language, name collisions resolved, Dormancy Risk rename, free tier normalization, 4-ESP per-contact scope, code pattern rules)

### Phase 2 — Data Foundation ✅ (mostly)
- **Migration `021_signal_intelligence_system`** — 6 new tables:
  - `signal_scores` — current reading per user/integration (19 columns for all 7 signals + MPP + trajectory + segments + JSON metadata)
  - `signal_score_history` — time-series snapshots with event annotations for chart timeline
  - `signal_rules` — automation rules with `action_dry_run` default ON
  - `signal_rule_log` — rule execution history with `was_dry_run` flag
  - `contact_segments` — per-contact engagement + verification + suppression tracking with unique constraint on (user_id, esp_integration_id, email)
  - `isp_compliance_requirements` — seeded with 12 rows of Gmail/Yahoo 2024 + Microsoft 2025 DMARC/SPF/DKIM/List-Unsubscribe mandates
- **Migration `022_alerts_signal_columns`** — extends existing `alerts` table with:
  - `signal_dimension`, `recommended_action`, `action_url`, `severity`, `is_dismissed`
  - Plus indexes on signal_dimension and is_dismissed
  - Reuses existing alerts infrastructure (not a parallel signal_alerts table) per SPEC decision
- **`modules/signal_copy.py`** — all copy constants:
  - PRO_SIGNAL_WEIGHTS (sums to 100)
  - FREE_SIGNAL_WEIGHTS (5 signals normalized to 100)
  - SIGNAL_DIMENSION_COPY for all 7 signals with market-first labels
  - SIGNAL_GRADE_COPY for A-F grades with cta text
  - ACTION_RECOMMENDATIONS per-signal
  - MPP_ACCURACY_LABELS + ESP_MPP_ACCURACY (Mailgun=high, Mailchimp/AC/AWeber=medium, Instantly/Smartlead/GHL=none)
  - SEGMENT_LABELS for Active/Warm/At-Risk/Dormant
  - PRE_BUILT_RULE_TEMPLATES (10 templates, all defaulting to dry-run)
  - CSV column flexible parsing helpers
- **`modules/esp_contact_sync.py`** — per-contact ESP sync:
  - Mailchimp: **fully implemented** (`sync_mailchimp_contacts` + `sync_mailchimp_campaign_activity`) with pagination, rate limits, incremental cursor via since_last_changed
  - ActiveCampaign, Mailgun, AWeber: **stubs** that return `not_implemented=True`. Phase 2b work.
  - Instantly, Smartlead, GoHighLevel: return `not_supported=True` (APIs don't expose per-contact engagement)
  - `_upsert_contacts_batch` with NULL-safe esp_integration_id handling
  - `get_contacts_for_signal_score()` reads from contact_segments table for engine consumption

### Phase 3 — Signal Engine + CSV ✅
- **`modules/signal_score.py`** — full 7-signal calculation engine:
  - `calculate_signal_score()` master function with tier parameter
  - Per-signal calculators: bounce_exposure, engagement_trajectory (MPP-aware), acquisition_quality (cohort analysis), domain_reputation, dormancy_risk (renamed from spam_trap_exposure), authentication_standing, decay_velocity
  - Trend language only — no predictive day counts
  - Hybrid MPP detection (`detect_mpp_open()`) with per-ESP accuracy
  - Free tier normalization (`_compose_free_tier_score`) — 5 signals scale to 100
  - `save_signal_score()` persistence with upsert + history append
  - `get_latest_signal_score()` / `get_signal_history()` readers
  - `parse_csv_contacts()` flexible CSV parser
  - `calculate_signal_score_from_csv()` — CSV upload entry point
- **Unit-tested against real-ish data**:
  - Healthy Pro list → 81/B
  - Bad list → 8/F
  - Free tier healthy list → 100/A (normalization verified)
  - CSV upload → 67/C with 5 contacts
  - Grade thresholds correct for all buckets
  - Persistence roundtrips correctly

### Phase 4 — Intelligence Layer ✅
- **`modules/signal_rules.py`** — rule evaluation engine:
  - `preview_signal_rule()` dry-run returning affected_count + sample_emails
  - `execute_signal_rules()` live execution (only for rules with action_dry_run=0)
  - 4 local actions: notify, tag, move_segment, suppress (ESP writeback deferred)
  - `_find_contact_row()` helper with proper NULL esp_integration_id handling
  - Rule CRUD: `create_rule_from_template`, `create_custom_rule`, `toggle_rule`, `flip_dry_run`, `delete_rule`, `get_user_rules`, `get_rule_log`
  - All new rules default to dry-run per SPEC safety rule
- **`modules/signal_alerts.py`** — Early Warning engine:
  - 8 built-in Early Warning rules covering all 7 signals
  - Uses trend language (no day predictions)
  - Title-based dedup with 7-day window
  - `check_early_warning_conditions()` evaluation entry point
  - Reuses existing `alerts` table via new columns (NOT parallel table)
  - `get_signal_alerts()`, `dismiss_alert()`, `get_unread_signal_alert_count()`
  - **Tested end-to-end**: 8 alerts fire on bad data, 0 on healthy, dedup works on repeat
- **`modules/signal_advisor.py`** — context-aware AI prompt builder:
  - `build_signal_advisor_prompt(user_id)` returns (system_prompt, has_data)
  - Injects full 7-signal data into Groq system prompt when data exists
  - Weakest-signal detection + recommended action
  - Free tier lock markers for locked signals (02, 03)
  - `get_signal_aware_subject_tips()` for Subject Intelligence injection
  - `get_signal_context_for_copy()` for Copy Intelligence injection
  - No data fallback mode (encourages user to connect ESP or upload CSV)

### Phase 4 — Tier Gating ✅
- **`modules/tiers.py`** updated with signal feature flags per tier:
  - Free: signal_score + csv upload only (signals 02, 03 locked)
  - Pro: all 7 signals + signal_watch + early_warning + signal_rules (max 10) + signal_advisor (20/mo) + recovery_sequences + send_readiness
  - Agency: same as Pro + signal_rules_unlimited
  - API: same as Agency
- Validated with `has_feature()` tests

### Phase 3 — Scheduler Integration ✅
- **`modules/scheduler.py`** extended:
  - `_scheduled_esp_sync` now also runs Signal Watch (does NOT add parallel job per SPEC rule)
  - `_signal_watch_for_all_users()` iterates Pro+ users with active integrations
  - `_signal_watch_for_user()` pulls per-contact data (for supported ESPs) → calculates signal → fires Early Warning → executes live Signal Rules
  - `_get_auth_data_for_user()` reads from existing `dns_monitor_snapshots` + `monitor_scans` tables for Authentication Standing + Domain Reputation blacklist input
  - Verified scheduler starts with 9 jobs (not 10 — no duplicate)

### Phase 3 — Flask Routes ✅
- **`blueprints/signal_routes.py`** — 17 routes:
  - `GET /signal-score` — Dashboard
  - `POST /signal-score/calculate` — Manual recalc (Pro+)
  - `POST /signal-score/from-csv` — CSV upload (all tiers)
  - `GET /signal-score/history` — JSON for chart
  - `GET /signal-map` — Segment view
  - `GET /signal-alerts` + `POST /signal-alerts/<id>/dismiss`
  - `GET /signal-rules` + create/preview/toggle/flip-dry-run/delete
  - `GET /send-readiness` + `POST /send-readiness/check`
  - `GET /recovery-sequences` + `POST /recovery-sequences/generate` (Groq-powered)
- Registered in `app.py` after `integration_bp`
- All routes use `@login_required` / `@tier_required` from `modules/auth.py` (NOT Flask-Login)
- All database access via raw SQLite helpers (NOT SQLAlchemy)

### Phase 4 — Templates ✅ (all 6 pages)
- `templates/signal/dashboard.html` — full Signal Score Dashboard with:
  - Animated SVG score ring with dynamic stroke color
  - 7 signal cards with score bars, tooltips, market-first badges, locked-state for free tier
  - Weakest-signal recommended action card
  - Contact segment composition bars
  - Recent alerts preview
  - Empty state with Connect-ESP + Upload-CSV flows
  - Recalculate button
- `templates/signal/map.html` — segment visualization
- `templates/signal/alerts.html` — alert list with severity colors + dismiss
- `templates/signal/rules.html` — rule list + templates grid + dry-run warning + flip-to-live confirmation dialog
- `templates/signal/send_readiness.html` — green/amber/red gate card + issues list + actions list
- `templates/signal/recovery_sequences.html` — form + Groq generation + result rendering

---

## What DIDN'T Ship Tonight (and why)

1. **ActiveCampaign, Mailgun, AWeber per-contact sync** — stubs only. Mailchimp was the priority for Phase 2a. Other ESPs are Phase 2b work — each is 1-3 days of focused effort and benefits from real API testing.

2. **Homepage rewrite (Phase 5)** — not started. Depends on signal engine shipping first per SPEC rule "do not rebrand until the engine works." Morning task: decide whether to start Phase 5 or focus on Phase 2b ESP sync.

3. **Onboarding 4-step flow (Phase 5)** — not started. Same reason.

4. **Email templates for Weekly Signal Report (Phase 4)** — scheduler job to extend `_scheduled_weekly_digest` not yet wired. Easy addition (1-2 hours) but deferred because it depends on real signal data accumulating over time.

5. **Admin signal analytics (Phase 7)** — not started. Low priority until real data exists.

6. **Recovery Sequences real Groq call** — blueprint stub calls Groq API but needs `GROQ_API_KEY` set to test. The structure is there; a morning test with credentials will validate.

7. **Testing against real ESP API credentials** — all modules validated against a prod DB copy, but the Mailchimp sync has never actually pulled real data from a real Mailchimp account. First run tomorrow should be against a test list with known contacts to verify the pagination and field mapping.

---

## What Needs Your Decisions in the Morning

### Decision 1: Deploy or hold?
All code is local. Nothing is committed. Nothing pushed. You have two options:

- **(A) Commit + push now** — Railway auto-deploys on push. New routes will be live at inbxr.us/signal-score. **Risk:** Any runtime error in Signal Watch job will show up in production logs. Users won't see anything unless they navigate to `/signal-score` directly (no nav links added yet).
- **(B) Hold until you manually test with a real Mailchimp account** — safer. Review the BUILD_STATUS.md, open `/signal-score` locally with Flask dev server, connect a test Mailchimp integration, trigger sync, verify data flows correctly before committing.

**Recommendation: (B)**. Phase 2b ESP work is a good morning session before committing.

### Decision 2: ESP API testing
To test Mailchimp per-contact sync, you'll need:
- A Mailchimp test list with at least 50-100 contacts (ideally with mixed engagement states)
- The Mailchimp API key already configured in your `esp_integrations` table OR a fresh test integration
- Run locally: `python -c "from modules.esp_contact_sync import sync_mailchimp_contacts; ..."` with the real API key

The sync function will pull contacts into `contact_segments` table. Then `calculate_signal_score` against those rows will give you the first real Signal Score reading.

### Decision 3: Nav integration (Phase 5 prep)
Once you're confident the engine works, you'll want to add `/signal-score` to the main navigation. Currently:
- Route exists and template renders
- No sidebar link, no nav bar entry
- Users who know the URL can access it
- Recommended: add to dashboard sidebar under new "Signal Intelligence" section (Pro+ only)

### Decision 4: Existing `/deliverability` page
The existing deliverability dashboard at `/deliverability` still works unchanged. The SPEC says Phase 5 evolves `/deliverability` into the Signal Score Dashboard. Right now there are TWO pages:
- `/deliverability` — old cross-platform ESP health (still works)
- `/signal-score` — new 7-signal dashboard (empty state unless signals calculated)

Decision: leave both side-by-side during Phase 2b ESP work, merge in Phase 5.

---

## Morning Test Plan

If you want to verify the system works end-to-end before deciding to deploy:

1. **Run the app locally:**
   ```
   cd C:/Users/josea/email-copy-tool
   python app.py
   ```
   Should start on port 5000 (or whatever Flask default is).

2. **Open `/signal-score` in browser:** You should see the empty state with "Connect an ESP" and "Upload CSV" buttons.

3. **Test CSV upload:** Use any small CSV with columns `email,last_open,last_click,date_added`. Upload via the button. Should render a Signal Score.

4. **Test Signal Rules:** Navigate to `/signal-rules`. Click "Add Rule (dry run)" on a template. Click Preview — should show affected count + sample emails from your uploaded CSV data.

5. **Test Early Warning:** After CSV upload with bad data (lots of dormants, no last_open, etc.), check `/signal-alerts`. Should show multiple warnings.

6. **Test Mailchimp sync (if you have a test account):**
   ```python
   from modules.esp_contact_sync import sync_mailchimp_contacts
   result = sync_mailchimp_contacts(integration_id=<your_id>, api_key='your-xxxx-us21')
   print(result)
   ```

7. **Verify existing tools still work:** Click through `/sender`, `/analyzer`, `/placement`, `/deliverability`, `/dashboard`. Nothing should have regressed.

---

## Files Changed Tonight

**New files:**
- `SIGNAL_SPEC.md`
- `BUILD_STATUS.md` (this file)
- `modules/signal_copy.py`
- `modules/signal_score.py`
- `modules/signal_rules.py`
- `modules/signal_alerts.py`
- `modules/signal_advisor.py`
- `modules/esp_contact_sync.py`
- `blueprints/signal_routes.py`
- `templates/signal/dashboard.html`
- `templates/signal/map.html`
- `templates/signal/alerts.html`
- `templates/signal/rules.html`
- `templates/signal/send_readiness.html`
- `templates/signal/recovery_sequences.html`

**Modified files:**
- `modules/database.py` — added `_add_alerts_signal_columns` + migrations 021, 022
- `modules/scheduler.py` — extended `_scheduled_esp_sync` with Signal Watch logic
- `modules/tiers.py` — added signal feature flags + rule limits per tier
- `app.py` — registered `signal_bp` blueprint

**NOT modified (preserved for backward compat):**
- All 9 existing testing tools
- `modules/esp_sync.py` — aggregate sync still runs
- `templates/auth/deliverability.html` — existing dashboard still works
- Any existing routes, blueprints, or auth/tier logic

---

## Known Issues / Deferred Items

1. **`datetime.utcnow()` deprecation warnings** — Python 3.12+ warns on these. The code still works but should migrate to `datetime.now(timezone.utc)` in a future polish pass. Not urgent.

2. **MPP detection on aggregate data is approximate** — the hybrid detection needs per-open User-Agent/IP data. The current Mailchimp sync doesn't pull that (campaign activity feed is a separate expensive call). `_map_mailchimp_contact()` uses `last_changed` as a proxy for `last_open_date`. **This is a known inaccuracy** that will be fixed in Phase 2b when we wire `sync_mailchimp_campaign_activity`.

3. **Signal Rules ESP writeback is STUBBED** — `action_esp_sync=1` rules still execute locally but log `esp_sync_status='skipped'`. Real ESP writeback (calling Mailchimp unsubscribe API, etc.) is deferred to Phase 6+ per the SPEC safety rule.

4. **Weekly Signal Report email not wired** — the `_scheduled_weekly_digest` job in `modules/scheduler.py` does not yet send signal reports. Easy Phase 4 fix tomorrow.

5. **Contact verification flags** — `is_catch_all`, `is_disposable` are not populated by the Mailchimp sync. They default to False. Future polish: integrate with existing `modules/email_verifier.py` on a sampling basis.

6. **No Signal Advisor route** — `modules/signal_advisor.py` exists and works, but there's no Flask route to expose it yet. It needs to be wired into the existing Email Expert Assistant chat flow (wherever that lives). Morning task.

7. **No navigation links** — `/signal-score` and friends are accessible by URL only. No sidebar entries, no nav bar entries. Phase 5 polish.

---

## Morning Startup Checklist

When you wake up:

1. [ ] Read this document
2. [ ] Read `SIGNAL_SPEC.md` to refresh on locked decisions
3. [ ] Run `git status` to see all uncommitted changes
4. [ ] Run the app locally and visit `/signal-score`
5. [ ] Test CSV upload with any CSV
6. [ ] Decide: commit + deploy, or hold for Phase 2b ESP testing first?
7. [ ] If testing Mailchimp sync: prepare a test list with ~50-100 contacts
8. [ ] If deploying: review commit message I suggest below

## Suggested Commit Message

```
Add Signal Intelligence system — Phase 1 through 4

Phase 1: Locked decisions in SIGNAL_SPEC.md (MPP hybrid detection,
trend language only, Dormancy Risk rename, free tier normalization,
4-ESP per-contact scope, name collisions resolved).

Phase 2: Migration 021 + 022 creating signal_scores,
signal_score_history, signal_rules, signal_rule_log, contact_segments,
isp_compliance_requirements tables + ALTER on alerts. Mailchimp
per-contact sync implemented; ActiveCampaign/Mailgun/AWeber stubbed.
signal_copy.py constants with all Phase 1 locked copy.

Phase 3: signal_score.py engine with 7 pure calculation functions,
hybrid MPP detection, free tier normalization, persistence, CSV upload.
Extended _scheduled_esp_sync to run Signal Watch (not parallel job).
New blueprint signal_routes.py with 17 routes registered in app.py.

Phase 4: signal_rules.py with dry-run default + 10 pre-built templates.
signal_alerts.py with 8 Early Warning rules, title-based dedup. Reuses
existing alerts table (not parallel signal_alerts). signal_advisor.py
builds context-aware Groq system prompts with full 7-signal injection.
Tier gating in tiers.py (Free: 5 of 7 normalized, Pro+: all 7 + automation).

Templates: 6 new pages under templates/signal/ — dashboard, map,
alerts, rules, send_readiness, recovery_sequences. All preserve
existing UI patterns and extend auth/base_auth.html.

No changes to existing 9 testing tools, ESP integrations, or the
existing /deliverability dashboard. All code uses raw SQLite via
modules/database.py and session auth via modules/auth.py per SPEC rules.

Validated end-to-end against prod DB copy: all 17 routes register,
all 6 templates compile, all 6 modules import, tier gating correct,
engine produces correct scores for healthy/bad/free-tier test data,
dedup works on Early Warning repeat runs.

Ref: SIGNAL_SPEC.md + BUILD_STATUS.md
```
