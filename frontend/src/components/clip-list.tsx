"use client";

import { useEffect, useState } from "react";
import {
  getClipOverlayUrl,
  listClips,
  processClip,
  type Clip,
  type ClipStatus,
} from "@/lib/api";

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

function canRetry(clip: Clip) {
  return (
    clip.source_type === "individual" &&
    (clip.status === "processing" ||
      clip.status === "failed" ||
      clip.status === "uploaded" ||
      clip.status === "done")
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
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not refresh clips");
        }
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
    try {
      await processClip(clipId);
      setClips((current) =>
        current.map((clip) =>
          clip.id === clipId
            ? { ...clip, status: "processing", error_message: null }
            : clip,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setRetryingId(null);
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
        <p className="mb-3 text-xs text-zinc-500">Pose extraction in progress… this can take a minute.</p>
      ) : null}
      <ul className="divide-y divide-zinc-100">
        {clips.map((clip) => (
          <li key={clip.id} className="py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium capitalize text-zinc-900">
                  {clip.clip_type} · {clip.source_type}
                </p>
                <p className="text-xs text-zinc-500">{formatDate(clip.created_at)}</p>
                {clip.status === "failed" && clip.error_message ? (
                  <p className="mt-1 text-xs text-red-600">{clip.error_message}</p>
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
            {clip.status === "done" ? <PoseOverlayPlayer clipId={clip.id} /> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
