import {
  index,
  jsonb,
  pgEnum,
  pgTable,
  text,
  timestamp,
  uuid,
} from "drizzle-orm/pg-core";

export const jobStatus = pgEnum("job_status", [
  "queued",
  "processing",
  "complete",
  "failed",
]);

/**
 * One row per analysis request.
 *
 * Deliberately stores no media. `storageKey` points at the object store and is
 * nulled once the TTL sweep deletes the object, so a row can outlive the media
 * it describes without implying the media is still retrievable.
 */
export const analysisJobs = pgTable(
  "analysis_jobs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: text("user_id").notNull(),

    status: jobStatus("status").notNull().default("queued"),

    filename: text("filename"),
    mimeType: text("mime_type").notNull(),

    // Object-store key for the uploaded media. Nulled by the TTL sweep.
    storageKey: text("storage_key"),

    // Perceptual hash, kept after the media is gone so repeat uploads can be
    // recognised without retaining the image itself.
    phash: text("phash"),

    // The full AnalysisReport as returned by the inference service.
    report: jsonb("report"),

    error: text("error"),

    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    completedAt: timestamp("completed_at", { withTimezone: true }),

    // When the stored media must be deleted.
    ttlExpiresAt: timestamp("ttl_expires_at", { withTimezone: true }).notNull(),

    // Set when the TTL sweep or a user deletion request removed the media.
    mediaDeletedAt: timestamp("media_deleted_at", { withTimezone: true }),
  },
  (table) => [
    index("analysis_jobs_user_id_idx").on(table.userId),
    index("analysis_jobs_phash_idx").on(table.phash),
    // Drives the TTL sweep.
    index("analysis_jobs_ttl_idx").on(table.ttlExpiresAt),
  ],
);

export type AnalysisJob = typeof analysisJobs.$inferSelect;
export type NewAnalysisJob = typeof analysisJobs.$inferInsert;
