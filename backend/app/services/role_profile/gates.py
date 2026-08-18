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
    MIN_POST_POSE_SAMPLES,
    MIN_PRE_POSE_SAMPLES,
    MIN_TRACK_CONFIDENCE,
    MIN_VIDEO_FPS,
    MIN_WRIST_SEPARATION_FOR_CATCH,
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

    catch_idx = find_catch_index(parsed, before_index=release_idx)
    if catch_idx is None or catch_idx >= release_idx:
        return GateResult(False, "no_catch_proxy", signal, quality, None)

    catch_frame, catch_lookup = parsed[catch_idx]
    left = catch_lookup.xy("left_wrist")
    right = catch_lookup.xy("right_wrist")
    if left is None or right is None:
        return GateResult(False, "no_catch_proxy", signal, quality, None)

    wrist_sep = float(np.linalg.norm(left - right))
    quality["wrist_separation_at_catch"] = wrist_sep
    if wrist_sep > MAX_WRIST_SEPARATION_FOR_CATCH:
        return GateResult(False, "no_catch_proxy", signal, quality, None)
    if wrist_sep < MIN_WRIST_SEPARATION_FOR_CATCH:
        return GateResult(False, "no_catch_proxy", signal, quality, None)

    pre_catch = catch_idx
    post_release = len(parsed) - release_idx - 1
    quality["pre_catch_pose_samples"] = pre_catch
    quality["post_release_pose_samples"] = post_release
    if pre_catch < MIN_PRE_POSE_SAMPLES or post_release < MIN_POST_POSE_SAMPLES:
        return GateResult(False, "insufficient_pre_post_window", signal, quality, None)

    signal["catch_frame_index"] = catch_frame
    signal["release_frame_index"] = release_frame
    signal["gather_to_release_pose_frames"] = float(release_frame - catch_frame)

    if video_fps is None or video_fps < MIN_VIDEO_FPS:
        return GateResult(False, "missing_fps", signal, quality, None)

    catch_to_release_s = (release_frame - catch_frame) / float(video_fps)
    signal["catch_to_release_s"] = catch_to_release_s
    quality["video_fps"] = video_fps

    if catch_to_release_s < CATCH_RELEASE_MIN_S or catch_to_release_s > CATCH_RELEASE_MAX_S:
        return GateResult(
            False,
            "catch_timing_out_of_range",
            signal,
            quality,
            _timing_confidence(catch_to_release_s) * 0.5,
        )

    confidence = _clamp01(
        0.35 * arm_vis
        + 0.25 * mean_track_conf
        + 0.40 * _timing_confidence(catch_to_release_s)
    )
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
    shoulder = lookup.xy(names["shoulder"])
    elbow = lookup.xy(names["elbow"])
    wrist = lookup.xy(names["wrist"])
    if shoulder is None or elbow is None or wrist is None:
        return GateResult(False, "low_pose_visibility", signal, quality, None)

    arm_vis = _shooting_arm_visibility(lookup, names)
    quality["pass_arm_visibility"] = arm_vis
    if arm_vis < 0.35:
        return GateResult(False, "low_pose_visibility", signal, quality, None)

    pre, post = _count_pre_post(parsed, peak_list_index)
    quality["pre_pose_samples"] = pre
    quality["post_pose_samples"] = post
    if pre < MIN_PRE_POSE_SAMPLES or post < MIN_POST_POSE_SAMPLES:
        return GateResult(False, "insufficient_pre_post_window", signal, quality, None)

    try:
        extension = angle_at(elbow, shoulder, wrist)
    except ValueError:
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

    if extension < 100.0:
        return GateResult(
            False,
            "no_pass_release",
            signal,
            quality,
            _clamp01(extension / 100.0) * 0.5,
        )

    confidence = _clamp01(0.40 * arm_vis + 0.30 * mean_track_conf + 0.30 * (extension / 180.0))
    return GateResult(True, None, signal, quality, confidence)


def find_pass_release_peaks(
    parsed: list[tuple[int, LandmarkLookup]],
    dominant_hand: str,
) -> list[int]:
    names = side_names(dominant_hand)
    elbow_series: list[float | None] = []
    for _, lookup in parsed:
        shoulder = lookup.xy(names["shoulder"])
        elbow = lookup.xy(names["elbow"])
        wrist = lookup.xy(names["wrist"])
        if shoulder is None or elbow is None or wrist is None:
            elbow_series.append(None)
            continue
        try:
            elbow_series.append(angle_at(elbow, shoulder, wrist))
        except ValueError:
            elbow_series.append(None)
    return local_maxima_indices(elbow_series, min_prominence=8.0)


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
