CREATE TYPE "public"."job_status" AS ENUM('queued', 'processing', 'complete', 'failed');--> statement-breakpoint
CREATE TABLE "analysis_jobs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"status" "job_status" DEFAULT 'queued' NOT NULL,
	"filename" text,
	"mime_type" text NOT NULL,
	"storage_key" text,
	"phash" text,
	"report" jsonb,
	"error" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"completed_at" timestamp with time zone,
	"ttl_expires_at" timestamp with time zone NOT NULL,
	"media_deleted_at" timestamp with time zone
);
--> statement-breakpoint
CREATE INDEX "analysis_jobs_user_id_idx" ON "analysis_jobs" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX "analysis_jobs_phash_idx" ON "analysis_jobs" USING btree ("phash");--> statement-breakpoint
CREATE INDEX "analysis_jobs_ttl_idx" ON "analysis_jobs" USING btree ("ttl_expires_at");