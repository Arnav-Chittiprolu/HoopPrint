"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ProfileFields } from "@/components/profile-fields";
import { SignOutButton } from "@/components/sign-out-button";
import { BrandMark } from "@/components/app-header";
import {
  getMyProfile,
  updateMyProfile,
  type ProfileQuestionnaire,
} from "@/lib/api";
import { isProfileComplete } from "@/lib/profile";

const emptyForm: ProfileQuestionnaire = {
  display_name: null,
  height_in: null,
  height_z: null,
  position: null,
  dominant_hand: null,
  primary_skill: null,
};

export default function SetupPage() {
  const router = useRouter();
  const [form, setForm] = useState<ProfileQuestionnaire>(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const profile = await getMyProfile();
        if (cancelled) return;
        if (isProfileComplete(profile.questionnaire)) {
          router.replace("/dashboard");
          return;
        }
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
  }, [router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!isProfileComplete(form)) {
      setError("Fill in name, height, position, dominant hand, and primary skill.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateMyProfile({
        display_name: form.display_name,
        height_in: form.height_in,
        position: form.position,
        dominant_hand: form.dominant_hand,
        primary_skill: form.primary_skill,
      });
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="relative mx-auto flex min-h-full w-full max-w-lg flex-col px-6 py-10">
      <div className="flex items-start justify-between gap-4">
        <BrandMark href="/setup" />
        <SignOutButton />
      </div>

      <p className="mt-10 text-xs font-medium uppercase tracking-wide text-zinc-400">Step 1 of 2</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900">
        Create your profile
      </h1>
      <p className="mt-2 text-sm leading-6 text-zinc-600">
        Name, height, and position first. Height only shapes which NBA bodies are realistic
        comps — clips decide how you play.
      </p>

      {loading ? (
        <p className="mt-10 text-sm text-zinc-500">Loading profile…</p>
      ) : (
        <form
          onSubmit={onSubmit}
          className="hp-card mt-8 p-5"
        >
          <p className="mb-5 text-xs font-semibold uppercase tracking-wide text-zinc-400">
            Your profile
          </p>
          <ProfileFields form={form} setForm={setForm} required />
          {error ? (
            <p className="mt-4 text-sm text-red-600" role="alert">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={saving}
            className="mt-6 w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-zinc-800 disabled:opacity-60"
          >
            {saving ? "Saving…" : "Continue"}
          </button>
        </form>
      )}
    </main>
  );
}
