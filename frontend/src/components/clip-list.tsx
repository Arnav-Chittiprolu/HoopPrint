import type { Clip, ClipStatus } from "@/lib/api";

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

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function ClipList({ clips }: { clips: Clip[] }) {
  if (clips.length === 0) {
    return (
      <p className="text-sm text-zinc-500">No clips yet. Upload your first clip above.</p>
    );
  }

  return (
    <ul className="divide-y divide-zinc-100">
      {clips.map((clip) => (
        <li key={clip.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div>
            <p className="text-sm font-medium capitalize text-zinc-900">
              {clip.clip_type} · {clip.source_type}
            </p>
            <p className="text-xs text-zinc-500">{formatDate(clip.created_at)}</p>
          </div>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_COLORS[clip.status]}`}
          >
            {STATUS_LABELS[clip.status]}
          </span>
        </li>
      ))}
    </ul>
  );
}
