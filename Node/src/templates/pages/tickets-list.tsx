import { html } from "hono/html";



interface TicketStage {
  id: string;
  name: string;
  color: string;
  order: number;
  isCompleted: boolean;
}

interface Ticket {
  id: string;
  name: string;
  status: string;
  priority: string;
  stageId: string | null;
  complexity: string;
  queueStatus: string;
  description: string;
}

interface TicketsListPageProps {
  user: { id: string; name: string; email?: string };
  project: { id: string; projectId: string; name: string; icon: string };
  stages: TicketStage[];
  tickets: Ticket[];
}

const PRIORITY_COLOR: Record<string, string> = {
  High: "#ef4444",
  Medium: "#f59e0b",
  Low: "#6b7280",
};

const STATUS_ICON: Record<string, string> = {
  open: "fa-circle",
  in_progress: "fa-spinner",
  review: "fa-eye",
  done: "fa-check-circle",
  failed: "fa-times-circle",
  blocked: "fa-ban",
};

export function TicketsListPage({ user, project, stages, tickets }: TicketsListPageProps) {
  const avatarLetter = (user.name?.[0] ?? user.email?.[0] ?? "?").toUpperCase();
  // Group tickets by stage
  const byStage: Record<string, Ticket[]> = {};
  for (const s of stages) byStage[s.id] = [];
  const unstaged: Ticket[] = [];
  for (const t of tickets) {
    if (t.stageId && byStage[t.stageId] !== undefined) {
      (byStage[t.stageId] as Ticket[]).push(t);
    } else {
      unstaged.push(t);
    }
  }

  return html`<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${project.name} Tickets — LFG</title>
  <link rel="stylesheet" href="/public/css/theme-variables.css" />
  <link rel="stylesheet" href="/public/css/common.css" />
  <link rel="stylesheet" href="/public/css/sidebar.css" />
  <link rel="stylesheet" href="/public/css/tickets.css" />
  <link rel="stylesheet" href="/public/css/polish.css" />
  <link rel="stylesheet" href="/public/css/light/light-mode.css" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
  <script src="/public/js/theme-switcher.js"></script>
</head>
<body data-user-id="${user.id}" data-project-id="${project.projectId}">

  <div class="app-container">
    <!-- Sidebar -->
    <div class="sidebar" id="sidebar" data-current-project-id="${project.projectId}">
      <div class="sidebar-top-content">
        <div class="sidebar-header">
          <div class="logo-section">
            <span class="logo-icon">🚀</span>
            <span class="logo-text">LFG</span>
          </div>
          <button id="minimize-btn" class="icon-btn" title="Collapse Sidebar">
            <i class="fas fa-chevron-left"></i>
          </button>
        </div>
        <div class="project-selector-section">
          <div class="nav-dropdown-container" id="projectDropdownContainer">
            <button class="project-dropdown-trigger" id="projectDropdownTrigger" title="Project Options">
              <i class="fas fa-folder-open"></i>
              <span class="project-name-text">${project.name}</span>
              <i class="fas fa-chevron-down dropdown-arrow"></i>
            </button>
            <div class="nav-dropdown" id="projectDropdown">
              <a href="/projects" class="nav-dropdown-item">
                <i class="fas fa-th-large"></i>
                <span>All Projects</span>
              </a>
            </div>
          </div>
        </div>
        <div class="new-chat-section">
          <a href="/chat/project/${project.projectId}" id="new-chat-btn" class="new-chat-link">
            <i class="fas fa-pen-to-square"></i>
            <span class="button-text">New chat</span>
          </a>
        </div>
        <div class="sidebar-nav">
          <a href="/chat/project/${project.projectId}" class="nav-link">
            <i class="fas fa-comments"></i>
            <span class="nav-text">Chat</span>
          </a>
          <a href="/projects/${project.projectId}" class="nav-link">
            <i class="fas fa-tachometer-alt"></i>
            <span class="nav-text">Dashboard</span>
          </a>
          <a href="/projects/${project.projectId}/tickets" class="nav-link active">
            <i class="fas fa-tasks"></i>
            <span class="nav-text">Tickets</span>
            <span style="margin-left:auto;font-size:0.7rem;background:rgba(139,92,246,0.2);color:#a78bfa;padding:0.1rem 0.4rem;border-radius:9999px;">${tickets.length}</span>
          </a>
        </div>
      </div>
      <div class="sidebar-bottom-content">
        <div class="sidebar-nav bottom-nav">
          <button class="nav-link theme-toggle-sidebar" data-theme-toggle>
            <i class="fas fa-sun theme-icon-light"></i>
            <i class="fas fa-moon theme-icon-dark"></i>
            <span class="nav-text theme-text">Light Mode</span>
          </button>
        </div>
        <div class="user-info" id="user-info">
          <button class="user-info-button" id="user-info-button">
            <div class="user-avatar">
              <div class="avatar-text">${avatarLetter}</div>
            </div>
            <div class="user-details">
              <span class="username">${user.name}</span>
            </div>
            <i class="fas fa-chevron-down dropdown-icon"></i>
          </button>
          <div class="user-dropdown" id="user-dropdown">
            <a href="/settings" class="dropdown-item">
              <i class="fas fa-cog"></i><span>Settings</span>
            </a>
            <div class="dropdown-divider"></div>
            <form method="POST" action="/api/auth/sign-out" style="margin:0;">
              <button type="submit" class="dropdown-item" style="width:100%;text-align:left;background:none;border:none;cursor:pointer;">
                <i class="fas fa-sign-out-alt"></i><span>Logout</span>
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>

    <!-- Tickets page -->
    <div class="tickets-page">
      <div class="tickets-header">
        <div class="tickets-header-content">
          <div style="display:flex;align-items:center;gap:0.75rem;">
            <a href="/projects/${project.projectId}" style="color:var(--text-secondary);text-decoration:none;font-size:0.875rem;">
              <i class="fas fa-chevron-left"></i> ${project.icon} ${project.name}
            </a>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-top:0.5rem;">
            <div>
              <h1 class="tickets-title">Tickets</h1>
              <p class="tickets-subtitle">${tickets.length} ticket${tickets.length !== 1 ? "s" : ""} across ${stages.length} stage${stages.length !== 1 ? "s" : ""}</p>
            </div>
            <a href="/chat/project/${project.projectId}" class="btn btn-primary" style="font-size:0.875rem;">
              <i class="fas fa-comment"></i> Chat to create tickets
            </a>
          </div>
        </div>
      </div>

      <div class="tickets-body">
        ${tickets.length === 0 ? html`
          <div style="text-align:center;padding:4rem 2rem;color:var(--text-secondary);">
            <i class="fas fa-ticket-alt" style="font-size:3rem;opacity:0.3;display:block;margin-bottom:1rem;"></i>
            <p style="margin:0 0 1rem;">No tickets yet. Ask the AI to break down your project into tickets.</p>
            <a href="/chat/project/${project.projectId}" class="btn btn-primary">Start chatting</a>
          </div>
        ` : html`
          <!-- Kanban board -->
          <div class="kanban-board">
            ${stages.map((stage) => {
              const stageTickets = byStage[stage.id] ?? [];
              return html`
                <div class="kanban-column" data-stage-id="${stage.id}">
                  <div class="kanban-column-header">
                    <div style="display:flex;align-items:center;gap:0.5rem;">
                      <span style="width:10px;height:10px;border-radius:50%;background:${stage.color};display:inline-block;flex-shrink:0;"></span>
                      <span class="kanban-column-title">${stage.name}</span>
                    </div>
                    <span style="font-size:0.75rem;color:var(--text-secondary);background:rgba(255,255,255,0.05);padding:0.15rem 0.5rem;border-radius:9999px;">${stageTickets.length}</span>
                  </div>
                  <div class="kanban-column-body">
                    ${stageTickets.length === 0 ? html`
                      <div style="text-align:center;padding:1.5rem;color:var(--text-secondary);font-size:0.8125rem;opacity:0.5;">
                        No tickets
                      </div>
                    ` : stageTickets.map((t) => html`
                      <div class="kanban-card" data-ticket-id="${t.id}">
                        <div class="kanban-card-header">
                          <span class="kanban-card-title">${t.name}</span>
                        </div>
                        <div class="kanban-card-meta">
                          <span style="display:flex;align-items:center;gap:0.3rem;font-size:0.75rem;color:${PRIORITY_COLOR[t.priority] ?? "var(--text-secondary)"};">
                            <i class="fas fa-flag" style="font-size:0.65rem;"></i>${t.priority}
                          </span>
                          <span style="display:flex;align-items:center;gap:0.3rem;font-size:0.75rem;color:var(--text-secondary);">
                            <i class="fas ${STATUS_ICON[t.status] ?? "fa-circle"}" style="font-size:0.65rem;"></i>${t.status.replace("_", " ")}
                          </span>
                          ${t.complexity !== "medium" ? html`
                            <span style="font-size:0.7rem;color:var(--text-secondary);background:rgba(255,255,255,0.05);padding:0.1rem 0.35rem;border-radius:var(--radius);">${t.complexity}</span>
                          ` : ""}
                        </div>
                        ${t.queueStatus !== "none" ? html`
                          <div class="kanban-card-queue">
                            <span class="queue-badge" style="font-size:0.7rem;background:rgba(139,92,246,0.15);color:#a78bfa;padding:0.2rem 0.5rem;border-radius:var(--radius);">
                              <i class="fas fa-clock"></i> ${t.queueStatus}
                            </span>
                          </div>
                        ` : ""}
                      </div>
                    `)}
                  </div>
                </div>
              `;
            })}
            ${unstaged.length > 0 ? html`
              <div class="kanban-column">
                <div class="kanban-column-header">
                  <span class="kanban-column-title" style="color:var(--text-secondary);">Unassigned</span>
                  <span style="font-size:0.75rem;color:var(--text-secondary);">${unstaged.length}</span>
                </div>
                <div class="kanban-column-body">
                  ${unstaged.map((t) => html`
                    <div class="kanban-card" data-ticket-id="${t.id}">
                      <div class="kanban-card-header">
                        <span class="kanban-card-title">${t.name}</span>
                      </div>
                      <div class="kanban-card-meta">
                        <span style="font-size:0.75rem;color:${PRIORITY_COLOR[t.priority] ?? "var(--text-secondary)"};">${t.priority}</span>
                        <span style="font-size:0.75rem;color:var(--text-secondary);">${t.status}</span>
                      </div>
                    </div>
                  `)}
                </div>
              </div>
            ` : ""}
          </div>
        `}
      </div>
    </div>
  </div>

  <script src="/public/js/sidebar.js"></script>
</body>
</html>`;
}
