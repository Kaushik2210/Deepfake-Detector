import { z } from "zod";
import { AnalysisReportSchema } from "./analysis-report.js";

/** POST /v1/analyze (JSON-URL variant; multipart form-data is handled outside Zod at the transport layer) */
export const AnalyzeByUrlRequestSchema = z.object({
  url: z.string().url(),
});

export const AnalyzeJobResponseSchema = z.object({
  job_id: z.string(),
  status: z.enum(["queued", "processing", "complete", "failed"]),
});

/** GET /v1/analyze/:job_id */
export const AnalyzeJobStatusResponseSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("queued") }),
  z.object({ status: z.literal("processing"), progress: z.number().min(0).max(1).optional() }),
  z.object({ status: z.literal("complete"), report: AnalysisReportSchema }),
  z.object({ status: z.literal("failed"), error: z.string() }),
]);

/** POST /v1/analyze/hash */
export const AnalyzeByHashRequestSchema = z.object({
  phash: z.string(),
});

/** GET /v1/health */
export const HealthResponseSchema = z.object({
  status: z.enum(["ok", "degraded", "down"]),
  model_versions: z.record(z.string(), z.string()),
  models_loaded: z.boolean(),
});

export type AnalyzeByUrlRequest = z.infer<typeof AnalyzeByUrlRequestSchema>;
export type AnalyzeJobResponse = z.infer<typeof AnalyzeJobResponseSchema>;
export type AnalyzeJobStatusResponse = z.infer<typeof AnalyzeJobStatusResponseSchema>;
export type AnalyzeByHashRequest = z.infer<typeof AnalyzeByHashRequestSchema>;
export type HealthResponse = z.infer<typeof HealthResponseSchema>;
