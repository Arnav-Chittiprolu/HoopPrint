"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getMyHistory,
  getMyProfile,
  type AggregatedFeature,
  type HistoryPoint,
} from "@/lib/api";
import { featureLabel, formatFeatureValue } from "@/lib/features";
import { FeatureBar, HistorySparkline } from "@/components/feature-bars";

export function MechanicsPanel() {
  const [agg, setAgg] = useState<AggregatedFeature[]>([]);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [profile, points] = await Promise.all([getMyProfile(), getMyHistory()]);
        if (cancelled) return;
        setAgg(profile.aggregated_features);
        setHistory(points);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load mechanics");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    const onFocus = () => {
      void load();
    };
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  const series = useMemo(() => {
    const byName = new Map<string, HistoryPoint[]>();
    for (const point of history) {
      const list = byName.get(point.feature_name) ?? [];
      list.push(point);
      byName.set(point.feature_name, list);
    }
    return [...byName.entries()].map(([name, points]) => ({
      name,
      points: points.slice().sort((a, b) => a.created_at.localeCompare(b.created_at)),
    }));
  }, [history]);

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="text-lg font-medium text-zinc-900">Mechanics</h2>
      <p className="mt-1 text-sm text-zinc-600">
        Pose measurements from your clips — release posture, elbow configuration, relative
        release height, wrist-rise proxy, and body-relative burst. Not used for NBA matching.
      </p>

      {loading ? <p className="mt-4 text-sm text-zinc-500">Loading mechanics…</p> : null}
      {error ? (
        <p className="mt-4 text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}

      {!loading && agg.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-600">
          Process a shot, pass, or drive clip to fill this card.
        </p>
      ) : null}

      {agg.length > 0 ? (
        <div className="mt-4 space-y-3">
          {agg.map((row) => (
            <FeatureBar
              key={row.feature_name}
              name={row.feature_name}
              value={row.value}
              hint={`${row.clip_count} clip${row.clip_count === 1 ? "" : "s"}`}
            />
          ))}
        </div>
      ) : null}

      {series.some((item) => item.points.length >= 2) ? (
        <div className="mt-6 border-t border-zinc-100 pt-4">
          <h3 className="text-sm font-medium text-zinc-800">History</h3>
          <p className="mt-1 text-xs text-zinc-500">How each mechanic changed as you added clips.</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            {series
              .filter((item) => item.points.length >= 2)
              .map((item) => (
                <HistorySparkline
                  key={item.name}
                  label={featureLabel(item.name)}
                  values={item.points.map((point) => point.value)}
                />
              ))}
          </div>
        </div>
      ) : history.length > 0 ? (
        <div className="mt-6 border-t border-zinc-100 pt-4">
          <h3 className="text-sm font-medium text-zinc-800">History</h3>
          <ul className="mt-2 space-y-1 text-xs text-zinc-600">
            {history
              .slice()
              .sort((a, b) => b.created_at.localeCompare(a.created_at))
              .slice(0, 8)
              .map((point) => (
                <li key={`${point.clip_id}-${point.feature_name}`}>
                  {featureLabel(point.feature_name)} · {formatFeatureValue(point.feature_name, point.value)}{" "}
                  · {point.clip_type}
                </li>
              ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
