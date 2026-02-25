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
  claudeCode?: {
    authenticated: boolean;
    hasCredentials: boolean;
    cliApiKey: string | null;
  };
  github?: {
    connected: boolean;
    username: string | null;
    avatarUrl: string | null;
  };
  activeSection?: "llm-keys" | "integrations";
  error?: string;
  success?: string;
}

export function SettingsPage({ user, apiKeys, claudeCode, github, activeSection = "llm-keys", error, success }: SettingsPageProps) {
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
          <a href="/settings" class="settings-nav-item ${activeSection === "llm-keys" ? "active" : ""}">
            <i class="fas fa-key"></i> LLM Keys
          </a>
          <a href="/settings/integrations" class="settings-nav-item ${activeSection === "integrations" ? "active" : ""}">
            <i class="fas fa-plug"></i> Integrations
          </a>
        </nav>
      </div>

      <!-- Content -->
      <div class="settings-content">

      ${activeSection === "integrations" ? html`

        <!-- Claude Code Card -->
        <div class="llm-keys-table" style="margin-bottom:1.5rem;">
          <div class="llm-keys-row" style="border-bottom:1px solid rgba(255,255,255,0.07);padding:1rem 1.375rem;justify-content:space-between;">
            <h3 style="margin:0;font-size:0.9375rem;font-weight:700;color:var(--text-color,#f0f0f0);display:flex;align-items:center;gap:.5rem;">
              <img src="/public/images/anthropic-logo.png" style="width:18px;height:18px;object-fit:contain;" />
              Claude Code CLI
            </h3>
            ${claudeCode?.hasCredentials && claudeCode?.authenticated ? html`
              <span style="font-size:.75rem;padding:.25rem .625rem;background:rgba(52,211,153,.1);color:#34d399;border:1px solid rgba(52,211,153,.25);border-radius:20px;">
                <i class="fas fa-check-circle" style="margin-right:.25rem;"></i>Connected
              </span>
            ` : claudeCode?.hasCredentials && !claudeCode?.authenticated ? html`
              <span style="font-size:.75rem;padding:.25rem .625rem;background:rgba(239,68,68,.1);color:#f87171;border:1px solid rgba(239,68,68,.25);border-radius:20px;">
                <i class="fas fa-exclamation-triangle" style="margin-right:.25rem;"></i>Disconnected
              </span>
            ` : html`
              <span style="font-size:.75rem;padding:.25rem .625rem;background:rgba(255,255,255,.06);color:rgba(255,255,255,.4);border:1px solid rgba(255,255,255,.1);border-radius:20px;">
                Not connected
              </span>
            `}
          </div>

          <!-- Status + connect/disconnect -->
          <div class="llm-keys-row" style="flex-direction:column;align-items:stretch;gap:1rem;">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;">
              <div>
                <div class="byok-label">Authentication</div>
                <div class="byok-desc">
                  ${claudeCode?.hasCredentials && claudeCode?.authenticated
                    ? "Your Claude credentials are stored. Ticket execution is enabled."
                    : claudeCode?.hasCredentials && !claudeCode?.authenticated
                    ? "Claude CLI session expired or disconnected. Please reconnect to resume ticket execution."
                    : "Connect your Claude account to enable AI-powered ticket execution."}
                </div>
              </div>
              <div style="display:flex;gap:.5rem;flex-shrink:0;">
                ${claudeCode?.hasCredentials && claudeCode?.authenticated ? html`
                  <button id="cc-disconnect-btn" onclick="claudeCodeDisconnect()"
                    class="llm-btn-remove" style="border-radius:7px;border:1px solid rgba(239,68,68,0.3);padding:.45rem .875rem;">
                    <i class="fas fa-unlink"></i>&nbsp; Disconnect
                  </button>
                ` : claudeCode?.hasCredentials && !claudeCode?.authenticated ? html`
                  <button id="cc-connect-btn" onclick="claudeCodeStartAuth()"
                    class="llm-btn-save" style="border-radius:7px;padding:.45rem .875rem;">
                    <i class="fas fa-plug"></i>&nbsp; Reconnect Claude Code
                  </button>
                  <button id="cc-disconnect-btn" onclick="claudeCodeDisconnect()"
                    class="llm-btn-remove" style="border-radius:7px;border:1px solid rgba(239,68,68,0.3);padding:.45rem .875rem;">
                    <i class="fas fa-unlink"></i>&nbsp; Disconnect
                  </button>
                ` : html`
                  <button id="cc-connect-btn" onclick="claudeCodeStartAuth()"
                    class="llm-btn-save" style="border-radius:7px;padding:.45rem .875rem;">
                    <i class="fas fa-plug"></i>&nbsp; Connect Claude Code
                  </button>
                `}
              </div>
            </div>

            <!-- OAuth Flow Panel (shown dynamically) -->
            <div id="cc-flow-panel" style="display:none;border-top:1px solid rgba(255,255,255,.07);padding-top:1rem;">

              <!-- Step 1: Provisioning -->
              <div id="cc-step-provisioning" style="display:none;">
                <div style="display:flex;align-items:center;gap:.75rem;color:rgba(255,255,255,.6);font-size:.875rem;">
                  <div class="cc-spinner"></div>
                  <span id="cc-provisioning-msg">Creating secure VM and installing Claude CLI…</span>
                </div>
              </div>

              <!-- Step 2: OAuth URL -->
              <div id="cc-step-oauth" style="display:none;">
                <!-- Step 1: open link -->
                <div style="display:flex;gap:.75rem;margin-bottom:1rem;align-items:flex-start;">
                  <div style="flex-shrink:0;width:22px;height:22px;border-radius:50%;background:rgba(139,92,246,.25);border:1px solid rgba(139,92,246,.5);display:flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:700;color:#c4b5fd;margin-top:1px;">1</div>
                  <div style="flex:1;min-width:0;">
                    <p style="font-size:.875rem;color:rgba(255,255,255,.75);margin:0 0 .5rem;">Open this link in your browser and sign in to Claude:</p>
                    <div style="display:flex;gap:.5rem;align-items:center;">
                      <div style="flex:1;min-width:0;display:flex;align-items:center;gap:.625rem;padding:.45rem .75rem;background:rgba(139,92,246,.08);border:1px solid rgba(139,92,246,.25);border-radius:8px;overflow:hidden;">
                        <i class="fas fa-link" style="color:#a78bfa;font-size:.7rem;flex-shrink:0;"></i>
                        <a id="cc-oauth-url" href="#" target="_blank" rel="noopener"
                          style="flex:1;min-width:0;color:#c4b5fd;font-size:.8rem;text-decoration:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block;">
                        </a>
                      </div>
                      <button onclick="copyOAuthUrl()" id="cc-copy-btn"
                        style="flex-shrink:0;padding:.45rem .75rem;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:8px;color:rgba(255,255,255,.6);cursor:pointer;font-size:.8rem;white-space:nowrap;transition:all .15s;">
                        <i class="fas fa-copy"></i> Copy
                      </button>
                    </div>
                  </div>
                </div>

                <!-- Step 2: paste code -->
                <div style="display:flex;gap:.75rem;align-items:flex-start;">
                  <div style="flex-shrink:0;width:22px;height:22px;border-radius:50%;background:rgba(139,92,246,.25);border:1px solid rgba(139,92,246,.5);display:flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:700;color:#c4b5fd;margin-top:1px;">2</div>
                  <div style="flex:1;min-width:0;">
                    <p style="font-size:.875rem;color:rgba(255,255,255,.75);margin:0 0 .5rem;">Paste the authorization code you receive:</p>
                    <div style="display:flex;gap:.5rem;">
                      <input id="cc-code-input" type="text" placeholder="Paste authorization code…"
                        style="flex:1;min-width:0;padding:.45rem .75rem;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.1);border-radius:8px;color:var(--text-color,#f0f0f0);font-size:.875rem;outline:none;"
                        onkeydown="if(event.key==='Enter') claudeCodeSubmitCode()" />
                      <button onclick="claudeCodeSubmitCode()" id="cc-submit-btn"
                        class="llm-btn-save" style="flex-shrink:0;border-radius:8px;padding:.45rem 1rem;white-space:nowrap;">
                        Verify
                      </button>
                    </div>
                    <div id="cc-code-error" style="display:none;margin-top:.4rem;font-size:.8rem;color:#f87171;"></div>
                  </div>
                </div>
              </div>

              <!-- Step 3: Verifying -->
              <div id="cc-step-verifying" style="display:none;">
                <div style="display:flex;align-items:center;gap:.75rem;color:rgba(255,255,255,.6);font-size:.875rem;">
                  <div class="cc-spinner"></div>
                  <span>Verifying and saving credentials…</span>
                </div>
              </div>

              <!-- Step 4: Done -->
              <div id="cc-step-done" style="display:none;">
                <div style="display:flex;align-items:center;gap:.75rem;color:#34d399;font-size:.875rem;">
                  <i class="fas fa-check-circle" style="font-size:1.1rem;"></i>
                  <span>Claude Code connected successfully! Reloading…</span>
                </div>
              </div>

              <!-- Error state -->
              <div id="cc-step-error" style="display:none;">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;">
                  <div style="display:flex;align-items:center;gap:.6rem;color:#f87171;font-size:.875rem;">
                    <i class="fas fa-exclamation-circle"></i>
                    <span id="cc-error-msg">Something went wrong.</span>
                  </div>
                  <button onclick="claudeCodeStartAuth()"
                    style="padding:.4rem .75rem;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:7px;color:rgba(255,255,255,.7);cursor:pointer;font-size:.8125rem;">
                    Try again
                  </button>
                </div>
              </div>
            </div>
          </div>

        </div>

        <style>
          .cc-spinner {
            width: 16px; height: 16px; border-radius: 50%;
            border: 2px solid rgba(255,255,255,.15);
            border-top-color: #a78bfa;
            animation: cc-spin .7s linear infinite;
            flex-shrink: 0;
          }
          @keyframes cc-spin { to { transform: rotate(360deg); } }
        </style>
        <script>
          function ccShowStep(name) {
            ['provisioning','oauth','verifying','done','error'].forEach(s => {
              document.getElementById('cc-step-' + s).style.display = 'none';
            });
            if (name) document.getElementById('cc-step-' + name).style.display = 'block';
            document.getElementById('cc-flow-panel').style.display = name ? 'block' : 'none';
          }

          async function claudeCodeStartAuth() {
            const btn = document.getElementById('cc-connect-btn');
            if (btn) { btn.disabled = true; btn.innerHTML = '<div class="cc-spinner" style="display:inline-block;margin-right:.4rem;"></div> Starting…'; }
            ccShowStep('provisioning');

            try {
              const res = await fetch('/api/v1/claude-auth/start', { method: 'POST' });
              const data = await res.json();

              if (data.status === 'already_authenticated') {
                ccShowStep('done');
                setTimeout(() => location.reload(), 1500);
                return;
              }

              if (data.status === 'pending' && data.oauthUrl) {
                document.getElementById('cc-oauth-url').href = data.oauthUrl;
                document.getElementById('cc-oauth-url').textContent = data.oauthUrl;
                ccShowStep('oauth');
                return;
              }

              ccShowStep('error');
              document.getElementById('cc-error-msg').textContent = data.error || 'Failed to start authentication.';
            } catch (err) {
              ccShowStep('error');
              document.getElementById('cc-error-msg').textContent = 'Network error: ' + err.message;
            } finally {
              if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-plug"></i>&nbsp; Connect Claude Code'; }
            }
          }

          async function claudeCodeSubmitCode() {
            const input = document.getElementById('cc-code-input');
            const code = input.value.trim();
            if (!code) {
              document.getElementById('cc-code-error').textContent = 'Please paste the authorization code.';
              document.getElementById('cc-code-error').style.display = 'block';
              return;
            }
            document.getElementById('cc-code-error').style.display = 'none';
            document.getElementById('cc-submit-btn').disabled = true;
            ccShowStep('verifying');

            try {
              const res = await fetch('/api/v1/claude-auth/submit-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
              });
              const data = await res.json();

              if (data.status === 'success') {
                ccShowStep('done');
                setTimeout(() => location.reload(), 1500);
              } else {
                ccShowStep('oauth');
                document.getElementById('cc-code-error').textContent = data.error || 'Verification failed.';
                document.getElementById('cc-code-error').style.display = 'block';
                document.getElementById('cc-submit-btn').disabled = false;
              }
            } catch (err) {
              ccShowStep('error');
              document.getElementById('cc-error-msg').textContent = 'Network error: ' + err.message;
            }
          }

          async function claudeCodeDisconnect() {
            if (!confirm('Disconnect Claude Code? This will remove your stored credentials.')) return;
            const btn = document.getElementById('cc-disconnect-btn');
            if (btn) { btn.disabled = true; btn.textContent = 'Disconnecting…'; }
            try {
              await fetch('/api/v1/claude-auth/disconnect', { method: 'POST' });
              location.reload();
            } catch {
              if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-unlink"></i>&nbsp; Disconnect'; }
            }
          }

          function copyOAuthUrl() {
            const url = document.getElementById('cc-oauth-url').href;
            navigator.clipboard.writeText(url).then(() => {
              const btn = document.getElementById('cc-copy-btn');
              if (btn) {
                btn.innerHTML = '<i class="fas fa-check"></i> Copied';
                btn.style.color = '#4ade80';
                btn.style.borderColor = 'rgba(74,222,128,.3)';
                setTimeout(() => {
                  btn.innerHTML = '<i class="fas fa-copy"></i> Copy';
                  btn.style.color = '';
                  btn.style.borderColor = '';
                }, 2000);
              }
            }).catch(() => {});
          }
        </script>

        <!-- GitHub Card -->
        <div class="llm-keys-table">
          <div class="llm-keys-row" style="border-bottom:1px solid rgba(255,255,255,0.07);padding:1rem 1.375rem;">
            <h3 style="margin:0;font-size:0.9375rem;font-weight:700;color:var(--text-color,#f0f0f0);">GitHub</h3>
          </div>
          <div class="llm-keys-row">
            <div style="flex:1;display:flex;align-items:center;gap:.875rem;">
              ${github?.avatarUrl ? html`<img src="${github.avatarUrl}" style="width:36px;height:36px;border-radius:50%;" />` : html`<div style="width:36px;height:36px;border-radius:50%;background:rgba(255,255,255,.08);display:flex;align-items:center;justify-content:center;"><i class="fab fa-github" style="font-size:1.25rem;color:rgba(255,255,255,.4);"></i></div>`}
              <div>
                <div class="byok-label" style="margin-bottom:.15rem;">
                  ${github?.connected ? `Connected as @${github.username}` : "Not connected"}
                </div>
                <div class="byok-desc">Used for creating branches and pull requests during ticket execution.</div>
              </div>
            </div>
            <div>
              ${github?.connected ? html`
                <div style="display:flex;align-items:center;gap:.5rem;">
                  <span style="padding:.4rem .875rem;background:rgba(16,185,129,.1);color:#34d399;border:1px solid rgba(16,185,129,.25);border-radius:7px;font-size:.8125rem;">
                    <i class="fas fa-check"></i> Connected
                  </span>
                  <form method="POST" action="/settings/github/disconnect" style="margin:0;">
                    <button type="submit" style="padding:.4rem .75rem;background:rgba(239,68,68,.08);color:#f87171;border:1px solid rgba(239,68,68,.2);border-radius:7px;font-size:.75rem;cursor:pointer;">
                      Disconnect
                    </button>
                  </form>
                </div>
              ` : html`
                <a href="/accounts/github-connect" style="padding:.4rem .875rem;background:rgba(255,255,255,.07);color:rgba(255,255,255,.75);border:1px solid rgba(255,255,255,.12);border-radius:7px;font-size:.8125rem;text-decoration:none;display:inline-flex;align-items:center;gap:.4rem;">
                  <i class="fab fa-github"></i> Connect GitHub
                </a>
              `}
            </div>
          </div>
        </div>

      ` : html`

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

      `}<!-- /activeSection conditional -->
      </div><!-- /settings-content -->
    </div><!-- /settings-wrapper -->
  </div><!-- /settings-main -->
</div>

<script src="/public/js/sidebar.js"></script>
</body>
</html>`;
}
