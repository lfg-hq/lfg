CREATE TABLE `account` (
	`id` text PRIMARY KEY NOT NULL,
	`account_id` text NOT NULL,
	`provider_id` text NOT NULL,
	`user_id` text NOT NULL,
	`access_token` text,
	`refresh_token` text,
	`id_token` text,
	`access_token_expires_at` integer,
	`refresh_token_expires_at` integer,
	`scope` text,
	`password` text,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `application_state` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`sidebar_minimized` integer DEFAULT false NOT NULL,
	`last_selected_model` text DEFAULT 'gpt-5-mini' NOT NULL,
	`last_selected_role` text DEFAULT 'product_analyst' NOT NULL,
	`turbo_mode_enabled` integer DEFAULT false NOT NULL,
	`claude_code_enabled` integer DEFAULT false NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `application_state_user_id_unique` ON `application_state` (`user_id`);--> statement-breakpoint
CREATE TABLE `email_verification_code` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`code` text NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`expires_at` integer NOT NULL,
	`used` integer DEFAULT false NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `evc_user_idx` ON `email_verification_code` (`user_id`);--> statement-breakpoint
CREATE TABLE `email_verification_token` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`token` text NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`expires_at` integer NOT NULL,
	`used` integer DEFAULT false NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `email_verification_token_token_unique` ON `email_verification_token` (`token`);--> statement-breakpoint
CREATE INDEX `evt_user_idx` ON `email_verification_token` (`user_id`);--> statement-breakpoint
CREATE TABLE `external_services_api_key` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`linear_api_key` text,
	`jira_api_key` text,
	`notion_api_key` text,
	`google_docs_api_key` text,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `external_services_api_key_user_id_unique` ON `external_services_api_key` (`user_id`);--> statement-breakpoint
CREATE TABLE `github_token` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`access_token` text NOT NULL,
	`github_user_id` text,
	`github_username` text,
	`github_avatar_url` text,
	`scope` text,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `github_token_user_id_unique` ON `github_token` (`user_id`);--> statement-breakpoint
CREATE TABLE `llm_api_key` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`openai_api_key` text,
	`anthropic_api_key` text,
	`xai_api_key` text,
	`google_api_key` text,
	`free_trial` integer DEFAULT true NOT NULL,
	`use_personal_llm_keys` integer DEFAULT false NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `llm_api_key_user_id_unique` ON `llm_api_key` (`user_id`);--> statement-breakpoint
CREATE TABLE `profile` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`bio` text DEFAULT '',
	`avatar` text,
	`sidebar_collapsed` integer DEFAULT false NOT NULL,
	`email_verified` integer DEFAULT false NOT NULL,
	`has_seen_onboarding` integer DEFAULT false NOT NULL,
	`claude_code_authenticated` integer DEFAULT false NOT NULL,
	`claude_code_s3_key` text,
	`claude_code_credentials` text,
	`claude_code_credentials_updated_at` integer,
	`cli_api_key` text,
	`current_organization_id` text,
	`allow_project_invitations` integer DEFAULT true NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `profile_user_id_unique` ON `profile` (`user_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `profile_cli_api_key_unique` ON `profile` (`cli_api_key`);--> statement-breakpoint
CREATE TABLE `session` (
	`id` text PRIMARY KEY NOT NULL,
	`expires_at` integer NOT NULL,
	`token` text NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	`ip_address` text,
	`user_agent` text,
	`user_id` text NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `session_token_unique` ON `session` (`token`);--> statement-breakpoint
CREATE TABLE `user` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`email` text NOT NULL,
	`email_verified` integer DEFAULT false NOT NULL,
	`image` text,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `user_email_unique` ON `user` (`email`);--> statement-breakpoint
CREATE TABLE `verification` (
	`id` text PRIMARY KEY NOT NULL,
	`identifier` text NOT NULL,
	`value` text NOT NULL,
	`expires_at` integer NOT NULL,
	`created_at` integer,
	`updated_at` integer
);
--> statement-breakpoint
CREATE TABLE `organization_invitation` (
	`id` text PRIMARY KEY NOT NULL,
	`organization_id` text NOT NULL,
	`inviter_id` text NOT NULL,
	`email` text NOT NULL,
	`role` text DEFAULT 'member' NOT NULL,
	`token` text NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`expires_at` integer NOT NULL,
	`responded_at` integer,
	FOREIGN KEY (`organization_id`) REFERENCES `organization`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`inviter_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `organization_invitation_token_unique` ON `organization_invitation` (`token`);--> statement-breakpoint
CREATE UNIQUE INDEX `org_invite_unique` ON `organization_invitation` (`organization_id`,`email`);--> statement-breakpoint
CREATE INDEX `org_invite_org_idx` ON `organization_invitation` (`organization_id`);--> statement-breakpoint
CREATE TABLE `organization_membership` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`organization_id` text NOT NULL,
	`role` text DEFAULT 'member' NOT NULL,
	`status` text DEFAULT 'active' NOT NULL,
	`joined_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`organization_id`) REFERENCES `organization`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `org_member_unique` ON `organization_membership` (`user_id`,`organization_id`);--> statement-breakpoint
CREATE INDEX `org_member_org_idx` ON `organization_membership` (`organization_id`);--> statement-breakpoint
CREATE TABLE `organization` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`slug` text NOT NULL,
	`owner_id` text NOT NULL,
	`description` text DEFAULT '',
	`avatar` text,
	`stripe_customer_id` text,
	`allow_member_invites` integer DEFAULT false NOT NULL,
	`is_active` integer DEFAULT true NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`owner_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `organization_slug_unique` ON `organization` (`slug`);--> statement-breakpoint
CREATE INDEX `org_owner_idx` ON `organization` (`owner_id`);--> statement-breakpoint
CREATE TABLE `agent_role` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`name` text DEFAULT 'product_analyst' NOT NULL,
	`turbo_mode` integer DEFAULT false NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `agent_role_user_id_unique` ON `agent_role` (`user_id`);--> statement-breakpoint
CREATE TABLE `chat_file` (
	`id` text PRIMARY KEY NOT NULL,
	`conversation_id` text NOT NULL,
	`message_id` text,
	`file_path` text NOT NULL,
	`original_filename` text NOT NULL,
	`file_type` text DEFAULT '',
	`file_size` integer DEFAULT 0 NOT NULL,
	`uploaded_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`conversation_id`) REFERENCES `conversation`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`message_id`) REFERENCES `message`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `chatfile_conv_idx` ON `chat_file` (`conversation_id`);--> statement-breakpoint
CREATE TABLE `conversation` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text,
	`title` text,
	`project_id` text,
	`design_canvas_id` text,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `conv_user_idx` ON `conversation` (`user_id`);--> statement-breakpoint
CREATE INDEX `conv_project_idx` ON `conversation` (`project_id`);--> statement-breakpoint
CREATE TABLE `message` (
	`id` text PRIMARY KEY NOT NULL,
	`conversation_id` text NOT NULL,
	`role` text NOT NULL,
	`content` text NOT NULL,
	`content_if_file` text DEFAULT '[]',
	`user_role` text DEFAULT 'default',
	`is_partial` integer DEFAULT false NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`last_updated` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`conversation_id`) REFERENCES `conversation`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `msg_conv_created_idx` ON `message` (`conversation_id`,`created_at`);--> statement-breakpoint
CREATE INDEX `msg_conv_partial_idx` ON `message` (`conversation_id`,`is_partial`);--> statement-breakpoint
CREATE TABLE `model_selection` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`selected_model` text DEFAULT 'gpt-5-mini' NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `model_selection_user_id_unique` ON `model_selection` (`user_id`);--> statement-breakpoint
CREATE TABLE `project_code_generation` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`folder_name` text NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `project_code_generation_project_id_unique` ON `project_code_generation` (`project_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `project_code_generation_folder_name_unique` ON `project_code_generation` (`folder_name`);--> statement-breakpoint
CREATE TABLE `project_environment_variable` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`key` text NOT NULL,
	`encrypted_value` text NOT NULL,
	`is_secret` integer DEFAULT true NOT NULL,
	`is_required` integer DEFAULT false NOT NULL,
	`has_value` integer DEFAULT true NOT NULL,
	`description` text DEFAULT '',
	`created_by_id` text,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`created_by_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE UNIQUE INDEX `pev_project_key_unique` ON `project_environment_variable` (`project_id`,`key`);--> statement-breakpoint
CREATE INDEX `pev_project_idx` ON `project_environment_variable` (`project_id`);--> statement-breakpoint
CREATE TABLE `project_feature` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`name` text NOT NULL,
	`description` text NOT NULL,
	`details` text NOT NULL,
	`priority` text DEFAULT 'Medium Priority' NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `pf_project_idx` ON `project_feature` (`project_id`);--> statement-breakpoint
CREATE TABLE `project_implementation` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`implementation` text NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `project_implementation_project_id_unique` ON `project_implementation` (`project_id`);--> statement-breakpoint
CREATE TABLE `project_invitation` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`inviter_id` text NOT NULL,
	`email` text NOT NULL,
	`role` text DEFAULT 'member' NOT NULL,
	`token` text NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`expires_at` integer NOT NULL,
	`responded_at` integer,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`inviter_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `project_invitation_token_unique` ON `project_invitation` (`token`);--> statement-breakpoint
CREATE UNIQUE INDEX `pi_project_email_unique` ON `project_invitation` (`project_id`,`email`);--> statement-breakpoint
CREATE INDEX `pi_project_idx` ON `project_invitation` (`project_id`);--> statement-breakpoint
CREATE TABLE `project_member` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`user_id` text NOT NULL,
	`role` text DEFAULT 'member' NOT NULL,
	`status` text DEFAULT 'active' NOT NULL,
	`can_edit_files` integer DEFAULT true NOT NULL,
	`can_manage_tickets` integer DEFAULT true NOT NULL,
	`can_chat` integer DEFAULT true NOT NULL,
	`can_invite_members` integer DEFAULT false NOT NULL,
	`joined_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	`invited_by_id` text,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`invited_by_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE UNIQUE INDEX `pm_project_user_unique` ON `project_member` (`project_id`,`user_id`);--> statement-breakpoint
CREATE INDEX `pm_project_idx` ON `project_member` (`project_id`);--> statement-breakpoint
CREATE TABLE `project_persona` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`name` text NOT NULL,
	`role` text NOT NULL,
	`description` text NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `pp_project_idx` ON `project_persona` (`project_id`);--> statement-breakpoint
CREATE TABLE `project_prd` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`name` text DEFAULT 'Main PRD' NOT NULL,
	`prd` text NOT NULL,
	`is_active` integer DEFAULT true NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `prd_project_name_unique` ON `project_prd` (`project_id`,`name`);--> statement-breakpoint
CREATE INDEX `prd_project_idx` ON `project_prd` (`project_id`);--> statement-breakpoint
CREATE TABLE `project` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`name` text NOT NULL,
	`provided_name` text,
	`description` text,
	`owner_id` text NOT NULL,
	`status` text DEFAULT 'active' NOT NULL,
	`icon` text DEFAULT '📋' NOT NULL,
	`stack` text DEFAULT '',
	`custom_project_dir` text,
	`custom_install_cmd` text,
	`custom_dev_cmd` text,
	`custom_default_port` integer,
	`linear_team_id` text,
	`linear_project_id` text,
	`linear_sync_enabled` integer DEFAULT false NOT NULL,
	`preview_ticket_id` text,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`owner_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `project_project_id_unique` ON `project` (`project_id`);--> statement-breakpoint
CREATE INDEX `project_owner_idx` ON `project` (`owner_id`);--> statement-breakpoint
CREATE TABLE `project_ticket_attachment` (
	`id` text PRIMARY KEY NOT NULL,
	`ticket_id` text NOT NULL,
	`uploaded_by_id` text,
	`file_path` text NOT NULL,
	`original_filename` text DEFAULT '',
	`file_type` text DEFAULT '',
	`file_size` integer DEFAULT 0 NOT NULL,
	`uploaded_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`ticket_id`) REFERENCES `project_ticket`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`uploaded_by_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `pta_ticket_idx` ON `project_ticket_attachment` (`ticket_id`);--> statement-breakpoint
CREATE TABLE `project_ticket` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`name` text NOT NULL,
	`status` text DEFAULT 'open' NOT NULL,
	`stage_id` text,
	`description` text NOT NULL,
	`priority` text DEFAULT 'Medium' NOT NULL,
	`role` text DEFAULT 'user' NOT NULL,
	`details` text DEFAULT '{}',
	`ui_requirements` text DEFAULT '{}',
	`component_specs` text DEFAULT '{}',
	`acceptance_criteria` text DEFAULT '[]',
	`dependencies` text DEFAULT '[]',
	`source_document_id` text,
	`conversation_id` text,
	`notes` text DEFAULT '',
	`complexity` text DEFAULT 'medium' NOT NULL,
	`requires_worktree` integer DEFAULT true NOT NULL,
	`github_branch` text,
	`github_commit_sha` text,
	`github_merge_status` text,
	`github_merge_commit_sha` text,
	`github_last_revert_sha` text,
	`github_reverted_at` integer,
	`github_reverted_by_id` text,
	`linear_issue_id` text,
	`linear_issue_url` text,
	`linear_state` text,
	`linear_priority` integer,
	`linear_assignee_id` text,
	`linear_synced_at` integer,
	`linear_sync_enabled` integer DEFAULT true NOT NULL,
	`queue_status` text DEFAULT 'none' NOT NULL,
	`queued_at` integer,
	`queue_task_id` text,
	`execution_time_seconds` real DEFAULT 0 NOT NULL,
	`last_execution_at` integer,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`stage_id`) REFERENCES `ticket_stage`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`github_reverted_by_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `pt_project_idx` ON `project_ticket` (`project_id`);--> statement-breakpoint
CREATE INDEX `pt_stage_idx` ON `project_ticket` (`stage_id`);--> statement-breakpoint
CREATE INDEX `pt_conv_idx` ON `project_ticket` (`conversation_id`);--> statement-breakpoint
CREATE TABLE `project_todo_list` (
	`id` text PRIMARY KEY NOT NULL,
	`ticket_id` text NOT NULL,
	`description` text NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`order` integer DEFAULT 0 NOT NULL,
	`cli_task_id` text,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`ticket_id`) REFERENCES `project_ticket`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `ptl_ticket_idx` ON `project_todo_list` (`ticket_id`);--> statement-breakpoint
CREATE TABLE `ticket_log` (
	`id` text PRIMARY KEY NOT NULL,
	`ticket_id` text NOT NULL,
	`task_id` text,
	`log_type` text DEFAULT 'command' NOT NULL,
	`command` text NOT NULL,
	`explanation` text,
	`output` text,
	`exit_code` integer,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`ticket_id`) REFERENCES `project_ticket`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`task_id`) REFERENCES `project_todo_list`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `tl_ticket_idx` ON `ticket_log` (`ticket_id`);--> statement-breakpoint
CREATE INDEX `tl_task_idx` ON `ticket_log` (`task_id`);--> statement-breakpoint
CREATE INDEX `tl_type_idx` ON `ticket_log` (`log_type`);--> statement-breakpoint
CREATE TABLE `ticket_merge_history` (
	`id` text PRIMARY KEY NOT NULL,
	`ticket_id` text NOT NULL,
	`action` text NOT NULL,
	`merge_commit_sha` text NOT NULL,
	`revert_commit_sha` text,
	`performed_by_id` text,
	`files_changed` text DEFAULT '[]',
	`lines_added` integer DEFAULT 0 NOT NULL,
	`lines_removed` integer DEFAULT 0 NOT NULL,
	`commit_message` text DEFAULT '',
	`commit_author` text DEFAULT '',
	`commit_date` integer,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`ticket_id`) REFERENCES `project_ticket`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`performed_by_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `tmh_ticket_idx` ON `ticket_merge_history` (`ticket_id`,`created_at`);--> statement-breakpoint
CREATE INDEX `tmh_sha_idx` ON `ticket_merge_history` (`merge_commit_sha`);--> statement-breakpoint
CREATE TABLE `ticket_stage` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`name` text NOT NULL,
	`color` text DEFAULT '#6366f1' NOT NULL,
	`order` integer DEFAULT 0 NOT NULL,
	`is_default` integer DEFAULT false NOT NULL,
	`is_completed` integer DEFAULT false NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `ts_project_name_unique` ON `ticket_stage` (`project_id`,`name`);--> statement-breakpoint
CREATE INDEX `ts_project_order_idx` ON `ticket_stage` (`project_id`,`order`);--> statement-breakpoint
CREATE TABLE `project_file_version` (
	`id` text PRIMARY KEY NOT NULL,
	`file_id` text NOT NULL,
	`version_number` integer NOT NULL,
	`content` text NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`created_by_id` text,
	`change_description` text,
	FOREIGN KEY (`file_id`) REFERENCES `project_file`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`created_by_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE UNIQUE INDEX `pfv_file_version_unique` ON `project_file_version` (`file_id`,`version_number`);--> statement-breakpoint
CREATE INDEX `pfv_file_idx` ON `project_file_version` (`file_id`);--> statement-breakpoint
CREATE TABLE `project_file` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`name` text NOT NULL,
	`file_type` text NOT NULL,
	`content` text,
	`s3_key` text,
	`is_active` integer DEFAULT true NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `pf_project_name_type_unique` ON `project_file` (`project_id`,`name`,`file_type`);--> statement-breakpoint
CREATE INDEX `pf_project_type_idx` ON `project_file` (`project_id`,`file_type`);--> statement-breakpoint
CREATE TABLE `tool_call_history` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`conversation_id` text,
	`message_id` text,
	`tool_name` text NOT NULL,
	`tool_input` text DEFAULT '{}',
	`generated_content` text NOT NULL,
	`content_type` text DEFAULT 'text' NOT NULL,
	`metadata` text DEFAULT '{}',
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `tch_project_idx` ON `tool_call_history` (`project_id`);--> statement-breakpoint
CREATE INDEX `tch_project_tool_idx` ON `tool_call_history` (`project_id`,`tool_name`);--> statement-breakpoint
CREATE INDEX `tch_conv_idx` ON `tool_call_history` (`conversation_id`);--> statement-breakpoint
CREATE TABLE `design_canvas` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`name` text NOT NULL,
	`description` text DEFAULT '',
	`is_default` integer DEFAULT false NOT NULL,
	`feature_positions` text DEFAULT '{}',
	`visible_features` text DEFAULT '[]',
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `dc_project_name_unique` ON `design_canvas` (`project_id`,`name`);--> statement-breakpoint
CREATE INDEX `dc_project_idx` ON `design_canvas` (`project_id`);--> statement-breakpoint
CREATE INDEX `dc_project_default_idx` ON `design_canvas` (`project_id`,`is_default`);--> statement-breakpoint
CREATE TABLE `project_design_feature` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`conversation_id` text,
	`feature_name` text NOT NULL,
	`feature_description` text DEFAULT '',
	`explainer` text DEFAULT '',
	`platform` text DEFAULT 'web' NOT NULL,
	`css_style` text DEFAULT '',
	`common_elements` text DEFAULT '[]',
	`pages` text DEFAULT '[]',
	`entry_page_id` text DEFAULT '',
	`feature_connections` text DEFAULT '[]',
	`canvas_position` text DEFAULT '{}',
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `pdf_project_name_unique` ON `project_design_feature` (`project_id`,`feature_name`);--> statement-breakpoint
CREATE INDEX `pdf_project_idx` ON `project_design_feature` (`project_id`);--> statement-breakpoint
CREATE TABLE `agent_event` (
	`id` text PRIMARY KEY NOT NULL,
	`agent_run_id` text NOT NULL,
	`ticket_execution_id` text,
	`event_type` text NOT NULL,
	`payload` text DEFAULT '{}',
	`requires_user_action` integer DEFAULT false NOT NULL,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`agent_run_id`) REFERENCES `agent_run`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`ticket_execution_id`) REFERENCES `ticket_execution`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `ae_run_type_idx` ON `agent_event` (`agent_run_id`,`event_type`);--> statement-breakpoint
CREATE INDEX `ae_user_action_idx` ON `agent_event` (`requires_user_action`,`created_at`);--> statement-breakpoint
CREATE TABLE `agent_run` (
	`id` text PRIMARY KEY NOT NULL,
	`conversation_id` text NOT NULL,
	`project_id` text NOT NULL,
	`user_id` text NOT NULL,
	`trigger_message` text NOT NULL,
	`run_type` text DEFAULT 'direct_response' NOT NULL,
	`plan` text DEFAULT '{}',
	`status` text DEFAULT 'planning' NOT NULL,
	`orchestrator_messages` text DEFAULT '[]',
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`updated_at` integer DEFAULT (unixepoch()) NOT NULL,
	`completed_at` integer,
	FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `ar_conv_status_idx` ON `agent_run` (`conversation_id`,`status`);--> statement-breakpoint
CREATE INDEX `ar_project_status_idx` ON `agent_run` (`project_id`,`status`);--> statement-breakpoint
CREATE TABLE `ticket_execution_dependency` (
	`id` text PRIMARY KEY NOT NULL,
	`execution_id` text NOT NULL,
	`depends_on_id` text NOT NULL,
	FOREIGN KEY (`execution_id`) REFERENCES `ticket_execution`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`depends_on_id`) REFERENCES `ticket_execution`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `ted_exec_idx` ON `ticket_execution_dependency` (`execution_id`);--> statement-breakpoint
CREATE TABLE `ticket_execution` (
	`id` text PRIMARY KEY NOT NULL,
	`agent_run_id` text NOT NULL,
	`ticket_id` text,
	`title` text NOT NULL,
	`description` text NOT NULL,
	`execution_type` text NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`sequence_number` integer DEFAULT 0 NOT NULL,
	`worker_context` text DEFAULT '{}',
	`result` text,
	`blocked_reason` text,
	`blocked_question` text,
	`user_response` text,
	`task_id` text,
	`worker_type` text,
	`created_at` integer DEFAULT (unixepoch()) NOT NULL,
	`started_at` integer,
	`completed_at` integer,
	FOREIGN KEY (`agent_run_id`) REFERENCES `agent_run`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `te_run_status_idx` ON `ticket_execution` (`agent_run_id`,`status`);--> statement-breakpoint
CREATE INDEX `te_status_seq_idx` ON `ticket_execution` (`status`,`sequence_number`);--> statement-breakpoint
CREATE TABLE `token_usage` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`project_id` text,
	`conversation_id` text,
	`provider` text NOT NULL,
	`model` text NOT NULL,
	`input_tokens` integer DEFAULT 0 NOT NULL,
	`output_tokens` integer DEFAULT 0 NOT NULL,
	`total_tokens` integer DEFAULT 0 NOT NULL,
	`timestamp` integer DEFAULT (unixepoch()) NOT NULL,
	`request_id` text,
	`cost` real,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `tu_user_ts_idx` ON `token_usage` (`user_id`,`timestamp`);--> statement-breakpoint
CREATE INDEX `tu_project_ts_idx` ON `token_usage` (`project_id`,`timestamp`);--> statement-breakpoint
CREATE INDEX `tu_conv_ts_idx` ON `token_usage` (`conversation_id`,`timestamp`);--> statement-breakpoint
CREATE INDEX `tu_provider_model_idx` ON `token_usage` (`provider`,`model`);