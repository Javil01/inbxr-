"""
INBXR Tier Configuration
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
            "priority_support": False,
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
        },
        "features": {
            "cloud_history": True,
            "pdf_reports": True,
            "bulk_verify": True,
            "scheduled_monitoring": True,
            "email_alerts": True,
            "api_access": False,
            "teams": False,
            "webhooks": False,
            "priority_support": True,
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
        },
        "features": {
            "cloud_history": True,
            "pdf_reports": True,
            "bulk_verify": True,
            "scheduled_monitoring": True,
            "email_alerts": True,
            "api_access": True,
            "teams": True,
            "webhooks": True,
            "priority_support": True,
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
        },
        "features": {
            "cloud_history": True,
            "pdf_reports": True,
            "bulk_verify": True,
            "scheduled_monitoring": True,
            "email_alerts": True,
            "api_access": True,
            "teams": False,
            "webhooks": True,
            "priority_support": True,
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
