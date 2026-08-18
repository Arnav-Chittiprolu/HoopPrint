import type { Clip } from "@/lib/api";

export const QUALITY_TARGET = 5;

export function qualityCheckedCount(clips: Clip[]): number {
  return clips.filter((clip) => clip.status === "done").length;
}

export function ClipProgress({ clips }: { clips: Clip[] }) {
  const done = qualityCheckedCount(clips);
  const pct = Math.min(100, Math.round((done / QUALITY_TARGET) * 100));
  const ready = done >= QUALITY_TARGET;

  return (
    <div className="hp-card px-5 py-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-zinc-900">
            {done} of {QUALITY_TARGET} quality-checked clips
          </p>
          <p className="mt-0.5 text-xs text-zinc-500">
            {ready
              ? "Enough evidence for a named NBA role example, if those clips passed the action check."
              : `${QUALITY_TARGET - done} more processed clip${QUALITY_TARGET - done === 1 ? "" : "s"} unlocks Established.`}
          </p>
        </div>
        <p className="text-xs font-medium tabular-nums text-zinc-500">{pct}%</p>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-zinc-100">
        <div
          className={`h-full rounded-full transition-[width] duration-300 ${ready ? "bg-emerald-600" : "bg-orange-700"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
