import { streamText, stepCountIs } from "ai";
import { db } from "../config/db.ts";
import { messages, conversations, modelSelections, agentRoles } from "../db/schema/chat.ts";
import { profiles, llmApiKeys } from "../db/schema/users.ts";
import { projects } from "../db/schema/projects.ts";
import { eq, asc, desc } from "drizzle-orm";
import { getModel, DEFAULT_MODEL_KEY } from "./provider.ts";
import { toolsProduct, toolsTurbo } from "./tools/index.ts";
import { setDocumentWsBroadcast, setTicketWsBroadcast } from "./tools/index.ts";
import { setMiscWsBroadcast } from "./tools/index.ts";
import { getProductSystemPrompt } from "./prompts/product.ts";
import { broadcastToUser } from "../ws/connection-manager.ts";
import type { ServerWebSocket } from "bun";
import type { WsData } from "../ws/types.ts";

const MAX_HISTORY = 20; // messages to load for context
const FLUSH_CHARS = 80;
const FLUSH_MS = 80;

// ── Tool names whose arguments should be streamed to the right panel ──────────
const DOCUMENT_STREAM_TOOLS = new Set([
  "streamDocumentContent",
]);

function toolFileType(_toolName: string, accumulated: string): string {
  // streamDocumentContent carries fileType in args
  const m = accumulated.match(/"fileType"\s*:\s*"([^"\\]*)"/);
  return m?.[1] ?? "document";
}

// State for extracting "content" field value from streaming JSON args
interface DocStreamState {
  toolName: string;
  accumulated: string;
  contentStartPos: number | null; // position AFTER the opening quote of content value
  lastSentPos: number;
}

// Advance through `state.accumulated` starting at `lastSentPos`, decode JSON
// escapes, and return any newly available content characters.
function drainContentDelta(state: DocStreamState): string {
  if (state.contentStartPos === null) return "";
  const slice = state.accumulated.slice(state.lastSentPos);
  let out = "";
  let i = 0;
  while (i < slice.length) {
    const ch = slice[i];
    if (ch === '"') { i++; break; }            // end of JSON string value
    if (ch !== "\\") { out += ch; i++; continue; }
    if (i + 1 >= slice.length) break;           // incomplete escape — wait
    const esc = slice[i + 1]!;
    if (esc === "u") {
      if (i + 5 >= slice.length) break;         // incomplete unicode — wait
      out += String.fromCharCode(parseInt(slice.slice(i + 2, i + 6), 16));
      i += 6;
    } else {
      const MAP: Record<string, string> = {
        '"': '"', "\\": "\\", n: "\n", t: "\t", r: "\r", b: "\b", f: "\f", "/": "/",
      };
      out += MAP[esc] ?? esc;
      i += 2;
    }
  }
  state.lastSentPos += i;
  return out;
}

// Wire up the WS broadcaster for streaming tools
const wsBroadcast = (userId: string, data: object) => broadcastToUser(userId, data);
setDocumentWsBroadcast(wsBroadcast);
setTicketWsBroadcast(wsBroadcast);
setMiscWsBroadcast(wsBroadcast);

export interface StreamRequest {
  ws: ServerWebSocket<WsData>;
  userId: string;
  userMessage: string;
  conversationId?: string;
  projectId?: string;
  turboMode?: boolean;
  userRole?: string;
  abortController: AbortController;
}

export async function handleStream(req: StreamRequest): Promise<{ conversationId: string }> {
  const { ws, userId, userMessage, projectId, turboMode, abortController } = req;

  // ── 1. Resolve or create conversation ───────────────────────────────────────
  let convId = req.conversationId;
  if (!convId) {
    const [conv] = await db
      .insert(conversations)
      .values({ userId, projectId: projectId ?? null, title: userMessage.slice(0, 50) })
      .returning();
    convId = conv!.id;
    // Notify client of new conversation
    ws.send(JSON.stringify({ type: "conversation_created", conversationId: convId }));
  }

  // ── 2. Save user message ─────────────────────────────────────────────────────
  await db.insert(messages).values({
    conversationId: convId,
    role: "user",
    content: userMessage,
  });

  // ── 3. Load recent history ───────────────────────────────────────────────────
  const history = await db
    .select()
    .from(messages)
    .where(eq(messages.conversationId, convId))
    .orderBy(desc(messages.createdAt))
    .limit(MAX_HISTORY);

  const contextMessages = history
    .reverse()
    .map((m) => ({ role: m.role as "user" | "assistant" | "system", content: m.content }));

  // ── 4. Resolve model & API keys ──────────────────────────────────────────────
  const [modelSel] = await db
    .select()
    .from(modelSelections)
    .where(eq(modelSelections.userId, userId));

  const [apiKeys] = await db
    .select()
    .from(llmApiKeys)
    .where(eq(llmApiKeys.userId, userId));

  const modelKey = modelSel?.selectedModel ?? DEFAULT_MODEL_KEY;
  const userApiKeys = apiKeys
    ? { anthropic: apiKeys.anthropicApiKey ?? undefined, openai: apiKeys.openaiApiKey ?? undefined, google: apiKeys.googleApiKey ?? undefined }
    : undefined;

  let model;
  try {
    model = getModel(modelKey, userApiKeys);
  } catch {
    model = getModel(DEFAULT_MODEL_KEY);
  }

  // ── 5. Select system prompt & tools ─────────────────────────────────────────
  const [role] = await db
    .select()
    .from(agentRoles)
    .where(eq(agentRoles.userId, userId));

  const agentRole = role?.name ?? "product_analyst";
  const isTurbo = turboMode ?? role?.turboMode ?? false;

  const tools = isTurbo ? toolsTurbo : toolsProduct;

  // Resolve the public URL projectId → internal projects.id so tools insert
  // records with the correct FK value (projectPrds.projectId, etc. all reference
  // projects.id, not the public-facing projects.projectId).
  let internalProjectId = projectId;
  if (projectId) {
    const [proj] = await db
      .select({ id: projects.id })
      .from(projects)
      .where(eq(projects.projectId, projectId));
    if (proj) internalProjectId = proj.id;
  }

  const systemPrompt = getProductSystemPrompt({ userId, projectId: internalProjectId });

  // ── 6. Stream with AI SDK ────────────────────────────────────────────────────
  let fullResponse = "";
  let chunkBuffer = "";
  let lastFlush = Date.now();
  let streamError: Error | null = null;

  const flush = () => {
    if (!chunkBuffer) return;
    ws.send(JSON.stringify({ type: "ai_chunk", chunk: chunkBuffer, is_final: false }));
    chunkBuffer = "";
    lastFlush = Date.now();
  };

  try {
    const result = streamText({
      model,
      system: systemPrompt,
      messages: contextMessages,
      tools,
      stopWhen: stepCountIs(80),
      abortSignal: abortController.signal,
      onStepFinish: ({ toolCalls }) => {
        if (!toolCalls?.length) return;
        flush();
        for (const tc of toolCalls) {
          // Skip document streaming tools — the panel was already opened and
          // populated via tool-input-delta events; a generic notification here
          // would cause a redundant tab-switch / reload.
          if (DOCUMENT_STREAM_TOOLS.has(tc.toolName)) continue;
          ws.send(JSON.stringify({
            type: "ai_chunk",
            chunk: "",
            is_final: false,
            is_notification: true,
            notification_type: tc.toolName,
            function_name: tc.toolName,
          }));
        }
      },
    });

    // ── Use fullStream so we can intercept tool-input-delta events and forward
    //    document content character-by-character as the model generates it.
    const docStreams = new Map<string, DocStreamState>();

    for await (const event of result.fullStream) {
      if (abortController.signal.aborted) break;

      switch (event.type) {

        case "text-delta": {
          fullResponse += event.text;
          chunkBuffer += event.text;
          const now = Date.now();
          if (chunkBuffer.length >= FLUSH_CHARS || now - lastFlush >= FLUSH_MS) flush();
          break;
        }

        case "tool-input-start": {
          if (DOCUMENT_STREAM_TOOLS.has(event.toolName)) {
            docStreams.set(event.id, {
              toolName: event.toolName,
              accumulated: "",
              contentStartPos: null,
              lastSentPos: 0,
            });
            // Open the panel immediately so the user sees it before content arrives
            flush();
            ws.send(JSON.stringify({
              type: "ai_chunk",
              is_notification: true,
              notification_type: "file_stream",
              file_type: "document", // refined to actual type once args arrive
              content_chunk: "",
              is_complete: false,
            }));
          }
          break;
        }

        case "tool-input-delta": {
          const st = docStreams.get(event.id);
          if (!st) break;

          st.accumulated += event.delta;

          // Try to locate the start of the "content" value in the JSON args
          if (st.contentStartPos === null) {
            const m = st.accumulated.match(/"content"\s*:\s*"/);
            if (m && m.index !== undefined) {
              st.contentStartPos = m.index + m[0].length;
              st.lastSentPos = st.contentStartPos;
            }
          }

          const chunk = drainContentDelta(st);
          if (chunk) {
            flush(); // flush any buffered chat text first
            ws.send(JSON.stringify({
              type: "ai_chunk",
              is_notification: true,
              notification_type: "file_stream",
              file_type: toolFileType(st.toolName, st.accumulated),
              content_chunk: chunk,
              is_complete: false,
            }));
          }
          break;
        }

        // tool-call fires once args are fully generated; execute() has NOT run yet.
        // Nothing extra needed here — execute() handles DB save + final notify.

        default:
          break;
      }
    }

    flush(); // send any remaining buffered text

  } catch (err: any) {
    if (err?.name !== "AbortError") {
      streamError = err;
    }
  }

  // ── 7. Save assistant response ───────────────────────────────────────────────
  const finalContent = streamError
    ? `${fullResponse}\n\n*Error: ${streamError.message}*`
    : fullResponse || "*Generation stopped*";

  if (finalContent) {
    await db.insert(messages).values({
      conversationId: convId,
      role: "assistant",
      content: finalContent,
    });
  }

  // ── 8. Send final signal ─────────────────────────────────────────────────────
  ws.send(JSON.stringify({
    type: "ai_chunk",
    chunk: streamError ? `\n\n*Error: ${streamError.message}*` : "",
    is_final: true,
    conversation_id: convId,
    projectId: projectId ?? null,
  }));

  // ── 9. Auto-generate title for new conversations ─────────────────────────────
  const isNewConv = !req.conversationId;
  if (isNewConv && fullResponse && !abortController.signal.aborted) {
    generateTitle(convId, userMessage, fullResponse, model).catch(() => {});
  }

  return { conversationId: convId };
}

async function generateTitle(
  convId: string,
  userMessage: string,
  assistantResponse: string,
  model: ReturnType<typeof getModel>
) {
  try {
    const result = await streamText({
      model,
      messages: [
        {
          role: "user",
          content: `Generate a short, descriptive title (5 words max) for this conversation based on the first exchange. Respond with ONLY the title, no quotes or punctuation.\n\nUser: ${userMessage.slice(0, 200)}\nAssistant: ${assistantResponse.slice(0, 200)}`,
        },
      ],
      maxOutputTokens: 20,
    });

    let title = "";
    for await (const chunk of result.textStream) {
      title += chunk;
    }
    title = title.trim().replace(/^["']|["']$/g, "");

    if (title) {
      await db.update(conversations).set({ title, updatedAt: new Date() }).where(eq(conversations.id, convId));
    }
  } catch {
    // Title generation failing is non-critical
  }
}
