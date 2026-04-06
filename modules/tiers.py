"""
InbXr Tier Configuration
Defines Free / Pro / Agency / API tier limits and features.
"""

TIERS = {
    "free": {
        "name": "Free",
        "price_monthly": 0,
        "stripe_price_id": None,
        "limits": {
            "checks_per_hour": 10,
            "checks_per_day": 50,
            "email_verifications_per_day": 25,
            "blocklist_domains": 2,
            "warmup_campaigns": 1,
            "subject_tests_per_day": 10,
            "placement_tests_per_day": 3,
            "esp_integrations": 0,
        },
        "features": {
            "cloud_history": False,
            "pdf_reports": False,
            "bulk_verify": False,
            "scheduled_monitoring": False,
            "email_alerts": False,
            "api_access": False,
            "teams": False,
            "webhooks": False,
            "email_assistant": False,
            "ai_rewrite": False,
            "ai_support_chat": True,
            "priority_support": False,
            "framework_builder": False,
            "esp_integrations": False,
            # Signal Intelligence (Phase 4)
            "signal_score": True,             # Free gets 5 of 7 (normalized to 100)
            "signal_csv_upload": True,        # Free can upload CSV for signal reading
            "signal_watch": False,            # No background monitoring
            "early_warning": False,           # No alerts from signal rules
            "signal_rules": False,            # No automation rules
            "signal_advisor": False,          # AI advisor is Pro+
            "recovery_sequences": False,      # Groq-generated sequences are Pro+
            "send_readiness": False,          # Pre-campaign gate is Pro+
            "engagement_trajectory_signal": False,  # Market-first locked for free
            "acquisition_quality_signal": False,    # Market-first locked for free
        },
    },
    "pro": {
        "name": "Pro",
        "price_monthly": 29,
        "stripe_price_id": None,  # Set via env: STRIPE_PRO_PRICE_ID
        "limits": {
            "checks_per_hour": 50,
            "checks_per_day": 500,
            "email_verifications_per_day": 500,
            "blocklist_domains": 10,
            "warmup_campaigns": 5,
            "subject_tests_per_day": 50,
            "placement_tests_per_day": 20,
            "assistant_chats_per_month": 10,
            "esp_integrations": 1,
            "signal_rules_max": 10,
            "signal_advisor_chats_per_month": 20,
        },
        "features": {
            "cloud_history": True,
            "pdf_reports": True,
            "bulk_verify": True,
            "scheduled_monitoring": True,
            "email_alerts": True,
            "api_access": False,
            "teams": False,
            "email_assistant": True,
            "ai_rewrite": True,
            "ai_support_chat": True,
            "webhooks": False,
            "priority_support": True,
            "framework_builder": True,
            "esp_integrations": True,
            # Signal Intelligence (Phase 4)
            "signal_score": True,             # Full 7 signals
            "signal_csv_upload": True,
            "signal_watch": True,             # Background monitoring every 6hr
            "early_warning": True,            # Early Warning alerts
            "signal_rules": True,             # Up to 10 active rules
            "signal_advisor": True,           # Context-aware AI advisor
            "recovery_sequences": True,       # Groq-generated re-engagement
            "send_readiness": True,           # Pre-campaign gate
            "engagement_trajectory_signal": True,
            "acquisition_quality_signal": True,
        },
    },
    "agency": {
        "name": "Agency",
        "price_monthly": 79,
        "stripe_price_id": None,  # Set via env: STRIPE_AGENCY_PRICE_ID
        "limits": {
            "checks_per_hour": 200,
            "checks_per_day": 2000,
            "email_verifications_per_day": 5000,
            "blocklist_domains": 50,
            "warmup_campaigns": 25,
            "subject_tests_per_day": 200,
            "placement_tests_per_day": 100,
            "esp_integrations": 10,
            "signal_rules_max": 999,
            "signal_advisor_chats_per_month": 999999,
        },
        "features": {
            "cloud_history": True,
            "pdf_reports": True,
            "bulk_verify": True,
            "scheduled_monitoring": True,
            "email_alerts": True,
            "api_access": True,
            "teams": True,
            "email_assistant": True,
            "ai_rewrite": True,
            "ai_support_chat": True,
            "webhooks": True,
            "priority_support": True,
            "framework_builder": True,
            "esp_integrations": True,
            # Signal Intelligence (Phase 4) — all unlocked
            "signal_score": True,
            "signal_csv_upload": True,
            "signal_watch": True,
            "early_warning": True,
            "signal_rules": True,
            "signal_advisor": True,
            "recovery_sequences": True,
            "send_readiness": True,
            "engagement_trajectory_signal": True,
            "acquisition_quality_signal": True,
            # Agency gets unlimited signal rules (enforced in UI)
            "signal_rules_unlimited": True,
        },
    },
    "api": {
        "name": "API",
        "price_monthly": 0,  # Usage-based
        "stripe_price_id": None,
        "limits": {
            "checks_per_hour": 500,
            "checks_per_day": 10000,
            "email_verifications_per_day": 50000,
            "blocklist_domains": 100,
            "warmup_campaigns": 0,
            "subject_tests_per_day": 1000,
            "placement_tests_per_day": 500,
            "esp_integrations": 10,
            "signal_rules_max": 999,
            "signal_advisor_chats_per_month": 999999,
        },
        "features": {
            "cloud_history": True,
            "pdf_reports": True,
            "bulk_verify": True,
            "scheduled_monitoring": True,
            "email_alerts": True,
            "api_access": True,
            "teams": False,
            "email_assistant": True,
            "ai_rewrite": True,
            "ai_support_chat": True,
            "webhooks": True,
            "priority_support": True,
            "framework_builder": True,
            "esp_integrations": True,
            # Signal Intelligence (Phase 4) — full API access
            "signal_score": True,
            "signal_csv_upload": True,
            "signal_watch": True,
            "early_warning": True,
            "signal_rules": True,
            "signal_advisor": True,
            "recovery_sequences": True,
            "send_readiness": True,
            "engagement_trajectory_signal": True,
            "acquisition_quality_signal": True,
            "signal_rules_unlimited": True,
        },
        "api_pricing": {
            "domain_check": 0.02,
            "email_verify": 0.005,
            "blocklist_scan": 0.01,
            "copy_analysis": 0.03,
            "placement_test": 0.10,
        },
    },
}


def get_tier(tier_name):
    """Get tier config by name. Returns free tier if not found."""
    return TIERS.get(tier_name, TIERS["free"])


def get_tier_limit(tier_name, limit_key):
    """Get a specific limit for a tier."""
    tier = get_tier(tier_name)
    return tier["limits"].get(limit_key, 0)


def has_feature(tier_name, feature_key):
    """Check if a tier has a specific feature."""
    tier = get_tier(tier_name)
    return tier["features"].get(feature_key, False)


def get_all_tiers():
    """Return all tiers for pricing page display."""
    return {k: v for k, v in TIERS.items() if k != "api"}


def get_api_tier():
    """Return API tier config."""
    return TIERS["api"]
