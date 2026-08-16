"use client";

import { useEffect, useState, useTransition } from "react";
import {
  getMyComp,
  runMyComp,
  type CompMatch,
  type CompResult,
  type Recommendation,
} from "@/lib/api";

function WhyBlock({ match }: { match: CompMatch }) {
  const why = match.why;
  if (!why) return null;
  const filter = why.filter;
  const terms = why.score_terms;
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-zinc-800">Why {match.name}</h3>
      <p className="text-xs text-zinc-500">
        {why.note ?? "Style similarity — not identical motion."}
      </p>
      {filter ? (
        <p className="text-sm text-zinc-700">
          Same position ({filter.position}) and height within ±{filter.band_in}" (
          you {filter.user_height_in}", them {filter.nba_height_in}").
        </p>
      ) : null}
      {terms ? (
        <p className="font-mono text-xs text-zinc-600">
          cosine={terms.cosine ?? "—"} · size={terms.size_similarity ?? "—"} · skill=
          {terms.primary_skill_bonus ?? "—"} · total={terms.total ?? match.score}
        </p>
      ) : null}
      {why.slots?.length ? (
        <ul className="space-y-1 text-xs text-zinc-700">
          {why.slots.map((slot) => (
            <li key={slot.dim}>
              {slot.dim}: you {slot.user.toFixed(2)} vs {slot.nba.toFixed(2)} (gap{" "}
              {slot.gap.toFixed(2)})
            </li>
          ))}
        </ul>
      ) : null}
      {why.omitted_slots?.length ? (
        <p className="text-xs text-zinc-500">
          Omitted (no clip evidence): {why.omitted_slots.join(", ")}
        </p>
      ) : null}
    </div>
  );
}

function RecsBlock({ recs }: { recs: Recommendation[] }) {
  if (!recs.length) return null;
  return (
    <div>
      <h3 className="text-sm font-medium text-zinc-800">Personalized next steps</h3>
      <ol className="mt-2 list-decimal space-y-2 pl-5 text-sm text-zinc-800">
        {recs.map((rec) => (
          <li key={rec.target}>
            <p>{rec.action}</p>
            <p className="text-xs text-zinc-500">{rec.because}</p>
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

function MatchList({ title, matches }: { title: string; matches: CompMatch[] }) {
  if (!matches.length) return null;
  return (
    <div>
      <h3 className="text-sm font-medium text-zinc-800">{title}</h3>
      <ul className="mt-2 space-y-2">
        {matches.map((m) => (
          <li
            key={`${title}-${m.player_id ?? m.name}-${m.score}`}
            className="flex items-baseline justify-between gap-3 text-sm"
          >
            <span className="text-zinc-900">
              {m.name}
              {m.position ? (
                <span className="text-zinc-500"> · {m.position}</span>
              ) : null}
              {m.height_in != null ? (
                <span className="text-zinc-500">
                  {" "}
                  · {Math.floor(m.height_in / 12)}'{Math.round(m.height_in % 12)}"
                </span>
              ) : null}
            </span>
            <span className="tabular-nums text-zinc-600">
              {(m.score * 100).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CompPanel() {
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
          // 404 → no comp yet is fine
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onRun}
          disabled={pending}
          className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {pending ? "Matching…" : "Run style comp"}
        </button>
        <p className="text-xs text-zinc-500">
          Style similarity from questionnaire + pose — not identical motion, not an LLM pick.
          Why + recs are computed from your numbers; Gemini only narrates them if GEMINI_API_KEY is set.
        </p>
      </div>

      {loading ? <p className="text-sm text-zinc-500">Loading…</p> : null}
      {error ? (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}

      {comp ? (
        <div className="space-y-4 border-t border-zinc-100 pt-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">
            Style card · {comp.season} · pool {comp.pool_size}
          </p>
          <MatchList title="Overall style" matches={comp.overall} />
          {comp.by_category.shot ? (
            <MatchList title="Jumper style" matches={comp.by_category.shot} />
          ) : null}
          {comp.by_category.pass ? (
            <MatchList title="Passing style" matches={comp.by_category.pass} />
          ) : null}
          {comp.by_category.drive ? (
            <MatchList title="Drive style" matches={comp.by_category.drive} />
          ) : null}

          {comp.overall[0] ? <WhyBlock match={comp.overall[0]} /> : null}
          <RecsBlock recs={comp.recommendations ?? []} />
          <SummaryBlock summary={comp.summary} />

          {Object.keys(comp.mechanics).length > 0 ? (
            <div>
              <h3 className="text-sm font-medium text-zinc-800">Mechanics (pose)</h3>
              <p className="mt-1 text-xs text-zinc-500">
                Joint angles from your clips — not compared as NBA shooting percentages.
              </p>
              <p className="mt-2 font-mono text-xs text-zinc-700">
                {Object.entries(comp.mechanics)
                  .map(([k, v]) => `${k}=${typeof v === "number" ? v.toFixed(2) : v}`)
                  .join(" · ")}
              </p>
            </div>
          ) : null}
        </div>
      ) : !loading ? (
        <p className="text-sm text-zinc-600">
          Save height + position, process a clip, seed NBA players, then run a comp.
        </p>
      ) : null}
    </div>
  );
}
