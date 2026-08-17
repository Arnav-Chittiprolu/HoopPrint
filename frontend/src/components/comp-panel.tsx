"use client";

import { useEffect, useState, useTransition } from "react";
import {
  getMyComp,
  runMyComp,
  type CompMatch,
  type CompResult,
  type Recommendation,
} from "@/lib/api";
import { STYLE_LABELS, formatHeightIn } from "@/lib/features";
import { SlotCompareBar } from "@/components/feature-bars";

function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score * 100));
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-zinc-100">
        <div className="h-full rounded-full bg-orange-600" style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular-nums text-sm font-medium text-zinc-900">{pct.toFixed(1)}%</span>
    </div>
  );
}

function MatchCard({ match, featured }: { match: CompMatch; featured?: boolean }) {
  const why = match.why;
  return (
    <article
      className={`rounded-lg border p-4 ${
        featured ? "border-orange-200 bg-orange-50/40" : "border-zinc-200 bg-zinc-50/50"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-base font-semibold text-zinc-900">{match.name}</p>
          <p className="mt-0.5 text-xs text-zinc-500">
            {match.position ?? "NBA"}
            {match.height_in != null ? ` · ${formatHeightIn(match.height_in)}` : ""}
            {match.season ? ` · ${match.season}` : ""}
            {featured ? " · overall style" : ""}
          </p>
        </div>
        <ScoreBar score={match.score} />
      </div>

      {featured && why ? (
        <div className="mt-4 space-y-3">
          <div>
            <h3 className="text-sm font-medium text-zinc-800">Why this match</h3>
            <p className="mt-1 text-xs text-zinc-500">
              {why.note ?? "Style similarity — not identical motion, not joint-angle matching."}
            </p>
            {why.filter ? (
              <p className="mt-2 text-sm text-zinc-700">
                Same position ({why.filter.position}) and height within ±{why.filter.band_in}"
                {why.filter.user_height_in != null && why.filter.nba_height_in != null
                  ? ` (you ${formatHeightIn(why.filter.user_height_in)}, them ${formatHeightIn(why.filter.nba_height_in)})`
                  : ""}
                .
              </p>
            ) : null}
            {why.score_terms ? (
              <p className="mt-1 font-mono text-[11px] text-zinc-500">
                cosine {why.score_terms.cosine ?? "—"} · size {why.score_terms.size_similarity ?? "—"} ·
                skill {why.score_terms.primary_skill_bonus ?? "—"}
              </p>
            ) : null}
          </div>
          {why.slots?.length ? (
            <div className="space-y-2">
              {why.slots.map((slot) => (
                <SlotCompareBar
                  key={slot.dim}
                  label={STYLE_LABELS[slot.dim] ?? slot.dim}
                  user={slot.user}
                  nba={slot.nba}
                />
              ))}
              <p className="text-[11px] text-zinc-500">Orange = you · gray = {match.name}</p>
            </div>
          ) : null}
          {why.omitted_slots?.length ? (
            <p className="text-xs text-zinc-500">
              Omitted (no clip evidence): {why.omitted_slots.map((s) => STYLE_LABELS[s] ?? s).join(", ")}
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function RecsBlock({ recs }: { recs: Recommendation[] }) {
  if (!recs.length) return null;
  return (
    <div>
      <h3 className="text-sm font-medium text-zinc-800">Personalized next steps</h3>
      <ol className="mt-2 list-decimal space-y-3 pl-5 text-sm text-zinc-800">
        {recs.map((rec, index) => (
          <li key={`${rec.target}-${index}`}>
            <p className="font-medium">{rec.action}</p>
            <p className="mt-0.5 text-xs text-zinc-500">{rec.because}</p>
            {rec.current_value != null || rec.reference != null ? (
              <p className="mt-1 font-mono text-[11px] text-zinc-500">
                {rec.target}
                {rec.current_value != null ? ` · you ${rec.current_value.toFixed(2)}` : ""}
                {rec.reference != null ? ` · ref ${rec.reference.toFixed(2)}` : ""}
                {rec.clip_count != null ? ` · n=${rec.clip_count}` : ""}
              </p>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}

function SummaryBlock({ summary }: { summary: string | null }) {
  if (!summary) return null;
  return (
    <div>
      <h3 className="text-sm font-medium text-zinc-800">Writeup</h3>
      <pre className="mt-2 whitespace-pre-wrap font-sans text-sm leading-6 text-zinc-700">
        {summary}
      </pre>
    </div>
  );
}

function CategoryList({ title, matches }: { title: string; matches: CompMatch[] }) {
  if (!matches.length) return null;
  return (
    <div>
      <h3 className="text-sm font-medium text-zinc-800">{title}</h3>
      <ul className="mt-2 space-y-2">
        {matches.map((match) => (
          <li key={`${title}-${match.player_id ?? match.name}`}>
            <MatchCard match={match} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CompPanel({ profileReady }: { profileReady: boolean }) {
  const [comp, setComp] = useState<CompResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const latest = await getMyComp();
        if (!cancelled) {
          setComp(latest);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Could not load comp";
          if (!/no comp/i.test(message)) {
            setError(message);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function onRun() {
    setError(null);
    startTransition(async () => {
      try {
        const result = await runMyComp();
        setComp(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Comp failed");
      }
    });
  }

  const top = comp?.overall[0];

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="text-lg font-medium text-zinc-900">NBA style comps</h2>
      <p className="mt-1 text-sm text-zinc-600">
        Cosine in style space (size, shot mix, creation, drive, passing) against the seeded roster,
        filtered by your position and height. Not identical motion.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onRun}
          disabled={pending || !profileReady}
          className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {pending ? "Matching…" : comp ? "Re-run style comp" : "Run style comp"}
        </button>
        {!profileReady ? (
          <p className="text-xs text-amber-700">Save height and position in Your profile first.</p>
        ) : (
          <p className="text-xs text-zinc-500">
            Why + recs are computed from your numbers. Gemini only narrates them if a key is set.
          </p>
        )}
      </div>

      {loading ? <p className="mt-4 text-sm text-zinc-500">Loading…</p> : null}
      {error ? (
        <p className="mt-4 text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}

      {comp ? (
        <div className="mt-5 space-y-5 border-t border-zinc-100 pt-5">
          <p className="text-xs uppercase tracking-wide text-zinc-500">
            Style card · {comp.season} · pool {comp.pool_size}
            {comp.height_z_nba != null ? ` · height_z_nba ${comp.height_z_nba.toFixed(2)}` : ""}
          </p>
          {top ? <MatchCard match={top} featured /> : null}
          {comp.overall.slice(1).length ? (
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-zinc-800">Also close</h3>
              {comp.overall.slice(1).map((match) => (
                <MatchCard key={match.player_id ?? match.name} match={match} />
              ))}
            </div>
          ) : null}
          {comp.by_category.shot ? (
            <CategoryList title="Jumper style" matches={comp.by_category.shot} />
          ) : null}
          {comp.by_category.pass ? (
            <CategoryList title="Passing style" matches={comp.by_category.pass} />
          ) : null}
          {comp.by_category.drive ? (
            <CategoryList title="Drive style" matches={comp.by_category.drive} />
          ) : null}
          <RecsBlock recs={comp.recommendations ?? []} />
          <SummaryBlock summary={comp.summary} />
        </div>
      ) : !loading && profileReady ? (
        <p className="mt-4 text-sm text-zinc-600">
          Process at least one clip, then run a comp to see a style match, why, and next steps.
        </p>
      ) : null}
    </div>
  );
}
