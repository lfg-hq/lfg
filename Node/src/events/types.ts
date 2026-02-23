// ── App Event Types ─────────────────────────────────────────────────
// All events emitted through the in-process event bus.
// When the orchestrator is added, subscribers can react to these events automatically.

export type TicketEventType =
  | "ticket.created"
  | "ticket.updated"
  | "ticket.status_changed"
  | "ticket.queued"
  | "ticket.commented";

export type DocumentEventType =
  | "document.created"      // PRD or implementation created
  | "document.updated"      // Implementation updated
  | "document.file_created" // Project file created
  | "document.file_updated";

export type ProjectEventType =
  | "project.updated"
  | "project.member_added";

export type AgentEventType =
  | "agent_run.completed"
  | "agent_run.failed";

export type AppEventType =
  | TicketEventType
  | DocumentEventType
  | ProjectEventType
  | AgentEventType;

// ── Payload shapes ───────────────────────────────────────────────────

export interface TicketCreatedPayload {
  projectId: string;
  ticketId: string;
  ticketName: string;
  priority: string;
  stageId: string | null;
}

export interface TicketUpdatedPayload {
  ticketId: string;
  projectId: string;
  changes: Record<string, unknown>;
}

export interface TicketStatusChangedPayload {
  ticketId: string;
  projectId: string;
  oldStatus?: string;
  newStatus: string;
}

export interface TicketQueuedPayload {
  ticketId: string;
  projectId: string;
  notes?: string;
}

export interface TicketCommentedPayload {
  ticketId: string;
  projectId: string;
  message: string;
  logType: string;
}

export interface DocumentCreatedPayload {
  projectId: string;
  documentId: string;
  documentType: string;
  name?: string;
}

export interface DocumentUpdatedPayload {
  projectId: string;
  documentId: string;
  documentType: string;
}

export interface ProjectUpdatedPayload {
  projectId: string;
  changes: Record<string, unknown>;
}

export interface AgentRunPayload {
  agentRunId: string;
  projectId: string;
  status: "completed" | "failed";
  error?: string;
}

// ── Discriminated union ───────────────────────────────────────────────

export type AppEvent =
  | { type: "ticket.created"; payload: TicketCreatedPayload }
  | { type: "ticket.updated"; payload: TicketUpdatedPayload }
  | { type: "ticket.status_changed"; payload: TicketStatusChangedPayload }
  | { type: "ticket.queued"; payload: TicketQueuedPayload }
  | { type: "ticket.commented"; payload: TicketCommentedPayload }
  | { type: "document.created"; payload: DocumentCreatedPayload }
  | { type: "document.updated"; payload: DocumentUpdatedPayload }
  | { type: "document.file_created"; payload: DocumentCreatedPayload }
  | { type: "document.file_updated"; payload: DocumentUpdatedPayload }
  | { type: "project.updated"; payload: ProjectUpdatedPayload }
  | { type: "project.member_added"; payload: { projectId: string; userId: string } }
  | { type: "agent_run.completed"; payload: AgentRunPayload }
  | { type: "agent_run.failed"; payload: AgentRunPayload };
