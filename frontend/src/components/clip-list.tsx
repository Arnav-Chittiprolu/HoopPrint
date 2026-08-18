"use client";

import { useEffect, useState } from "react";
import {
  deleteAllClips,
  deleteClip,
  getClipOverlayUrl,
  listClipEvents,
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
  awaiting_bbox: "Needs box",
  processing: "Processing",
  done: "Processed",
  failed: "Error",
};

const STATUS_COLORS: Record<ClipStatus, string> = {
  uploaded: "bg-sky-50 text-sky-800",
  awaiting_bbox: "bg-amber-50 text-amber-800",
  processing: "bg-sky-50 text-sky-800",
  done: "bg-emerald-50 text-emerald-800",
  failed: "bg-red-50 text-red-700",
};

const TYPE_CHIP: Record<ClipType, string> = {
  shot: "bg-orange-50 text-orange-800",
  pass: "bg-zinc-100 text-zinc-700",
  drive: "bg-orange-50 text-orange-800",
};

function clipFileName(clip: Clip) {
  return `${clip.clip_type}-${clip.id.slice(0, 8)}.mp4`;
}

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

function roleEventHint(reason: string | null): string {
  switch (reason) {
    case "catch_timing_out_of_range":
      return "Need a visible catch, then a shot — or a pull-up off the bounce.";
    case "no_catch_proxy":
    case "form_shot":
      return "Didn’t see a catch or a jumper off the bounce. Start the box before the gather, then Reprocess — form shooting still isn’t used for NBA comparison.";
    case "sparse_track":
      return "We only locked onto you for a couple of frames. Draw a tighter full-body box a second before the pass, keep yourself in frame after, then Reprocess.";
    case "insufficient_pre_post_window":
      return "Start the box before the move and stay in frame after it — tracking started too close to the action.";
    case "no_drive_onset":
    case "insufficient_hip_displacement":
      return "Need a clear first-step burst toward the rim.";
    case "no_pass_release":
      return "Didn’t catch a clear throwing motion. Draw a larger full-body box so your arms stay in the box, then Reprocess.";
    default:
      return reason ? `Not used for NBA comparison (${reason.replaceAll("_", " ")}).` : "Not used for NBA comparison.";
  }
}

function ClipRoleStatus({ clipId, status }: { clipId: string; status: ClipStatus }) {
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    if (status !== "done") return;
    let cancelled = false;
    (async () => {
      try {
        const events = await listClipEvents(clipId);
        if (cancelled) return;
        const passed = events.find((event) => event.gate_passed);
        if (passed) {
          setLabel("Counted toward NBA comparison");
          return;
        }
        const failed = events.find((event) => !event.gate_passed);
        setLabel(roleEventHint(failed?.rejection_reason ?? null));
      } catch {
        if (!cancelled) setLabel(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clipId, status]);

  if (!label) return null;
  const counted = label.startsWith("Counted");
  return (
    <p className={`mt-1 text-xs ${counted ? "text-emerald-700" : "text-amber-700"}`}>{label}</p>
  );
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
  const [deletingAll, setDeletingAll] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

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

  async function onDeleteAll() {
    const ok = window.confirm(
      "Permanently delete all of your clips? This also clears pose data, clip events, and resets your mechanics and playing-style profile. Comp history is kept.",
    );
    if (!ok) return;
    setDeletingAll(true);
    setError(null);
    try {
      await deleteAllClips();
      setClips([]);
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete clips");
      setDeletingAll(false);
    }
  }

  async function onDeleteOne(clipId: string) {
    const ok = window.confirm(
      "Delete this clip? Pose data and NBA comparison events from it will be removed. Comp history is kept.",
    );
    if (!ok) return;
    setDeletingId(clipId);
    setError(null);
    try {
      await deleteClip(clipId);
      setClips((current) => current.filter((clip) => clip.id !== clipId));
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete clip");
      setDeletingId(null);
    }
  }

  if (clips.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500">No clips yet. Drop your first clip in the middle column.</p>
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
      <div className="mb-2 flex justify-end">
        <button
          type="button"
          onClick={() => void onDeleteAll()}
          disabled={deletingAll}
          className="text-xs font-medium text-zinc-500 transition-colors duration-200 hover:text-red-700 disabled:opacity-60"
        >
          {deletingAll ? "Removing…" : "Remove all"}
        </button>
      </div>
      <ul className="divide-y divide-zinc-100">
        {clips.map((clip) => {
          const open = expandedId === clip.id;
          return (
            <li key={clip.id} className="py-2.5">
              <button
                type="button"
                onClick={() => setExpandedId(open ? null : clip.id)}
                className="flex w-full items-start justify-between gap-3 text-left"
                aria-expanded={open}
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium capitalize ${TYPE_CHIP[clip.clip_type]}`}
                    >
                      {clip.clip_type}
                    </span>
                    <span className="truncate text-sm font-medium text-zinc-900">
                      {clipFileName(clip)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-zinc-500">
                    {formatDate(clip.created_at)} · {clip.source_type}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_COLORS[clip.status]}`}
                >
                  {STATUS_LABELS[clip.status]}
                </span>
              </button>
              {open ? (
                <div className="mt-3 space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="inline-flex items-center gap-1.5 text-xs text-zinc-600">
                      Type
                      <select
                        value={clip.clip_type}
                        onChange={(event) =>
                          onChangeType(clip.id, event.target.value as ClipType)
                        }
                        className="rounded-md border border-zinc-200 bg-white px-1.5 py-1 text-xs font-medium capitalize text-zinc-900 outline-none ring-orange-600 focus:ring-2"
                      >
                        <option value="shot">shot</option>
                        <option value="pass">pass</option>
                        <option value="drive">drive</option>
                      </select>
                    </label>
                    {canRetry(clip) ? (
                      <button
                        type="button"
                        onClick={() => onRetry(clip.id)}
                        disabled={retryingId === clip.id || deletingId === clip.id}
                        className="rounded-md border border-zinc-200 px-2.5 py-1 text-xs font-medium text-zinc-700 transition-colors duration-200 hover:bg-zinc-50 disabled:opacity-60"
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
                    <button
                      type="button"
                      onClick={() => void onDeleteOne(clip.id)}
                      disabled={deletingId === clip.id || deletingAll}
                      className="rounded-md border border-zinc-200 px-2.5 py-1 text-xs font-medium text-red-700 transition-colors duration-200 hover:bg-red-50 disabled:opacity-60"
                    >
                      {deletingId === clip.id ? "Deleting…" : "Delete"}
                    </button>
                  </div>
                  <ClipRoleStatus clipId={clip.id} status={clip.status} />
                  {clip.status === "failed" && clip.error_message ? (
                    <div className="space-y-0.5">
                      <p className="text-xs text-red-600">{clip.error_message}</p>
                      {trackingHint(clip.error_message) ? (
                        <p className="text-xs text-amber-700">{trackingHint(clip.error_message)}</p>
                      ) : null}
                    </div>
                  ) : null}
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
                  {clip.status === "failed" && clip.source_type === "gameplay" ? (
                    <div>
                      <p className="text-xs text-amber-800">
                        Tracking missed you. Draw a larger full-body box on a second where you
                        are clearly visible, then save.
                      </p>
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
                    </div>
                  ) : null}
                  {clip.status === "done" ? (
                    <>
                      <PoseOverlayPlayer clipId={clip.id} />
                      <ClipFeatureBars clipId={clip.id} />
                    </>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
