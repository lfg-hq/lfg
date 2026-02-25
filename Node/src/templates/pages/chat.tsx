import { html } from "hono/html";
import { ChatInput } from "../components/chat-input.tsx";

interface ChatPageProps {
  user: { id: string; name: string; email: string };
  projectId: string;
  projectName: string;
  conversationId?: string;
  modelKey?: string;
  roleKey?: string;
  models?: Array<{ key: string; providerLabel: string; requiresPro: boolean }>;
}

export function ChatPage({
  user,
  projectId,
  projectName,
  conversationId,
  modelKey = "claude_4.5_sonnet",
  roleKey = "product_analyst",
  models = [],
}: ChatPageProps) {
  return html`<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${projectName} — LFG</title>
  <script>(function(){if(localStorage.getItem('sidebarMinimized')==='true'){document.documentElement.classList.add('sidebar-minimized-preload');}})()</script>
  <link rel="stylesheet" href="/public/css/theme-variables.css" />
  <link rel="stylesheet" href="/public/css/common.css" />
  <link rel="stylesheet" href="/public/css/sidebar.css" />
  <link rel="stylesheet" href="/public/css/artifacts.css" />
  <link rel="stylesheet" href="/public/css/chat.css" />
  <link rel="stylesheet" href="/public/css/artifacts-fix.css" />
  <link rel="stylesheet" href="/public/css/polish.css" />
  <link rel="stylesheet" href="/public/css/light/light-mode.css" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
  <script src="/public/js/theme-switcher.js"></script>
</head>
<body
  data-user-id="${user.id}"
  data-user-name="${user.name}"
  data-project-id="${projectId}"
  data-model-key="${modelKey}"
  data-role-key="${roleKey}"
>
  <div class="messages" id="toast-container"></div>

  <div class="app-container">
    <!-- Sidebar -->
    <div class="sidebar" id="sidebar" data-current-project-id="${projectId}">
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
              <span class="project-name-text">${projectName}</span>
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
          <a href="/chat/project/${projectId}" id="new-chat-btn" class="new-chat-link">
            <i class="fas fa-pen-to-square"></i>
            <span class="button-text">New chat</span>
          </a>
        </div>
        <div class="sidebar-nav">
          <a href="/chat/project/${projectId}" class="nav-link chat-link active">
            <i class="fas fa-comments"></i>
            <span class="nav-text">Chat</span>
          </a>
          <a href="/projects/${projectId}" class="nav-link">
            <i class="fas fa-tachometer-alt"></i>
            <span class="nav-text">Dashboard</span>
          </a>
          <a href="/projects/${projectId}/tickets" class="nav-link">
            <i class="fas fa-tasks"></i>
            <span class="nav-text">Tickets</span>
          </a>
          <a href="/instant/project/${projectId}" class="nav-link">
            <i class="fas fa-bolt"></i>
            <span class="nav-text">Instant</span>
          </a>
        </div>
        <div class="conversations-section">
          <h3 class="sidebar-section-title">Recents</h3>
          <div id="conversation-list" class="conversation-list">
            <!-- Populated by JS -->
          </div>
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
              <div class="avatar-text">${(user.name?.[0] ?? user.email?.[0] ?? "?").toUpperCase()}</div>
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

    <!-- Main Chat Area -->
    <div class="chat-container">
      <!-- Project Header -->
      <div class="project-header">
        <div class="project-header-content">
          <div class="project-name-container" id="project-name-container">
            <h1 class="project-name" id="project-name-display">${projectName}</h1>
          </div>
          <button id="artifacts-button" class="artifacts-button" title="Toggle Artifacts Panel">
            <i class="fas fa-cube"></i>
          </button>
        </div>
      </div>

      <!-- Messages -->
      <div class="chat-messages" id="chat-messages">
        <div class="message-container">
          <div class="welcome-message">
            <h2>LFG 🚀</h2>
            <p>Start a conversation with the AI assistant below.</p>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      ${ChatInput({
        placeholder: "Type your message here...",
        models,
        selectedModelKey: modelKey,
        selectedRoleKey: roleKey,
        roleOptions: [{ key: "product_analyst", label: "Analyst" }],
        showTurboToggle: true,
        turboEnabled: false,
        showMic: true,
      })}
    </div>
  </div>

  <!-- Artifacts / document panel -->
  <div class="artifacts-container" id="artifacts-panel">
    <div class="resize-handle" id="resize-handle"></div>
    <div class="artifacts-accent-bar"></div>

    <!-- Tabs Navigation -->
    <div class="artifacts-tabs" style="display:flex;justify-content:space-between;align-items:center;">
      <div style="display:flex;">
        <button class="tab-button active" data-tab="filebrowser">Docs</button>
        <button class="tab-button" data-tab="checklist">Task List</button>
      </div>
      <button class="panel-arrow-right" id="artifacts-toggle" style="margin-left:auto;padding:8px;background:none;border:none;color:#ccc;cursor:pointer;">
        <i class="fas fa-chevron-right"></i>
      </button>
    </div>

    <div class="artifacts-content">
      <div class="tab-content">

        <!-- Checklist Tab -->
        <div class="tab-pane" id="checklist">
          <div class="empty-state">
            <div class="empty-state-icon"><i class="fas fa-check-square"></i></div>
            <div class="empty-state-text">No checklist items created yet.</div>
          </div>
        </div>

        <!-- File Browser Tab (active) -->
        <div class="tab-pane active" id="filebrowser">
          <div class="filebrowser-container" style="height:92%;display:flex;flex-direction:column;">
            <!-- Browser View -->
            <div id="filebrowser-main" style="height:100%;display:flex;flex-direction:column;">
              <div class="filebrowser-header" style="padding:20px;border-bottom:1px solid #2a2a2a;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:15px;">
                  <h3 style="color:#e2e8f0;margin:0;font-size:18px;font-weight:600;">Documents</h3>
                  <div style="display:flex;gap:10px;align-items:center;">
                    <select id="file-type-filter" style="padding:8px 12px;background:#1a1a1a;border:1px solid #333;border-radius:6px;color:#e2e8f0;font-size:13px;">
                      <option value="">All Types</option>
                    </select>
                    <button id="refresh-filebrowser" class="btn btn-sm" style="padding:8px 16px;background:#2a2a2a;color:#e2e8f0;border:1px solid #333;border-radius:6px;cursor:pointer;display:flex;align-items:center;gap:6px;font-size:13px;">
                      <i class="fas fa-sync-alt"></i> Refresh
                    </button>
                  </div>
                </div>
                <div style="position:relative;">
                  <input type="text" id="file-search" placeholder="Search documents..." style="width:100%;padding:10px 15px 10px 40px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#e2e8f0;font-size:14px;" />
                  <i class="fas fa-search" style="position:absolute;left:15px;top:50%;transform:translateY(-50%);color:#666;font-size:14px;"></i>
                </div>
              </div>
              <div class="filebrowser-content" style="flex:1;overflow-y:auto;">
                <div id="file-table-header" style="display:none;"></div>
                <div class="loading-state" id="filebrowser-loading" style="text-align:center;padding:60px;display:none;">
                  <div class="spinner"></div>
                  <div style="margin-top:10px;color:#9ca3af;">Loading documents...</div>
                </div>
                <div class="empty-state" id="filebrowser-empty">
                  <div class="empty-state-icon"><i class="fas fa-folder-open"></i></div>
                  <div class="empty-state-text">No documents found in this project.</div>
                </div>
                <div id="filebrowser-list"></div>
                <div id="filebrowser-pagination" style="display:none;"></div>
              </div>
            </div>
            <!-- File Viewer (hidden by default) -->
            <div id="filebrowser-viewer" style="height:100%;display:none;flex-direction:column;">
              <div class="viewer-header">
                <div class="viewer-title-container">
                  <button id="viewer-back" class="viewer-back"><i class="fas fa-arrow-left"></i></button>
                  <h3 id="viewer-title"></h3>
                </div>
                <div id="viewer-actions" class="viewer-actions"></div>
              </div>
              <div class="viewer-content" style="flex:1;overflow-y:auto;">
                <div id="viewer-markdown" class="prd-content markdown-content" style="padding:20px;color:#e2e8f0;"></div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>

  <!-- JS (same files as Django, just /public/ paths) -->
  <script>
    // Inject server-side data for chat.js
    const initialConversationId = ${conversationId ? `"${conversationId}"` : "null"};
    const CURRENT_USER_ID = "${user.id}";
    // Override WS path — Bun uses /ws/chat (no trailing slash needed)
    window.__WS_PATH__ = '/ws/chat';
  </script>
  <script src="/public/js/marked.min.js"></script>
  <script src="/public/js/markdown-config.js"></script>
  <script src="/public/js/artifacts-loader.js"></script>
  <script src="/public/js/artifacts.js"></script>
  <script src="/public/js/sidebar.js"></script>
  <script src="/public/js/chat.js"></script>
  <script src="/public/js/mobile-menu.js"></script>

  <script>
    // Model selector: wire up submenu clicks → POST /api/settings/model
    document.querySelectorAll('#model-submenu .submenu-option').forEach(btn => {
      btn.addEventListener('click', async () => {
        const key = btn.dataset.value;
        await fetch('/api/settings/model', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ modelKey: key }),
          credentials: 'include',
        });
        document.querySelectorAll('#model-submenu .submenu-option').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        document.getElementById('current-model-left').textContent = btn.querySelector('span').textContent.trim();
      });
    });

    // Set initial model label
    const selectedModelBtn = document.querySelector('#model-submenu .submenu-option.selected');
    if (selectedModelBtn) {
      document.getElementById('current-model-left').textContent = selectedModelBtn.querySelector('span').textContent.trim();
    }

    // Artifacts panel toggle is handled by artifacts.js (uses #artifacts-toggle and #resize-handle)
    requestAnimationFrame(()=>requestAnimationFrame(()=>document.documentElement.classList.remove('sidebar-minimized-preload')));
  </script>
</body>
</html>`;
}
