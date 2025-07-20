document.addEventListener('DOMContentLoaded', () => {
    // Initialize PRD streaming debug globals
    window.PRD_STREAM_DEBUG = true;
    window.PRD_STREAM_CHUNKS = [];
    window.PRD_STREAM_CONTENT = '';
    console.log('🎯 PRD STREAMING DEBUG MODE ENABLED');
    console.log('🎯 PRD content will be logged to console automatically');
    console.log('🎯 Access chunks: window.PRD_STREAM_CHUNKS');
    console.log('🎯 Access full content: window.PRD_STREAM_CONTENT');
    
    // Check if the artifacts panel is in the DOM
    const artifactsPanel = document.getElementById('artifacts-panel');
    if (artifactsPanel) {
        console.log('✅ Artifacts panel found in DOM');
    } else {
        console.error('❌ Artifacts panel NOT found in DOM! This will cause issues with notifications.');
    }
    
    // Check if the ArtifactsPanel API is available
    if (window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function') {
        console.log('✅ ArtifactsPanel API is available');
    } else {
        console.log('❌ ArtifactsPanel API is NOT available yet. This may be a timing issue.');
        // We'll check again after a delay to see if it's a timing issue
        setTimeout(() => {
            if (window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function') {
                console.log('✅ ArtifactsPanel API is now available (after delay)');
            } else {
                console.error('❌ ArtifactsPanel API is still NOT available after delay. Check script loading order.');
            }
        }, 1000);
    }
    
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');
    const messageContainer = document.querySelector('.message-container') || createMessageContainer();
    const conversationList = document.getElementById('conversation-list');
    const newChatBtn = document.getElementById('new-chat-btn');
    const backBtn = document.getElementById('back-btn');
    const sidebar = document.getElementById('sidebar');
    const appContainer = document.querySelector('.app-container');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    
    let currentConversationId = null;
    let currentProvider = 'openai';
    let currentProjectId = null;
    let socket = null;
    let isSocketConnected = false;
    let messageQueue = [];
    let isStreaming = false; // Track whether we're currently streaming a response
    let stopRequested = false; // Track if user has already requested to stop generation
    
    // Chunk reassembly tracking
    let chunkBuffers = {};  // Store partial chunks by sequence number
    let expectedSequence = 0;  // Track expected sequence number
    
    // Get or create the send button
    const sendBtn = document.getElementById('send-btn') || createSendButton();
    let stopBtn = null; // Will be created when needed
    
    // Button state machine to prevent race conditions
    const ButtonState = {
        SEND: 'send',
        STOP: 'stop',
        TRANSITIONING: 'transitioning'
    };
    let currentButtonState = ButtonState.SEND;
    let buttonTransitionTimeout = null;
    
    // Extract project ID from path if in format /chat/project/{id}/
    function extractProjectIdFromPath() {
        const pathParts = window.location.pathname.split('/').filter(part => part);
        if (pathParts.length >= 3 && pathParts[0] === 'chat' && pathParts[1] === 'project') {
            return pathParts[2];
        }
        return null;
    }
    
    // Check for conversation ID in the URL or from Django template
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('conversation_id')) {
        currentConversationId = urlParams.get('conversation_id');
    } else if (typeof initialConversationId !== 'undefined' && initialConversationId) {
        currentConversationId = initialConversationId;
    }
    
    // Check for project ID from different sources
    if (urlParams.has('project_id')) {
        currentProjectId = urlParams.get('project_id');
    } else if (typeof initialProjectId !== 'undefined' && initialProjectId) {
        currentProjectId = initialProjectId;
    } else {
        // Try to extract from path
        const pathProjectId = extractProjectIdFromPath();
        if (pathProjectId) {
            currentProjectId = pathProjectId;
            console.log('Extracted project ID from path:', currentProjectId);
        }
    }
    
    // Store requirements for later use
    let pendingRequirements = null;
    const requirements = urlParams.get('requirements');
    console.log('URL requirements parameter:', requirements);
    if (requirements) {
        pendingRequirements = decodeURIComponent(requirements);
        console.log('Decoded requirements:', pendingRequirements);
        // Set the requirements in the chat input immediately so user can see it
        if (chatInput) {
            chatInput.value = pendingRequirements;
            console.log('Set chat input value to:', chatInput.value);
        } else {
            console.error('Chat input element not found!');
            // Try again after a short delay
            setTimeout(() => {
                const delayedChatInput = document.getElementById('chat-input');
                if (delayedChatInput) {
                    delayedChatInput.value = pendingRequirements;
                    console.log('Set chat input value after delay to:', delayedChatInput.value);
                }
            }, 100);
        }
        
        // Remove requirements from URL to avoid resubmitting on refresh
        const url = new URL(window.location);
        url.searchParams.delete('requirements');
        window.history.replaceState({}, '', url);
    }
    
    // Also set up a global variable that can be accessed from console for debugging
    window.debugPendingRequirements = pendingRequirements;
    
    // Initialize WebSocket connection
    connectWebSocket();
    
    // Load agent settings and initialize turbo mode
    loadAgentSettings();
    
    // Test backend notification sending
    window.testBackendNotification = function() {
        if (socket && socket.readyState === WebSocket.OPEN) {
            console.log('%c SENDING TEST NOTIFICATION REQUEST ', 'background: #00ff00; color: #000; font-weight: bold; padding: 5px;');
            socket.send(JSON.stringify({
                type: 'test_notification'
            }));
            console.log('Test notification request sent. Check console for WebSocket messages...');
        } else {
            console.error('WebSocket not connected');
        }
    };

    // Test function for execute_command
    window.testExecuteCommand = function() {
        if (socket && socket.readyState === WebSocket.OPEN) {
            console.log('%c SENDING TEST EXECUTE_COMMAND REQUEST ', 'background: #ffa500; color: #000; font-weight: bold; padding: 5px;');
            socket.send(JSON.stringify({
                type: 'test_execute_command'
            }));
            console.log('Test execute_command request sent. Check console for WebSocket messages...');
        } else {
            console.error('WebSocket not connected');
        }
    };
    
    // Add manual animation trigger for testing
    // window.triggerToolAnimation = function(toolName = 'extract_features') {
    //     console.log('Manually triggering tool animation for:', toolName);
        
    //     // 1. Show tool execution indicator
    //     const indicator = window.showToolExecutionIndicator(toolName);
    //     console.log('Tool execution indicator created:', indicator);
        
    //     // 2. Show function call indicator
    //     const funcIndicator = showFunctionCallIndicator(toolName);
    //     console.log('Function call indicator created:', funcIndicator);
        
    //     // 3. Add separator
    //     const separator = document.createElement('div');
    //     separator.className = 'function-call-separator';
    //     separator.innerHTML = `<div class="separator-line"></div>
    //                           <div class="separator-text">Manually triggered: ${toolName}</div>
    //                           <div class="separator-line"></div>`;
    //     messageContainer.appendChild(separator);
        
    //     // 4. Show progress for supported functions
    //     if (['extract_features', 'extract_personas'].includes(toolName)) {
    //         handleToolProgress({
    //             tool_name: toolName,
    //             message: `Starting ${toolName.replace('_', ' ')}...`,
    //             progress_percentage: 0
    //         });
            
    //         // Simulate progress
    //         setTimeout(() => {
    //             handleToolProgress({
    //                 tool_name: toolName,
    //                 message: `Processing...`,
    //                 progress_percentage: 50
    //             });
    //         }, 1000);
            
    //         setTimeout(() => {
    //             handleToolProgress({
    //                 tool_name: toolName,
    //                 message: `Completing...`,
    //                 progress_percentage: 100
    //             });
    //         }, 2000);
    //     }
        
    //     return true;
    // };
    
    // Auto-resize the text area based on content
    chatInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });
    
    // Handle Enter key press in the textarea
    chatInput.addEventListener('keydown', function(e) {
        // Check if Enter was pressed without Shift key (Shift+Enter allows for new lines)
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault(); // Prevent the default behavior (new line)
            const message = this.value.trim();
            if (message || window.attachedFile) {
                sendMessage(message);
                this.value = '';
                this.style.height = 'auto';
                
                // Clear file attachment if exists
                const fileAttachmentIndicator = document.querySelector('.input-file-attachment');
                if (fileAttachmentIndicator) {
                    fileAttachmentIndicator.remove();
                }
            }
        }
    });
    
    // Load conversation history on page load
    loadConversations();
    
    // If we have a conversation ID, load that conversation
    if (currentConversationId) {
        loadConversation(currentConversationId);
    }
    
    // New chat button click handler
    newChatBtn.addEventListener('click', () => {
        // Reset conversation ID but keep project ID if it's from URL
        currentConversationId = null;
        
        // Check if we should maintain the project ID
        const urlParams = new URLSearchParams(window.location.search);
        console.log('Url Params:', urlParams);
        const urlProjectId = urlParams.get('project_id');
        const pathProjectId = extractProjectIdFromPath();
        
        // Only reset project ID if it's not specified in URL or path
        if (!urlProjectId && !pathProjectId) {
            currentProjectId = null;
        } else if (pathProjectId && !currentProjectId) {
            // Update currentProjectId if it was found in the path but wasn't set
            currentProjectId = pathProjectId;
        }
        
        // Clear chat messages and show welcome message
        clearChatMessages();
        
        // Add welcome message
        const welcomeMessage = document.createElement('div');
        welcomeMessage.className = 'welcome-message';
        welcomeMessage.innerHTML = '<h2>LFG 🚀🚀</h2><p>Start a conversation with the AI assistant below.</p>';
        messageContainer.appendChild(welcomeMessage);
        
        // Reset WebSocket connection to ensure clean session
        connectWebSocket();
        
        // Update URL handling
        if (pathProjectId) {
            // If we're in path format, keep the same URL format but remove conversation_id param
            const url = new URL(window.location);
            url.searchParams.delete('conversation_id');
            window.history.pushState({}, '', url);
        } else {
            // Normal handling for query param style URLs
            const url = new URL(window.location);
            url.searchParams.delete('conversation_id');
            // Only remove project_id from URL if it's not specified
            if (!urlProjectId) {
                url.searchParams.delete('project_id');
            }
            window.history.pushState({}, '', url);
        }
        
        // Remove active class from all conversations in sidebar
        document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.remove('active');
        });
        
        // Focus on input for immediate typing
        chatInput.focus();
        
        console.log('New chat session started with project ID:', currentProjectId);
    });
    
    // Submit message when form is submitted
    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const message = chatInput.value.trim();
        if (message || window.attachedFile) {
            sendMessage(message);
            chatInput.value = '';
            chatInput.style.height = 'auto';
            
            // Clear file attachment if exists
            const fileAttachmentIndicator = document.querySelector('.input-file-attachment');
            if (fileAttachmentIndicator) {
                fileAttachmentIndicator.remove();
            }
        }
    });
    
    // Set up provider selection
    const providerOptions = document.querySelectorAll('input[name="ai-provider"]');
    providerOptions.forEach(option => {
        option.addEventListener('change', function() {
            if (this.checked) {
                currentProvider = this.value;
                console.log(`Switched to ${currentProvider} provider`);
            }
        });
    });
    
    // Back button click handler
    if (backBtn) {
        backBtn.addEventListener('click', () => {
            window.location.href = '/projects/';
        });
    }
    
    // Function to synchronize streaming state with server
    function syncStreamingState() {
        if (socket && socket.readyState === WebSocket.OPEN) {
            // Request current streaming state from server
            const syncMessage = {
                type: 'sync_state',
                conversation_id: currentConversationId
            };
            socket.send(JSON.stringify(syncMessage));
            console.log('Sent sync state request');
        }
    }
    
    // Window event listeners for WebSocket
    window.addEventListener('beforeunload', () => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.close();
        }
    });
    
    // File upload functionality
    const fileUploadBtn = document.getElementById('file-upload-btn');
    const fileUploadInput = document.getElementById('file-upload-input');
    
    if (fileUploadBtn && fileUploadInput) {
        fileUploadBtn.addEventListener('click', () => {
            fileUploadInput.click();
        });
        
        fileUploadInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                console.log('%c FILE SELECTED', 'background: #44f; color: white; font-weight: bold;');
                console.log('User selected file:', file.name, 'type:', file.type, 'size:', file.size);
                
                // Create a notification about the selected file
                const fileInfo = document.createElement('div');
                fileInfo.className = 'file-info';
                fileInfo.textContent = `Selected file: ${file.name}`;
                
                // Show the selected file notification temporarily
                const inputWrapper = document.querySelector('.input-wrapper');
                inputWrapper.appendChild(fileInfo);
                
                // Simple animation to show file is ready
                setTimeout(() => {
                    fileInfo.classList.add('show');
                }, 10);
                
                // Get current conversation ID - first check currentConversationId, then URL
                let conversationId = currentConversationId;
                if (!conversationId) {
                    // Try to get it from URL
                    const urlParams = new URLSearchParams(window.location.search);
                    if (urlParams.has('conversation_id')) {
                        conversationId = urlParams.get('conversation_id');
                        console.log('Found conversation ID in URL:', conversationId);
                        // Update current conversation ID
                        currentConversationId = conversationId;
                    }
                }
                
                // File will be stored in this object until message is sent
                const fileData = {
                    file: file,
                    name: file.name,
                    type: file.type,
                    size: file.size
                };
                
                // Add a visual indicator in the input area
                const fileAttachmentIndicator = document.createElement('div');
                fileAttachmentIndicator.className = 'input-file-attachment';
                
                // Remove any existing indicators
                const existingIndicator = document.querySelector('.input-file-attachment');
                if (existingIndicator) {
                    existingIndicator.remove();
                }
                
                // IMPORTANT CHANGE: Always try to upload immediately, even without conversationId
                // Show uploading status in the file attachment indicator
                fileAttachmentIndicator.classList.add('uploading');
                fileAttachmentIndicator.innerHTML = `
                    <i class="fas fa-sync fa-spin"></i>
                    <span>Uploading ${file.name}...</span>
                `;
                
                // Add the indicator to the input area
                inputWrapper.appendChild(fileAttachmentIndicator);
                
                // If no conversation exists yet, create one first via API
                const uploadFile = async () => {
                    try {
                        // Check if we need to create a conversation first
                        if (!conversationId) {
                            console.log('%c CREATING NEW CONVERSATION', 'background: #f90; color: white; font-weight: bold;');
                            
                            // Get CSRF token
                            const csrfToken = getCsrfToken();
                            
                            // Create a new conversation
                            const createResponse = await fetch('/api/conversations/', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': csrfToken,
                                    'X-Requested-With': 'XMLHttpRequest'
                                },
                                body: JSON.stringify({
                                    project_id: currentProjectId || null
                                })
                            });
                            
                            if (!createResponse.ok) {
                                throw new Error('Failed to create conversation');
                            }
                            
                            const conversationData = await createResponse.json();
                            conversationId = conversationData.id;
                            currentConversationId = conversationId;
                            
                            console.log('Created new conversation with ID:', conversationId);
                            
                            // Update URL with conversation ID
                            const url = new URL(window.location);
                            url.searchParams.set('conversation_id', conversationId);
                            window.history.pushState({}, '', url);
                        }
                        
                        // Now upload the file with the conversation ID
                        console.log('%c UPLOADING FILE IMMEDIATELY', 'background: #f50; color: white; font-weight: bold;');
                        console.log('Using conversation ID for upload:', conversationId);
                        
                        const fileResponse = await uploadFileToServer(file, conversationId);
                        console.log('File uploaded immediately after selection, file_id:', fileResponse.id);
                        
                        // Update the indicator to show success
                        fileAttachmentIndicator.classList.remove('uploading');
                        fileAttachmentIndicator.classList.add('uploaded');
                        fileAttachmentIndicator.innerHTML = `
                            <i class="fas fa-check-circle"></i>
                            <span>${file.name}</span>
                            <button type="button" id="remove-file-btn" title="Remove file">
                                <i class="fas fa-times"></i>
                            </button>
                        `;
                        
                        // Store the file with the file_id in a global variable
                        window.attachedFile = {
                            file: file,
                            name: file.name,
                            type: file.type,
                            size: file.size,
                            id: fileResponse.id
                        };
                        
                        console.log('Updated window.attachedFile with file_id:', window.attachedFile);
                        
                        // Add event listener to remove button
                        const removeFileBtn = document.getElementById('remove-file-btn');
                        if (removeFileBtn) {
                            removeFileBtn.addEventListener('click', (e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                window.attachedFile = null;
                                fileAttachmentIndicator.remove();
                            });
                        }
                    } catch (error) {
                        console.error('%c FILE UPLOAD ERROR', 'background: #f00; color: white; font-weight: bold;');
                        console.error('Error details:', error);
                        
                        // Update the indicator to show error
                        fileAttachmentIndicator.classList.remove('uploading');
                        fileAttachmentIndicator.classList.add('error');
                        fileAttachmentIndicator.innerHTML = `
                            <i class="fas fa-exclamation-circle"></i>
                            <span>Error: ${file.name}</span>
                            <button type="button" id="remove-file-btn" title="Remove file">
                                <i class="fas fa-times"></i>
                            </button>
                        `;
                        
                        // Still store the file in a global variable, but without file_id
                        window.attachedFile = fileData;
                        
                        // Add event listener to remove button
                        const removeFileBtn = document.getElementById('remove-file-btn');
                        if (removeFileBtn) {
                            removeFileBtn.addEventListener('click', (e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                window.attachedFile = null;
                                fileAttachmentIndicator.remove();
                            });
                        }
                    }
                };
                
                // Call the upload function immediately
                uploadFile();
                
                // Focus on the input so the user can type their message
                chatInput.focus();
                
                // Clear the file input to allow uploading the same file again
                fileUploadInput.value = '';
                
                // Remove the notification after a short delay
                setTimeout(() => {
                    fileInfo.classList.remove('show');
                    setTimeout(() => fileInfo.remove(), 300);
                }, 3000);
            }
        });
    }
    
    // Audio recording functionality
    const recordAudioBtn = document.getElementById('record-audio-btn');
    let mediaRecorder = null;
    let audioChunks = [];
    let recordingStartTime = null;
    let recordingTimer = null;
    let recordingIndicator = null;
    
    if (recordAudioBtn) {
        recordAudioBtn.addEventListener('click', async () => {
            if (!mediaRecorder || mediaRecorder.state === 'inactive') {
                // Start recording
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];
                    
                    // Create and show waveform indicator
                    recordingIndicator = createRecordingIndicator();
                    const messagesContainer = document.getElementById('chat-messages');
                    messagesContainer.appendChild(recordingIndicator);
                    messagesContainer.scrollTop = messagesContainer.scrollHeight;
                    
                    mediaRecorder.ondataavailable = (event) => {
                        audioChunks.push(event.data);
                    };
                    
                    mediaRecorder.onstop = async () => {
                        // Stop all tracks
                        stream.getTracks().forEach(track => track.stop());
                        
                        // Remove recording indicator
                        if (recordingIndicator) {
                            recordingIndicator.remove();
                            recordingIndicator = null;
                        }
                        
                        // Create audio blob
                        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                        const audioFile = new File([audioBlob], `recording_${Date.now()}.webm`, { type: 'audio/webm' });
                        
                        console.log('Audio recording completed:', audioFile.name, 'size:', audioFile.size);
                        
                        // Send audio message directly
                        await sendAudioMessage(audioFile);
                        
                        // Reset button state
                        recordAudioBtn.classList.remove('recording');
                        recordAudioBtn.innerHTML = '<i class="fas fa-microphone"></i>';
                        
                        // Clear timer
                        if (recordingTimer) {
                            clearInterval(recordingTimer);
                            recordingTimer = null;
                        }
                    };
                    
                    mediaRecorder.start();
                    recordingStartTime = Date.now();
                    
                    // Update button state
                    recordAudioBtn.classList.add('recording');
                    recordAudioBtn.innerHTML = '<i class="fas fa-stop"></i>';
                    
                    // Update timer in waveform indicator
                    recordingTimer = setInterval(() => {
                        const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
                        const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
                        const seconds = (elapsed % 60).toString().padStart(2, '0');
                        
                        if (recordingIndicator) {
                            const timeDisplay = recordingIndicator.querySelector('.recording-time');
                            if (timeDisplay) {
                                timeDisplay.textContent = `${minutes}:${seconds}`;
                            }
                        }
                        
                        // Auto-stop after 5 minutes
                        if (elapsed >= 300) {
                            mediaRecorder.stop();
                        }
                    }, 1000);
                    
                } catch (error) {
                    console.error('Error accessing microphone:', error);
                    alert('Unable to access microphone. Please check your permissions.');
                }
            } else {
                // Stop recording
                mediaRecorder.stop();
            }
        });
    }
    
    // Connection management variables
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    const reconnectDelay = 3000;
    let heartbeatInterval = null;
    let lastHeartbeatResponse = Date.now();
    let connectionMonitorInterval = null;
    
    // Function to connect WebSocket and receive messages
    function connectWebSocket() {
        // Check if already connected
        if (socket && socket.readyState === WebSocket.OPEN) {
            console.log('WebSocket already connected');
            return;
        }
        
        // Determine if we're on HTTPS or HTTP
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/chat/`;

        console.log('Current Project ID:', currentProjectId);
        console.log('URL path:', window.location.pathname);
        console.log('URL params:', window.location.search);
        
        // Add conversation ID and project ID as query parameters if available
        let wsUrlWithParams = wsUrl;
        const urlParams = [];
        
        if (currentConversationId) {
            urlParams.push(`conversation_id=${currentConversationId}`);
        }
        
        if (currentProjectId) {
            urlParams.push(`project_id=${currentProjectId}`);
            console.log('Adding project_id to WebSocket URL:', currentProjectId);
        } else {
            console.warn('No project_id available for WebSocket connection!');
            // Try once more to get project ID from path as a fallback
            const pathProjectId = extractProjectIdFromPath();
            if (pathProjectId) {
                currentProjectId = pathProjectId;
                urlParams.push(`project_id=${currentProjectId}`);
                console.log('Found and added project_id from path:', currentProjectId);
            }
        }
        
        if (urlParams.length > 0) {
            wsUrlWithParams = `${wsUrl}?${urlParams.join('&')}`;
        }
        
        console.log('Connecting to WebSocket:', wsUrlWithParams);
        
        // Close existing socket if it exists
        if (socket) {
            socket.close();
        }
        
        socket = new WebSocket(wsUrlWithParams);
        
        socket.onopen = function(e) {
            console.log('WebSocket connection established');
            isSocketConnected = true;
            reconnectAttempts = 0;  // Reset reconnect attempts
            
            // Show connected status
            showConnectionStatus('connected');
            
            // Start heartbeat monitoring
            startHeartbeat();
            startConnectionMonitor();
            
            // Synchronize state with server
            syncStreamingState();
            
            // Check if we have pending requirements to send
            console.log('Checking pending requirements:', pendingRequirements);
            console.log('Current chat input value:', chatInput ? chatInput.value : 'chatInput not found');
            if (pendingRequirements) {
                setTimeout(() => {
                    console.log('About to send pending requirements:', pendingRequirements);
                    if (typeof sendMessage === 'function') {
                        sendMessage(pendingRequirements);
                        if (chatInput) {
                            chatInput.value = '';
                            chatInput.style.height = 'auto';
                        }
                        pendingRequirements = null; // Clear to avoid re-sending
                    } else {
                        console.error('sendMessage function not available!');
                    }
                }, 500);
            }
            
            // Send any queued messages
            while (messageQueue.length > 0) {
                const queuedMessage = messageQueue.shift();
                socket.send(JSON.stringify(queuedMessage));
            }
            
            // Load any saved draft
            loadDraftMessage();
        };
        
        socket.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            // Log ALL notifications for debugging
            if (data.is_notification || data.notification_type) {
                console.log(`📨 WebSocket notification: type=${data.notification_type}, has_content=${!!data.content_chunk}`);
            }
            
            // AUTOMATIC LOGGING FOR ALL PRD NOTIFICATIONS AT WEBSOCKET LEVEL
            if (data.notification_type === 'prd_stream' || (data.is_notification && data.notification_type === 'prd_stream')) {
                console.log('\n' + '🔴'.repeat(50));
                console.log('🔴🔴🔴 RAW WEBSOCKET PRD MESSAGE RECEIVED! 🔴🔴🔴');
                console.log('🔴 Type:', data.type);
                console.log('🔴 Notification type:', data.notification_type);
                console.log('🔴 Has content_chunk:', 'content_chunk' in data);
                console.log('🔴 Content length:', data.content_chunk ? data.content_chunk.length : 0);
                console.log('🔴 Is complete:', data.is_complete);
                console.log('🔴 FULL RAW DATA:', JSON.stringify(data, null, 2));
                console.log('🔴'.repeat(50) + '\n');
            }
            
            // Handle heartbeat
            if (data.type === 'heartbeat') {
                lastHeartbeatResponse = Date.now();
                // Send acknowledgment
                if (socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({ type: 'heartbeat_ack' }));
                }
                return;
            }
            
            // Enhanced logging for debugging purposes
            console.log('=== WebSocket message received ===');
            console.log('Full data:', JSON.stringify(data, null, 2));
            console.log('data.type:', data.type);
            console.log('data.is_notification:', data.is_notification);
            console.log('Type of is_notification:', typeof data.is_notification);
            console.log('data.notification_type:', data.notification_type);
            console.log('data.early_notification:', data.early_notification);
            console.log('data.function_name:', data.function_name);
            
            // Special handling for notifications - Use the same improved detection logic
            const isNotification = data.is_notification === true || 
                                  data.is_notification === "true" || 
                                  (data.notification_type && data.notification_type !== "");
                                  
            const isEarlyNotification = isNotification && 
                                       (data.early_notification === true || 
                                        data.early_notification === "true");
            
            console.log('Computed isNotification:', isNotification);
            console.log('Computed isEarlyNotification:', isEarlyNotification);
            console.log('=================================');
            
            if (data.type === 'ai_chunk' && isNotification) {
                console.log('%c NOTIFICATION DATA RECEIVED IN WEBSOCKET! ', 'background: #ffa500; color: #000; font-weight: bold; padding: 2px 5px;');
                console.log('Notification data:', data);
                console.log('Is early notification:', isEarlyNotification);
                
                if (isEarlyNotification) {
                    console.log('%c EARLY NOTIFICATION RECEIVED! ', 'background: #ff0000; color: #fff; font-weight: bold; padding: 2px 5px;');
                    console.log('Function name:', data.function_name);
                }
            }
            
            // Log message content for troubleshooting empty messages
            if (data.type === 'ai_chunk' && data.is_final) {
                console.log('Final AI chunk received - conversation saved');
            } else if (data.type === 'ai_chunk' && data.chunk === '') {
                console.log('Empty AI chunk received - this may be a typing indicator');
            } else if (data.type === 'message' && (!data.message || data.message.trim() === '')) {
                console.warn('Empty message content received in message event:', data);
            }
            
            switch (data.type) {
                case 'chat_history':
                    // Handle chat history
                    clearChatMessages();
                    data.messages.forEach(msg => {
                        // Handle audio messages
                        if (msg.audio_file) {
                            // Create audio indicator for historical audio messages
                            const audioIndicator = document.createElement('div');
                            audioIndicator.className = 'message-audio';
                            audioIndicator.innerHTML = `
                                <div class="message-audio-container">
                                    <div class="message-audio-header">
                                        <i class="fas fa-microphone" style="font-size: 14px;"></i>
                                        Voice message
                                    </div>
                                    ${msg.audio_file.transcription ? `
                                        <div class="audio-transcription">
                                            ${msg.audio_file.transcription}
                                        </div>
                                    ` : ''}
                                </div>
                            `;
                            // For audio messages, don't pass content since transcription is in the indicator
                            addMessageToChat(msg.role, '', { audioIndicator: audioIndicator });
                        } else if (msg.content && msg.content.trim() !== '') {
                            // Regular text messages
                            addMessageToChat(msg.role, msg.content, null, null, msg.is_partial);
                        }
                    });
                    scrollToBottom();
                    break;
                    
                case 'message':
                    // Handle complete message
                    addMessageToChat(data.sender, data.message);
                    scrollToBottom();
                    break;
                    
                case 'ai_chunk':
                    // Handle AI response chunk for streaming
                    // Skip entirely empty chunks that aren't typing indicators or final messages
                    // BUT don't skip notifications!
                    if (data.chunk === '' && !data.is_final && document.querySelector('.message.assistant:last-child') && !data.is_notification) {
                        console.log('Skipping empty non-final chunk...');
                        break;
                    }
                    
                    handleAIChunk(data);
                    break;
                
                case 'tool_progress':
                    // Handle tool progress updates
                    handleToolProgress(data);
                    break;
                
                case 'stop_confirmed':
                    // Handle confirmation that generation was stopped
                    console.log('Generation stopped by server');
                    
                    // If the user has already processed the stop locally, don't do anything
                    if (!stopRequested) {
                        // Remove typing indicator if it exists
                        const typingIndicator = document.querySelector('.typing-indicator');
                        if (typingIndicator) {
                            typingIndicator.remove();
                        }
                        
                        // Check if there's an assistant message, if not add one
                        const assistantMessage = document.querySelector('.message.assistant:last-child');
                        if (!assistantMessage) {
                            // No message was created yet, so create one with the stopped message
                            addMessageToChat('system', '*Generation stopped by server*');
                        }
                        
                        // Re-enable input and restore send button
                        chatInput.disabled = false;
                        hideStopButton();
                    }
                    
                    // Reset the flag
                    stopRequested = false;
                    break;
                    
                case 'heartbeat':
                    // Handle heartbeat - acknowledge it
                    lastHeartbeatResponse = Date.now();
                    socket.send(JSON.stringify({ type: 'heartbeat_ack' }));
                    
                    // Check if this is a heartbeat during operation
                    if (data.during_operation) {
                        console.log('Heartbeat during operation received - connection is alive');
                    }
                    break;
                    
                case 'sync_state_response':
                    // Handle state synchronization response
                    console.log('Received sync state response:', data);
                    
                    if (data.is_streaming) {
                        // Server says it's streaming but client isn't aware
                        if (!isStreaming) {
                            console.log('Server is streaming but client was unaware - updating UI');
                            isStreaming = true;
                            chatInput.disabled = true;
                            showStopButton();
                        }
                    } else {
                        // Server says it's not streaming
                        if (isStreaming) {
                            console.log('Client thought it was streaming but server says no - resetting UI');
                            resetStreamingState();
                        }
                    }
                    break;
                    
                case 'error':
                    console.error('WebSocket error:', data.message);
                    // Display error message to user
                    const errorMsg = document.createElement('div');
                    errorMsg.className = 'error-message';
                    errorMsg.textContent = data.message;
                    messageContainer.appendChild(errorMsg);
                    scrollToBottom();
                    
                    // In case of error, restore UI
                    chatInput.disabled = false;
                    hideStopButton();
                    break;
                    
                case 'token_usage_updated':
                    // Update the daily token usage display
                    if (window.updateDailyTokens) {
                        window.updateDailyTokens();
                    }
                    break;
                    
                default:
                    console.log('Unknown message type:', data.type);
            }
        };
        
        socket.onclose = function(event) {
            stopHeartbeat();
            stopConnectionMonitor();
            isSocketConnected = false;
            
            // If we were streaming when connection was lost, reset the UI state
            if (isStreaming) {
                console.log('Connection lost while streaming, resetting UI state');
                resetStreamingState();
            }
            
            if (event.wasClean) {
                console.log(`WebSocket connection closed cleanly, code=${event.code}, reason=${event.reason}`);
            } else {
                console.error('WebSocket connection died');
                
                // Save current input as draft
                if (chatInput.value.trim()) {
                    saveDraftMessage(chatInput.value);
                }
                
                // Show connection lost indicator
                showConnectionStatus('disconnected');
                
                // Attempt to reconnect with exponential backoff
                if (reconnectAttempts < maxReconnectAttempts) {
                    const delay = reconnectDelay * Math.pow(1.5, reconnectAttempts);
                    reconnectAttempts++;
                    
                    console.log(`Attempting to reconnect (attempt ${reconnectAttempts}/${maxReconnectAttempts}) in ${delay}ms...`);
                    showConnectionStatus('reconnecting', reconnectAttempts, maxReconnectAttempts);
                    
                    setTimeout(() => {
                        connectWebSocket();
                    }, delay);
                } else {
                    showConnectionStatus('failed');
                    console.error('Max reconnection attempts reached');
                }
            }
        };
        
        socket.onerror = function(error) {
            console.error('WebSocket error:', error);
            isSocketConnected = false;
        };
    }
    
    // Function to handle AI response chunks
    function handleAIChunk(data) {
        // Handle chunked messages first
        if (data.is_chunked) {
            console.log(`Received chunk ${data.chunk_sequence}/${data.total_chunks} for sequence ${data.sequence}`);
            
            // Initialize buffer for this sequence if needed
            if (!chunkBuffers[data.sequence]) {
                chunkBuffers[data.sequence] = {
                    chunks: {},
                    totalChunks: data.total_chunks,
                    receivedChunks: 0
                };
            }
            
            // Store the chunk
            chunkBuffers[data.sequence].chunks[data.chunk_sequence] = data.chunk;
            chunkBuffers[data.sequence].receivedChunks++;
            
            // Check if we have all chunks
            if (chunkBuffers[data.sequence].receivedChunks === data.total_chunks) {
                // Reassemble the message
                let fullContent = '';
                for (let i = 0; i < data.total_chunks; i++) {
                    fullContent += chunkBuffers[data.sequence].chunks[i] || '';
                }
                
                // Clean up the buffer
                delete chunkBuffers[data.sequence];
                
                // Process the reassembled message
                data.chunk = fullContent;
                data.is_chunked = false;
                console.log('Reassembled full message:', fullContent.length, 'characters');
            } else {
                // Still waiting for more chunks
                console.log(`Waiting for ${data.total_chunks - chunkBuffers[data.sequence].receivedChunks} more chunks`);
                return;
            }
        }
        
        // Handle sequence validation
        if (data.sequence !== undefined) {
            if (data.sequence < expectedSequence) {
                console.warn(`Received old sequence ${data.sequence}, expected ${expectedSequence}. Ignoring.`);
                return;
            } else if (data.sequence > expectedSequence) {
                console.warn(`Received future sequence ${data.sequence}, expected ${expectedSequence}. Messages may be out of order.`);
            }
            expectedSequence = data.sequence + 1;
        }
        
        const chunk = data.chunk;
        const isFinal = data.is_final;
        
        // Add explicit debug for notification property
        console.log('\n=== handleAIChunk Debug ===');
        console.log('Full data object:', JSON.stringify(data, null, 2));
        console.log('chunk:', chunk);
        console.log('is_final:', isFinal);
        console.log('is_notification:', data.is_notification);
        console.log('notification_type:', data.notification_type);
        console.log('early_notification:', data.early_notification);
        console.log('function_name:', data.function_name);
        console.log('===========================\n');
        
        // AUTOMATIC PRD CONSOLE LOGGING
        if (data.notification_type === 'prd_stream') {
            console.log('\n' + '🎯'.repeat(50));
            console.log('🎯🎯🎯 PRD STREAM CONTENT RECEIVED IN BROWSER! 🎯🎯🎯');
            console.log('🎯 Has content_chunk:', 'content_chunk' in data);
            console.log('🎯 Content length:', data.content_chunk ? data.content_chunk.length : 0);
            console.log('🎯 Is complete:', data.is_complete);
            console.log('🎯 PRD CONTENT:');
            console.log('---START OF PRD CHUNK---');
            console.log(data.content_chunk || '[NO CONTENT]');
            console.log('---END OF PRD CHUNK---');
            console.log('🎯'.repeat(50) + '\n');
            
            // Store in global variable for easy access
            if (!window.PRD_STREAM_CONTENT) {
                window.PRD_STREAM_CONTENT = '';
            }
            if (!window.PRD_STREAM_CHUNKS) {
                window.PRD_STREAM_CHUNKS = [];
            }
            if (data.content_chunk) {
                window.PRD_STREAM_CONTENT += data.content_chunk;
                window.PRD_STREAM_CHUNKS.push({
                    timestamp: new Date().toISOString(),
                    length: data.content_chunk.length,
                    content: data.content_chunk,
                    is_complete: data.is_complete
                });
            }
            console.log('🎯 Total PRD content so far:', window.PRD_STREAM_CONTENT.length, 'chars');
            console.log('🎯 Total chunks received:', window.PRD_STREAM_CHUNKS.length);
            console.log('🎯 Access full content: window.PRD_STREAM_CONTENT');
            console.log('🎯 Access all chunks: window.PRD_STREAM_CHUNKS');
        }
        
        // AUTOMATIC IMPLEMENTATION CONSOLE LOGGING
        if (data.notification_type === 'implementation_stream') {
            console.log('\n' + '💚'.repeat(50));
            console.log('💚💚💚 IMPLEMENTATION STREAM CONTENT RECEIVED IN BROWSER! 💚💚💚');
            console.log('💚 Has content_chunk:', 'content_chunk' in data);
            console.log('💚 Content length:', data.content_chunk ? data.content_chunk.length : 0);
            console.log('💚 Is complete:', data.is_complete);
            console.log('💚 IMPLEMENTATION CONTENT:');
            console.log('---START OF IMPLEMENTATION CHUNK---');
            console.log(data.content_chunk || '[NO CONTENT]');
            console.log('---END OF IMPLEMENTATION CHUNK---');
            console.log('💚'.repeat(50) + '\n');
            
            // Store in global variable for easy access
            if (!window.IMPLEMENTATION_STREAM_CONTENT) {
                window.IMPLEMENTATION_STREAM_CONTENT = '';
            }
            if (!window.IMPLEMENTATION_STREAM_CHUNKS) {
                window.IMPLEMENTATION_STREAM_CHUNKS = [];
            }
            if (data.content_chunk) {
                window.IMPLEMENTATION_STREAM_CONTENT += data.content_chunk;
                window.IMPLEMENTATION_STREAM_CHUNKS.push({
                    timestamp: new Date().toISOString(),
                    length: data.content_chunk.length,
                    content: data.content_chunk,
                    is_complete: data.is_complete
                });
            }
            console.log('💚 Total Implementation content so far:', window.IMPLEMENTATION_STREAM_CONTENT.length, 'chars');
            console.log('💚 Total chunks received:', window.IMPLEMENTATION_STREAM_CHUNKS.length);
            console.log('💚 Access full content: window.IMPLEMENTATION_STREAM_CONTENT');
            console.log('💚 Access all chunks: window.IMPLEMENTATION_STREAM_CHUNKS');
        }
        
        // Fix notification detection by checking for either boolean true, string "true", or existence of notification_type
        // This handles cases where is_notification is undefined but we still want to process regular chunks
        const isNotification = data.is_notification === true || 
                              data.is_notification === "true" || 
                              (data.notification_type && data.notification_type !== "");
                              
        // Check if this is an early notification
        const isEarlyNotification = isNotification && 
                                   (data.early_notification === true || 
                                    data.early_notification === "true");
        
        // Skip debug logging for non-notification messages to reduce noise
        if (isNotification || data.is_notification !== undefined || data.notification_type !== undefined) {
            // Add additional debugging to see the entire data structure
            console.log("Received AI chunk data:", data);
            console.log("Is Notification (after fix):", isNotification);
            console.log("Is Early Notification:", isEarlyNotification);
            console.log("Function name (if early):", data.function_name || "none");
        }
        
        if (isFinal) {
            // Final chunk with metadata
            console.log('AI response complete');
            
            // Skip creating a message if it's empty (likely just the final signal after a stop)
            if (chunk === '' && document.querySelector('.message.system:last-child')) {
                console.log('Skipping empty final chunk after stopped generation');
            }
            
            // Update conversation ID and other metadata if provided
            if (data.conversation_id) {
                currentConversationId = data.conversation_id;
                
                // Update URL with conversation ID
                const url = new URL(window.location);
                url.searchParams.set('conversation_id', currentConversationId);
                window.history.pushState({}, '', url);
            }
            
            if (data.provider) {
                currentProvider = data.provider;
            }
            
            if (data.project_id) {
                currentProjectId = data.project_id;
            }
            
            // Check if this is the final chunk
            if (data.is_final) {
                // Streaming is complete
                isStreaming = false;
                
                // Re-enable the input
                chatInput.disabled = false;
                chatInput.focus();
                
                // Restore send button
                hideStopButton();
                
                // Reset the stop requested flag
                stopRequested = false;
            }
            
            // Reload the conversations list to include the new one
            if (data.conversation_id) {
                loadConversations();
            }
            
            // Only return if this is the final chunk
            if (data.is_final) {
                return;
            }
        }
        
        // Handle early notifications (show a function call indicator but don't open artifacts yet)
        if (isEarlyNotification && data.function_name) {
            console.log('\n\n==========================================');
            console.log('EARLY NOTIFICATION RECEIVED:');
            console.log('Function name early notification:', data.function_name);
            console.log('Notification type:', data.notification_type);
            
            // List of read operations that should NOT open the panel
            const readOperations = [
                'get_features',
                'get_personas',
                'get_prd',
                'get_implementation',
                'get_next_ticket',
                'get_pending_tickets',
                'get_project_name'
            ];
            
            // Only process if it's not a read operation
            
            console.log('Is early notification:', data.early_notification);
            console.log('==========================================\n\n');
            
            // Remove any previous function call indicators
            removeFunctionCallIndicator();
            
            // Show function call indicator for the function
            const indicator = showFunctionCallIndicator(data.function_name);
            console.log('Function call indicator created:', indicator);
            
            // Also show the tool progress indicator immediately for supported functions
            if (['extract_features', 'extract_personas'].includes(data.function_name)) {
                handleToolProgress({
                    tool_name: data.function_name,
                    message: `Starting ${data.function_name.replace('_', ' ')}...`,
                    progress_percentage: 0
                });
            }
            
            
            scrollToBottom();
            
            return;
        }
        
        // Handle regular (completion) notifications
        if (isNotification && !isEarlyNotification) {
            console.log('\n\n==========================================');
            console.log('COMPLETION NOTIFICATION RECEIVED - DETAILED DEBUG INFO:');
            console.log('Full data object:', data);
            console.log('Notification type:', data.notification_type);
            console.log('Current project ID:', currentProjectId);
            console.log('==========================================\n\n');
            
            // Show a function call indicator in the UI for the function that generated this notification
            const functionName = data.notification_type === 'features' ? 'extract_features' : 
                               data.notification_type === 'personas' ? 'extract_personas' : 
                               data.notification_type === 'execute_command' ? 'execute_command' : 
                               data.notification_type === 'command_output' ? 'execute_command' : 
                               data.notification_type === 'start_server' ? 'start_server' : 
                               data.notification_type === 'implementation' ? 'save_implementation' : 
                               data.notification_type === 'prd' ? 'create_prd' :
                               data.notification_type === 'prd_stream' ? 'stream_prd_content' :
                               data.notification_type === 'design' ? 'design_schema' :
                               data.notification_type === 'tickets' ? 'generate_tickets' :
                               data.notification_type === 'checklist' ? 'checklist_tickets' :
                               data.function_name || data.notification_type;
            
            // Remove any previous function call indicators
            removeFunctionCallIndicator();
            
            // Remove tool execution indicator
            const toolExecutionIndicator = document.querySelector('.tool-execution-indicator');
            if (toolExecutionIndicator) {
                toolExecutionIndicator.remove();
            }
            
            
            // Check if we have a valid project ID from somewhere
            if (!currentProjectId) {
                // Try to get project ID from URL first
                const urlParams = new URLSearchParams(window.location.search);
                const urlProjectId = urlParams.get('project_id');
                
                // Then try from path (format: /chat/project/{id}/)
                const pathProjectId = extractProjectIdFromPath();
                
                if (urlProjectId) {
                    console.log(`Using project ID from URL: ${urlProjectId}`);
                    currentProjectId = urlProjectId;
                } else if (pathProjectId) {
                    console.log(`Using project ID from path: ${pathProjectId}`);
                    currentProjectId = pathProjectId;
                }
            }
            
            // If still no project ID, we can't proceed with loading artifacts
            if (!currentProjectId) {
                console.error('Unable to determine project ID for notification! Cannot load artifacts.');
                // Try to at least open the panel even if we can't load content
                if (window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function') {
                    console.log('Opening artifacts panel with forceOpen=true');
                    try {
                        window.ArtifactsPanel.toggle(true); // Use forceOpen parameter to ensure it opens
                        console.log('ArtifactsPanel.toggle called successfully');
                        
                        // Double check if panel is actually open now
                        const panel = document.getElementById('artifacts-panel');
                        if (panel) {
                            console.log('Panel element found, expanded status:', panel.classList.contains('expanded'));
                            if (!panel.classList.contains('expanded')) {
                                console.log('Panel still not expanded after toggle, forcing expanded class');
                                panel.classList.add('expanded');
                                document.querySelector('.app-container')?.classList.add('artifacts-expanded');
                                document.getElementById('artifacts-button')?.classList.add('active');
                            }
                        } else {
                            console.error('Could not find artifacts-panel element in DOM');
                        }
                    } catch (err) {
                        console.error('Error toggling artifacts panel:', err);
                    }
                } else {
                    console.error('ArtifactsPanel not available!', window.ArtifactsPanel);
                }
                return;
            }
            
            console.log('\n\nArtifacts Panel Status:');
            console.log('ArtifactsPanel available:', !!window.ArtifactsPanel);
            console.log('Toggle function available:', !!(window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function'));
            
            // Make sure artifacts panel is visible
            let panelOpenSuccess = false;
            
            // For PRD and Implementation streaming, we should open the artifacts panel
            if (data.notification_type === 'prd_stream' || data.notification_type === 'implementation_stream') {
                console.log(`${data.notification_type} detected - checking if artifacts panel is open`);
                
                // Check if panel is already open
                const panel = document.getElementById('artifacts-panel');
                const isPanelOpen = panel && panel.classList.contains('expanded');
                
                if (!isPanelOpen) {
                    console.log('Panel is not open, opening it now');
                    // Try multiple methods to ensure panel opens
                    if (window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function') {
                        console.log('Opening artifacts panel using ArtifactsPanel.toggle');
                        try {
                            window.ArtifactsPanel.toggle(true); // Force open
                            panelOpenSuccess = true;
                        } catch (err) {
                            console.error('Error opening artifacts panel for stream:', err);
                        }
                    }
                    
                    // Also try direct DOM manipulation as backup
                    if (!panelOpenSuccess) {
                        console.log('Trying direct DOM manipulation to open panel');
                        const appContainer = document.querySelector('.app-container');
                        const button = document.getElementById('artifacts-button');
                        
                        if (panel) {
                            panel.classList.add('expanded');
                            if (appContainer) appContainer.classList.add('artifacts-expanded');
                            if (button) button.classList.add('active');
                            panelOpenSuccess = true;
                            console.log('Panel opened via direct DOM manipulation');
                        }
                    }
                } else {
                    console.log('Panel is already open, skipping toggle to prevent reload');
                    panelOpenSuccess = true;
                }
            }

            // Update logic to pop open the artifacts panel when needed
            
            // if (window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function') {
            //     console.log('Opening artifacts panel with ArtifactsPanel.toggle');
            //     try {
            //         window.ArtifactsPanel.toggle(true); // Use forceOpen parameter to ensure it opens
            //         console.log('ArtifactsPanel.toggle called successfully');
                    
            //         // Double check if panel is actually open now
            //         const panel = document.getElementById('artifacts-panel');
            //         if (panel) {
            //             console.log('Panel element found, expanded status:', panel.classList.contains('expanded'));
            //             panelOpenSuccess = panel.classList.contains('expanded');
                        
            //             if (!panelOpenSuccess) {
            //                 console.log('Panel still not expanded after toggle, adding expanded class directly');
            //                 panel.classList.add('expanded');
            //                 document.querySelector('.app-container')?.classList.add('artifacts-expanded');
            //                 document.getElementById('artifacts-button')?.classList.add('active');
            //                 panelOpenSuccess = true;
            //             }
            //         } else {
            //             console.error('Could not find artifacts-panel element in DOM');
            //         }
            //     } catch (err) {
            //         console.error('Error toggling artifacts panel:', err);
            //     }
            // } else {
            //     console.error('ArtifactsPanel not available!', window.ArtifactsPanel);
            // }
            
            // If the panel still isn't open, try the direct approach
            // if (!panelOpenSuccess && window.forceOpenArtifactsPanel) {
            //     console.log('Using forceOpenArtifactsPanel as fallback');
            //     window.forceOpenArtifactsPanel(data.notification_type);
            //     panelOpenSuccess = true;
            // }
            
            // Last resort - direct DOM manipulation if all else fails
            // if (!panelOpenSuccess) {
            //     console.log('Attempting direct DOM manipulation to open panel');
            //     try {
            //         // Try to manipulate DOM directly
            //         const panel = document.getElementById('artifacts-panel');
            //         const appContainer = document.querySelector('.app-container');
            //         const button = document.getElementById('artifacts-button');
                    
            //         if (panel && appContainer) {
            //             panel.classList.add('expanded');
            //             appContainer.classList.add('artifacts-expanded');
            //             if (button) button.classList.add('active');
            //             console.log('Panel forced open with direct DOM manipulation');
            //             panelOpenSuccess = true;
            //         }
            //     } catch (e) {
            //         console.error('Error in direct DOM manipulation:', e);
            //     }
            // }
            
            console.log('\n\nTab Switching Status:');
            console.log('switchTab available:', !!window.switchTab);
            console.log('notification_type available:', !!data.notification_type);
            
            // Switch to the appropriate tab
            if (window.switchTab && data.notification_type) {
                console.log(`Switching to tab: ${data.notification_type}`);
                
                // Map non-existent tabs to existing ones
                const tabMapping = {
                    // 'features': 'checklist',
                    // 'personas': 'checklist',
                    'design': 'implementation',
                    'tickets': 'checklist',
                    // 'execute_command': 'toolhistory',
                    // 'command_output': 'toolhistory',
                    'start_server': 'apps',
                    // 'get_pending_tickets': 'checklist',
                    'create_checklist_tickets': 'checklist',
                    'implement_ticket': 'implementation',
                    'prd_stream': 'prd',  // Map prd_stream to prd tab
                    'implementation_stream': 'implementation'  // Map implementation_stream to implementation tab
                };
                
                // Use mapped tab if original doesn't exist
                const targetTab = tabMapping[data.notification_type] || data.notification_type;
                
                // Check if we're already on the target tab to avoid redundant switching during streaming
                const currentActiveTab = document.querySelector('.tab-button.active')?.getAttribute('data-tab');
                const isStreamingNotification = data.notification_type === 'prd_stream' || data.notification_type === 'implementation_stream';
                
                // Only switch tabs if we're not already on the target tab, or if it's not a streaming notification
                if (currentActiveTab !== targetTab || !isStreamingNotification) {
                    // Try the standard tab switching first
                    try {
                        window.switchTab(targetTab);
                        console.log(`Tab switched successfully to ${targetTab} using window.switchTab`);
                    } catch (err) {
                        console.error(`Error switching tab to ${targetTab} with window.switchTab:`, err);
                        
                        // Try direct DOM manipulation as fallback
                        try {
                            const tabButtons = document.querySelectorAll('.tab-button');
                            const tabPanes = document.querySelectorAll('.tab-pane');
                            
                            // Find the right tab using the mapped target
                            const targetButton = document.querySelector(`.tab-button[data-tab="${targetTab}"]`);
                            const targetPane = document.getElementById(targetTab);
                            
                            if (targetButton && targetPane) {
                                // Remove active class from all tabs
                                tabButtons.forEach(btn => btn.classList.remove('active'));
                                tabPanes.forEach(pane => pane.classList.remove('active'));
                                
                                // Set active class on the target tab
                                targetButton.classList.add('active');
                                targetPane.classList.add('active');
                                console.log(`Tab switched successfully to ${targetTab} using direct DOM manipulation`);
                            } else {
                                console.error(`Could not find tab elements for ${targetTab} (original: ${data.notification_type})`);
                            }
                        } catch (domErr) {
                            console.error('Error switching tab with direct DOM manipulation:', domErr);
                        }
                    }
                } else {
                    console.log(`Already on ${targetTab} tab during streaming, skipping tab switch`);
                }
                
                // Load the content for that tab if we have a project ID
                console.log(`Current project ID for loading: ${currentProjectId}`);
                
                console.log('\n\nLoader Status:');
                console.log('ArtifactsLoader available:', !!window.ArtifactsLoader);
                console.log(`loadFeatures function available:`, !!(window.ArtifactsLoader && typeof window.ArtifactsLoader.loadFeatures === 'function'));
                console.log(`loadPersonas function available:`, !!(window.ArtifactsLoader && typeof window.ArtifactsLoader.loadPersonas === 'function'));
                console.log(`loadPRD function available:`, !!(window.ArtifactsLoader && typeof window.ArtifactsLoader.loadPRD === 'function'));
                
                // Load the appropriate content based on notification type
                if (window.ArtifactsLoader && currentProjectId) {
                    // Special handling for PRD streaming
                    if (data.notification_type === 'prd_stream') {
                        console.log('PRD stream notification detected');
                        console.log('Full notification data:', data);
                        console.log('Content chunk exists:', data.content_chunk !== undefined);
                        console.log('Content chunk value:', data.content_chunk);
                        console.log('Is complete:', data.is_complete);
                        
                        // CONSOLE STREAMING OUTPUT
                        console.log('\n' + '='.repeat(80));
                        console.log('🔵 PRD STREAM RECEIVED IN BROWSER');
                        console.log(`📅 Time: ${new Date().toISOString()}`);
                        console.log(`📏 Length: ${data.content_chunk ? data.content_chunk.length : 0} chars`);
                        console.log(`✅ Complete: ${data.is_complete}`);
                        if (data.content_chunk) {
                            console.log(`📝 Content: ${data.content_chunk.substring(0, 200)}${data.content_chunk.length > 200 ? '...' : ''}`);
                        }
                        console.log('='.repeat(80) + '\n');
                        
                        if (data.content_chunk !== undefined) {
                            console.log(`Streaming PRD chunk: ${data.content_chunk.substring(0, 50)}...`);
                            console.log('Current project ID:', currentProjectId);
                            // Ensure we have a project ID for streaming
                            let projectIdForStreaming = currentProjectId;
                            if (!projectIdForStreaming) {
                                // Try to get it from various sources
                                const urlParams = new URLSearchParams(window.location.search);
                                projectIdForStreaming = urlParams.get('project_id') || 
                                                       extractProjectIdFromPath() || 
                                                       data.project_id;
                                console.log(`PRD Streaming: Using project ID: ${projectIdForStreaming}`);
                            }
                            
                            if (projectIdForStreaming) {
                                console.log('Streaming PRD content with project ID:', projectIdForStreaming);
                                window.ArtifactsLoader.streamPRDContent(
                                    data.content_chunk, 
                                    data.is_complete || false, 
                                    projectIdForStreaming,
                                    data.prd_name || 'Main PRD'
                                );
                            } else {
                                console.error('PRD stream: No project ID available for streaming!');
                            }
                        } else {
                            console.error('PRD stream notification missing content_chunk!');
                        }
                    } else if (data.notification_type === 'implementation_stream') {
                        // Special handling for Implementation streaming
                        console.log('Implementation stream notification detected');
                        console.log('Full notification data:', data);
                        console.log('Content chunk exists:', data.content_chunk !== undefined);
                        console.log('Content chunk value:', data.content_chunk);
                        console.log('Is complete:', data.is_complete);
                        
                        // CONSOLE STREAMING OUTPUT
                        console.log('\n' + '='.repeat(80));
                        console.log('🟢 IMPLEMENTATION STREAM RECEIVED IN BROWSER');
                        console.log(`📅 Time: ${new Date().toISOString()}`);
                        console.log(`📏 Length: ${data.content_chunk ? data.content_chunk.length : 0} chars`);
                        console.log(`✅ Complete: ${data.is_complete}`);
                        if (data.content_chunk) {
                            console.log(`📝 Content: ${data.content_chunk.substring(0, 200)}${data.content_chunk.length > 200 ? '...' : ''}`);
                        }
                        console.log('='.repeat(80) + '\n');
                        
                        if (data.content_chunk !== undefined) {
                            console.log(`Streaming Implementation chunk: ${data.content_chunk.substring(0, 50)}...`);
                            console.log('Current project ID:', currentProjectId);
                            // Ensure we have a project ID for streaming
                            let projectIdForStreaming = currentProjectId;
                            if (!projectIdForStreaming) {
                                // Try to get it from various sources
                                const urlParams = new URLSearchParams(window.location.search);
                                projectIdForStreaming = urlParams.get('project_id') || 
                                                       extractProjectIdFromPath() || 
                                                       data.project_id;
                                console.log(`Implementation Streaming: Using project ID: ${projectIdForStreaming}`);
                            }
                            
                            if (projectIdForStreaming) {
                                console.log('Streaming Implementation content with project ID:', projectIdForStreaming);
                                window.ArtifactsLoader.streamImplementationContent(
                                    data.content_chunk, 
                                    data.is_complete || false, 
                                    projectIdForStreaming
                                );
                            } else {
                                console.error('Implementation stream: No project ID available for streaming!');
                            }
                        } else {
                            console.error('Implementation stream notification missing content_chunk!');
                        }
                    } else {
                        const loaderMap = {
                            'features': 'loadFeatures',
                            'personas': 'loadPersonas',
                            'prd': 'loadPRD',
                            'implementation': 'loadImplementation',
                            'design': 'loadDesignSchema',
                            'tickets': 'loadTickets',
                            'checklist': 'loadChecklist'
                        };
                        
                        const loaderMethod = loaderMap[data.notification_type];
                        if (loaderMethod && typeof window.ArtifactsLoader[loaderMethod] === 'function') {
                            console.log(`Calling ArtifactsLoader.${loaderMethod}(${currentProjectId})`);
                            window.ArtifactsLoader[loaderMethod](currentProjectId);
                        } else if (data.notification_type === 'command_output' || 
                                  data.notification_type === 'execute_command' ||
                                  data.notification_type === 'start_server' ||
                                  data.notification_type === 'implement_ticket') {
                            // These notification types don't have corresponding tabs/loaders
                            console.log(`Notification type '${data.notification_type}' doesn't require tab loading`);
                        } else {
                            console.log(`No loader method found for notification type: ${data.notification_type}`);
                        }
                    }
                }
            } else {
                console.error(`switchTab not available or no notification_type provided!`);
            }
            console.log('==========================================\n\n');
            return;
        }
        
        if (!chunk) {
            // This is just a typing indicator
            const typingIndicator = document.querySelector('.typing-indicator');
            if (!typingIndicator) {
                const indicator = document.createElement('div');
                indicator.className = 'typing-indicator';
                indicator.innerHTML = '<span></span><span></span><span></span>';
                messageContainer.appendChild(indicator);
                scrollToBottom();
            }
            return;
        }
        
        // Check for function call mentions in text
        checkForFunctionCall(chunk);
        
        // Get or create the assistant message
        const assistantMessage = document.querySelector('.message.assistant:last-child');
        if (assistantMessage) {
            // Add to existing message
            const existingContent = assistantMessage.querySelector('.message-content');
            const currentContent = existingContent.getAttribute('data-raw-content') || '';
            const newContent = currentContent + chunk;
            
            // Store raw content and render with markdown
            existingContent.setAttribute('data-raw-content', newContent);
            existingContent.innerHTML = marked.parse(newContent);
            
            // // Quick trigger for common tool call indicators
            // const quickTriggers = [
            //     'I\'ll use', 'I will use', 'Let me use', 'I\'ll call', 'Let me call',
            //     'I\'ll execute', 'Let me execute', 'I\'ll run', 'Let me run',
            //     'Using the', 'Calling the', 'Executing', 'Running'
            // ];
            
            // const lowerChunk = chunk.toLowerCase();
            // const shouldQuickTrigger = quickTriggers.some(trigger => lowerChunk.includes(trigger.toLowerCase()));
            
            // if (shouldQuickTrigger && !document.querySelector('.tool-execution-indicator')) {
            //     console.log('Quick trigger activated - showing tool animation');
            //     // Show a generic tool execution indicator immediately
            //     window.showToolExecutionIndicator('Processing...');
            // }
            
            // Check if this chunk mentions any tool/function calls
            const toolFunctions = [
                'extract_features', 'extract_personas', 'get_features', 'get_personas',
                'save_implementation', 'execute_command', 'start_server', 'create_implementation',
                'update_implementation', 'get_implementation', 'save_prd', 'get_prd'
            ];
            
            // More aggressive detection - check if any function name appears
            let detectedFunction = null;
            for (const func of toolFunctions) {
                if (newContent.includes(func) || chunk.includes(func)) {
                    detectedFunction = func;
                    console.log(`Tool function "${func}" detected in chunk`);
                    break;
                }
            }
            
            // Also check for common patterns that indicate a function is being called
            const functionPatterns = [
                /I'll (?:now )?(?:use|call|execute|run) (?:the )?(\w+)/i,
                /(?:Using|Calling|Executing|Running) (?:the )?(\w+) (?:function|tool|command)?/i,
                /Let me (?:use|call|execute|run) (?:the )?(\w+)/i,
                /I (?:will|am going to) (?:use|call|execute|run) (?:the )?(\w+)/i,
                /(?:extract|save|get|create|update)_(?:features|personas|implementation|prd)/i,
                /(?:execute)_command/i,
                /(?:start)_server/i
            ];
            
            for (const pattern of functionPatterns) {
                const match = chunk.match(pattern) || newContent.match(pattern);
                if (match) {
                    // Check if it's a direct function name match or if match[1] exists
                    const funcName = match[1] || match[0];
                    const normalizedFunc = funcName.toLowerCase().replace(/-/g, '_');
                    
                    // Check if this matches any known tool
                    for (const tool of toolFunctions) {
                        if (tool === normalizedFunc || funcName.includes(tool)) {
                            detectedFunction = tool;
                            console.log(`Tool function "${tool}" detected via pattern: ${pattern}`);
                            break;
                        }
                    }
                    
                    if (detectedFunction) break;
                }
            }
            
            if (detectedFunction && !document.querySelector('.function-call-indicator') && !document.querySelector('.tool-execution-indicator')) {
                console.log('Function call detected in text:', detectedFunction);
                
                // Show the prominent tool execution indicator
                // window.showToolExecutionIndicator(detectedFunction);
                
                // Also show the function call indicator
                showFunctionCallIndicator(detectedFunction);
                
                // For extract_features and extract_personas, also show progress
                if (['extract_features', 'extract_personas'].includes(detectedFunction)) {
                    setTimeout(() => {
                        handleToolProgress({
                            tool_name: detectedFunction,
                            message: `Preparing to ${detectedFunction.replace('_', ' ')}...`,
                            progress_percentage: 0
                        });
                    }, 500);
                }
                
                // Add a visual "calling function" separator
                const separator = document.createElement('div');
                separator.className = 'function-call-separator';
                separator.innerHTML = `<div class="separator-line"></div>
                                      <div class="separator-text">Calling function: ${detectedFunction}</div>
                                      <div class="separator-line"></div>`;
                messageContainer.appendChild(separator);
                scrollToBottom();
            }
        } else {
            // Remove typing indicator if present
            const typingIndicator = document.querySelector('.typing-indicator');
            if (typingIndicator) {
                typingIndicator.remove();
            }
            
            // Create new message
            addMessageToChat('assistant', chunk);
        }
        
        scrollToBottom();
    }
    
    // Function to create message container if it doesn't exist
    function createMessageContainer() {
        const container = document.createElement('div');
        container.className = 'message-container';
        chatMessages.appendChild(container);
        return container;
    }
    
    // Function to create send button if it doesn't exist
    function createSendButton() {
        const btn = document.createElement('button');
        btn.id = 'send-btn';
        btn.type = 'submit';
        btn.className = 'action-btn';
        btn.innerHTML = '<i class="fas fa-paper-plane"></i>';
        btn.title = 'Send message';
        
        const inputActions = document.querySelector('.input-actions');
        if (inputActions) {
            inputActions.appendChild(btn);
        } else {
            chatForm.appendChild(btn);
        }
        return btn;
    }
    
    // Function to create and show stop button
    function showStopButton() {
        // Check if we're already in the process of transitioning
        if (currentButtonState === ButtonState.TRANSITIONING) {
            console.log('Button transition in progress, skipping showStopButton');
            return;
        }
        
        // If already showing stop button, nothing to do
        if (currentButtonState === ButtonState.STOP) {
            console.log('Stop button already visible');
            return;
        }
        
        // Clear any pending transition
        if (buttonTransitionTimeout) {
            clearTimeout(buttonTransitionTimeout);
            buttonTransitionTimeout = null;
        }
        
        currentButtonState = ButtonState.TRANSITIONING;
        
        // Create stop button if it doesn't exist
        if (!stopBtn) {
            stopBtn = document.createElement('button');
            stopBtn.id = 'stop-btn';
            stopBtn.type = 'button';
            stopBtn.className = 'action-btn';
            stopBtn.innerHTML = '<i class="fas fa-stop"></i>';
            stopBtn.title = 'Stop generating';
            
            // Add event listener to stop button
            stopBtn.addEventListener('click', stopGeneration);
        }
        
        // Handle the input actions container
        const inputActions = document.querySelector('.input-actions');
        const sendBtnContainer = sendBtn.parentElement;
        
        if (inputActions && sendBtnContainer === inputActions) {
            // If send button is in input actions, replace it with stop button
            inputActions.replaceChild(stopBtn, sendBtn);
        } else {
            // Otherwise just append to form
            chatForm.appendChild(stopBtn);
            sendBtn.style.display = 'none';
        }
        
        isStreaming = true;
        currentButtonState = ButtonState.STOP;
        
        // Set a timeout to prevent stuck states
        buttonTransitionTimeout = setTimeout(() => {
            if (currentButtonState === ButtonState.STOP && !isStreaming) {
                console.log('Stuck in stop state, forcing reset');
                resetStreamingState();
            }
        }, 30000); // 30 seconds timeout
    }
    
    // Function to hide stop button and show send button
    function hideStopButton() {
        // Check if we're already in the process of transitioning
        if (currentButtonState === ButtonState.TRANSITIONING) {
            console.log('Button transition in progress, skipping hideStopButton');
            return;
        }
        
        // If already showing send button, nothing to do
        if (currentButtonState === ButtonState.SEND) {
            console.log('Send button already visible');
            return;
        }
        
        // Clear any pending transition
        if (buttonTransitionTimeout) {
            clearTimeout(buttonTransitionTimeout);
            buttonTransitionTimeout = null;
        }
        
        currentButtonState = ButtonState.TRANSITIONING;
        
        const inputActions = document.querySelector('.input-actions');
        
        if (stopBtn) {
            if (inputActions && stopBtn.parentElement === inputActions) {
                // If stop button is in input actions, replace it with send button
                inputActions.replaceChild(sendBtn, stopBtn);
            } else {
                stopBtn.style.display = 'none';
                sendBtn.style.display = 'block';
            }
        }
        
        isStreaming = false;
        currentButtonState = ButtonState.SEND;
    }
    
    // Function to reset streaming state completely
    function resetStreamingState() {
        console.log('Resetting streaming state');
        
        // Reset flags
        isStreaming = false;
        stopRequested = false;
        
        // Clear button transition timeout
        if (buttonTransitionTimeout) {
            clearTimeout(buttonTransitionTimeout);
            buttonTransitionTimeout = null;
        }
        
        // Force button state to SEND
        currentButtonState = ButtonState.SEND;
        
        // Remove typing indicator if exists
        const typingIndicator = document.querySelector('.typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
        
        // Force send button to be shown
        const inputActions = document.querySelector('.input-actions');
        if (stopBtn && inputActions && stopBtn.parentElement === inputActions) {
            // If stop button is in input actions, replace it with send button
            try {
                inputActions.replaceChild(sendBtn, stopBtn);
            } catch (e) {
                console.warn('Error replacing stop button:', e);
                // Fallback: ensure send button is visible
                if (!inputActions.contains(sendBtn)) {
                    inputActions.appendChild(sendBtn);
                }
            }
        } else if (stopBtn) {
            stopBtn.style.display = 'none';
            sendBtn.style.display = 'block';
        }
        
        // Re-enable chat input
        const chatInput = document.getElementById('chat-input');
        if (chatInput) {
            chatInput.disabled = false;
        }
        
        // Clear any active generation task reference
        if (window.activeStreamingTimeout) {
            clearTimeout(window.activeStreamingTimeout);
            window.activeStreamingTimeout = null;
        }
    }
    
    // Function to stop the generation
    function stopGeneration() {
        if (socket && socket.readyState === WebSocket.OPEN && !stopRequested) {
            // Set flag to indicate stop has been requested
            stopRequested = true;
            
            const stopMessage = {
                type: 'stop_generation',
                conversation_id: currentConversationId,
                project_id: currentProjectId
            };
            socket.send(JSON.stringify(stopMessage));
            console.log('Stop generation message sent');
            
            // Remove typing indicator if it exists
            const typingIndicator = document.querySelector('.typing-indicator');
            if (typingIndicator) {
                typingIndicator.remove();
            }
            
            // Add a note that generation was stopped
            const assistantMessage = document.querySelector('.message.assistant:last-child');
            if (assistantMessage) {
                const contentDiv = assistantMessage.querySelector('.message-content');
                const currentContent = contentDiv.getAttribute('data-raw-content') || '';
                const newContent = currentContent + '\n\n*Generation stopped by user*';
                
                contentDiv.setAttribute('data-raw-content', newContent);
                contentDiv.innerHTML = marked.parse(newContent);
            } else {
                // If there's no assistant message yet, create one with the stopped message
                addMessageToChat('system', '*Generation stopped by user*');
            }
            
            // Reset UI - enable input and restore send button
            chatInput.disabled = false;
            hideStopButton();
        }
    }
    
    // Function to send message using WebSocket
    function sendMessage(message) {
        console.log('sendMessage: Starting to send message:', message);
        
        // Check if we have a message or an attached file
        if (!message && !window.attachedFile) {
            console.log('No message or file to send');
            return;
        }

        // Reset stop requested flag
        stopRequested = false;
        
        // Get selected role from dropdown if it exists
        let userRole = 'default';
        if (typeof getCustomDropdownValue === 'function') {
            userRole = getCustomDropdownValue('role-dropdown') || 'default';
        } else {
            // Fallback for old select dropdown
            const roleDropdown = document.getElementById('role-dropdown');
            if (roleDropdown && roleDropdown.tagName === 'SELECT') {
                userRole = roleDropdown.value;
            }
        }
        console.log('Selected role:', userRole);
        
        // Get file data from the attached file (which may already have a file_id if it was uploaded)
        let fileData = null;
        if (window.attachedFile) {
            console.log('Attached file found:', window.attachedFile);
            fileData = {
                name: window.attachedFile.name,
                type: window.attachedFile.type,
                size: window.attachedFile.size
            };
            
            // If the file was already uploaded, it will have an id
            if (window.attachedFile.id) {
                fileData.id = window.attachedFile.id;
            }
        }
        
        // Store a reference to the attached file and clear the global reference
        const attachedFile = window.attachedFile;
        window.attachedFile = null;
        
        // Clear the file attachment indicator
        const fileAttachmentIndicator = document.querySelector('.input-file-attachment');
        if (fileAttachmentIndicator) {
            fileAttachmentIndicator.remove();
        }
        
        // If there's an attached file that hasn't been uploaded yet, upload it first
        if (attachedFile && attachedFile.file && !attachedFile.id) {
            // Show typing indicator (shows we're doing something)
            const typingIndicator = document.createElement('div');
            typingIndicator.className = 'typing-indicator';
            typingIndicator.innerHTML = '<span></span><span></span><span></span>';
            messageContainer.appendChild(typingIndicator);
            console.log('sendMessage: Added typing indicator for file upload');
            
            // Disable input while uploading file and waiting for response
            chatInput.disabled = true;
            
            // Check for conversation ID - first in currentConversationId, then in URL
            let conversationId = currentConversationId;
            if (!conversationId) {
                // Try to get it from URL
                const urlParams = new URLSearchParams(window.location.search);
                if (urlParams.has('conversation_id')) {
                    conversationId = urlParams.get('conversation_id');
                    console.log('Found conversation ID in URL:', conversationId);
                    // Update current conversation ID
                    currentConversationId = conversationId;
                }
            }
            
            if (conversationId) {
                // If we have a conversation ID from anywhere, upload file first
                console.log('Uploading file to conversation:', conversationId);
                uploadFileToServer(attachedFile.file, conversationId)
                    .then(fileResponse => {
                        console.log('File uploaded successfully before message, file_id:', fileResponse.id);
                        
                        // Now add the file_id to the file data
                        fileData.id = fileResponse.id;
                        
                        // Now actually add the user message to chat with file data
                        addMessageToChat('user', message, fileData, userRole);
                        
                        // Proceed with sending the message with the file_id
                        sendMessageToServer(message, fileData);
                    })
                    .catch(error => {
                        console.error('Error uploading file before message:', error);
                        
                        // If file upload failed, still send the message without file_id
                        addMessageToChat('user', message, fileData, userRole);
                        sendMessageToServer(message, fileData);
                        
                        // Re-enable input
                        chatInput.disabled = false;
                    });
            } else {
                // If we still don't have a conversation ID, just send the message with file data
                console.log('No conversation ID found. Sending message with file data.');
                
                // Add user message to chat with file data
                addMessageToChat('user', message, fileData, userRole);
                
                // For simplicity, we'll just send message without file_id
                // The server will need to handle creating both conversation and file
                sendMessageToServer(message, fileData);
                
                // Remove typing indicator for file upload
                const typingIndicator = document.querySelector('.typing-indicator');
                if (typingIndicator) {
                    typingIndicator.remove();
                }
            }
        } else {
            // Either no file is attached, or the file was already uploaded and has a file_id
            
            // Add user message to chat with file data (including file_id if available)
            addMessageToChat('user', message, fileData, userRole);
            
            // Proceed with standard message sending
            sendMessageToServer(message, fileData);
        }
    }
    
    // Function to handle the actual WebSocket message sending
    function sendMessageToServer(message, fileData = null) {
        // Show typing indicator if not already present
        if (!document.querySelector('.typing-indicator')) {
            const typingIndicator = document.createElement('div');
            typingIndicator.className = 'typing-indicator';
            typingIndicator.innerHTML = '<span></span><span></span><span></span>';
            messageContainer.appendChild(typingIndicator);
            console.log('sendMessageToServer: Added typing indicator');
        }
        
        // Scroll to bottom
        scrollToBottom();
        
        // Disable input while waiting for response (if not already disabled)
        chatInput.disabled = true;
        
        // Show stop button since we're about to start streaming
        showStopButton();
        
        // Get selected role from dropdown if it exists
        let userRole = 'default';
        const roleDropdown = document.getElementById('role-dropdown');
        if (roleDropdown) {
            userRole = roleDropdown.value;
            console.log('Selected role for API request:', userRole);
        }
        
        // Get turbo mode toggle state
        const turboModeToggle = document.getElementById('turbo-mode-toggle');
        const turboMode = turboModeToggle ? turboModeToggle.checked : false;
        
        // Prepare message data
        const messageData = {
            type: 'message',
            message: message,
            conversation_id: currentConversationId,
            provider: currentProvider,
            project_id: currentProjectId,
            user_role: userRole,
            turbo_mode: turboMode
        };
        
        // Add project_id if available
        if (currentProjectId) {
            messageData.project_id = currentProjectId;
        }
        
        // Add file data if provided
        if (fileData) {
            messageData.file = fileData;
        }
        
        console.log('sendMessageToServer: Message data:', messageData);
        
        // Send via WebSocket if connected, otherwise queue
        if (isSocketConnected && socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(messageData));
        } else {
            console.log('WebSocket not connected, queueing message');
            messageQueue.push(messageData);
            
            // Try to reconnect
            if (!isSocketConnected) {
                connectWebSocket();
            }
        }
    }
    
    // Function to upload file to server via REST API
    async function uploadFileToServer(file, conversationId = null, messageId = null) {
        try {
            console.log('%c FILE UPLOAD - Starting file upload process', 'background: #3a9; color: white; font-weight: bold;');
            console.log('File to upload:', file);
            console.log('Conversation ID:', conversationId);
            console.log('Message ID:', messageId);
            
            // Validate that we have a conversation ID if required
            if (!conversationId) {
                console.warn('No conversation ID provided for file upload');
                showFileNotification(`File upload requires a conversation ID`, 'error');
                throw new Error('Conversation ID is required');
            }
            
            // Show uploading notification
            const notification = showFileNotification(`Uploading ${file.name}...`, 'uploading');
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('conversation_id', conversationId);
            if (messageId) {
                formData.append('message_id', messageId);
            }
            
            // Get CSRF token
            const csrfToken = getCsrfToken();
            console.log('CSRF Token obtained:', csrfToken ? 'Token exists' : 'No token found');
            
            // Log request details
            console.log('%c API REQUEST - About to send file upload request', 'background: #f50; color: white; font-weight: bold;');
            console.log('Endpoint:', '/api/files/upload/');
            console.log('Method:', 'POST');
            console.log('FormData contents:', {
                file: file.name,
                conversation_id: conversationId,
                message_id: messageId || 'Not provided'
            });
            
            // Add a timestamp to force cache busting
            const timestamp = new Date().getTime();
            const apiUrl = `/api/files/upload/?_=${timestamp}`;
            
            // Force this to be a visible network call by adding headers
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                },
                body: formData,
                credentials: 'same-origin' // Include cookies
            });
            
            console.log('%c API RESPONSE - Received response from server', 'background: #0a5; color: white; font-weight: bold;');
            console.log('Response status:', response.status);
            console.log('Response OK:', response.ok);
            
            if (!response.ok) {
                console.error('Upload failed with status:', response.status);
                let errorData;
                try {
                    errorData = await response.json();
                    console.error('Error details:', errorData);
                } catch (e) {
                    const textError = await response.text();
                    console.error('Error response (text):', textError);
                    errorData = { error: 'Failed to upload file' };
                }
                throw new Error(errorData.error || `Failed to upload file: ${response.status}`);
            }
            
            // Parse response data
            let data;
            try {
                data = await response.json();
                console.log('%c SUCCESS - File uploaded successfully', 'background: #0c0; color: white; font-weight: bold;');
                console.log('Server response:', data);
            } catch (e) {
                console.error('Failed to parse JSON response:', e);
                const textResponse = await response.text();
                console.log('Raw response text:', textResponse);
                throw new Error('Invalid response format from server');
            }
            
            // Check for file_id in response
            if (!data.id) {
                console.error('Server response missing file_id:', data);
                throw new Error('Server did not return a file_id');
            }
            
            console.log('%c FILE ID - Obtained file ID from server', 'background: #00c; color: white; font-weight: bold;');
            console.log('File ID:', data.id);
            
            // Update notification to show success
            if (notification && notification.parentNode) {
                notification.className = 'file-notification success';
                notification.innerHTML = `
                    <i class="fas fa-check-circle"></i>
                    <span>File ${file.name} uploaded successfully (ID: ${data.id})</span>
                `;
                
                // Remove after a delay
                setTimeout(() => {
                    if (notification.parentNode) {
                        notification.classList.remove('show');
                        setTimeout(() => notification.remove(), 300);
                    }
                }, 5000);
            }
            
            // Return the data with file_id
            return data;
        } catch (error) {
            console.error('%c ERROR - File upload failed', 'background: #f00; color: white; font-weight: bold;');
            console.error('Error details:', error);
            console.error('Stack trace:', error.stack);
            
            // Show error notification
            showFileNotification(`Error uploading file: ${error.message}`, 'error');
            throw error;
        }
    }
    
    // Helper function to show file notifications
    function showFileNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `file-notification ${type}`;
        
        // Add icon based on type
        let icon = 'info-circle';
        if (type === 'success') icon = 'check-circle';
        if (type === 'error') icon = 'exclamation-circle';
        if (type === 'uploading') icon = 'sync fa-spin';
        
        notification.innerHTML = `
            <i class="fas fa-${icon}"></i>
            <span>${message}</span>
        `;
        
        // Add to container
        const container = document.querySelector('.chat-messages');
        container.appendChild(notification);
        
        // Show with animation
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);
        
        // Remove after delay unless it's an uploading notification
        if (type !== 'uploading') {
            setTimeout(() => {
                notification.classList.remove('show');
                setTimeout(() => notification.remove(), 300);
            }, 5000);
        }
        
        return notification;
    }

    // Function to add a message to the chat
    // Function to check if a message contains tool-related content
    function checkForToolMention(message) {
        if (!message) return null;
        
        const toolPatterns = [
            /(?:calling|using|executing|running)\s+(?:the\s+)?(\w+)\s+(?:function|tool)/i,
            /I'll\s+(?:now\s+)?(?:use|call|execute)\s+(?:the\s+)?(\w+)/i,
            /Let\s+me\s+(?:use|call|execute)\s+(?:the\s+)?(\w+)/i,
            /(\w+)\s+function\s+(?:to|will)/i
        ];
        
        const knownTools = [
            'extract_features', 'extract_personas', 'get_features', 'get_personas',
            'save_implementation', 'execute_command', 'start_server', 'create_implementation',
            'update_implementation', 'get_implementation', 'save_prd', 'get_prd'
        ];
        
        // Direct tool name check
        for (const tool of knownTools) {
            if (message.toLowerCase().includes(tool)) {
                return tool;
            }
        }
        
        // Pattern matching
        for (const pattern of toolPatterns) {
            const match = message.match(pattern);
            if (match && match[1]) {
                const toolName = match[1].toLowerCase();
                if (knownTools.includes(toolName)) {
                    return toolName;
                }
            }
        }
        
        return null;
    }
    
    function addMessageToChat(role, content, fileData = null, userRole = null, isPartial = false) {
        // Skip adding empty messages unless there's an audio indicator
        if (!content || content.trim() === '') {
            if (!fileData || !fileData.audioIndicator) {
                console.log(`Skipping empty ${role} message`);
                return;
            }
        }
        
        // Check for tool mentions in AI messages
        if (role === 'assistant') {
            const detectedTool = checkForToolMention(content);
            if (detectedTool && !document.querySelector('.tool-execution-indicator')) {
                console.log('Tool detected in complete message:', detectedTool);
                window.triggerToolAnimation(detectedTool);
            }
            
            // Check for audio transcription in the response
            const transcription = extractAudioTranscription(content);
            console.log('Checking for transcription. Found:', transcription, 'Last audio element:', window.lastAudioMessageElement);
            
            if (transcription && window.lastAudioMessageElement) {
                // Update the last audio message with transcription
                const transcriptionDiv = window.lastAudioMessageElement.querySelector('.audio-transcription');
                console.log('Found transcription div:', transcriptionDiv);
                if (transcriptionDiv) {
                    transcriptionDiv.textContent = transcription;
                    transcriptionDiv.style.display = 'block';
                    console.log('Updated transcription display');
                }
                // Clear the reference
                window.lastAudioMessageElement = null;
            }
        }
        
        // Create message element
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        // If this is a partial message, add a special class
        if (isPartial) {
            messageDiv.classList.add('partial-message');
        }
        
        // If this is a user message and userRole is provided, add it as a data attribute
        if (role === 'user' && userRole) {
            messageDiv.dataset.userRole = userRole;
        }
        
        // Create message content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.setAttribute('data-raw-content', content);
        
        // Use marked.js to render markdown for assistant messages
        if (role === 'assistant' || role === 'system') {
            contentDiv.innerHTML = marked.parse(content);
        } else {
            // For user messages, escape HTML and preserve line breaks
            const escapedContent = content
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;')
                // .replace(/\n/g, '<br>');
            contentDiv.innerHTML = escapedContent;

            
            // Add file attachment indicator if fileData is provided
            if (fileData) {
                // Check if it's an audio indicator
                if (fileData.audioIndicator) {
                    // For audio messages, replace the entire content
                    contentDiv.innerHTML = '';
                    contentDiv.appendChild(fileData.audioIndicator);
                } else if (fileData.name) {
                    const fileAttachment = document.createElement('div');
                    fileAttachment.className = 'file-attachment';
                    fileAttachment.innerHTML = `
                        <i class="fas fa-paperclip"></i>
                        <span class="file-name">${fileData.name}</span>
                        <span class="file-type">${fileData.type}</span>
                    `;
                    contentDiv.appendChild(document.createElement('br'));
                    contentDiv.appendChild(fileAttachment);
                }
            }
        }
        
        // Create copy button
        const copyButton = document.createElement('button');
        copyButton.className = 'message-copy-btn';
        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
        copyButton.title = 'Copy message';
        copyButton.onclick = function() {
            copyMessageToClipboard(content, this);
        };
        
        // Create a message actions container
        const messageActions = document.createElement('div');
        messageActions.className = 'message-actions';
        messageActions.appendChild(copyButton);
        
        // Append elements
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(messageActions);
        
        // Add partial message indicator if needed
        if (isPartial) {
            const partialIndicator = document.createElement('div');
            partialIndicator.className = 'partial-indicator';
            partialIndicator.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> <span>Message in progress...</span>';
            messageDiv.appendChild(partialIndicator);
        }
        
        messageContainer.appendChild(messageDiv);
        
        // Remove typing indicator if it exists
        const typingIndicator = document.querySelector('.typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
        
        // Return the message element for reference
        return messageDiv;
    }
    
    // Function to copy message to clipboard
    function copyMessageToClipboard(content, button) {
        // Use the Clipboard API if available
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(content).then(() => {
                // Show success feedback
                const originalHTML = button.innerHTML;
                button.innerHTML = '<i class="fas fa-check"></i>';
                button.classList.add('copied');
                
                setTimeout(() => {
                    button.innerHTML = originalHTML;
                    button.classList.remove('copied');
                }, 2000);
            }).catch(err => {
                console.error('Failed to copy text: ', err);
                // Fallback to older method
                fallbackCopyToClipboard(content, button);
            });
        } else {
            // Fallback for older browsers or non-secure contexts
            fallbackCopyToClipboard(content, button);
        }
    }
    
    // Fallback copy method for older browsers
    function fallbackCopyToClipboard(content, button) {
        const textArea = document.createElement("textarea");
        textArea.value = content;
        textArea.style.position = "fixed";
        textArea.style.left = "-999999px";
        textArea.style.top = "-999999px";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
            document.execCommand('copy');
            // Show success feedback
            const originalHTML = button.innerHTML;
            button.innerHTML = '<i class="fas fa-check"></i>';
            button.classList.add('copied');
            
            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.classList.remove('copied');
            }, 2000);
        } catch (err) {
            console.error('Failed to copy text: ', err);
            alert('Failed to copy message');
        }
        
        document.body.removeChild(textArea);
    }
    
    // Function to show a function call indicator
    function showFunctionCallIndicator(functionName) {
        // Remove any existing function call indicators
        removeFunctionCallIndicator();
        
        // Get a user-friendly function description
        const functionDetails = getFunctionDetails(functionName);
        
        // Create the indicator element
        const indicator = document.createElement('div');
        indicator.className = 'function-call-indicator';
        
        // Add function-specific class for styling
        const functionType = functionName.includes('features') ? 'features' :
                           functionName.includes('personas') ? 'personas' :
                           functionName.includes('implementation') ? 'implementation' :
                           functionName === 'execute_command' ? 'execute_command' :
                           functionName === 'start_server' ? 'start_server' :
                           'generic';
        indicator.classList.add(`function-${functionType}`);
        
        indicator.innerHTML = `
            <div class="function-call-spinner"></div>
            <div class="function-call-text">
                <div class="function-name">${functionName}()</div>
                <div class="function-status">
                    ${functionDetails.description || 'Processing function call...'}
                </div>
            </div>
        `;
        
        // Add to message container
        messageContainer.appendChild(indicator);
        scrollToBottom();
        
        return indicator;
    }
    
    // Function to show a function call success message
    function showFunctionCallSuccess(functionName, type) {
        // Remove any existing function call indicators
        removeFunctionCallIndicator();
        
        // Get function details
        const functionDetails = getFunctionDetails(functionName);
        
        // Create the success element
        const successElement = document.createElement('div');
        successElement.className = 'function-call-success';
        
        // Add function-specific class for styling
        const functionType = functionName.includes('features') ? 'features' :
                           functionName.includes('personas') ? 'personas' :
                           functionName.includes('implementation') ? 'implementation' :
                           functionName === 'execute_command' ? 'execute_command' :
                           functionName === 'start_server' ? 'start_server' :
                           type || 'generic';
        successElement.classList.add(`function-${functionType}`);
        
        let message = '';
        if (type === 'features') {
            message = 'Features extracted and saved successfully!';
        } else if (type === 'personas') {
            message = 'Personas extracted and saved successfully!';
        } else if (type === 'prd') {
            message = 'PRD generated and saved successfully!';
        } else if (type === 'command_output' || functionName === 'execute_command') {
            message = 'Command executed successfully!';
        } else if (type === 'implementation') {
            message = 'Implementation saved successfully!';
        } else if (type === 'design') {
            message = 'Design schema created successfully!';
        } else if (type === 'tickets') {
            message = 'Tickets generated successfully!';
        } else if (type === 'checklist') {
            message = 'Checklist updated successfully!';
        } else {
            message = 'Function call completed successfully!';
        }
        
        successElement.innerHTML = `
            <div class="function-call-icon">✓</div>
            <div class="function-call-text">
                <div class="function-name">${functionName}()</div>
                <div class="function-result">
                    ${message}<br>
                    <small>${functionDetails.successMessage || 'Results have been processed and saved.'}</small>
                </div>
            </div>
        `;
        
        // Add to message container
        messageContainer.appendChild(successElement);
        scrollToBottom();
        
        // Remove after a delay
        setTimeout(() => {
            if (successElement.parentNode) {
                successElement.classList.add('fade-out');
                setTimeout(() => {
                    if (successElement.parentNode) {
                        successElement.remove();
                    }
                }, 500); // fade out time
            }
        }, 4000); // show for 4 seconds
    }
    
    // Function to add a permanent mini indicator of function call success
    function addFunctionCallMiniIndicator(functionName, type) {
        // Create mini indicator
        const miniIndicator = document.createElement('div');
        miniIndicator.className = 'function-mini-indicator';
        
        let icon = '';
        if (type === 'features') icon = '📋';
        else if (type === 'personas') icon = '👥';
        else if (type === 'prd') icon = '📄';
        else icon = '✓';
        
        miniIndicator.innerHTML = `
            <span class="mini-icon">${icon}</span>
            <span class="mini-name">${functionName}</span>
        `;
        
        // Add it to the message container
        messageContainer.appendChild(miniIndicator);
        
        // Add fade-in animation
        setTimeout(() => {
            miniIndicator.classList.add('show');
        }, 100);
    }
    
    // Helper function to get function details for UI display
    function getFunctionDetails(functionName) {
        const functionDetails = {
            'extract_features': {
                description: 'Extracting and processing features from the conversation...',
                successMessage: 'Features have been extracted, categorized, and saved to the project.'
            },
            'extract_personas': {
                description: 'Analyzing and extracting personas from the conversation...',
                successMessage: 'Personas have been identified and saved to the project.'
            },
            'get_features': {
                description: 'Retrieving existing features for this project...',
                successMessage: 'Existing features have been loaded from the database.'
            },
            'get_personas': {
                description: 'Retrieving existing personas for this project...',
                successMessage: 'Existing personas have been loaded from the database.'
            },
            'extract_prd': {
                description: 'Generating and processing PRD from the conversation...',
                successMessage: 'PRD has been generated and saved to the project.'
            },
            'get_prd': {
                description: 'Retrieving existing PRD for this project...',
                successMessage: 'Existing PRD has been loaded from the database.'
            },
            'execute_command': {
                description: 'Executing a command...',
                successMessage: 'Command executed successfully.'
            },
            'start_server': {
                description: 'Starting the server...',
                successMessage: 'Server started successfully.'
            },
            'save_implementation': {
                description: 'Saving implementation...',
                successMessage: 'Implementation saved successfully.'
            },
            'create_prd': {
                description: 'Creating and saving PRD document...',
                successMessage: 'PRD has been created and saved to the project.'
            },
            'create_implementation': {
                description: 'Creating implementation document...',
                successMessage: 'Implementation document has been created and saved.'
            },
            'update_implementation': {
                description: 'Updating implementation document...',
                successMessage: 'Implementation document has been updated.'
            },
            'get_implementation': {
                description: 'Retrieving implementation document...',
                successMessage: 'Implementation document has been loaded.'
            },
            'save_features': {
                description: 'Saving features to the project...',
                successMessage: 'Features have been saved successfully.'
            },
            'save_personas': {
                description: 'Saving personas to the project...',
                successMessage: 'Personas have been saved successfully.'
            },
            'design_schema': {
                description: 'Creating database design schema...',
                successMessage: 'Database schema has been designed and saved.'
            },
            'generate_tickets': {
                description: 'Generating development tickets...',
                successMessage: 'Development tickets have been generated successfully.'
            },
            'checklist_tickets': {
                description: 'Creating checklist for tickets...',
                successMessage: 'Ticket checklist has been created.'
            },
            'update_checklist_ticket': {
                description: 'Updating ticket checklist...',
                successMessage: 'Checklist has been updated.'
            },
            'get_next_ticket': {
                description: 'Getting next ticket to work on...',
                successMessage: 'Next ticket has been retrieved.'
            },
            'implement_ticket': {
                description: 'Implementing ticket...',
                successMessage: 'Ticket has been implemented.'
            }
        };
        
        return functionDetails[functionName] || {};
    }
    
    // Function to remove any function call indicators
    function removeFunctionCallIndicator() {
        const existingIndicators = document.querySelectorAll('.function-call-indicator, .function-call-success');
        existingIndicators.forEach(indicator => {
            indicator.remove();
        });
    }
    
    // Add new function to detect function calls in text and show indicators
    function checkForFunctionCall(text) {
        // More comprehensive patterns to detect function calls in the AI's text
        const patterns = [
            // Standard function call patterns
            /(?:I'll|I will|Let me|I'm going to|I am going to)\s+(?:call|use|execute|run)\s+(?:the\s+)?`?(\w+)`?\s+function/i,
            
            // Direct function mentions
            /(?:calling|executing|running|using)\s+(?:the\s+)?`?(\w+)`?\s+function/i,
            
            // Code block style mentions
            /```(?:python|js|javascript)?\s*(?:function\s+)?(\w+)\s*\(/i,
            
            // Now let's/I'm extracting patterns
            /(?:Now|I'm|I am)\s+(?:extracting|getting)\s+(?:the\s+)?(\w+)/i,
            
            // Calling with specific syntax
            /(?:extract_(\w+)|get_(\w+))\(/i
        ];
        
        // Check each pattern
        for (const pattern of patterns) {
            const match = text.match(pattern);
            if (match) {
                let functionName = '';
                
                // Special case for the last pattern with capturing groups
                if (pattern.toString().includes('extract_') && (match[1] || match[2])) {
                    functionName = match[1] ? `extract_${match[1]}` : `get_${match[2]}`;
                } else if (match[1]) {
                    functionName = match[1].toLowerCase();
                    
                    // Handle some common variations
                    if (functionName === 'extract' || functionName === 'extracting') functionName = 'extract_features';
                    if (functionName === 'features') functionName = 'extract_features';
                    if (functionName === 'personas') functionName = 'extract_personas';
                    if (functionName === 'prd') functionName = 'extract_prd';
                }
                
                // Only show for known functions to avoid false positives
                const knownFunctions = ['extract_features', 'extract_personas', 'get_features', 'get_personas', 'extract_prd', 'get_prd', 'execute_command', 'start_server', 'save_implementation'];
                
                if (knownFunctions.includes(functionName)) {
                    showFunctionCallIndicator(functionName);
                    return; // Exit after finding the first match
                }
            }
        }
    }
    
    // Function to clear all messages from the chat
    function clearChatMessages() {
        messageContainer.innerHTML = '';
    }
    
    // Function to scroll to the bottom of the chat
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // Function to handle tool progress updates
    function handleToolProgress(data) {
        const { tool_name, message, progress_percentage } = data;
        
        // Find or create progress indicator
        let progressIndicator = document.querySelector('.tool-progress-indicator');
        if (!progressIndicator) {
            progressIndicator = document.createElement('div');
            progressIndicator.className = 'tool-progress-indicator';
            messageContainer.appendChild(progressIndicator);
        }
        
        // Update progress UI
        let progressBar = '';
        if (progress_percentage !== null && progress_percentage >= 0) {
            progressBar = `
                <div class="progress-bar-container">
                    <div class="progress-bar" style="width: ${progress_percentage}%"></div>
                </div>
            `;
        }
        
        // Error state
        const isError = progress_percentage < 0;
        const statusClass = isError ? 'error' : (progress_percentage === 100 ? 'success' : 'active');
        
        progressIndicator.className = `tool-progress-indicator ${statusClass}`;
        progressIndicator.innerHTML = `
            <div class="tool-progress-content">
                <div class="tool-progress-header">
                    <i class="fas ${isError ? 'fa-exclamation-circle' : (progress_percentage === 100 ? 'fa-check-circle' : 'fa-cog fa-spin')}"></i>
                    <span class="tool-name">${tool_name}</span>
                </div>
                <div class="tool-progress-message">${message}</div>
                ${progressBar}
            </div>
        `;
        
        // Remove on completion or error
        if (progress_percentage === 100 || progress_percentage < 0) {
            setTimeout(() => {
                progressIndicator.classList.add('fade-out');
                setTimeout(() => progressIndicator.remove(), 500);
            }, 2000);
        }
        
        scrollToBottom();
    }
    
    // Heartbeat and connection monitoring functions
    function startHeartbeat() {
        // Clear any existing interval
        if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
        }
        
        lastHeartbeatResponse = Date.now();
    }
    
    function stopHeartbeat() {
        if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
            heartbeatInterval = null;
        }
    }
    
    function startConnectionMonitor() {
        connectionMonitorInterval = setInterval(() => {
            const timeSinceLastHeartbeat = Date.now() - lastHeartbeatResponse;
            
            // Be more lenient during streaming operations
            const heartbeatTimeout = isStreaming ? 120000 : 60000;  // 2 minutes during streaming, 1 minute otherwise
            
            if (timeSinceLastHeartbeat > heartbeatTimeout) {
                console.warn(`No heartbeat received for ${heartbeatTimeout/1000} seconds, connection may be dead`);
                showConnectionStatus('unstable');
                
                // Force reconnect
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.close();
                }
            }
        }, 5000);  // Check every 5 seconds
    }
    
    function stopConnectionMonitor() {
        if (connectionMonitorInterval) {
            clearInterval(connectionMonitorInterval);
            connectionMonitorInterval = null;
        }
    }
    
    function showConnectionStatus(status, current = 0, max = 0) {
        let statusElement = document.querySelector('.connection-status');
        if (!statusElement) {
            statusElement = document.createElement('div');
            statusElement.className = 'connection-status';
            document.body.appendChild(statusElement);
        }
        
        switch (status) {
            case 'disconnected':
                statusElement.innerHTML = `
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>Connection lost. Attempting to reconnect...</span>
                `;
                statusElement.className = 'connection-status warning';
                break;
                
            case 'reconnecting':
                statusElement.innerHTML = `
                    <i class="fas fa-sync fa-spin"></i>
                    <span>Reconnecting... (${current}/${max})</span>
                `;
                statusElement.className = 'connection-status warning';
                break;
                
            case 'failed':
                statusElement.innerHTML = `
                    <i class="fas fa-times-circle"></i>
                    <span>Connection failed. Please refresh the page.</span>
                    <button onclick="location.reload()" class="refresh-btn">Refresh</button>
                `;
                statusElement.className = 'connection-status error';
                break;
                
            case 'unstable':
                statusElement.innerHTML = `
                    <i class="fas fa-wifi"></i>
                    <span>Connection unstable...</span>
                `;
                statusElement.className = 'connection-status warning';
                break;
                
            // case 'connected':
            //     statusElement.innerHTML = `
            //         <i class="fas fa-check-circle"></i>
            //         <span>Connected</span>
            //     `;
            //     statusElement.className = 'connection-status success';
            //     setTimeout(() => {
            //         statusElement.classList.add('fade-out');
            //         setTimeout(() => statusElement.remove(), 500);
            //     }, 3000);
            //     break;
        }
    }
    
    // Draft message management
    function saveDraftMessage(message) {
        if (message && message.trim()) {
            const draftData = {
                message: message,
                conversationId: currentConversationId || '',
                timestamp: Date.now()
            };
            localStorage.setItem('chat_draft', JSON.stringify(draftData));
        }
    }
    
    function loadDraftMessage() {
        try {
            const draftJson = localStorage.getItem('chat_draft');
            if (draftJson) {
                const draftData = JSON.parse(draftJson);
                
                // Check if draft is less than 24 hours old
                const ageInHours = (Date.now() - draftData.timestamp) / (1000 * 60 * 60);
                if (ageInHours < 24 && draftData.conversationId === (currentConversationId || '')) {
                    chatInput.value = draftData.message;
                    
                    // Show draft indicator
                    const draftIndicator = document.createElement('div');
                    draftIndicator.className = 'draft-indicator';
                    draftIndicator.innerHTML = `
                        <i class="fas fa-info-circle"></i>
                        Draft message restored
                        <button onclick="clearDraftMessage(); this.parentElement.remove();" class="clear-draft">
                            <i class="fas fa-times"></i>
                        </button>
                    `;
                    chatInput.parentElement.appendChild(draftIndicator);
                    
                    setTimeout(() => {
                        if (draftIndicator.parentNode) {
                            draftIndicator.classList.add('fade-out');
                            setTimeout(() => draftIndicator.remove(), 500);
                        }
                    }, 5000);
                } else {
                    // Clear old draft
                    clearDraftMessage();
                }
            }
        } catch (e) {
            console.error('Error loading draft:', e);
        }
    }
    
    function clearDraftMessage() {
        localStorage.removeItem('chat_draft');
    }
    
    // Make clearDraftMessage available globally for onclick handler
    window.clearDraftMessage = clearDraftMessage;
    
    // Auto-save draft as user types (debounced)
    chatInput.addEventListener('input', debounce(function() {
        if (this.value.trim()) {
            saveDraftMessage(this.value);
        }
    }, 1000));
    
    // Clear draft when message is sent successfully
    const originalSendMessage = sendMessage;
    sendMessage = function(message) {
        const result = originalSendMessage(message);
        // Clear draft after successful send
        if (result !== false) {
            clearDraftMessage();
        }
        return result;
    };
    
    // Utility function for debouncing
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func.apply(this, args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    // Add event listener for beforeunload to save draft
    window.addEventListener('beforeunload', () => {
        if (chatInput.value.trim()) {
            saveDraftMessage(chatInput.value);
        }
    });
    
    // Load draft on DOMContentLoaded
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => {
            loadDraftMessage();
        }, 100);
    });
    
    // Test function for tool progress (for debugging)
    window.testToolProgress = function() {
        console.log('Testing tool progress indicator...');
        const progressSteps = [
            { message: "Starting extraction...", percentage: 10 },
            { message: "Analyzing data...", percentage: 40 },
            { message: "Processing results...", percentage: 70 },
            { message: "Saving to database...", percentage: 90 },
            { message: "Complete!", percentage: 100 }
        ];
        
        progressSteps.forEach((step, index) => {
            setTimeout(() => {
                console.log(`Sending progress: ${step.message} (${step.percentage}%)`);
                handleToolProgress({
                    tool_name: 'test_function',
                    message: step.message,
                    progress_percentage: step.percentage
                });
            }, index * 1000);
        });
    };
    
    // Test all animations
    // window.testAllAnimations = function() {
    //     console.log('Testing all tool animations...');
        
    //     // 1. Show tool execution indicator
    //     console.log('1. Showing tool execution indicator...');
    //     window.showToolExecutionIndicator('extract_features');
        
    //     // 2. Show function call indicator after 1 second
    //     setTimeout(() => {
    //         console.log('2. Showing function call indicator...');
    //         showFunctionCallIndicator('extract_features');
    //     }, 1000);
        
    //     // 3. Show tool progress after 2 seconds
    //     setTimeout(() => {
    //         console.log('3. Starting tool progress...');
    //         window.testToolProgress();
    //     }, 2000);
        
    //     // 4. Clean up after 8 seconds
    //     setTimeout(() => {
    //         console.log('4. Cleaning up...');
    //         document.querySelector('.tool-execution-indicator')?.remove();
    //         removeFunctionCallIndicator();
    //         document.querySelector('.tool-progress-indicator')?.remove();
    //     }, 8000);
    // };
    
    // Simple function to show a tool execution indicator
    window.showToolExecutionIndicator = function(toolName) {
        // Remove any existing indicators
        const existing = document.querySelector('.tool-execution-indicator');
        if (existing) existing.remove();
        
        const indicator = document.createElement('div');
        indicator.className = 'tool-execution-indicator';
        indicator.innerHTML = `
            <div class="tool-execution-content">
                <div class="tool-execution-spinner"></div>
                <div class="tool-execution-text">
                    <div class="tool-execution-title">Executing Tool</div>
                    <div class="tool-execution-name">${toolName || 'Processing...'}</div>
                </div>
            </div>
        `;
        
        messageContainer.appendChild(indicator);
        scrollToBottom();
        
        return indicator;
    };
    
    // Function to load conversation list
    async function loadConversations() {
        try {
            // First check path for project ID since we're in project context
            const pathProjectId = extractProjectIdFromPath();
            
            if (!pathProjectId) {
                throw new Error('No project ID found in path. Expected format: /chat/project/{id}/');
            }
            
            // Build the URL with project_id
            const url = `/api/projects/${pathProjectId}/conversations/`;
            console.log('Loading conversations for project:', pathProjectId);
            
            const response = await fetch(url);
            const conversations = await response.json();
            
            // Clear the conversation list
            conversationList.innerHTML = '';
            
            // Add conversations to the list
            conversations.forEach(conversation => {
                const conversationItem = createCompactConversationItem(conversation);
                
                // Add active class if this is the current conversation
                if (conversation.id === currentConversationId) {
                    conversationItem.classList.add('active');
                }
                
                // Add click handler
                conversationItem.addEventListener('click', () => {
                    loadConversation(conversation.id);
                });
                
                // Add delete handler
                const deleteBtn = conversationItem.querySelector('.delete-conversation');
                deleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    deleteConversation(conversation.id);
                });
                
                conversationList.appendChild(conversationItem);
            });
            
            // If sidebar is empty, add a message
            if (conversations.length === 0) {
                const emptyMessage = document.createElement('div');
                emptyMessage.className = 'empty-conversations-message';
                emptyMessage.textContent = 'No conversations yet. Start chatting!';
                conversationList.appendChild(emptyMessage);
            }
        } catch (error) {
            console.error('Error loading conversations:', error);
        }
    }
    
    // Function to load a specific conversation
    async function loadConversation(conversationId) {
        try {
            const response = await fetch(`/api/conversations/${conversationId}/`);
            const data = await response.json();
            
            // Set current conversation ID
            currentConversationId = conversationId;
            
            // Clear chat
            clearChatMessages();
            
            // Set project ID if this conversation is linked to a project
            if (data.project) {
                currentProjectId = data.project.id;
            }
            
            // Add each message to the chat
            data.messages.forEach(message => {
                // Skip empty messages and show all non-empty messages
                if (message.content && message.content.trim() !== '') {
                    addMessageToChat(message.role, message.content);
                }
            });
            
            // Load files for this conversation
            loadMessageFiles(conversationId);
            
            // Mark this conversation as active in the sidebar
            document.querySelectorAll('.conversation-item').forEach(item => {
                if (item.dataset.id === conversationId) {
                    item.classList.add('active');
                } else {
                    item.classList.remove('active');
                }
            });
            
            // Check if we're in project path format
            const pathProjectId = extractProjectIdFromPath();
            
            // Update URL appropriately based on format
            if (pathProjectId) {
                // If we're already in path format, just add conversation_id as query param
                const url = new URL(window.location);
                url.searchParams.set('conversation_id', conversationId);
                window.history.pushState({}, '', url);
            } else {
                // Standard query param format
                const url = new URL(window.location);
                url.searchParams.set('conversation_id', conversationId);
                if (currentProjectId) {
                    url.searchParams.set('project_id', currentProjectId);
                }
                window.history.pushState({}, '', url);
            }
            
            // Scroll to bottom
            scrollToBottom();
        } catch (error) {
            console.error('Error loading conversation:', error);
        }
    }

    // Function to set sidebar state
    function setSidebarState(collapsed) {
        const sidebar = document.getElementById('sidebar');
        
        if (collapsed) {
            sidebar.classList.remove('expanded');
            appContainer.classList.remove('sidebar-expanded');
        } else {
            sidebar.classList.add('expanded');
            appContainer.classList.add('sidebar-expanded');
        }
        
        // Store in localStorage
        localStorage.setItem('sidebar_collapsed', collapsed);
        
        // Save to server if user is logged in
        if (document.body.dataset.userAuthenticated === 'true') {
            fetch('/api/toggle-sidebar/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ collapsed: collapsed }),
            });
        }
    }

    // Close sidebar when overlay is clicked (mobile)
    sidebarOverlay.addEventListener('click', () => {
        setSidebarState(true); // Collapse sidebar
    });

    // Add a mobile toggle button
    function addMobileToggle() {
        const mobileToggle = document.createElement('button');
        mobileToggle.className = 'mobile-sidebar-toggle';
        mobileToggle.innerHTML = '☰';
        mobileToggle.addEventListener('click', () => {
            const sidebar = document.getElementById('sidebar');
            const isCurrentlyExpanded = sidebar.classList.contains('expanded');
            setSidebarState(isCurrentlyExpanded); // Toggle sidebar state
        });
        document.body.appendChild(mobileToggle);
    }

    // Call the initialization functions
    if (window.innerWidth <= 768) {
        addMobileToggle();
    }

    // Helper function to get CSRF token
    function getCsrfToken() {
        // Try to get it from the meta tag first (Django's standard location)
        const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (metaToken) {
            console.log('Found CSRF token in meta tag');
            return metaToken;
        }
        
        // Then try the input field (another common location)
        const inputToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (inputToken) {
            console.log('Found CSRF token in input field');
            return inputToken;
        }
        
        // Finally try to get it from cookies
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        
        if (cookieValue) {
            console.log('Found CSRF token in cookies');
            return cookieValue;
        }
        
        console.error('CSRF token not found in any location');
        return '';
    }

    // Function to delete a conversation
    async function deleteConversation(conversationId) {
        if (!confirm('Are you sure you want to delete this conversation? This action cannot be undone.')) {
            return;
        }
        
        try {
            // Get CSRF token
            const csrfToken = getCsrfToken();
            
            // Send delete request
            const response = await fetch(`/api/conversations/${conversationId}/`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                }
            });
            
            if (!response.ok) {
                throw new Error(`Server returned ${response.status}`);
            }
            
            // Remove from DOM
            const conversationItem = document.querySelector(`.conversation-item[data-id="${conversationId}"]`);
            if (conversationItem) {
                conversationItem.remove();
            }
            
            // If this was the active conversation, clear the chat
            if (currentConversationId === conversationId) {
                currentConversationId = null;
                clearChatMessages();
                chatInput.focus();
                
                // Clear URL parameter
                const url = new URL(window.location);
                url.searchParams.delete('conversation_id');
                window.history.pushState({}, '', url);
            }
            
            // Refresh conversation list
            loadConversations();
            
        } catch (error) {
            console.error('Error deleting conversation:', error);
            alert('Failed to delete conversation. Please try again.');
        }
    }

    // Helper function to format timestamps
    function formatTimestamp(date) {
        const now = new Date();
        const diff = now - date;
        const hours = Math.floor(diff / (1000 * 60 * 60));
        const days = Math.floor(hours / 24);
        
        if (hours < 1) return 'Just now';
        if (hours < 24) return `${hours}h ago`;
        if (days < 7) return `${days}d ago`;
        
        // Format as date for older conversations
        const options = { month: 'short', day: 'numeric' };
        if (date.getFullYear() !== now.getFullYear()) {
            options.year = 'numeric';
        }
        return date.toLocaleDateString('en-US', options);
    }
    
    // Modify the function that creates conversation items to be even more compact
    function createCompactConversationItem(conversation) {
        const conversationItem = document.createElement('div');
        conversationItem.className = 'conversation-item';
        conversationItem.dataset.id = conversation.id;
        
        // Truncate title to be compact
        let title = conversation.title || `Chat ${conversation.id}`;
        if (title.length > 25) { // Allow slightly longer titles
            title = title.substring(0, 25) + '...';
        }
        
        // Format timestamp
        const timestamp = conversation.created_at ? new Date(conversation.created_at) : new Date();
        const timeStr = formatTimestamp(timestamp);
        
        // Create sleek HTML structure
        conversationItem.innerHTML = `
            <div class="conversation-title" title="${conversation.title}">${title}</div>
            <button class="delete-conversation" title="Delete">
                <i class="fas fa-trash"></i>
            </button>
        `;
        
        return conversationItem;
    }

    // Add a test function to simulate a notification for debugging purposes
    window.testNotification = function(type) {
        console.log('Manually triggering notification test...');
        const notificationType = type || 'features';
        
        // Create a fake notification data object
        const fakeNotificationData = {
            type: 'ai_chunk',
            chunk: '',
            is_final: false,
            is_notification: true,
            notification_type: notificationType
        };
        
        // Process it through the normal handler
        console.log('Simulating notification with data:', fakeNotificationData);
        handleAIChunk(fakeNotificationData);
    };

    // Add a test function to simulate function call indicators for debugging
    window.testFunctionCall = function(functionName) {
        console.log('Testing function call indicator for:', functionName);
        
        const validFunctions = ['extract_features', 'extract_personas', 'get_features', 'get_personas', 'execute_command', 'start_server', 'save_implementation'];
        const fn = validFunctions.includes(functionName) ? functionName : validFunctions[0];
        
        // Add a simulated assistant message first
        if (!document.querySelector('.message.assistant:last-child')) {
            addMessageToChat('assistant', `I'll extract the key information from our conversation. Let me call the ${fn} function to process this data.`);
        }
        
        // Add the separator that would normally appear right after the function mention
        const separator = document.createElement('div');
        separator.className = 'function-call-separator';
        separator.innerHTML = `<div class="separator-line"></div>
                              <div class="separator-text">Calling function: ${fn}</div>
                              <div class="separator-line"></div>`;
        messageContainer.appendChild(separator);
        
        // Show the function call indicator
        showFunctionCallIndicator(fn);
        
        // After a delay, show the success message
        setTimeout(() => {
            const type = fn.includes('features') ? 'features' : 'personas';
            
            // Add a simulated response message
            setTimeout(() => {
                if (fn === 'extract_features') {
                    addMessageToChat('assistant', 'I\'ve successfully extracted and saved the features. You can view them in the artifacts panel.');
                } else if (fn === 'extract_personas') {
                    addMessageToChat('assistant', 'I\'ve successfully identified and saved the personas. You can view them in the artifacts panel.');
                } else {
                    addMessageToChat('assistant', 'I\'ve successfully retrieved the data. You can view it in the artifacts panel.');
                }
            }, 1000);
        }, 3000);
    };

    // Add a helper function to force open the artifacts panel
    window.forceOpenArtifactsPanel = function(tabType) {
        console.log('Force opening artifacts panel with tab:', tabType);
        
        // First try using the API if available
        if (window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function') {
            window.ArtifactsPanel.toggle(true);
        }
        
        // Then try direct DOM manipulation
        const panel = document.getElementById('artifacts-panel');
        const appContainer = document.querySelector('.app-container');
        const button = document.getElementById('artifacts-button');
        
        if (panel && appContainer) {
            panel.classList.add('expanded');
            appContainer.classList.add('artifacts-expanded');
            if (button) button.classList.add('active');
        }
        
        // Then try to switch to the correct tab
        if (window.switchTab && tabType) {
            setTimeout(() => {
                window.switchTab(tabType);
                
                // Try to load the content based on the tab type
                if (window.ArtifactsLoader) {
                    const projectId = currentProjectId || extractProjectIdFromPath() || 
                                    new URLSearchParams(window.location.search).get('project_id');
                    
                    if (projectId) {
                        if (tabType === 'features' && typeof window.ArtifactsLoader.loadFeatures === 'function') {
                            window.ArtifactsLoader.loadFeatures(projectId);
                        } else if (tabType === 'personas' && typeof window.ArtifactsLoader.loadPersonas === 'function') {
                            window.ArtifactsLoader.loadPersonas(projectId);
                        } else if (tabType === 'prd' && typeof window.ArtifactsLoader.loadPRD === 'function') {
                            // Check if PRD is currently streaming before loading
                            if (window.prdStreamingState && window.prdStreamingState.isStreaming) {
                                console.log('[Chat] PRD is currently streaming, skipping loadPRD');
                            } else {
                                window.ArtifactsLoader.loadPRD(projectId);
                            }
                        }
                    }
                }
            }, 100); // Small delay to ensure panel is open first
        }
    };

    /**
     * Test function to demonstrate notification styles
     * This can be called from the console with: testNotifications()
     */
    function testNotifications() {
        console.log('Testing notification indicators');
        
        // Test default function call indicator
        showFunctionCallIndicator('test_function');
        
        // Test function call for features
        setTimeout(() => {
            const featuresElement = document.createElement('div');
            featuresElement.className = 'function-features';
            document.querySelector('.messages').appendChild(featuresElement);
            
            showFunctionCallIndicator('extract_features', 'features');
        }, 1000);
        
        // Test function call for personas
        setTimeout(() => {
            const personasElement = document.createElement('div');
            personasElement.className = 'function-personas';
            document.querySelector('.messages').appendChild(personasElement);
            
            showFunctionCallIndicator('extract_personas', 'personas');
        }, 2000);
        
        // Test success notification
        setTimeout(() => {
            showFunctionCallSuccess('test_function');
        }, 3000);
        
        // Test success notification for features
        setTimeout(() => {
            showFunctionCallSuccess('extract_features', 'features');
        }, 4000);
        
        // Test success notification for personas
        setTimeout(() => {
            showFunctionCallSuccess('extract_personas', 'personas');
        }, 5000);
        
        // Test mini indicators
        setTimeout(() => {
            addFunctionCallMiniIndicator('test_function');
        }, 6000);
        
        setTimeout(() => {
            addFunctionCallMiniIndicator('extract_features', 'features');
        }, 6500);
        
        setTimeout(() => {
            addFunctionCallMiniIndicator('extract_personas', 'personas');
        }, 7000);
        
        console.log('All notification tests queued');
    }

    // Expose the test function globally
    window.testNotifications = testNotifications;

    // Function to load message files
    async function loadMessageFiles(conversationId) {
        try {
            const response = await fetch(`/api/conversations/${conversationId}/files/`);
            const files = await response.json();
            
            // Clear existing message files
            const messageFilesContainer = document.getElementById('message-files');
            if (!messageFilesContainer) {
                console.warn('[Chat] message-files container not found');
                return;
            }
            messageFilesContainer.innerHTML = '';
            
            // Add message files to the container
            files.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.className = 'message-file';
                fileItem.textContent = file.name;
                
                // Add click handler to download the file
                fileItem.addEventListener('click', () => {
                    downloadFile(file.url);
                });
                
                messageFilesContainer.appendChild(fileItem);
            });
        } catch (error) {
            console.error('Error loading message files:', error);
        }
    }

    // Function to download a file
    function downloadFile(fileUrl) {
        // Implement the logic to download the file from the given URL
        console.log('Downloading file:', fileUrl);
    }

    // Add a function to test the file upload API directly for debugging
    window.testFileUpload = async function(conversationId) {
        // Create a simple test file
        const blob = new Blob(['Test file content'], { type: 'text/plain' });
        const file = new File([blob], 'test-upload.txt', { type: 'text/plain' });
        
        console.log('Starting test upload with file:', file);
        console.log('Using conversation ID:', conversationId);
        
        try {
            const result = await uploadFileToServer(file, conversationId);
            console.log('Test upload successful:', result);
            alert(`Test upload successful! File ID: ${result.id}`);
            return result;
        } catch (error) {
            console.error('Test upload failed:', error);
            alert(`Test upload failed: ${error.message}`);
        }
    };
    
    // Function to load agent settings including turbo mode
    async function loadAgentSettings() {
        try {
            const response = await fetch('/accounts/agent-settings/', {
                method: 'GET',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    // Set turbo mode toggle state
                    const turboModeToggle = document.getElementById('turbo-mode-toggle');
                    if (turboModeToggle) {
                        turboModeToggle.checked = data.turbo_mode;
                        console.log('Turbo mode loaded:', data.turbo_mode);
                        
                        // Update role dropdown visibility based on turbo mode
                        updateRoleDropdownVisibility(data.turbo_mode);
                    }
                    
                    // Set role dropdown value if not in turbo mode
                    if (!data.turbo_mode && data.agent_role) {
                        if (typeof setCustomDropdownValue === 'function') {
                            setCustomDropdownValue('role-dropdown', data.agent_role);
                        } else {
                            // Fallback for old select dropdown
                            const roleDropdown = document.getElementById('role-dropdown');
                            if (roleDropdown && roleDropdown.tagName === 'SELECT') {
                                roleDropdown.value = data.agent_role;
                            }
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error loading agent settings:', error);
        }
    }
    
    // Function to update role dropdown visibility based on turbo mode
    function updateRoleDropdownVisibility(turboModeEnabled) {
        // For custom dropdown wrapper
        const roleDropdownWrapper = document.getElementById('role-dropdown-wrapper');
        if (roleDropdownWrapper) {
            roleDropdownWrapper.style.display = turboModeEnabled ? 'none' : 'block';
        } else {
            // Fallback for old select dropdown
            const roleDropdown = document.getElementById('role-dropdown');
            if (roleDropdown) {
                roleDropdown.style.display = turboModeEnabled ? 'none' : 'block';
            }
        }
    }
    
    // Add event listener for turbo mode toggle
    const turboModeToggle = document.getElementById('turbo-mode-toggle');
    if (turboModeToggle) {
        turboModeToggle.addEventListener('change', function() {
            const isEnabled = this.checked;
            console.log('Turbo mode toggled:', isEnabled);
            
            // Update role dropdown visibility
            updateRoleDropdownVisibility(isEnabled);
        });
    }
    
    // Helper function to create recording indicator
    function createRecordingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'audio-recording-indicator';
        
        // Create waveform
        const waveform = document.createElement('div');
        waveform.className = 'audio-waveform';
        
        // Add 20 bars for the waveform
        for (let i = 0; i < 20; i++) {
            const bar = document.createElement('div');
            bar.className = 'waveform-bar';
            waveform.appendChild(bar);
        }
        
        // Create time display
        const timeDisplay = document.createElement('div');
        timeDisplay.className = 'recording-time';
        timeDisplay.textContent = '00:00';
        
        indicator.appendChild(waveform);
        indicator.appendChild(timeDisplay);
        
        return indicator;
    }
    
    // Helper function to send audio message
    async function sendAudioMessage(audioFile) {
        // Add user message with audio indicator
        const audioIndicator = document.createElement('div');
        audioIndicator.className = 'message-audio';
        audioIndicator.innerHTML = `
            <div class="message-audio-container">
                <div class="message-audio-header">
                    <i class="fas fa-microphone" style="font-size: 14px;"></i>
                    Voice message
                </div>
                <div class="audio-transcription" style="display: none;">
                    Transcribing...
                </div>
            </div>
        `;
        
        const messageElement = addMessageToChat('user', '', { 
            audioIndicator: audioIndicator,
            file: audioFile 
        });
        
        // Store reference to update transcription later
        if (messageElement) {
            window.lastAudioMessageElement = messageElement;
        }
        
        // Upload audio file
        const formData = new FormData();
        formData.append('file', audioFile);
        formData.append('conversation_id', currentConversationId || '');
        
        try {
            const response = await fetch('/api/files/upload/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: formData
            });
            
            if (!response.ok) {
                throw new Error('Failed to upload audio file');
            }
            
            const fileData = await response.json();
            console.log('Audio file uploaded:', fileData);
            
            // Show transcription loading state
            if (window.lastAudioMessageElement) {
                const transcriptionDiv = window.lastAudioMessageElement.querySelector('.audio-transcription');
                if (transcriptionDiv) {
                    transcriptionDiv.style.display = 'block';
                }
            }
            
            // Get transcription from the API
            let transcription = null;
            try {
                console.log('Fetching transcription for file:', fileData.id);
                const transcriptionResponse = await fetch(`/api/files/transcribe/${fileData.id}/`, {
                    method: 'GET',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken'),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                
                console.log('Transcription response status:', transcriptionResponse.status);
                
                if (transcriptionResponse.ok) {
                    const transcriptionData = await transcriptionResponse.json();
                    console.log('Transcription received:', transcriptionData);
                    transcription = transcriptionData.transcription;
                    
                    // Update the audio message with transcription
                    if (window.lastAudioMessageElement) {
                        const transcriptionDiv = window.lastAudioMessageElement.querySelector('.audio-transcription');
                        console.log('Found transcription div:', transcriptionDiv);
                        if (transcriptionDiv && transcription) {
                            transcriptionDiv.innerHTML = transcription;
                            transcriptionDiv.style.display = 'block';
                            console.log('Updated transcription display with:', transcription);
                        }
                    } else {
                        console.log('No lastAudioMessageElement found');
                    }
                } else {
                    const errorData = await transcriptionResponse.text();
                    console.error('Transcription failed:', transcriptionResponse.status, errorData);
                    // Show error in UI
                    if (window.lastAudioMessageElement) {
                        const transcriptionDiv = window.lastAudioMessageElement.querySelector('.audio-transcription');
                        if (transcriptionDiv) {
                            transcriptionDiv.textContent = 'Transcription failed';
                            transcriptionDiv.style.display = 'block';
                            transcriptionDiv.style.color = '#ef4444';
                        }
                    }
                }
            } catch (error) {
                console.error('Error getting transcription:', error);
                // Show error in UI
                if (window.lastAudioMessageElement) {
                    const transcriptionDiv = window.lastAudioMessageElement.querySelector('.audio-transcription');
                    if (transcriptionDiv) {
                        transcriptionDiv.textContent = 'Transcription error';
                        transcriptionDiv.style.display = 'block';
                        transcriptionDiv.style.color = '#ef4444';
                    }
                }
            }
            
            // Send message via WebSocket with audio file reference
            if (socket && isSocketConnected) {
                // Use transcription as message content if available
                const messageContent = transcription || '[Voice Message]';
                
                const messageData = {
                    type: 'message',
                    message: messageContent,
                    conversation_id: currentConversationId,
                    project_id: currentProjectId,
                    file: {
                        id: fileData.id,
                        name: audioFile.name,
                        type: audioFile.type,
                        size: audioFile.size
                    },
                    user_role: getCurrentUserRole(),
                    turbo_mode: document.getElementById('turbo-mode-toggle')?.checked || false
                };
                
                socket.send(JSON.stringify(messageData));
            }
            
        } catch (error) {
            console.error('Error sending audio message:', error);
            showToast('Failed to send audio message', 'error');
        }
    }
    
    // Helper function to format file size
    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        else if (bytes < 1048576) return Math.round(bytes / 1024) + ' KB';
        else return Math.round(bytes / 1048576) + ' MB';
    }
    
    // Helper function to extract audio transcription from AI response
    function extractAudioTranscription(content) {
        // Match pattern: [Audio Transcription of filename]: transcribed text
        // Look for the transcription pattern and capture everything after it
        const match = content.match(/\[Audio Transcription of [^\]]+\]:\s*\n*(.+?)$/s);
        if (match && match[1]) {
            // Extract just the transcribed text, stopping at the next paragraph or end
            const transcribedText = match[1].split(/\n\n/)[0].trim();
            console.log('Extracted transcription:', transcribedText);
            return transcribedText;
        }
        console.log('No transcription found in:', content);
        return null;
    }
    
    // Helper function to get current user role
    function getCurrentUserRole() {
        const roleDropdown = document.querySelector('#role-dropdown-wrapper .custom-dropdown-item.selected');
        return roleDropdown ? roleDropdown.dataset.value : 'product_analyst';
    }
});