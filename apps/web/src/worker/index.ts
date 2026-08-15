/**
 * Standalone queue worker.
 *
 * Runs as its own process (`pnpm worker`), matching how it is deployed rather
 * than piggy-backing on the Next.js server. It owns two responsibilities:
 * consuming analysis jobs, and sweeping expired media.
 */
import "./load-env";

import { Worker } from "bullmq";
import { eq } from "drizzle-orm";

import { db, schema } from "@/db";
import { serverEnv } from "@/lib/env";
import { ANALYSIS_QUEUE, redisConnection, type AnalysisJobData } from "@/lib/queue";
import { ensureBucket, getMedia } from "@/lib/storage";
import { startTtlSweep } from "./ttl-sweep";

async function analyze(data: AnalysisJobData) {
  const env = serverEnv();
  const media = await getMedia(data.storageKey);

  const form = new FormData();
  form.append(
    "file",
    new Blob([media as BlobPart], { type: data.mimeType }),
    data.filename ?? "upload",
  );

  const response = await fetch(`${env.INFERENCE_SERVICE_URL}/v1/analyze`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(
      `inference service returned ${response.status}: ${detail.slice(0, 300)}`,
    );
  }

  return response.json();
}

async function main() {
  await ensureBucket();

  const worker = new Worker<AnalysisJobData>(
    ANALYSIS_QUEUE,
    async (job) => {
      const { jobId } = job.data;

      await db()
        .update(schema.analysisJobs)
        .set({ status: "processing" })
        .where(eq(schema.analysisJobs.id, jobId));

      const report = await analyze(job.data);

      await db()
        .update(schema.analysisJobs)
        .set({
          status: "complete",
          report,
          phash: report?.provenance?.phash ?? null,
          completedAt: new Date(),
        })
        .where(eq(schema.analysisJobs.id, jobId));

      return { jobId };
    },
    { connection: redisConnection(), concurrency: 2 },
  );

  worker.on("failed", async (job, error) => {
    if (!job) return;

    // Only give up once BullMQ has exhausted its retries.
    const attemptsAllowed = job.opts.attempts ?? 1;
    if (job.attemptsMade < attemptsAllowed) return;

    await db()
      .update(schema.analysisJobs)
      .set({ status: "failed", error: error.message, completedAt: new Date() })
      .where(eq(schema.analysisJobs.id, job.data.jobId));
  });

  worker.on("completed", (job) => {
    console.log(`[worker] completed ${job.data.jobId}`);
  });

  const stopSweep = startTtlSweep();
  console.log("[worker] listening on queue:", ANALYSIS_QUEUE);

  const shutdown = async () => {
    console.log("[worker] shutting down");
    stopSweep();
    await worker.close();
    process.exit(0);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((error) => {
  console.error("[worker] fatal:", error);
  process.exit(1);
});
