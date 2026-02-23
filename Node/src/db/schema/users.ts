import {
  sqliteTable,
  text,
  integer,
  index,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";

// ── Better Auth core tables ──────────────────────────────────────────
// Better Auth manages these automatically; we declare them so Drizzle
// knows the shape and we can reference them in relations / queries.

export const users = sqliteTable("user", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  emailVerified: integer("email_verified", { mode: "boolean" }).notNull().default(false),
  image: text("image"),
  createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
});

export const sessions = sqliteTable("session", {
  id: text("id").primaryKey(),
  expiresAt: integer("expires_at", { mode: "timestamp" }).notNull(),
  token: text("token").notNull().unique(),
  createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  userId: text("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
});

export const accounts = sqliteTable("account", {
  id: text("id").primaryKey(),
  accountId: text("account_id").notNull(),
  providerId: text("provider_id").notNull(),
  userId: text("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  idToken: text("id_token"),
  accessTokenExpiresAt: integer("access_token_expires_at", { mode: "timestamp" }),
  refreshTokenExpiresAt: integer("refresh_token_expires_at", { mode: "timestamp" }),
  scope: text("scope"),
  password: text("password"),
  createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
});

export const verifications = sqliteTable("verification", {
  id: text("id").primaryKey(),
  identifier: text("identifier").notNull(),
  value: text("value").notNull(),
  expiresAt: integer("expires_at", { mode: "timestamp" }).notNull(),
  createdAt: integer("created_at", { mode: "timestamp" }),
  updatedAt: integer("updated_at", { mode: "timestamp" }),
});

// ── Profile (extends user) ───────────────────────────────────────────

export const profiles = sqliteTable("profile", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  userId: text("user_id")
    .notNull()
    .unique()
    .references(() => users.id, { onDelete: "cascade" }),
  bio: text("bio").default(""),
  avatar: text("avatar"),
  sidebarCollapsed: integer("sidebar_collapsed", { mode: "boolean" }).notNull().default(false),
  emailVerified: integer("email_verified", { mode: "boolean" }).notNull().default(false),
  hasSeenOnboarding: integer("has_seen_onboarding", { mode: "boolean" }).notNull().default(false),

  // Claude Code CLI
  claudeCodeAuthenticated: integer("claude_code_authenticated", { mode: "boolean" })
    .notNull()
    .default(false),
  claudeCodeS3Key: text("claude_code_s3_key"),
  claudeCodeCredentials: text("claude_code_credentials"),
  claudeCodeCredentialsUpdatedAt: integer("claude_code_credentials_updated_at", { mode: "timestamp" }),
  cliApiKey: text("cli_api_key").unique(),

  // Organization context
  currentOrganizationId: text("current_organization_id"),

  allowProjectInvitations: integer("allow_project_invitations", { mode: "boolean" })
    .notNull()
    .default(true),

  createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
});

// ── LLM API Keys ────────────────────────────────────────────────────

export const llmApiKeys = sqliteTable("llm_api_key", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  userId: text("user_id")
    .notNull()
    .unique()
    .references(() => users.id, { onDelete: "cascade" }),
  openaiApiKey: text("openai_api_key"),
  anthropicApiKey: text("anthropic_api_key"),
  xaiApiKey: text("xai_api_key"),
  googleApiKey: text("google_api_key"),
  freeTrial: integer("free_trial", { mode: "boolean" }).notNull().default(true),
  usePersonalLlmKeys: integer("use_personal_llm_keys", { mode: "boolean" })
    .notNull()
    .default(false),
});

// ── External Services API Keys ──────────────────────────────────────

export const externalServicesApiKeys = sqliteTable("external_services_api_key", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  userId: text("user_id")
    .notNull()
    .unique()
    .references(() => users.id, { onDelete: "cascade" }),
  linearApiKey: text("linear_api_key"),
  jiraApiKey: text("jira_api_key"),
  notionApiKey: text("notion_api_key"),
  googleDocsApiKey: text("google_docs_api_key"),
});

// ── Application State ───────────────────────────────────────────────

export const applicationState = sqliteTable("application_state", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  userId: text("user_id")
    .notNull()
    .unique()
    .references(() => users.id, { onDelete: "cascade" }),
  sidebarMinimized: integer("sidebar_minimized", { mode: "boolean" }).notNull().default(false),
  lastSelectedModel: text("last_selected_model")
    .notNull()
    .default("gpt-5-mini"),
  lastSelectedRole: text("last_selected_role")
    .notNull()
    .default("product_analyst"),
  turboModeEnabled: integer("turbo_mode_enabled", { mode: "boolean" }).notNull().default(false),
  claudeCodeEnabled: integer("claude_code_enabled", { mode: "boolean" }).notNull().default(false),
  createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
});

// ── GitHub Token ────────────────────────────────────────────────────

export const githubTokens = sqliteTable("github_token", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  userId: text("user_id")
    .notNull()
    .unique()
    .references(() => users.id, { onDelete: "cascade" }),
  accessToken: text("access_token").notNull(),
  githubUserId: text("github_user_id"),
  githubUsername: text("github_username"),
  githubAvatarUrl: text("github_avatar_url"),
  scope: text("scope"),
  createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
});

// ── Email Verification Tokens ───────────────────────────────────────

export const emailVerificationTokens = sqliteTable(
  "email_verification_token",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    token: text("token").notNull().unique(),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    expiresAt: integer("expires_at", { mode: "timestamp" }).notNull(),
    used: integer("used", { mode: "boolean" }).notNull().default(false),
  },
  (t) => [index("evt_user_idx").on(t.userId)]
);

// ── Email Verification Codes ────────────────────────────────────────

export const emailVerificationCodes = sqliteTable(
  "email_verification_code",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    code: text("code").notNull(),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    expiresAt: integer("expires_at", { mode: "timestamp" }).notNull(),
    used: integer("used", { mode: "boolean" }).notNull().default(false),
  },
  (t) => [index("evc_user_idx").on(t.userId)]
);
