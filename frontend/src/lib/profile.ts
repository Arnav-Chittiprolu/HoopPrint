import type { ProfileQuestionnaire } from "@/lib/api";

const inputClass =
  "w-full rounded-lg border border-zinc-200 bg-white px-3 py-2.5 text-sm text-zinc-900 outline-none ring-orange-600 focus:ring-2";

export const PROFILE_FIELD_CLASS = inputClass;

export function isProfileComplete(
  profile: Pick<
    ProfileQuestionnaire,
    "display_name" | "height_in" | "position" | "dominant_hand" | "primary_skill"
  > | null
    | undefined,
): boolean {
  if (!profile) return false;
  return (
    Boolean(profile.display_name?.trim()) &&
    profile.height_in != null &&
    Boolean(profile.position) &&
    Boolean(profile.dominant_hand) &&
    Boolean(profile.primary_skill)
  );
}

export function initialsFromName(name: string | null | undefined, fallback = "HP"): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return fallback;
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] ?? ""}${parts[parts.length - 1][0] ?? ""}`.toUpperCase();
}
