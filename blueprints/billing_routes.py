"""
InbXr — Stripe Billing Routes
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
def create_checkout_session():
    """Create a Stripe Checkout session. Works for both logged-in and anonymous users."""
    if not _STRIPE_CONFIGURED:
        return _billing_not_configured()
    _ensure_price_map()

    from flask import session as flask_session

    user = get_current_user()  # may be None for anonymous visitors

    data = request.get_json(silent=True) or {}
    tier = data.get("tier")
    return_url = data.get("return_url", "")
    if tier not in ("pro", "agency"):
        return jsonify({"error": "Invalid tier"}), 400

    # Validate return_url (prevent open redirect)
    if not return_url or not return_url.startswith("/") or return_url.startswith("//"):
        return_url = "/dashboard"

    # If logged-in user already subscribed, send to Customer Portal
    if user and user.get("stripe_subscription_id"):
        try:
            portal = stripe.billing_portal.Session.create(
                customer=user["stripe_customer_id"],
                return_url=request.host_url.rstrip("/") + return_url,
            )
            return jsonify({"url": portal.url})
        except stripe.error.StripeError as e:
            return jsonify({"error": str(e)}), 400

    price_id = os.environ.get(TIER_TO_PRICE_ENV.get(tier, ""))
    if not price_id:
        return jsonify({"error": "Pricing not configured"}), 500

    # Store return URL in session for post-checkout redirect
    flask_session["billing_return_url"] = return_url

    try:
        checkout_params = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": url_for("billing.success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": request.host_url.rstrip("/") + return_url,
        }

        if user:
            # Logged-in user
            checkout_params["client_reference_id"] = str(user["id"])
            if user.get("stripe_customer_id"):
                checkout_params["customer"] = user["stripe_customer_id"]
            else:
                checkout_params["customer_email"] = user["email"]
        else:
            # Anonymous visitor — Stripe will collect their email
            checkout_params["client_reference_id"] = "new"

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

    event_id = event.get("id")
    event_type = event["type"]
    data_obj = event["data"]["object"]

    # Idempotency guard: Stripe retries on network blips. We MUST NOT process
    # the same event twice (would double-grant tiers, etc.). Reserve the event
    # id in stripe_webhook_events; if already present, ack and skip.
    if event_id:
        from modules.database import execute, fetchone
        try:
            existing = fetchone(
                "SELECT 1 FROM stripe_webhook_events WHERE event_id = ?",
                (event_id,),
            )
            if existing:
                logger.info("Stripe webhook %s (%s) already processed; skipping", event_id, event_type)
                return jsonify({"status": "ok", "duplicate": True}), 200
            execute(
                "INSERT OR IGNORE INTO stripe_webhook_events (event_id, event_type) VALUES (?, ?)",
                (event_id, event_type),
            )
        except Exception:
            # Don't fail the webhook over a logging table issue. Stripe will
            # retry if we 500, which is worse than a possible double-process.
            logger.exception("stripe_webhook_events table failure (non-fatal)")

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
def success():
    """Post-checkout success page. Works for both logged-in and new users."""
    from flask import session as flask_session

    # Try to auto-login new user from Stripe session
    session_id = request.args.get("session_id")
    if session_id and not flask_session.get("user_id") and _STRIPE_CONFIGURED:
        try:
            checkout = stripe.checkout.Session.retrieve(session_id)
            email = checkout.get("customer_details", {}).get("email", "")
            if email:
                from modules.auth import get_user_by_email, login_user
                user = get_user_by_email(email)
                if user:
                    login_user(user)
        except Exception:
            logger.exception("Failed to auto-login after checkout")

    return_url = flask_session.pop("billing_return_url", "/dashboard")
    is_new = not flask_session.get("user_id")  # still not logged in = brand new
    return render_template(
        "auth/billing_success.html",
        active_page="account",
        return_url=return_url,
        is_new_account=is_new,
    )


# ── Webhook Handlers ──────────────────────────────────────

def _handle_checkout_completed(session_obj):
    """New subscription created via Checkout. Handles both existing and new users."""
    client_ref = session_obj.get("client_reference_id")
    customer_id = session_obj.get("customer")
    subscription_id = session_obj.get("subscription")
    customer_email = session_obj.get("customer_details", {}).get("email", "")

    if not subscription_id:
        return

    # Fetch subscription to determine tier from price
    sub = stripe.Subscription.retrieve(subscription_id)
    price_id = sub["items"]["data"][0]["price"]["id"]
    tier = PRICE_TO_TIER.get(price_id, "pro")

    if client_ref and client_ref != "new":
        # Existing logged-in user
        update_user_tier(
            int(client_ref), tier,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
        )
    else:
        # Anonymous checkout — find or create user by email
        if not customer_email:
            # Try to get email from Stripe customer
            try:
                cust = stripe.Customer.retrieve(customer_id)
                customer_email = cust.get("email", "")
            except Exception:
                logger.exception("Failed to retrieve Stripe customer %s for email lookup", customer_id)

        if not customer_email:
            logger.error("Checkout completed but no email found. customer=%s", customer_id)
            return

        from modules.auth import get_user_by_email, create_user
        user = get_user_by_email(customer_email)

        if user:
            # Existing user who wasn't logged in — just upgrade them
            update_user_tier(
                user["id"], tier,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
            )
        else:
            # Brand new user — create account with temporary password
            import secrets as _secrets
            temp_password = _secrets.token_urlsafe(16)
            user = create_user(customer_email, temp_password)
            if not user:
                logger.error("Failed to create user for checkout email=%s", customer_email)
                return

            update_user_tier(
                user["id"], tier,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
            )

            # Mark email as verified (they verified via Stripe payment)
            execute(
                "UPDATE users SET email_verified = 1, verification_token = NULL WHERE id = ?",
                (user["id"],)
            )

            # Send "Set your password" email
            try:
                from modules.auth import create_reset_token
                token = create_reset_token(customer_email)
                from modules.mailer import send as send_email
                base_url = os.environ.get("BASE_URL", "https://inbxr.us")
                send_email(
                    to_email=customer_email,
                    subject="Welcome to InbXr — Set Your Password",
                    html=f"""<h2>Welcome to InbXr!</h2>
                    <p>Your <strong>{tier.title()}</strong> subscription is now active.</p>
                    <p>We created your account automatically. Click below to set your password:</p>
                    <p><a href="{base_url}/reset-password?token={token}" style="display:inline-block;padding:12px 24px;background:#22c55e;color:#fff;text-decoration:none;border-radius:8px;font-weight:700;">Set My Password</a></p>
                    <p>Or log in at <a href="{base_url}/login">{base_url}/login</a> using this email and request a password reset.</p>
                    <p style="color:#888;font-size:0.85rem;">If you didn't make this purchase, please contact us immediately.</p>""",
                )
                logger.info("Sent welcome + set-password email to %s", customer_email)
            except Exception:
                logger.exception("Failed to send welcome email to %s", customer_email)


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
