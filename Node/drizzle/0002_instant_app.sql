CREATE TABLE `instant_app` (
	`id` text PRIMARY KEY NOT NULL,
	`app_id` text NOT NULL,
	`name` text NOT NULL,
	`description` text,
	`status` text DEFAULT 'gathering' NOT NULL,
	`requirements` text,
	`env_vars` text DEFAULT '{}' ,
	`preview_url` text,
	`metadata` text DEFAULT '{}' ,
	`project_id` text,
	`user_id` text NOT NULL,
	`sandbox_id` text,
	`conversation_id` text,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`sandbox_id`) REFERENCES `sandbox`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`conversation_id`) REFERENCES `conversation`(`id`) ON UPDATE no action ON DELETE set null
);
CREATE UNIQUE INDEX `instant_app_id_unique` ON `instant_app` (`app_id`);
CREATE INDEX `instant_user_idx` ON `instant_app` (`user_id`);
CREATE INDEX `instant_project_idx` ON `instant_app` (`project_id`);
CREATE INDEX `instant_status_idx` ON `instant_app` (`status`);
CREATE UNIQUE INDEX `instant_sandbox_unique` ON `instant_app` (`sandbox_id`);
CREATE UNIQUE INDEX `instant_conversation_unique` ON `instant_app` (`conversation_id`);
