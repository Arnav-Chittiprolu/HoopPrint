"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ProfileFields } from "@/components/profile-fields";
import { getMyProfile, updateMyProfile, type ProfileQuestionnaire } from "@/lib/api";

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
      setSuccess("Profile saved");
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
      <ProfileFields form={form} setForm={setForm} required />
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
        className="w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-zinc-800 disabled:opacity-60"
      >
        {saving ? "Saving…" : "Save"}
      </button>
    </form>
  );
}
