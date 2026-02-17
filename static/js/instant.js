/**
 * Instant Mode — chat + live preview
 * Reuses the same message UI patterns as the main chat (chat.js).
 */
document.addEventListener('DOMContentLoaded', () => {
    const config = window.INSTANT_CONFIG || {};
    const projectId = config.projectId;
    const projectDbId = config.projectDbId;

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
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    let socket = null;
    let conversationId = config.conversationId;
    let isStreaming = false;
    let currentAssistantEl = null;
    let currentRawContent = '';

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
            clearWelcome();
            (data.messages || []).forEach(msg => {
                addMessageToChat(msg.role, msg.content);
            });
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
            setPreviewState('building', message);
            setStatus(status, message);
            appendBuildNotice(message);
        }

        if (ntype === 'instant_app_ready') {
            const url = data.preview_url;
            if (url) {
                loadPreview(url);
                setStatus('running', data.app_name + ' is live');
            }
            appendBuildNotice(data.message || 'App is ready!');
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

    function appendBuildNotice(message) {
        const el = document.createElement('div');
        el.className = 'instant-build-notice';
        el.innerHTML = `<div class="spinner-small"></div><span>${escapeHtml(message)}</span>`;
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
        if (!text.trim() || !socket || socket.readyState !== WebSocket.OPEN) return;

        addMessageToChat('user', text);
        showTypingIndicator();

        socket.send(JSON.stringify({
            type: 'message',
            message: text,
            conversation_id: conversationId,
            project_id: projectId,
            instant_mode: true,
        }));
    }

    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (!text) return;
        chatInput.value = '';
        chatInput.style.height = 'auto';
        sendMessage(text);
    });

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
        previewOpenBtn.href = url;
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

    // ---- Init ----

    initPanelWidth();

    // If we already have a preview URL, load it
    if (config.previewUrl) {
        loadPreview(config.previewUrl);
        setStatus('running', 'Running');
    } else if (config.currentAppStatus === 'building') {
        setPreviewState('building', 'Building your app...');
        setStatus('building', 'Building');
    }

    connectWebSocket();

    // ---- App switcher ----
    window.instantMode = {
        switchApp(appId) {
            if (!appId) {
                window.location.href = `/instant/project/${projectId}/`;
            } else {
                window.location.href = `/instant/project/${projectId}/app/${appId}/`;
            }
        }
    };
});
