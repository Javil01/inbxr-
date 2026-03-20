"""
INBXR — Framework Lab Blueprint
Public framework library + Pro/Agency custom builder API.
"""

import json

from flask import (
    Blueprint, render_template, request, jsonify, session,
)

from modules.database import fetchone
from modules.auth import login_required, tier_required
from modules.frameworks import (
    get_all_frameworks, get_framework_by_slug,
    get_user_frameworks, get_user_framework,
    create_user_framework, update_user_framework, delete_user_framework,
    log_framework_usage, get_decision_tree,
    toggle_favorite, get_user_favorites,
)

framework_bp = Blueprint("frameworks", __name__)

# Frameworks visible to free users (full steps unlocked)
_FREE_VISIBLE_SLUGS = {"aida", "pas", "c3po"}


@framework_bp.route("/frameworks")
def frameworks_page():
    """Render the Framework Lab page."""
    return render_template(
        "frameworks.html",
        active_page="frameworks",
        page_title="Framework Lab — Copywriting Frameworks for Email | INBXR",
        page_description="Browse 16 proven copywriting frameworks, build custom frameworks, and apply them to AI rewrites. Master email copy with the INBXR Method.",
        canonical_url="https://inbxr.us/frameworks",
    )


# ── Public API ────────────────────────────────────────

@framework_bp.route("/api/frameworks")
def api_frameworks():
    """Return all built-in frameworks. Steps blurred for free users except AIDA, PAS, C3PO."""
    frameworks = get_all_frameworks()
    tier = session.get("user_tier", "free") if session.get("user_id") else "free"
    is_paid = tier in ("pro", "agency", "api")

    result = []
    for fw in frameworks:
        item = {
            "id": fw["id"],
            "name": fw["name"],
            "slug": fw["slug"],
            "acronym": fw["acronym"],
            "category": fw["category"],
            "description": fw["description"],
            "when_to_use": fw["when_to_use"],
            "sort_order": fw["sort_order"],
        }
        # Unlock steps for paid users or free-visible frameworks
        if is_paid or fw["slug"] in _FREE_VISIBLE_SLUGS:
            item["steps"] = json.loads(fw["steps_json"]) if fw["steps_json"] else []
            item["deliverability_notes"] = fw["deliverability_notes"]
            item["example_output"] = fw["example_output"]
            item["locked"] = False
        else:
            item["steps"] = _blur_steps(fw["steps_json"])
            item["deliverability_notes"] = ""
            item["example_output"] = ""
            item["locked"] = True
        result.append(item)

    return jsonify(result)


@framework_bp.route("/api/frameworks/<slug>")
def api_framework_detail(slug):
    """Return a single framework by slug."""
    fw = get_framework_by_slug(slug)
    if not fw:
        return jsonify({"error": "Framework not found"}), 404

    tier = session.get("user_tier", "free") if session.get("user_id") else "free"
    is_paid = tier in ("pro", "agency", "api")

    item = {
        "id": fw["id"],
        "name": fw["name"],
        "slug": fw["slug"],
        "acronym": fw["acronym"],
        "category": fw["category"],
        "description": fw["description"],
        "when_to_use": fw["when_to_use"],
        "sort_order": fw["sort_order"],
    }

    if is_paid or fw["slug"] in _FREE_VISIBLE_SLUGS:
        item["steps"] = json.loads(fw["steps_json"]) if fw["steps_json"] else []
        item["deliverability_notes"] = fw["deliverability_notes"]
        item["example_output"] = fw["example_output"]
        item["locked"] = False
    else:
        item["steps"] = _blur_steps(fw["steps_json"])
        item["deliverability_notes"] = ""
        item["example_output"] = ""
        item["locked"] = True

    return jsonify(item)


@framework_bp.route("/api/frameworks/decision-tree")
def api_decision_tree():
    """Return the decision tree data."""
    return jsonify(get_decision_tree())


# ── Favorites ─────────────────────────────────────────

@framework_bp.route("/api/frameworks/favorites")
@login_required
def api_get_favorites():
    """Return the current user's favorited framework slugs."""
    user_id = session["user_id"]
    return jsonify(get_user_favorites(user_id))


@framework_bp.route("/api/frameworks/<slug>/favorite", methods=["POST"])
@login_required
def api_toggle_favorite(slug):
    """Toggle favorite on a framework. Returns {favorited: bool}."""
    fw = get_framework_by_slug(slug)
    if not fw:
        return jsonify({"error": "Framework not found"}), 404
    user_id = session["user_id"]
    favorited = toggle_favorite(user_id, fw["id"])
    return jsonify({"favorited": favorited})


# ── User frameworks (Pro/Agency) ──────────────────────

@framework_bp.route("/api/my-frameworks")
@login_required
def api_my_frameworks():
    """Return current user's custom frameworks."""
    user_id = session["user_id"]
    frameworks = get_user_frameworks(user_id)
    result = []
    for fw in frameworks:
        result.append({
            "id": fw["id"],
            "name": fw["name"],
            "slug": fw["slug"],
            "steps": json.loads(fw["steps_json"]) if fw["steps_json"] else [],
            "base_framework_id": fw["base_framework_id"],
            "notes": fw["notes"],
            "created_at": fw["created_at"],
            "updated_at": fw["updated_at"],
        })
    return jsonify(result)


@framework_bp.route("/api/my-frameworks", methods=["POST"])
@login_required
@tier_required("pro", "agency")
def api_create_framework():
    """Create a new custom framework."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    name = (data.get("name") or "").strip()
    steps = data.get("steps") or []
    base_framework_id = data.get("base_framework_id")
    notes = (data.get("notes") or "").strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not steps or not isinstance(steps, list):
        return jsonify({"error": "At least one step is required"}), 400
    if len(name) > 100:
        return jsonify({"error": "Name must be under 100 characters"}), 400
    if len(steps) > 10:
        return jsonify({"error": "Maximum 10 steps allowed"}), 400

    user_id = session["user_id"]
    fw = create_user_framework(user_id, name, steps, base_framework_id, notes)
    if not fw:
        return jsonify({"error": "Could not create framework"}), 500

    log_framework_usage(user_id, framework_id=base_framework_id, action="create")

    return jsonify({
        "id": fw["id"],
        "name": fw["name"],
        "slug": fw["slug"],
        "steps": json.loads(fw["steps_json"]) if fw["steps_json"] else [],
        "notes": fw["notes"],
    }), 201


@framework_bp.route("/api/my-frameworks/<int:fw_id>", methods=["PUT"])
@login_required
@tier_required("pro", "agency")
def api_update_framework(fw_id):
    """Update a custom framework."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    user_id = session["user_id"]
    name = data.get("name")
    steps = data.get("steps")
    notes = data.get("notes")

    if name is not None and not name.strip():
        return jsonify({"error": "Name cannot be empty"}), 400
    if steps is not None and (not isinstance(steps, list) or len(steps) == 0):
        return jsonify({"error": "At least one step is required"}), 400

    fw = update_user_framework(user_id, fw_id, name=name, steps=steps, notes=notes)
    if not fw:
        return jsonify({"error": "Framework not found"}), 404

    return jsonify({
        "id": fw["id"],
        "name": fw["name"],
        "slug": fw["slug"],
        "steps": json.loads(fw["steps_json"]) if fw["steps_json"] else [],
        "notes": fw["notes"],
    })


@framework_bp.route("/api/my-frameworks/<int:fw_id>", methods=["DELETE"])
@login_required
@tier_required("pro", "agency")
def api_delete_framework(fw_id):
    """Delete a custom framework."""
    user_id = session["user_id"]
    deleted = delete_user_framework(user_id, fw_id)
    if not deleted:
        return jsonify({"error": "Framework not found"}), 404
    return jsonify({"ok": True})


# ── Helpers ───────────────────────────────────────────

def _blur_steps(steps_json):
    """Return step keys/labels without descriptions (for locked frameworks)."""
    try:
        steps = json.loads(steps_json) if steps_json else []
    except (json.JSONDecodeError, TypeError):
        return []
    return [{"key": s.get("key", ""), "label": s.get("label", ""), "description": ""} for s in steps]
