import { EventEmitter } from "node:events";
import type { AppEvent, AppEventType } from "./types.ts";

// ── Typed event bus ──────────────────────────────────────────────────
// In-process pub/sub using composition over inheritance to avoid
// EventEmitter signature conflicts. Swap to Redis/NATS later for multi-server.

class AppEventBus {
  private emitter = new EventEmitter();

  constructor() {
    this.emitter.setMaxListeners(50);
  }

  /** Publish an event to all subscribers. */
  emit<E extends AppEvent>(event: E): void {
    if (process.env["NODE_ENV"] !== "production") {
      console.log(`[event] ${event.type}`, JSON.stringify(event.payload));
    }
    this.emitter.emit(event.type, event);
  }

  /** Subscribe to a specific event type. */
  on<T extends AppEventType>(
    eventType: T,
    handler: (event: Extract<AppEvent, { type: T }>) => void
  ): void {
    this.emitter.on(eventType, handler as (...args: unknown[]) => void);
  }

  /** Subscribe once to a specific event type. */
  once<T extends AppEventType>(
    eventType: T,
    handler: (event: Extract<AppEvent, { type: T }>) => void
  ): void {
    this.emitter.once(eventType, handler as (...args: unknown[]) => void);
  }

  /** Remove a specific handler. */
  off<T extends AppEventType>(
    eventType: T,
    handler: (event: Extract<AppEvent, { type: T }>) => void
  ): void {
    this.emitter.off(eventType, handler as (...args: unknown[]) => void);
  }
}

export const bus = new AppEventBus();

/**
 * Convenience shorthand: emit an event using flat payload fields.
 * Usage: emit({ type: "ticket.queued", ticketId: "...", projectId: "..." })
 * The `type` field is extracted and the rest becomes the payload.
 */
export function emit(event: FlatEvent): void {
  const { type, ...payload } = event;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  bus.emit({ type, payload } as any);
}

type FlatEvent =
  | { type: "ticket.status_changed"; ticketId: string; status: string; message?: string }
  | { type: "ticket.tasks_updated"; ticketId: string; taskIds: string[] }
  | { type: "ticket.input_requested"; ticketId: string; question: string; options?: string[] }
  | { type: "ticket.chat_message"; ticketId: string; message: string; sender: string }
  | { type: "ticket.execution_started"; ticketId: string; sandboxId: string }
  | { type: "ticket.execution_finished"; ticketId: string; status: "complete" | "failed"; durationMs?: number }
  | { type: "ticket.queued"; ticketId: string; projectId: string; notes?: string }
  | { type: "ticket.commented"; ticketId: string; projectId: string; message: string; logType: string };
