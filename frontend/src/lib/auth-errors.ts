/** Map Supabase auth errors to clearer user-facing messages. */
export function formatAuthError(message: string): string {
  const lower = message.toLowerCase();

  if (lower.includes("email rate limit") || lower.includes("over_email_send_rate_limit")) {
    return (
      "Supabase email rate limit reached. For local dev: Supabase Dashboard → " +
      "Authentication → Providers → Email → turn OFF “Confirm email”, then try again " +
      "in ~15 minutes. Or create your user manually under Authentication → Users."
    );
  }

  if (lower.includes("user already registered")) {
    return "An account with this email already exists. Try signing in instead.";
  }

  return message;
}
