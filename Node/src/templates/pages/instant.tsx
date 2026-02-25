import { html } from "hono/html";
import { ChatInput } from "../components/chat-input.tsx";

interface InstantAppSummary {
  appId: string;
  name: string;
  status: string;
  previewUrl?: string | null;
  conversationId?: string | null;
}

interface InstantPageProps {
  user: { id: string; name: string; email: string };
  standaloneMode: boolean;
  projectId?: string;
  projectName?: string;
  modelKey: string;
  roleKey: string;
  models: Array<{ key: string; providerLabel: string; requiresPro: boolean }>;
  currentApp?: InstantAppSummary | null;
  instantApps?: InstantAppSummary[];
}

function appStatusBadge(status: string) {
  if (!status) return "gathering";
  return status;
}

export function InstantPage({
  user,
  standaloneMode,
  projectId,
  projectName,
  modelKey,
  roleKey,
  models,
  currentApp = null,
  instantApps = [],
}: InstantPageProps) {
  const avatarLetter = (user.name?.[0] ?? user.email?.[0] ?? "?").toUpperCase();
  const canShowProjectNav = !standaloneMode && !!projectId;

  return html`<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Instant Mode${projectName ? ` - ${projectName}` : ""} - LFG</title>
  <script>(function(){if(localStorage.getItem('sidebarMinimized')==='true'){document.documentElement.classList.add('sidebar-minimized-preload');}})()</script>
  <link rel="stylesheet" href="/public/css/theme-variables.css" />
  <link rel="stylesheet" href="/public/css/common.css" />
  <link rel="stylesheet" href="/public/css/sidebar.css" />
  <link rel="stylesheet" href="/public/css/styles.css" />
  <link rel="stylesheet" href="/public/css/chat.css" />
  <link rel="stylesheet" href="/public/css/instant.css" />
  <link rel="stylesheet" href="/public/css/light/light-mode.css" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
  <script src="/public/js/theme-switcher.js"></script>
</head>
<body data-theme="dark" data-model-key="${modelKey}" data-role-key="${roleKey}">
  <div class="app-container">
    <div class="sidebar" id="sidebar"${projectId ? ` data-current-project-id="${projectId}"` : ""}>
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
              <span class="project-name-text">${projectName ?? "Instant Mode"}</span>
              <i class="fas fa-chevron-down dropdown-arrow"></i>
            </button>
            <div class="nav-dropdown" id="projectDropdown">
              <a href="/projects" class="nav-dropdown-item">
                <i class="fas fa-th-large"></i>
                <span>All Projects</span>
              </a>
              ${canShowProjectNav
                ? html`
                    <a href="/chat/project/${projectId}" class="nav-dropdown-item">
                      <i class="fas fa-comments"></i>
                      <span>Open Chat</span>
                    </a>
                  `
                : ""}
            </div>
          </div>
        </div>

        <div class="new-chat-section">
          <a
            href="${standaloneMode ? "/instant/" : `/instant/project/${projectId}`}"
            id="new-chat-btn"
            class="new-chat-link"
          >
            <i class="fas fa-bolt"></i>
            <span class="button-text">New app</span>
          </a>
        </div>

        <div class="sidebar-nav">
          ${canShowProjectNav
            ? html`
                <a href="/chat/project/${projectId}" class="nav-link">
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
              `
            : ""}
          <a href="${standaloneMode ? "/instant/" : `/instant/project/${projectId}`}" class="nav-link active">
            <i class="fas fa-bolt"></i>
            <span class="nav-text">Instant</span>
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

    <main class="instant-main">
      <div class="instant-chat-panel">
        <div class="instant-chat-header">
          <div class="instant-chat-header-left">
            ${currentApp
              ? html`
                  <span class="instant-app-name" title="${currentApp.name}">${currentApp.name}</span>
                  <span class="instant-app-status-badge ${appStatusBadge(currentApp.status)}">${currentApp.status}</span>
                `
              : html`<span class="instant-app-name">New App</span>`}
          </div>

          ${instantApps.length > 0
            ? html`
                <div class="instant-chat-header-right">
                  <div class="instant-app-switcher-dropdown">
                    <button class="instant-switcher-btn" id="app-switcher-btn" title="Switch app">
                      <i class="fas fa-exchange-alt"></i>
                    </button>
                    <div class="instant-switcher-menu" id="app-switcher-menu">
                      <a
                        href="${standaloneMode ? "/instant/" : `/instant/project/${projectId}/`}"
                        class="instant-switcher-item${currentApp ? "" : " active"}"
                      >
                        <i class="fas fa-plus" style="font-size:0.7rem;opacity:0.5;"></i>
                        <span>New App</span>
                      </a>
                      ${instantApps.map(
                        (app) => html`
                          <a
                            href="${standaloneMode
                              ? `/instant/app/${app.appId}/`
                              : `/instant/project/${projectId}/app/${app.appId}/`}"
                            class="instant-switcher-item${currentApp?.appId === app.appId ? " active" : ""}"
                          >
                            <span class="switcher-item-name">${app.name}</span>
                            <span class="switcher-item-status ${app.status}">${app.status}</span>
                          </a>
                        `
                      )}
                    </div>
                  </div>
                </div>
              `
            : ""}
        </div>

        <div class="chat-messages" id="chat-messages">
          <div class="message-container" id="message-container">
            ${currentApp && currentApp.status !== "gathering"
              ? ""
              : html`
                  <div class="welcome-message">
                    <h2>Instant Mode <i class="fas fa-bolt" style="color:#f59e0b;"></i></h2>
                    <p>Describe your app and I'll build it for you.</p>
                  </div>
                `}
          </div>
        </div>

        ${ChatInput({
          placeholder: "Describe your app...",
          models,
          selectedModelKey: modelKey,
          selectedRoleKey: roleKey,
          roleOptions: [{ key: "product_analyst", label: "Analyst" }],
          showTurboToggle: false,
          showMic: true,
        })}
      </div>

      <div class="instant-divider" id="instant-divider"></div>

      <div class="instant-preview-panel">
        <div class="instant-preview-header">
          <div class="instant-preview-controls">
            <div class="preview-tab-toggle">
              <button class="preview-tab-btn active" data-tab="preview" title="Preview">
                <i class="fas fa-eye"></i> Preview
              </button>
              <button class="preview-tab-btn" data-tab="logs" title="Logs">
                <i class="fas fa-terminal"></i> Logs
              </button>
              <button class="preview-tab-btn" data-tab="env" title="Environment Variables">
                <i class="fas fa-key"></i> Env
              </button>
            </div>
            <div class="viewport-toggle" id="viewport-toggle">
              <button class="viewport-btn active" data-viewport="desktop" title="Desktop"><i class="fas fa-desktop"></i></button>
              <button class="viewport-btn" data-viewport="tablet" title="Tablet"><i class="fas fa-tablet-alt"></i></button>
              <button class="viewport-btn" data-viewport="mobile" title="Mobile"><i class="fas fa-mobile-alt"></i></button>
            </div>
            <div class="preview-url-bar" id="preview-url-bar" style="display:none;">
              <i class="fas fa-globe"></i>
              <span id="preview-url-text"></span>
              <a href="#" id="preview-open-btn" target="_blank" title="Open in new tab"><i class="fas fa-external-link-alt"></i></a>
            </div>
            <button id="preview-refresh-btn" class="preview-action-btn" title="Rebuild & Refresh" style="display:none">
              <i class="fas fa-sync-alt"></i>
            </button>
          </div>
          <div class="preview-status" id="preview-status">
            <span class="status-dot" id="status-dot"></span>
            <span class="status-text" id="status-text">Waiting</span>
          </div>
        </div>

        <div class="instant-preview-content" id="preview-content">
          <div class="instant-preview-placeholder" id="preview-placeholder">
            <div class="placeholder-icon"><i class="fas fa-rocket"></i></div>
            <h3>Your app will appear here</h3>
            <p>Describe what you want to build in the chat, and a live preview will load once it's ready.</p>
          </div>

          <div class="instant-preview-building" id="preview-building" style="display:none;">
            <canvas id="snake-game" width="320" height="320"></canvas>
            <p id="building-message" class="building-command-text">Provisioning sandbox...</p>
          </div>

          <iframe
            id="preview-iframe"
            class="instant-preview-iframe"
            style="display:none;"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
          ></iframe>
        </div>

        <div class="instant-logs-content" id="logs-content" style="display:none;">
          <div class="logs-toolbar">
            <button class="logs-btn" id="logs-refresh-btn" title="Refresh logs"><i class="fas fa-sync-alt"></i></button>
            <button class="logs-btn" id="logs-clear-btn" title="Clear display"><i class="fas fa-eraser"></i></button>
            <label class="logs-auto-scroll">
              <input type="checkbox" id="logs-autoscroll" checked /> Auto-scroll
            </label>
          </div>
          <pre class="logs-output" id="logs-output"><span class="logs-placeholder">Logs will appear here once the app is running...</span></pre>
        </div>

        <div class="instant-env-content" id="env-content" style="display:none;">
          <div class="env-toolbar">
            <button class="env-add-btn" id="env-add-btn" title="Add variable">
              <i class="fas fa-plus"></i> Add Variable
            </button>
            <button class="env-save-btn" id="env-save-btn" title="Save changes">
              <i class="fas fa-save"></i> Save
            </button>
          </div>
          <div class="env-table" id="env-table">
            <div class="env-empty-state" id="env-empty-state">
              <i class="fas fa-key" style="font-size:1.5rem;opacity:0.3;margin-bottom:0.5rem;"></i>
              <p>No environment variables set.</p>
              <p style="font-size:0.75rem;opacity:0.5;">Click "Add Variable" to add one.</p>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>

  <script>
    window.INSTANT_CONFIG = {
      projectId: ${projectId ? `"${projectId}"` : "''"},
      projectDbId: null,
      standaloneMode: ${standaloneMode ? "true" : "false"},
      currentAppId: ${currentApp ? `"${currentApp.appId}"` : "''"},
      currentAppStatus: ${currentApp ? `"${currentApp.status}"` : "'gathering'"},
      previewUrl: ${currentApp?.previewUrl ? `"${currentApp.previewUrl}"` : "''"},
      conversationId: ${currentApp?.conversationId ? `"${currentApp.conversationId}"` : "null"},
    };
    window.__WS_PATH__ = '/ws/chat';
  </script>
  <script src="/public/js/sidebar.js"></script>
  <script src="/public/js/marked.min.js"></script>
  <script src="/public/js/markdown-config.js"></script>
  <script src="/public/js/custom-dropdown.js"></script>
  <script src="/public/js/instant.js"></script>
  <script>requestAnimationFrame(()=>requestAnimationFrame(()=>document.documentElement.classList.remove('sidebar-minimized-preload')));</script>
</body>
</html>`;
}
