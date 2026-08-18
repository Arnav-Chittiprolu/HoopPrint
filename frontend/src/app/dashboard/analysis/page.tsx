import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { CompPanel } from "@/components/comp-panel";
import { MechanicsPanel } from "@/components/mechanics-panel";

export default async function AnalysisPage() {
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

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Role analysis</h1>
      <p className="mt-1 max-w-2xl text-sm text-zinc-500">
        Match by what you do on the court, then keep named comparisons physically realistic.
        Height does not decide playing style.
      </p>
      <div className="mt-6">
        <CompPanel profileReady={profileReady} />
      </div>
      <div className="mt-5">
        <MechanicsPanel />
      </div>
    </main>
  );
}
