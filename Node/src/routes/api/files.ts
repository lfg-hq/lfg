import { Hono } from "hono";
import { requireAuth } from "../../auth/middleware.ts";
import { db } from "../../config/db.ts";
import { chatFiles } from "../../db/schema/chat.ts";
import { eq } from "drizzle-orm";
import { env } from "../../config/env.ts";
import * as path from "node:path";
import * as fs from "node:fs/promises";
import type { auth } from "../../auth/index.ts";

type AuthEnv = {
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
};

const files = new Hono<AuthEnv>();
files.use("*", requireAuth);

const UPLOADS_DIR = path.resolve("./uploads");

async function ensureUploadsDir() {
  await fs.mkdir(UPLOADS_DIR, { recursive: true });
}

// POST /api/files/upload
files.post("/upload", async (c) => {
  const user = c.get("user");
  const body = await c.req.parseBody();

  const file = body["file"] as File | undefined;
  const conversationId = body["conversation_id"] as string | undefined;

  if (!file) return c.json({ error: "No file provided" }, 400);

  await ensureUploadsDir();

  const ext = file.name.split(".").pop() ?? "";
  const filename = `${crypto.randomUUID()}.${ext}`;
  const filePath = path.join(UPLOADS_DIR, filename);

  const buffer = await file.arrayBuffer();
  await fs.writeFile(filePath, Buffer.from(buffer));

  // Insert into chatFiles if we have a conversation context
  let fileRecord = null;
  if (conversationId) {
    const [row] = await db
      .insert(chatFiles)
      .values({
        conversationId,
        filePath: `uploads/${filename}`,
        originalFilename: file.name,
        fileType: file.type,
        fileSize: file.size,
      })
      .returning();
    fileRecord = row;
  }

  return c.json({
    id: fileRecord?.id ?? null,
    filename,
    originalName: file.name,
    fileType: file.type,
    fileSize: file.size,
    path: `uploads/${filename}`,
  });
});

// GET /api/files/transcribe/:fileId — transcribe audio via OpenAI Whisper
files.get("/transcribe/:fileId", async (c) => {
  if (!env.OPENAI_API_KEY) {
    return c.json({ error: "OpenAI API key not configured" }, 503);
  }

  const { fileId } = c.req.param();
  const [fileRow] = await db
    .select()
    .from(chatFiles)
    .where(eq(chatFiles.id, fileId));

  if (!fileRow) return c.json({ error: "File not found" }, 404);

  const fullPath = path.resolve(fileRow.filePath);
  let fileData: Buffer;
  try {
    fileData = await fs.readFile(fullPath);
  } catch {
    return c.json({ error: "File not readable" }, 404);
  }

  // Call OpenAI Whisper
  const formData = new FormData();
  formData.append("file", new Blob([fileData], { type: fileRow.fileType ?? "audio/webm" }), fileRow.originalFilename);
  formData.append("model", "whisper-1");

  const res = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.OPENAI_API_KEY}` },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.text();
    return c.json({ error: `Whisper API error: ${err}` }, 500);
  }

  const data = (await res.json()) as { text: string };
  return c.json({ text: data.text, fileId });
});

export default files;
