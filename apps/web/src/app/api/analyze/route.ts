import { randomUUID } from "node:crypto";
import { NextResponse } from "next/server";

import { db, schema } from "@/db";
import { currentUserId } from "@/lib/auth";
import { serverEnv } from "@/lib/env";
import { analysisQueue } from "@/lib/queue";
import { ensureBucket, putMedia } from "@/lib/storage";

export const runtime = "nodejs";

const ACCEPTED_IMAGE = new Set(["image/jpeg", "image/png", "image/webp", "image/bmp"]);
const ACCEPTED_VIDEO = new Set([
  "video/mp4",
  "video/quicktime",
  "video/webm",
  "video/x-matroska",
]);
const ACCEPTED_AUDIO = new Set([
  "audio/wav",
  "audio/x-wav",
  "audio/flac",
  "audio/x-flac",
  "audio/ogg",
  "audio/mpeg",
]);
const ACCEPTED = new Set([...ACCEPTED_IMAGE, ...ACCEPTED_VIDEO, ...ACCEPTED_AUDIO]);

export async function POST(request: Request) {
  const userId = await currentUserId();
  if (!userId) {
    return NextResponse.json({ error: "not authenticated" }, { status: 401 });
  }

  const env = serverEnv();
  const form = await request.formData();

  // Consent is a hard gate, not a UI nicety: nothing is stored or uploaded
  // until the user has explicitly agreed to this specific upload.
  if (form.get("consent") !== "true") {
    return NextResponse.json(
      { error: "explicit consent is required before upload" },
      { status: 400 },
    );
  }

  const file = form.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "no file provided" }, { status: 400 });
  }

  if (!ACCEPTED.has(file.type)) {
    return NextResponse.json(
      { error: `unsupported type ${file.type || "unknown"}` },
      { status: 415 },
    );
  }

  if (file.size === 0) {
    return NextResponse.json({ error: "empty file" }, { status: 400 });
  }

  const isVideo = ACCEPTED_VIDEO.has(file.type);
  const isAudio = ACCEPTED_AUDIO.has(file.type);
  const sizeLimit = isVideo
    ? env.MAX_VIDEO_BYTES
    : isAudio
      ? env.MAX_AUDIO_BYTES
      : env.MAX_UPLOAD_BYTES;

  if (file.size > sizeLimit) {
    return NextResponse.json(
      { error: `file exceeds ${sizeLimit} bytes` },
      { status: 413 },
    );
  }

  const jobId = randomUUID();
  const ttlExpiresAt = new Date(Date.now() + env.MEDIA_TTL_HOURS * 60 * 60 * 1000);

  await ensureBucket();
  const storageKey = await putMedia(
    jobId,
    new Uint8Array(await file.arrayBuffer()),
    file.type,
  );

  await db().insert(schema.analysisJobs).values({
    id: jobId,
    userId,
    status: "queued",
    filename: file.name,
    mimeType: file.type,
    storageKey,
    ttlExpiresAt,
  });

  await analysisQueue().add("analyze", {
    jobId,
    storageKey,
    filename: file.name,
    mimeType: file.type,
  });

  return NextResponse.json(
    { job_id: jobId, status: "queued", ttl_expires_at: ttlExpiresAt.toISOString() },
    { status: 202 },
  );
}
