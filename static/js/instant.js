/**
 * Instant Mode — chat + live preview
 * Reuses the same message UI patterns as the main chat (chat.js).
 */
document.addEventListener('DOMContentLoaded', () => {
    const config = window.INSTANT_CONFIG || {};
    const projectId = config.projectId;
    const projectDbId = config.projectDbId;
    const standaloneMode = config.standaloneMode || false;

    const messageContainer = document.getElementById('message-container');
    const chatMessages = document.getElementById('chat-messages');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const previewIframe = document.getElementById('preview-iframe');
    const previewPlaceholder = document.getElementById('preview-placeholder');
    const previewBuilding = document.getElementById('preview-building');
    const buildingMessage = document.getElementById('building-message');
    const previewUrlBar = document.getElementById('preview-url-bar');
    const previewUrlText = document.getElementById('preview-url-text');
    const previewOpenBtn = document.getElementById('preview-open-btn');
    const previewRefreshBtn = document.getElementById('preview-refresh-btn');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    let socket = null;
    let conversationId = config.conversationId;
    let isStreaming = false;
    let currentAssistantEl = null;
    let currentRawContent = '';
    let historyLoaded = false;

    // ---- WebSocket ----

    function connectWebSocket() {
        if (socket && socket.readyState === WebSocket.OPEN) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        let wsUrl = `${protocol}//${window.location.host}/ws/chat/`;
        const params = [];
        if (conversationId) params.push(`conversation_id=${conversationId}`);
        if (projectId) params.push(`project_id=${projectId}`);
        if (params.length) wsUrl += '?' + params.join('&');

        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            console.log('[Instant] WS connected');
        };

        socket.onmessage = (e) => {
            const data = JSON.parse(e.data);
            handleMessage(data);
        };

        socket.onclose = () => {
            console.log('[Instant] WS closed, reconnecting in 3s...');
            setTimeout(connectWebSocket, 3000);
        };

        socket.onerror = (err) => {
            console.error('[Instant] WS error', err);
        };
    }

    function handleMessage(data) {
        const type = data.type;

        if (type === 'heartbeat') return;

        // Chat history load
        if (type === 'chat_history') {
            if (historyLoaded) return; // Don't re-render on WS reconnect
            historyLoaded = true;
            console.log('[Instant] WS chat_history received,', (data.messages || []).length, 'messages');

            const result = renderHistoryMessages(data.messages);
            // Load preview URL — prefer history, fallback to config
            const resolvedUrl = result.previewUrl || config.previewUrl;
            if (resolvedUrl) {
                loadPreview(resolvedUrl);
                setStatus('running', (result.appName || 'App') + ' is live');
            }
            scrollToBottom();
            return;
        }

        // AI streaming chunk
        if (type === 'ai_chunk') {
            // Notification handling
            if (data.is_notification) {
                handleNotification(data);
                return;
            }

            // Final signal
            if (data.is_final) {
                if (data.conversation_id && !conversationId) {
                    conversationId = data.conversation_id;
                }
                finishStreaming();
                return;
            }

            // Text chunk
            if (data.chunk) {
                if (!isStreaming) startStreaming();
                appendChunk(data.chunk);
            }
            return;
        }
    }

    function handleNotification(data) {
        const ntype = data.notification_type;

        if (ntype === 'instant_app_building' || ntype === 'instant_app_status') {
            const status = data.instant_app_status || 'building';
            const message = data.message || 'Building...';

            if (status === 'error') {
                setPreviewState('building', message);
                setStatus('error', 'Error');
                if (buildingMessage) buildingMessage.style.color = 'var(--danger, #e74c3c)';
            } else {
                if (buildingMessage) buildingMessage.style.color = '';
                setPreviewState('building', message);
                setStatus(status, 'Building');
            }
            appendBuildNotice(message, status);
        }

        if (ntype === 'env_var_request') {
            const envData = data.data || {};
            appendEnvVarRequest(envData.key, envData.description, envData.required !== false, envData.app_id);
            return;
        }

        if (ntype === 'instant_app_ready') {
            const url = data.preview_url;
            if (url) {
                loadPreview(url);
                setStatus('running', data.app_name + ' is live');
            }
            appendBuildNotice(data.message || 'App is ready!', 'running');
        }
    }

    // ---- Chat UI (matching main chat patterns) ----

    function clearWelcome() {
        const welcome = messageContainer.querySelector('.welcome-message');
        if (welcome) welcome.remove();
    }

    function escapeHtml(str) {
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function addMessageToChat(role, content) {
        clearWelcome();

        // Create message element — same structure as chat.js
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        // Create message content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.setAttribute('data-raw-content', content);

        if (role === 'assistant' || role === 'system') {
            contentDiv.innerHTML = marked.parse(content);
        } else {
            contentDiv.innerHTML = escapeHtml(content);
        }

        // Create copy button
        const copyButton = document.createElement('button');
        copyButton.className = 'message-copy-btn';
        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
        copyButton.title = 'Copy message';
        copyButton.onclick = function() {
            copyMessageToClipboard(content, this);
        };

        // Create message actions container
        const messageActions = document.createElement('div');
        messageActions.className = 'message-actions';
        messageActions.appendChild(copyButton);

        // Append elements
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(messageActions);
        messageContainer.appendChild(messageDiv);

        scrollToBottom();
        return messageDiv;
    }

    function copyMessageToClipboard(content, button) {
        navigator.clipboard.writeText(content).then(() => {
            button.classList.add('copied');
            button.innerHTML = '<i class="fas fa-check"></i>';
            setTimeout(() => {
                button.classList.remove('copied');
                button.innerHTML = '<i class="fas fa-copy"></i>';
            }, 2000);
        });
    }

    function appendBuildNotice(message, status) {
        // When a terminal status arrives, resolve all prior spinning notices
        if (status === 'running' || status === 'error') {
            messageContainer.querySelectorAll('.instant-build-notice.notice-building').forEach(prev => {
                prev.classList.remove('notice-building');
                prev.classList.add('notice-past');
                const spinner = prev.querySelector('.spinner-small');
                if (spinner) spinner.outerHTML = '<i class="fas fa-circle" style="font-size:5px;opacity:0.4;margin:0 2px"></i>';
            });
        }

        const el = document.createElement('div');
        el.className = 'instant-build-notice';
        if (status === 'error') el.classList.add('notice-error');
        else if (status === 'running') el.classList.add('notice-done');
        else if (status === 'done') el.classList.add('notice-past');
        else el.classList.add('notice-building');

        const icon = status === 'error' ? '<i class="fas fa-times-circle" style="font-size:10px"></i>'
                   : status === 'running' ? '<i class="fas fa-check-circle" style="font-size:10px"></i>'
                   : '<i class="fas fa-circle" style="font-size:5px;opacity:0.4;margin:0 2px"></i>';
        el.innerHTML = `${icon}<span>${escapeHtml(message)}</span>`;
        messageContainer.appendChild(el);
        scrollToBottom();
    }

    function startStreaming() {
        isStreaming = true;
        currentRawContent = '';
        clearWelcome();
        removeTypingIndicator();

        // Create the same message structure as addMessageToChat
        currentAssistantEl = document.createElement('div');
        currentAssistantEl.className = 'message assistant';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.setAttribute('data-raw-content', '');
        currentAssistantEl.appendChild(contentDiv);

        messageContainer.appendChild(currentAssistantEl);
        sendBtn.disabled = true;
    }

    function appendChunk(text) {
        if (!currentAssistantEl) startStreaming();
        currentRawContent += text;

        const contentDiv = currentAssistantEl.querySelector('.message-content');
        contentDiv.setAttribute('data-raw-content', currentRawContent);
        contentDiv.innerHTML = marked.parse(currentRawContent);

        scrollToBottom();
    }

    function finishStreaming() {
        if (currentAssistantEl) {
            // Add copy button + actions on completion
            const rawContent = currentRawContent;
            const copyButton = document.createElement('button');
            copyButton.className = 'message-copy-btn';
            copyButton.innerHTML = '<i class="fas fa-copy"></i>';
            copyButton.title = 'Copy message';
            copyButton.onclick = function() {
                copyMessageToClipboard(rawContent, this);
            };

            const messageActions = document.createElement('div');
            messageActions.className = 'message-actions';
            messageActions.appendChild(copyButton);
            currentAssistantEl.appendChild(messageActions);
        }

        removeTypingIndicator();
        isStreaming = false;
        currentAssistantEl = null;
        currentRawContent = '';
        sendBtn.disabled = false;
        chatInput.focus();
    }

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // ---- Typing Indicator ----

    function showTypingIndicator() {
        removeTypingIndicator();
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.id = 'typing-indicator';
        indicator.innerHTML = '<span></span><span></span><span></span>';
        messageContainer.appendChild(indicator);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
    }

    // ---- Send message ----

    function sendMessage(text) {
        if (!text.trim() && !window.instantAttachedFile) return;
        if (!socket || socket.readyState !== WebSocket.OPEN) return;

        const displayText = text || `Attached file: ${window.instantAttachedFile?.name || ''}`;
        addMessageToChat('user', displayText);
        showTypingIndicator();

        const payload = {
            type: 'message',
            message: text,
            conversation_id: conversationId,
            instant_mode: true,
        };
        if (projectId) payload.project_id = projectId;
        if (window.instantAttachedFile) {
            payload.file_data = {
                name: window.instantAttachedFile.name,
                type: window.instantAttachedFile.type,
                size: window.instantAttachedFile.size,
            };
            if (window.instantAttachedFile.id) payload.file_data.id = window.instantAttachedFile.id;
            window.instantAttachedFile = null;
            const indicator = document.querySelector('.instant-file-attachment');
            if (indicator) indicator.remove();
        }
        socket.send(JSON.stringify(payload));
    }

    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (!text && !window.instantAttachedFile) return;
        chatInput.value = '';
        chatInput.style.height = 'auto';
        sendMessage(text);
    });

    // ---- File Upload ----
    const fileUploadBtn = document.getElementById('file-upload-btn');
    const fileUploadInput = document.getElementById('file-upload-input');

    if (fileUploadBtn && fileUploadInput) {
        fileUploadBtn.addEventListener('click', () => fileUploadInput.click());

        fileUploadInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            fileUploadInput.value = '';

            // Remove existing indicator
            const existing = document.querySelector('.instant-file-attachment');
            if (existing) existing.remove();

            // Show uploading indicator
            const indicator = document.createElement('div');
            indicator.className = 'instant-file-attachment uploading';
            indicator.innerHTML = `<i class="fas fa-sync fa-spin"></i><span>Uploading ${escapeHtml(file.name)}...</span>`;
            const inputWrapper = document.querySelector('.input-wrapper');
            inputWrapper.insertBefore(indicator, inputWrapper.firstChild);

            // Upload via REST API
            try {
                const formData = new FormData();
                formData.append('file', file);
                if (conversationId) formData.append('conversation_id', conversationId);

                const resp = await fetch(`/api/files/upload/?_=${Date.now()}`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: formData,
                });
                const data = await resp.json();

                window.instantAttachedFile = {
                    file, name: file.name, type: file.type, size: file.size,
                    id: data.id || null,
                };

                indicator.classList.remove('uploading');
                indicator.classList.add('uploaded');
                indicator.innerHTML = `
                    <i class="fas fa-paperclip"></i>
                    <span>${escapeHtml(file.name)}</span>
                    <button type="button" class="instant-file-remove" title="Remove"><i class="fas fa-times"></i></button>
                `;
                indicator.querySelector('.instant-file-remove').addEventListener('click', () => {
                    window.instantAttachedFile = null;
                    indicator.remove();
                });
            } catch (err) {
                console.error('[Instant] File upload error:', err);
                // Still allow attaching without server-side upload
                window.instantAttachedFile = { file, name: file.name, type: file.type, size: file.size };
                indicator.classList.remove('uploading');
                indicator.classList.add('uploaded');
                indicator.innerHTML = `
                    <i class="fas fa-paperclip"></i>
                    <span>${escapeHtml(file.name)}</span>
                    <button type="button" class="instant-file-remove" title="Remove"><i class="fas fa-times"></i></button>
                `;
                indicator.querySelector('.instant-file-remove').addEventListener('click', () => {
                    window.instantAttachedFile = null;
                    indicator.remove();
                });
            }
        });
    }

    // Auto-resize textarea
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + 'px';
    });

    // Enter to send (shift+enter for newline)
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // ---- Preview ----

    function setPreviewState(state, message) {
        previewPlaceholder.style.display = state === 'placeholder' ? '' : 'none';
        previewBuilding.style.display = state === 'building' ? '' : 'none';
        previewIframe.style.display = state === 'running' ? '' : 'none';
        if (message && buildingMessage) buildingMessage.textContent = message;
        // Start/stop snake game based on building state
        if (state === 'building') startSnakeGame();
        else stopSnakeGame();
    }

    function setStatus(status, text) {
        statusDot.className = 'status-dot ' + status;
        statusText.textContent = text || status;
    }

    function loadPreview(url) {
        previewIframe.src = url;
        setPreviewState('running');
        previewUrlBar.style.display = '';
        previewUrlText.textContent = url.replace(/^https?:\/\//, '');
        previewUrlText.title = url;
        previewUrlText.onclick = () => window.open(url, '_blank');
        previewOpenBtn.href = url;
        if (previewRefreshBtn) previewRefreshBtn.style.display = '';
    }

    // ---- Rebuild & Refresh ----
    if (previewRefreshBtn) {
        previewRefreshBtn.addEventListener('click', () => {
            const appId = config.currentAppId;
            if (!appId) return;
            previewRefreshBtn.classList.add('refreshing');
            previewRefreshBtn.disabled = true;

            const url = standaloneMode
                ? `/api/instant/apps/${appId}/rebuild/`
                : `/api/instant/${projectId}/apps/${appId}/rebuild/`;

            fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': getCsrfToken() } })
                .then(r => r.json())
                .then(data => {
                    // Wait a moment for server to start, then reload iframe
                    setTimeout(() => {
                        if (previewIframe.src) previewIframe.src = previewIframe.src;
                        previewRefreshBtn.classList.remove('refreshing');
                        previewRefreshBtn.disabled = false;
                    }, 4000);
                })
                .catch(err => {
                    console.warn('[Instant] Rebuild error:', err);
                    previewRefreshBtn.classList.remove('refreshing');
                    previewRefreshBtn.disabled = false;
                });
        });
    }

    // Viewport toggle
    document.querySelectorAll('.viewport-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.viewport-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const vp = btn.dataset.viewport;
            previewIframe.className = 'instant-preview-iframe' + (vp !== 'desktop' ? ' viewport-' + vp : '');
        });
    });

    // ---- Draggable Divider ----

    const divider = document.getElementById('instant-divider');
    const chatPanel = document.querySelector('.instant-chat-panel');
    const instantMain = document.querySelector('.instant-main');
    const STORAGE_KEY = 'instant-panel-width';
    const MIN_CHAT = 300;
    const MAX_CHAT_RATIO = 0.6; // max 60% of available space

    function initPanelWidth() {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const w = parseInt(saved, 10);
            const max = instantMain.offsetWidth * MAX_CHAT_RATIO;
            chatPanel.style.width = Math.min(Math.max(w, MIN_CHAT), max) + 'px';
        } else {
            chatPanel.style.width = '40%';
        }
    }

    if (divider) {
        let isDragging = false;

        divider.addEventListener('mousedown', (e) => {
            e.preventDefault();
            isDragging = true;
            divider.classList.add('dragging');
            instantMain.classList.add('resizing');
        });

        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            const mainRect = instantMain.getBoundingClientRect();
            let newWidth = e.clientX - mainRect.left;
            const maxWidth = mainRect.width * MAX_CHAT_RATIO;
            newWidth = Math.min(Math.max(newWidth, MIN_CHAT), maxWidth);
            chatPanel.style.width = newWidth + 'px';
        });

        document.addEventListener('mouseup', () => {
            if (!isDragging) return;
            isDragging = false;
            divider.classList.remove('dragging');
            instantMain.classList.remove('resizing');
            localStorage.setItem(STORAGE_KEY, chatPanel.offsetWidth);
        });
    }

    // ---- Load conversation history via HTTP (fallback if WS doesn't deliver) ----

    function renderHistoryMessages(messages) {
        /**
         * Shared renderer for chat history — used by both WS and HTTP paths.
         * Returns { previewUrl, appName } extracted from build notices.
         */
        messageContainer.innerHTML = '';
        let lastPreviewUrl = null;
        let lastAppName = null;

        (messages || []).forEach(msg => {
            const content = msg.content || '';
            if (!content.trim()) return;

            // System messages that are JSON (build notices, env requests)
            if (msg.role === 'system') {
                try {
                    const parsed = JSON.parse(content);
                    if (parsed.type === 'env_var_request') {
                        const el = document.createElement('div');
                        el.className = 'notice-env-request notice-done';
                        el.innerHTML = `
                            <div class="env-request-header">
                                <i class="fas fa-key"></i>
                                <span>Set: <strong>${escapeHtml(parsed.key || '')}</strong></span>
                            </div>
                            <div class="env-request-desc">${escapeHtml(parsed.description || '')}</div>
                        `;
                        messageContainer.appendChild(el);
                        return;
                    }
                    if (parsed.type === 'instant_build_notice') {
                        const historyStatus = (parsed.status === 'building') ? 'done' : parsed.status;
                        appendBuildNotice(parsed.message, historyStatus);
                        if (parsed.status === 'running' && parsed.preview_url) {
                            lastPreviewUrl = parsed.preview_url;
                            lastAppName = parsed.app_name;
                        }
                        return;
                    }
                } catch (_) { /* not JSON — render as normal text */ }
            }

            // Regular user/assistant/system messages
            addMessageToChat(msg.role, content);
        });

        return { previewUrl: lastPreviewUrl, appName: lastAppName };
    }

    function loadConversationHistoryHTTP() {
        if (historyLoaded || !conversationId) return;
        console.log('[Instant] Loading history via HTTP for conversation', conversationId);
        fetch(`/api/conversations/${conversationId}/`, { credentials: 'same-origin' })
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(data => {
                if (historyLoaded) return; // WS beat us
                historyLoaded = true;
                console.log('[Instant] HTTP loaded', (data.messages || []).length, 'messages');
                const result = renderHistoryMessages(data.messages);
                const resolvedUrl = result.previewUrl || config.previewUrl;
                if (resolvedUrl) {
                    loadPreview(resolvedUrl);
                    setStatus('running', (result.appName || 'App') + ' is live');
                }
                scrollToBottom();
            })
            .catch(err => console.warn('[Instant] HTTP history load error:', err));
    }

    // ---- App Switcher Dropdown (set up EARLY so it always works) ----
    const appSwitcherBtn = document.getElementById('app-switcher-btn');
    const appSwitcherMenu = document.getElementById('app-switcher-menu');

    if (appSwitcherBtn && appSwitcherMenu) {
        appSwitcherBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = appSwitcherMenu.classList.toggle('open');
            if (isOpen) {
                const rect = appSwitcherBtn.getBoundingClientRect();
                appSwitcherMenu.style.top = (rect.bottom + 4) + 'px';
                appSwitcherMenu.style.right = (window.innerWidth - rect.right) + 'px';
            }
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!appSwitcherMenu.contains(e.target) && !appSwitcherBtn.contains(e.target)) {
                appSwitcherMenu.classList.remove('open');
            }
        });
    }

    // ---- Init ----

    console.log('[Instant] Init config:', JSON.stringify({
        projectId, standaloneMode, appId: config.currentAppId,
        status: config.currentAppStatus, hasPreviewUrl: !!config.previewUrl,
        conversationId
    }));

    try {
        initPanelWidth();
    } catch (e) {
        console.warn('[Instant] initPanelWidth error:', e);
    }

    // If we already have a preview URL, load it
    if (config.previewUrl) {
        loadPreview(config.previewUrl);
        setStatus('running', 'Running');
    } else if (config.currentAppStatus === 'building') {
        setPreviewState('building', 'Building your app...');
        setStatus('building', 'Building');
    }

    connectWebSocket();

    // Fallback: if WebSocket doesn't deliver chat_history within 2s, load via HTTP
    if (conversationId) {
        setTimeout(() => {
            if (!historyLoaded) {
                console.warn('[Instant] WS chat_history not received after 2s, loading via HTTP fallback');
                loadConversationHistoryHTTP();
            }
        }, 2000);
    }

    // ---- Preview / Logs / Env Tab Toggle ----

    const previewContent = document.getElementById('preview-content');
    const logsContent = document.getElementById('logs-content');
    const envContent = document.getElementById('env-content');
    const logsOutput = document.getElementById('logs-output');
    const logsRefreshBtn = document.getElementById('logs-refresh-btn');
    const logsClearBtn = document.getElementById('logs-clear-btn');
    const logsAutoscroll = document.getElementById('logs-autoscroll');
    const viewportToggle = document.getElementById('viewport-toggle');
    let activeTab = 'preview';
    let logsPollingInterval = null;
    let logsOffset = 0;
    let envLoaded = false;

    document.querySelectorAll('.preview-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.preview-tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeTab = btn.dataset.tab;

            previewContent.style.display = activeTab === 'preview' ? '' : 'none';
            logsContent.style.display = activeTab === 'logs' ? 'flex' : 'none';
            if (envContent) envContent.style.display = activeTab === 'env' ? 'flex' : 'none';

            if (viewportToggle) viewportToggle.style.display = (activeTab === 'preview') ? '' : 'none';
            if (previewRefreshBtn) previewRefreshBtn.style.display = (activeTab === 'preview' && previewIframe.src) ? '' : 'none';

            if (activeTab === 'logs') {
                startLogsPolling();
            } else {
                stopLogsPolling();
            }

            if (activeTab === 'env' && !envLoaded) {
                loadEnvVars();
            }
        });
    });

    function fetchLogs(reset) {
        const appId = config.currentAppId;
        if (!appId) return;
        if (!standaloneMode && !projectId) return;

        if (reset) logsOffset = 0;
        const url = standaloneMode
            ? `/api/instant/apps/${appId}/logs/?offset=${logsOffset}`
            : `/api/instant/${projectId}/apps/${appId}/logs/?offset=${logsOffset}`;

        fetch(url, { credentials: 'same-origin' })
            .then(r => r.json())
            .then(data => {
                if (data.error && !data.logs) {
                    if (logsOutput.querySelector('.logs-placeholder')) {
                        logsOutput.innerHTML = `<span class="log-warn">${escapeHtml(data.error)}</span>\n`;
                    }
                    return;
                }
                if (data.logs) {
                    // Remove placeholder on first real content
                    const placeholder = logsOutput.querySelector('.logs-placeholder');
                    if (placeholder) placeholder.remove();

                    // Colorize and append
                    const colored = colorizeLogs(data.logs);
                    logsOutput.insertAdjacentHTML('beforeend', colored);

                    if (data.offset) logsOffset = data.offset;

                    // Auto-scroll
                    if (logsAutoscroll && logsAutoscroll.checked) {
                        logsOutput.scrollTop = logsOutput.scrollHeight;
                    }
                }
            })
            .catch(err => {
                console.warn('[Instant] Logs fetch error:', err);
            });
    }

    function colorizeLogs(text) {
        return escapeHtml(text)
            .split('\n')
            .map(line => {
                if (/error|ERR!|Error/i.test(line)) return `<span class="log-error">${line}</span>`;
                if (/warn|WARN/i.test(line)) return `<span class="log-warn">${line}</span>`;
                if (/ready|compiled|listening|started/i.test(line)) return `<span class="log-info">${line}</span>`;
                return line;
            })
            .join('\n');
    }

    function startLogsPolling() {
        stopLogsPolling();
        fetchLogs(false);
        logsPollingInterval = setInterval(() => fetchLogs(false), 3000);
    }

    function stopLogsPolling() {
        if (logsPollingInterval) {
            clearInterval(logsPollingInterval);
            logsPollingInterval = null;
        }
    }

    if (logsRefreshBtn) {
        logsRefreshBtn.addEventListener('click', () => fetchLogs(true));
    }
    if (logsClearBtn) {
        logsClearBtn.addEventListener('click', () => {
            logsOutput.innerHTML = '<span class="logs-placeholder">Logs cleared.</span>';
            logsOffset = 0;
        });
    }

    // ---- Env Vars CRUD ----

    function getEnvApiUrl() {
        const appId = config.currentAppId;
        if (!appId) return null;
        if (standaloneMode) return `/api/instant/apps/${appId}/env/`;
        if (projectId) return `/api/instant/${projectId}/apps/${appId}/env/`;
        return null;
    }

    function loadEnvVars() {
        const url = getEnvApiUrl();
        if (!url) return;

        fetch(url, { credentials: 'same-origin' })
            .then(r => r.json())
            .then(data => {
                envLoaded = true;
                renderEnvTable(data.env_vars || {});
            })
            .catch(err => console.warn('[Instant] Env fetch error:', err));
    }

    function renderEnvTable(vars) {
        const table = document.getElementById('env-table');
        const emptyState = document.getElementById('env-empty-state');
        if (!table) return;

        // Remove existing rows
        table.querySelectorAll('.env-row').forEach(r => r.remove());

        const keys = Object.keys(vars);
        if (keys.length === 0) {
            if (emptyState) emptyState.style.display = '';
            return;
        }
        if (emptyState) emptyState.style.display = 'none';

        keys.forEach(key => {
            addEnvRow(key, vars[key], false);
        });
    }

    function addEnvRow(key, value, isNew) {
        const table = document.getElementById('env-table');
        const emptyState = document.getElementById('env-empty-state');
        if (emptyState) emptyState.style.display = 'none';

        const row = document.createElement('div');
        row.className = 'env-row';

        const keyInput = document.createElement('input');
        keyInput.className = 'env-key-input';
        keyInput.type = 'text';
        keyInput.placeholder = 'KEY';
        keyInput.value = key || '';
        if (!isNew && key) {
            keyInput.readOnly = true;
            keyInput.classList.add('readonly');
        }

        const valueInput = document.createElement('input');
        valueInput.className = 'env-value-input';
        valueInput.type = 'password';
        valueInput.placeholder = 'value';
        valueInput.value = value || '';

        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'env-value-toggle';
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
        toggleBtn.title = 'Toggle visibility';
        toggleBtn.onclick = () => {
            if (valueInput.type === 'password') {
                valueInput.type = 'text';
                toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i>';
            } else {
                valueInput.type = 'password';
                toggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
            }
        };

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'env-delete-btn';
        deleteBtn.innerHTML = '<i class="fas fa-trash"></i>';
        deleteBtn.title = 'Remove';
        deleteBtn.onclick = () => {
            row.remove();
            // Show empty state if no rows left
            if (!table.querySelector('.env-row')) {
                if (emptyState) emptyState.style.display = '';
            }
        };

        row.appendChild(keyInput);
        row.appendChild(valueInput);
        row.appendChild(toggleBtn);
        row.appendChild(deleteBtn);
        table.appendChild(row);

        if (isNew) keyInput.focus();
    }

    function collectEnvVars() {
        const rows = document.querySelectorAll('#env-table .env-row');
        const vars = {};
        rows.forEach(row => {
            const key = row.querySelector('.env-key-input').value.trim();
            const value = row.querySelector('.env-value-input').value;
            if (key) vars[key] = value;
        });
        return vars;
    }

    function saveEnvVars() {
        const url = getEnvApiUrl();
        if (!url) return;

        const vars = collectEnvVars();
        fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ env_vars: vars }),
        })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                console.error('[Instant] Env save error:', data.error);
                return;
            }
            // Flash the save button green briefly
            const saveBtn = document.getElementById('env-save-btn');
            if (saveBtn) {
                saveBtn.innerHTML = '<i class="fas fa-check"></i> Saved';
                setTimeout(() => { saveBtn.innerHTML = '<i class="fas fa-save"></i> Save'; }, 2000);
            }
            // Reload to normalize
            renderEnvTable(data.env_vars || {});
        })
        .catch(err => console.error('[Instant] Env save error:', err));
    }

    function getCsrfToken() {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }

    // Wire up env toolbar buttons
    const envAddBtn = document.getElementById('env-add-btn');
    const envSaveBtn = document.getElementById('env-save-btn');
    if (envAddBtn) envAddBtn.addEventListener('click', () => addEnvRow('', '', true));
    if (envSaveBtn) envSaveBtn.addEventListener('click', saveEnvVars);

    // ---- Env Var Request (from AI) ----

    function appendEnvVarRequest(key, description, required, appId) {
        const el = document.createElement('div');
        el.className = 'notice-env-request';
        el.setAttribute('data-env-key', key);

        const reqLabel = required ? 'Required' : 'Optional';
        el.innerHTML = `
            <div class="env-request-header">
                <i class="fas fa-key"></i>
                <span>${reqLabel}: <strong>${escapeHtml(key)}</strong></span>
            </div>
            <div class="env-request-desc">${escapeHtml(description)}</div>
            <div class="env-request-form">
                <input type="password" class="env-request-input" placeholder="Enter value for ${escapeHtml(key)}...">
                <button class="env-request-set-btn">Set</button>
            </div>
        `;

        const input = el.querySelector('.env-request-input');
        const setBtn = el.querySelector('.env-request-set-btn');

        setBtn.addEventListener('click', () => {
            const value = input.value;
            if (!value && required) return;

            // Save to env vars via API
            const resolvedAppId = appId || config.currentAppId;
            if (!resolvedAppId) return;

            const url = standaloneMode
                ? `/api/instant/apps/${resolvedAppId}/env/`
                : `/api/instant/${projectId}/apps/${resolvedAppId}/env/`;

            // First fetch current vars, then merge
            fetch(url, { credentials: 'same-origin' })
                .then(r => r.json())
                .then(data => {
                    const currentVars = data.env_vars || {};
                    currentVars[key] = value;
                    return fetch(url, {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        },
                        body: JSON.stringify({ env_vars: currentVars }),
                    });
                })
                .then(r => r.json())
                .then(() => {
                    // Mark as done
                    el.classList.add('notice-done');
                    input.disabled = true;
                    input.type = 'password';
                    setBtn.textContent = 'Set';
                    setBtn.disabled = true;

                    // Notify the AI that the var was set
                    if (socket && socket.readyState === WebSocket.OPEN) {
                        socket.send(JSON.stringify({
                            type: 'message',
                            message: `I've set the environment variable \`${key}\`. You can proceed.`,
                            conversation_id: conversationId,
                            instant_mode: true,
                            ...(projectId ? { project_id: projectId } : {}),
                        }));
                        addMessageToChat('user', `I've set the environment variable \`${key}\`. You can proceed.`);
                        showTypingIndicator();
                    }

                    // Reload env tab if it was loaded
                    envLoaded = false;
                })
                .catch(err => console.error('[Instant] Env var set error:', err));
        });

        messageContainer.appendChild(el);
        scrollToBottom();
    }

    // ---- Snake Game (plays while building) ----
    const snakeCanvas = document.getElementById('snake-game');
    const snakeCtx = snakeCanvas ? snakeCanvas.getContext('2d') : null;
    let snakeInterval = null;
    let snakeState = null;

    const CELL = 16;                       // px per grid cell
    const COLS = 20, ROWS = 20;            // 320x320 canvas
    const TICK_MS = 100;

    function initSnakeState() {
        const mid = Math.floor(ROWS / 2);
        return {
            snake: [{x: 5, y: mid}, {x: 4, y: mid}, {x: 3, y: mid}],
            dir: {x: 1, y: 0},
            nextDir: {x: 1, y: 0},
            food: spawnFood([{x: 5, y: mid}, {x: 4, y: mid}, {x: 3, y: mid}]),
            score: 0,
            autoMode: true,
            autoTimer: 0,
        };
    }

    function spawnFood(snake) {
        let pos;
        do {
            pos = {x: Math.floor(Math.random() * COLS), y: Math.floor(Math.random() * ROWS)};
        } while (snake.some(s => s.x === pos.x && s.y === pos.y));
        return pos;
    }

    function autoDirection(s) {
        const head = s.snake[0];
        const food = s.food;
        const dir = s.dir;

        // Simple chase: prefer direction toward food, avoid self-collision
        const candidates = [
            {x: 0, y: -1}, {x: 0, y: 1}, {x: -1, y: 0}, {x: 1, y: 0}
        ].filter(d => !(d.x === -dir.x && d.y === -dir.y)); // no reverse

        // Check which moves are safe
        const safe = candidates.filter(d => {
            const nx = (head.x + d.x + COLS) % COLS;
            const ny = (head.y + d.y + ROWS) % ROWS;
            return !s.snake.some(seg => seg.x === nx && seg.y === ny);
        });

        if (safe.length === 0) return dir; // no safe move, keep going

        // Sort by distance to food
        safe.sort((a, b) => {
            const ax = (head.x + a.x + COLS) % COLS, ay = (head.y + a.y + ROWS) % ROWS;
            const bx = (head.x + b.x + COLS) % COLS, by = (head.y + b.y + ROWS) % ROWS;
            const da = Math.abs(ax - food.x) + Math.abs(ay - food.y);
            const db = Math.abs(bx - food.x) + Math.abs(by - food.y);
            return da - db;
        });

        return safe[0];
    }

    function tickSnake() {
        if (!snakeState) return;
        const s = snakeState;

        // Auto-pilot
        if (s.autoMode) {
            s.nextDir = autoDirection(s);
        }

        s.dir = s.nextDir;
        const head = s.snake[0];
        const nx = (head.x + s.dir.x + COLS) % COLS;
        const ny = (head.y + s.dir.y + ROWS) % ROWS;

        // Self-collision → restart
        if (s.snake.some(seg => seg.x === nx && seg.y === ny)) {
            snakeState = initSnakeState();
            return;
        }

        s.snake.unshift({x: nx, y: ny});

        if (nx === s.food.x && ny === s.food.y) {
            s.score++;
            s.food = spawnFood(s.snake);
        } else {
            s.snake.pop();
        }

        drawSnake();
    }

    function drawSnake() {
        if (!snakeCtx || !snakeState) return;
        const ctx = snakeCtx;
        const s = snakeState;

        ctx.clearRect(0, 0, snakeCanvas.width, snakeCanvas.height);

        // Background grid (subtle)
        ctx.strokeStyle = 'rgba(255,255,255,0.03)';
        ctx.lineWidth = 0.5;
        for (let x = 0; x <= COLS; x++) {
            ctx.beginPath(); ctx.moveTo(x * CELL, 0); ctx.lineTo(x * CELL, ROWS * CELL); ctx.stroke();
        }
        for (let y = 0; y <= ROWS; y++) {
            ctx.beginPath(); ctx.moveTo(0, y * CELL); ctx.lineTo(COLS * CELL, y * CELL); ctx.stroke();
        }

        // Food
        ctx.fillStyle = '#f59e0b';
        ctx.shadowColor = '#f59e0b';
        ctx.shadowBlur = 8;
        ctx.beginPath();
        ctx.arc(s.food.x * CELL + CELL / 2, s.food.y * CELL + CELL / 2, CELL / 2 - 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;

        // Snake body
        s.snake.forEach((seg, i) => {
            const alpha = 1 - (i / s.snake.length) * 0.6;
            if (i === 0) {
                ctx.fillStyle = '#bb86fc';
                ctx.shadowColor = '#bb86fc';
                ctx.shadowBlur = 6;
            } else {
                ctx.fillStyle = `rgba(187, 134, 252, ${alpha})`;
                ctx.shadowBlur = 0;
            }
            const sx = seg.x * CELL + 1, sy = seg.y * CELL + 1, sw = CELL - 2, r = 3;
            ctx.beginPath();
            ctx.moveTo(sx + r, sy);
            ctx.lineTo(sx + sw - r, sy); ctx.arcTo(sx + sw, sy, sx + sw, sy + r, r);
            ctx.lineTo(sx + sw, sy + sw - r); ctx.arcTo(sx + sw, sy + sw, sx + sw - r, sy + sw, r);
            ctx.lineTo(sx + r, sy + sw); ctx.arcTo(sx, sy + sw, sx, sy + sw - r, r);
            ctx.lineTo(sx, sy + r); ctx.arcTo(sx, sy, sx + r, sy, r);
            ctx.fill();
        });
        ctx.shadowBlur = 0;

        // Score
        ctx.fillStyle = 'rgba(255,255,255,0.25)';
        ctx.font = '10px monospace';
        ctx.fillText('Score: ' + s.score, 6, 14);

        // Auto/manual indicator
        ctx.fillStyle = 'rgba(255,255,255,0.2)';
        ctx.fillText(s.autoMode ? 'Auto' : 'You', COLS * CELL - 30, 14);
    }

    function startSnakeGame() {
        if (snakeInterval) return;
        if (!snakeCanvas) return;
        snakeState = initSnakeState();
        drawSnake();
        snakeInterval = setInterval(tickSnake, TICK_MS);
    }

    function stopSnakeGame() {
        if (snakeInterval) {
            clearInterval(snakeInterval);
            snakeInterval = null;
        }
        snakeState = null;
    }

    // Keyboard controls — arrow keys or WASD
    document.addEventListener('keydown', (e) => {
        if (!snakeState) return;
        const keyMap = {
            ArrowUp: {x: 0, y: -1}, ArrowDown: {x: 0, y: 1},
            ArrowLeft: {x: -1, y: 0}, ArrowRight: {x: 1, y: 0},
            w: {x: 0, y: -1}, s: {x: 0, y: 1},
            a: {x: -1, y: 0}, d: {x: 1, y: 0},
        };
        const nd = keyMap[e.key];
        if (!nd) return;
        // Don't reverse
        if (nd.x === -snakeState.dir.x && nd.y === -snakeState.dir.y) return;
        snakeState.nextDir = nd;
        snakeState.autoMode = false;
        // Resume auto after 5 seconds of no input
        clearTimeout(snakeState.autoTimer);
        snakeState.autoTimer = setTimeout(() => { if (snakeState) snakeState.autoMode = true; }, 5000);
        e.preventDefault();
    });
});
