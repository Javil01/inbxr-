"""
INBXR — Stripe Billing Routes
Checkout sessions, customer portal, and webhook handling.
"""

import os
import logging
import stripe
from flask import Blueprint, request, jsonify, redirect, url_for, render_template

from modules.auth import login_required, get_current_user, get_user_by_id, update_user_tier
from modules.database import fetchone, execute

logger = logging.getLogger('inbxr.billing')

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

# ── Graceful degradation when Stripe is not configured ──
_STRIPE_CONFIGURED = bool(stripe.api_key)

if not _STRIPE_CONFIGURED:
    logger.warning("STRIPE_SECRET_KEY not set — billing routes will return 503")


def _billing_not_configured():
    """Return a friendly error when Stripe keys are missing."""
    return jsonify({
        "error": "Billing is not configured. Please contact the administrator."
    }), 503

# ── Map Stripe price IDs → tier names ──────────────────
PRICE_TO_TIER = {}

def _ensure_price_map():
    if PRICE_TO_TIER:
        return
    pro = os.environ.get("STRIPE_PRICE_PRO")
    agency = os.environ.get("STRIPE_PRICE_AGENCY")
    if pro:
        PRICE_TO_TIER[pro] = "pro"
    if agency:
        PRICE_TO_TIER[agency] = "agency"

TIER_TO_PRICE_ENV = {
    "pro": "STRIPE_PRICE_PRO",
    "agency": "STRIPE_PRICE_AGENCY",
}


@billing_bp.route("/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    """Create a Stripe Checkout session for upgrading."""
    if not _STRIPE_CONFIGURED:
        return _billing_not_configured()
    _ensure_price_map()
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json(silent=True) or {}
    tier = data.get("tier")
    if tier not in ("pro", "agency"):
        return jsonify({"error": "Invalid tier"}), 400

    # If already subscribed, send to Customer Portal for plan changes
    if user.get("stripe_subscription_id"):
        try:
            portal = stripe.billing_portal.Session.create(
                customer=user["stripe_customer_id"],
                return_url=url_for("auth.account", _external=True),
            )
            return jsonify({"url": portal.url})
        except stripe.error.StripeError as e:
            return jsonify({"error": str(e)}), 400

    price_id = os.environ.get(TIER_TO_PRICE_ENV.get(tier, ""))
    if not price_id:
        return jsonify({"error": "Pricing not configured"}), 500

    try:
        checkout_params = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": url_for("billing.success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": url_for("auth.pricing", _external=True),
            "client_reference_id": str(user["id"]),
        }
        # Reuse existing Stripe customer if we have one
        if user.get("stripe_customer_id"):
            checkout_params["customer"] = user["stripe_customer_id"]
        else:
            checkout_params["customer_email"] = user["email"]

        session_obj = stripe.checkout.Session.create(**checkout_params)
        return jsonify({"url": session_obj.url})
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e)}), 400


@billing_bp.route("/customer-portal", methods=["POST"])
@login_required
def customer_portal():
    """Open Stripe Customer Portal for managing subscription."""
    if not _STRIPE_CONFIGURED:
        return _billing_not_configured()
    user = get_current_user()
    if not user or not user.get("stripe_customer_id"):
        return jsonify({"error": "No active subscription found"}), 400

    try:
        portal = stripe.billing_portal.Session.create(
            customer=user["stripe_customer_id"],
            return_url=url_for("auth.account", _external=True),
        )
        return jsonify({"url": portal.url})
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e)}), 400


@billing_bp.route("/webhook", methods=["POST"])
def webhook():
    """Handle Stripe webhook events."""
    if not _STRIPE_CONFIGURED:
        return _billing_not_configured()
    _ensure_price_map()
    payload = request.data
    sig = request.headers.get("Stripe-Signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        return jsonify({"error": "Webhook not configured"}), 500

    try:
        event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"]
    data_obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data_obj)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(data_obj)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data_obj)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(data_obj)

    return jsonify({"status": "ok"}), 200


@billing_bp.route("/success")
@login_required
def success():
    """Post-checkout success page."""
    return render_template("auth/billing_success.html", active_page="account")


# ── Webhook Handlers ──────────────────────────────────────

def _handle_checkout_completed(session_obj):
    """New subscription created via Checkout."""
    user_id = session_obj.get("client_reference_id")
    customer_id = session_obj.get("customer")
    subscription_id = session_obj.get("subscription")

    if not user_id or not subscription_id:
        return

    # Fetch subscription to determine tier from price
    sub = stripe.Subscription.retrieve(subscription_id)
    price_id = sub["items"]["data"][0]["price"]["id"]
    tier = PRICE_TO_TIER.get(price_id, "pro")

    update_user_tier(
        int(user_id), tier,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
    )


def _handle_subscription_updated(subscription):
    """Subscription changed (upgrade, downgrade, or renewal)."""
    customer_id = subscription.get("customer")
    status = subscription.get("status")

    user = fetchone("SELECT id FROM users WHERE stripe_customer_id = ?", (customer_id,))
    if not user:
        return

    if status == "active":
        price_id = subscription["items"]["data"][0]["price"]["id"]
        tier = PRICE_TO_TIER.get(price_id, "pro")
        update_user_tier(
            user["id"], tier,
            stripe_subscription_id=subscription["id"],
        )
    elif status in ("canceled", "unpaid"):
        update_user_tier(user["id"], "free", stripe_subscription_id=None)


def _handle_subscription_deleted(subscription):
    """Subscription cancelled — downgrade to free."""
    customer_id = subscription.get("customer")
    user = fetchone("SELECT id FROM users WHERE stripe_customer_id = ?", (customer_id,))
    if not user:
        return
    update_user_tier(user["id"], "free", stripe_subscription_id=None)


def _handle_payment_failed(invoice):
    """Payment failed on renewal — notify user."""
    customer_id = invoice.get("customer")
    user = fetchone("SELECT id, email FROM users WHERE stripe_customer_id = ?", (customer_id,))
    if not user:
        return
    # Create an in-app alert
    try:
        from modules.alerts import create_alert
        create_alert(
            user["id"],
            "payment_failed",
            "Payment Failed",
            "Your subscription payment failed. Please update your payment method to avoid losing access.",
            severity="critical",
        )
    except Exception:
        logger.exception("Failed to create payment_failed alert for user %s", user["id"])
