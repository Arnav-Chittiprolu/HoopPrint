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
import { Initials, SectionLabel } from "@/components/app-header";

function evidenceBadge(tier: string | null | undefined) {
  const label = tier || "Building";
  const established = /establish/i.test(label);
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
        established ? "bg-emerald-50 text-emerald-800" : "bg-zinc-100 text-zinc-600"
      }`}
    >
      {label}
    </span>
  );
}

function Proximity({ match }: { match: CompMatch }) {
  const band = match.resemblance_band ?? match.why?.score_terms?.resemblance_band ?? "—";
  const confidence = match.match_confidence;
  return (
    <div className="text-right">
      <p className="text-sm font-medium text-zinc-900">{band}</p>
      {confidence != null ? (
        <p className="mt-0.5 text-xs text-zinc-500">Match confidence {confidence}/100</p>
      ) : null}
    </div>
  );
}

function MatchCard({
  match,
  featured,
  styleOnly,
}: {
  match: CompMatch;
  featured?: boolean;
  styleOnly?: boolean;
}) {
  const why = match.why;
  const mismatch = styleOnly || match.body_mismatch || match.comp_bucket === "style_only";
  return (
    <article
      className={`rounded-xl border p-4 transition-colors duration-200 ${
        featured
          ? "border-orange-200 bg-orange-50/50"
          : mismatch
            ? "border-sky-100 bg-sky-50/40"
            : "border-zinc-200 bg-white"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <Initials name={match.name} />
          <div className="min-w-0">
            <p className="text-base font-semibold text-zinc-900">{match.name}</p>
            <p className="mt-0.5 text-xs text-zinc-500">
              {match.position ?? "NBA"}
              {match.height_in != null ? ` · ${formatHeightIn(match.height_in)}` : ""}
              {match.season ? ` · ${match.season}` : ""}
            </p>
            {mismatch ? (
              <p className="mt-1 text-[11px] font-medium text-sky-800">
                style similarity · body mismatch
                {match.height_delta_in != null ? ` · ${match.height_delta_in}" gap` : ""}
              </p>
            ) : featured ? (
              <p className="mt-1 text-[11px] font-medium text-orange-800">primary role resemblance</p>
            ) : null}
          </div>
        </div>
        <Proximity match={match} />
      </div>

      {featured && why ? (
        <div className="mt-4 space-y-3">
          <div>
            <h3 className="text-sm font-medium text-zinc-800">Why this resemblance</h3>
            <p className="mt-1 text-xs leading-5 text-zinc-500">
              {why.note ??
                "Public-stat role resemblance — not shared mechanics, skill, or performance."}
            </p>
            {why.filter?.user_height_in != null && why.filter.nba_height_in != null ? (
              <p className="mt-2 text-sm text-zinc-700">
                You {formatHeightIn(why.filter.user_height_in)}, them{" "}
                {formatHeightIn(why.filter.nba_height_in)}
                {why.filter.height_delta_in != null ? ` (${why.filter.height_delta_in}" apart)` : ""}.
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

function suppressionCopy(comp: CompResult): string {
  const counted = comp.valid_event_count;
  const countedBit =
    counted != null ? ` ${counted} quality-checked clip${counted === 1 ? "" : "s"} counted so far.` : "";
  switch (comp.suppression_reason) {
    case "evidence_tier":
      return `Named NBA examples need 5 clips that pass the action check.${countedBit} Form shooting, missing catches, or clips that start/end on the action do not count.`;
    case "pool_size":
      return "No NBA players are within 9 inches of your listed height, so named examples are omitted.";
    case "active_dimensions":
      return "Need at least one role dimension with enough valid events.";
    default:
      return "Named NBA examples are withheld until evidence is Established. The archetype above is the current role-level summary.";
  }
}

function RecsBlock({ title, recs }: { title: string; recs: Recommendation[] }) {
  if (!recs.length) return null;
  return (
    <div className="hp-card p-5">
      <h3 className="text-sm font-medium text-zinc-800">{title}</h3>
      <ol className="mt-3 list-decimal space-y-3 pl-5 text-sm text-zinc-800">
        {recs.map((rec, index) => (
          <li key={`${rec.target}-${index}`}>
            <p className="font-medium">{rec.action}</p>
            <p className="mt-0.5 text-xs text-zinc-500">{rec.because}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function SummaryBlock({ summary }: { summary: string | null }) {
  if (!summary) return null;
  return (
    <div className="hp-card p-5">
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
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        <section className="hp-card p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <SectionLabel>Playing-style profile</SectionLabel>
              <p className="mt-2 text-sm text-zinc-600">
                Built from quality-checked events. Role tendencies, not skill level or outcomes.
              </p>
            </div>
            {evidenceBadge(comp?.evidence_tier)}
          </div>
          {loading ? <p className="mt-4 text-sm text-zinc-500">Loading…</p> : null}
          {comp ? (
            <div className="mt-4">
              {archetype?.shown && archetype.label ? (
                <p className="text-lg font-semibold text-zinc-900">{archetype.label}</p>
              ) : (
                <p className="text-sm text-zinc-600">Keep building your profile.</p>
              )}
              <p className="mt-2 text-xs leading-5 text-zinc-500">
                {comp.active_dimensions?.length
                  ? `Active: ${comp.active_dimensions.join(", ")}`
                  : ""}
                {comp.excluded_dimensions?.length
                  ? ` · excluded: ${comp.excluded_dimensions.join(", ")}`
                  : ""}
                {comp.pool_confidence === "limited" ? " · small comparison set" : ""}
              </p>
            </div>
          ) : null}
        </section>

        <section className="hp-card p-5">
          <SectionLabel>Physical context</SectionLabel>
          <p className="mt-3 text-sm leading-6 text-zinc-700">
            {comp?.physical_context ||
              comp?.pool_sentence ||
              "Height shapes which NBA bodies are realistic primary comps, not how you play."}
          </p>
        </section>

        {error ? (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        ) : null}

        {comp?.stale ? (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            Height, position, or clips changed since this comparison. Re-run to update named
            examples.
          </p>
        ) : null}

        {comp ? (
          <>
            {comp.named_matches_suppressed || (!top && !(comp.style_only?.length)) ? (
              <section className="hp-card p-5">
                <p className="text-sm text-zinc-600">{suppressionCopy(comp)}</p>
              </section>
            ) : (
              <>
                {top ? (
                  <section className="space-y-3">
                    <div>
                      <h2 className="text-sm font-semibold text-zinc-900">Primary NBA role comps</h2>
                      <p className="mt-0.5 text-xs text-zinc-500">
                        Style and body profile are both plausible.
                        {comp.pool_confidence === "limited"
                          ? " Few body-plausible names — treat with lower confidence."
                          : ""}
                      </p>
                    </div>
                    <MatchCard match={top} featured />
                    {comp.overall.slice(1).map((match) => (
                      <MatchCard key={match.player_id ?? match.name} match={match} />
                    ))}
                  </section>
                ) : (
                  <section className="hp-card p-5">
                    <p className="text-sm text-zinc-600">
                      No body-plausible primary comps. Style-only references below are for learning,
                      not &quot;you are this player.&quot;
                    </p>
                  </section>
                )}
                {comp.style_only?.length ? (
                  <section className="space-y-3">
                    <div>
                      <h2 className="text-sm font-semibold text-zinc-900">Style-only references</h2>
                      <p className="mt-0.5 text-xs text-zinc-500">
                        Similar tendencies with a major size mismatch. For learning, not a primary
                        comparison.
                      </p>
                    </div>
                    {comp.style_only.map((match) => (
                      <MatchCard key={match.player_id ?? match.name} match={match} styleOnly />
                    ))}
                  </section>
                ) : null}
              </>
            )}
            <RecsBlock title="Mechanics next steps" recs={mechanicsRecs} />
            <RecsBlock title="Role-profile next steps" recs={roleRecs} />
            <RecsBlock title="Personalized next steps" recs={fallbackRecs} />
            <SummaryBlock summary={comp.summary} />
          </>
        ) : !loading && profileReady ? (
          <section className="hp-card p-5">
            <p className="text-sm text-zinc-600">
              Process quality-checked clips, then run a comparison to see an archetype or named
              role resemblance.
            </p>
          </section>
        ) : null}
      </div>

      <aside className="hp-card h-fit p-5 lg:sticky lg:top-20">
        <SectionLabel>Run settings</SectionLabel>
        <p className="mt-3 text-sm leading-6 text-zinc-600">
          Role resemblance is 72% of rank. Height is body plausibility, not a style slot. Named
          names need Established evidence.
        </p>
        <button
          type="button"
          onClick={onRun}
          disabled={pending || !profileReady}
          className="mt-5 w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-zinc-800 disabled:opacity-60"
        >
          {pending ? "Comparing…" : comp ? "Re-run comparison" : "Run comparison"}
        </button>
        {!profileReady ? (
          <p className="mt-3 text-xs text-amber-700">Save height and position on Clips first.</p>
        ) : (
          <p className="mt-3 text-xs leading-5 text-zinc-500">
            Named NBA examples need about 5 quality-checked clips (Established).
          </p>
        )}
      </aside>
    </div>
  );
}
