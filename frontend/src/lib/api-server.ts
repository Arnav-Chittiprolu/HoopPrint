import { createClient } from "@/lib/supabase/server";
import type { Clip } from "@/lib/api";

const API_URL =
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_DIRECT_URL ||
  "http://127.0.0.1:8000";

export async function listClipsServer(): Promise<Clip[]> {
  const supabase = await createClient();

  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    return [];
  }

  let {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    const { data: refreshed } = await supabase.auth.refreshSession();
    session = refreshed.session;
  }

  if (!session?.access_token) {
    return [];
  }

  const res = await fetch(`${API_URL}/clips`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    cache: "no-store",
  });

  if (!res.ok) {
    let message = `Failed to list clips (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  return res.json();
}
