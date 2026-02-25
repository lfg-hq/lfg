import { html } from "hono/html";

export interface ChatInputModelOption {
  key: string;
  providerLabel: string;
  requiresPro?: boolean;
  label?: string;
}

export interface ChatInputRoleOption {
  key: string;
  label: string;
}

interface ChatInputProps {
  placeholder: string;
  models: ChatInputModelOption[];
  selectedModelKey: string;
  selectedRoleKey?: string;
  roleOptions?: ChatInputRoleOption[];
  showTurboToggle?: boolean;
  turboEnabled?: boolean;
  showMic?: boolean;
}

function groupModels(models: ChatInputModelOption[]) {
  const grouped: Record<string, ChatInputModelOption[]> = {};
  for (const model of models) {
    if (!grouped[model.providerLabel]) grouped[model.providerLabel] = [];
    grouped[model.providerLabel]!.push(model);
  }
  return grouped;
}

export function ChatInput({
  placeholder,
  models,
  selectedModelKey,
  selectedRoleKey = "product_analyst",
  roleOptions = [
    { key: "product_analyst", label: "Analyst" },
    { key: "developer", label: "Developer" },
    { key: "designer", label: "Designer" },
  ],
  showTurboToggle = true,
  turboEnabled = false,
  showMic = true,
}: ChatInputProps) {
  const groupedModels = groupModels(models);
  const selectedRole =
    roleOptions.find((role) => role.key === selectedRoleKey)?.label ?? "Analyst";
  const selectedModel =
    models.find((model) => model.key === selectedModelKey)?.label ?? selectedModelKey;

  return html`
    <div class="chat-input-container">
      <form id="chat-form">
        <div class="input-wrapper">
          <div class="left-actions">
            <button type="button" id="file-upload-btn" class="action-btn" title="Upload file">
              <i class="fas fa-paperclip"></i>
            </button>
            <input
              type="file"
              id="file-upload-input"
              style="display:none"
              multiple
              accept="image/*,.pdf,.csv,.txt,.md,.docx,.xlsx,.mp3,.mp4,.m4a,.wav,.webm,.json,.js,.ts,.py,.html,.css"
            />

            <button type="button" id="settings-btn" class="action-btn settings-btn-styled" title="Settings">
              <i class="fas fa-sliders-h"></i>
            </button>

            <span class="status-indicators">
              <span class="status-item role-status" id="role-status-btn">
                <span id="current-role-left">${selectedRole}</span>
              </span>
              <span class="status-divider">•</span>
              <span class="status-item model-status" id="model-status-btn">
                <span id="current-model-left">${selectedModel}</span>
              </span>
            </span>

            <div class="settings-dropdown" id="settings-dropdown">
              <div class="settings-menu">
                <div class="menu-item" data-submenu="role">
                  <i class="fas fa-user-tie"></i><span>Role</span>
                  <i class="fas fa-chevron-right submenu-arrow"></i>
                  <div class="submenu" id="role-submenu">
                    ${roleOptions.map(
                      (role) => html`
                        <button
                          type="button"
                          class="submenu-option${role.key === selectedRoleKey ? " selected" : ""}"
                          data-value="${role.key}"
                        >
                          <span>${role.label}</span><i class="fas fa-check"></i>
                        </button>
                      `
                    )}
                  </div>
                </div>

                <div class="menu-item" data-submenu="model">
                  <i class="fas fa-robot"></i><span>Model</span>
                  <i class="fas fa-chevron-right submenu-arrow"></i>
                  <div class="submenu" id="model-submenu">
                    ${Object.entries(groupedModels).map(
                      ([providerLabel, providerModels]) => html`
                        <div class="submenu-group">${providerLabel}</div>
                        ${providerModels.map(
                          (model) => html`
                            <button
                              type="button"
                              class="submenu-option${model.key === selectedModelKey ? " selected" : ""}"
                              data-value="${model.key}"
                            >
                              <span>${model.label ?? model.key}</span>
                              <i class="fas fa-check"></i>
                            </button>
                          `
                        )}
                      `
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div id="chat-input-box">
            <textarea id="chat-input" placeholder="${placeholder}" rows="2" autofocus></textarea>
          </div>

          <div class="input-actions">
            ${showTurboToggle
              ? html`
                  <div class="turbo-switch-container" title="Turbo mode">
                    <label class="turbo-switch">
                      <input type="checkbox" id="turbo-mode-toggle"${turboEnabled ? " checked" : ""} />
                      <span class="turbo-slider"></span>
                    </label>
                    <span class="turbo-label">Turbo</span>
                  </div>
                `
              : ""}
            ${showMic
              ? html`
                  <button type="button" id="record-audio-btn" class="action-btn" title="Record audio">
                    <i class="fas fa-microphone"></i>
                  </button>
                `
              : ""}
            <button type="submit" id="send-btn" class="action-btn" title="Send">
              <i class="fas fa-paper-plane"></i>
            </button>
          </div>
        </div>
      </form>
    </div>
  `;
}
