import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { listClipsServer } from "@/lib/api-server";
import type { Clip } from "@/lib/api";
import { SignOutButton } from "@/components/sign-out-button";
import { ClipUploadForm } from "@/components/clip-upload-form";
import { ClipList } from "@/components/clip-list";
import { ProfileQuestionnaireForm } from "@/components/profile-questionnaire-form";
import { CompPanel } from "@/components/comp-panel";
import { MechanicsPanel } from "@/components/mechanics-panel";

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
    .select("display_name, height_in, position")
    .eq("id", session.user.id)
    .maybeSingle();

  const displayName = profile?.display_name || session.user.email || "Athlete";
  const profileReady = profile?.height_in != null && Boolean(profile?.position);

  let clips: Clip[] = [];
  let clipsError: string | null = null;
  try {
    clips = await listClipsServer();
  } catch (err) {
    clipsError = err instanceof Error ? err.message : "Could not load clips";
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold tracking-wide text-orange-700">HoopPrint</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900">Results</h1>
          <p className="mt-2 text-zinc-600">
            Signed in as <span className="font-medium text-zinc-900">{displayName}</span>
          </p>
        </div>
        <SignOutButton />
      </div>

      {!profileReady ? (
        <p className="mt-6 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Save height and position in Your profile before running an NBA role comparison.
        </p>
      ) : null}

      <div className="mt-8 grid gap-6 lg:grid-cols-5">
        <section className="space-y-6 lg:col-span-3">
          <CompPanel profileReady={profileReady} />
          <MechanicsPanel />
        </section>

        <section className="space-y-6 lg:col-span-2">
          <div className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-lg font-medium text-zinc-900">Your profile</h2>
            <p className="mt-1 text-sm text-zinc-600">
              Height and position filter the NBA comparison pool. They are not role-profile
              dimensions.
            </p>
            <div className="mt-4">
              <ProfileQuestionnaireForm />
            </div>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-lg font-medium text-zinc-900">Upload clip</h2>
            <p className="mt-1 text-sm text-zinc-600">
              Short mp4 (~25s, 50MB). Individual drills process immediately. Gameplay asks you to
              box yourself, then tracks only that person.
            </p>
            <div className="mt-4">
              <ClipUploadForm />
            </div>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-lg font-medium text-zinc-900">Your clips</h2>
            {clipsError ? (
              <p className="mt-2 text-sm text-amber-700">{clipsError}</p>
            ) : (
              <div className="mt-3">
                <ClipList clips={clips} />
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
