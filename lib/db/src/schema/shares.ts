import {
  pgTable,
  text,
  boolean,
  timestamp,
  integer,
} from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const shareLinksTable = pgTable("share_links", {
  id: text("id").primaryKey(),
  slug: text("slug").notNull().unique(),
  repoOwner: text("repo_owner").notNull(),
  repoName: text("repo_name").notNull(),
  filePath: text("file_path").notNull(),
  baseBranch: text("base_branch").notNull().default("main"),
  title: text("title").notNull(),
  description: text("description"),
  isActive: boolean("is_active").notNull().default(true),
  expiresAt: timestamp("expires_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const insertShareLinkSchema = createInsertSchema(shareLinksTable).omit(
  { id: true, createdAt: true },
);
export type InsertShareLink = z.infer<typeof insertShareLinkSchema>;
export type ShareLinkRow = typeof shareLinksTable.$inferSelect;

export const submissionsTable = pgTable("submissions", {
  id: text("id").primaryKey(),
  shareLinkId: text("share_link_id")
    .notNull()
    .references(() => shareLinksTable.id, { onDelete: "cascade" }),
  prUrl: text("pr_url").notNull(),
  prNumber: integer("pr_number").notNull(),
  branchName: text("branch_name").notNull(),
  submitterName: text("submitter_name"),
  note: text("note"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const insertSubmissionSchema = createInsertSchema(
  submissionsTable,
).omit({ id: true, createdAt: true });
export type InsertSubmission = z.infer<typeof insertSubmissionSchema>;
export type SubmissionRow = typeof submissionsTable.$inferSelect;
