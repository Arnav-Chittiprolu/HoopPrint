"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getMyProfile,
  updateMyProfile,
  type PlayerPosition,
  type ProfileQuestionnaire,
  type DominantHand,
  type PrimarySkill,
} from "@/lib/api";

const emptyForm: ProfileQuestionnaire = {
  display_name: null,
  height_in: null,
  height_z: null,
  position: null,
  dominant_hand: null,
  primary_skill: null,
};

export function ProfileQuestionnaireForm() {
  const router = useRouter();
  const [form, setForm] = useState<ProfileQuestionnaire>(emptyForm);
  const [aggSummary, setAggSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const profile = await getMyProfile();
        if (cancelled) return;
        setForm(profile.questionnaire);
        if (profile.aggregated_features.length > 0) {
          const parts = profile.aggregated_features
            .slice(0, 4)
            .map((f) => `${f.feature_name}=${f.value.toFixed(1)} (n=${f.clip_count})`);
          setAggSummary(parts.join(" · "));
        } else {
          setAggSummary(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load profile");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const profile = await updateMyProfile({
        display_name: form.display_name,
        height_in: form.height_in,
        position: form.position,
        dominant_hand: form.dominant_hand,
        primary_skill: form.primary_skill,
      });
      setForm(profile.questionnaire);
      setSuccess(
        profile.questionnaire.height_z == null
          ? "Profile saved"
          : `Profile saved · height_z ${profile.questionnaire.height_z.toFixed(2)}`,
      );
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-zinc-500">Loading profile…</p>;
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800">Display name</span>
          <input
            value={form.display_name ?? ""}
            onChange={(e) =>
              setForm((f) => ({ ...f, display_name: e.target.value || null }))
            }
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 outline-none ring-orange-600 focus:ring-2"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800">Height (inches)</span>
          <input
            type="number"
            min={48}
            max={96}
            step={0.5}
            value={form.height_in ?? ""}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                height_in: e.target.value === "" ? null : Number(e.target.value),
              }))
            }
            placeholder="e.g. 74"
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 outline-none ring-orange-600 focus:ring-2"
          />
          <span className="text-xs text-zinc-500">
            Saved as short/average/tall vs ~5&apos;9&quot; male average (height_z)
            {form.height_z != null ? ` · current ${form.height_z.toFixed(2)}` : ""}
          </span>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800">Position</span>
          <select
            value={form.position ?? ""}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                position: (e.target.value || null) as PlayerPosition | null,
              }))
            }
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 outline-none ring-orange-600 focus:ring-2"
          >
            <option value="">Select…</option>
            <option value="guard">Guard</option>
            <option value="wing">Wing</option>
            <option value="forward">Forward</option>
            <option value="center">Center</option>
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-800">Dominant hand</span>
          <select
            value={form.dominant_hand ?? ""}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                dominant_hand: (e.target.value || null) as DominantHand | null,
              }))
            }
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 outline-none ring-orange-600 focus:ring-2"
          >
            <option value="">Select…</option>
            <option value="right">Right</option>
            <option value="left">Left</option>
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          <span className="font-medium text-zinc-800">Primary skill</span>
          <select
            value={form.primary_skill ?? ""}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                primary_skill: (e.target.value || null) as PrimarySkill | null,
              }))
            }
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 outline-none ring-orange-600 focus:ring-2"
          >
            <option value="">Select…</option>
            <option value="shot">Shot</option>
            <option value="pass">Pass</option>
            <option value="drive">Drive</option>
          </select>
        </label>
      </div>

      {aggSummary ? (
        <p className="text-xs text-zinc-500">
          Aggregated mechanics: {aggSummary}
        </p>
      ) : (
        <p className="text-xs text-zinc-500">
          Aggregated features appear after a successful clip finishes processing.
        </p>
      )}

      {error ? (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}
      {success ? (
        <p className="text-sm text-emerald-700" role="status">
          {success}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={saving}
        className="rounded-md bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-60"
      >
        {saving ? "Saving…" : "Save profile"}
      </button>
    </form>
  );
}
