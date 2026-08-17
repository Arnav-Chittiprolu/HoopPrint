"use client";

import { useEffect, useState } from "react";
import {
  getClipOverlayUrl,
  listClipFeatures,
  listClips,
  processClip,
  updateClipType,
  type Clip,
  type ClipFeature,
  type ClipStatus,
  type ClipType,
} from "@/lib/api";
import { BboxPicker } from "@/components/bbox-picker";
import { FeatureBar } from "@/components/feature-bars";

const STATUS_LABELS: Record<ClipStatus, string> = {
  uploaded: "Uploaded",
  awaiting_bbox: "Awaiting player box",
  processing: "Processing",
  done: "Done",
  failed: "Failed",
};

const STATUS_COLORS: Record<ClipStatus, string> = {
  uploaded: "bg-blue-50 text-blue-700",
  awaiting_bbox: "bg-amber-50 text-amber-700",
  processing: "bg-violet-50 text-violet-700",
  done: "bg-emerald-50 text-emerald-700",
  failed: "bg-red-50 text-red-700",
};

const POLL_MS = 2500;

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function trackingHint(message: string | null): string | null {
  if (!message) return null;
  const lower = message.toLowerCase();
  if (
    lower.includes("box") ||
    lower.includes("track") ||
    lower.includes("person detected") ||
    lower.includes("no person")
  ) {
    return "Redraw a tighter box around yourself on the first frame, then Retry.";
  }
  return null;
}

function ClipFeatureBars({ clipId }: { clipId: string }) {
  const [rows, setRows] = useState<ClipFeature[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const next = await listClipFeatures(clipId);
        if (!cancelled) setRows(next);
      } catch {
        if (!cancelled) setRows([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clipId]);

  if (!rows?.length) return null;
  return (
    <div className="mt-3 space-y-2 rounded-md border border-zinc-100 bg-zinc-50 px-3 py-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">
        This clip
      </p>
      {rows.map((row) => (
        <FeatureBar key={row.id} name={row.feature_name} value={row.value} />
      ))}
    </div>
  );
}

function canRetry(clip: Clip) {
  return (
    clip.status === "processing" ||
    clip.status === "failed" ||
    clip.status === "done" ||
    (clip.source_type === "individual" && clip.status === "uploaded")
  );
}

function PoseOverlayPlayer({ clipId }: { clipId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const next = await getClipOverlayUrl(clipId);
        if (!cancelled) setUrl(next);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load pose video");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clipId]);

  if (loading) {
    return <p className="mt-3 text-xs text-zinc-500">Loading pose overlay…</p>;
  }
  if (error) {
    return <p className="mt-3 text-xs text-amber-700">{error}</p>;
  }
  if (!url) {
    return (
      <p className="mt-3 text-xs text-zinc-500">
        Pose overlay not ready yet — click Process to regenerate.
      </p>
    );
  }

  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-zinc-200 bg-black">
      <video
        key={url}
        controls
        playsInline
        className="max-h-80 w-full bg-black"
        src={url}
      >
        Your browser does not support video playback.
      </video>
      <p className="bg-zinc-950 px-3 py-2 text-xs text-zinc-400">
        MediaPipe skeleton overlay (green lines / cyan joints)
      </p>
    </div>
  );
}

export function ClipList({ clips: initialClips }: { clips: Clip[] }) {
  const [clips, setClips] = useState(initialClips);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setClips(initialClips);
  }, [initialClips]);

  const hasActive = clips.some(
    (clip) =>
      clip.status === "processing" ||
      (clip.source_type === "individual" && clip.status === "uploaded"),
  );

  useEffect(() => {
    if (!hasActive) return;

    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const next = await listClips();
        if (!cancelled) {
          setClips(next);
          setError(null);
        }
      } catch {
        // Pose can stall a poll; keep showing Processing instead of a timeout banner.
      }
    }, POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [hasActive]);

  async function onRetry(clipId: string) {
    setRetryingId(clipId);
    setError(null);
    setClips((current) =>
      current.map((clip) =>
        clip.id === clipId
          ? { ...clip, status: "processing", error_message: null }
          : clip,
      ),
    );
    try {
      await processClip(clipId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setRetryingId(null);
    }
  }

  async function onChangeType(clipId: string, clipType: ClipType) {
    setError(null);
    const previous = clips.find((clip) => clip.id === clipId)?.clip_type;
    setClips((current) =>
      current.map((clip) => (clip.id === clipId ? { ...clip, clip_type: clipType } : clip)),
    );
    try {
      await updateClipType(clipId, clipType);
    } catch (err) {
      if (previous) {
        setClips((current) =>
          current.map((clip) =>
            clip.id === clipId ? { ...clip, clip_type: previous } : clip,
          ),
        );
      }
      setError(err instanceof Error ? err.message : "Could not change clip type");
    }
  }

  if (clips.length === 0) {
    return (
      <p className="text-sm text-zinc-500">No clips yet. Upload your first clip above.</p>
    );
  }

  return (
    <div>
      {error ? (
        <p className="mb-3 text-sm text-amber-700" role="alert">
          {error}
        </p>
      ) : null}
      {hasActive ? (
        <p className="mb-3 text-xs text-zinc-500">
          Pose extraction in progress… 4K clips can take a couple of minutes.
        </p>
      ) : null}
      <ul className="divide-y divide-zinc-100">
        {clips.map((clip) => (
          <li key={clip.id} className="py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium capitalize text-zinc-900">
                  <label className="inline-flex items-center gap-1">
                    <span className="sr-only">Clip type</span>
                    <select
                      value={clip.clip_type}
                      onChange={(event) =>
                        onChangeType(clip.id, event.target.value as ClipType)
                      }
                      className="rounded-md border border-zinc-200 bg-white px-1.5 py-0.5 text-sm font-medium capitalize text-zinc-900 outline-none ring-orange-600 focus:ring-2"
                    >
                      <option value="shot">shot</option>
                      <option value="pass">pass</option>
                      <option value="drive">drive</option>
                    </select>
                    <span className="text-zinc-400">·</span>
                    <span>{clip.source_type}</span>
                  </label>
                </p>
                <p className="text-xs text-zinc-500">{formatDate(clip.created_at)}</p>
                {clip.status === "failed" && clip.error_message ? (
                  <div className="mt-1 space-y-0.5">
                    <p className="text-xs text-red-600">{clip.error_message}</p>
                    {trackingHint(clip.error_message) ? (
                      <p className="text-xs text-amber-700">{trackingHint(clip.error_message)}</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                {canRetry(clip) ? (
                  <button
                    type="button"
                    onClick={() => onRetry(clip.id)}
                    disabled={retryingId === clip.id}
                    className="rounded-md border border-zinc-200 px-2.5 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
                  >
                    {retryingId === clip.id
                      ? "Starting…"
                      : clip.status === "processing"
                        ? "Retry"
                        : clip.status === "done"
                          ? "Reprocess"
                          : "Process"}
                  </button>
                ) : null}
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_COLORS[clip.status]}`}
                >
                  {STATUS_LABELS[clip.status]}
                </span>
              </div>
            </div>
            {clip.status === "awaiting_bbox" && clip.source_type === "gameplay" ? (
              <BboxPicker
                clipId={clip.id}
                onSaved={() => {
                  setClips((current) =>
                    current.map((item) =>
                      item.id === clip.id
                        ? { ...item, status: "processing", error_message: null }
                        : item,
                    ),
                  );
                }}
              />
            ) : null}
            {clip.status === "done" ? (
              <>
                <PoseOverlayPlayer clipId={clip.id} />
                <ClipFeatureBars clipId={clip.id} />
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
