"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SignOutButton } from "@/components/sign-out-button";

export function AppHeader({ displayName }: { displayName: string }) {
  const pathname = usePathname();
  const onAnalysis = pathname.startsWith("/dashboard/analysis");
  const tab =
    "relative pb-1 text-sm font-medium transition-colors duration-200 hover:text-zinc-900";
  const on =
    "text-zinc-900 after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:rounded-full after:bg-orange-700";
  const off = "text-zinc-500";

  return (
    <header className="sticky top-0 z-30 border-b border-zinc-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-8">
          <Link href="/dashboard" className="text-sm font-semibold tracking-wide text-orange-700">
            HoopPrint
          </Link>
          <nav className="flex items-center gap-5" aria-label="App">
            <Link
              href="/dashboard"
              className={`${tab} ${onAnalysis ? off : on}`}
              aria-current={onAnalysis ? undefined : "page"}
            >
              Clips
            </Link>
            <Link
              href="/dashboard/analysis"
              className={`${tab} ${onAnalysis ? on : off}`}
              aria-current={onAnalysis ? "page" : undefined}
            >
              Analysis
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm text-zinc-600">
          <span className="hidden sm:inline">
            Signed in as <span className="font-medium text-zinc-900">{displayName}</span>
          </span>
          <SignOutButton />
        </div>
      </div>
    </header>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-400">
      {children}
    </p>
  );
}

export function Initials({ name }: { name: string }) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters =
    parts.length >= 2
      ? `${parts[0][0]}${parts[parts.length - 1][0]}`
      : (parts[0] || "HP").slice(0, 2);
  return (
    <span
      className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-xs font-semibold text-zinc-600"
      aria-hidden
    >
      {letters.toUpperCase()}
    </span>
  );
}

export function BrandMark({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="text-sm font-semibold tracking-wide text-orange-700">
      HoopPrint
    </Link>
  );
}
