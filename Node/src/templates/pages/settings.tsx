import { html } from "hono/html";

interface SettingsPageProps {
  user: { id: string; name: string; email: string };
  apiKeys: {
    openai: boolean;
    anthropic: boolean;
    google: boolean;
    xai: boolean;
    usePersonalKeys: boolean;
  };
  error?: string;
  success?: string;
}

export function SettingsPage({ user, apiKeys, error, success }: SettingsPageProps) {
  const avatarLetter = (user.name?.[0] ?? user.email?.[0] ?? "?").toUpperCase();

  return html`<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Settings — LFG</title>
  <link rel="stylesheet" href="/public/css/theme-variables.css" />
  <link rel="stylesheet" href="/public/css/common.css" />
  <link rel="stylesheet" href="/public/css/sidebar.css" />
  <link rel="stylesheet" href="/public/css/polish.css" />
  <link rel="stylesheet" href="/public/css/light/light-mode.css" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
  <script src="/public/js/theme-switcher.js"></script>
  <style>
    /* ── Layout ─────────────────────────────────────────────── */
    .settings-main {
      margin-left: 260px;
      min-height: 100vh;
      background: var(--body-bg, #0d0d0d);
      transition: margin-left 0.2s ease;
    }
    .app-container.sidebar-minimized .settings-main { margin-left: 60px; }

    .settings-page-header {
      padding: 2rem 2.5rem 1.5rem;
      border-bottom: 1px solid rgba(255,255,255,0.07);
    }
    .settings-page-title {
      font-size: 1.75rem;
      font-weight: 700;
      color: var(--text-color, #f0f0f0);
      margin: 0;
      display: flex;
      align-items: center;
      gap: 0.625rem;
    }

    .settings-wrapper {
      display: flex;
      gap: 2rem;
      padding: 2rem 2.5rem;
    }

    /* ── Secondary nav ───────────────────────────────────────── */
    .settings-sidebar { width: 220px; flex-shrink: 0; }
    .settings-nav {
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.07);
      border-radius: 10px;
      padding: 0.5rem;
    }
    .settings-nav-item {
      display: flex;
      align-items: center;
      gap: 0.625rem;
      padding: 0.6rem 0.875rem;
      border-radius: 7px;
      color: rgba(255,255,255,0.5);
      text-decoration: none;
      font-size: 0.875rem;
      font-weight: 500;
      transition: all 0.15s;
    }
    .settings-nav-item:hover { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.85); }
    .settings-nav-item.active {
      background: rgba(139,92,246,0.15);
      color: #c4b5fd;
    }
    .settings-nav-item.disabled { opacity: 0.35; pointer-events: none; }
    .settings-nav-item i { width: 15px; text-align: center; font-size: 0.8125rem; }

    /* ── Content area ────────────────────────────────────────── */
    .settings-content { flex: 1; min-width: 0; }

    /* ── BYOK label/desc (used inside the unified card row) ─── */
    .byok-label {
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--text-color, #f0f0f0);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 0.3rem;
    }
    .byok-desc { font-size: 0.8125rem; color: rgba(255,255,255,0.45); line-height: 1.5; }

    /* ── Toggle ──────────────────────────────────────────────── */
    .toggle-switch {
      position: relative;
      display: inline-block;
      width: 52px;
      height: 28px;
      flex-shrink: 0;
    }
    .toggle-switch input { opacity: 0; width: 0; height: 0; position: absolute; }
    .toggle-slider {
      position: absolute; cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 28px;
      transition: 0.3s;
    }
    .toggle-slider:before {
      content: "";
      position: absolute;
      width: 20px; height: 20px;
      left: 3px; bottom: 3px;
      background: rgba(255,255,255,0.6);
      border-radius: 50%;
      transition: 0.3s;
    }
    .toggle-switch input:checked + .toggle-slider {
      background: linear-gradient(135deg, #8B5CF6, #A855F7);
      border-color: #A855F7;
    }
    .toggle-switch input:checked + .toggle-slider:before {
      transform: translateX(24px);
      background: white;
    }

    /* ── LLM keys table — ONE card ───────────────────────────── */
    .llm-keys-table {
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.09);
      border-radius: 10px;
      overflow: hidden;
    }
    .llm-keys-row {
      display: flex;
      align-items: center;
      gap: 1.5rem;
      padding: 1.125rem 1.375rem;
      border-bottom: 1px solid rgba(255,255,255,0.07);
    }
    .llm-keys-row:last-child { border-bottom: none; }

    /* Left: logo + info */
    .llm-row-label {
      display: flex;
      align-items: center;
      gap: 0.875rem;
      width: 220px;
      flex-shrink: 0;
    }
    .llm-logo-wrap {
      width: 38px; height: 38px;
      border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
    }
    .llm-logo-wrap.openai  { background: rgba(16,163,127,0.12); color: #10a37f; }
    .llm-logo-wrap.anthropic { background: rgba(217,119,6,0.12); color: #d97706; }
    .llm-logo-wrap.gemini  { background: rgba(66,133,244,0.12); color: #4285f4; }
    .llm-logo-wrap svg, .llm-logo-wrap img { width: 22px; height: 22px; display: block; }

    .llm-row-name {
      font-size: 0.9375rem;
      font-weight: 600;
      color: var(--text-color, #f0f0f0);
      margin-bottom: 0.15rem;
      display: flex; align-items: center; gap: 6px;
    }
    .llm-row-sub { font-size: 0.75rem; color: rgba(255,255,255,0.38); }

    .help-circle {
      display: inline-flex; align-items: center; justify-content: center;
      width: 17px; height: 17px; border-radius: 50%;
      border: 1px solid rgba(148,163,184,0.4);
      color: rgba(203,213,245,0.7); font-size: 10px;
      text-decoration: none; transition: all 0.2s; line-height: 1;
    }
    .help-circle:hover { border-color: rgba(167,139,250,0.7); color: #f0f0f0; }

    /* Right: input group */
    .llm-row-right {
      flex: 1;
      display: flex;
      justify-content: flex-end;
    }
    .llm-input-group {
      display: flex;
      align-items: center;
      width: 100%;
      max-width: 420px;
      margin: 0;
    }
    .llm-input-group input {
      flex: 1;
      padding: 0.5625rem 0.875rem;
      background: rgba(0,0,0,0.35);
      border: 1px solid rgba(255,255,255,0.1);
      border-right: none;
      border-radius: 7px 0 0 7px;
      color: var(--text-color, #f0f0f0);
      font-size: 0.875rem;
      outline: none;
      transition: border-color 0.15s;
    }
    .llm-input-group input::placeholder { color: rgba(255,255,255,0.25); }
    .llm-input-group input:focus { border-color: rgba(139,92,246,0.6); }
    .llm-input-group input:disabled { opacity: 0.6; cursor: default; font-family: monospace; letter-spacing: 0.1em; }
    .llm-btn-save {
      padding: 0.5625rem 0.875rem;
      background: linear-gradient(135deg, #8B5CF6, #A855F7);
      color: white; border: none;
      border-radius: 0 7px 7px 0;
      cursor: pointer; font-size: 0.875rem; font-weight: 500;
      transition: opacity 0.15s; white-space: nowrap;
      display: flex; align-items: center; gap: 5px;
    }
    .llm-btn-save:hover { opacity: 0.88; }
    .llm-btn-remove {
      padding: 0.5625rem 0.75rem;
      background: rgba(239,68,68,0.12);
      color: #f87171;
      border: 1px solid rgba(239,68,68,0.25);
      border-left: none;
      border-radius: 0 7px 7px 0;
      cursor: pointer; font-size: 0.875rem;
      transition: background 0.15s;
      display: flex; align-items: center;
    }
    .llm-btn-remove:hover { background: rgba(239,68,68,0.2); }
  </style>
</head>
<body data-user-id="${user.id}" data-user-name="${user.name}">
<div class="app-container">

  <!-- Sidebar -->
  <div class="sidebar" id="sidebar">
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
        <a href="/projects" class="project-dropdown-trigger">
          <i class="fas fa-folder"></i>
          <span class="project-name-text">Projects</span>
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

  <!-- Main -->
  <div class="settings-main">
    <div class="settings-page-header">
      ${error ? html`<div style="margin-bottom:.875rem;padding:.7rem 1rem;background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.25);border-radius:8px;color:#f87171;font-size:.875rem;">${error}</div>` : ""}
      ${success ? html`<div style="margin-bottom:.875rem;padding:.7rem 1rem;background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.25);border-radius:8px;color:#4ade80;font-size:.875rem;">${success}</div>` : ""}
      <h1 class="settings-page-title"><i class="fas fa-cog"></i> Settings</h1>
    </div>

    <div class="settings-wrapper">

      <!-- Secondary nav -->
      <div class="settings-sidebar">
        <nav class="settings-nav">
          <a href="/settings" class="settings-nav-item active">
            <i class="fas fa-key"></i> LLM Keys
          </a>
          <a href="/settings/profile" class="settings-nav-item disabled">
            <i class="fas fa-user"></i> Profile
          </a>
        </nav>
      </div>

      <!-- Content -->
      <div class="settings-content">

        <!-- One large card containing heading + BYOK + all providers -->
        <div class="llm-keys-table">

          <!-- Card heading row -->
          <div class="llm-keys-row" style="border-bottom:1px solid rgba(255,255,255,0.07);padding:1rem 1.375rem;">
            <h3 style="margin:0;font-size:0.9375rem;font-weight:700;color:var(--text-color,#f0f0f0);letter-spacing:0.01em;">AI Model API Keys</h3>
          </div>

          <!-- BYOK row -->
          <div class="llm-keys-row" style="background:rgba(255,255,255,0.02);">
            <div style="flex:1;">
              <div class="byok-label">Bring Your Own Keys</div>
              <div class="byok-desc">Your OpenAI, Anthropic, and Google keys will be used where available.</div>
            </div>
            <form method="POST" action="/settings/toggle-byok">
              <label class="toggle-switch">
                <input type="checkbox" name="enabled" ${apiKeys.usePersonalKeys ? "checked" : ""} onchange="this.form.submit()">
                <span class="toggle-slider"></span>
              </label>
            </form>
          </div>

          <!-- OpenAI -->
          <div class="llm-keys-row">
            <div class="llm-row-label">
              <div class="llm-logo-wrap openai">
                <svg fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142-.0852 4.783-2.7582a.7712.7712 0 0 0 .7806 0l5.8428 3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142.0852-4.7735 2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0593a4.4708 4.4708 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997L9.4041 13.5V10.4976z"/></svg>
              </div>
              <div>
                <div class="llm-row-name">OpenAI <a href="https://platform.openai.com/api-keys" target="_blank" class="help-circle">?</a></div>
                <div class="llm-row-sub">Bring your OpenAI API key</div>
              </div>
            </div>
            <div class="llm-row-right">
              ${apiKeys.openai ? html`
                <form method="POST" action="/settings/remove-key" class="llm-input-group">
                  <input type="hidden" name="provider" value="openai" />
                  <input type="password" value="••••••••••••" disabled />
                  <button type="submit" class="llm-btn-remove"><i class="fas fa-times"></i></button>
                </form>
              ` : html`
                <form method="POST" action="/settings/save-key" class="llm-input-group">
                  <input type="hidden" name="provider" value="openai" />
                  <input type="password" name="key" placeholder="sk-..." autocomplete="off" />
                  <button type="submit" class="llm-btn-save">Save</button>
                </form>
              `}
            </div>
          </div>

          <!-- Anthropic -->
          <div class="llm-keys-row">
            <div class="llm-row-label">
              <div class="llm-logo-wrap anthropic">
                <img src="/public/images/anthropic-logo.png" alt="Anthropic" />
              </div>
              <div>
                <div class="llm-row-name">Anthropic <a href="https://console.anthropic.com/settings/keys" target="_blank" class="help-circle">?</a></div>
                <div class="llm-row-sub">Bring your Claude API key</div>
              </div>
            </div>
            <div class="llm-row-right">
              ${apiKeys.anthropic ? html`
                <form method="POST" action="/settings/remove-key" class="llm-input-group">
                  <input type="hidden" name="provider" value="anthropic" />
                  <input type="password" value="••••••••••••" disabled />
                  <button type="submit" class="llm-btn-remove"><i class="fas fa-times"></i></button>
                </form>
              ` : html`
                <form method="POST" action="/settings/save-key" class="llm-input-group">
                  <input type="hidden" name="provider" value="anthropic" />
                  <input type="password" name="key" placeholder="sk-ant-..." autocomplete="off" />
                  <button type="submit" class="llm-btn-save">Save</button>
                </form>
              `}
            </div>
          </div>

          <!-- Google Gemini -->
          <div class="llm-keys-row">
            <div class="llm-row-label">
              <div class="llm-logo-wrap gemini">
                <img src="/public/images/gemini-logo.png" alt="Google Gemini" />
              </div>
              <div>
                <div class="llm-row-name">Google Gemini <a href="https://makersuite.google.com/app/apikey" target="_blank" class="help-circle">?</a></div>
                <div class="llm-row-sub">Bring your Gemini API key</div>
              </div>
            </div>
            <div class="llm-row-right">
              ${apiKeys.google ? html`
                <form method="POST" action="/settings/remove-key" class="llm-input-group">
                  <input type="hidden" name="provider" value="google" />
                  <input type="password" value="••••••••••••" disabled />
                  <button type="submit" class="llm-btn-remove"><i class="fas fa-times"></i></button>
                </form>
              ` : html`
                <form method="POST" action="/settings/save-key" class="llm-input-group">
                  <input type="hidden" name="provider" value="google" />
                  <input type="password" name="key" placeholder="AIza..." autocomplete="off" />
                  <button type="submit" class="llm-btn-save">Save</button>
                </form>
              `}
            </div>
          </div>

        </div><!-- /llm-keys-table -->
      </div><!-- /settings-content -->
    </div><!-- /settings-wrapper -->
  </div><!-- /settings-main -->
</div>

<script src="/public/js/sidebar.js"></script>
</body>
</html>`;
}
