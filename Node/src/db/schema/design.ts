import {
  sqliteTable,
  text,
  integer,
  index,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { projects } from "./projects.ts";

// ── Project Design Features ─────────────────────────────────────────

export const projectDesignFeatures = sqliteTable(
  "project_design_feature",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    conversationId: text("conversation_id"), // FK set in relations
    featureName: text("feature_name").notNull(),
    featureDescription: text("feature_description").default(""),
    explainer: text("explainer").default(""),
    platform: text("platform").notNull().default("web"), // web | mobile

    cssStyle: text("css_style").default(""),
    commonElements: text("common_elements", { mode: "json" }).default([]),
    pages: text("pages", { mode: "json" }).default([]),
    entryPageId: text("entry_page_id").default(""),
    featureConnections: text("feature_connections", { mode: "json" }).default([]),
    canvasPosition: text("canvas_position", { mode: "json" }).default({}),

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    uniqueIndex("pdf_project_name_unique").on(t.projectId, t.featureName),
    index("pdf_project_idx").on(t.projectId),
  ]
);

// ── Design Canvases ─────────────────────────────────────────────────

export const designCanvases = sqliteTable(
  "design_canvas",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    description: text("description").default(""),
    isDefault: integer("is_default", { mode: "boolean" }).notNull().default(false),

    featurePositions: text("feature_positions", { mode: "json" }).default({}),
    visibleFeatures: text("visible_features", { mode: "json" }).default([]),

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    uniqueIndex("dc_project_name_unique").on(t.projectId, t.name),
    index("dc_project_idx").on(t.projectId),
    index("dc_project_default_idx").on(t.projectId, t.isDefault),
  ]
);
