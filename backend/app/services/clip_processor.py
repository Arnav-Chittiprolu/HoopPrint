from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from app.config import get_settings
from app.models.clip import ClipStatus, SourceType
from app.services.aggregate import average_features_by_name
from app.services.features.extract import extract_clip_features
from app.services.pose_job import extract_pose_isolated
from app.services.pose_overlay import overlay_storage_path, prepare_working_video, render_pose_overlay_video
from app.services.supabase_client import SupabaseService
from app.services.track import NormBox

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = {
    ClipStatus.uploaded.value,
    ClipStatus.awaiting_bbox.value,
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
    """Back-compat alias used by the CLI and existing callers."""
    return await process_clip(clip_id, user_id)


async def process_clip(clip_id: str, user_id: str | None = None) -> dict:
    """Download clip, extract pose (full-frame or tracked crop), persist, mark done."""
    settings = get_settings()
    supabase = SupabaseService(settings)

    if user_id:
        clip = await supabase.get_clip(clip_id, user_id)
    else:
        clip = await supabase.get_clip_by_id(clip_id)

    if clip is None:
        raise ClipProcessingError("Clip not found")

    source = clip["source_type"]
    if source not in {SourceType.individual.value, SourceType.gameplay.value}:
        raise ClipProcessingError(f"Unsupported source_type '{source}'")

    if clip["status"] not in RETRYABLE_STATUSES:
        raise ClipProcessingError(f"Clip cannot be processed from status '{clip['status']}'")

    bbox: NormBox | None = None
    if source == SourceType.gameplay.value:
        box_row = await supabase.get_player_box(clip_id)
        if box_row is None:
            raise ClipProcessingError("Draw a player box on the first frame before processing")
        bbox = NormBox(
            x=float(box_row["x"]),
            y=float(box_row["y"]),
            w=float(box_row["w"]),
            h=float(box_row["h"]),
        )

    await supabase.update_clip(clip_id, {"status": ClipStatus.processing.value, "error_message": None})

    tmp_path: str | None = None
    try:
        video_bytes = await supabase.download_clip_file(clip["storage_path"])
        suffix = _storage_suffix(clip["storage_path"])
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name
        del video_bytes

        work_path = prepare_working_video(tmp_path)
        bbox_tuple = None if bbox is None else (bbox.x, bbox.y, bbox.w, bbox.h)
        frames = await extract_pose_isolated(
            work_path,
            source=source,
            suffix=suffix,
            bbox=bbox_tuple,
        )

        if not frames:
            raise ClipProcessingError(
                "No person detected in clip — upload footage with you clearly in frame"
                + (" and keep the box on yourself" if source == SourceType.gameplay.value else "")
            )

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
                work_path,
                keypoint_rows,
            )
            await supabase.upload_clip_file(
                overlay_storage_path(clip["storage_path"]),
                overlay_bytes,
                "video/mp4",
                upsert=True,
            )
        except Exception:
            pass

        try:
            all_features = await supabase.list_done_clip_features_for_user(clip["user_id"])
            just_written = [
                {
                    "clip_id": clip_id,
                    "feature_name": row["feature_name"],
                    "value": row["value"],
                }
                for row in feature_rows
            ]
            merged = [f for f in all_features if str(f.get("clip_id")) != str(clip_id)] + just_written
            aggregated = average_features_by_name(merged)
            await supabase.replace_user_profile_agg(clip["user_id"], aggregated)
        except Exception:
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
        logger.warning(
            "clip_pipeline_failed",
            extra={
                "event": "clip_pipeline_failed",
                "clip_id": clip_id,
                "user_id": clip.get("user_id") if clip else user_id,
                "reason": message[:500],
            },
        )
        await supabase.update_clip(
            clip_id,
            {"status": ClipStatus.failed.value, "error_message": message[:500]},
        )
        raise ClipProcessingError(message) from exc
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
            work = Path(tmp_path).with_name(Path(tmp_path).stem + ".work.mp4")
            work.unlink(missing_ok=True)
