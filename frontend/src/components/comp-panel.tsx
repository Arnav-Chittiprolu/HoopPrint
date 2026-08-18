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

function Proximity({ match }: { match: CompMatch }) {
  const band = match.resemblance_band ?? match.why?.score_terms?.resemblance_band ?? "—";
  const confidence = match.match_confidence;
  return (
    <div className="text-right">
      <p className="text-sm font-medium text-zinc-900">Role-profile proximity: {band}</p>
      {confidence != null ? (
        <p className="mt-0.5 text-xs text-zinc-500">Match confidence: {confidence}/100</p>
      ) : null}
    </div>
  );
}

function MatchCard({ match, featured }: { match: CompMatch; featured?: boolean }) {
  const why = match.why;
  const groups = why?.filter?.position_groups;
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
            {featured ? " · role resemblance" : ""}
          </p>
        </div>
        <Proximity match={match} />
      </div>

      {featured && why ? (
        <div className="mt-4 space-y-3">
          <div>
            <h3 className="text-sm font-medium text-zinc-800">Why this resemblance</h3>
            <p className="mt-1 text-xs text-zinc-500">
              {why.note ??
                "Public-stat role resemblance — not shared mechanics, skill, or performance."}
            </p>
            {why.filter ? (
              <p className="mt-2 text-sm text-zinc-700">
                Comparison pool
                {groups?.length ? ` (${groups.join(", ")})` : why.filter.position ? ` (${why.filter.position})` : ""}
                {why.filter.band_in != null ? ` within ±${why.filter.band_in}"` : ""}
                {why.filter.user_height_in != null && why.filter.nba_height_in != null
                  ? ` (you ${formatHeightIn(why.filter.user_height_in)}, them ${formatHeightIn(why.filter.nba_height_in)})`
                  : ""}
                .
              </p>
            ) : null}
            {why.score_terms ? (
              <p className="mt-1 font-mono text-[11px] text-zinc-500">
                distance {why.score_terms.distance ?? "—"} · height tie-break{" "}
                {why.score_terms.height_tiebreak ?? "—"}
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
              Masked (no shared evidence): {why.omitted_slots.map((s) => STYLE_LABELS[s] ?? s).join(", ")}
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function RecsBlock({ title, recs }: { title: string; recs: Recommendation[] }) {
  if (!recs.length) return null;
  return (
    <div>
      <h3 className="text-sm font-medium text-zinc-800">{title}</h3>
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
          const message = err instanceof Error ? err.message : "Could not load comparison";
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
        setError(err instanceof Error ? err.message : "Comparison failed");
      }
    });
  }

  const top = comp?.overall[0];
  const archetype = comp?.archetype_result;
  const mechanicsRecs = comp?.mechanics_recs ?? [];
  const roleRecs = comp?.role_recs ?? [];
  const fallbackRecs = !mechanicsRecs.length && !roleRecs.length ? (comp?.recommendations ?? []) : [];

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="text-lg font-medium text-zinc-900">NBA role resemblances</h2>
      <p className="mt-1 text-sm text-zinc-600">
        Similar public role-stat profiles within your comparison pool. Not shared mechanics, skill,
        or performance.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onRun}
          disabled={pending || !profileReady}
          className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {pending ? "Comparing…" : comp ? "Re-run role comparison" : "Run role comparison"}
        </button>
        {!profileReady ? (
          <p className="text-xs text-amber-700">Save height and position in Your profile first.</p>
        ) : (
          <p className="text-xs text-zinc-500">
            Named NBA examples need Established evidence on at least two role dimensions.
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
          <div>
            <h3 className="text-sm font-medium text-zinc-800">Your playing-style profile</h3>
            <p className="mt-1 text-xs text-zinc-500">
              Built from quality-checked events. Describes role tendencies, not skill level or
              outcomes.
            </p>
            <p className="mt-2 text-xs text-zinc-600">
              Evidence strength: {comp.evidence_tier ?? "—"}
              {comp.active_dimensions?.length
                ? ` · active: ${comp.active_dimensions.join(", ")}`
                : ""}
              {comp.excluded_dimensions?.length
                ? ` · excluded: ${comp.excluded_dimensions.join(", ")}`
                : ""}
            </p>
            {archetype?.shown && archetype.label ? (
              <p className="mt-2 text-sm text-zinc-800">
                Archetype: <span className="font-medium">{archetype.label}</span>
              </p>
            ) : (
              <p className="mt-2 text-sm text-zinc-600">Keep building your profile.</p>
            )}
            {comp.pool_sentence ? (
              <p className="mt-2 text-sm text-zinc-700">{comp.pool_sentence}</p>
            ) : (
              <p className="mt-2 text-xs uppercase tracking-wide text-zinc-500">
                {comp.season} · pool {comp.pool_size}
              </p>
            )}
          </div>
          {comp.named_matches_suppressed || !top ? (
            <p className="text-sm text-zinc-600">
              Named NBA examples are withheld until evidence is Established and stable. The
              archetype above is the current role-level summary.
            </p>
          ) : (
            <>
              <MatchCard match={top} featured />
              {comp.overall.slice(1).length ? (
                <div className="space-y-2">
                  <h3 className="text-sm font-medium text-zinc-800">Also close</h3>
                  {comp.overall.slice(1).map((match) => (
                    <MatchCard key={match.player_id ?? match.name} match={match} />
                  ))}
                </div>
              ) : null}
            </>
          )}
          <RecsBlock title="Mechanics next steps" recs={mechanicsRecs} />
          <RecsBlock title="Role-profile next steps" recs={roleRecs} />
          <RecsBlock title="Personalized next steps" recs={fallbackRecs} />
          <SummaryBlock summary={comp.summary} />
        </div>
      ) : !loading && profileReady ? (
        <p className="mt-4 text-sm text-zinc-600">
          Process quality-checked clips, then run a comparison to see an archetype or named role
          resemblance.
        </p>
      ) : null}
    </div>
  );
}
