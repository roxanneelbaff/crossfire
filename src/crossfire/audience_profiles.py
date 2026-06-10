"""
Loads audience group profiles from the project-level profiles/ folder.
Each subfolder is a profile set (e.g. american_political_ideology).
Each JSON file within is one group.
"""

import json

from .paths import PROFILES_DIR


def load_profile_set(profile_set: str) -> list:
    """
    Load all group JSON files from profiles/<profile_set>/ and return
    a list of group dicts, sorted by filename (preserves a stable order).
    """
    folder = PROFILES_DIR / profile_set
    groups = []
    for path in sorted(folder.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        # Use the filename stem as the canonical id if not set
        data.setdefault("id", path.stem)
        groups.append(data)
    return groups


# ── Default profile set used by the app ─────────────────────────────────────

AUDIENCE_GROUPS = load_profile_set("american_political_ideology")
GROUPS_BY_ID    = {g["id"]: g for g in AUDIENCE_GROUPS}
