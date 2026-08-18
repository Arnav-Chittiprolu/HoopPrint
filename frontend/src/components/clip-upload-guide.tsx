import type { Clip, ClipType } from "@/lib/api";
import { QUALITY_TARGET } from "@/components/clip-progress";

const TYPES: Array<{
  type: ClipType;
  label: string;
  what: string;
}> = [
  {
    type: "shot",
    label: "Shot",
    what: "Catch-and-shoot or a pull-up. Form shooting is mechanics only.",
  },
  {
    type: "pass",
    label: "Pass",
    what: "A clear pass-like arm release.",
  },
  {
    type: "drive",
    label: "Drive",
    what: "A first-step burst toward the rim, not a walk.",
  },
];

function countByType(clips: Clip[]): Record<ClipType, number> {
  const counts: Record<ClipType, number> = { shot: 0, pass: 0, drive: 0 };
  for (const clip of clips) {
    if (clip.status === "failed") continue;
    counts[clip.clip_type] += 1;
  }
  return counts;
}

export function ClipUploadGuide({ clips }: { clips: Clip[] }) {
  const counts = countByType(clips);
  const total = TYPES.reduce((sum, { type }) => sum + counts[type], 0);
  const remaining = Math.max(0, QUALITY_TARGET - total);

  let overall: string;
  if (total >= QUALITY_TARGET) {
    overall =
      "You have about enough clips for a named NBA role example if they pass the action check.";
  } else if (total > 0) {
    overall = `${remaining} more quality-checked clip${remaining === 1 ? "" : "s"} unlocks a named comparison. Mix shot, pass, and drive.`;
  } else {
    overall = `${QUALITY_TARGET} usable clips unlocks Established. Mixing types is stronger, but five of one type also works.`;
  }

  return (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50 px-3 py-3">
      <p className="text-xs font-medium text-zinc-800">What to post</p>
      <p className="mt-1 text-xs leading-5 text-zinc-600">{overall}</p>
      <ul className="mt-3 space-y-2">
        {TYPES.map(({ type, label, what }) => (
          <li key={type} className="text-xs text-zinc-700">
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-medium">{label}</span>
              <span className="tabular-nums text-zinc-500">{counts[type]}</span>
            </div>
            <p className="mt-0.5 text-zinc-500">{what}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
