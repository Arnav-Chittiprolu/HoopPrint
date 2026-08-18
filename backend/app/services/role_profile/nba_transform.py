"""NBA raw stats → rate fields, provenance, cohort percentiles, role_vector.

Does not write style_vector. Missing denominators omit the dimension (never
zero-fill). Rim pressure prefers drives/touch; paint-points share is a documented
proxy only when touches are unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.role_profile import validate_role_vector_payload
from app.services.role_profile.constants import (
    MIN_CATCH_ATTEMPT_SHARE_DENOM,
    MIN_NBA_GP,
    MIN_NBA_MINUTES,
    MIN_TOUCHES_FOR_RATE,
    NBA_TRANSFORM_VERSION,
    ROLE_VECTOR_KEYS,
    SEASON_TYPE_DEFAULT,
)

ROLE_FIELD_SPECS: dict[str, dict[str, str]] = {
    "catch_readiness": {
        "rate_key": "catch_shoot_share",
        "endpoint_name": "LeagueDashPtStats:CatchShoot+PullUpShot",
        "field_name": "CATCH_SHOOT_FGA / (CATCH_SHOOT_FGA + PULL_UP_FGA)",
    },
    "rim_pressure_tendency": {
        "rate_key": "drives_per_touch",
        "endpoint_name": "LeagueDashPtStats:Drives+Possessions",
        "field_name": "DRIVES / TOUCHES",
    },
    "playmaking_orientation": {
        "rate_key": "potential_assists_per_touch",
        "endpoint_name": "LeagueDashPtStats:Passing+Possessions",
        "field_name": "POTENTIAL_AST / TOUCHES",
    },
}

_RIM_PROXY_SPEC = {
    "rate_key": "rim_attempt_share",
    "endpoint_name": "LeagueDashPlayerStats:Scoring",
    "field_name": "PCT_PTS_PAINT",
    "note": "paint_points_share_proxy_not_restricted_area_fga",
}


def _f(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _raw(player: dict[str, Any]) -> dict[str, Any]:
    raw = player.get("raw_stats")
    return raw if isinstance(raw, dict) else {}


def empirical_percentile(value: float, population: list[float]) -> float:
    """Mid-rank empirical CDF in [0, 1]."""
    n = len(population)
    if n == 0:
        return 0.5
    below = sum(1 for item in population if item < value)
    equal = sum(1 for item in population if item == value)
    return (below + 0.5 * equal) / n


def _ratio(num: float | None, den: float | None, min_den: float) -> float | None:
    if num is None or den is None or den < min_den:
        return None
    return float(num) / float(den)


def derive_rates(player: dict[str, Any]) -> dict[str, Any]:
    """Fill rate columns from endpoint fields or legacy raw_stats keys."""
    raw = _raw(player)
    catch_fga = _f(player.get("catch_shoot_fga")) or _f(raw.get("catch_shoot_fga"))
    pull_fga = _f(player.get("pull_up_fga")) or _f(raw.get("pull_up_fga"))
    drives = _f(player.get("drives")) or _f(raw.get("drives"))
    touches = _f(player.get("touches")) or _f(raw.get("touches"))
    passes = (
        _f(player.get("passes"))
        or _f(raw.get("passes"))
        or _f(raw.get("passes_made"))
    )
    potential = (
        _f(player.get("potential_assists"))
        or _f(raw.get("potential_assists"))
        or _f(raw.get("potential_ast"))
    )
    gp = _f(player.get("gp")) or _f(raw.get("gp"))
    minutes = _f(player.get("minutes")) or _f(raw.get("minutes")) or _f(raw.get("min"))
    paint = _f(player.get("rim_attempt_share")) or _f(raw.get("pct_pts_paint"))
    ast_pct = _f(player.get("assist_pct")) or _f(raw.get("ast_pct")) or _f(raw.get("assist_pct"))

    catch_share = _ratio(
        catch_fga,
        (catch_fga + pull_fga) if catch_fga is not None and pull_fga is not None else None,
        MIN_CATCH_ATTEMPT_SHARE_DENOM,
    )
    drives_per_touch = _ratio(drives, touches, MIN_TOUCHES_FOR_RATE)
    passes_per_touch = _ratio(passes, touches, MIN_TOUCHES_FOR_RATE)
    pot_per_touch = _ratio(potential, touches, MIN_TOUCHES_FOR_RATE)
    pot_per_pass = _ratio(potential, passes, MIN_TOUCHES_FOR_RATE)

    gp_ok = gp is not None and gp >= MIN_NBA_GP
    min_ok = minutes is None or minutes >= MIN_NBA_MINUTES
    meets = bool(gp_ok and min_ok)

    return {
        "catch_shoot_fga": catch_fga,
        "pull_up_fga": pull_fga,
        "catch_shoot_share": catch_share,
        "drives": drives,
        "touches": touches,
        "drives_per_touch": drives_per_touch,
        "rim_attempt_share": paint,
        "passes": passes,
        "potential_assists": potential,
        "passes_per_touch": passes_per_touch,
        "potential_assists_per_pass": pot_per_pass,
        "potential_assists_per_touch": pot_per_touch,
        "assist_pct": ast_pct,
        "minutes": minutes,
        "gp": gp,
        "meets_min_sample": meets,
        "used_rim_paint_proxy": drives_per_touch is None and paint is not None,
    }


def _reliability(player: dict[str, Any], *, denom: float | None, denom_scale: float) -> float:
    gp = _f(player.get("gp")) or 0.0
    minutes = _f(player.get("minutes")) or 0.0
    sample = min(1.0, max(gp / 40.0, minutes / 800.0 if minutes else 0.0, gp / 40.0))
    if denom is None or denom_scale <= 0:
        return sample
    return sample * min(1.0, denom / denom_scale)


def _prov(
    *,
    season: str,
    position_group: str,
    endpoint_name: str,
    field_name: str,
    raw_value: float | None,
    raw_numerator: float | None,
    raw_denominator: float | None,
    percentile: float | None,
    sample_reliability: float | None,
    fetched_at: datetime,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "raw_value": raw_value,
        "raw_numerator": raw_numerator,
        "raw_denominator": raw_denominator,
        "season": season,
        "season_type": SEASON_TYPE_DEFAULT,
        "endpoint_name": endpoint_name,
        "endpoint_params": {
            "season": season,
            "season_type": SEASON_TYPE_DEFAULT,
            "per_mode": "PerGame",
        },
        "field_name": field_name,
        "transformation_version": NBA_TRANSFORM_VERSION,
        "cohort_definition": (
            f"position_group={position_group}; min_gp={MIN_NBA_GP}; "
            f"min_minutes={MIN_NBA_MINUTES}"
        ),
        "percentile": percentile,
        "sample_reliability": sample_reliability,
        "fetched_at": fetched_at.isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


def _require_provenance(source: dict[str, Any], dim: str) -> None:
    block = source.get(dim)
    if not isinstance(block, dict):
        raise ValueError(f"NBA field {dim} missing provenance")
    if not block.get("endpoint_name") or not block.get("field_name"):
        raise ValueError(f"NBA field {dim} missing endpoint/field provenance")
    if block.get("raw_denominator") is None and block.get("raw_value") is None:
        raise ValueError(f"NBA field {dim} missing denominator or raw_value")


def finalize_nba_role_rows(
    players: list[dict[str, Any]],
    *,
    season: str | None = None,
    fetched_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Derive rates + within-cohort percentiles + role_vector. No style_vector."""
    stamp = fetched_at or datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []

    prepared: list[dict[str, Any]] = []
    for player in players:
        row = dict(player)
        rates = derive_rates(row)
        row.update({k: v for k, v in rates.items() if k != "used_rim_paint_proxy"})
        row["_used_rim_paint_proxy"] = rates["used_rim_paint_proxy"]
        row["position_group"] = row.get("position_group") or row.get("position")
        row["season"] = row.get("season") or season
        row["season_type"] = row.get("season_type") or SEASON_TYPE_DEFAULT
        row["transform_version"] = NBA_TRANSFORM_VERSION
        prepared.append(row)

    eligible = [p for p in prepared if p.get("meets_min_sample")]
    by_group: dict[str, list[dict[str, Any]]] = {}
    for player in eligible:
        group = str(player.get("position_group") or "")
        by_group.setdefault(group, []).append(player)

    def _pop(group: str, key: str) -> list[float]:
        values: list[float] = []
        for player in by_group.get(group, []):
            value = _f(player.get(key))
            if value is not None:
                values.append(value)
        return values

    for row in prepared:
        group = str(row.get("position_group") or "")
        season_s = str(row.get("season") or season or "")
        source: dict[str, Any] = {}
        vector: dict[str, float] = {}
        percentiles: dict[str, float] = {}

        catch_rate = _f(row.get("catch_shoot_share"))
        catch_den = None
        if row.get("catch_shoot_fga") is not None and row.get("pull_up_fga") is not None:
            catch_den = float(row["catch_shoot_fga"]) + float(row["pull_up_fga"])
        if catch_rate is not None and row.get("meets_min_sample"):
            pop = _pop(group, "catch_shoot_share")
            pct = empirical_percentile(catch_rate, pop) if pop else None
            if pct is not None:
                vector["catch_readiness"] = pct
                percentiles["catch_readiness"] = pct
            source["catch_readiness"] = _prov(
                season=season_s,
                position_group=group,
                endpoint_name=ROLE_FIELD_SPECS["catch_readiness"]["endpoint_name"],
                field_name=ROLE_FIELD_SPECS["catch_readiness"]["field_name"],
                raw_value=catch_rate,
                raw_numerator=_f(row.get("catch_shoot_fga")),
                raw_denominator=catch_den,
                percentile=pct,
                sample_reliability=_reliability(row, denom=catch_den, denom_scale=4.0),
                fetched_at=stamp,
            )

        rim_key = "drives_per_touch"
        rim_rate = _f(row.get("drives_per_touch"))
        rim_num = _f(row.get("drives"))
        rim_den = _f(row.get("touches"))
        rim_spec = ROLE_FIELD_SPECS["rim_pressure_tendency"]
        extra: dict[str, Any] | None = None
        if rim_rate is None and _f(row.get("rim_attempt_share")) is not None:
            rim_key = "rim_attempt_share"
            rim_rate = _f(row.get("rim_attempt_share"))
            rim_num = rim_rate
            rim_den = 1.0
            rim_spec = _RIM_PROXY_SPEC
            extra = {"proxy_note": _RIM_PROXY_SPEC["note"]}
        if rim_rate is not None and row.get("meets_min_sample"):
            pop = _pop(group, rim_key)
            pct = empirical_percentile(rim_rate, pop) if pop else None
            if pct is not None:
                vector["rim_pressure_tendency"] = pct
                percentiles["rim_pressure_tendency"] = pct
            source["rim_pressure_tendency"] = _prov(
                season=season_s,
                position_group=group,
                endpoint_name=rim_spec["endpoint_name"],
                field_name=rim_spec["field_name"],
                raw_value=rim_rate,
                raw_numerator=rim_num,
                raw_denominator=rim_den,
                percentile=pct,
                sample_reliability=_reliability(row, denom=rim_den, denom_scale=2.0),
                fetched_at=stamp,
                extra=extra,
            )

        play_rate = _f(row.get("potential_assists_per_touch"))
        play_num = _f(row.get("potential_assists"))
        play_den = _f(row.get("touches"))
        play_field = ROLE_FIELD_SPECS["playmaking_orientation"]["field_name"]
        play_endpoint = ROLE_FIELD_SPECS["playmaking_orientation"]["endpoint_name"]
        if play_rate is None:
            play_rate = _f(row.get("potential_assists_per_pass"))
            play_den = _f(row.get("passes"))
            play_field = "POTENTIAL_AST / PASSES_MADE"
            play_endpoint = "LeagueDashPtStats:Passing"
        if play_rate is not None and row.get("meets_min_sample"):
            key = (
                "potential_assists_per_touch"
                if row.get("potential_assists_per_touch") is not None
                else "potential_assists_per_pass"
            )
            pop = _pop(group, key)
            pct = empirical_percentile(play_rate, pop) if pop else None
            if pct is not None:
                vector["playmaking_orientation"] = pct
                percentiles["playmaking_orientation"] = pct
            source["playmaking_orientation"] = _prov(
                season=season_s,
                position_group=group,
                endpoint_name=play_endpoint,
                field_name=play_field,
                raw_value=play_rate,
                raw_numerator=play_num,
                raw_denominator=play_den,
                percentile=pct,
                sample_reliability=_reliability(row, denom=play_den, denom_scale=2.0),
                fetched_at=stamp,
            )

        if vector:
            validate_role_vector_payload(vector)
        extra_keys = set(vector) - ROLE_VECTOR_KEYS
        if extra_keys:
            raise ValueError(f"Unknown role vector keys: {sorted(extra_keys)}")
        for dim in vector:
            _require_provenance(source, dim)

        row["role_vector"] = vector
        row["cohort_percentiles"] = percentiles
        row["raw_source"] = source
        row["style_vector"] = {}
        row.pop("_used_rim_paint_proxy", None)
        out.append(row)

    return out


def nba_role_vector(player: dict[str, Any]) -> dict[str, float]:
    vector = player.get("role_vector") or {}
    if not isinstance(vector, dict):
        return {}
    validate_role_vector_payload({k: v for k, v in vector.items() if v is not None})
    return {
        key: float(vector[key])
        for key in ROLE_VECTOR_KEYS
        if isinstance(vector.get(key), (int, float))
    }


def nba_reliability_weights(player: dict[str, Any]) -> dict[str, float]:
    source = player.get("raw_source") or {}
    out: dict[str, float] = {}
    for key in ROLE_VECTOR_KEYS:
        block = source.get(key) if isinstance(source, dict) else None
        if isinstance(block, dict) and isinstance(block.get("sample_reliability"), (int, float)):
            out[key] = max(0.05, min(1.0, float(block["sample_reliability"])))
        elif key in nba_role_vector(player):
            out[key] = 0.5
    return out
