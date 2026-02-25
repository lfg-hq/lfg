import { tool, zodSchema } from "ai";
import { z } from "zod";
import {
  askInstantSandboxQuestion,
  createOrContinueInstantApp,
  getInstantAppStatus,
  requestInstantEnvVariable,
} from "../../services/instant-app.ts";

export interface InstantToolContext {
  userId: string;
  conversationId: string;
  projectId?: string;
}

export function createInstantTools(ctx: InstantToolContext) {
  return {
    create_instant_app: tool({
      description:
        "Create a new instant app once requirements are clear. This provisions a sandbox, builds the app with Claude CLI over Mags, and starts the server.",
      inputSchema: zodSchema(
        z.object({
          name: z.string().describe("Short app name in kebab-case"),
          requirements: z.string().describe("Detailed requirements doc with features/data/pages/UI"),
          env_vars: z.record(z.string(), z.string()).optional(),
        })
      ),
      execute: async ({ name, requirements, env_vars }) => {
        const result = await createOrContinueInstantApp({
          userId: ctx.userId,
          projectId: ctx.projectId,
          conversationId: ctx.conversationId,
          name,
          requirements,
          envVars: env_vars,
        });

        return {
          message_to_agent: result.continued
            ? `Sending your changes to the running app ${result.appName}.`
            : `Provisioning sandbox and building ${result.appName}.`,
          data: {
            app_id: result.appId,
            app_name: result.appName,
            status: result.status,
          },
        };
      },
    }),

    get_instant_app_status: tool({
      description:
        "Get the current status and preview URL of the instant app for this conversation. Use this whenever the user asks for a URL or reports preview issues.",
      inputSchema: zodSchema(
        z.object({
          restart_server: z.boolean().optional().default(false),
        })
      ),
      execute: async ({ restart_server }) => {
        const status = await getInstantAppStatus({
          userId: ctx.userId,
          conversationId: ctx.conversationId,
          restartServer: restart_server,
        });

        if (!status) {
          return {
            message_to_agent:
              "No instant app exists for this conversation yet. Ask the user what they want to build and call create_instant_app.",
          };
        }

        return {
          message_to_agent: `App ${status.appName} status: ${status.status}. Preview URL: ${status.previewUrl || "(not available yet)"}`,
          data: {
            app_name: status.appName,
            status: status.status,
            preview_url: status.previewUrl,
          },
        };
      },
    }),

    request_env_variable: tool({
      description:
        "Request a required environment variable from the user. This sends a structured prompt to the instant chat UI.",
      inputSchema: zodSchema(
        z.object({
          key: z.string(),
          description: z.string(),
          required: z.boolean().optional().default(true),
        })
      ),
      execute: async ({ key, description, required }) => {
        const result = await requestInstantEnvVariable({
          userId: ctx.userId,
          conversationId: ctx.conversationId,
          key,
          description,
          required,
        });
        return result.sent
          ? { message_to_agent: `Requested ${key} from the user.` }
          : { message_to_agent: `Could not request ${key}: ${result.reason}` };
      },
    }),

    ask_sandbox: tool({
      description:
        "Ask a question about the current sandbox environment for debugging or project inspection.",
      inputSchema: zodSchema(
        z.object({
          question: z.string(),
        })
      ),
      execute: async ({ question }) => {
        const result = await askInstantSandboxQuestion({
          userId: ctx.userId,
          conversationId: ctx.conversationId,
          question,
        });
        return {
          message_to_agent: result.answer,
        };
      },
    }),
  };
}
