import { html } from "hono/html";

interface Conversation {
  id: string;
  title: string | null;
  updatedAt: Date;
}

interface TicketStage {
  id: string;
  name: string;
  color: string;
  order: number;
}

interface EnvVar {
  id: string;
  key: string;
  isSecret: boolean;
  hasValue: boolean;
  description: string | null;
}

interface ProjectDetailPageProps {
  user: { id: string; name: string; email?: string };
  project: {
    id: string;
    projectId: string;
    name: string;
    icon: string;
    status: string;
    description: string | null;
    stack: string | null;
  };
  conversations: Conversation[];
  stages: TicketStage[];
  ticketCounts: Record<string, number>;
  envVars: EnvVar[];
  activeTab?: string;
}

export function ProjectDetailPage({
  user,
  project,
  conversations,
  stages,
  ticketCounts,
  envVars,
  activeTab = "conversations",
}: ProjectDetailPageProps) {
  const totalTickets = Object.values(ticketCounts).reduce((a, b) => a + b, 0);
  const avatarLetter = (user.name?.[0] ?? user.email?.[0] ?? "?").toUpperCase();

  return html`<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${project.name} — LFG</title>
  <link rel="stylesheet" href="/public/css/theme-variables.css" />
  <link rel="stylesheet" href="/public/css/common.css" />
  <link rel="stylesheet" href="/public/css/sidebar.css" />
  <link rel="stylesheet" href="/public/css/projects.css" />
  <link rel="stylesheet" href="/public/css/project_detail.css" />
  <link rel="stylesheet" href="/public/css/polish.css" />
  <link rel="stylesheet" href="/public/css/light/light-mode.css" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
  <script src="/public/js/theme-switcher.js"></script>
</head>
<body data-user-id="${user.id}" data-user-name="${user.name}" data-project-id="${project.projectId}">

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
          <a href="/projects/${project.projectId}" class="nav-link${activeTab === "conversations" ? " active" : ""}">
            <i class="fas fa-tachometer-alt"></i>
            <span class="nav-text">Dashboard</span>
          </a>
          <a href="/projects/${project.projectId}/tickets" class="nav-link">
            <i class="fas fa-tasks"></i>
            <span class="nav-text">Tickets</span>
            ${totalTickets > 0 ? html`<span style="margin-left:auto;font-size:0.7rem;background:rgba(139,92,246,0.2);color:#a78bfa;padding:0.1rem 0.4rem;border-radius:9999px;">${totalTickets}</span>` : ""}
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

    <!-- Main content -->
    <div class="main-content-with-sidebar">
      <!-- Project Header -->
      <div class="page-header" style="padding:1.25rem 2rem;border-bottom:1px solid var(--border-color);display:flex;align-items:center;justify-content:space-between;">
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <a href="/projects" style="color:var(--text-secondary);text-decoration:none;font-size:0.875rem;display:flex;align-items:center;gap:0.4rem;">
            <i class="fas fa-arrow-left"></i> Projects
          </a>
          <span style="color:var(--text-secondary);">/</span>
          <span style="font-size:1.5rem;">${project.icon}</span>
          <div>
            <h1 style="font-size:1.25rem;font-weight:700;color:var(--text-color);margin:0;">${project.name}</h1>
            <div style="display:flex;gap:0.5rem;align-items:center;margin-top:0.2rem;">
              <span style="font-size:0.75rem;padding:0.2rem 0.5rem;border-radius:9999px;background:${project.status === "active" ? "rgba(34,197,94,0.1)" : "rgba(156,163,175,0.1)"};color:${project.status === "active" ? "#22c55e" : "var(--text-secondary)"};">
                ${project.status}
              </span>
              ${project.stack ? html`<span style="font-size:0.75rem;color:var(--text-secondary);">${project.stack}</span>` : ""}
            </div>
          </div>
        </div>
        <a href="/chat/project/${project.projectId}" class="btn btn-primary" style="display:flex;align-items:center;gap:0.5rem;">
          <i class="fas fa-arrow-left"></i> Back to Workspace
        </a>
      </div>

      <!-- Horizontal Tab Nav -->
      <div class="project-tabs" style="display:flex;gap:0;border-bottom:1px solid var(--border-color);padding:0 2rem;background:var(--body-bg);">
        <a href="/projects/${project.projectId}" class="tab-item${activeTab === "conversations" ? " active" : ""}" style="display:flex;align-items:center;gap:0.5rem;padding:0.875rem 1.25rem;text-decoration:none;font-size:0.875rem;font-weight:500;color:${activeTab === "conversations" ? "var(--text-color)" : "var(--text-secondary)"};border-bottom:2px solid ${activeTab === "conversations" ? "var(--primary-color)" : "transparent"};margin-bottom:-1px;transition:color 0.15s;">
          <i class="fas fa-comments"></i> Conversations
          ${conversations.length > 0 ? html`<span style="font-size:0.7rem;background:rgba(139,92,246,0.2);color:#a78bfa;padding:0.1rem 0.4rem;border-radius:9999px;">${conversations.length}</span>` : ""}
        </a>
        <a href="/projects/${project.projectId}/tickets" class="tab-item" style="display:flex;align-items:center;gap:0.5rem;padding:0.875rem 1.25rem;text-decoration:none;font-size:0.875rem;font-weight:500;color:var(--text-secondary);border-bottom:2px solid transparent;margin-bottom:-1px;transition:color 0.15s;">
          <i class="fas fa-tasks"></i> Tickets
          ${totalTickets > 0 ? html`<span style="font-size:0.7rem;background:rgba(139,92,246,0.2);color:#a78bfa;padding:0.1rem 0.4rem;border-radius:9999px;">${totalTickets}</span>` : ""}
        </a>
        <a href="/projects/${project.projectId}?tab=environment" class="tab-item${activeTab === "environment" ? " active" : ""}" style="display:flex;align-items:center;gap:0.5rem;padding:0.875rem 1.25rem;text-decoration:none;font-size:0.875rem;font-weight:500;color:${activeTab === "environment" ? "var(--text-color)" : "var(--text-secondary)"};border-bottom:2px solid ${activeTab === "environment" ? "var(--primary-color)" : "transparent"};margin-bottom:-1px;transition:color 0.15s;">
          <i class="fas fa-key"></i> Environment
        </a>
        <a href="/projects/${project.projectId}?tab=settings" class="tab-item${activeTab === "settings" ? " active" : ""}" style="display:flex;align-items:center;gap:0.5rem;padding:0.875rem 1.25rem;text-decoration:none;font-size:0.875rem;font-weight:500;color:${activeTab === "settings" ? "var(--text-color)" : "var(--text-secondary)"};border-bottom:2px solid ${activeTab === "settings" ? "var(--primary-color)" : "transparent"};margin-bottom:-1px;transition:color 0.15s;">
          <i class="fas fa-cog"></i> Settings
        </a>
      </div>

      <!-- Tab content -->
      <div style="padding:2rem;">
        ${activeTab === "conversations" ? html`
          <div style="max-width:800px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem;">
              <h2 style="font-size:1.1rem;font-weight:600;color:var(--text-color);margin:0;">Conversations</h2>
              <a href="/chat/project/${project.projectId}" class="btn btn-primary" style="font-size:0.875rem;">
                <i class="fas fa-plus"></i> New Conversation
              </a>
            </div>
            ${conversations.length === 0 ? html`
              <div style="text-align:center;padding:3rem;color:var(--text-secondary);border:1px dashed var(--border-color);border-radius:var(--radius-lg);">
                <i class="fas fa-comments" style="font-size:2rem;opacity:0.3;display:block;margin-bottom:0.75rem;"></i>
                <p style="margin:0 0 1rem;">No conversations yet.</p>
                <a href="/chat/project/${project.projectId}" class="btn btn-primary">Start a conversation</a>
              </div>
            ` : html`
              <div style="display:flex;flex-direction:column;gap:0.5rem;">
                ${conversations.map((c) => html`
                  <a href="/chat/project/${project.projectId}/conversation/${c.id}"
                    style="display:flex;align-items:center;gap:1rem;padding:0.875rem 1rem;border:1px solid var(--border-color);border-radius:var(--radius);background:var(--card-bg);text-decoration:none;color:var(--text-color);transition:border-color 0.15s;">
                    <i class="fas fa-comment-dots" style="color:var(--text-secondary);width:1rem;"></i>
                    <span style="flex:1;font-size:0.9375rem;">${c.title ?? "Untitled conversation"}</span>
                    <span style="font-size:0.75rem;color:var(--text-secondary);">${new Date(c.updatedAt).toLocaleDateString()}</span>
                  </a>
                `)}
              </div>
            `}
          </div>
        ` : ""}

        ${activeTab === "environment" ? html`
          <div style="max-width:800px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem;">
              <div>
                <h2 style="font-size:1.1rem;font-weight:600;color:var(--text-color);margin:0;">Environment Variables</h2>
                <p style="font-size:0.8125rem;color:var(--text-secondary);margin:0.25rem 0 0;">${envVars.length} variable${envVars.length !== 1 ? "s" : ""}</p>
              </div>
            </div>
            ${envVars.length === 0 ? html`
              <div style="text-align:center;padding:3rem;color:var(--text-secondary);border:1px dashed var(--border-color);border-radius:var(--radius-lg);">
                <i class="fas fa-key" style="font-size:2rem;opacity:0.3;display:block;margin-bottom:0.75rem;"></i>
                <p style="margin:0;">No environment variables. Ask the AI to set them up.</p>
              </div>
            ` : html`
              <div style="border:1px solid var(--border-color);border-radius:var(--radius-lg);overflow:hidden;">
                <table style="width:100%;border-collapse:collapse;">
                  <thead>
                    <tr style="background:var(--card-bg);border-bottom:1px solid var(--border-color);">
                      <th style="padding:0.75rem 1rem;text-align:left;font-size:0.75rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.05em;">Key</th>
                      <th style="padding:0.75rem 1rem;text-align:left;font-size:0.75rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.05em;">Value</th>
                      <th style="padding:0.75rem 1rem;text-align:left;font-size:0.75rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.05em;">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${envVars.map((ev, i) => html`
                      <tr style="border-bottom:${i < envVars.length - 1 ? "1px solid var(--border-color)" : "none"};">
                        <td style="padding:0.75rem 1rem;font-family:monospace;font-size:0.875rem;color:var(--text-color);">${ev.key}</td>
                        <td style="padding:0.75rem 1rem;font-size:0.875rem;color:var(--text-secondary);">
                          ${ev.hasValue ? html`<em>${ev.isSecret ? "••••••••" : "set"}</em>` : html`<em style="color:var(--danger-color);">not set</em>`}
                        </td>
                        <td style="padding:0.75rem 1rem;font-size:0.8125rem;color:var(--text-secondary);">${ev.description ?? ""}</td>
                      </tr>
                    `)}
                  </tbody>
                </table>
              </div>
            `}
          </div>
        ` : ""}

        ${activeTab === "settings" ? html`
          <div style="max-width:600px;">
            <h2 style="font-size:1.1rem;font-weight:600;color:var(--text-color);margin:0 0 1.5rem;">Project Settings</h2>
            <form method="POST" action="/projects/${project.projectId}/update">
              <div style="margin-bottom:1rem;">
                <label style="display:block;font-size:0.875rem;font-weight:500;color:var(--text-color);margin-bottom:0.5rem;">Project Name</label>
                <input type="text" name="name" value="${project.name}" class="input" style="width:100%;box-sizing:border-box;" />
              </div>
              <div style="margin-bottom:1rem;">
                <label style="display:block;font-size:0.875rem;font-weight:500;color:var(--text-color);margin-bottom:0.5rem;">Description</label>
                <textarea name="description" rows="3" class="input" style="width:100%;box-sizing:border-box;resize:vertical;">${project.description ?? ""}</textarea>
              </div>
              <div style="margin-bottom:1rem;">
                <label style="display:block;font-size:0.875rem;font-weight:500;color:var(--text-color);margin-bottom:0.5rem;">Tech Stack</label>
                <input type="text" name="stack" value="${project.stack ?? ""}" placeholder="e.g. Next.js, Postgres, Tailwind" class="input" style="width:100%;box-sizing:border-box;" />
              </div>
              <div style="display:flex;gap:0.75rem;margin-top:1.5rem;">
                <button type="submit" class="btn btn-primary">Save Changes</button>
              </div>
            </form>
            <div style="margin-top:3rem;padding-top:2rem;border-top:1px solid var(--border-color);">
              <h3 style="font-size:1rem;font-weight:600;color:var(--danger-color);margin:0 0 0.75rem;">Danger Zone</h3>
              <form method="POST" action="/projects/${project.projectId}/delete"
                onsubmit="return confirm('Delete project &quot;${project.name}&quot;? This cannot be undone.')">
                <button type="submit" class="btn" style="background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.3);">
                  <i class="fas fa-trash"></i> Delete Project
                </button>
              </form>
            </div>
          </div>
        ` : ""}
      </div>
    </div>
  </div>

  <script src="/public/js/sidebar.js"></script>

</body>
</html>`;

}
