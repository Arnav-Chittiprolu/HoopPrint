"""Deterministic role archetypes from role-vector bands (not LLM)."""

from __future__ import annotations

from typing import Any

from app.models.role_profile import EvidenceTier
from app.services.role_profile.constants import ROLE_VECTOR_KEYS

HIGH = 0.66
LOW = 0.33


def _band(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= HIGH:
        return "high"
    if value <= LOW:
        return "low"
    return "mid"


def classify_archetype(
    vector: dict[str, float],
    *,
    position: str | None = None,
    evidence_tier: EvidenceTier | str | None = None,
) -> dict[str, Any]:
    """Map role-vector bands to a stored archetype. Emerging tier minimum."""
    tier = evidence_tier.value if isinstance(evidence_tier, EvidenceTier) else evidence_tier
    if tier in {None, EvidenceTier.insufficient.value, "insufficient"}:
        return {
            "key": "insufficient_evidence",
            "label": "Keep building your profile",
            "detail": "Not enough quality-checked events for a role archetype yet.",
            "bands": {},
            "shown": False,
        }

    cr = vector.get("catch_readiness")
    rp = vector.get("rim_pressure_tendency")
    pm = vector.get("playmaking_orientation")
    bands = {
        "catch_readiness": _band(cr),
        "rim_pressure_tendency": _band(rp),
        "playmaking_orientation": _band(pm),
    }
    pos = (position or "player").strip().lower()
    pos_word = pos if pos in {"guard", "wing", "forward", "center"} else "player"

    if cr is not None and cr >= HIGH and (rp is None or rp < HIGH):
        key, label = "quick_trigger_perimeter", "quick-trigger perimeter role"
    elif rp is not None and rp >= HIGH:
        key, label = "rim_pressure", f"rim-pressure {pos_word}"
    elif pm is not None and pm >= HIGH:
        key, label = "pass_oriented_connector", "pass-oriented connector"
    else:
        key, label = "balanced_developing", "balanced developing profile"

    return {
        "key": key,
        "label": label,
        "detail": (
            "Mapped from quality-checked role-dimension bands. "
            "Not a skill rating or NBA mechanical match."
        ),
        "bands": bands,
        "shown": True,
        "active_keys": [k for k in ROLE_VECTOR_KEYS if k in vector],
    }
