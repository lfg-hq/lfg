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
