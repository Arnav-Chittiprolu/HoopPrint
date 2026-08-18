"""Phase 10.2 — role dimension event gates (pure functions)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.services.features.geometry import (
    LandmarkLookup,
    angle_at,
    distance,
    mid_hip,
    side_names,
    standing_height_proxy,
)
from app.services.features.heuristics import (
    find_catch_index,
    find_pass_release_index,
    find_shot_release_index,
    local_maxima_indices,
    mean_standing_height,
)
from app.services.role_profile.constants import (
    BURST_WINDOW_MS_DEFAULT,
    BURST_WINDOW_MS_MAX,
    BURST_WINDOW_MS_MIN,
    CATCH_RELEASE_MAX_S,
    CATCH_RELEASE_MIN_S,
    MAX_WRIST_SEPARATION_FOR_CATCH,
    MIN_HIP_BURST_BODY_LENGTHS,
    MIN_HIP_TRAVEL_FOR_PULL_UP,
    MIN_POSE_SAMPLES_FOR_PASS,
    MIN_POST_POSE_SAMPLES,
    MIN_PRE_POSE_SAMPLES,
    MIN_TRACK_CONFIDENCE,
    MIN_VIDEO_FPS,
    MIN_WRIST_SEPARATION_FOR_CATCH,
    PLAYMAKING_EXTENSION_FLOOR_DEG,
)


@dataclass(frozen=True)
class GateResult:
    gate_passed: bool
    rejection_reason: str | None
    signal_values: dict[str, Any]
    quality: dict[str, Any]
    event_confidence: float | None
    burst_window_ms: int | None = None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _timing_confidence(seconds: float) -> float:
    mid = (CATCH_RELEASE_MIN_S + CATCH_RELEASE_MAX_S) / 2.0
    half = (CATCH_RELEASE_MAX_S - CATCH_RELEASE_MIN_S) / 2.0
    if half <= 0:
        return 1.0
    return _clamp01(1.0 - abs(seconds - mid) / half)


def _hip_travel_body_lengths(
    parsed: list[tuple[int, LandmarkLookup]],
    end_list_index: int | None = None,
) -> float:
    """Max hip path span in the window, not just start-to-end.

    A pull-up jumper often lands near where they jumped, so hips[-1] - hips[0]
    can be ~0 even when there was a clear jump. If `end_list_index` is None,
    use the full clip (needed when tracking starts at the shot itself).
    """
    if end_list_index is None:
        window = parsed
    else:
        window = parsed[: max(end_list_index, 0) + 1]
    standing = mean_standing_height(window) or 1.0
    hips: list[np.ndarray] = []
    for _, lookup in window:
        hip = mid_hip(lookup)
        if hip is not None:
            hips.append(hip)
    if len(hips) < 2:
        return 0.0
    arr = np.stack(hips)
    from_start = float(np.max(np.linalg.norm(arr - arr[0], axis=1)))
    bbox_span = float(np.linalg.norm(arr.max(axis=0) - arr.min(axis=0)))
    return max(from_start, bbox_span) / max(float(standing), 1e-6)


def _hip_vertical_range_body_lengths(
    parsed: list[tuple[int, LandmarkLookup]],
) -> float:
    standing = mean_standing_height(parsed) or 1.0
    ys: list[float] = []
    for _, lookup in parsed:
        hip = mid_hip(lookup)
        if hip is not None:
            ys.append(float(hip[1]))
    if len(ys) < 2:
        return 0.0
    return (max(ys) - min(ys)) / max(float(standing), 1e-6)


def _catch_ok(lookup: LandmarkLookup) -> tuple[bool, float | None]:
    left = lookup.xy("left_wrist")
    right = lookup.xy("right_wrist")
    if left is None or right is None:
        return False, None
    wrist_sep = float(np.linalg.norm(left - right))
    ok = MIN_WRIST_SEPARATION_FOR_CATCH <= wrist_sep <= MAX_WRIST_SEPARATION_FOR_CATCH
    return ok, wrist_sep


def gate_catch_readiness(
    parsed: list[tuple[int, LandmarkLookup]],
    *,
    dominant_hand: str,
    video_fps: float | None,
    mean_track_conf: float,
) -> GateResult:
    quality: dict[str, Any] = {"mean_track_confidence": mean_track_conf}
    signal: dict[str, Any] = {}

    if mean_track_conf < MIN_TRACK_CONFIDENCE:
        return GateResult(
            False,
            "low_track_confidence",
            signal,
            quality,
            None,
        )

    release_idx = find_shot_release_index(parsed, dominant_hand)
    if release_idx is None:
        return GateResult(False, "no_release_frame", signal, quality, None)

    release_frame, release_lookup = parsed[release_idx]
    names = side_names(dominant_hand)
    arm_vis = _shooting_arm_visibility(release_lookup, names)
    quality["release_arm_visibility"] = arm_vis
    if arm_vis < 0.35:
        return GateResult(False, "low_pose_visibility", signal, quality, None)

    if video_fps is None or video_fps < MIN_VIDEO_FPS:
        return GateResult(False, "missing_fps", signal, quality, None)
    quality["video_fps"] = video_fps

    catch_idx = find_catch_index(parsed, before_index=release_idx)
    has_catch = False
    catch_to_release_s: float | None = None
    if catch_idx is not None and catch_idx < release_idx:
        catch_frame, catch_lookup = parsed[catch_idx]
        catch_ok, wrist_sep = _catch_ok(catch_lookup)
        quality["wrist_separation_at_catch"] = wrist_sep
        if catch_ok:
            has_catch = True
            catch_to_release_s = (release_frame - catch_frame) / float(video_fps)
            signal["catch_frame_index"] = catch_frame
            signal["gather_to_release_pose_frames"] = float(release_frame - catch_frame)

    hip_travel_to_release = _hip_travel_body_lengths(parsed, release_idx)
    hip_travel = _hip_travel_body_lengths(parsed)
    hip_vertical = _hip_vertical_range_body_lengths(parsed)
    quality["hip_travel_body_lengths"] = hip_travel
    quality["hip_travel_to_release_body_lengths"] = hip_travel_to_release
    quality["hip_vertical_range_body_lengths"] = hip_vertical

    pre_samples = catch_idx if has_catch and catch_idx is not None else release_idx
    post_release = len(parsed) - release_idx - 1
    quality["pre_pose_samples"] = pre_samples
    quality["post_release_pose_samples"] = post_release

    moving_into_shot = max(hip_travel, hip_vertical) >= MIN_HIP_TRAVEL_FOR_PULL_UP

    origin: str | None = None
    if has_catch and catch_to_release_s is not None:
        origin = "catch_and_shoot" if catch_to_release_s <= CATCH_RELEASE_MAX_S else "pull_up"
    elif moving_into_shot:
        origin = "pull_up"
    else:
        origin = None

    if origin == "catch_and_shoot":
        if pre_samples < MIN_PRE_POSE_SAMPLES or post_release < MIN_POST_POSE_SAMPLES:
            return GateResult(False, "insufficient_pre_post_window", signal, quality, None)
    elif origin == "pull_up":
        # Box often starts on the jumper (no pre-release) or ends at the peak
        # (no follow-through). Either side of the shot is enough.
        if pre_samples < MIN_PRE_POSE_SAMPLES and post_release < MIN_POST_POSE_SAMPLES:
            return GateResult(False, "insufficient_pre_post_window", signal, quality, None)
    else:
        return GateResult(False, "form_shot", signal, quality, None)

    signal["release_frame_index"] = release_frame
    signal["shot_origin"] = origin
    if catch_to_release_s is None:
        catch_to_release_s = CATCH_RELEASE_MAX_S
    signal["catch_to_release_s"] = catch_to_release_s

    if origin == "catch_and_shoot":
        confidence = _clamp01(
            0.35 * arm_vis
            + 0.25 * mean_track_conf
            + 0.40 * _timing_confidence(max(catch_to_release_s, CATCH_RELEASE_MIN_S))
        )
    else:
        confidence = _clamp01(0.35 * arm_vis + 0.25 * mean_track_conf + 0.28)
        if moving_into_shot:
            confidence = _clamp01(confidence + 0.1)

    return GateResult(True, None, signal, quality, confidence)


def gate_rim_pressure(
    parsed: list[tuple[int, LandmarkLookup]],
    *,
    video_fps: float | None,
    mean_track_conf: float,
    burst_window_ms: int = BURST_WINDOW_MS_DEFAULT,
) -> GateResult:
    burst_window_ms = int(
        max(BURST_WINDOW_MS_MIN, min(BURST_WINDOW_MS_MAX, burst_window_ms))
    )
    quality: dict[str, Any] = {
        "mean_track_confidence": mean_track_conf,
        "burst_window_ms": burst_window_ms,
    }
    signal: dict[str, Any] = {}

    if len(parsed) < 3:
        return GateResult(False, "insufficient_pre_post_window", signal, quality, None)

    if mean_track_conf < MIN_TRACK_CONFIDENCE:
        return GateResult(False, "low_track_confidence", signal, quality, None)

    if video_fps is None or video_fps < MIN_VIDEO_FPS:
        return GateResult(False, "missing_fps", signal, quality, None)

    quality["video_fps"] = video_fps

    hips: list[np.ndarray | None] = [mid_hip(lookup) for _, lookup in parsed]
    standing = mean_standing_height(parsed) or 1.0
    hip_vis = sum(hip_visibility(lookup) for _, lookup in parsed) / len(parsed)
    quality["mean_hip_visibility"] = hip_vis
    if hip_vis < 0.35:
        return GateResult(False, "low_pose_visibility", signal, quality, None)

    speeds: list[float | None] = [None]
    for prev, curr in zip(hips, hips[1:]):
        if prev is None or curr is None:
            speeds.append(None)
        else:
            speeds.append(distance(prev, curr))

    valid_speeds = [s for s in speeds if s is not None]
    if not valid_speeds:
        return GateResult(False, "no_drive_onset", signal, quality, None)

    peak = max(valid_speeds)
    threshold = max(peak * 0.3, 1e-4)
    onset_list_idx = 0
    for index, speed in enumerate(speeds):
        if speed is not None and speed >= threshold:
            onset_list_idx = max(index - 1, 0)
            break

    onset_frame = parsed[onset_list_idx][0]
    signal["onset_frame_index"] = onset_frame

    pre_onset = onset_list_idx
    post_onset = len(parsed) - onset_list_idx - 1
    quality["pre_onset_pose_samples"] = pre_onset
    quality["post_onset_pose_samples"] = post_onset
    if pre_onset > 0 and pre_onset < MIN_PRE_POSE_SAMPLES:
        return GateResult(False, "insufficient_pre_post_window", signal, quality, None)
    if post_onset < MIN_POST_POSE_SAMPLES:
        return GateResult(False, "insufficient_pre_post_window", signal, quality, None)

    window_frames = max(1, int(round(video_fps * burst_window_ms / 1000.0)))
    end_frame = onset_frame + window_frames

    first_hip: np.ndarray | None = None
    last_hip: np.ndarray | None = None
    for frame_index, lookup in parsed[onset_list_idx:]:
        if frame_index > end_frame:
            break
        hip = mid_hip(lookup)
        if hip is None:
            continue
        if first_hip is None:
            first_hip = hip
        last_hip = hip

    if first_hip is None or last_hip is None:
        return GateResult(False, "no_drive_onset", signal, quality, None)

    burst_body_lengths = distance(first_hip, last_hip) / standing
    signal["burst_body_lengths"] = float(burst_body_lengths)
    signal["burst_window_ms"] = burst_window_ms
    signal["burst_window_frames"] = float(window_frames)

    if burst_body_lengths < MIN_HIP_BURST_BODY_LENGTHS:
        return GateResult(
            False,
            "insufficient_hip_displacement",
            signal,
            quality,
            _clamp01(burst_body_lengths / MIN_HIP_BURST_BODY_LENGTHS) * 0.4,
        )

    confidence = _clamp01(
        0.30 * hip_vis
        + 0.30 * mean_track_conf
        + 0.40 * min(1.0, burst_body_lengths / 0.25)
    )
    return GateResult(True, None, signal, quality, confidence, burst_window_ms=burst_window_ms)


def gate_pass_event(
    parsed: list[tuple[int, LandmarkLookup]],
    *,
    peak_list_index: int,
    dominant_hand: str,
    mean_track_conf: float,
    video_fps: float | None,
) -> GateResult:
    quality: dict[str, Any] = {"mean_track_confidence": mean_track_conf}
    signal: dict[str, Any] = {"peak_list_index": peak_list_index}

    if mean_track_conf < MIN_TRACK_CONFIDENCE:
        return GateResult(False, "low_track_confidence", signal, quality, None)

    frame_index, lookup = parsed[peak_list_index]
    names = side_names(dominant_hand)
    other_names = side_names("left" if names["wrist"].startswith("right") else "right")
    arm_vis = max(
        _shooting_arm_visibility(lookup, names),
        _shooting_arm_visibility(lookup, other_names),
    )
    quality["pass_arm_visibility"] = arm_vis
    if arm_vis < 0.35:
        return GateResult(False, "low_pose_visibility", signal, quality, None)

    quality["pose_sample_count"] = len(parsed)
    if len(parsed) < MIN_POSE_SAMPLES_FOR_PASS:
        return GateResult(False, "sparse_track", signal, quality, None)

    pre, post = _count_pre_post(parsed, peak_list_index)
    quality["pre_pose_samples"] = pre
    quality["post_pose_samples"] = post
    # Tracking often starts on the throw or ends right after it.
    if pre < MIN_PRE_POSE_SAMPLES and post < MIN_POST_POSE_SAMPLES:
        return GateResult(False, "insufficient_pre_post_window", signal, quality, None)

    try:
        extension = _best_arm_extension(lookup, dominant_hand)
    except ValueError:
        return GateResult(False, "no_pass_release", signal, quality, None)
    if extension is None:
        return GateResult(False, "no_pass_release", signal, quality, None)

    signal["release_frame_index"] = frame_index
    signal["arm_extension_deg"] = float(extension)

    catch_idx = find_catch_index(parsed, before_index=peak_list_index)
    if catch_idx is not None and catch_idx < peak_list_index:
        catch_frame = parsed[catch_idx][0]
        signal["catch_frame_index"] = catch_frame
        if video_fps is not None and video_fps >= MIN_VIDEO_FPS:
            signal["gather_to_release_s"] = (frame_index - catch_frame) / float(video_fps)
            quality["video_fps"] = video_fps
        else:
            signal["gather_to_release_pose_frames"] = float(frame_index - catch_frame)

    nearby_max = extension
    lo = max(0, peak_list_index - 2)
    hi = min(len(parsed), peak_list_index + 3)
    for _, nearby in parsed[lo:hi]:
        other = _best_arm_extension(nearby, dominant_hand)
        if other is not None:
            nearby_max = max(nearby_max, other)
    signal["arm_extension_deg"] = float(nearby_max)
    quality["video_fps"] = video_fps if video_fps is not None else quality.get("video_fps")

    if nearby_max < PLAYMAKING_EXTENSION_FLOOR_DEG:
        return GateResult(
            False,
            "no_pass_release",
            signal,
            quality,
            _clamp01(nearby_max / PLAYMAKING_EXTENSION_FLOOR_DEG) * 0.5,
        )

    confidence = _clamp01(
        0.40 * arm_vis + 0.30 * mean_track_conf + 0.30 * (nearby_max / 180.0)
    )
    return GateResult(True, None, signal, quality, confidence)


def find_pass_release_peaks(
    parsed: list[tuple[int, LandmarkLookup]],
    dominant_hand: str,
) -> list[int]:
    dominant_series = _elbow_series(parsed, dominant_hand)
    other = "left" if str(dominant_hand).lower().startswith("r") else "right"
    other_series = _elbow_series(parsed, other)
    dom_max = max((v for v in dominant_series if v is not None), default=float("-inf"))
    oth_max = max((v for v in other_series if v is not None), default=float("-inf"))
    series = other_series if oth_max > dom_max else dominant_series
    return local_maxima_indices(series, min_prominence=8.0)


def _elbow_series(
    parsed: list[tuple[int, LandmarkLookup]], dominant_hand: str
) -> list[float | None]:
    names = side_names(dominant_hand)
    elbow_series: list[float | None] = []
    for _, lookup in parsed:
        elbow_series.append(_arm_extension(lookup, names))
    return elbow_series


def _best_arm_extension(lookup: LandmarkLookup, dominant_hand: str) -> float | None:
    dominant = _arm_extension(lookup, side_names(dominant_hand))
    other_hand = "left" if str(dominant_hand).lower().startswith("r") else "right"
    other = _arm_extension(lookup, side_names(other_hand))
    values = [v for v in (dominant, other) if v is not None]
    if not values:
        return None
    return max(values)


def _arm_extension(lookup: LandmarkLookup, names: dict[str, str]) -> float | None:
    shoulder = lookup.xy(names["shoulder"])
    elbow = lookup.xy(names["elbow"])
    wrist = lookup.xy(names["wrist"])
    if shoulder is None or elbow is None or wrist is None:
        return None
    try:
        return float(angle_at(elbow, shoulder, wrist))
    except ValueError:
        return None


def _count_pre_post(
    parsed: list[tuple[int, LandmarkLookup]],
    center_list_index: int,
) -> tuple[int, int]:
    return center_list_index, len(parsed) - center_list_index - 1


def _shooting_arm_visibility(lookup: LandmarkLookup, names: dict[str, str]) -> float:
    visibilities: list[float] = []
    for key in (names["shoulder"], names["elbow"], names["wrist"]):
        point = lookup.get(key)
        if point is None:
            continue
        visibilities.append(float(point.get("visibility") or 0.0))
    if not visibilities:
        return 0.0
    return sum(visibilities) / len(visibilities)


def hip_visibility(lookup: LandmarkLookup) -> float:
    visibilities: list[float] = []
    for key in ("left_hip", "right_hip"):
        point = lookup.get(key)
        if point is None:
            continue
        visibilities.append(float(point.get("visibility") or 0.0))
    if not visibilities:
        return 0.0
    return sum(visibilities) / len(visibilities)
