"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { formatAuthError } from "@/lib/auth-errors";
import { BrandMark } from "@/components/app-header";

const fieldClass =
  "rounded-lg border border-zinc-200 bg-white px-3 py-2.5 outline-none ring-orange-600 transition-shadow duration-200 focus:ring-2";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const supabase = createClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (signInError) {
        setError(formatAuthError(signInError.message));
        return;
      }
      router.push("/setup");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative flex min-h-full flex-1 flex-col">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_#fff7ed_0%,_#fafafa_55%)]"
      />
      <div className="relative z-10 mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-16">
        <BrandMark />
        <h1 className="mt-8 text-3xl font-semibold tracking-tight text-zinc-900">Sign in</h1>
        <p className="mt-2 text-sm text-zinc-600">Continue to your clips and role analysis.</p>

        <form onSubmit={onSubmit} className="hp-card mt-8 flex flex-col gap-4 p-5">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-zinc-800">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-zinc-800">Password</span>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={fieldClass}
            />
          </label>
          {error ? (
            <p className="text-sm text-red-600" role="alert">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-zinc-800 disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-sm text-zinc-600">
          No account?{" "}
          <Link href="/signup" className="font-medium text-orange-700 hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </main>
  );
}
