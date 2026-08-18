"""Extract clip_events from processed pose frames."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from app.models.clip import ClipType
from app.models.role_profile import ClipEventRecord, RoleDimension
from app.services.features.geometry import parse_frames
from app.services.features.heuristics import find_pass_release_index
from app.services.pose_job import FrameKeypoints
from app.services.role_profile.constants import BURST_WINDOW_MS_DEFAULT
from app.services.role_profile.gates import (
    find_pass_release_peaks,
    gate_catch_readiness,
    gate_pass_event,
    gate_rim_pressure,
)
from app.services.role_profile.quality import mean_track_confidence


def _session_date(clip_created_at: str | datetime | None) -> date | None:
    if clip_created_at is None:
        return None
    if isinstance(clip_created_at, datetime):
        return clip_created_at.date()
    try:
        return datetime.fromisoformat(str(clip_created_at).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _pass_record(
    clip_id: UUID | str,
    user_id: UUID | str,
    event_index: int,
    result,
    clip_type: str,
    video_fps: float | None,
    session: date | None,
) -> ClipEventRecord:
    return ClipEventRecord(
        clip_id=_as_uuid(clip_id),
        user_id=_as_uuid(user_id),
        role_dimension=RoleDimension.playmaking,
        event_index=event_index,
        gate_passed=result.gate_passed,
        rejection_reason=result.rejection_reason,
        signal_values=result.signal_values,
        quality={**result.quality, "clip_type": clip_type},
        fps=video_fps,
        burst_window_ms=None,
        event_confidence=result.event_confidence,
        session_date=session,
    )


def extract_clip_events(
    frames: list[FrameKeypoints],
    *,
    clip_id: UUID | str,
    user_id: UUID | str,
    clip_type: str,
    dominant_hand: str = "right",
    video_fps: float | None = None,
    clip_created_at: str | datetime | None = None,
) -> list[ClipEventRecord]:
    """Run role gates and return per-event records (Phase 10.2)."""
    parsed = parse_frames(frames)
    if not parsed:
        return []

    mean_track = mean_track_confidence(frames)
    session = _session_date(clip_created_at)
    kind = clip_type if isinstance(clip_type, str) else str(clip_type)

    if kind == ClipType.shot.value:
        result = gate_catch_readiness(
            parsed,
            dominant_hand=dominant_hand,
            video_fps=video_fps,
            mean_track_conf=mean_track,
        )
        return [
            ClipEventRecord(
                clip_id=_as_uuid(clip_id),
                user_id=_as_uuid(user_id),
                role_dimension=RoleDimension.catch_readiness,
                event_index=0,
                gate_passed=result.gate_passed,
                rejection_reason=result.rejection_reason,
                signal_values=result.signal_values,
                quality={**result.quality, "clip_type": kind},
                fps=video_fps,
                event_confidence=result.event_confidence,
                session_date=session,
            )
        ]

    if kind == ClipType.drive.value:
        result = gate_rim_pressure(
            parsed,
            video_fps=video_fps,
            mean_track_conf=mean_track,
            burst_window_ms=BURST_WINDOW_MS_DEFAULT,
        )
        return [
            ClipEventRecord(
                clip_id=_as_uuid(clip_id),
                user_id=_as_uuid(user_id),
                role_dimension=RoleDimension.rim_pressure,
                event_index=0,
                gate_passed=result.gate_passed,
                rejection_reason=result.rejection_reason,
                signal_values=result.signal_values,
                quality={**result.quality, "clip_type": kind},
                fps=video_fps,
                burst_window_ms=result.burst_window_ms,
                event_confidence=result.event_confidence,
                session_date=session,
            )
        ]

    if kind == ClipType.pass_clip.value:
        peaks = find_pass_release_peaks(parsed, dominant_hand)
        if not peaks:
            release_idx = find_pass_release_index(parsed, dominant_hand)
            if release_idx is None:
                return [
                    ClipEventRecord(
                        clip_id=_as_uuid(clip_id),
                        user_id=_as_uuid(user_id),
                        role_dimension=RoleDimension.playmaking,
                        event_index=0,
                        gate_passed=False,
                        rejection_reason="no_pass_release",
                        signal_values={},
                        quality={"mean_track_confidence": mean_track, "clip_type": kind},
                        fps=video_fps,
                        event_confidence=None,
                        session_date=session,
                    )
                ]
            peaks = [release_idx]

        return [
            _pass_record(
                clip_id,
                user_id,
                event_index,
                gate_pass_event(
                    parsed,
                    peak_list_index=peak_idx,
                    dominant_hand=dominant_hand,
                    mean_track_conf=mean_track,
                    video_fps=video_fps,
                ),
                kind,
                video_fps,
                session,
            )
            for event_index, peak_idx in enumerate(peaks)
        ]

    return []
