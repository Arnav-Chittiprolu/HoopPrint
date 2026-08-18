import { FEATURE_BAR_MAX, featureLabel, formatFeatureValue } from "@/lib/features";

export function FeatureBar({
  name,
  value,
  hint,
}: {
  name: string;
  value: number;
  hint?: string;
}) {
  const max = FEATURE_BAR_MAX[name] ?? Math.max(1, Math.abs(value) * 1.2);
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-xs">
        <span className="text-zinc-700">{featureLabel(name)}</span>
        <span className="tabular-nums text-zinc-900">{formatFeatureValue(name, value)}</span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-zinc-100">
        <div
          className="h-full rounded-full bg-orange-600 transition-[width] duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      {hint ? <p className="mt-0.5 text-[11px] text-zinc-500">{hint}</p> : null}
    </div>
  );
}

export function SlotCompareBar({
  label,
  user,
  nba,
}: {
  label: string;
  user: number;
  nba: number;
}) {
  const max = 1;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-xs text-zinc-600">
        <span className="text-zinc-800">{label}</span>
        <span className="tabular-nums">
          you {user.toFixed(2)} · them {nba.toFixed(2)}
        </span>
      </div>
      <div className="mt-1 space-y-1">
        <div className="h-1.5 overflow-hidden rounded-full bg-zinc-100">
          <div
            className="h-full rounded-full bg-orange-600"
            style={{ width: `${Math.max(0, Math.min(100, (user / max) * 100))}%` }}
          />
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-zinc-100">
          <div
            className="h-full rounded-full bg-zinc-500"
            style={{ width: `${Math.max(0, Math.min(100, (nba / max) * 100))}%` }}
          />
        </div>
      </div>
    </div>
  );
}

export function HistorySparkline({
  values,
  label,
}: {
  values: number[];
  label: string;
}) {
  if (values.length < 2) return null;
  const width = 220;
  const height = 48;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * (width - 8) + 4;
    const y = height - 6 - ((value - min) / span) * (height - 12);
    return `${x},${y}`;
  });
  return (
    <div>
      <p className="text-xs font-medium text-zinc-800">{label}</p>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mt-1 h-12 w-full text-orange-700"
        role="img"
        aria-label={`${label} over ${values.length} clips`}
      >
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          points={points.join(" ")}
        />
      </svg>
    </div>
  );
}
