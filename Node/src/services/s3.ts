/**
 * S3 storage service for project files.
 * Mirrors the Django ProjectFile.save_content() / file_content behaviour:
 *   - Key pattern: project_files/{internalProjectId}/{fileType}/{name}
 *   - When FILE_STORAGE_TYPE=s3: upload to S3, store s3Key in DB, clear content column
 *   - When FILE_STORAGE_TYPE=local: skip S3, content lives in DB
 *   - getContent(): if s3Key is set → fetch from S3; else → return DB content
 */

import {
  S3Client,
  PutObjectCommand,
  GetObjectCommand,
  DeleteObjectCommand,
} from "@aws-sdk/client-s3";
import { env } from "../config/env.ts";

// ── Client (lazy-initialised so non-S3 deployments pay no cost) ───────

let _client: S3Client | null = null;

function getClient(): S3Client {
  if (!_client) {
    _client = new S3Client({
      region: env.AWS_S3_REGION,
      credentials: {
        accessKeyId: env.AWS_ACCESS_KEY_ID,
        secretAccessKey: env.AWS_SECRET_ACCESS_KEY,
      },
    });
  }
  return _client;
}

export const isS3Enabled =
  env.FILE_STORAGE_TYPE === "s3" &&
  !!env.AWS_S3_BUCKET_NAME &&
  !!env.AWS_ACCESS_KEY_ID &&
  !!env.AWS_SECRET_ACCESS_KEY;

// ── Key builder ───────────────────────────────────────────────────────
// Matches Django: project_files/{project_id}/{file_type}/{name}

export function buildS3Key(projectId: string, fileType: string, name: string): string {
  const safeName = name.replace(/[^a-zA-Z0-9._\- ]/g, "_");
  return `project_files/${projectId}/${fileType}/${safeName}`;
}

// ── Upload ────────────────────────────────────────────────────────────

export async function uploadFile(key: string, content: string): Promise<void> {
  await getClient().send(
    new PutObjectCommand({
      Bucket: env.AWS_S3_BUCKET_NAME,
      Key: key,
      Body: content,
      ContentType: "text/plain; charset=utf-8",
    })
  );
}

// ── Download ──────────────────────────────────────────────────────────

export async function downloadFile(key: string): Promise<string> {
  const res = await getClient().send(
    new GetObjectCommand({
      Bucket: env.AWS_S3_BUCKET_NAME,
      Key: key,
    })
  );
  if (!res.Body) return "";
  // Bun / Node streaming body → string
  const chunks: Uint8Array[] = [];
  for await (const chunk of res.Body as AsyncIterable<Uint8Array>) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf-8");
}

// ── Delete ────────────────────────────────────────────────────────────

export async function deleteFile(key: string): Promise<void> {
  await getClient().send(
    new DeleteObjectCommand({
      Bucket: env.AWS_S3_BUCKET_NAME,
      Key: key,
    })
  );
}

// ── High-level helpers used by routes + tools ─────────────────────────

/**
 * Save file content.
 * Returns `{ s3Key, dbContent }` — exactly one will be non-null.
 * If S3 is enabled and upload succeeds, s3Key is set and dbContent is null.
 * If S3 is disabled or upload fails, dbContent is set and s3Key is null.
 */
export async function saveContent(
  projectId: string,
  fileType: string,
  name: string,
  content: string
): Promise<{ s3Key: string | null; dbContent: string | null }> {
  if (!isS3Enabled) {
    return { s3Key: null, dbContent: content };
  }

  const key = buildS3Key(projectId, fileType, name);
  try {
    await uploadFile(key, content);
    return { s3Key: key, dbContent: null };
  } catch (err) {
    console.error("[S3] Upload failed, falling back to DB:", err);
    return { s3Key: null, dbContent: content };
  }
}

/**
 * Retrieve file content — from S3 if s3Key is set, otherwise from the DB value.
 */
export async function getContent(
  s3Key: string | null | undefined,
  dbContent: string | null | undefined
): Promise<string> {
  if (s3Key) {
    try {
      return await downloadFile(s3Key);
    } catch (err) {
      console.error("[S3] Download failed, falling back to DB:", err);
    }
  }
  return dbContent ?? "";
}

/**
 * Delete file from S3 (no-op if S3 disabled or key missing).
 */
export async function deleteContent(s3Key: string | null | undefined): Promise<void> {
  if (isS3Enabled && s3Key) {
    try {
      await deleteFile(s3Key);
    } catch (err) {
      console.error("[S3] Delete failed:", err);
    }
  }
}
