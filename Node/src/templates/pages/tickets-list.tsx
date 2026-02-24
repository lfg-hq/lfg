import { html, raw } from "hono/html";

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
  createdAt?: Date | string;
  updatedAt?: Date | string;
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
  <script>(function(){if(localStorage.getItem('sidebarMinimized')==='true'){document.documentElement.classList.add('sidebar-minimized-preload');}})()</script>
  <link rel="stylesheet" href="/public/css/theme-variables.css" />
  <link rel="stylesheet" href="/public/css/common.css" />
  <link rel="stylesheet" href="/public/css/sidebar.css" />
  <link rel="stylesheet" href="/public/css/tickets.css" />
  <link rel="stylesheet" href="/public/css/polish.css" />
  <link rel="stylesheet" href="/public/css/light/light-mode.css" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
  <script src="/public/js/theme-switcher.js"></script>
  <style>
    /* Layout overrides — not in tickets.css */
    .tickets-page { height: 100vh; overflow: hidden; display: flex; flex-direction: column; }
    .tickets-toolbar {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.625rem 1.25rem;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      background: var(--background-color, #121212);
      flex-shrink: 0;
    }
    .tickets-toolbar .filter-search { min-width: 180px; }
    .toolbar-spacer { flex: 1; }
    .toolbar-btn-new {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.4rem 1rem;
      font-size: 0.8125rem;
      font-weight: 600;
      border-radius: 999px;
      border: none;
      background: linear-gradient(135deg, #7c3aed, #8b5cf6);
      color: white;
      cursor: pointer;
      text-decoration: none;
      white-space: nowrap;
      box-shadow: 0 4px 12px rgba(124,58,237,0.35);
      transition: opacity 0.2s ease;
    }
    .toolbar-btn-new:hover { opacity: 0.88; }
    .kanban-wrap {
      flex: 1;
      overflow: hidden;
      padding: 1rem 1.25rem;
      display: flex;
      flex-direction: column;
    }
    /* Tab panes — not in tickets.css */
    .drawer-tab-content { display: none !important; }
    .drawer-tab-content.active { display: flex !important; flex-direction: column; flex: 1; }
    #tab-actions.active { padding: 0; position: relative; }
    #tab-preview.active { padding: 0; }
    .placeholder-pane { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-secondary); opacity: 0.4; gap: 0.75rem; }
    .placeholder-pane i { font-size: 2rem; }
    .placeholder-pane p { font-size: 0.875rem; margin: 0; }
    /* Agent thinking indicator */
    .agent-thinking-dots {
      font-size: .8rem;
      color: #a78bfa;
      animation: thinkPulse 1.5s ease-in-out infinite;
    }
    @keyframes thinkPulse {
      0%, 100% { opacity: 0.4; }
      50%      { opacity: 1; }
    }
  </style>
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
              <i class="fas fa-th-large"></i><span>All Projects</span>
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
          <i class="fas fa-comments"></i><span class="nav-text">Chat</span>
        </a>
        <a href="/projects/${project.projectId}" class="nav-link">
          <i class="fas fa-tachometer-alt"></i><span class="nav-text">Dashboard</span>
        </a>
        <a href="/projects/${project.projectId}/tickets" class="nav-link active">
          <i class="fas fa-tasks"></i><span class="nav-text">Tickets</span>
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
          <div class="user-avatar"><div class="avatar-text">${avatarLetter}</div></div>
          <div class="user-details"><span class="username">${user.name}</span></div>
          <i class="fas fa-chevron-down dropdown-icon"></i>
        </button>
        <div class="user-dropdown" id="user-dropdown">
          <a href="/settings" class="dropdown-item"><i class="fas fa-cog"></i><span>Settings</span></a>
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

  <!-- Main tickets page -->
  <div class="tickets-page">

    <!-- Toolbar -->
    <div class="tickets-toolbar">
      <input class="filter-search" type="text" placeholder="Search tickets..." id="ticket-search" oninput="filterTickets()" />
      <select class="filter-select" id="filter-status" onchange="filterTickets()">
        <option value="">All Statuses</option>
        <option value="open">Open</option>
        <option value="in_progress">In Progress</option>
        <option value="review">Review</option>
        <option value="done">Done</option>
        <option value="failed">Failed</option>
        <option value="blocked">Blocked</option>
      </select>
      <select class="filter-select" id="filter-priority" onchange="filterTickets()">
        <option value="">All Priorities</option>
        <option value="High">High</option>
        <option value="Medium">Medium</option>
        <option value="Low">Low</option>
      </select>
      <div class="toolbar-spacer"></div>
      <a href="/chat/project/${project.projectId}" class="toolbar-btn-new">
        <i class="fas fa-plus"></i> New Ticket
      </a>
    </div>

    <!-- Kanban board -->
    <div class="kanban-wrap">
      <div class="kanban-board" id="kanban-board">
        ${stages.map((stage) => {
          const stageTickets = byStage[stage.id] ?? [];
          return html`
            <div class="kanban-column" data-stage-id="${stage.id}">
              <div class="kanban-column-header" style="border-top-color:${stage.color};">
                <div class="kanban-column-title">
                  <span class="stage-color-dot" style="background:${stage.color};"></span>
                  <span class="stage-name">${stage.name}</span>
                  <span class="ticket-count">${stageTickets.length}</span>
                </div>
              </div>
              <div class="kanban-column-body" data-stage-id="${stage.id}">
                ${stageTickets.length === 0 ? html`
                  <div style="text-align:center;padding:1.5rem;color:var(--text-secondary);font-size:0.8rem;opacity:0.4;">No tickets</div>
                ` : stageTickets.map((t) => html`
                  <div class="kanban-card" data-ticket-id="${t.id}" data-status="${t.status}" data-priority="${t.priority}"
                       draggable="true" onclick="openTicketDrawer('${t.id}')">
                    <div class="kanban-card-header">
                      <span class="kanban-card-title">${t.name}</span>
                    </div>
                    <div class="kanban-card-meta">
                      <span class="priority-label" style="color:${PRIORITY_COLOR[t.priority] ?? "#6b7280"};">
                        <span class="kanban-priority-dot" style="background:${PRIORITY_COLOR[t.priority] ?? "#6b7280"};"></span>
                        ${t.priority}
                      </span>
                    </div>
                  </div>
                `)}
              </div>
            </div>
          `;
        })}
        ${unstaged.length > 0 ? html`
          <div class="kanban-column" style="border-top-color:#6b7280;">
            <div class="kanban-column-header">
              <div class="kanban-column-title">
                <span class="stage-color-dot" style="background:#6b7280;"></span>
                <span class="stage-name">Unassigned</span>
                <span class="ticket-count">${unstaged.length}</span>
              </div>
            </div>
            <div class="kanban-column-body">
              ${unstaged.map((t) => html`
                <div class="kanban-card" data-ticket-id="${t.id}" data-status="${t.status}" data-priority="${t.priority}"
                     draggable="true" onclick="openTicketDrawer('${t.id}')">
                  <div class="kanban-card-header">
                    <span class="kanban-card-title">${t.name}</span>
                  </div>
                  <div class="kanban-card-meta">
                    <span class="priority-label" style="color:${PRIORITY_COLOR[t.priority] ?? "#6b7280"};">
                      <span class="kanban-priority-dot" style="background:${PRIORITY_COLOR[t.priority] ?? "#6b7280"};"></span>
                      ${t.priority}
                    </span>
                  </div>
                </div>
              `)}
            </div>
          </div>
        ` : ""}
      </div>
    </div>
  </div>
</div>

<!-- Drawer overlay -->
<div class="drawer-overlay" id="drawer-overlay"></div>

<!-- Ticket detail drawer -->
<div class="drawer" id="ticket-drawer">
  <div class="drawer-resize-handle" id="drawer-resize-handle"></div>

  <!-- Drawer header -->
  <div class="drawer-header">
    <div class="drawer-header-left">
      <div class="drawer-title" id="drawer-title"></div>
    </div>
    <div class="drawer-header-right">
      <div class="drawer-actions">
        <button class="drawer-server-btn" onclick="restartPreview()"><i class="fas fa-redo"></i> Restart Server</button>
        <button class="drawer-execute-btn" id="drawer-build-btn" onclick="buildCurrentTicket()">
          <i class="fas fa-bolt"></i> Build Ticket
        </button>
        <div class="drawer-more-menu">
          <button class="drawer-more-btn" onclick="toggleDrawerMore()">
            <i class="fas fa-ellipsis-v"></i>
          </button>
          <div class="drawer-more-dropdown" id="drawer-more-dropdown">
            <button class="drawer-more-item drawer-more-item--danger" onclick="deleteCurrentTicket()">
              <i class="fas fa-trash"></i> Delete Ticket
            </button>
          </div>
        </div>
        <button class="drawer-close" onclick="closeTicketDrawer()">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>
  </div>

  <!-- Drawer tabs -->
  <div class="drawer-tabs">
    <button class="drawer-tab active" data-tab="details" onclick="switchDrawerTab('details', this)">
      <i class="fas fa-info-circle"></i> Details
    </button>
    <button class="drawer-tab" data-tab="actions" onclick="switchDrawerTab('actions', this)">
      <i class="fas fa-terminal"></i> Actions
    </button>
    <button class="drawer-tab" data-tab="tasks" onclick="switchDrawerTab('tasks', this)">
      <i class="fas fa-list-check"></i> Tasks
    </button>
    <button class="drawer-tab" data-tab="preview" onclick="switchDrawerTab('preview', this)">
      <i class="fas fa-desktop"></i> Preview
    </button>
    <button class="drawer-tab" data-tab="git" onclick="switchDrawerTab('git', this)">
      <i class="fab fa-github"></i> Git
    </button>
    <button class="drawer-tab" data-tab="logs" onclick="switchDrawerTab('logs', this)">
      <i class="fas fa-file-alt"></i> Server Logs
    </button>
  </div>

  <!-- Drawer body -->
  <div class="drawer-body">

    <!-- Details tab -->
    <div class="drawer-tab-content active" id="tab-details">
      <div class="ticket-detail-drawer">
        <div class="detail-meta-row">
          <span class="detail-label status-label" id="drawer-status"></span>
          <span class="detail-label priority-label" id="drawer-priority"></span>
          <div class="detail-meta-spacer"></div>
          <button type="button" class="detail-edit-btn"><i class="fas fa-pen"></i> Edit</button>
          <button type="button" class="detail-delete-btn" onclick="deleteCurrentTicket()"><i class="fas fa-trash"></i></button>
        </div>
        <div class="detail-section">
          <h4>Description</h4>
          <p id="drawer-description"></p>
        </div>
        <div class="detail-section" id="drawer-linked-docs" style="display:none;">
          <h4>Linked Documents</h4>
          <div id="drawer-linked-docs-list"></div>
        </div>
        <div class="detail-section">
          <h4>Details</h4>
          <div class="detail-grid">
            <div class="detail-grid-item">
              <div class="label">Created</div>
              <div class="value" id="drawer-created"></div>
            </div>
            <div class="detail-grid-item">
              <div class="label">Updated</div>
              <div class="value" id="drawer-updated"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Actions tab: Execution logs + chat -->
    <div class="drawer-tab-content" id="tab-actions">
      <!-- Git branch banner (hidden by default) -->
      <div id="actions-git-banner" style="display:none;padding:.5rem 1rem;background:rgba(139,92,246,.06);border-bottom:1px solid rgba(139,92,246,.12);flex-shrink:0;">
        <div style="display:flex;align-items:center;gap:.5rem;font-size:.8rem;">
          <i class="fas fa-code-branch" style="color:#a78bfa;font-size:.75rem;"></i>
          <code id="actions-git-branch" style="color:#c4b5fd;font-size:.8rem;">—</code>
          <span style="color:rgba(255,255,255,.25);margin:0 .25rem;">·</span>
          <code id="actions-git-sha" style="color:rgba(255,255,255,.35);font-size:.75rem;">—</code>
        </div>
      </div>
      <!-- Log rows -->
      <div id="actions-log-area" class="execution-logs-container"></div>
      <!-- Chat input (fixed to bottom) -->
      <div class="logs-chat-container">
        <div class="logs-chat-field">
          <input id="actions-chat-input" type="text" placeholder="Send a message to the agent..."
            onkeydown="if(event.key==='Enter'){sendTicketChatMsg();}" />
          <button onclick="sendTicketChatMsg()" class="logs-chat-send-btn" title="Send message">
            <i class="fas fa-arrow-up" style="font-size:.65rem;"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Tasks tab -->
    <div class="drawer-tab-content" id="tab-tasks">
      <div id="tasks-list" style="flex:1;overflow-y:auto;padding:0.875rem 1rem;display:flex;flex-direction:column;gap:0.5rem;">
        <div class="placeholder-pane"><i class="fas fa-list-check"></i><p>No tasks yet</p></div>
      </div>
    </div>

    <!-- Preview tab -->
    <div class="drawer-tab-content" id="tab-preview">
      <div id="preview-toolbar" style="display:flex;align-items:center;gap:0.5rem;padding:0.5rem 0.75rem;border-bottom:1px solid rgba(255,255,255,0.07);flex-shrink:0;background:rgba(0,0,0,0.2);">
        <span id="preview-url-label" style="flex:1;font-size:0.775rem;color:rgba(255,255,255,0.4);font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Not started</span>
        <button id="preview-start-btn" onclick="startPreview()" style="padding:0.3rem 0.6rem;background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.25);border-radius:5px;font-size:0.75rem;cursor:pointer;">
          <i class="fas fa-play"></i> Start
        </button>
        <button onclick="restartPreview()" style="padding:0.3rem 0.6rem;background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:5px;font-size:0.75rem;cursor:pointer;" title="Restart server">
          <i class="fas fa-redo"></i>
        </button>
        <a id="preview-open-link" href="#" target="_blank" style="padding:0.3rem 0.6rem;background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:5px;font-size:0.75rem;cursor:pointer;text-decoration:none;display:none;" title="Open in new tab">
          <i class="fas fa-external-link-alt"></i>
        </a>
      </div>
      <iframe id="preview-iframe" src="about:blank" style="flex:1;width:100%;border:none;background:#0a0a0a;"></iframe>
    </div>

    <!-- Git tab -->
    <div class="drawer-tab-content" id="tab-git">
      <div id="git-info" style="flex:1;overflow-y:auto;padding:1rem;">
        <div class="placeholder-pane"><i class="fab fa-github"></i><p>Loading git info…</p></div>
      </div>
    </div>

    <!-- Server Logs tab -->
    <div class="drawer-tab-content" id="tab-logs">
      <div id="server-logs-area" style="flex:1;overflow-y:auto;padding:0.625rem 0.875rem;font-family:monospace;font-size:0.775rem;line-height:1.6;color:rgba(255,255,255,0.7);"></div>
      <div style="border-top:1px solid rgba(255,255,255,0.07);padding:0.5rem 0.875rem;display:flex;gap:0.5rem;">
        <button onclick="refreshServerLogs()" style="padding:0.3rem 0.75rem;background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.55);border:1px solid rgba(255,255,255,0.1);border-radius:6px;font-size:0.775rem;cursor:pointer;">
          <i class="fas fa-sync-alt"></i> Refresh
        </button>
      </div>
    </div>
  </div>
</div>

<script src="/public/js/sidebar.js"></script>
<script>
  const PROJECT_ID = document.body.dataset.projectId;
  let _currentTicketId = null;

  // Restore drawer state from sessionStorage on page load
  (function restoreDrawer() {
    var saved = sessionStorage.getItem('lfg_drawer_ticket_' + PROJECT_ID);
    if (saved) {
      // Defer so DOM is ready and ticketMap is populated
      setTimeout(function() { openTicketDrawer(saved); }, 0);
    }
  })();

  // Inline ticket data (avoids extra fetch on click)
  const TICKET_DATA = ${raw(JSON.stringify(
    tickets.map((t, i) => ({
      id: t.id,
      name: t.name,
      status: t.status ?? "open",
      priority: t.priority ?? "Medium",
      description: t.description ?? "",
      complexity: t.complexity ?? "medium",
      createdAt: t.createdAt
        ? new Date(t.createdAt as string).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
        : "—",
      updatedAt: t.updatedAt
        ? new Date(t.updatedAt as string).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
        : "—",
      index: i + 1,
    }))
  // Escape </ to prevent HTML parser terminating the script tag on </script in data
  ).replace(/<\//g, "<\\/"))};
  const ticketMap = Object.fromEntries(TICKET_DATA.map(t => [t.id, t]));

  function openTicketDrawer(ticketId) {
    stopLogPolling();
    _lastLogCount = 0;
    _lastLogContent = '';
    _logsFirstLoad = true;
    _currentTicketId = ticketId;
    const t = ticketMap[ticketId];
    if (!t) return;

    document.getElementById('drawer-title').textContent = 'TKT-' + t.index + ': ' + t.name;

    const sb = document.getElementById('drawer-status');
    sb.textContent = t.status.replace(/_/g, ' ');
    sb.className = 'detail-label status-label status-' + t.status;

    const pb = document.getElementById('drawer-priority');
    pb.textContent = t.priority;
    pb.className = 'detail-label priority-label priority-' + t.priority.toLowerCase();

    document.getElementById('drawer-description').textContent = t.description || 'No description provided.';
    document.getElementById('drawer-created').textContent = t.createdAt;
    document.getElementById('drawer-updated').textContent = t.updatedAt;

    // Pre-clear log area
    const actionsArea = document.getElementById('actions-log-area');
    if (actionsArea) actionsArea.innerHTML = '';

    // Persist drawer state so it survives page reload / re-render
    sessionStorage.setItem('lfg_drawer_ticket_' + PROJECT_ID, ticketId);

    // Show drawer immediately with Details tab as default
    document.getElementById('ticket-drawer').classList.add('active');

    // Fetch LIVE ticket status to detect executing tickets (ticketMap is stale)
    fetch('/api/projects/' + PROJECT_ID + '/tickets/' + ticketId)
      .then(function(r) { return r.json(); })
      .then(function(live) {
        var qs = live.queueStatus || live.queue_status || '';
        var st = live.status || t.status;
        var isActive = qs === 'queued' || qs === 'executing' || st === 'in_progress';
        var buildBtn = document.getElementById('drawer-build-btn');
        buildBtn.disabled = isActive;
        buildBtn.innerHTML = isActive
          ? '<i class="fas fa-spinner fa-spin"></i> Building…'
          : '<i class="fas fa-bolt"></i> Build Ticket';
        // If executing, switch to Actions tab so user sees live logs
        if (isActive) {
          switchDrawerTab('actions', document.querySelector('.drawer-tab[data-tab="actions"]'));
        } else {
          switchDrawerTab('details', document.querySelector('.drawer-tab[data-tab="details"]'));
        }
      }).catch(function() {
        switchDrawerTab('details', document.querySelector('.drawer-tab[data-tab="details"]'));
      });
  }

  function closeTicketDrawer() {
    stopLogPolling();
    document.getElementById('ticket-drawer').classList.remove('active');
    sessionStorage.removeItem('lfg_drawer_ticket_' + PROJECT_ID);
    _currentTicketId = null;
    _lastLogCount = 0;
    _lastLogContent = '';
    _logsFirstLoad = true;
  }

  function switchDrawerTab(tabId, btn) {
    document.querySelectorAll('.drawer-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.drawer-tab-content').forEach(p => p.classList.remove('active'));
    if (btn) btn.classList.add('active');
    const pane = document.getElementById('tab-' + tabId);
    if (pane) pane.classList.add('active');
    // Lazy-load tab data
    if (tabId === 'actions') {
      _lastLogCount = 0;
      _lastLogContent = '';
      _logsFirstLoad = true;
      loadExecutionLogs();
      // Always start polling — the interval self-stops when ticket is idle
      startLogPolling();
    } else {
      stopLogPolling();
    }
    if (tabId === 'tasks')   loadTasks();
    if (tabId === 'git')     loadGitInfo();
    if (tabId === 'logs')    refreshServerLogs();
    if (tabId === 'preview') loadSandboxInfo();
  }

  // ── Build Ticket ─────────────────────────────────────────────────
  async function buildCurrentTicket() {
    if (!_currentTicketId) return;
    const btn = document.getElementById('drawer-build-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Queuing…';
    try {
      const res = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId + '/queue', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.error || 'Failed to queue ticket');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-bolt"></i> Build Ticket';
        return;
      }
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Building…';
      // Switch to Actions tab so user sees logs immediately
      switchDrawerTab('actions', document.querySelector('.drawer-tab[data-tab="actions"]'));
      startLogPolling();
    } catch(e) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-bolt"></i> Build Ticket';
      alert('Failed to queue ticket: ' + e.message);
    }
  }

  // ── Actions tab: execution logs + agent chat ─────────────────────
  let _logPollTimer = null;
  let _lastLogCount = 0;
  let _lastLogContent = '';

  function startLogPolling() {
    stopLogPolling();
    console.log('[logs] polling started for ticket', _currentTicketId);
    _logPollTimer = setInterval(async () => {
      await loadExecutionLogs();
      // Check if ticket is done — stop polling and refresh button state
      if (!_currentTicketId) { stopLogPolling(); return; }
      try {
        const t = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId)
          .then(r => r.json());
        // Handle both camelCase and snake_case API responses
        const qs = t.queueStatus || t.queue_status || '';
        const st = t.status || '';
        const active = qs === 'queued' || qs === 'executing' || st === 'in_progress';
        if (!active) {
          stopLogPolling();
          const btn = document.getElementById('drawer-build-btn');
          if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-bolt"></i> Build Ticket'; }
          // Refresh kanban card status badge
          const card = document.querySelector('.kanban-card[data-ticket-id="' + _currentTicketId + '"]');
          if (card) {
            const badge = card.querySelector('.kanban-status');
            if (badge) { badge.textContent = st.replace(/_/g, ' '); badge.className = 'kanban-status status-' + st; }
          }
        }
      } catch(e) {}
    }, 3000);
  }

  function stopLogPolling() {
    if (_logPollTimer) { clearInterval(_logPollTimer); _logPollTimer = null; }
  }

  function fmtLogTime(ts) {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('en-US', { month:'short', day:'numeric', hour:'numeric', minute:'2-digit', second:'2-digit', hour12:true });
    } catch(e) { return ''; }
  }

  // Derive a short description from a command message (like Django shows)
  function describeCmd(msg, explanation) {
    // If the API returned an explanation, use it
    if (explanation) return explanation;
    // Derive from message content
    if (msg.startsWith('$ ')) {
      // Bash command — try to describe it
      var cmd = msg.slice(2).trim();
      if (cmd.startsWith('npm install') || cmd.startsWith('bun add') || cmd.startsWith('yarn add'))
        return 'Install dependencies';
      if (cmd.startsWith('npm run build') || cmd.startsWith('bun run build'))
        return 'Build project';
      if (cmd.startsWith('npm run dev') || cmd.startsWith('bun run dev'))
        return 'Start dev server';
      if (cmd.startsWith('npx create-') || cmd.startsWith('bunx create-'))
        return 'Create project scaffold';
      if (cmd.startsWith('mkdir')) return 'Create directory';
      if (cmd.startsWith('cat ')) return 'Read file: ' + cmd.slice(4).split(' ')[0];
      if (cmd.startsWith('ls ')) return 'List directory';
      // Fall back to first ~80 chars
      return cmd.length > 80 ? cmd.slice(0, 80) + '...' : cmd;
    }
    if (msg.includes('Read:')) return msg.replace(/^[^\w]*/, '');
    if (msg.includes('Write:')) return 'Writing file: ' + msg.split(':').slice(1).join(':').trim();
    if (msg.includes('Edit:')) return 'Editing file: ' + msg.split(':').slice(1).join(':').trim();
    if (msg.includes('TodoWrite') || msg.includes('updating tasks')) return 'Updating task list';
    if (msg.includes('Grep:') || msg.includes('Glob:')) return msg.replace(/^[^\w]*/, '');
    // Generic — truncate
    return msg.length > 100 ? msg.slice(0, 100) + '...' : msg;
  }

  function renderLogEntry(row, idx) {
    var msg = (row.message || '').trim();
    var explanation = (row.explanation || '').trim();
    var ts = fmtLogTime(row.createdAt);
    var type = row.type || 'command';
    var rowId = 'log-' + idx;
    var el = document.createElement('div');
    el.className = 'log-entry';

    if (type === 'ai_response') {
      // Agent — green left border, always expanded
      el.className += ' log-agent';
      el.innerHTML =
        '<div class="log-agent-header">' +
          '<span class="log-agent-label">Agent</span>' +
          '<span class="log-time">' + ts + '</span>' +
        '</div>' +
        '<div class="log-agent-content">' + escHtml(msg) + '</div>';

    } else if (type === 'user_message') {
      // User — purple left border
      el.className += ' log-user';
      el.innerHTML =
        '<div class="log-user-header">' +
          '<span class="log-user-label">You</span>' +
          '<span class="log-time">' + ts + '</span>' +
        '</div>' +
        '<div class="log-user-content">' + escHtml(msg) + '</div>';

    } else {
      // Command / system — show description, expand for details (like Django)
      el.className += ' log-cmd';
      var desc = describeCmd(msg, explanation);
      el.innerHTML =
        '<div class="log-cmd-header">' +
          '<i id="' + rowId + '-chev" class="fas fa-chevron-right log-chev"></i>' +
          '<span class="log-cmd-text">' + escHtml(desc) + '</span>' +
          '<span class="log-time">' + ts + '</span>' +
        '</div>' +
        '<div id="' + rowId + '" class="log-cmd-body">' + escHtml(msg) + '</div>';
      el.querySelector('.log-cmd-header').onclick = function() { toggleCmd(rowId); };
    }
    return el;
  }

  function toggleCmd(id) {
    var details = document.getElementById(id);
    var chev = document.getElementById(id + '-chev');
    if (!details) return;
    var showing = details.style.display === 'block';
    details.style.display = showing ? 'none' : 'block';
    if (chev) chev.style.transform = showing ? '' : 'rotate(90deg)';
  }

  var _logsFirstLoad = true;
  async function loadExecutionLogs() {
    if (!_currentTicketId) return;
    try {
      var res = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId + '/logs');
      var rows = await res.json();
      var area = document.getElementById('actions-log-area');
      if (!area) return;
      if (!rows.length) {
        area.innerHTML = '<div class="log-placeholder">' +
          '<i class="fas fa-terminal" style="font-size:1.5rem;margin-bottom:.75rem;display:block;opacity:.4;"></i>' +
          'No execution logs yet.<br>Logs will appear here when the ticket is built.</div>';
        _lastLogCount = 0;
        _logsFirstLoad = true;
        return;
      }
      var contentKey = rows.length + ':' + (rows[rows.length - 1].id || rows[rows.length - 1].createdAt || '');
      if (contentKey === _lastLogContent) return;
      _lastLogContent = contentKey;
      _lastLogCount = rows.length;

      updateActionsBanner();

      var scrollContainer = area.closest('.drawer-body') || area;
      var shouldScroll = _logsFirstLoad || (scrollContainer.scrollHeight - scrollContainer.scrollTop - scrollContainer.clientHeight < 60);
      area.innerHTML = '';

      rows.forEach(function(row, idx) {
        area.appendChild(renderLogEntry(row, idx));
      });

      if (shouldScroll) {
        requestAnimationFrame(function() {
          // .drawer-body is the actual scroll container
          var scrollParent = area.closest('.drawer-body') || area;
          scrollParent.scrollTop = scrollParent.scrollHeight;
        });
      }
      _logsFirstLoad = false;
    } catch(e) { console.error('loadExecutionLogs', e); }
  }

  async function updateActionsBanner() {
    if (!_currentTicketId) return;
    try {
      var ticket = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId).then(function(r) { return r.json(); });
      var branch = ticket.github_branch || ticket.githubBranch;
      var sha = ticket.github_commit_sha || ticket.githubCommitSha;
      var banner = document.getElementById('actions-git-banner');
      if (banner && branch) {
        document.getElementById('actions-git-branch').textContent = branch;
        document.getElementById('actions-git-sha').textContent = sha ? sha.slice(0, 7) : '';
        banner.style.display = 'block';
      }
    } catch(e) {}
  }

  function escHtml(s) {
    const m = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'};
    return String(s).replace(/[&<>"]/g, function(c) { return m[c] || c; });
  }

  function showThinkingIndicator() {
    hideThinkingIndicator();
    var area = document.getElementById('actions-log-area');
    if (!area) return;
    var el = document.createElement('div');
    el.id = 'agent-thinking';
    el.className = 'log-entry log-agent';
    el.innerHTML = '<div class="log-agent-header">' +
      '<span class="log-agent-label">AGENT</span>' +
      '<span class="agent-thinking-dots">Thinking<span class="dot-anim">...</span></span>' +
      '</div>';
    area.appendChild(el);
    var scrollParent = area.closest('.drawer-body') || area;
    requestAnimationFrame(function() { scrollParent.scrollTop = scrollParent.scrollHeight; });
  }

  function hideThinkingIndicator() {
    var el = document.getElementById('agent-thinking');
    if (el) el.remove();
  }

  async function sendTicketChatMsg() {
    var input = document.getElementById('actions-chat-input');
    var msg = input.value.trim();
    if (!msg || !_currentTicketId) return;
    input.value = '';
    // Show thinking indicator
    showThinkingIndicator();
    try {
      var resp = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId + '/chat', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ message: msg })
      });
      if (!resp.ok) {
        var err = await resp.json().catch(function() { return { error: 'Failed' }; });
        console.error('sendTicketChatMsg error:', err);
        hideThinkingIndicator();
      }
      _lastLogCount = 0; _lastLogContent = ''; _logsFirstLoad = true;
      setTimeout(loadExecutionLogs, 800);
      startLogPolling();
    } catch(e) { console.error('sendTicketChatMsg', e); hideThinkingIndicator(); }
  }

  // ── Tasks tab ────────────────────────────────────────────────────
  async function loadTasks() {
    if (!_currentTicketId) return;
    try {
      const res = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId + '/tasks');
      const tasks = await res.json();
      const list = document.getElementById('tasks-list');
      if (!list) return;
      if (!tasks.length) {
        list.innerHTML = '<div class="placeholder-pane"><i class="fas fa-list-check"></i><p>No tasks yet</p></div>';
        return;
      }
      const statusIcon = { pending:'○', in_progress:'◑', success:'●', fail:'✕' };
      const statusColor = { pending:'rgba(255,255,255,0.3)', in_progress:'#f59e0b', success:'#34d399', fail:'#f87171' };
      list.innerHTML = tasks.map(t => {
        const icon = statusIcon[t.status] || '○';
        const color = statusColor[t.status] || 'rgba(255,255,255,0.3)';
        return '<div style="display:flex;gap:0.625rem;align-items:flex-start;padding:0.5rem 0.625rem;border-radius:7px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">'
          + '<span style="color:' + color + ';font-size:1rem;margin-top:1px;flex-shrink:0;">' + icon + '</span>'
          + '<span style="font-size:0.8375rem;color:rgba(255,255,255,0.8);line-height:1.5;">' + (t.description || '') + '</span>'
          + '</div>';
      }).join('');
    } catch(e) { console.error('loadTasks', e); }
  }

  // ── Preview tab ──────────────────────────────────────────────────
  async function loadSandboxInfo() {
    if (!_currentTicketId) return;
    try {
      const res = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId + '/sandbox');
      if (!res.ok) return;
      const sb = await res.json();
      if (!sb) return;
      const label = document.getElementById('preview-url-label');
      const link = document.getElementById('preview-open-link');
      const iframe = document.getElementById('preview-iframe');
      if (sb.previewUrl) {
        label.textContent = sb.previewUrl;
        link.href = sb.previewUrl;
        link.style.display = 'inline-flex';
        iframe.src = sb.previewUrl;
      }
    } catch(e) { console.error('loadSandboxInfo', e); }
  }

  async function startPreview() {
    if (!_currentTicketId) return;
    const btn = document.getElementById('preview-start-btn');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting…';
    btn.disabled = true;
    try {
      const res = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId + '/preview', {
        method: 'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ action: 'start' })
      });
      const data = await res.json();
      if (data.previewUrl) {
        document.getElementById('preview-url-label').textContent = data.previewUrl;
        const link = document.getElementById('preview-open-link');
        link.href = data.previewUrl; link.style.display = 'inline-flex';
        document.getElementById('preview-iframe').src = data.previewUrl;
      }
    } catch(e) { console.error('startPreview', e); }
    btn.innerHTML = '<i class="fas fa-play"></i> Start';
    btn.disabled = false;
  }

  async function restartPreview() {
    if (!_currentTicketId) return;
    try {
      await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId + '/preview', {
        method: 'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ action: 'restart' })
      });
      setTimeout(loadSandboxInfo, 4000);
    } catch(e) { console.error('restartPreview', e); }
  }

  // ── Git tab ──────────────────────────────────────────────────────
  async function loadGitInfo() {
    if (!_currentTicketId) return;
    const t = ticketMap[_currentTicketId];
    const info = document.getElementById('git-info');
    if (!t || !info) return;

    // We show ticket git fields from inline data (no extra fetch needed)
    const ticket = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId)
      .then(r => r.json()).catch(() => null);
    if (!ticket) return;

    const branch = ticket.github_branch || ticket.githubBranch || '—';
    const sha = ticket.github_commit_sha || ticket.githubCommitSha;
    const shortSha = sha ? sha.slice(0,7) : '—';
    const mergeStatus = ticket.github_merge_status || ticket.githubMergeStatus || '—';

    info.innerHTML = '<div style="display:flex;flex-direction:column;gap:0.875rem;font-size:0.8375rem;">'
      + '<div style="display:flex;flex-direction:column;gap:0.25rem;">'
      + '<span style="color:rgba(255,255,255,0.4);font-size:0.75rem;text-transform:uppercase;letter-spacing:.05em;">Branch</span>'
      + '<code style="color:#c4b5fd;background:rgba(139,92,246,0.1);padding:.2rem .5rem;border-radius:5px;">' + branch + '</code>'
      + '</div>'
      + '<div style="display:flex;flex-direction:column;gap:0.25rem;">'
      + '<span style="color:rgba(255,255,255,0.4);font-size:0.75rem;text-transform:uppercase;letter-spacing:.05em;">Last Commit</span>'
      + '<code style="color:#94a3b8;">' + shortSha + '</code>'
      + '</div>'
      + '<div style="display:flex;flex-direction:column;gap:0.25rem;">'
      + '<span style="color:rgba(255,255,255,0.4);font-size:0.75rem;text-transform:uppercase;letter-spacing:.05em;">Merge Status</span>'
      + '<span style="color:rgba(255,255,255,0.7);">' + mergeStatus + '</span>'
      + '</div>'
      + '</div>';
  }

  // ── Server logs tab ──────────────────────────────────────────────
  async function refreshServerLogs() {
    if (!_currentTicketId) return;
    try {
      const sb = await fetch('/api/projects/' + PROJECT_ID + '/tickets/' + _currentTicketId + '/sandbox')
        .then(r => r.json()).catch(() => null);
      if (!sb) return;
      const area = document.getElementById('server-logs-area');
      if (!area) return;
      // Re-use the sandbox logs endpoint via CLI route isn't set yet; show sandbox status
      area.innerHTML = '<div style="color:rgba(255,255,255,0.3);">Sandbox status: ' + (sb.status || '—') + '</div>'
        + (sb.previewUrl ? '<div style="color:#34d399;">Server running at ' + sb.previewUrl + '</div>' : '<div style="color:rgba(255,255,255,0.3);">Server not started</div>');
    } catch(e) { console.error('refreshServerLogs', e); }
  }

  function toggleDrawerMore() {
    document.getElementById('drawer-more-dropdown').classList.toggle('open');
  }
  document.addEventListener('click', e => {
    if (!e.target.closest('.drawer-more-menu')) {
      document.getElementById('drawer-more-dropdown')?.classList.remove('open');
    }
  });

  async function deleteCurrentTicket() {
    if (!_currentTicketId) return;
    if (!confirm('Delete this ticket?')) return;
    try {
      const res = await fetch('/projects/' + PROJECT_ID + '/api/checklist/' + _currentTicketId + '/delete', { method: 'DELETE' });
      if (res.ok) { closeTicketDrawer(); location.reload(); }
    } catch(e) { alert('Failed to delete ticket'); }
  }

  function filterTickets() {
    const q = document.getElementById('ticket-search').value.toLowerCase();
    const status = document.getElementById('filter-status').value;
    const priority = document.getElementById('filter-priority').value;
    document.querySelectorAll('.kanban-card').forEach(card => {
      const name = card.querySelector('.kanban-card-title')?.textContent?.toLowerCase() || '';
      const s = card.dataset.status;
      const p = card.dataset.priority;
      const show = (!q || name.includes(q)) && (!status || s === status) && (!priority || p === priority);
      card.style.display = show ? '' : 'none';
    });
  }

  // Drag & drop
  let _dragId = null;
  document.querySelectorAll('.kanban-card').forEach(card => {
    card.addEventListener('dragstart', e => {
      _dragId = card.dataset.ticketId;
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    card.addEventListener('dragend', () => { card.classList.remove('dragging'); _dragId = null; });
  });
  document.querySelectorAll('.kanban-column-body').forEach(col => {
    col.addEventListener('dragover', e => { e.preventDefault(); col.classList.add('drag-over'); });
    col.addEventListener('dragleave', () => col.classList.remove('drag-over'));
    col.addEventListener('drop', async e => {
      e.preventDefault();
      col.classList.remove('drag-over');
      const stageId = col.dataset.stageId;
      if (!_dragId || !stageId) return;
      try {
        await fetch('/projects/' + PROJECT_ID + '/api/checklist/' + _dragId + '/stage', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stageId })
        });
        location.reload();
      } catch(e) { console.error('Move failed', e); }
    });
  });

  // Drawer resize
  (function() {
    const handle = document.getElementById('drawer-resize-handle');
    const drawer = document.getElementById('ticket-drawer');
    let resizing = false, startX = 0, startW = 0;
    handle.addEventListener('mousedown', e => {
      resizing = true; startX = e.clientX; startW = drawer.offsetWidth;
      drawer.classList.add('resizing');
      document.body.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', e => {
      if (!resizing) return;
      const newW = Math.max(400, Math.min(window.innerWidth * 0.85, startW + (startX - e.clientX)));
      drawer.style.width = newW + 'px';
    });
    document.addEventListener('mouseup', () => {
      if (resizing) { resizing = false; drawer.classList.remove('resizing'); document.body.style.userSelect = ''; }
    });
  })();

  // ── WebSocket for live log updates ───────────────────────────────
  (function() {
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var wsUrl = proto + '//' + location.host + '/ws/chat';
    var ws = null;
    var reconnectTimer = null;

    function connectWS() {
      try {
        ws = new WebSocket(wsUrl);
      } catch(e) { console.warn('[ws] connect error', e); return; }

      ws.onopen = function() {
        console.log('[ws] connected for live ticket logs');
      };

      ws.onmessage = function(evt) {
        try {
          var msg = JSON.parse(evt.data);
          if (msg.type === 'ticket_log' && msg.ticketId === _currentTicketId) {
            console.log('[ws] live log:', msg.log.type, msg.log.message?.slice(0, 80));
            appendLiveLog(msg.log);
          }
        } catch(e) {}
      };

      ws.onclose = function() {
        console.log('[ws] disconnected, reconnecting in 5s...');
        reconnectTimer = setTimeout(connectWS, 5000);
      };

      ws.onerror = function() {
        // onclose will fire after onerror
      };
    }

    function appendLiveLog(log) {
      var area = document.getElementById('actions-log-area');
      if (!area) return;
      // Check if we are on Actions tab
      var actionsTab = document.getElementById('tab-actions');
      if (!actionsTab || !actionsTab.classList.contains('active')) return;

      // Hide thinking indicator when agent responds
      if (log.type !== 'user_message') hideThinkingIndicator();

      var placeholder = area.querySelector('.log-placeholder');
      if (placeholder) area.innerHTML = '';

      var idx = area.children.length;
      var scrollParent = area.closest('.drawer-body') || area;
      var wasAtBottom = !area.children.length || (scrollParent.scrollHeight - scrollParent.scrollTop - scrollParent.clientHeight < 120);
      area.appendChild(renderLogEntry(log, 'live-' + idx));

      if (wasAtBottom) {
        requestAnimationFrame(function() {
          var scrollParent = area.closest('.drawer-body') || area;
          scrollParent.scrollTop = scrollParent.scrollHeight;
        });
      }
      _lastLogCount = area.children.length;
      _lastLogContent = '';
    }

    connectWS();
  })();

  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.classList.remove('sidebar-minimized-preload');
  }));
</script>
</body>
</html>`;
}
