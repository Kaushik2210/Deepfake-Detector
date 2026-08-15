/**
 * Media retention sweep.
 *
 * Privacy principle 4: server-side media is deleted after its TTL. The job row
 * survives so the user can still see the report they were given, but the media
 * it was derived from is gone and `mediaDeletedAt` records when.
 */
import { and, eq, isNotNull, isNull, lte } from "drizzle-orm";

import { db, schema } from "@/db";
import { deleteMedia } from "@/lib/storage";

const SWEEP_INTERVAL_MS = 5 * 60 * 1000;

export async function sweepExpiredMedia(now: Date = new Date()): Promise<number> {
  const expired = await db()
    .select({
      id: schema.analysisJobs.id,
      storageKey: schema.analysisJobs.storageKey,
    })
    .from(schema.analysisJobs)
    .where(
      and(
        lte(schema.analysisJobs.ttlExpiresAt, now),
        isNotNull(schema.analysisJobs.storageKey),
        isNull(schema.analysisJobs.mediaDeletedAt),
      ),
    )
    .limit(500);

  let deleted = 0;

  for (const job of expired) {
    if (!job.storageKey) continue;

    try {
      await deleteMedia(job.storageKey);
      await db()
        .update(schema.analysisJobs)
        .set({ storageKey: null, mediaDeletedAt: new Date() })
        .where(eq(schema.analysisJobs.id, job.id));
      deleted += 1;
    } catch (error) {
      // Leave the row untouched so the next sweep retries it rather than
      // marking media deleted that may still exist.
      console.error(`[ttl-sweep] failed to delete ${job.storageKey}:`, error);
    }
  }

  if (deleted > 0) {
    console.log(`[ttl-sweep] deleted media for ${deleted} expired job(s)`);
  }

  return deleted;
}

export function startTtlSweep(): () => void {
  void sweepExpiredMedia().catch((error) =>
    console.error("[ttl-sweep] initial sweep failed:", error),
  );

  const timer = setInterval(() => {
    void sweepExpiredMedia().catch((error) =>
      console.error("[ttl-sweep] sweep failed:", error),
    );
  }, SWEEP_INTERVAL_MS);

  return () => clearInterval(timer);
}
