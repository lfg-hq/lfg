# LFG Node.js Rewrite Plan — Hono + Bun

## Status Tracker

| Phase | Description | Status |
|-------|------------|--------|
| 1 | Bootstrap + Database Schema | ✅ Done |
| 2 | Hono Server + Landing Pages | ✅ Done |
| 3 | Authentication | ✅ Done |
| 4 | AI SDK + Product Tools | ✅ Done |
| 5 | WebSocket AI Chat (Streaming) | ✅ Done |
| 6 | Chat UI + File Upload + Model Selection + Audio | ✅ Done |
| 7 | Ticket System + Project Dashboard | ✅ Done |
| 8 | Event Bus Foundation | ✅ Done |
| 9 | UI Polish | ✅ Done |

---

## Context

The current LFG platform is a Django monolith that has grown bulky and slow. The goal is to rewrite it as a lightweight Node.js app using **Bun runtime**, **Hono framework**, **Drizzle ORM**, **Better Auth**, and **Vercel AI SDK**. This will be created in a new `Node/` folder at the project root. Using SQLite for fast local development (swap to PostgreSQL later). Hono JSX for server-rendered pages reusing existing CSS/JS.

---

## Project Structure

```
Node/
├── package.json / tsconfig.json / drizzle.config.ts / .env
├── src/
│   ├── index.ts                     # Bun.serve — Hono HTTP + native WebSocket
│   ├── config/
│   │   ├── env.ts                   # Zod-validated env vars
│   │   ├── db.ts                    # Drizzle + SQLite client (swap to postgres later)
│   │   └── llm-models.json         # Model registry (port from config/llm_models.json)
│   ├── db/schema/                   # Drizzle table definitions
│   │   ├── index.ts / users.ts / organizations.ts / chat.ts
│   │   ├── projects.ts / tickets.ts / documents.ts
│   │   ├── design.ts / orchestrator.ts / tokens.ts
│   ├── auth/
│   │   ├── index.ts                 # Better Auth instance (Google, GitHub, email/pw, org plugin)
│   │   └── middleware.ts            # requireAuth Hono middleware
│   ├── routes/
│   │   ├── landing.ts / auth.ts / chat.ts / projects.ts
│   │   └── api/ (chat.ts, projects.ts, tickets.ts, files.ts, settings.ts)
│   ├── ws/
│   │   ├── chat-handler.ts          # WS message handler (replaces ChatConsumer)
│   │   ├── connection-manager.ts    # Track active connections per user
│   │   └── types.ts
│   ├── ai/
│   │   ├── provider.ts              # AI SDK provider factory
│   │   ├── tools/ (project, document, ticket, codebase, streaming, env, preview)
│   │   ├── prompts/product.ts       # Product analyst system prompt
│   │   └── stream-handler.ts        # Orchestrates streamText + WS notifications
│   ├── events/
│   │   ├── bus.ts                   # In-process EventEmitter pub/sub
│   │   ├── types.ts                 # Event type definitions
│   │   └── emitters.ts              # Helper functions to emit events from services
│   ├── services/                    # Business logic
│   ├── templates/
│   │   ├── layouts/ (base.tsx, chat-layout.tsx, project-layout.tsx)
│   │   ├── pages/ (landing.tsx, login.tsx, register.tsx, chat.tsx, project-list.tsx, project-detail.tsx, tickets-list.tsx)
│   │   └── components/ (sidebar.tsx, header.tsx, ticket-card.tsx, model-selector.tsx)
│   └── utils/ (slug.ts, id.ts, encryption.ts)
├── public/                          # Static assets (copied from Django static/)
│   ├── css/ js/ images/
├── data/                            # SQLite database file
└── drizzle/                         # Generated migrations
```

---

## Implementation Phases

### Phase 1: Bootstrap + Database Schema ✅
**Files**: `package.json`, `tsconfig.json`, `drizzle.config.ts`, `.env`, `src/config/*`, `src/db/schema/*`

1. ✅ `bun init` in `Node/` folder
2. ✅ Install deps: `hono`, `drizzle-orm`, `postgres`, `zod`, `better-auth`, `ai`, `@ai-sdk/anthropic`, `@ai-sdk/openai`, `@ai-sdk/google`
3. ✅ Create env config with Zod validation (`src/config/env.ts`)
4. ✅ Create Drizzle client (`src/config/db.ts`)
5. ✅ Port ALL models to Drizzle schemas:
   - **users.ts**: users (Better Auth managed), profiles, llmApiKeys, applicationState
   - **organizations.ts**: organizations, orgMemberships, orgInvitations
   - **chat.ts**: conversations, messages, chatFiles, agentRoles, modelSelections
   - **projects.ts**: projects, projectFeatures, projectPersonas, projectPrds, projectImplementations, projectMembers, projectInvitations
   - **tickets.ts**: ticketStages, projectTickets, projectTodoLists, ticketLogs, ticketMergeHistory
   - **documents.ts**: projectFiles, projectFileVersions, toolCallHistory
   - **design.ts**: projectDesignFeatures, designCanvases
   - **orchestrator.ts**: agentRuns, ticketExecutions, agentEvents
   - **tokens.ts**: tokenUsage
6. ✅ Typecheck passes, server starts
7. Switched from PostgreSQL to SQLite for fast local dev

Source models: `accounts/models.py`, `chat/models.py`, `projects/models.py`, `orchestrator/models.py`, `development/models.py`

### Phase 2: Hono Server + Landing Pages
**Files**: `src/index.ts`, `src/routes/landing.ts`, `src/templates/layouts/base.tsx`, `src/templates/pages/landing.tsx`, `public/*`

1. Create Hono app entry point with `Bun.serve` (HTTP + WebSocket)
2. Serve static files from `public/` via `hono/bun` serveStatic
3. Copy ALL static assets from `static/css/`, `static/js/`, `static/images/` to `public/`
4. Convert `templates/home/landing.html` (Tailwind-based) to Hono JSX
5. Convert base layout from `templates/base.html` to `base.tsx`
6. Keep all existing CSS intact, same class names

Source templates: `templates/home/landing.html`, `templates/base.html`

### Phase 3: Authentication
**Files**: `src/auth/index.ts`, `src/auth/middleware.ts`, `src/routes/auth.ts`, `src/templates/pages/login.tsx`, `src/templates/pages/register.tsx`

1. Configure Better Auth with:
   - Email/password enabled
   - Google OAuth (same callback URL pattern)
   - GitHub OAuth
   - Organization plugin (teams from day 1)
2. Create `requireAuth` middleware checking session via Better Auth API
3. Port login/register pages from `templates/accounts/` using existing `auth.css`
4. Auto-create profile + llmApiKeys + applicationState rows on first login (Better Auth hook)
5. Organization CRUD: create org, invite members, switch org context

Source: `accounts/models.py` (Organization, OrganizationMembership, OrganizationInvitation, Profile)

### Phase 4: AI SDK + Product Tools
**Files**: `src/ai/provider.ts`, `src/ai/tools/*.ts`, `src/ai/prompts/product.ts`, `src/config/llm-models.json`

1. Create unified provider factory using `@ai-sdk/anthropic`, `@ai-sdk/openai`, `@ai-sdk/google`
2. Port model config from `config/llm_models.json`
3. Convert ALL product tools from `factory/ai_tools.py` to AI SDK `tool()` with Zod schemas:
   - **project-tools.ts**: getProjectDashboard, setProjectStack, captureProjectName
   - **document-tools.ts**: createPrd, getPrd, createImplementation, getImplementation, updateImplementation, extractFeatures, extractPersonas, getFeatures, getPersonas, getFileList, getFileContent
   - **ticket-tools.ts**: createTickets, getPendingTickets, getTicketDetails, updateTicket, updateTicketDetails, updateAllTickets, getNextTicket, scheduleTickets, retryTicket, sendTicketMessage, queueTicketExecution
   - **streaming-tools.ts**: streamPrdContent, streamImplementationContent, streamDocumentContent
   - **codebase-tools.ts**: searchExistingCode, getCodebaseSummary, askCodebase, getCodebaseContext, getRepositoryInsights, indexRepository
   - **env-tools.ts**: getProjectEnvVars, registerRequiredEnvVars, setEnvVar, provisionPostgresDb
   - **preview-tools.ts**: startTicketPreview, checkTicketPreview
   - **misc-tools.ts**: lookupTechnologySpecs, broadcastToUser
4. Port product analyst system prompt from `factory/prompts/product_prompt.py`
5. Each tool's `execute` function replaces the corresponding case in `factory/tool_execution.py`

Source: `factory/ai_tools.py`, `factory/tool_execution.py`, `factory/ai_functions.py`, `factory/prompts/product_prompt.py`

### Phase 5: WebSocket AI Chat (Streaming)
**Files**: `src/ws/chat-handler.ts`, `src/ws/connection-manager.ts`, `src/ws/types.ts`, `src/ai/stream-handler.ts`

1. Bun native WebSocket in `src/index.ts` — upgrade on `/ws/chat` path
2. Auth on WS upgrade: validate session cookie or JWT token from query string
3. Connection manager: track user -> WebSocket mappings for broadcasting
4. Chat handler replaces `ChatConsumer.receive()`:
   - Save user message to DB
   - Load last 20 messages for context
   - Determine system prompt + tools based on agent role
   - Call `streamText()` from AI SDK with `maxSteps: 80`
   - Buffer text chunks (~80 chars / 80ms) before flushing to WS
   - `onStepFinish` callback sends tool notifications to WS
   - Streaming tools send WS messages from their execute()
   - Save full response to messages table after stream completes
5. Heartbeat loop (every 20s)
6. Stop generation support: set flag, check in stream loop
7. Auto-title generation using AI after first message pair

Source: `chat/consumers.py` (ChatConsumer class)

### Phase 6: Chat UI + File Upload + Model Selection + Audio
**Files**: `src/templates/pages/chat.tsx`, `src/templates/components/sidebar.tsx`, `src/routes/api/files.ts`, `src/routes/api/settings.ts`

1. Port chat page from `templates/chat/main.html` to JSX
2. Port sidebar from `templates/includes/sidebar.html` to JSX component
3. Copy `static/js/chat.js` to `public/js/chat.js` — update WS URL if needed
4. File upload endpoint: `POST /api/files/upload`
5. Model selection endpoint: `POST /api/settings/model`
6. Audio transcription: `GET /api/files/transcribe/:fileId`
7. Wire file attachments into AI messages
8. Model selector component in chat toolbar
9. Right panel for document rendering

Source: `templates/chat/main.html`, `templates/includes/sidebar.html`, `static/js/chat.js`

### Phase 7: Ticket System + Project Dashboard
**Files**: `src/routes/projects.ts`, `src/routes/api/tickets.ts`, `src/templates/pages/project-detail.tsx`, `src/templates/pages/project-list.tsx`, `src/templates/pages/tickets-list.tsx`

1. Project list page: CRUD, status badges, icons
2. Project detail page with tabs: Codebase, Conversations, Integrations, Events, Environment, Settings
3. Tickets list/kanban view with stages
4. REST API for ticket CRUD, status updates, stage management
5. Default ticket stages created with new projects
6. Ticket detail view with logs, todos, acceptance criteria

Source: `templates/projects/project_detail.html`, `templates/projects/tickets_list.html`, `projects/views.py`

### Phase 8: Event Bus Foundation
**Files**: `src/events/bus.ts`, `src/events/types.ts`, `src/events/emitters.ts`

1. Create typed event definitions
2. Create in-process pub/sub using EventEmitter
3. Create helper emitter functions
4. Wire emitters into services
5. Log events to agentEvents table

### Phase 9: UI Polish
**Files**: `public/css/theme-variables.css`, various CSS files, JSX templates

1. Improve color contrast in theme variables
2. Pull accent colors from landing page palette
3. Better typography scale
4. Improve dark mode readability
5. Modernize button styles, card shadows, input focus states

---

## Key Architecture Decisions

| Concern | Django (current) | Hono+Bun (target) |
|---------|-----------------|-------------------|
| Database | PostgreSQL | SQLite (dev) → PostgreSQL (prod) |
| WebSocket | Django Channels + Redis | Bun native WebSocket |
| AI streaming | Manual async generator + `__NOTIFICATION__` markers | AI SDK `streamText()` + `onStepFinish` callbacks |
| Tool execution | `execute_tool_call()` switch statement | Each tool has its own `execute()` function |
| Auth | Django auth + JWT | Better Auth (session cookies + OAuth) |
| ORM | Django ORM | Drizzle ORM (type-safe, lightweight) |
| Templating | Django templates | Hono JSX (SSR) |
| Static files | Django collectstatic | `serveStatic` from `hono/bun` |
| Event bus | None (ad-hoc signals) | Typed EventEmitter |

## Frontend JS Compatibility

The existing `static/js/chat.js` connects to `ws://host/ws/chat/` and handles `ai_chunk` messages. We keep the same WS message format:
- `{ type: 'ai_chunk', chunk, isFinal, isNotification?, notificationType?, functionName? }`
- `{ type: 'chat_history', messages }`
- `{ type: 'heartbeat' }`

## Verification

After each phase:
1. `bun run dev` — server starts on port 3000
2. Phase 1: `bun run db:generate` + `bun run db:migrate` — verify all tables created
3. Phase 2: `curl http://localhost:3000` — landing page renders with CSS
4. Phase 3: Login flow works with email/password and Google OAuth
5. Phase 4: Tools compile, Zod schemas validate
6. Phase 5: WebSocket connects, AI streams responses, tool calls work
7. Phase 6: File upload, model switching, audio transcription work
8. Phase 7: Project dashboard renders, tickets can be created via AI
9. Phase 8: Create a ticket via AI chat → verify event emitted and logged
10. Phase 9: Visual inspection of UI improvements
