"""
Chapter 3 argument quality framework from:
"Audience-Aware Computational Argumentation" — El Baff, 2026
"""

from itertools import combinations

QUALITY_MATRIX = {
    ("CHALLENGING",  "CHALLENGING"):  "High",
    ("CHALLENGING",  "REINFORCING"):  "High",
    ("REINFORCING",  "CHALLENGING"):  "High",
    ("REINFORCING",  "REINFORCING"):  "Medium",
    ("CHALLENGING",  "INEFFECTIVE"):  "Medium",
    ("INEFFECTIVE",  "CHALLENGING"):  "Medium",
    ("REINFORCING",  "INEFFECTIVE"):  "Low",
    ("INEFFECTIVE",  "REINFORCING"):  "Low",
    ("INEFFECTIVE",  "INEFFECTIVE"):  "Lowest",
}

# Ordered from best to worst
QUALITY_ORDER = ["High", "Medium", "Low", "Lowest"]


def pairwise_quality(e1: str, e2: str) -> str:
    """Return quality label for a pair of group effects."""
    key = (e1, e2)
    if key in QUALITY_MATRIX:
        return QUALITY_MATRIX[key]
    # Try reversed key
    key_r = (e2, e1)
    if key_r in QUALITY_MATRIX:
        return QUALITY_MATRIX[key_r]
    return "Lowest"


def overall_quality(pairwise_results: list) -> str:
    """Return worst (most conservative) quality label from a list of pairwise results."""
    if not pairwise_results:
        return "Lowest"
    return max(pairwise_results, key=lambda q: QUALITY_ORDER.index(q))


def compute_pairwise_and_overall(group_effects: dict) -> tuple:
    """
    Given {group_id: final_label}, compute all pairwise quality labels
    and derive the overall quality.

    Returns: (pairwise_list, overall_quality_label)
      pairwise_list: [{"g1": id, "g2": id, "quality": str, "is_worst": bool}, ...]
    """
    group_ids = list(group_effects.keys())
    pairwise = []

    for g1, g2 in combinations(group_ids, 2):
        e1 = group_effects[g1]
        e2 = group_effects[g2]
        # Skip ERROR labels in quality computation
        if e1 == "ERROR" or e2 == "ERROR":
            continue
        q = pairwise_quality(e1, e2)
        pairwise.append({"g1": g1, "g2": g2, "quality": q, "is_worst": False})

    quality_labels = [p["quality"] for p in pairwise]
    overall = overall_quality(quality_labels) if quality_labels else "Lowest"

    # Mark worst pairs
    for p in pairwise:
        if p["quality"] == overall:
            p["is_worst"] = True

    return pairwise, overall


def apply_level1_majority(runs: list) -> str:
    """
    Aggregate run labels using this priority order (a single run passes through):
    1. Any CHALLENGING → CHALLENGING
    2. Any REINFORCING → REINFORCING
    3. Otherwise → INEFFECTIVE
    """
    labels = [r.get("label", "INEFFECTIVE") for r in runs]
    if "CHALLENGING" in labels:
        return "CHALLENGING"
    if "REINFORCING" in labels:
        return "REINFORCING"
    return "INEFFECTIVE"
