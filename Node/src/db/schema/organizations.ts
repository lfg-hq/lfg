import {
  sqliteTable,
  text,
  integer,
  uniqueIndex,
  index,
} from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { users } from "./users.ts";

// ── Organizations ───────────────────────────────────────────────────

export const organizations = sqliteTable(
  "organization",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    name: text("name").notNull(),
    slug: text("slug").notNull().unique(),
    ownerId: text("owner_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    description: text("description").default(""),
    avatar: text("avatar"),

    stripeCustomerId: text("stripe_customer_id"),

    allowMemberInvites: integer("allow_member_invites", { mode: "boolean" })
      .notNull()
      .default(false),
    isActive: integer("is_active", { mode: "boolean" }).notNull().default(true),

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [index("org_owner_idx").on(t.ownerId)]
);

// ── Organization Memberships ────────────────────────────────────────

export const orgMemberships = sqliteTable(
  "organization_membership",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    organizationId: text("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    role: text("role").notNull().default("member"), // owner | admin | member
    status: text("status").notNull().default("active"), // pending | active | inactive

    joinedAt: integer("joined_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    uniqueIndex("org_member_unique").on(t.userId, t.organizationId),
    index("org_member_org_idx").on(t.organizationId),
  ]
);

// ── Organization Invitations ────────────────────────────────────────

export const orgInvitations = sqliteTable(
  "organization_invitation",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    organizationId: text("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    inviterId: text("inviter_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    email: text("email").notNull(),
    role: text("role").notNull().default("member"),

    token: text("token").notNull().unique(),
    status: text("status").notNull().default("pending"), // pending | accepted | declined | expired

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    expiresAt: integer("expires_at", { mode: "timestamp" }).notNull(),
    respondedAt: integer("responded_at", { mode: "timestamp" }),
  },
  (t) => [
    uniqueIndex("org_invite_unique").on(t.organizationId, t.email),
    index("org_invite_org_idx").on(t.organizationId),
  ]
);
