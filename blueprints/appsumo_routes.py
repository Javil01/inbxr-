"""
InbXr — AppSumo LTD Funnel Routes
─────────────────────────────────
Dedicated /appsumo routes for the lifetime deal funnel. Kept in a
separate blueprint so the AppSumo experience is cleanly isolated
from the main inbxr.us funnel. Rule: inbxr.us never shows LTD
pricing on its main pages, and /appsumo never shows MRR pricing
as the primary CTA. Each audience sees their own funnel.

Routes:
    GET  /appsumo              Landing page with 3-tier stack pricing
    GET  /appsumo/redeem       Redeem form (requires login)
    POST /appsumo/redeem       Process the redeem
    GET  /account/ltd          View current LTD status + stacked codes
"""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session

from modules.auth import get_current_user, login_required
from modules.appsumo import (
    redeem_code,
    get_user_code_count,
    get_user_codes,
    get_toolkit_tier,
    TOOLKIT_TIERS,
)

logger = logging.getLogger("inbxr.appsumo")

appsumo_bp = Blueprint("appsumo", __name__)


@appsumo_bp.route("/appsumo")
def appsumo_landing():
    """AppSumo LTD landing page. Public, indexable.

    Shows:
      - Hero with the core LTD pitch
      - 3-tier stack pricing table
      - What's included at each tier
      - Comparison with MRR (honest: Intelligence features are MRR only)
      - "Redeem your code" CTA for buyers coming from AppSumo
    """
    return render_template(
        "public/appsumo.html",
        allow_index=True,
        title="InbXr Toolkit · Lifetime Deal · Signal Engine for Email Deliverability",
        meta_description=(
            "Stack AppSumo codes to unlock the InbXr Toolkit: Signal Score engine, "
            "7-signal PDF reports, Chrome extension, bulk CSV grading, and all "
            "deliverability utilities. Lifetime access. No monthly fees."
        ),
        tiers=TOOLKIT_TIERS,
    )


@appsumo_bp.route("/appsumo/redeem", methods=["GET"])
def appsumo_redeem_form():
    """Redeem form. Requires login so we can tie the code to an account."""
    user = get_current_user()
    if not user:
        # Stash the intent in session and bounce to signup
        session["_post_signup_redirect"] = "/appsumo/redeem"
        return redirect(url_for("auth.signup") + "?from=appsumo")

    codes = get_user_codes(user["id"])
    code_count = len(codes)
    tier_level = min(3, code_count)
    tier = get_toolkit_tier(tier_level)

    return render_template(
        "public/appsumo_redeem.html",
        allow_index=False,
        title="Redeem AppSumo Code · InbXr",
        user=user,
        codes=codes,
        code_count=code_count,
        tier_level=tier_level,
        tier=tier,
        all_tiers=TOOLKIT_TIERS,
    )


@appsumo_bp.route("/appsumo/redeem", methods=["POST"])
@login_required
def appsumo_redeem_submit():
    """Process a code redemption. Returns JSON so the form can update inline."""
    user = get_current_user()
    data = request.get_json(silent=True) or request.form.to_dict()
    code = (data.get("code") or "").strip()

    if not code:
        return jsonify({"ok": False, "error": "Enter a code."}), 400

    ok, result = redeem_code(user["id"], code)
    if not ok:
        return jsonify(result), 400

    return jsonify(result)


@appsumo_bp.route("/account/ltd")
@login_required
def account_ltd():
    """User's LTD status page. Shows their stacked codes, current tier,
    and capacity. Also hosts the 'stack another code' form for users
    who want to upgrade by redeeming additional AppSumo codes."""
    user = get_current_user()
    codes = get_user_codes(user["id"])
    code_count = len(codes)
    tier_level = min(3, code_count)
    tier = get_toolkit_tier(tier_level)

    return render_template(
        "auth/account_ltd.html",
        user=user,
        active_page="account",
        codes=codes,
        code_count=code_count,
        tier_level=tier_level,
        tier=tier,
        all_tiers=TOOLKIT_TIERS,
    )
