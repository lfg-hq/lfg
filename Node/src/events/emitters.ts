import { bus } from "./bus.ts";
import type {
  TicketCreatedPayload,
  TicketUpdatedPayload,
  TicketStatusChangedPayload,
  TicketQueuedPayload,
  TicketCommentedPayload,
  DocumentCreatedPayload,
  DocumentUpdatedPayload,
  ProjectUpdatedPayload,
  AgentRunPayload,
} from "./types.ts";

// ── Ticket emitters ──────────────────────────────────────────────────

export function emitTicketCreated(payload: TicketCreatedPayload) {
  bus.emit({ type: "ticket.created", payload });
}

export function emitTicketUpdated(payload: TicketUpdatedPayload) {
  bus.emit({ type: "ticket.updated", payload });
}

export function emitTicketStatusChanged(payload: TicketStatusChangedPayload) {
  bus.emit({ type: "ticket.status_changed", payload });
}

export function emitTicketQueued(payload: TicketQueuedPayload) {
  bus.emit({ type: "ticket.queued", payload });
}

export function emitTicketCommented(payload: TicketCommentedPayload) {
  bus.emit({ type: "ticket.commented", payload });
}

// ── Document emitters ────────────────────────────────────────────────

export function emitDocumentCreated(payload: DocumentCreatedPayload) {
  bus.emit({ type: "document.created", payload });
}

export function emitDocumentUpdated(payload: DocumentUpdatedPayload) {
  bus.emit({ type: "document.updated", payload });
}

export function emitFileCreated(payload: DocumentCreatedPayload) {
  bus.emit({ type: "document.file_created", payload });
}

export function emitFileUpdated(payload: DocumentUpdatedPayload) {
  bus.emit({ type: "document.file_updated", payload });
}

// ── Project emitters ─────────────────────────────────────────────────

export function emitProjectUpdated(payload: ProjectUpdatedPayload) {
  bus.emit({ type: "project.updated", payload });
}

export function emitMemberAdded(payload: { projectId: string; userId: string }) {
  bus.emit({ type: "project.member_added", payload });
}

// ── Agent run emitters ───────────────────────────────────────────────

export function emitAgentRunCompleted(payload: AgentRunPayload) {
  bus.emit({ type: "agent_run.completed", payload });
}

export function emitAgentRunFailed(payload: AgentRunPayload) {
  bus.emit({ type: "agent_run.failed", payload });
}
