"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { formatAuthError } from "@/lib/auth-errors";
import { BrandMark } from "@/components/app-header";

const fieldClass =
  "rounded-lg border border-zinc-200 bg-white px-3 py-2.5 outline-none ring-orange-600 transition-shadow duration-200 focus:ring-2";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setLoading(true);
    try {
      const supabase = createClient();
      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
      });
      if (signUpError) {
        setError(formatAuthError(signUpError.message));
        return;
      }
      if (data.session) {
        router.push("/setup");
        router.refresh();
        return;
      }
      setMessage("Check your email to confirm your account, then sign in.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed");
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
        <h1 className="mt-8 text-3xl font-semibold tracking-tight text-zinc-900">Create account</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Then set height and position before uploading clips.
        </p>

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
          {message ? (
            <p className="text-sm text-emerald-700" role="status">
              {message}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-zinc-800 disabled:opacity-60"
          >
            {loading ? "Creating…" : "Sign up"}
          </button>
        </form>

        <p className="mt-6 text-sm text-zinc-600">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-orange-700 hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
