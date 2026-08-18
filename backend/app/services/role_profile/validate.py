"""Role-profile validation helpers."""

from __future__ import annotations

from typing import Any

from app.models.role_profile import UserRoleVector, validate_role_vector_payload
from app.services.role_profile.constants import BANNED_MECHANICS_KEYS


def build_user_role_vector(data: dict[str, float | None]) -> UserRoleVector:
    """Parse and validate a user role vector dict."""
    validate_role_vector_payload({k: v for k, v in data.items() if v is not None})
    return UserRoleVector(
        catch_readiness=data.get("catch_readiness"),
        rim_pressure_tendency=data.get("rim_pressure_tendency"),
        playmaking_orientation=data.get("playmaking_orientation"),
    )


def build_role_vector(data: dict[str, float | None]) -> dict[str, float]:
    """Public scoring helper: banned mechanics keys; omit nulls; never zero-fill."""
    model = build_user_role_vector(data)
    return {
        key: float(value)
        for key, value in model.model_dump(exclude_none=True).items()
        if isinstance(value, (int, float))
    }


def assert_no_mechanics_keys(payload: dict[str, Any]) -> None:
    """Regression helper: raise if any banned mechanics key appears at top level."""
    found = set(payload) & BANNED_MECHANICS_KEYS
    if found:
        raise ValueError(f"Banned mechanics keys in role payload: {sorted(found)}")
