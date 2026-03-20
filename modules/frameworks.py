"""
INBXR — Framework Lab CRUD Helpers
Manage built-in frameworks, user custom frameworks, and usage tracking.
"""

import json
import re
from modules.database import fetchall, fetchone, execute


# ── Built-in framework queries ────────────────────────

def get_all_frameworks():
    """Return all built-in frameworks ordered by sort_order."""
    return fetchall(
        "SELECT * FROM frameworks WHERE is_builtin = 1 ORDER BY sort_order, name"
    )


def get_framework_by_slug(slug):
    """Return a single framework by slug."""
    return fetchone("SELECT * FROM frameworks WHERE slug = ?", (slug,))


def get_framework_by_id(framework_id):
    """Return a single framework by id."""
    return fetchone("SELECT * FROM frameworks WHERE id = ?", (framework_id,))


# ── User custom framework queries ─────────────────────

def get_user_frameworks(user_id):
    """Return all custom frameworks for a user."""
    return fetchall(
        "SELECT * FROM user_frameworks WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )


def get_user_framework(user_id, fw_id):
    """Return a single user framework (must belong to user)."""
    return fetchone(
        "SELECT * FROM user_frameworks WHERE id = ? AND user_id = ?",
        (fw_id, user_id)
    )


def create_user_framework(user_id, name, steps, base_framework_id=None, notes=""):
    """Create a custom framework. Returns the new row."""
    slug = _make_slug(name, user_id)
    steps_json = json.dumps(steps) if isinstance(steps, list) else steps
    cur = execute(
        """INSERT INTO user_frameworks
           (user_id, name, slug, steps_json, base_framework_id, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, name, slug, steps_json, base_framework_id, notes)
    )
    return get_user_framework(user_id, cur.lastrowid)


def update_user_framework(user_id, fw_id, name=None, steps=None, notes=None):
    """Update a custom framework. Only updates provided fields."""
    fw = get_user_framework(user_id, fw_id)
    if not fw:
        return None
    new_name = name if name is not None else fw["name"]
    new_steps = json.dumps(steps) if steps is not None else fw["steps_json"]
    new_notes = notes if notes is not None else fw["notes"]
    new_slug = _make_slug(new_name, user_id) if name is not None else fw["slug"]
    execute(
        """UPDATE user_frameworks
           SET name = ?, slug = ?, steps_json = ?, notes = ?, updated_at = datetime('now')
           WHERE id = ? AND user_id = ?""",
        (new_name, new_slug, new_steps, new_notes, fw_id, user_id)
    )
    return get_user_framework(user_id, fw_id)


def delete_user_framework(user_id, fw_id):
    """Delete a user framework. Returns True if deleted."""
    cur = execute(
        "DELETE FROM user_frameworks WHERE id = ? AND user_id = ?",
        (fw_id, user_id)
    )
    return cur.rowcount > 0


# ── Usage tracking ────────────────────────────────────

def log_framework_usage(user_id, framework_id=None, user_framework_id=None,
                        check_history_id=None, action="rewrite"):
    """Log framework usage for analytics."""
    execute(
        """INSERT INTO framework_usage
           (user_id, framework_id, user_framework_id, check_history_id, action)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, framework_id, user_framework_id, check_history_id, action)
    )


# ── Decision tree data ────────────────────────────────

def get_decision_tree():
    """Return decision tree structure for framework selection."""
    return {
        "question": "What's your audience's current state?",
        "options": [
            {
                "label": "They don't know they have a problem",
                "description": "Unaware audience — need education first",
                "frameworks": ["aida", "star-story-solution", "c3po"],
            },
            {
                "label": "They know the problem but not the solution",
                "description": "Problem-aware — agitate and solve",
                "frameworks": ["pas", "bab", "papa", "acca"],
            },
            {
                "label": "They know solutions exist but haven't chosen",
                "description": "Solution-aware — differentiate and prove",
                "frameworks": ["fab", "4ps", "app", "4us"],
            },
            {
                "label": "They're comparing options right now",
                "description": "Product-aware — close with proof and urgency",
                "frameworks": ["5cs", "slap", "3-reasons-why"],
            },
            {
                "label": "They know you, just need a nudge",
                "description": "Most-aware — simple CTA with reminder",
                "frameworks": ["4es", "prune", "pas"],
            },
        ],
    }


# ── Helpers ───────────────────────────────────────────

def _make_slug(name, user_id):
    """Generate a URL-safe slug from a name."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not slug:
        slug = "framework"
    # Check for uniqueness within user's frameworks
    existing = fetchone(
        "SELECT id FROM user_frameworks WHERE user_id = ? AND slug = ?",
        (user_id, slug)
    )
    if existing:
        slug = f"{slug}-{existing['id'] + 1}"
    return slug
