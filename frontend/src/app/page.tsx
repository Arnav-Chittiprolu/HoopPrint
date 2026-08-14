import Link from "next/link";

export default function HomePage() {
  return (
    <main className="relative flex min-h-full flex-1 flex-col overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_#fff7ed_0%,_#fafafa_45%,_#e4e4e7_100%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(24,24,27,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(24,24,27,0.06) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />

      <div className="relative z-10 mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-6 py-20">
        <p className="text-sm font-semibold tracking-[0.2em] text-orange-700 uppercase">
          HoopPrint
        </p>
        <h1 className="mt-4 max-w-xl text-4xl font-semibold tracking-tight text-zinc-900 sm:text-5xl">
          Basketball skill analysis from your own footage.
        </h1>
        <p className="mt-4 max-w-lg text-base leading-7 text-zinc-600">
          Upload a clip, extract pose mechanics, match an NBA comp from real
          stats, and get a grounded summary. Phase 0: auth shell only.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/signup"
            className="rounded-md bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-zinc-800"
          >
            Get started
          </Link>
          <Link
            href="/login"
            className="rounded-md border border-zinc-300 bg-white/80 px-5 py-2.5 text-sm font-medium text-zinc-800 backdrop-blur hover:bg-white"
          >
            Sign in
          </Link>
        </div>
      </div>
    </main>
  );
}
