import { Queue } from "bullmq";
import IORedis from "ioredis";

import { serverEnv } from "./env";

export const ANALYSIS_QUEUE = "analysis";

export interface AnalysisJobData {
  jobId: string;
  storageKey: string;
  filename: string | null;
  mimeType: string;
}

/**
 * BullMQ requires maxRetriesPerRequest to be null on connections used by a
 * Worker, otherwise it refuses to start. Sharing one factory keeps the producer
 * and consumer connections configured identically.
 */
export function redisConnection(): IORedis {
  return new IORedis(serverEnv().REDIS_URL, { maxRetriesPerRequest: null });
}

let queue: Queue<AnalysisJobData> | null = null;

export function analysisQueue(): Queue<AnalysisJobData> {
  if (!queue) {
    queue = new Queue<AnalysisJobData>(ANALYSIS_QUEUE, {
      connection: redisConnection(),
      defaultJobOptions: {
        attempts: 2,
        backoff: { type: "exponential", delay: 2000 },
        removeOnComplete: { count: 100 },
        removeOnFail: { count: 100 },
      },
    });
  }
  return queue;
}
