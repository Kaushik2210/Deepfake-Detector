import {
  CreateBucketCommand,
  DeleteObjectCommand,
  GetObjectCommand,
  HeadBucketCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";

import { serverEnv } from "./env";

let client: S3Client | null = null;

function s3(): S3Client {
  if (client) return client;

  const env = serverEnv();
  client = new S3Client({
    endpoint: env.S3_ENDPOINT,
    region: env.S3_REGION,
    credentials: {
      accessKeyId: env.S3_ACCESS_KEY_ID,
      secretAccessKey: env.S3_SECRET_ACCESS_KEY,
    },
    // MinIO serves buckets as path segments rather than subdomains.
    forcePathStyle: true,
  });
  return client;
}

/** Create the media bucket if it isn't there. Safe to call repeatedly. */
export async function ensureBucket(): Promise<void> {
  const { S3_BUCKET } = serverEnv();
  try {
    await s3().send(new HeadBucketCommand({ Bucket: S3_BUCKET }));
  } catch {
    await s3().send(new CreateBucketCommand({ Bucket: S3_BUCKET }));
  }
}

export function mediaKey(jobId: string): string {
  return `media/${jobId}`;
}

export async function putMedia(
  jobId: string,
  body: Uint8Array,
  contentType: string,
): Promise<string> {
  const key = mediaKey(jobId);
  await s3().send(
    new PutObjectCommand({
      Bucket: serverEnv().S3_BUCKET,
      Key: key,
      Body: body,
      ContentType: contentType,
    }),
  );
  return key;
}

export async function getMedia(key: string): Promise<Uint8Array> {
  const response = await s3().send(
    new GetObjectCommand({ Bucket: serverEnv().S3_BUCKET, Key: key }),
  );
  if (!response.Body) {
    throw new Error(`object ${key} has no body`);
  }
  return response.Body.transformToByteArray();
}

/** Delete media. Missing objects are not an error — the TTL sweep may race a manual delete. */
export async function deleteMedia(key: string): Promise<void> {
  try {
    await s3().send(
      new DeleteObjectCommand({ Bucket: serverEnv().S3_BUCKET, Key: key }),
    );
  } catch (error) {
    const name = (error as { name?: string }).name;
    if (name !== "NoSuchKey" && name !== "NotFound") throw error;
  }
}
