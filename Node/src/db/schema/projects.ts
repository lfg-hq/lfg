import {
  sqliteTable,
  text,
  integer,
  index,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { users } from "./users.ts";

// ── Projects ────────────────────────────────────────────────────────

export const projects = sqliteTable(
  "project",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .unique()
      .$defaultFn(() => crypto.randomUUID()),
    name: text("name").notNull(),
    providedName: text("provided_name"),
    description: text("description"),
    ownerId: text("owner_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    status: text("status").notNull().default("active"), // active | archived | completed
    icon: text("icon").notNull().default("📋"),

    // Stack
    stack: text("stack").default(""),
    customProjectDir: text("custom_project_dir"),
    customInstallCmd: text("custom_install_cmd"),
    customDevCmd: text("custom_dev_cmd"),
    customDefaultPort: integer("custom_default_port"),

    // Linear integration
    linearTeamId: text("linear_team_id"),
    linearProjectId: text("linear_project_id"),
    linearSyncEnabled: integer("linear_sync_enabled", { mode: "boolean" }).notNull().default(false),

    // Preview
    previewTicketId: text("preview_ticket_id"), // FK handled in relations

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [index("project_owner_idx").on(t.ownerId)]
);

// ── Project Members ─────────────────────────────────────────────────

export const projectMembers = sqliteTable(
  "project_member",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    role: text("role").notNull().default("member"), // owner | admin | member | viewer
    status: text("status").notNull().default("active"),

    canEditFiles: integer("can_edit_files", { mode: "boolean" }).notNull().default(true),
    canManageTickets: integer("can_manage_tickets", { mode: "boolean" }).notNull().default(true),
    canChat: integer("can_chat", { mode: "boolean" }).notNull().default(true),
    canInviteMembers: integer("can_invite_members", { mode: "boolean" }).notNull().default(false),

    joinedAt: integer("joined_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    invitedById: text("invited_by_id").references(() => users.id, {
      onDelete: "set null",
    }),
  },
  (t) => [
    uniqueIndex("pm_project_user_unique").on(t.projectId, t.userId),
    index("pm_project_idx").on(t.projectId),
  ]
);

// ── Project Invitations ─────────────────────────────────────────────

export const projectInvitations = sqliteTable(
  "project_invitation",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    inviterId: text("inviter_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    email: text("email").notNull(),
    role: text("role").notNull().default("member"),
    token: text("token").notNull().unique(),
    status: text("status").notNull().default("pending"),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    expiresAt: integer("expires_at", { mode: "timestamp" }).notNull(),
    respondedAt: integer("responded_at", { mode: "timestamp" }),
  },
  (t) => [
    uniqueIndex("pi_project_email_unique").on(t.projectId, t.email),
    index("pi_project_idx").on(t.projectId),
  ]
);

// ── Project Environment Variables ───────────────────────────────────

export const projectEnvironmentVariables = sqliteTable(
  "project_environment_variable",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    key: text("key").notNull(),
    encryptedValue: text("encrypted_value").notNull(),
    isSecret: integer("is_secret", { mode: "boolean" }).notNull().default(true),
    isRequired: integer("is_required", { mode: "boolean" }).notNull().default(false),
    hasValue: integer("has_value", { mode: "boolean" }).notNull().default(true),
    description: text("description").default(""),
    createdById: text("created_by_id").references(() => users.id, {
      onDelete: "set null",
    }),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    uniqueIndex("pev_project_key_unique").on(t.projectId, t.key),
    index("pev_project_idx").on(t.projectId),
  ]
);

// ── Project Code Generation ─────────────────────────────────────────

export const projectCodeGenerations = sqliteTable("project_code_generation", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  projectId: text("project_id")
    .notNull()
    .unique()
    .references(() => projects.id, { onDelete: "cascade" }),
  folderName: text("folder_name").notNull().unique(),
  createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
});
