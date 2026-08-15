import { NextResponse } from "next/server";

/**
 * Clerk's middleware is only mounted when Clerk is actually configured. Without
 * keys the module isn't imported at all, so the app boots in development
 * without a Clerk account.
 */
const clerkConfigured =
  Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) &&
  Boolean(process.env.CLERK_SECRET_KEY);

async function passthrough() {
  return NextResponse.next();
}

export default clerkConfigured
  ? (await import("@clerk/nextjs/server")).clerkMiddleware()
  : passthrough;

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)"],
};
