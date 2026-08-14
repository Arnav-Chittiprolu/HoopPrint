"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

type HealthState =
  | { status: "loading" }
  | { status: "ok"; body: Record<string, unknown> }
  | { status: "error"; message: string };

export function ApiHealthCard() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });
  const [me, setMe] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    async function run() {
      try {
        const res = await fetch(`${apiUrl}/health`);
        if (!res.ok) {
          setHealth({ status: "error", message: `HTTP ${res.status}` });
        } else {
          setHealth({ status: "ok", body: await res.json() });
        }
      } catch (err) {
        setHealth({
          status: "error",
          message: err instanceof Error ? err.message : "Failed to reach API",
        });
      }

      try {
        const supabase = createClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (!session?.access_token) {
          setMe({ status: "error", message: "No session token" });
          return;
        }
        const res = await fetch(`${apiUrl}/me`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) {
          const text = await res.text();
          setMe({ status: "error", message: text || `HTTP ${res.status}` });
          return;
        }
        setMe({ status: "ok", body: await res.json() });
      } catch (err) {
        setMe({
          status: "error",
          message: err instanceof Error ? err.message : "Failed /me call",
        });
      }
    }

    void run();
  }, []);

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h2 className="text-lg font-medium text-zinc-900">Backend checks</h2>
      <ul className="mt-3 space-y-2 text-sm text-zinc-700">
        <li>
          <span className="font-medium">GET /health:</span>{" "}
          {health.status === "loading" && "Checking…"}
          {health.status === "ok" && (
            <span className="text-emerald-700">ok ({JSON.stringify(health.body)})</span>
          )}
          {health.status === "error" && (
            <span className="text-amber-700">{health.message}</span>
          )}
        </li>
        <li>
          <span className="font-medium">GET /me (JWT):</span>{" "}
          {me.status === "loading" && "Checking…"}
          {me.status === "ok" && (
            <span className="text-emerald-700">ok ({JSON.stringify(me.body)})</span>
          )}
          {me.status === "error" && (
            <span className="text-amber-700">{me.message}</span>
          )}
        </li>
      </ul>
      <p className="mt-3 text-xs text-zinc-500">
        Configure <code>NEXT_PUBLIC_API_URL</code> and backend{" "}
        <code>SUPABASE_JWT_SECRET</code> for the protected check.
      </p>
    </div>
  );
}
