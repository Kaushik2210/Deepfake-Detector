import { z } from "zod";

/**
 * Server-side environment. Parsed lazily so that importing this module in a
 * context that doesn't need every variable (e.g. a unit test) doesn't explode.
 */
const serverSchema = z.object({
  DATABASE_URL: z.string().url(),
  REDIS_URL: z.string().url(),

  S3_ENDPOINT: z.string().url(),
  S3_ACCESS_KEY_ID: z.string().min(1),
  S3_SECRET_ACCESS_KEY: z.string().min(1),
  S3_BUCKET: z.string().min(1),
  S3_REGION: z.string().default("auto"),

  INFERENCE_SERVICE_URL: z.string().url(),

  MEDIA_TTL_HOURS: z.coerce.number().int().positive().default(24),
  MAX_UPLOAD_BYTES: z.coerce.number().int().positive().default(25 * 1024 * 1024),
  MAX_VIDEO_BYTES: z.coerce.number().int().positive().default(100 * 1024 * 1024),

  CLERK_SECRET_KEY: z.string().optional(),
});

export type ServerEnv = z.infer<typeof serverSchema>;

let cached: ServerEnv | null = null;

export function serverEnv(): ServerEnv {
  if (cached) return cached;

  const parsed = serverSchema.safeParse(process.env);
  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((i) => `  ${i.path.join(".")}: ${i.message}`)
      .join("\n");
    throw new Error(`Invalid server environment:\n${issues}`);
  }

  cached = parsed.data;
  return cached;
}

/**
 * Clerk is optional in local development. When no publishable key is configured
 * the app runs in a single-user development mode rather than refusing to boot,
 * so the rest of the stack can be worked on without a Clerk account. This is
 * gated on NODE_ENV so it can never silently disable auth in production.
 */
export function authDisabled(): boolean {
  const hasKeys =
    Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) &&
    Boolean(process.env.CLERK_SECRET_KEY);

  if (hasKeys) return false;

  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "Clerk keys are required in production. Set NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY.",
    );
  }

  return true;
}

export const DEV_USER_ID = "dev-user";
