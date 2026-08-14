from __future__ import annotations

import asyncio

from app.config import get_settings
from app.models.clip import ClipStatus, SourceType
from app.services.aggregate import average_features_by_name
from app.services.features.extract import extract_clip_features
from app.services.pose_extraction import extract_pose_keypoints
from app.services.pose_overlay import overlay_storage_path, render_pose_overlay_video
from app.services.supabase_client import SupabaseService

RETRYABLE_STATUSES = {
    ClipStatus.uploaded.value,
    ClipStatus.processing.value,
    ClipStatus.failed.value,
    ClipStatus.done.value,
}


class ClipProcessingError(Exception):
    pass


def _storage_suffix(storage_path: str) -> str:
    if storage_path.lower().endswith(".mov"):
        return ".mov"
    return ".mp4"


async def process_individual_clip(clip_id: str, user_id: str | None = None) -> dict:
    """Download clip, extract pose keypoints, persist rows, update clip status."""
    settings = get_settings()
    supabase = SupabaseService(settings)

    if user_id:
        clip = await supabase.get_clip(clip_id, user_id)
    else:
        clip = await supabase.get_clip_by_id(clip_id)

    if clip is None:
        raise ClipProcessingError("Clip not found")

    if clip["source_type"] != SourceType.individual.value:
        raise ClipProcessingError("Pose extraction is only supported for individual clips")

    if clip["status"] not in RETRYABLE_STATUSES:
        raise ClipProcessingError(f"Clip cannot be processed from status '{clip['status']}'")

    await supabase.update_clip(clip_id, {"status": ClipStatus.processing.value, "error_message": None})

    try:
        video_bytes = await supabase.download_clip_file(clip["storage_path"])
        frames = await asyncio.to_thread(
            extract_pose_keypoints,
            video_bytes,
            suffix=_storage_suffix(clip["storage_path"]),
        )

        if not frames:
            raise ClipProcessingError("No person detected in clip — upload footage with you clearly in frame")

        await supabase.delete_keypoints_for_clip(clip_id)
        await supabase.insert_keypoints(
            [
                {
                    "clip_id": clip_id,
                    "frame_index": frame.frame_index,
                    "keypoints": frame.keypoints,
                    "track_confidence": frame.track_confidence,
                }
                for frame in frames
            ]
        )

        profile = await supabase.get_profile(clip["user_id"])
        dominant_hand = "right"
        height_in = None
        if profile:
            raw_hand = profile.get("dominant_hand")
            if isinstance(raw_hand, str) and raw_hand.strip():
                dominant_hand = raw_hand
            raw_height = profile.get("height_in")
            if isinstance(raw_height, (int, float)):
                height_in = float(raw_height)

        feature_rows = extract_clip_features(
            frames,
            clip["clip_type"],
            dominant_hand=dominant_hand,
            height_in=height_in,
        )
        await supabase.delete_clip_features(clip_id)
        await supabase.insert_clip_features(
            [
                {
                    "clip_id": clip_id,
                    "feature_name": row["feature_name"],
                    "value": row["value"],
                    "meta": row.get("meta") or {},
                }
                for row in feature_rows
            ]
        )

        keypoint_rows = [
            {
                "frame_index": frame.frame_index,
                "keypoints": frame.keypoints,
            }
            for frame in frames
        ]
        try:
            overlay_bytes = await asyncio.to_thread(
                render_pose_overlay_video,
                video_bytes,
                keypoint_rows,
                suffix=_storage_suffix(clip["storage_path"]),
            )
            await supabase.upload_clip_file(
                overlay_storage_path(clip["storage_path"]),
                overlay_bytes,
                "video/mp4",
                upsert=True,
            )
        except Exception:
            # Overlay is nice-to-have; pose + features still succeed.
            pass

        try:
            all_features = await supabase.list_done_clip_features_for_user(clip["user_id"])
            # Include the features we just wrote (clip may still be processing until update below)
            just_written = [
                {
                    "clip_id": clip_id,
                    "feature_name": row["feature_name"],
                    "value": row["value"],
                }
                for row in feature_rows
            ]
            merged = [
                f for f in all_features if str(f.get("clip_id")) != str(clip_id)
            ] + just_written
            aggregated = average_features_by_name(merged)
            await supabase.replace_user_profile_agg(clip["user_id"], aggregated)
        except Exception:
            # Aggregation failure should not fail the clip once features exist.
            pass

        updated = await supabase.update_clip(
            clip_id,
            {"status": ClipStatus.done.value, "error_message": None},
        )
        return {
            "clip": updated,
            "frame_count": len(frames),
            "feature_count": len(feature_rows),
        }
    except Exception as exc:
        message = str(exc) if str(exc) else exc.__class__.__name__
        await supabase.update_clip(
            clip_id,
            {"status": ClipStatus.failed.value, "error_message": message[:500]},
        )
        raise ClipProcessingError(message) from exc
