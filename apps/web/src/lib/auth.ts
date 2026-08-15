import { authDisabled, DEV_USER_ID } from "./env";

/**
 * Resolve the current user id.
 *
 * When Clerk isn't configured (local development only — `authDisabled` throws in
 * production) every request is attributed to a single development user, so the
 * ownership checks downstream still run against a real value rather than being
 * skipped. That keeps the authorization path identical in both modes.
 */
export async function currentUserId(): Promise<string | null> {
  if (authDisabled()) return DEV_USER_ID;

  const { auth } = await import("@clerk/nextjs/server");
  const { userId } = await auth();
  return userId;
}
