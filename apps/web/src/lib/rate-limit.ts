import { redisConnection } from "./queue";

/**
 * Fixed-window rate limiting, mirroring services/inference/app/pipeline/rate_limit.py
 * exactly: same Redis, same INCR+EXPIRE fixed-window counter, same fail-open
 * philosophy -- an unreachable Redis must not take the upload endpoint down,
 * only its rate limiting for the duration.
 */

let client: ReturnType<typeof redisConnection> | null = null;

function limiterClient() {
  if (!client) client = redisConnection();
  return client;
}

export class RateLimitExceededError extends Error {
  constructor(
    public readonly limit: number,
    public readonly windowSeconds: number,
  ) {
    super(`rate limit exceeded: ${limit} requests per ${windowSeconds}s`);
  }
}

/**
 * Throws RateLimitExceededError once `identifier` has made more than `limit`
 * requests for `scope` within the current window. Resolves silently
 * (fail-open) if Redis cannot be reached in time.
 */
export async function enforceRateLimit(
  scope: string,
  identifier: string,
  limit: number,
  windowSeconds: number,
): Promise<void> {
  const key = `ratelimit:${scope}:${identifier}`;

  let count: number;
  try {
    const redis = limiterClient();
    const pipeline = redis.multi();
    pipeline.incr(key);
    pipeline.expire(key, windowSeconds, "NX"); // only arms the TTL once
    const results = await pipeline.exec();
    count = Number(results?.[0]?.[1] ?? 0);
  } catch {
    // Best-effort: an unreachable limiter degrades to "unrestricted for this
    // request", not to a failed upload the user already waited on.
    return;
  }

  if (count > limit) {
    throw new RateLimitExceededError(limit, windowSeconds);
  }
}
