import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { listClipsServer } from "@/lib/api-server";
import type { Clip } from "@/lib/api";
import { SignOutButton } from "@/components/sign-out-button";
import { ClipUploadForm } from "@/components/clip-upload-form";
import { ClipList } from "@/components/clip-list";
import { ProfileQuestionnaireForm } from "@/components/profile-questionnaire-form";

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
    .select("display_name")
    .eq("id", session.user.id)
    .maybeSingle();

  const displayName = profile?.display_name || session.user.email || "Athlete";

  let clips: Clip[] = [];
  let clipsError: string | null = null;
  try {
    clips = await listClipsServer();
  } catch (err) {
    clipsError = err instanceof Error ? err.message : "Could not load clips";
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold tracking-wide text-orange-700">
            HoopPrint
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-900">
            Dashboard
          </h1>
          <p className="mt-2 text-zinc-600">
            Signed in as <span className="font-medium text-zinc-900">{displayName}</span>
          </p>
        </div>
        <SignOutButton />
      </div>

      <section className="mt-10 space-y-4">
        <div className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-lg font-medium text-zinc-900">Your profile</h2>
          <p className="mt-1 text-sm text-zinc-600">
            Height, position, hand, and primary skill calibrate pose features and (later) NBA style comps.
            Facts only — not “who you play like.”
          </p>
          <div className="mt-4">
            <ProfileQuestionnaireForm />
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-lg font-medium text-zinc-900">Upload clip</h2>
          <p className="mt-1 text-sm text-zinc-600">
            Short mp4 (~25s max). Individual drills process immediately; gameplay
            clips will ask you to box yourself in Phase 7.
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

        <p className="text-xs text-zinc-500">
          Individual clips run MediaPipe Pose after upload. Refresh is automatic while
          processing. See <code>PROJECT_PLAN.md</code>.
        </p>
      </section>
    </main>
  );
}
