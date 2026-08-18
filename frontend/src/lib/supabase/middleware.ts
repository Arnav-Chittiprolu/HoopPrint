import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    return supabaseResponse;
  }

  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => {
          supabaseResponse.cookies.set(name, value, options);
        });
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;
  const isAuthRoute = path.startsWith("/login") || path.startsWith("/signup");
  const isProtected = path.startsWith("/dashboard") || path.startsWith("/setup");

  if (!user && isProtected) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/login";
    redirectUrl.searchParams.set("next", path);
    return NextResponse.redirect(redirectUrl);
  }

  if (user) {
    const { data: profile } = await supabase
      .from("profiles")
      .select("display_name, height_in, position, dominant_hand, primary_skill")
      .eq("id", user.id)
      .maybeSingle();
    const complete = Boolean(
      profile?.display_name?.trim() &&
        profile?.height_in != null &&
        profile?.position &&
        profile?.dominant_hand &&
        profile?.primary_skill,
    );

    if (isAuthRoute) {
      const redirectUrl = request.nextUrl.clone();
      redirectUrl.pathname = complete ? "/dashboard" : "/setup";
      return NextResponse.redirect(redirectUrl);
    }

    if (path.startsWith("/dashboard") && !complete) {
      const redirectUrl = request.nextUrl.clone();
      redirectUrl.pathname = "/setup";
      return NextResponse.redirect(redirectUrl);
    }

    if (path.startsWith("/setup") && complete) {
      const redirectUrl = request.nextUrl.clone();
      redirectUrl.pathname = "/dashboard";
      return NextResponse.redirect(redirectUrl);
    }
  }

  return supabaseResponse;
}
