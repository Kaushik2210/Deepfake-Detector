import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

/**
 * Clerk's middleware is only applied when Clerk is actually configured, so the
 * app boots in development without a Clerk account.
 *
 * The import is static and the choice is made synchronously. An earlier version
 * used `await import(...)` at module scope, which made this a top-level-await
 * module — unsupported in the Edge runtime middleware executes in, and Next
 * warned it could fail at runtime. Importing `clerkMiddleware` without calling
 * it is harmless when no keys are set.
 */
const clerkConfigured =
  Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) &&
  Boolean(process.env.CLERK_SECRET_KEY);

export default clerkConfigured ? clerkMiddleware() : () => NextResponse.next();

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)"],
};
