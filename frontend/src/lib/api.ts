import { createClient } from "@/lib/supabase/client";

/** Browser calls backend directly — avoids Next.js proxy hanging on large multipart uploads. */
const API_URL =
  process.env.NEXT_PUBLIC_API_DIRECT_URL || "http://127.0.0.1:8000";

const UPLOAD_TIMEOUT_MS = 120_000;

function isNetworkError(err: unknown): boolean {
  return err instanceof TypeError && /fetch/i.test(err.message);
}

/** Validates session with Supabase, then returns a fresh access token. */
async function getAccessToken(): Promise<string> {
  const supabase = createClient();

  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    throw new Error("Not signed in — please log in again");
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (session?.access_token) {
    const expiresAt = (session.expires_at ?? 0) * 1000;
    if (expiresAt > Date.now() + 15_000) {
      return session.access_token;
    }
  }

  const refreshResult = await Promise.race([
    supabase.auth.refreshSession(),
    new Promise<never>((_, reject) =>
      setTimeout(
        () => reject(new Error("Session refresh timed out — sign in again")),
        8_000,
      ),
    ),
  ]);

  const { data, error } = refreshResult;
  if (error || !data.session?.access_token) {
    throw new Error("Session expired — please sign in again");
  }
  return data.session.access_token;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
  timeoutMs = 30_000,
): Promise<Response> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(`${API_URL}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error("Request timed out — try again or use a smaller clip");
    }
    if (isNetworkError(err)) {
      throw new Error(
        "Could not reach the API. Make sure the backend is running on port 8000.",
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export type SourceType = "individual" | "gameplay";
export type ClipType = "shot" | "pass" | "drive";
export type ClipStatus =
  | "uploaded"
  | "awaiting_bbox"
  | "processing"
  | "done"
  | "failed";

export interface Clip {
  id: string;
  user_id: string;
  source_type: SourceType;
  clip_type: ClipType;
  storage_path: string;
  status: ClipStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

function parseApiError(body: unknown, fallback: string): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e) =>
          typeof e === "object" && e && "msg" in e ? String(e.msg) : String(e),
        )
        .join(", ");
    }
  }
  return fallback;
}

export async function listClips(): Promise<Clip[]> {
  const res = await apiFetch("/clips");
  if (!res.ok) {
    let message = `Failed to list clips (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json();
}

export async function processClip(clipId: string): Promise<{
  clip_id: string;
  status: ClipStatus;
  frame_count: number;
}> {
  const res = await apiFetch(`/clips/${clipId}/process`, { method: "POST" });
  if (!res.ok) {
    let message = `Failed to process clip (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json();
}

export interface ClipFeature {
  id: string;
  clip_id: string;
  feature_name: string;
  value: number;
  meta: Record<string, unknown>;
  created_at: string;
}

export async function listClipFeatures(clipId: string): Promise<ClipFeature[]> {
  const res = await apiFetch(`/clips/${clipId}/features`);
  if (!res.ok) {
    let message = `Failed to list features (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json();
}

export async function getClipOverlayUrl(clipId: string): Promise<string | null> {
  const res = await apiFetch(`/clips/${clipId}/overlay-url`);
  if (res.status === 404) return null;
  if (!res.ok) {
    let message = `Failed to load overlay (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  const body = (await res.json()) as { url: string };
  return body.url;
}

export type PlayerPosition = "guard" | "wing" | "forward" | "center";
export type DominantHand = "left" | "right";
export type PrimarySkill = "shot" | "pass" | "drive";

export interface ProfileQuestionnaire {
  display_name: string | null;
  height_in: number | null;
  height_z: number | null;
  position: PlayerPosition | null;
  dominant_hand: DominantHand | null;
  primary_skill: PrimarySkill | null;
}

export interface AggregatedFeature {
  feature_name: string;
  value: number;
  clip_count: number;
  updated_at?: string | null;
}

export interface UserProfile {
  id: string;
  email: string | null;
  questionnaire: ProfileQuestionnaire;
  aggregated_features: AggregatedFeature[];
}

export interface HistoryPoint {
  clip_id: string;
  clip_type: string;
  feature_name: string;
  value: number;
  created_at: string;
}

export async function getMyProfile(): Promise<UserProfile> {
  const res = await apiFetch("/me/profile");
  if (!res.ok) {
    let message = `Failed to load profile (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json();
}

export async function updateMyProfile(
  patch: Partial<Omit<ProfileQuestionnaire, "height_z">>,
): Promise<UserProfile> {
  const res = await apiFetch("/me/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    let message = `Failed to update profile (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json();
}

export async function getMyHistory(): Promise<HistoryPoint[]> {
  const res = await apiFetch("/me/history");
  if (!res.ok) {
    let message = `Failed to load history (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json();
}

export interface CompMatch {
  player_id: number | null;
  name: string;
  season: string | null;
  position: string | null;
  height_in: number | null;
  score: number;
  style_vector: Record<string, number>;
  kind: string;
}

export interface CompResult {
  id: string | null;
  user_id: string;
  created_at: string | null;
  season: string | null;
  label: string;
  user_style: Record<string, number>;
  evidence: Record<string, boolean>;
  mechanics: Record<string, number>;
  overall: CompMatch[];
  by_category: Partial<Record<"shot" | "pass" | "drive", CompMatch[]>>;
  pool_size: number;
  summary: string | null;
}

export async function getMyComp(): Promise<CompResult | null> {
  const res = await apiFetch("/me/comp");
  if (res.status === 404) return null;
  if (!res.ok) {
    let message = `Failed to load comp (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json();
}

export async function runMyComp(): Promise<CompResult> {
  const res = await apiFetch("/me/comp", { method: "POST" });
  if (!res.ok) {
    let message = `Failed to run comp (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json();
}

export async function uploadClip(
  file: File,
  sourceType: SourceType,
  clipType: ClipType,
): Promise<Clip> {
  const form = new FormData();
  form.append("file", file);
  form.append("source_type", sourceType);
  form.append("clip_type", clipType);

  const res = await apiFetch("/clips", { method: "POST", body: form }, UPLOAD_TIMEOUT_MS);
  if (!res.ok) {
    let message = `Upload failed (${res.status})`;
    try {
      message = parseApiError(await res.json(), message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return res.json();
}
