import { and, eq } from "drizzle-orm";
import { NextResponse } from "next/server";

import { db, schema } from "@/db";
import { currentUserId } from "@/lib/auth";
import { deleteMedia } from "@/lib/storage";

export const runtime = "nodejs";

async function loadOwnedJob(jobId: string, userId: string) {
  const [job] = await db()
    .select()
    .from(schema.analysisJobs)
    .where(
      and(
        eq(schema.analysisJobs.id, jobId),
        // Scoping by user means a wrong id and someone else's id are
        // indistinguishable from the outside — both simply 404.
        eq(schema.analysisJobs.userId, userId),
      ),
    )
    .limit(1);

  return job ?? null;
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const userId = await currentUserId();
  if (!userId) {
    return NextResponse.json({ error: "not authenticated" }, { status: 401 });
  }

  const { jobId } = await params;
  const job = await loadOwnedJob(jobId, userId);
  if (!job) {
    return NextResponse.json({ error: "unknown job" }, { status: 404 });
  }

  if (job.status === "complete") {
    return NextResponse.json({
      status: "complete",
      report: job.report,
      media_deleted_at: job.mediaDeletedAt?.toISOString() ?? null,
    });
  }

  if (job.status === "failed") {
    return NextResponse.json({ status: "failed", error: job.error ?? "analysis failed" });
  }

  return NextResponse.json({ status: job.status });
}

/**
 * Deletion endpoint required by DPDP Act 2023 and GDPR. Removes the stored media
 * immediately and drops the job row, rather than only flagging it.
 */
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const userId = await currentUserId();
  if (!userId) {
    return NextResponse.json({ error: "not authenticated" }, { status: 401 });
  }

  const { jobId } = await params;
  const job = await loadOwnedJob(jobId, userId);
  if (!job) {
    return NextResponse.json({ error: "unknown job" }, { status: 404 });
  }

  if (job.storageKey) {
    await deleteMedia(job.storageKey);
  }

  await db()
    .delete(schema.analysisJobs)
    .where(
      and(eq(schema.analysisJobs.id, jobId), eq(schema.analysisJobs.userId, userId)),
    );

  return new NextResponse(null, { status: 204 });
}
