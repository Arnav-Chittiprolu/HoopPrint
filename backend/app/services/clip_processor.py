from __future__ import annotations

from app.config import Settings, get_settings
from app.models.clip import ClipStatus, SourceType
from app.services.pose_extraction import extract_pose_keypoints
from app.services.supabase_client import SupabaseService


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

    if clip["status"] not in {ClipStatus.uploaded.value, ClipStatus.failed.value}:
        raise ClipProcessingError(f"Clip cannot be processed from status '{clip['status']}'")

    await supabase.update_clip(clip_id, {"status": ClipStatus.processing.value, "error_message": None})

    try:
        video_bytes = await supabase.download_clip_file(clip["storage_path"])
        frames = extract_pose_keypoints(
            video_bytes,
            suffix=_storage_suffix(clip["storage_path"]),
        )

        if not frames:
            raise ClipProcessingError("No pose detected in clip")

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
        updated = await supabase.update_clip(
            clip_id,
            {"status": ClipStatus.done.value, "error_message": None},
        )
        return {
            "clip": updated,
            "frame_count": len(frames),
        }
    except Exception as exc:
        message = str(exc) if str(exc) else exc.__class__.__name__
        await supabase.update_clip(
            clip_id,
            {"status": ClipStatus.failed.value, "error_message": message[:500]},
        )
        raise ClipProcessingError(message) from exc
