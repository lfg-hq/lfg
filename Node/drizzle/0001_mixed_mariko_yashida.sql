CREATE TABLE `sandbox` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text,
	`user_id` text,
	`ticket_id` text,
	`mags_workspace_id` text UNIQUE,
	`mags_job_id` text,
	`mags_base_workspace_id` text,
	`workspace_type` text NOT NULL DEFAULT 'ticket',
	`status` text NOT NULL DEFAULT 'ready',
	`cli_session_id` text,
	`preview_url` text,
	`preview_port` integer,
	`current_branch` text,
	`output_offset` integer NOT NULL DEFAULT 0,
	`tech_stack` text,
	`created_at` integer NOT NULL DEFAULT (unixepoch()),
	`updated_at` integer NOT NULL DEFAULT (unixepoch()),
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`ticket_id`) REFERENCES `project_ticket`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE UNIQUE INDEX `sb_mags_ws_idx` ON `sandbox` (`mags_workspace_id`);
--> statement-breakpoint
CREATE INDEX `sb_project_idx` ON `sandbox` (`project_id`);
--> statement-breakpoint
CREATE INDEX `sb_ticket_idx` ON `sandbox` (`ticket_id`);
--> statement-breakpoint
CREATE INDEX `sb_user_idx` ON `sandbox` (`user_id`);
--> statement-breakpoint
CREATE TABLE `server_log` (
	`id` text PRIMARY KEY NOT NULL,
	`sandbox_id` text NOT NULL,
	`ticket_id` text,
	`level` text NOT NULL DEFAULT 'info',
	`message` text NOT NULL,
	`created_at` integer NOT NULL DEFAULT (unixepoch()),
	FOREIGN KEY (`sandbox_id`) REFERENCES `sandbox`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`ticket_id`) REFERENCES `project_ticket`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `sl_sandbox_idx` ON `server_log` (`sandbox_id`, `created_at`);
--> statement-breakpoint
CREATE INDEX `sl_ticket_idx` ON `server_log` (`ticket_id`, `created_at`);
