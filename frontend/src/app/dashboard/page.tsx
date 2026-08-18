import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { listClipsServer } from "@/lib/api-server";
import type { Clip } from "@/lib/api";
import { ClipUploadForm } from "@/components/clip-upload-form";
import { ClipUploadGuide } from "@/components/clip-upload-guide";
import { ClipList } from "@/components/clip-list";
import { ClipProgress } from "@/components/clip-progress";
import { ProfileQuestionnaireForm } from "@/components/profile-questionnaire-form";
import { SectionLabel } from "@/components/app-header";

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    redirect("/login");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("height_in, position")
    .eq("id", session.user.id)
    .maybeSingle();

  const profileReady = profile?.height_in != null && Boolean(profile?.position);

  let clips: Clip[] = [];
  let clipsError: string | null = null;
  try {
    clips = await listClipsServer();
  } catch (err) {
    clipsError = err instanceof Error ? err.message : "Could not load clips";
  }

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Clips</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Upload short footage. Quality-checked clips build your playing-style profile.
          </p>
        </div>
      </div>

      {!profileReady ? (
        <p className="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Save height and position in Your profile before running an NBA role comparison.
        </p>
      ) : null}

      <div className="mt-6">
        <ClipProgress clips={clips} />
      </div>

      <div className="hp-stagger mt-6 grid gap-5 lg:grid-cols-3">
        <section className="hp-card p-5">
          <SectionLabel>Your profile</SectionLabel>
          <p className="mt-2 text-sm text-zinc-600">
            Height is body plausibility for NBA names — not a playing-style dimension.
          </p>
          <div className="mt-4">
            <ProfileQuestionnaireForm />
          </div>
        </section>

        <section className="hp-card p-5">
          <SectionLabel>Upload clip</SectionLabel>
          <p className="mt-2 text-sm text-zinc-600">
            Short mp4 or mov, about 25 seconds, 50MB. Tag the action you actually did.
          </p>
          <div className="mt-4">
            <ClipUploadForm />
          </div>
          <div className="mt-4">
            <ClipUploadGuide clips={clips} />
          </div>
        </section>

        <section className="hp-card p-5">
          <SectionLabel>Your clips</SectionLabel>
          {clipsError ? (
            <p className="mt-3 text-sm text-amber-700">{clipsError}</p>
          ) : (
            <div className="mt-3">
              <ClipList clips={clips} />
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
