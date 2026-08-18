import Link from "next/link";
import { BrandMark } from "@/components/app-header";

function IconUpload() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 15.5V17a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-1.5M16 8l-4-4m0 0L8 8m4-4v12" />
    </svg>
  );
}

function IconRole() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 19V5m0 14h16M8 15l3-4 3 2 4-6" />
    </svg>
  );
}

function IconComp() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
      <circle cx="9.5" cy="7" r="3.5" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 8v6m3-3h-6" />
    </svg>
  );
}

export default function HomePage() {
  return (
    <main className="relative flex min-h-full flex-1 flex-col overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_#fff7ed_0%,_#fafafa_48%,_#f4f4f5_100%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.28]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(24,24,27,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(24,24,27,0.06) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />

      <header className="relative z-10 mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-5">
        <BrandMark />
        <Link
          href="/login"
          className="text-sm font-medium text-zinc-600 transition-colors duration-200 hover:text-zinc-900"
        >
          Sign in
        </Link>
      </header>

      <div className="relative z-10 mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 pb-16 pt-10 sm:pt-16">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-orange-700">
          Basketball footage, read as a role
        </p>
        <h1 className="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-zinc-900 sm:text-5xl">
          See which NBA roles your clips actually resemble.
        </h1>
        <p className="mt-4 max-w-xl text-base leading-7 text-zinc-600">
          Upload short shot, pass, and drive clips. HoopPrint quality-checks the action, builds a
          playing-style profile, then names physically realistic NBA role comps — not a claim that
          you shoot like them.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/signup"
            className="rounded-lg bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-zinc-800"
          >
            Get started
          </Link>
          <Link
            href="/login"
            className="rounded-lg border border-zinc-300 bg-white/80 px-5 py-2.5 text-sm font-medium text-zinc-800 backdrop-blur transition-colors duration-200 hover:bg-white"
          >
            Sign in
          </Link>
        </div>

        <div className="hp-stagger mt-16 grid gap-4 sm:grid-cols-3">
          {[
            {
              title: "Clip the action",
              copy: "Tag shot, pass, or drive. Solo drills process immediately; gameplay asks you to box yourself.",
              icon: <IconUpload />,
            },
            {
              title: "Build a role profile",
              copy: "Catch readiness, rim pressure, and playmaking come from quality-checked events — not form shooting.",
              icon: <IconRole />,
            },
            {
              title: "Named NBA comps",
              copy: "Five established clips unlock names. Height is body plausibility, not a style dimension.",
              icon: <IconComp />,
            },
          ].map((item) => (
            <article key={item.title} className="hp-card p-5">
              <span className="inline-flex size-9 items-center justify-center rounded-lg bg-orange-50 text-orange-800">
                {item.icon}
              </span>
              <h2 className="mt-4 text-sm font-semibold text-zinc-900">{item.title}</h2>
              <p className="mt-1.5 text-sm leading-6 text-zinc-600">{item.copy}</p>
            </article>
          ))}
        </div>
      </div>
    </main>
  );
}
