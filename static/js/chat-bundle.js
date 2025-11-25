/**
 * Chat experience bundle.
 * Combines the legacy chat, artifacts, and settings scripts into one file
 * for easier debugging and simplified template wiring.
 *
 * Sections are concatenated in the order they originally loaded:
 *  - chat.js
 *  - artifacts.js
 *  - artifacts-loader.js
 *  - artifacts-editor.js
 *  - design-loader.js
 *  - custom-dropdown.js
 *  - role-handler.js
 *  - model-handler.js
 *  - turbo-handler.js
 *  - app-loader.js (fallback helpers)
 */

/* ==== Begin: chat.js ==== */
document.addEventListener('DOMContentLoaded', () => {
    // Initialize file streaming debug globals
    window.FILE_STREAM_DEBUG = true;
    window.FILE_STREAM_CHUNKS = [];
    window.FILE_STREAM_CONTENT = '';
    console.log('🎯 FILE STREAMING DEBUG MODE ENABLED');
    console.log('🎯 File content will be logged to console automatically');
    console.log('🎯 Access chunks: window.FILE_STREAM_CHUNKS');
    console.log('🎯 Access full content: window.FILE_STREAM_CONTENT');
    
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
    // Make currentProjectId globally accessible for ArtifactsLoader
    window.currentProjectId = null;
    let socket = null;
    let isSocketConnected = false;
    let messageQueue = [];
    let isStreaming = false; // Track whether we're currently streaming a response
    let stopRequested = false; // Track if user has already requested to stop generation
    
    // Chunk reassembly tracking
    let chunkBuffers = {};  // Store partial chunks by sequence number
    let expectedSequence = 0;  // Track expected sequence number

    const pendingToolCalls = {};
    
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
    
    // Extract project ID from path
    const pathProjectId = extractProjectIdFromPath();
    
    if (!pathProjectId) {
        throw new Error('No project ID found in path. Expected format: /chat/project/{id}/');
    }
    
    currentProjectId = pathProjectId;
    window.currentProjectId = currentProjectId;
    console.log('Extracted project ID from path:', currentProjectId);
    
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
    
    // Variables for @ mention functionality
    let mentionDropdown = null;
    let mentionStartIndex = -1;
    let selectedMentionIndex = 0;
    let mentionFiles = [];

    // Auto-resize the text area based on content
    chatInput.addEventListener('input', function(e) {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        
        // Check for @file mentions
        const cursorPosition = this.selectionStart;
        const textBeforeCursor = this.value.substring(0, cursorPosition);
        
        // Look for @file pattern
        const atFileMatch = textBeforeCursor.match(/@file(\S*)$/);
        
        // Check if we should show mention dropdown
        if (atFileMatch) {
            // Found @file pattern at the end of text before cursor
            const searchQuery = atFileMatch[1]; // Text after @file
            mentionStartIndex = textBeforeCursor.length - atFileMatch[0].length;
            showMentionDropdown(searchQuery);
        } else {
            hideMentionDropdown();
        }
    });
    
    // Handle Enter key press in the textarea
    chatInput.addEventListener('keydown', function(e) {
        // Handle navigation in mention dropdown
        if (mentionDropdown && mentionDropdown.style.display !== 'none') {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedMentionIndex = Math.min(selectedMentionIndex + 1, mentionFiles.length - 1);
                updateMentionSelection();
                return;
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedMentionIndex = Math.max(selectedMentionIndex - 1, 0);
                updateMentionSelection();
                return;
            } else if (e.key === 'Enter' || e.key === 'Tab') {
                e.preventDefault();
                if (mentionFiles.length > 0) {
                    selectMentionFile(mentionFiles[selectedMentionIndex]);
                }
                return;
            } else if (e.key === 'Escape') {
                e.preventDefault();
                hideMentionDropdown();
                return;
            }
        }
        
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
        // Reset conversation ID but keep project ID
        currentConversationId = null;
        
        // Project ID should always be available from path
        const pathProjectId = extractProjectIdFromPath();
        if (!pathProjectId) {
            console.error('No project ID found in path during new chat creation');
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
        
        // Update URL to remove conversation_id param
        const url = new URL(window.location);
        url.searchParams.delete('conversation_id');
        window.history.pushState({}, '', url);
        
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
                    const stream = await navigator.mediaDevices.getUserMedia({ 
                        audio: {
                            echoCancellation: false,
                            noiseSuppression: false,
                            autoGainControl: false
                        }
                    });
                    
                    console.log('🎙️ Got audio stream:', {
                        active: stream.active,
                        tracks: stream.getTracks().map(t => ({
                            kind: t.kind,
                            enabled: t.enabled,
                            muted: t.muted,
                            readyState: t.readyState
                        }))
                    });
                    
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];
                    
                    // Create and show waveform indicator
                    recordingIndicator = createRecordingIndicator();
                    const messagesContainer = document.getElementById('chat-messages');
                    messagesContainer.appendChild(recordingIndicator);
                    messagesContainer.scrollTop = messagesContainer.scrollHeight;
                    
                    // Set up Web Speech API for live transcription
                    let recognition = null;
                    let finalTranscript = '';
                    let interimTranscript = '';
                    
                    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
                        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                        recognition = new SpeechRecognition();
                        
                        recognition.continuous = true;
                        recognition.interimResults = true;
                        recognition.lang = 'en-US';
                        
                        recognition.onstart = () => {
                            console.log('Speech recognition started');
                        };
                        
                        recognition.onresult = (event) => {
                            interimTranscript = '';
                            
                            for (let i = event.resultIndex; i < event.results.length; i++) {
                                const transcript = event.results[i][0].transcript;
                                
                                if (event.results[i].isFinal) {
                                    finalTranscript += transcript + ' ';
                                } else {
                                    interimTranscript += transcript;
                                }
                            }
                            
                            // Update transcription display
                            if (recordingIndicator && recordingIndicator.transcriptionArea) {
                                const displayText = finalTranscript + '<span style="color: #94a3b8; font-style: italic;">' + interimTranscript + '</span>';
                                recordingIndicator.transcriptionArea.innerHTML = displayText || '<span style="color: #94a3b8; font-style: italic;">Listening...</span>';
                                
                                // Show send button if there's any transcribed text
                                if (finalTranscript.trim() || interimTranscript.trim()) {
                                    recordingIndicator.sendBtn.style.display = 'block';
                                }
                            }
                        };
                        
                        recognition.onerror = (event) => {
                            console.error('Speech recognition error:', event.error);
                            if (recordingIndicator && recordingIndicator.transcriptionArea) {
                                recordingIndicator.transcriptionArea.innerHTML = '<span style="color: #ef4444;">Error: ' + event.error + '</span>';
                            }
                        };
                        
                        recognition.onend = () => {
                            console.log('Speech recognition ended');
                        };
                        
                        // Start recognition
                        try {
                            recognition.start();
                        } catch (e) {
                            console.error('Failed to start speech recognition:', e);
                        }
                        
                        // Store recognition instance for cleanup
                        window.currentRecognition = recognition;
                    } else {
                        console.warn('Web Speech API not supported');
                        if (recordingIndicator && recordingIndicator.transcriptionArea) {
                            recordingIndicator.transcriptionArea.innerHTML = '<span style="color: #f59e0b;">Live transcription not supported in this browser</span>';
                        }
                    }
                    
                    // Set up audio analysis for voice-reactive waveform
                    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    console.log('AudioContext created, state:', audioContext.state);
                    
                    // Resume audio context if suspended (browser security)
                    if (audioContext.state === 'suspended') {
                        console.log('AudioContext suspended, resuming...');
                        await audioContext.resume();
                        console.log('AudioContext resumed, new state:', audioContext.state);
                    }
                    
                    const analyser = audioContext.createAnalyser();
                    const microphone = audioContext.createMediaStreamSource(stream);
                    
                    // Store analyser globally for debugging
                    window.debugAnalyser = analyser;
                    window.debugMicrophone = microphone;
                    
                    console.log('Audio analysis setup:', {
                        analyserCreated: !!analyser,
                        microphoneCreated: !!microphone,
                        frequencyBinCount: analyser.frequencyBinCount,
                        streamActive: stream.active,
                        audioTracks: stream.getAudioTracks().length
                    });
                    
                    analyser.smoothingTimeConstant = 0.8;
                    analyser.fftSize = 256; // Increase for better frequency resolution
                    analyser.minDecibels = -90;
                    analyser.maxDecibels = -10;
                    
                    // Connect microphone -> analyser
                    microphone.connect(analyser);
                    
                    // Test the audio by checking if we're getting data
                    setTimeout(() => {
                        const testArray = new Uint8Array(analyser.frequencyBinCount);
                        analyser.getByteFrequencyData(testArray);
                        const testSum = testArray.reduce((a, b) => a + b, 0);
                        console.log('🔊 Audio routing test:', {
                            sum: testSum,
                            avg: testSum / testArray.length,
                            contextState: audioContext.state,
                            analyserConnected: true
                        });
                    }, 100);
                    
                    console.log('Audio routing established:', {
                        microphoneConnected: true,
                        analyserFftSize: analyser.fftSize,
                        frequencyBinCount: analyser.frequencyBinCount
                    });
                    
                    // Store audio context for cleanup
                    window.currentAudioContext = audioContext;
                    
                    // Simple waveform animation
                    let frameCount = 0;
                    let animationRunning = false;
                    
                    function animateWaveform() {
                        // Debug first frame
                        if (!animationRunning) {
                            console.log('🚀 First animation frame:', {
                                hasIndicator: !!recordingIndicator,
                                hasRecorder: !!mediaRecorder,
                                recorderState: mediaRecorder?.state,
                                hasAnalyser: !!analyser,
                                analyserBinCount: analyser?.frequencyBinCount
                            });
                            animationRunning = true;
                        }
                        
                        if (!recordingIndicator || !mediaRecorder || mediaRecorder.state !== 'recording') {
                            console.log('❌ Animation stopped - missing requirements');
                            animationRunning = false;
                            return;
                        }
                        
                        try {
                            const dataArray = new Uint8Array(analyser.frequencyBinCount);
                            analyser.getByteFrequencyData(dataArray);
                            
                            // Get average volume
                            let sum = 0;
                            let max = 0;
                            for (let i = 0; i < dataArray.length; i++) {
                                sum += dataArray[i];
                                max = Math.max(max, dataArray[i]);
                            }
                            const average = sum / dataArray.length;
                            
                            // Log every 30 frames (0.5 second)
                            if (frameCount % 30 === 0) {
                                console.log('🎤 Audio:', {
                                    avg: average.toFixed(1),
                                    max: max,
                                    frame: frameCount,
                                    firstValues: dataArray.slice(0, 5).join(',')
                                });
                            }
                            frameCount++;
                            
                            // Update bars
                            const bars = recordingIndicator.querySelectorAll('.waveform-bar');
                            if (bars.length === 0) {
                                console.error('❌ No waveform bars found!');
                                return;
                            }
                            
                            bars.forEach((bar, i) => {
                                const index = Math.floor((i / bars.length) * dataArray.length);
                                const value = dataArray[index] || 0;
                                const height = 3 + (value / 255) * 30;
                                bar.style.height = height + 'px';
                            });
                            
                            requestAnimationFrame(animateWaveform);
                        } catch (error) {
                            console.error('❌ Animation error:', error);
                            animationRunning = false;
                        }
                    }
                    
                    // Start the animation loop
                    console.log('🎯 Starting waveform animation...');
                    
                    // Add test function to window for debugging
                    window.testAudioLevel = () => {
                        const testData = new Uint8Array(analyser.frequencyBinCount);
                        analyser.getByteFrequencyData(testData);
                        const sum = testData.reduce((a, b) => a + b, 0);
                        const avg = sum / testData.length;
                        console.log('Manual audio test:', {
                            average: avg,
                            max: Math.max(...testData),
                            analyserState: analyser.context.state,
                            dataLength: testData.length
                        });
                        return avg;
                    };
                    
                    mediaRecorder.ondataavailable = (event) => {
                        audioChunks.push(event.data);
                    };
                    
                    mediaRecorder.onstop = async () => {
                        // Stop all tracks
                        stream.getTracks().forEach(track => track.stop());
                        
                        // Clean up audio context
                        if (window.currentAudioContext) {
                            window.currentAudioContext.close();
                            window.currentAudioContext = null;
                        }
                        
                        // Stop speech recognition
                        if (window.currentRecognition) {
                            window.currentRecognition.stop();
                            window.currentRecognition = null;
                        }
                        
                        // Get final transcript before removing indicator
                        let transcriptToSend = '';
                        if (recordingIndicator && recordingIndicator.transcriptionArea) {
                            // Extract text content without HTML
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = recordingIndicator.transcriptionArea.innerHTML;
                            transcriptToSend = tempDiv.textContent || tempDiv.innerText || '';
                            transcriptToSend = transcriptToSend.replace('Listening...', '').trim();
                        }
                        
                        // Remove recording indicator
                        if (recordingIndicator) {
                            recordingIndicator.remove();
                            recordingIndicator = null;
                        }
                        
                        // Check if recording was cancelled
                        if (window.recordingCancelled) {
                            window.recordingCancelled = false;
                            console.log('Recording cancelled by user');
                        } else {
                            // Always create the audio blob for consistency
                            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                            const audioFile = new File([audioBlob], `recording_${Date.now()}.webm`, { type: 'audio/webm' });
                            
                            console.log('Audio recording completed:', audioFile.name, 'size:', audioFile.size);
                            
                            // Send audio message with transcript (if available)
                            await sendAudioMessage(audioFile, transcriptToSend);
                        }
                        
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
                    
                    // Start the waveform animation after recorder is started
                    animateWaveform();
                    
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
                window.currentProjectId = currentProjectId;
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
            
            // AUTOMATIC LOGGING FOR ALL FILE NOTIFICATIONS AT WEBSOCKET LEVEL
            if (data.notification_type === 'file_stream' || (data.is_notification && data.notification_type === 'file_stream')) {
                console.log('\n' + '🔴'.repeat(50));
                console.log('🔴🔴🔴 RAW WEBSOCKET FILE MESSAGE RECEIVED! 🔴🔴🔴');
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
                    const lastAssistantMessage = getLastAssistantMessage();
                    if (data.chunk === '' && !data.is_final && lastAssistantMessage && !data.is_notification) {
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
                        const assistantMessage = getLastAssistantMessage();
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
                    
                    // Check if this is a token exhaustion error
                    if (data.message && (
                        data.message.includes('token limit') || 
                        data.message.includes('tokens. Please upgrade') ||
                        data.message.includes('reached your') ||
                        data.message.includes('token quota')
                    )) {
                        showTokenExhaustedPopup();
                    }
                    
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
        
        // AUTOMATIC FILE CONSOLE LOGGING
        if (data.notification_type === 'file_stream' && data.file_type === 'prd') {
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
            if (!window.FILE_STREAM_CONTENT) {
                window.FILE_STREAM_CONTENT = '';
            }
            if (!window.FILE_STREAM_CHUNKS) {
                window.FILE_STREAM_CHUNKS = [];
            }
            if (data.content_chunk) {
                window.FILE_STREAM_CONTENT += data.content_chunk;
                window.FILE_STREAM_CHUNKS.push({
                    timestamp: new Date().toISOString(),
                    length: data.content_chunk.length,
                    content: data.content_chunk,
                    is_complete: data.is_complete
                });
            }
            console.log('🎯 Total file content so far:', window.FILE_STREAM_CONTENT.length, 'chars');
            console.log('🎯 Total chunks received:', window.FILE_STREAM_CHUNKS.length);
            console.log('🎯 Access full content: window.FILE_STREAM_CONTENT');
            console.log('🎯 Access all chunks: window.FILE_STREAM_CHUNKS');
        }
        
        // AUTOMATIC FILE CONSOLE LOGGING
        if (data.notification_type === 'file_stream' && data.file_type === 'implementation') {
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
            if (!window.FILE_STREAM_CONTENT) {
                window.FILE_STREAM_CONTENT = '';
            }
            if (!window.FILE_STREAM_CHUNKS) {
                window.FILE_STREAM_CHUNKS = [];
            }
            if (data.content_chunk) {
                window.FILE_STREAM_CONTENT += data.content_chunk;
                window.FILE_STREAM_CHUNKS.push({
                    timestamp: new Date().toISOString(),
                    length: data.content_chunk.length,
                    content: data.content_chunk,
                    is_complete: data.is_complete
                });
            }
            console.log('💚 Total file content so far:', window.FILE_STREAM_CONTENT.length, 'chars');
            console.log('💚 Total chunks received:', window.FILE_STREAM_CHUNKS.length);
            console.log('💚 Access full content: window.FILE_STREAM_CONTENT');
            console.log('💚 Access all chunks: window.FILE_STREAM_CHUNKS');
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
                window.currentProjectId = currentProjectId;
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
        const assistantMessage = getLastAssistantMessage();
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

    function getLastAssistantMessage() {
        const assistants = messageContainer.querySelectorAll('.message.assistant');
        if (!assistants.length) {
            return null;
        }
        return assistants[assistants.length - 1];
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
            const assistantMessage = getLastAssistantMessage();
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
        
        // First check the left menu submenu
        const roleSubmenu = document.getElementById('role-submenu');
        if (roleSubmenu) {
            const selectedRole = roleSubmenu.querySelector('.submenu-option.selected');
            if (selectedRole) {
                userRole = selectedRole.getAttribute('data-value') || 'default';
            }
        } else if (typeof getCustomDropdownValue === 'function' && document.getElementById('role-dropdown')) {
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
        
        // Add mentioned files if any
        if (window.mentionedFiles && Object.keys(window.mentionedFiles).length > 0) {
            messageData.mentioned_files = window.mentionedFiles;
            // Clear mentioned files after adding to message
            window.mentionedFiles = {};
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
    function showFunctionCallSuccess(functionName, type, details = {}) {
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
        } else if (type === 'error') {
            message = details.errorMessage || 'Function call failed. Check the tool output for details.';
        } else {
            message = 'Function call completed successfully!';
        }
        
        const iconHtml = type === 'error'
            ? '<div class="function-call-icon error" style="background: #4b1f1f; color: #f87171;">⚠️</div>'
            : '<div class="function-call-icon">✓</div>';

        successElement.innerHTML = `
            ${iconHtml}
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

    // Function to set sidebar state - COMMENTED OUT: Using new sidebar.js system instead
    /*
    function setSidebarState(collapsed) {
        console.log("SIDEBAR!!!")
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
    */

    // Close sidebar when overlay is clicked (mobile) - COMMENTED OUT: Handled by sidebar.js
    /*
    sidebarOverlay.addEventListener('click', () => {
        setSidebarState(true); // Collapse sidebar
    });
    */

    // Add a mobile toggle button - COMMENTED OUT: Handled by sidebar.js
    /*
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
    */

    // Call the initialization functions
    // Mobile toggle - COMMENTED OUT: Handled by sidebar.js
    /*
    if (window.innerWidth <= 768) {
        console.log("Mobile Toggle")
        addMobileToggle();
    }
    */

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
        if (!getLastAssistantMessage()) {
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
                    const projectId = currentProjectId || extractProjectIdFromPath();
                    
                    if (projectId) {
                        if (tabType === 'features' && typeof window.ArtifactsLoader.loadFeatures === 'function') {
                            window.ArtifactsLoader.loadFeatures(projectId);
                        } else if (tabType === 'personas' && typeof window.ArtifactsLoader.loadPersonas === 'function') {
                            window.ArtifactsLoader.loadPersonas(projectId);
                        } else if (tabType === 'prd' && typeof window.ArtifactsLoader.loadFileBrowser === 'function') {
                            // Load file browser for PRD
                            window.ArtifactsLoader.loadFileBrowser(projectId);
                        } else if (tabType === 'implementation' && typeof window.ArtifactsLoader.loadFileBrowser === 'function') {
                            // Load file browser for Implementation
                            window.ArtifactsLoader.loadFileBrowser(projectId);
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
        
        // Create top row with waveform and controls
        const topRow = document.createElement('div');
        topRow.style.cssText = 'display: flex; align-items: center; gap: 8px; width: 100%;';
        
        // Create waveform
        const waveform = document.createElement('div');
        waveform.className = 'audio-waveform';
        
        // Add 20 bars for the waveform
        for (let i = 0; i < 20; i++) {
            const bar = document.createElement('div');
            bar.className = 'waveform-bar';
            bar.style.height = '4px'; // Set smaller initial height
            waveform.appendChild(bar);
        }
        
        // Create time display
        const timeDisplay = document.createElement('div');
        timeDisplay.className = 'recording-time';
        timeDisplay.textContent = '00:00';
        
        // Create cancel button
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'recording-cancel-btn';
        cancelBtn.innerHTML = '<i class="fas fa-times"></i>';
        cancelBtn.title = 'Cancel recording';
        cancelBtn.onclick = () => {
            // Stop recording without saving
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                // Set flag to indicate cancellation
                window.recordingCancelled = true;
                mediaRecorder.stop();
            }
        };
        
        topRow.appendChild(waveform);
        topRow.appendChild(timeDisplay);
        topRow.appendChild(cancelBtn);
        
        // Create transcription row
        const transcriptionRow = document.createElement('div');
        transcriptionRow.style.cssText = 'display: flex; align-items: center; gap: 8px; margin-top: 12px;';
        
        // Create transcription area
        const transcriptionArea = document.createElement('div');
        transcriptionArea.className = 'live-transcription';
        transcriptionArea.style.cssText = 'flex: 1; padding: 8px 12px; background: rgba(255,255,255,0.05); border-radius: 6px; min-height: 40px; color: #e2e8f0; font-size: 14px; line-height: 1.4;';
        transcriptionArea.innerHTML = '<span style="color: #94a3b8; font-style: italic;">Listening...</span>';
        
        // Create send button (initially hidden)
        const sendBtn = document.createElement('button');
        sendBtn.className = 'recording-send-btn';
        sendBtn.style.cssText = 'width: 36px; height: 36px; padding: 0; background: #3b82f6; color: white; border: none; border-radius: 50%; font-size: 14px; cursor: pointer; display: none; align-self: center; flex-shrink: 0;';
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
        sendBtn.title = 'Send message';
        sendBtn.onclick = () => {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
            }
        };
        
        transcriptionRow.appendChild(transcriptionArea);
        transcriptionRow.appendChild(sendBtn);
        
        indicator.appendChild(topRow);
        indicator.appendChild(transcriptionRow);
        
        // Store references for easy access
        indicator.transcriptionArea = transcriptionArea;
        indicator.sendBtn = sendBtn;
        
        return indicator;
    }
    
    // Helper function to send audio message
    async function sendAudioMessage(audioFile, liveTranscript = '') {
        // Add user message with audio indicator
        const audioIndicator = document.createElement('div');
        audioIndicator.className = 'message-audio';
        audioIndicator.innerHTML = `
            <div class="message-audio-container">
                <div class="message-audio-header">
                    <i class="fas fa-microphone" style="font-size: 14px;"></i>
                    Voice message
                </div>
                ${liveTranscript ? `
                    <div class="audio-transcription">
                        ${liveTranscript}
                    </div>
                ` : `
                    <div class="audio-transcription" style="display: none;">
                        Transcribing...
                    </div>
                `}
            </div>
        `;
        
        // If we have a live transcript, send it as a message with audio styling
        if (liveTranscript && liveTranscript.trim()) {
            const messageElement = addMessageToChat('user', '', { 
                audioIndicator: audioIndicator
            });
            
            // Send the transcribed text to the server
            sendMessageToServer(liveTranscript);
            return;
        }
        
        // Otherwise, proceed with file upload
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
            alert('Failed to send audio message');
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
    
    // @ Mention Helper Functions
    function showMentionDropdown(searchQuery) {
        // Create dropdown if it doesn't exist
        if (!mentionDropdown) {
            mentionDropdown = document.createElement('div');
            mentionDropdown.className = 'mention-dropdown';
            mentionDropdown.style.cssText = `
                position: absolute;
                background: #1a1a1a;
                border: 1px solid #333;
                border-radius: 4px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.5);
                max-height: 200px;
                overflow-y: auto;
                z-index: 1000;
                min-width: 250px;
            `;
            document.body.appendChild(mentionDropdown);
        }
        
        // Position the dropdown near the cursor
        const inputRect = chatInput.getBoundingClientRect();
        const inputStyle = window.getComputedStyle(chatInput);
        const lineHeight = parseInt(inputStyle.lineHeight);
        
        // Calculate approximate position based on cursor
        mentionDropdown.style.left = inputRect.left + 'px';
        mentionDropdown.style.bottom = (window.innerHeight - inputRect.top + 5) + 'px';
        
        // Fetch files from API
        fetchMentionFiles(searchQuery);
    }
    
    function hideMentionDropdown() {
        if (mentionDropdown) {
            mentionDropdown.style.display = 'none';
            mentionFiles = [];
            selectedMentionIndex = 0;
        }
    }
    
    async function fetchMentionFiles(searchQuery) {
        if (!currentProjectId) {
            console.error('No project ID available for fetching files');
            return;
        }
        
        try {
            const url = `/projects/${currentProjectId}/api/files/mentions/?q=${encodeURIComponent(searchQuery)}`;
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            mentionFiles = data.files || [];
            selectedMentionIndex = 0;
            
            // Update dropdown content
            updateMentionDropdown();
            
        } catch (error) {
            console.error('Error fetching mention files:', error);
            hideMentionDropdown();
        }
    }
    
    function updateMentionDropdown() {
        if (!mentionDropdown || mentionFiles.length === 0) {
            hideMentionDropdown();
            return;
        }
        
        // Clear existing content
        mentionDropdown.innerHTML = '';
        
        // Add files to dropdown
        mentionFiles.forEach((file, index) => {
            const item = document.createElement('div');
            item.className = 'mention-item';
            item.style.cssText = `
                padding: 8px 12px;
                cursor: pointer;
                border-bottom: 1px solid #333;
                ${index === selectedMentionIndex ? 'background-color: #2a2a2a;' : ''}
            `;
            
            item.innerHTML = `
                <div style="font-weight: 500; color: #e0e0e0;">${file.name}</div>
                <div style="font-size: 12px; color: #999;">${file.type} • Updated ${file.updated_at}</div>
            `;
            
            item.addEventListener('click', () => selectMentionFile(file));
            item.addEventListener('mouseenter', () => {
                selectedMentionIndex = index;
                updateMentionSelection();
            });
            
            mentionDropdown.appendChild(item);
        });
        
        // Show the dropdown
        mentionDropdown.style.display = 'block';
    }
    
    function updateMentionSelection() {
        const items = mentionDropdown.querySelectorAll('.mention-item');
        items.forEach((item, index) => {
            if (index === selectedMentionIndex) {
                item.style.backgroundColor = '#2a2a2a';
            } else {
                item.style.backgroundColor = '';
            }
        });
    }
    
    async function selectMentionFile(file) {
        if (!file) return;
        
        try {
            // Get the file content
            const url = `/projects/${currentProjectId}/api/files/${file.id}/content/`;
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const fileData = await response.json();
            
            // Remove the @mention from the input
            const cursorPosition = chatInput.selectionStart;
            const textBeforeMention = chatInput.value.substring(0, mentionStartIndex);
            const textAfterCursor = chatInput.value.substring(cursorPosition);
            
            // Add a reference to the file in the message
            const fileReference = `[@${file.name}](file:${file.id})`;
            
            // Update the input value with the file reference
            chatInput.value = textBeforeMention + fileReference + ' ' + textAfterCursor;
            
            // Set cursor position after the reference
            const newCursorPosition = textBeforeMention.length + fileReference.length + 1;
            chatInput.setSelectionRange(newCursorPosition, newCursorPosition);
            
            // Store the file content in a hidden data structure that will be sent with the message
            if (!window.mentionedFiles) {
                window.mentionedFiles = {};
            }
            window.mentionedFiles[file.id] = {
                id: file.id,
                name: file.name,
                type: file.type,
                content: fileData.content
            };
            
            console.log('Mentioned file stored:', file.name);
            
            // Trigger input event to resize textarea
            chatInput.dispatchEvent(new Event('input'));
            
            // Hide the dropdown
            hideMentionDropdown();
            
            // Focus back on the input
            chatInput.focus();
            
        } catch (error) {
            console.error('Error fetching file content:', error);
            alert('Failed to fetch file content');
        }
    }
    
    // Add styles for mention dropdown
    const mentionStyles = document.createElement('style');
    mentionStyles.textContent = `
        .mention-dropdown {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        
        .mention-item:hover {
            background-color: #f0f0f0;
        }
        
        .mention-item:last-child {
            border-bottom: none;
        }
    `;
    document.head.appendChild(mentionStyles);
    
    // Function to show token exhausted popup dynamically
    function showTokenExhaustedPopup() {
        // Check if popup already exists
        if (document.getElementById('dynamic-tokens-exhausted-popup')) {
            return;
        }
        
        // Get user tier info from window or default values
        const isFreeTier = window.isFreeTier !== undefined ? window.isFreeTier : true;
        
        const popup = document.createElement('div');
        popup.id = 'dynamic-tokens-exhausted-popup';
        popup.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); display: flex; align-items: center; justify-content: center; z-index: 10000;';
        
        popup.innerHTML = `
            <div style="background: #1f2937; border-radius: 12px; padding: 2rem; max-width: 500px; width: 90%; border: 1px solid #374151; position: relative;">
                <button onclick="document.getElementById('dynamic-tokens-exhausted-popup').remove()" style="position: absolute; top: 1rem; right: 1rem; background: none; border: none; color: #9ca3af; font-size: 1.5rem; cursor: pointer;">
                    <i class="fas fa-times"></i>
                </button>
                
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <i class="fas fa-exclamation-triangle" style="font-size: 3rem; color: #f59e0b; margin-bottom: 1rem; display: block;"></i>
                    <h2 style="color: #f3f4f6; font-size: 1.5rem; margin-bottom: 0.5rem;">Token Limit Reached</h2>
                    <p style="color: #9ca3af;">You've used all your available tokens</p>
                </div>
                
                ${isFreeTier ? `
                <div style="background: #111827; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem;">
                    <p style="color: #f3f4f6; margin-bottom: 0.5rem;">You've used your 100,000 free tokens.</p>
                    <p style="color: #9ca3af;">Upgrade to Pro to continue building with AI.</p>
                </div>
                
                <div style="background: linear-gradient(135deg, #9333ea 0%, #7c3aed 100%); padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
                    <h3 style="color: #ffffff; font-size: 1rem; margin-bottom: 0.5rem;">Pro Plan - $9/month</h3>
                    <ul style="color: #e9d5ff; list-style: none; padding: 0; margin: 0;">
                        <li style="margin-bottom: 0.25rem;"><i class="fas fa-check" style="margin-right: 0.5rem;"></i> 300,000 tokens per month</li>
                        <li style="margin-bottom: 0.25rem;"><i class="fas fa-check" style="margin-right: 0.5rem;"></i> Access to all AI models</li>
                        <li><i class="fas fa-check" style="margin-right: 0.5rem;"></i> Monthly token reset</li>
                    </ul>
                </div>
                ` : `
                <div style="background: #111827; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem;">
                    <p style="color: #f3f4f6; margin-bottom: 0.5rem;">You've used your monthly quota of 300,000 tokens.</p>
                    <p style="color: #9ca3af;">Purchase additional tokens or wait for your monthly reset.</p>
                </div>
                `}
                
                <div style="display: flex; gap: 1rem;">
                    <button onclick="document.getElementById('dynamic-tokens-exhausted-popup').remove()" style="flex: 1; background: #374151; color: #f3f4f6; border: none; padding: 0.75rem; border-radius: 8px; cursor: pointer; font-size: 1rem;">
                        Close
                    </button>
                    <a href="/subscriptions/" style="flex: 1; background: #10b981; color: white; border: none; padding: 0.75rem; border-radius: 8px; cursor: pointer; font-size: 1rem; text-align: center; text-decoration: none; display: block;">
                        ${isFreeTier ? 'Upgrade to Pro' : 'Buy More Tokens'}
                    </a>
                </div>
            </div>
        `;
        
        document.body.appendChild(popup);
    }
    
    // Make it available globally
    window.showTokenExhaustedPopup = showTokenExhaustedPopup;
});
/* ==== End: chat.js ==== */

/* ==== Begin: artifacts.js ==== */
/**
 * Artifacts Panel JavaScript
 * Handles the functionality for the resizable and collapsible artifacts panel
 */
document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const appContainer = document.querySelector('.app-container');
    const artifactsPanel = document.getElementById('artifacts-panel');
    const artifactsToggle = document.getElementById('artifacts-toggle');
    const resizeHandle = document.getElementById('resize-handle');
    const chatContainer = document.querySelector('.chat-container');
    
    // Get the artifacts button (now in HTML header)
    const artifactsButton = document.getElementById('artifacts-button');
    
    // If elements don't exist, exit early
    if (!artifactsPanel || !artifactsToggle || !resizeHandle || !artifactsButton) {
        console.warn('Artifacts panel elements not found');
        return;
    }
    
    // Initialize state
    let isResizing = false;
    let lastDownX = 0;
    let panelWidth = parseInt(getComputedStyle(artifactsPanel).width) || 350;
    
    // Check if panel should start expanded (from localStorage)
    const shouldBeExpanded = localStorage.getItem('artifacts_expanded') === 'true';
    if (shouldBeExpanded) {
        artifactsPanel.classList.add('expanded');
        appContainer.classList.add('artifacts-expanded');
        artifactsButton.classList.add('active');
        updateChatContainerPosition(true);
    }
    
    // Toggle panel visibility when floating button is clicked
    artifactsButton.addEventListener('click', function() {
        const isExpanded = artifactsPanel.classList.toggle('expanded');
        artifactsButton.classList.toggle('active');
        
        // Update app container class to adjust chat container
        if (isExpanded) {
            appContainer.classList.add('artifacts-expanded');
            
            // When opening the panel, load data for the currently active tab
            const activeTab = document.querySelector('.tab-button.active');
            if (activeTab) {
                const tabId = activeTab.getAttribute('data-tab');
                console.log(`[ArtifactsPanel] Panel opened, loading data for active tab: ${tabId}`);
                if (window.switchTab) {
                    window.switchTab(tabId);
                }
            }
        } else {
            appContainer.classList.remove('artifacts-expanded');
        }
        
        // Store state in localStorage
        localStorage.setItem('artifacts_expanded', isExpanded);
        
        // Update chat container position
        updateChatContainerPosition(isExpanded);
    });
    
    // Close panel when toggle button inside panel is clicked
    artifactsToggle.addEventListener('click', function() {
        artifactsPanel.classList.remove('expanded');
        artifactsButton.classList.remove('active');
        appContainer.classList.remove('artifacts-expanded');
        
        // Store state in localStorage
        localStorage.setItem('artifacts_expanded', false);
        
        // Update chat container position
        updateChatContainerPosition(false);
    });
    
    // Resize functionality
    resizeHandle.addEventListener('mousedown', function(e) {
        // Only allow resizing when panel is expanded
        if (!artifactsPanel.classList.contains('expanded')) {
            return;
        }
        
        isResizing = true;
        lastDownX = e.clientX;
        resizeHandle.classList.add('active');
        
        // Prevent text selection during resize
        document.body.style.userSelect = 'none';
        
        // Add event listeners for mouse movement and release
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        
        e.preventDefault();
    });
    
    // Set up tab switching event listeners - direct implementation
    document.querySelectorAll('.tab-button').forEach(button => {
        button.addEventListener('click', function() {
            const tabId = this.getAttribute('data-tab');
            
            // If switchTab is available in the window object, use it
            if (window.switchTab) {
                window.switchTab(tabId);
            } else {
                // Otherwise, use a simple tab switching implementation
                const tabButtons = document.querySelectorAll('.tab-button');
                const tabPanes = document.querySelectorAll('.tab-pane');
                
                // Remove active class from all buttons and panes
                tabButtons.forEach(btn => btn.classList.remove('active'));
                tabPanes.forEach(pane => pane.classList.remove('active'));
                
                // Add active class to the selected button and pane
                this.classList.add('active');
                const selectedPane = document.getElementById(tabId);
                if (selectedPane) {
                    selectedPane.classList.add('active');
                }
            }
        });
    });
    
    // Function to handle markdown rendering of content
    function renderMarkdownContent() {
        if (typeof marked !== 'undefined') {
            // Find all markdown-content elements in the artifacts panel
            const markdownElements = artifactsPanel.querySelectorAll('.markdown-content');
            
            markdownElements.forEach(element => {
                const rawContent = element.getAttribute('data-raw-content');
                if (rawContent) {
                    // Render the raw content as markdown
                    element.innerHTML = marked.parse(rawContent);
                }
            });
        }
    }
    
    // Event listener for when content is dynamically added to the panel
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList') {
                // Check if any new markdown content was added
                renderMarkdownContent();
            }
        });
    });
    
    // Start observing changes to the artifacts content
    const artifactsContent = document.querySelector('.artifacts-content');
    if (artifactsContent) {
        observer.observe(artifactsContent, { childList: true, subtree: true });
    }
    
    function handleMouseMove(e) {
        if (!isResizing) return;
        
        // Calculate new width (right panel, so we subtract)
        const offsetX = lastDownX - e.clientX;
        const newWidth = panelWidth + offsetX;
        
        // Calculate maximum width (75% of window width)
        const maxWidth = window.innerWidth * 0.75;
        
        // Limit minimum and maximum width
        if (newWidth >= 250 && newWidth <= maxWidth) {
            artifactsPanel.style.width = newWidth + 'px';
            
            // Update chat container position
            updateChatContainerPosition(true, newWidth);
        }
    }
    
    function handleMouseUp() {
        if (isResizing) {
            isResizing = false;
            resizeHandle.classList.remove('active');
            
            // Update stored width
            panelWidth = parseInt(getComputedStyle(artifactsPanel).width);
            
            // Store width in localStorage
            localStorage.setItem('artifacts_width', panelWidth);
            
            // Re-enable text selection
            document.body.style.userSelect = '';
            
            // Remove event listeners
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        }
    }
    
    // Touch support for mobile
    resizeHandle.addEventListener('touchstart', function(e) {
        // Only allow resizing when panel is expanded
        if (!artifactsPanel.classList.contains('expanded')) {
            return;
        }
        
        isResizing = true;
        lastDownX = e.touches[0].clientX;
        resizeHandle.classList.add('active');
        
        document.addEventListener('touchmove', handleTouchMove);
        document.addEventListener('touchend', handleTouchEnd);
        e.preventDefault();
    });
    
    function handleTouchMove(e) {
        if (!isResizing) return;
        
        const offsetX = lastDownX - e.touches[0].clientX;
        const newWidth = panelWidth + offsetX;
        const maxWidth = window.innerWidth * 0.75;
        
        if (newWidth >= 250 && newWidth <= maxWidth) {
            artifactsPanel.style.width = newWidth + 'px';
            updateChatContainerPosition(true, newWidth);
        }
        
        e.preventDefault();
    }
    
    function handleTouchEnd() {
        if (isResizing) {
            isResizing = false;
            resizeHandle.classList.remove('active');
            
            panelWidth = parseInt(getComputedStyle(artifactsPanel).width);
            localStorage.setItem('artifacts_width', panelWidth);
            
            document.removeEventListener('touchmove', handleTouchMove);
            document.removeEventListener('touchend', handleTouchEnd);
        }
    }
    
    // Function to update chat container position based on artifacts panel
    function updateChatContainerPosition(isExpanded, width) {
        if (!chatContainer) return;
        
        if (isExpanded) {
            const panelWidth = width || parseInt(getComputedStyle(artifactsPanel).width);
            // Update width and margin instead of right position
            chatContainer.style.width = `calc(100% - ${panelWidth}px)`;
            chatContainer.style.marginRight = `${panelWidth}px`;
        } else {
            // Reset to full width when panel is hidden
            chatContainer.style.width = '100%';
            chatContainer.style.marginRight = '0';
        }
    }
    
    // Load saved width from localStorage if available
    const savedWidth = localStorage.getItem('artifacts_width');
    if (savedWidth && !isNaN(parseInt(savedWidth))) {
        panelWidth = parseInt(savedWidth);
        artifactsPanel.style.width = panelWidth + 'px';
        
        // Only update chat container if panel is expanded
        if (artifactsPanel.classList.contains('expanded')) {
            updateChatContainerPosition(true, panelWidth);
        }
    }
    
    // Window resize handler
    window.addEventListener('resize', function() {
        const maxWidth = window.innerWidth * 0.75;
        
        // On mobile, reset panel width to full width
        if (window.innerWidth <= 768) {
            artifactsPanel.style.width = '100%';
            panelWidth = window.innerWidth;
        } else if (!isResizing) {
            // On desktop, ensure panel width is within bounds
            if (panelWidth > maxWidth) {
                panelWidth = maxWidth;
                artifactsPanel.style.width = maxWidth + 'px';
            }
        }
        
        // Update chat container position based on current state
        updateChatContainerPosition(artifactsPanel.classList.contains('expanded'), panelWidth);
    });
    
    // Public API for artifacts panel
    window.ArtifactsPanel = {
        /**
         * Add a new artifact to the panel
         * @param {Object} artifact - The artifact to add
         * @param {string} artifact.title - The title of the artifact
         * @param {string} artifact.description - The description of the artifact
         * @param {string} artifact.type - The type of artifact (image, code, etc.)
         * @param {string} artifact.content - The content or URL of the artifact
         */
        addArtifact: function(artifact) {
            const artifactsContent = document.querySelector('.artifacts-content');
            const emptyState = document.querySelector('.empty-state');
            
            if (!artifactsContent) return;
            
            // Hide empty state if it exists
            if (emptyState) {
                emptyState.style.display = 'none';
            }
            
            // Create artifact item
            const artifactItem = document.createElement('div');
            artifactItem.className = 'artifact-item';
            
            // Create title
            const title = document.createElement('div');
            title.className = 'artifact-title';
            title.textContent = artifact.title;
            
            // Create description
            const description = document.createElement('div');
            description.className = 'artifact-description';
            description.textContent = artifact.description;
            
            // Add to DOM
            artifactItem.appendChild(title);
            artifactItem.appendChild(description);
            
            // Add content based on type
            if (artifact.type === 'image' && artifact.content) {
                const img = document.createElement('img');
                img.src = artifact.content;
                img.alt = artifact.title;
                img.style.width = '100%';
                img.style.marginTop = '10px';
                img.style.borderRadius = '4px';
                artifactItem.appendChild(img);
            } else if (artifact.type === 'code' && artifact.content) {
                const pre = document.createElement('pre');
                pre.style.marginTop = '10px';
                pre.style.padding = '10px';
                pre.style.backgroundColor = 'rgba(0, 0, 0, 0.2)';
                pre.style.borderRadius = '4px';
                pre.style.overflow = 'auto';
                pre.style.fontSize = '0.85rem';
                
                const code = document.createElement('code');
                code.textContent = artifact.content;
                
                pre.appendChild(code);
                artifactItem.appendChild(pre);
            }
            
            // Add to the beginning of the list
            if (artifactsContent.firstChild) {
                artifactsContent.insertBefore(artifactItem, artifactsContent.firstChild);
            } else {
                artifactsContent.appendChild(artifactItem);
            }
            
            // Show panel if not expanded
            if (!artifactsPanel.classList.contains('expanded')) {
                artifactsButton.click();
            }
            
            return artifactItem;
        },
        
        /**
         * Clear all artifacts from the panel
         */
        clearArtifacts: function() {
            const artifactsContent = document.querySelector('.artifacts-content');
            const emptyState = document.querySelector('.empty-state');
            
            if (!artifactsContent) return;
            
            // Remove all artifact items
            const items = artifactsContent.querySelectorAll('.artifact-item');
            items.forEach(item => item.remove());
            
            // Show empty state if it exists
            if (emptyState) {
                emptyState.style.display = 'flex';
            }
        },
        
        /**
         * Check if the artifacts panel is currently open
         * @returns {boolean} True if the panel is open, false otherwise
         */
        isOpen: function() {
            return artifactsPanel.classList.contains('expanded');
        },
        
        /**
         * Open the artifacts panel
         */
        open: function() {
            this.toggle(true);
        },
        
        /**
         * Close the artifacts panel
         */
        close: function() {
            this.toggle(false);
        },
        
        /**
         * Toggle the artifacts panel visibility
         * If forceOpen is true, ensures the panel is opened
         */
        toggle: function(forceOpen) {
            console.log('[ArtifactsPanel] Toggle called with forceOpen:', forceOpen);
            
            // Get current state
            const isCurrentlyExpanded = artifactsPanel.classList.contains('expanded');
            console.log('[ArtifactsPanel] Current panel state - expanded:', isCurrentlyExpanded);
            
            // Determine if we should open, close, or toggle
            let shouldBeExpanded;
            if (forceOpen === true) {
                shouldBeExpanded = true; // Force open
            } else if (forceOpen === false) {
                shouldBeExpanded = false; // Force close
            } else {
                shouldBeExpanded = !isCurrentlyExpanded; // Toggle
            }
            
            console.log('[ArtifactsPanel] Should be expanded:', shouldBeExpanded);
            
            // Apply the state directly
            if (shouldBeExpanded) {
                // Open the panel
                artifactsPanel.classList.add('expanded');
                appContainer.classList.add('artifacts-expanded');
                artifactsButton.classList.add('active');
                
                // Update chat container
                updateChatContainerPosition(true);
                
                // When opening the panel, load data for the currently active tab
                const activeTab = document.querySelector('.tab-button.active');
                if (activeTab) {
                    const tabId = activeTab.getAttribute('data-tab');
                    console.log(`[ArtifactsPanel] Panel opened, loading data for active tab: ${tabId}`);
                    loadTabData(tabId);
                }
                
                console.log('[ArtifactsPanel] Panel opened');
            } else {
                // Close the panel
                artifactsPanel.classList.remove('expanded');
                appContainer.classList.remove('artifacts-expanded');
                artifactsButton.classList.remove('active');
                
                // Update chat container
                updateChatContainerPosition(false);
                
                console.log('[ArtifactsPanel] Panel closed');
            }
            
            // Store state in localStorage
            localStorage.setItem('artifacts_expanded', shouldBeExpanded);
        }
    };

    // Tab switching functionality
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabPanes = document.querySelectorAll('.tab-pane');

    function saveActiveTab(tabId) {
        try {
            localStorage.setItem('artifactsActiveTab', tabId);
        } catch (error) {
            console.warn('[ArtifactsPanel] Unable to persist active tab:', error);
        }
    }

    function getSavedActiveTab() {
        try {
            return localStorage.getItem('artifactsActiveTab');
        } catch (error) {
            console.warn('[ArtifactsPanel] Unable to read persisted tab:', error);
            return null;
        }
    }

    function switchTab(tabId) {
        console.log(`[ArtifactsPanel] Switching to tab: ${tabId}`);
        console.log(`[ArtifactsPanel] Tab switching called at:`, new Date().toISOString());
        
        // Remove active class from all buttons and panes
        tabButtons.forEach(button => button.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));

        // Add active class to clicked button and corresponding pane
        const activeButton = document.querySelector(`[data-tab="${tabId}"]`);
        const activePane = document.getElementById(tabId);
        
        console.log(`[ArtifactsPanel] Active button found:`, !!activeButton);
        console.log(`[ArtifactsPanel] Active pane found:`, !!activePane);
        
        if (activeButton && activePane) {
            activeButton.classList.add('active');
            activePane.classList.add('active');
            saveActiveTab(tabId);
            
            console.log(`[ArtifactsPanel] About to call loadTabData for tab: ${tabId}`);
            // Automatically load data when switching to certain tabs
            loadTabData(tabId);
        } else {
            console.error(`[ArtifactsPanel] Could not find elements for tab: ${tabId}`);
        }
    }
    
    // Function to load data for specific tabs
    function loadTabData(tabId) {
        console.log(`[ArtifactsPanel] loadTabData called for tab: ${tabId}`);
        
        // Get the current project ID from the URL or data attribute
        const projectId = getCurrentProjectId();
        console.log(`[ArtifactsPanel] Current project ID: ${projectId}`);
        
        if (!projectId) {
            console.warn('[ArtifactsPanel] No project ID found, cannot load tab data');
            return;
        }
        
        // Load different data based on tab ID
        switch (tabId) {
            case 'features':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadFeatures === 'function') {
                    window.ArtifactsLoader.loadFeatures(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadFeatures not found');
                }
                break;
            case 'personas':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadPersonas === 'function') {
                    window.ArtifactsLoader.loadPersonas(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadPersonas not found');
                }
                break;
            case 'tickets':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadTickets === 'function') {
                    window.ArtifactsLoader.loadTickets(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadTickets not found');
                }
                break;
            case 'filebrowser':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadFileBrowser === 'function') {
                    window.ArtifactsLoader.loadFileBrowser(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadFileBrowser not found');
                }
                break;
            case 'checklist':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadChecklist === 'function') {
                    window.ArtifactsLoader.loadChecklist(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadChecklist not found');
                }
                break;
            case 'codebase':
                console.log('[ArtifactsPanel] Codebase tab selected');
                console.log('[ArtifactsPanel] ArtifactsLoader available:', !!window.ArtifactsLoader);
                console.log('[ArtifactsPanel] loadCodebase function available:', !!(window.ArtifactsLoader && typeof window.ArtifactsLoader.loadCodebase === 'function'));
                
                // Load codebase explorer in iframe
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadCodebase === 'function') {
                    console.log('[ArtifactsPanel] Calling ArtifactsLoader.loadCodebase with project ID:', projectId);
                    window.ArtifactsLoader.loadCodebase(projectId);
                } else {
                    // Fallback to internal function if loader not available
                    console.log('[ArtifactsPanel] ArtifactsLoader not available, using fallback function');
                    loadCodebaseExplorer(projectId);
                }
                break;
            case 'apps':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadAppPreview === 'function') {
                    console.log('[ArtifactsPanel] Loading app preview from artifacts.js');
                    window.ArtifactsLoader.loadAppPreview(projectId, null);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadAppPreview not found');
                }
                break;
            // case 'toolhistory':
            //     if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadToolHistory === 'function') {
            //         console.log('[ArtifactsPanel] Loading tool history from artifacts.js');
            //         window.ArtifactsLoader.loadToolHistory(projectId);
            //     } else {
            //         console.warn('[ArtifactsPanel] ArtifactsLoader.loadToolHistory not found');
            //     }
            //     break;
            case 'filebrowser':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadFileBrowser === 'function') {
                    console.log('[ArtifactsPanel] Loading file browser from artifacts.js');
                    window.ArtifactsLoader.loadFileBrowser(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadFileBrowser not found');
                }
                break;
            // Add more cases as needed for other tabs
        }
    }
    
    // Function to load the codebase explorer in an iframe
    function loadCodebaseExplorer(projectId) {
        console.log(`[ArtifactsPanel] Loading codebase explorer for project ID: ${projectId}`);
        
        const codebaseTab = document.getElementById('codebase');
        const codebaseLoading = document.getElementById('codebase-loading');
        const codebaseEmpty = document.getElementById('codebase-empty');
        const codebaseFrameContainer = document.getElementById('codebase-frame-container');
        const codebaseIframe = document.getElementById('codebase-iframe');
        
        if (!codebaseTab || !codebaseLoading || !codebaseEmpty || !codebaseFrameContainer || !codebaseIframe) {
            console.warn('[ArtifactsPanel] Codebase UI elements not found');
            return;
        }
        
        // Show loading state
        codebaseLoading.style.display = 'block';
        codebaseEmpty.style.display = 'none';
        codebaseFrameContainer.style.display = 'none';
        
        // Set the iframe source to the development editor page
        const editorUrl = `/development/editor/?project_id=${projectId}`;
        console.log(`[ArtifactsPanel] Loading codebase from URL: ${editorUrl}`);
        
        codebaseIframe.onload = function() {
            // Hide loading and show iframe when loaded
            codebaseLoading.style.display = 'none';
            codebaseFrameContainer.style.display = 'block';
            console.log('[ArtifactsPanel] Codebase iframe loaded successfully');
        };
        
        codebaseIframe.onerror = function() {
            // Show error state if loading fails
            codebaseLoading.style.display = 'none';
            codebaseEmpty.style.display = 'block';
            codebaseEmpty.innerHTML = `
                <div class="error-state">
                    <div class="error-state-icon">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <div class="error-state-text">
                        Error loading codebase explorer. Please try again.
                    </div>
                </div>
            `;
            console.error('[ArtifactsPanel] Error loading codebase iframe');
        };
        
        codebaseIframe.src = editorUrl;
    }
    
    // Helper function to get current project ID from URL path only
    function getCurrentProjectId() {
        // Use the same logic as extractProjectIdFromPath in chat.js
        const pathParts = window.location.pathname.split('/').filter(part => part);
        if (pathParts.length >= 3 && pathParts[0] === 'chat' && pathParts[1] === 'project') {
            return pathParts[2];
        }
        
        throw new Error('No project ID found in path. Expected format: /chat/project/{id}/');
    }

    // Make switchTab function available globally
    window.switchTab = switchTab;

    // Add click event listeners to all tab buttons
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabId = button.getAttribute('data-tab');
            switchTab(tabId);
        });
    });
    
    // Load data for the initially active tab when ArtifactsLoader is ready
    function loadInitialTab() {
        const savedTabId = getSavedActiveTab();
        if (savedTabId) {
            const savedButton = document.querySelector(`.tab-button[data-tab="${savedTabId}"]`);
            if (savedButton) {
                console.log(`[ArtifactsPanel] Restoring saved tab: ${savedTabId}`);
                switchTab(savedTabId);
                return;
            }
        }

        const activeTab = document.querySelector('.tab-button.active');
        if (activeTab) {
            const tabId = activeTab.getAttribute('data-tab');
            const projectId = getCurrentProjectId();
            console.log(`[ArtifactsPanel] Initial load - loading data for active tab: ${tabId}, projectId: ${projectId}`);
            if (projectId) {
                loadTabData(tabId);
            } else {
                console.warn('[ArtifactsPanel] No project ID found on initial load');
            }
        }
    }
    
    // Check if ArtifactsLoader is already available
    if (window.ArtifactsLoader) {
        loadInitialTab();
    } else {
        // Wait for ArtifactsLoader to be ready
        const checkInterval = setInterval(() => {
            if (window.ArtifactsLoader) {
                clearInterval(checkInterval);
                loadInitialTab();
            }
        }, 50); // Check every 50ms
        
        // Stop checking after 5 seconds
        setTimeout(() => {
            clearInterval(checkInterval);
            console.error('[ArtifactsPanel] ArtifactsLoader not found after 5 seconds');
        }, 5000);
    }
}); 

/* ==== End: artifacts.js ==== */

/* ==== Begin: artifacts-loader.js ==== */
/**
 * Artifacts Loader JavaScript
 * Handles loading artifact data from the server and updating the artifacts panel
 */

// Global helper functions
window.showToast = function(message, type = 'info') {
    // Get or create toast container
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'messages';
        document.body.appendChild(toastContainer);
    }
    
    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.textContent = message;
    
    // Make toast clickable to dismiss
    toast.addEventListener('click', function() {
        this.style.animation = 'fadeOut 0.3s ease-out forwards';
        setTimeout(() => this.remove(), 300);
    });
    
    toastContainer.appendChild(toast);
    
    // Auto-remove toast after 5 seconds (CSS animation handles the fade out)
    setTimeout(() => {
        if (toast.parentNode) {
            toast.remove();
        }
    }, 5500); // 5s display + 0.5s fade out
};

window.getCookie = function(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
};

// Make showLinearProjectSelectionPopup globally accessible
window.showLinearProjectSelectionPopup = async function(projectId, teams) {
    const showToast = window.showToast;
    const getCookie = window.getCookie;
    
    // Create popup overlay
    const overlay = document.createElement('div');
    overlay.className = 'linear-popup-overlay';
    overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center;';
    
    // Create popup container
    const popup = document.createElement('div');
    popup.className = 'linear-popup';
    popup.style.cssText = 'background: #2a2a2a; padding: 30px; border-radius: 8px; max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.5);';
    
    // Check if we have teams
    if (!teams || teams.length === 0) {
        popup.innerHTML = `
            <h3 style="color: #fff; margin-bottom: 20px;">No Linear Teams Found</h3>
            <p style="color: #ccc; margin-bottom: 20px;">Please make sure your Linear API key has access to at least one team.</p>
            <button class="close-popup-btn" style="background: #666; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Close</button>
        `;
        overlay.appendChild(popup);
        document.body.appendChild(overlay);
        
        popup.querySelector('.close-popup-btn').addEventListener('click', () => {
            overlay.remove();
        });
        return;
    }
    
    // Get current project info
    const projectResponse = await fetch(`/projects/${projectId}/?format=json`);
    const projectData = await projectResponse.json();
    const currentLinearProjectId = projectData.linear_project_id;
    
    let popupHTML = `
        <h3 style="color: #fff; margin-bottom: 20px;">Sync with Linear Team</h3>
        <div class="linear-teams-container">
    `;
    
    // Always show team selection
    popupHTML += `
        <div style="margin-bottom: 20px;">
            <label style="color: #ccc; display: block; margin-bottom: 8px;">Select Team:</label>
            <select id="linear-team-select" style="width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; color: #fff; border-radius: 4px;">
                ${teams.map(team => `<option value="${team.id}">${team.name}</option>`).join('')}
            </select>
        </div>
    `;
    
    popupHTML += `
        <div style="display: flex; justify-content: flex-end; gap: 10px;">
            <button class="cancel-popup-btn" style="background: #666; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Cancel</button>
            <button class="confirm-popup-btn" style="background: #5856d6; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Sync with Selected Team</button>
        </div>
    </div>
    `;
    
    popup.innerHTML = popupHTML;
    overlay.appendChild(popup);
    document.body.appendChild(overlay);
    
    // Elements
    const teamSelect = popup.querySelector('#linear-team-select');
    // Project-related elements removed - syncing with teams only
    const confirmBtn = popup.querySelector('.confirm-popup-btn');
    const cancelBtn = popup.querySelector('.cancel-popup-btn');
    
    // Project-related code removed - syncing directly with teams
    
    // No team change handler needed since we're syncing with the selected team
    
    // Create project functionality removed - syncing with teams only
    /* Removed create project handler */
    
    // Cancel handler
    cancelBtn.addEventListener('click', () => {
        overlay.remove();
    });
    
    // Confirm handler
    confirmBtn.addEventListener('click', async () => {
        const selectedTeamId = teams.length === 1 ? teams[0].id : teamSelect.value;
        
        if (!selectedTeamId) {
            showToast('Please select a team', 'error');
            return;
        }
        
        // Save the selected team to the backend
        const saveResponse = await fetch(`/projects/${projectId}/update/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: new URLSearchParams({
                'name': projectData.name || '',
                'description': projectData.description || '',
                'linear_sync_enabled': 'on',
                'linear_team_id': selectedTeamId,
                'linear_project_id': ''
            })
        });
        
        if (saveResponse.ok) {
            // Close popup
            overlay.remove();
            
            // Show progress overlay
            const progressOverlay = document.createElement('div');
            progressOverlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; z-index: 10000;';
            
            const progressContainer = document.createElement('div');
            progressContainer.style.cssText = 'background: #2a2a2a; padding: 30px; border-radius: 8px; min-width: 400px; text-align: center;';
            
            progressContainer.innerHTML = `
                <h3 style="color: #fff; margin-bottom: 20px;">Syncing with Linear</h3>
                <div style="margin-bottom: 15px;">
                    <div style="background: #444; height: 20px; border-radius: 10px; overflow: hidden;">
                        <div id="sync-progress-bar" style="background: #5856d6; height: 100%; width: 0%; transition: width 0.3s ease;"></div>
                    </div>
                </div>
                <p id="sync-progress-text" style="color: #ccc; margin: 0;">Initializing sync...</p>
            `;
            
            progressOverlay.appendChild(progressContainer);
            document.body.appendChild(progressOverlay);
            
            // Simulate progress while waiting for response
            const progressBar = document.getElementById('sync-progress-bar');
            const progressText = document.getElementById('sync-progress-text');
            
            progressBar.style.width = '20%';
            progressText.textContent = 'Connecting to Linear...';
            
            try {
                const syncResponse = await fetch(`/projects/${projectId}/api/linear/sync/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                });
                
                progressBar.style.width = '60%';
                progressText.textContent = 'Processing items...';
                
                const syncData = await syncResponse.json();
                
                progressBar.style.width = '100%';
                
                if (syncData.success) {
                    progressText.textContent = `Synced ${syncData.results?.created || 0} items successfully!`;
                    
                    // Show completion for a moment
                    setTimeout(() => {
                        progressOverlay.remove();
                        showToast(syncData.message || 'Tasks synced successfully!', 'success');
                        // Reload the checklist if ArtifactsLoader is available
                        if (window.ArtifactsLoader && window.ArtifactsLoader.loadChecklist) {
                            window.ArtifactsLoader.loadChecklist(projectId);
                        }
                    }, 1500);
                } else {
                    progressText.textContent = 'Sync failed!';
                    progressBar.style.background = '#f44336';
                    
                    setTimeout(() => {
                        progressOverlay.remove();
                        showToast(syncData.error || 'Failed to sync tasks', 'error');
                    }, 1500);
                }
            } catch (error) {
                progressBar.style.width = '100%';
                progressBar.style.background = '#f44336';
                progressText.textContent = 'Network error!';
                
                setTimeout(() => {
                    progressOverlay.remove();
                    showToast('Network error during sync', 'error');
                }, 1500);
            }
        } else {
            showToast('Failed to save Linear team selection', 'error');
        }
    });
    
    // Close on overlay click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.remove();
        }
    });
};

document.addEventListener('DOMContentLoaded', function() {
    
    // Helper function to get current conversation ID from URL or global variables
    function getCurrentConversationId() {
        // Try to get conversation ID from URL first
        const urlParams = new URLSearchParams(window.location.search);
        const urlConversationId = urlParams.get('conversation_id');
        
        if (urlConversationId) {
            return urlConversationId;
        }
        
        // Then try from path (format: /chat/conversation/{id}/)
        const pathMatch = window.location.pathname.match(/\/chat\/conversation\/(\d+)\//);
        if (pathMatch && pathMatch[1]) {
            return pathMatch[1];
        }
        
        // Try global variables if available
        if (window.conversation_id) {
            return window.conversation_id;
        }
        
        if (window.CONVERSATION_DATA && window.CONVERSATION_DATA.id) {
            return window.CONVERSATION_DATA.id;
        }
        
        return null;
    }
    
    // Helper function to get current project ID from URL path only
    function getCurrentProjectId() {
        // Use the same logic as extractProjectIdFromPath in chat.js
        const pathParts = window.location.pathname.split('/').filter(part => part);
        if (pathParts.length >= 3 && pathParts[0] === 'chat' && pathParts[1] === 'project') {
            const projectId = pathParts[2];
            console.log('[ArtifactsLoader] Found project ID in URL path:', projectId);
            return projectId;
        }
        
        console.error('[ArtifactsLoader] No project ID found in path. Expected format: /chat/project/{id}/');
        throw new Error('No project ID found in path. Expected format: /chat/project/{id}/');
    }

    // Helper function to get CSRF token
    function getCsrfToken() {
        // Try to get it from the meta tag first (Django's standard location)
        const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (metaToken) {
            return metaToken;
        }
        
        // Then try the input field (another common location)
        const inputToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (inputToken) {
            return inputToken;
        }
        
        // Finally try to get it from cookies
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        
        if (cookieValue) {
            return cookieValue;
        }
        
        console.error('[ArtifactsLoader] CSRF token not found in any location');
        return '';
    }

    // Initialize the artifact loaders immediately
    console.log('[ArtifactsLoader] Initializing ArtifactsLoader');
    window.ArtifactsLoader = {
        /**
         * Get the current project ID from various sources
         * @returns {number|null} The current project ID or null if not found
         */
        getCurrentProjectId: getCurrentProjectId,
        ticketModalState: {
            list: [],
            index: -1,
            projectId: null,
            onEdit: null,
            onDelete: null,
            onExecute: null
        },
        _ticketModalElements: null,
        _ticketModalHelpers: null,
        getTicketModalHelpers: function() {
            if (this._ticketModalHelpers) {
                return this._ticketModalHelpers;
            }

            const self = this;
            const modalState = this.ticketModalState;
            let modalElements = this._ticketModalElements || {};
            let eventsBound = false;

            function escapeHtml(value) {
                if (value === null || value === undefined) {
                    return '';
                }
                return String(value)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            }

            function renderMarkdownContent(content) {
                if (!content) {
                    return '<p class="ticket-modal-empty">No description provided.</p>';
                }
                try {
                    if (typeof marked !== 'undefined') {
                        return marked.parse(content);
                    }
                } catch (error) {
                    console.error('[ArtifactsLoader] Error parsing markdown content:', error);
                }
                return escapeHtml(content).replace(/\n/g, '<br>');
            }

            function renderValueBlock(value) {
                if (value === null || value === undefined) {
                    return '';
                }
                if (Array.isArray(value)) {
                    if (value.length === 0) {
                        return '';
                    }
                    return `<ul>${value.map(item => `<li>${escapeHtml(typeof item === 'string' ? item : JSON.stringify(item))}</li>`).join('')}</ul>`;
                }
                if (typeof value === 'object') {
                    if (Object.keys(value).length === 0) {
                        return '';
                    }
                    return `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
                }
                if (typeof value === 'string') {
                    const trimmed = value.trim();
                    if (!trimmed || trimmed === '{}' || trimmed === '[]' || trimmed === 'null' || trimmed === 'undefined') {
                        return '';
                    }
                    return renderMarkdownContent(value);
                }
                return escapeHtml(String(value));
            }

            function formatStatus(value) {
                if (!value) {
                    return 'Open';
                }
                return value.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
            }

            function formatTitleCase(value, fallback = '') {
                const source = value || fallback;
                if (!source) {
                    return '';
                }
                return String(source)
                    .toLowerCase()
                    .replace(/(^|\s|[_-])(\w)/g, (_, sep, char) => `${sep === '_' || sep === '-' ? ' ' : sep}${char.toUpperCase()}`)
                    .trim();
            }

            function slugify(value) {
                return String(value || '')
                    .toLowerCase()
                    .replace(/[^a-z0-9]+/g, '-')
                    .replace(/^-+|-+$/g, '') || 'default';
            }

            function applyPill(element, value, formatter, datasetKey) {
                if (!element) {
                    return;
                }
                if (!value) {
                    element.style.display = 'none';
                    element.textContent = '';
                    if (datasetKey) {
                        element.dataset[datasetKey] = '';
                    }
                    return;
                }
                const formatted = formatter ? formatter(value) : value;
                element.style.display = '';
                element.textContent = formatted;
                if (datasetKey) {
                    element.dataset[datasetKey] = slugify(value);
                }
            }

            function cacheModalElements() {
                const priorityElement = document.getElementById('ticket-modal-priority-text');

                modalElements = {
                    overlay: document.getElementById('ticket-modal-overlay'),
                    container: document.getElementById('ticket-modal'),
                    closeBtn: document.getElementById('ticket-modal-close'),
                    prevBtn: document.getElementById('ticket-modal-prev'),
                    nextBtn: document.getElementById('ticket-modal-next'),
                    editBtn: document.getElementById('ticket-modal-edit'),
                    deleteBtn: document.getElementById('ticket-modal-delete'),
                    executeBtn: document.getElementById('ticket-modal-execute'),
                    name: document.getElementById('ticket-modal-name'),
                    subtitle: document.getElementById('ticket-modal-subtitle'),
                    status: document.getElementById('ticket-modal-status-chip'),
                    complexityChip: document.getElementById('ticket-modal-complexity-chip'),
                    priorityText: priorityElement,
                    priorityWrapper: priorityElement ? priorityElement.closest('.ticket-meta-inline-item') : null,
                    assigned: document.getElementById('ticket-modal-assigned'),
                    worktree: document.getElementById('ticket-modal-worktree'),
                    description: document.getElementById('ticket-modal-description'),
                    acceptanceSection: document.getElementById('ticket-modal-acceptance-section'),
                    acceptance: document.getElementById('ticket-modal-acceptance'),
                    detailsSection: document.getElementById('ticket-modal-details-section'),
                    details: document.getElementById('ticket-modal-details'),
                    uiSection: document.getElementById('ticket-modal-ui-section'),
                    ui: document.getElementById('ticket-modal-ui'),
                    specSection: document.getElementById('ticket-modal-spec-section'),
                    spec: document.getElementById('ticket-modal-spec'),
                    dependenciesSection: document.getElementById('ticket-modal-dependencies-section'),
                    dependencies: document.getElementById('ticket-modal-dependencies'),
                    notesSection: document.getElementById('ticket-modal-notes-section'),
                    notes: document.getElementById('ticket-modal-notes'),
                    linearSection: document.getElementById('ticket-modal-linear-section'),
                    linear: document.getElementById('ticket-modal-linear')
                };
                self._ticketModalElements = modalElements;
            }

            function updateNavigationControls() {
                if (!modalElements.prevBtn || !modalElements.nextBtn) {
                    return;
                }
                modalElements.prevBtn.disabled = modalState.index <= 0;
                modalElements.nextBtn.disabled = modalState.index >= modalState.list.length - 1 || modalState.list.length === 0;
            }

            function updateActionVisibility() {
                if (modalElements.editBtn) {
                    modalElements.editBtn.style.display = modalState.onEdit ? '' : 'none';
                }
                if (modalElements.deleteBtn) {
                    modalElements.deleteBtn.style.display = modalState.onDelete ? '' : 'none';
                }
                if (modalElements.executeBtn) {
                    modalElements.executeBtn.style.display = modalState.onExecute ? '' : 'none';
                }
            }

            function populateModal(ticket) {
                if (!ticket || !modalElements.container) {
                    return;
                }

                if (modalElements.name) {
                    modalElements.name.textContent = ticket.name || 'Untitled Ticket';
                }
                if (modalElements.subtitle) {
                    modalElements.subtitle.textContent = ticket.id ? `Ticket #${ticket.id}` : '';
                }
                if (modalElements.status) {
                    applyPill(modalElements.status, ticket.status || 'open', value => formatStatus(value).toUpperCase(), 'state');
                }
                if (modalElements.complexityChip) {
                    const complexityLabel = ticket.complexity || 'medium';
                    applyPill(modalElements.complexityChip, complexityLabel, value => formatTitleCase(value, 'Medium').toUpperCase(), 'level');
                }
                if (modalElements.priorityText) {
                    const priorityValue = formatTitleCase(ticket.priority, '');
                    if (priorityValue) {
                        modalElements.priorityText.textContent = priorityValue;
                        if (modalElements.priorityWrapper) {
                            modalElements.priorityWrapper.style.display = 'inline-flex';
                        }
                    } else {
                        modalElements.priorityText.textContent = '';
                        if (modalElements.priorityWrapper) {
                            modalElements.priorityWrapper.style.display = 'none';
                        }
                    }
                }
                if (modalElements.assigned) {
                    modalElements.assigned.textContent = formatTitleCase(ticket.role, 'Agent');
                }
                if (modalElements.worktree) {
                    modalElements.worktree.textContent = ticket.requires_worktree ? 'Required' : 'Not Required';
                }
                if (modalElements.description) {
                    modalElements.description.innerHTML = renderMarkdownContent(ticket.description || '');
                }

                if (modalElements.acceptanceSection) {
                    if (ticket.acceptance_criteria && ticket.acceptance_criteria.length > 0) {
                        modalElements.acceptanceSection.style.display = '';
                        modalElements.acceptance.innerHTML = `<ul>${ticket.acceptance_criteria.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
                    } else {
                        modalElements.acceptanceSection.style.display = 'none';
                        modalElements.acceptance.innerHTML = '';
                    }
                }

                if (modalElements.detailsSection) {
                    if (ticket.details && Object.keys(ticket.details || {}).length > 0) {
                        modalElements.detailsSection.style.display = '';
                        modalElements.details.innerHTML = `<pre>${escapeHtml(JSON.stringify(ticket.details, null, 2))}</pre>`;
                    } else {
                        modalElements.detailsSection.style.display = 'none';
                        modalElements.details.innerHTML = '';
                    }
                }

                if (modalElements.uiSection) {
                    const uiContent = renderValueBlock(ticket.ui_requirements);
                    if (uiContent) {
                        modalElements.uiSection.style.display = '';
                        modalElements.ui.innerHTML = uiContent;
                    } else {
                        modalElements.uiSection.style.display = 'none';
                        modalElements.ui.innerHTML = '';
                    }
                }

                if (modalElements.specSection) {
                    const specContent = renderValueBlock(ticket.component_specs);
                    if (specContent) {
                        modalElements.specSection.style.display = '';
                        modalElements.spec.innerHTML = specContent;
                    } else {
                        modalElements.specSection.style.display = 'none';
                        modalElements.spec.innerHTML = '';
                    }
                }

                if (modalElements.dependenciesSection) {
                    if (ticket.dependencies && ticket.dependencies.length > 0) {
                        modalElements.dependenciesSection.style.display = '';
                        modalElements.dependencies.innerHTML = `<ul>${ticket.dependencies.map(dep => `<li>${escapeHtml(dep)}</li>`).join('')}</ul>`;
                    } else {
                        modalElements.dependenciesSection.style.display = 'none';
                        modalElements.dependencies.innerHTML = '';
                    }
                }

                if (modalElements.notesSection) {
                    if (ticket.notes) {
                        modalElements.notesSection.style.display = '';
                        modalElements.notes.innerHTML = `<div class="ticket-notes" style="background: rgba(148, 163, 184, 0.1); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; padding: 12px; color: #e2e8f0;">${escapeHtml(ticket.notes).replace(/\n/g, '<br>')}</div>`;
                    } else {
                        modalElements.notesSection.style.display = 'none';
                        modalElements.notes.innerHTML = '';
                    }
                }

                if (modalElements.linearSection) {
                    if (ticket.linear_issue_id) {
                        modalElements.linearSection.style.display = '';
                        const parts = [];
                        if (ticket.linear_state) {
                            parts.push(`<p><strong>State:</strong> ${escapeHtml(ticket.linear_state)}</p>`);
                        }
                        if (ticket.linear_issue_url) {
                            parts.push(`<p><a href="${escapeHtml(ticket.linear_issue_url)}" target="_blank" rel="noopener" class="ticket-modal-link">View in Linear</a></p>`);
                        }
                        if (ticket.linear_synced_at) {
                            parts.push(`<p class="ticket-modal-subtext">Last synced: ${new Date(ticket.linear_synced_at).toLocaleString()}</p>`);
                        }
                        modalElements.linear.innerHTML = parts.join('') || '<p>No Linear metadata available.</p>';
                    } else {
                        modalElements.linearSection.style.display = 'none';
                        modalElements.linear.innerHTML = '';
                    }
                }

                modalElements.container.scrollTop = 0;
                if (modalElements.description && modalElements.description.classList.contains('markdown-content')) {
                    modalElements.description.setAttribute('data-raw-content', ticket.description || '');
                }
            }

            function ensureModal() {
                if (!document.getElementById('ticket-modal-overlay')) {
                    const overlay = document.createElement('div');
                    overlay.id = 'ticket-modal-overlay';
                    overlay.className = 'ticket-modal-overlay';
                    overlay.setAttribute('aria-hidden', 'true');
                    overlay.innerHTML = `
                        <div class="ticket-modal" id="ticket-modal" role="dialog" aria-modal="true" aria-labelledby="ticket-modal-name" tabindex="-1">
                            <div class="ticket-modal-header">
                                <div class="ticket-modal-nav">
                                    <button type="button" class="ticket-modal-nav-btn" id="ticket-modal-prev" title="Previous ticket">
                                        <i class="fas fa-chevron-left"></i>
                                    </button>
                                    <button type="button" class="ticket-modal-nav-btn" id="ticket-modal-next" title="Next ticket">
                                        <i class="fas fa-chevron-right"></i>
                                    </button>
                                </div>
                                <div class="ticket-modal-header-actions">
                                    <div class="ticket-chip-group">
                                        <span class="ticket-chip ticket-status-chip" id="ticket-modal-status-chip"></span>
                                        <span class="ticket-chip ticket-complexity-chip" id="ticket-modal-complexity-chip"></span>
                                    </div>
                                    <button type="button" class="ticket-modal-close" id="ticket-modal-close" title="Close ticket details">
                                        <i class="fas fa-times"></i>
                                    </button>
                                </div>
                            </div>
                            <div class="ticket-modal-header-content">
                                <div class="ticket-modal-title-group">
                                    <p class="ticket-modal-context">Ticket overview</p>
                                    <h2 class="ticket-modal-name" id="ticket-modal-name"></h2>
                                    <p class="ticket-modal-subtitle" id="ticket-modal-subtitle"></p>
                                </div>
                                <div class="ticket-meta-inline" id="ticket-modal-summary">
                                    <div class="ticket-meta-inline-item">
                                        <span class="ticket-meta-inline-label">Assignee</span>
                                        <span class="ticket-meta-inline-value" id="ticket-modal-assigned"></span>
                                    </div>
                                    <div class="ticket-meta-inline-item">
                                        <span class="ticket-meta-inline-label">Worktree</span>
                                        <span class="ticket-meta-inline-value" id="ticket-modal-worktree"></span>
                                    </div>
                                    <div class="ticket-meta-inline-item">
                                        <span class="ticket-meta-inline-label">Priority</span>
                                        <span class="ticket-meta-inline-value" id="ticket-modal-priority-text"></span>
                                    </div>
                                </div>
                            </div>
                            <div class="ticket-modal-body">
                                <section class="ticket-modal-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-align-left"></i>
                                            <h4>Description</h4>
                                        </div>
                                        <span class="ticket-section-label">Rich markdown</span>
                                    </header>
                                    <div id="ticket-modal-description" class="ticket-modal-description markdown-content"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-acceptance-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-clipboard-check"></i>
                                            <h4>Acceptance Criteria</h4>
                                        </div>
                                        <span class="ticket-section-label">Delivery checklist</span>
                                    </header>
                                    <div id="ticket-modal-acceptance"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-details-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-microchip"></i>
                                            <h4>Technical Details</h4>
                                        </div>
                                        <span class="ticket-section-label">Implementation notes</span>
                                    </header>
                                    <div id="ticket-modal-details"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-ui-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-layer-group"></i>
                                            <h4>UI Requirements</h4>
                                        </div>
                                        <span class="ticket-section-label">Screens & flows</span>
                                    </header>
                                    <div id="ticket-modal-ui"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-spec-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-project-diagram"></i>
                                            <h4>Component Specs</h4>
                                        </div>
                                        <span class="ticket-section-label">Interfaces & contracts</span>
                                    </header>
                                    <div id="ticket-modal-spec"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-dependencies-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-link"></i>
                                            <h4>Dependencies</h4>
                                        </div>
                                        <span class="ticket-section-label">Prerequisites</span>
                                    </header>
                                    <div id="ticket-modal-dependencies"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-notes-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-sticky-note"></i>
                                            <h4>Notes</h4>
                                        </div>
                                        <span class="ticket-section-label">Execution log</span>
                                    </header>
                                    <div id="ticket-modal-notes"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-linear-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-plug"></i>
                                            <h4>Linear Integration</h4>
                                        </div>
                                        <span class="ticket-section-label">Sync state</span>
                                    </header>
                                    <div id="ticket-modal-linear"></div>
                                </section>
                            </div>
                            <div class="ticket-modal-footer">
                                <button type="button" class="ticket-modal-secondary" id="ticket-modal-edit">
                                    <i class="fas fa-pen"></i> Edit ticket
                                </button>
                                <button type="button" class="ticket-modal-danger" id="ticket-modal-delete">
                                    <i class="fas fa-trash"></i> Delete
                                </button>
                                <button type="button" class="ticket-modal-primary" id="ticket-modal-execute">
                                    <i class="fas fa-play"></i> Execute (Build Now)
                                </button>
                            </div>
                        </div>
                    `;
                    document.body.appendChild(overlay);
                }

                cacheModalElements();

                if (!eventsBound && modalElements.overlay) {
                    eventsBound = true;

                    modalElements.overlay.addEventListener('click', function(event) {
                        if (event.target === modalElements.overlay) {
                            helpers.close();
                        }
                    });

                    if (modalElements.closeBtn) {
                        modalElements.closeBtn.addEventListener('click', function() {
                            helpers.close();
                        });
                    }

                    if (modalElements.prevBtn) {
                        modalElements.prevBtn.addEventListener('click', function() {
                            helpers.openAtIndex(modalState.index - 1);
                        });
                    }

                    if (modalElements.nextBtn) {
                        modalElements.nextBtn.addEventListener('click', function() {
                            helpers.openAtIndex(modalState.index + 1);
                        });
                    }

                    if (modalElements.editBtn) {
                        modalElements.editBtn.addEventListener('click', function() {
                            if (modalState.onEdit) {
                                modalState.onEdit(helpers.getCurrentTicket(), helpers);
                            }
                        });
                    }

                    if (modalElements.deleteBtn) {
                        modalElements.deleteBtn.addEventListener('click', function() {
                            if (!modalState.onDelete) {
                                return;
                            }
                            const result = modalState.onDelete(helpers.getCurrentTicket(), helpers);
                            if (result && typeof result.then === 'function') {
                                modalElements.deleteBtn.disabled = true;
                                result.finally(() => {
                                    modalElements.deleteBtn.disabled = false;
                                });
                            }
                        });
                    }

                    if (modalElements.executeBtn) {
                        modalElements.executeBtn.addEventListener('click', function() {
                            if (modalState.onExecute) {
                                modalState.onExecute(helpers.getCurrentTicket(), helpers);
                            }
                        });
                    }

                    document.addEventListener('keydown', function(event) {
                        if (!modalElements.overlay || !modalElements.overlay.classList.contains('active')) {
                            return;
                        }
                        if (event.key === 'Escape') {
                            helpers.close();
                        } else if (event.key === 'ArrowRight') {
                            helpers.openAtIndex(modalState.index + 1);
                        } else if (event.key === 'ArrowLeft') {
                            helpers.openAtIndex(modalState.index - 1);
                        }
                    });
                }

                updateActionVisibility();
                return modalElements;
            }

            const helpers = {
                escapeHtml,
                renderMarkdownContent,
                setProjectId(projectId) {
                    modalState.projectId = projectId;
                },
                setHandlers(handlers = {}) {
                    modalState.onEdit = handlers.onEdit || null;
                    modalState.onDelete = handlers.onDelete || null;
                    modalState.onExecute = handlers.onExecute || null;
                    ensureModal();
                    updateActionVisibility();
                },
                ensure: ensureModal,
                getCurrentTicket() {
                    if (modalState.index < 0 || modalState.index >= modalState.list.length) {
                        return null;
                    }
                    return modalState.list[modalState.index];
                },
                open(list, index) {
                    ensureModal();
                    modalState.list = Array.isArray(list) ? list.slice() : [];
                    this.openAtIndex(index);
                },
                openAtIndex(index) {
                    ensureModal();
                    if (index < 0 || index >= modalState.list.length) {
                        return;
                    }
                    modalState.index = index;
                    populateModal(this.getCurrentTicket());
                    updateNavigationControls();
                    if (modalElements.overlay) {
                        modalElements.overlay.classList.add('active');
                        modalElements.overlay.setAttribute('aria-hidden', 'false');
                    }
                    if (modalElements.container) {
                        modalElements.container.focus({ preventScroll: true });
                    }
                    document.body.classList.add('ticket-modal-open');
                },
                close() {
                    ensureModal();
                    if (modalElements.overlay) {
                        modalElements.overlay.classList.remove('active');
                        modalElements.overlay.setAttribute('aria-hidden', 'true');
                    }
                    document.body.classList.remove('ticket-modal-open');
                    modalState.index = -1;
                }
            };

            this._ticketModalElements = modalElements;
            this._ticketModalHelpers = helpers;
            return helpers;
        },
        
        /**
         * Load features from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadFeatures: function(projectId) {
            console.log(`[ArtifactsLoader] loadFeatures called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading features');
                return;
            }
            
            // Get features tab content element
            const featuresTab = document.getElementById('features');
            if (!featuresTab) {
                console.warn('[ArtifactsLoader] Features tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state');
            featuresTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading features...</div></div>';
            
            // Fetch features from API
            const url = `/projects/${projectId}/api/features/`;
            console.log(`[ArtifactsLoader] Fetching features from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] API data received:', data);
                    // Process features data
                    const features = data.features || [];
                    console.log(`[ArtifactsLoader] Found ${features.length} features`);
                    
                    if (features.length === 0) {
                        // Show empty state if no features found
                        console.log('[ArtifactsLoader] No features found, showing empty state');
                        featuresTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-list-check"></i>
                                </div>
                                <div class="empty-state-text">
                                    No features defined yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Create features content
                    console.log('[ArtifactsLoader] Rendering features to UI');
                    let featuresHtml = '<div class="features-list">';
                    
                    features.forEach(feature => {
                        const priorityClass = feature.priority.toLowerCase().replace(' ', '-');
                        
                        featuresHtml += `
                            <div class="feature-item">
                                <div class="feature-header">
                                    <h3 class="feature-name">${feature.name}</h3>
                                    <span class="feature-priority ${priorityClass}">${feature.priority}</span>
                                </div>
                                <div class="feature-description">${feature.description}</div>
                                <div class="feature-details markdown-content">
                                    ${typeof marked !== 'undefined' ? marked.parse(feature.details) : feature.details}
                                </div>
                            </div>
                        `;
                    });
                    
                    featuresHtml += '</div>';
                    featuresTab.innerHTML = featuresHtml;
                })
                .catch(error => {
                    console.error('Error fetching features:', error);
                    featuresTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading features. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        /**
         * Load personas from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadPersonas: function(projectId) {
            console.log(`[ArtifactsLoader] loadPersonas called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading personas');
                return;
            }
            
            // Get personas tab content element
            const personasTab = document.getElementById('personas');
            if (!personasTab) {
                console.warn('[ArtifactsLoader] Personas tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for personas');
            personasTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading personas...</div></div>';
            
            // Fetch personas from API
            const url = `/projects/${projectId}/api/personas/`;
            console.log(`[ArtifactsLoader] Fetching personas from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] Personas API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Personas API data received:', data);
                    // Process personas data
                    const personas = data.personas || [];
                    console.log(`[ArtifactsLoader] Found ${personas.length} personas`);
                    
                    if (personas.length === 0) {
                        // Show empty state if no personas found
                        console.log('[ArtifactsLoader] No personas found, showing empty state');
                        personasTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-users"></i>
                                </div>
                                <div class="empty-state-text">
                                    No personas defined yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Create personas content
                    console.log('[ArtifactsLoader] Rendering personas to UI');
                    let personasHtml = '<div class="personas-list">';
                    
                    personas.forEach(persona => {
                        personasHtml += `
                            <div class="persona-item">
                                <div class="persona-header">
                                    <h3 class="persona-name">${persona.name}</h3>
                                    <span class="persona-role">${persona.role}</span>
                                </div>
                                <div class="persona-description markdown-content">
                                    ${typeof marked !== 'undefined' ? marked.parse(persona.description) : persona.description}
                                </div>
                            </div>
                        `;
                    });
                    
                    personasHtml += '</div>';
                    personasTab.innerHTML = personasHtml;
                })
                .catch(error => {
                    console.error('Error fetching personas:', error);
                    personasTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading personas. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        /**
         * Load PRD from the API for the current project
         * @param {number} projectId - The ID of the current project
         * @param {string} prdName - Optional PRD name to load (defaults to currently selected)
         */
        loadPRD: function(projectId, prdName = null) {
            console.log(`[ArtifactsLoader] loadPRD called with project ID: ${projectId}, PRD name: ${prdName}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading PRD');
                return;
            }
            
            // Check if we're currently streaming PRD content
            if (window.prdStreamingState && window.prdStreamingState.isStreaming) {
                console.log('[ArtifactsLoader] PRD is currently streaming, skipping loadPRD');
                return;
            }
            
            // Get PRD tab content element
            const prdTab = document.getElementById('prd');
            if (!prdTab) {
                console.warn('[ArtifactsLoader] PRD tab element not found');
                return;
            }
            
            // Get the existing elements
            const prdContainer = document.getElementById('prd-container');
            const emptyState = document.getElementById('prd-empty-state');
            const streamingContent = document.getElementById('prd-streaming-content');
            const streamingStatus = document.getElementById('prd-streaming-status');
            const prdSelector = document.getElementById('prd-selector');
            
            // Clear any existing content first
            if (streamingContent) {
                streamingContent.innerHTML = '';
            }
            
            // Hide both container and empty state initially
            if (prdContainer) prdContainer.style.display = 'none';
            if (emptyState) emptyState.style.display = 'none';
            
            // Show loading state using the existing streaming status element
            console.log('[ArtifactsLoader] Showing loading state for PRD');
            if (prdContainer && streamingStatus) {
                prdContainer.style.display = 'block';
                streamingStatus.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Loading PRDs...';
                streamingStatus.style.color = '#8b5cf6';
            }
            
            // First fetch the list of PRDs
            const listUrl = `/projects/${projectId}/api/prd/?list=1`;
            console.log(`[ArtifactsLoader] Fetching PRD list from API: ${listUrl}`);
            
            fetch(listUrl)
                .then(response => response.json())
                .then(listData => {
                    console.log('[ArtifactsLoader] PRD list received:', listData);
                    const prds = listData.prds || [];
                    
                    // Update PRD selector
                    if (prdSelector) {
                        const selectorWrapper = document.querySelector('.prd-selector-wrapper');
                        const selectorButton = document.getElementById('prd-selector-button');
                        const selectorText = document.getElementById('prd-selector-text');
                        const selectorDropdown = document.getElementById('prd-selector-dropdown');
                        
                        if (prds.length > 1) {
                            // Show custom selector if there are multiple PRDs
                            if (selectorWrapper) selectorWrapper.style.display = 'block';
                            
                            // Update hidden select options
                            prdSelector.innerHTML = prds.map(prd => 
                                `<option value="${prd.name}">${prd.name}</option>`
                            ).join('');
                            
                            // Build custom dropdown options
                            if (selectorDropdown) {
                                selectorDropdown.innerHTML = prds.map(prd => 
                                    `<div class="prd-dropdown-option ${prd.name === prdName ? 'selected' : ''}" data-value="${prd.name}">
                                        <span class="prd-name">${prd.name}</span>
                                    </div>`
                                ).join('');
                            }
                            
                            console.log(`[ArtifactsLoader] Showing PRD selector with ${prds.length} PRDs`);
                        } else {
                            // Hide selector if only one PRD
                            if (selectorWrapper) selectorWrapper.style.display = 'none';
                            console.log('[ArtifactsLoader] Hiding PRD selector - only one PRD exists');
                        }
                        
                        // Set the current PRD name
                        if (!prdName && prds.length > 0) {
                            prdName = prds[0].name;
                        }
                        if (prds.length > 0) {
                            prdSelector.value = prdName;
                            if (selectorText) selectorText.textContent = prdName;
                        }
                    }
                    
                    
                    // Now fetch the specific PRD content
                    const url = `/projects/${projectId}/api/prd/?prd_name=${encodeURIComponent(prdName || 'Main PRD')}`;
                    console.log(`[ArtifactsLoader] Fetching PRD from API: ${url}`);
                    
                    return fetch(url);
                })
                .then(response => {
                    console.log(`[ArtifactsLoader] PRD API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] PRD API data received:', data);
                    // Process PRD data
                    const prdContent = data.content || '';
                    
                    if (!prdContent) {
                        // Show empty state if no PRD found
                        console.log('[ArtifactsLoader] No PRD found, showing empty state');
                        const emptyState = document.getElementById('prd-empty-state');
                        const prdContainer = document.getElementById('prd-container');
                        
                        if (emptyState) emptyState.style.display = 'block';
                        if (prdContainer) prdContainer.style.display = 'none';
                        return;
                    }
                    
                    // Use existing containers to display PRD content
                    const emptyState = document.getElementById('prd-empty-state');
                    const prdContainer = document.getElementById('prd-container');
                    const streamingContent = document.getElementById('prd-streaming-content');
                    const streamingStatus = document.getElementById('prd-streaming-status');
                    
                    if (emptyState) emptyState.style.display = 'none';
                    if (prdContainer) prdContainer.style.display = 'block';
                    
                    // Update status to show it's a loaded PRD
                    if (streamingStatus) {
                        streamingStatus.textContent = data.updated_at ? `Last updated: ${data.updated_at}` : 'Loaded from server';
                    }
                    
                    // Add action buttons to the prd-actions-container
                    const prdActionsContainer = document.querySelector('.prd-actions-container');
                    if (prdActionsContainer) {
                        // Get current PRD name
                        const currentPrdName = data.name || 'Main PRD';
                        
                        // Clear any existing content and add the action buttons
                        prdActionsContainer.innerHTML = `
                            <div class="prd-actions" style="display: flex; gap: 4px;">
                                <button class="artifact-edit-btn" id="prd-edit-btn" data-project-id="${projectId}" title="Edit" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="artifact-copy-btn" id="prd-copy-btn" data-project-id="${projectId}" title="Copy" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                    <i class="fas fa-copy"></i>
                                </button>
                                <button class="artifact-download-btn" id="prd-download-btn" data-project-id="${projectId}" title="Download PDF" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                    <i class="fas fa-download"></i>
                                </button>
                                <button class="artifact-delete-btn" id="prd-delete-action-btn" data-project-id="${projectId}" data-prd-name="${currentPrdName}" title="Delete PRD" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'; this.style.color='#ef4444'" onmouseout="this.style.opacity='0.7'; this.style.color='#fff'">
                                    <i class="fas fa-trash"></i>
                                </button>
                                
                            </div>
                        `;
                    }
                    
                    // Render the PRD content
                    if (streamingContent) {
                        let parsedContent = prdContent;
                        
                        // Ensure marked is loaded and configured
                        if (typeof marked !== 'undefined') {
                            try {
                                // Configure marked if not already done
                                if (!window.markedConfigured) {
                                    marked.setOptions({
                                        gfm: true,          // Enable GitHub Flavored Markdown
                                        breaks: true,       // Add <br> on line breaks
                                        headerIds: true,    // Add IDs to headers
                                        mangle: false,      // Don't mangle header IDs
                                        tables: true,       // Enable table support
                                        smartLists: true,   // Improve behavior of lists
                                        xhtml: false        // Don't use XHTML compatible tags
                                    });
                                    window.markedConfigured = true;
                                    console.log('[ArtifactsLoader] Marked.js configured for PRD rendering');
                                }
                                
                                parsedContent = marked.parse(prdContent);
                                console.log('[ArtifactsLoader] PRD markdown parsed successfully');
                            } catch (e) {
                                console.error('[ArtifactsLoader] Error parsing PRD markdown:', e);
                                // Fallback to basic line break conversion
                                parsedContent = prdContent
                                    .replace(/##/g, '\n##')
                                    .replace(/\n/g, '<br>');
                            }
                        } else {
                            console.warn('[ArtifactsLoader] Marked.js not available for PRD, using fallback rendering');
                            // Basic fallback rendering
                            parsedContent = prdContent
                                .replace(/##/g, '\n##')
                                .replace(/\n/g, '<br>');
                        }
                        
                        streamingContent.innerHTML = parsedContent;
                    }
                    
                    // Clear streaming state since we're loading saved content
                    if (window.prdStreamingState) {
                        window.prdStreamingState.isStreaming = false;
                        window.prdStreamingState.fullContent = prdContent;
                    }
                    
                    // Add click event listener for the edit button
                    const editBtn = document.getElementById('prd-edit-btn');
                    if (editBtn) {
                        editBtn.addEventListener('click', function() {
                            ArtifactsEditor.enablePRDEdit(projectId, prdContent);
                        });
                    }
                    
                    // Add click event listener for the PDF download button
                    const downloadBtn = document.getElementById('prd-download-btn');
                    if (downloadBtn) {
                        downloadBtn.addEventListener('click', function() {
                            ArtifactsLoader.downloadFileAsPDF(projectId, data.title || 'Product Requirement Document', prdContent);
                        });
                    }
                    
                    // Add click event listener for the copy button
                    const copyBtn = document.getElementById('prd-copy-btn');
                    if (copyBtn) {
                        copyBtn.addEventListener('click', function() {
                            ArtifactsLoader.copyToClipboard(prdContent, 'PRD content');
                        });
                    }
                    
                    // Add click event listener for the delete button
                    const deleteActionBtn = document.getElementById('prd-delete-action-btn');
                    if (deleteActionBtn) {
                        deleteActionBtn.addEventListener('click', function() {
                            const prdNameToDelete = this.getAttribute('data-prd-name');
                            if (confirm(`Are you sure you want to delete the PRD "${prdNameToDelete}"?`)) {
                                // Delete the PRD
                                fetch(`/projects/${projectId}/api/prd/?prd_name=${encodeURIComponent(prdNameToDelete)}`, {
                                    method: 'DELETE',
                                    headers: {
                                        'X-CSRFToken': getCsrfToken()
                                    }
                                })
                                .then(response => response.json())
                                .then(deleteData => {
                                    if (deleteData.success) {
                                        window.showToast(`PRD "${prdNameToDelete}" deleted successfully`, 'success');
                                        // Load Main PRD after deletion
                                        window.ArtifactsLoader.loadPRD(projectId, 'Main PRD');
                                    } else {
                                        window.showToast(`Error deleting PRD: ${deleteData.error || 'Unknown error'}`, 'error');
                                    }
                                })
                                .catch(error => {
                                    console.error('[ArtifactsLoader] Error deleting PRD:', error);
                                    window.showToast('Error deleting PRD', 'error');
                                });
                            }
                        });
                    }
                })
                .catch(error => {
                    console.error('Error fetching PRD:', error);
                    
                    // Hide container and show empty state with error
                    if (prdContainer) prdContainer.style.display = 'none';
                    if (emptyState) {
                        emptyState.style.display = 'block';
                        emptyState.innerHTML = `
                            <div class="error-state">
                                <div class="error-state-icon">
                                    <i class="fas fa-exclamation-triangle"></i>
                                </div>
                                <div class="error-state-text">
                                    Error loading PRD. Please try again.
                                </div>
                            </div>
                        `;
                    }
                });
        },
        
        
        
        
        /**
         * Unified document streaming function for PRD and Implementation
         * @param {string} contentChunk - The chunk of content to append
         * @param {boolean} isComplete - Whether this is the final chunk
         * @param {number} projectId - The ID of the current project
         * @param {string} documentType - Type of document ('prd' or 'implementation')
         * @param {string} documentName - Name of the document
         * @param {number} fileId - The file ID (optional, provided when document is saved)
         */
        streamDocumentContent: function(contentChunk, isComplete, projectId, documentType, documentName) {
            console.log(`[ArtifactsLoader] streamDocumentContent called`);
            console.log(`  Type: ${documentType}, Name: ${documentName}`);
            console.log(`  Chunk length: ${contentChunk ? contentChunk.length : 0}, isComplete: ${isComplete}`);
            console.log(`  Project ID: ${projectId}`);
            
        
            // Ensure filebrowser tab is active
            const filebrowserTab = document.querySelector('.tab-button[data-tab="filebrowser"]');
            const filebrowserPane = document.getElementById('filebrowser');
            if (filebrowserTab && !filebrowserTab.classList.contains('active')) {
                console.log('[ArtifactsLoader] Activating filebrowser tab for streaming');
                document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
                filebrowserTab.classList.add('active');
                if (filebrowserPane) filebrowserPane.classList.add('active');
            }
            
            // Initialize streaming state
            const stateKey = `${documentType}StreamingState`;
            if (!window[stateKey]) {
                window[stateKey] = {
                    fullContent: '',
                    isStreaming: false,
                    projectId: projectId,
                    documentName: documentName,
                    documentType: documentType
                };
            }
            
            // Get or create streaming viewer
            const filebrowserViewer = document.getElementById('filebrowser-viewer');
            const filebrowserMain = document.getElementById('filebrowser-main');
            
            if (!filebrowserViewer || !filebrowserMain) {
                console.error('[ArtifactsLoader] File browser elements not found');
                return;
            }
            
            // Start streaming if not already started
            if (!window[stateKey].isStreaming) {
                window[stateKey].isStreaming = true;
                window[stateKey].fullContent = '';
                window[stateKey].projectId = projectId;
                
                // Switch to viewer mode
                filebrowserMain.style.display = 'none';
                filebrowserViewer.style.display = 'flex';
                
                // Set viewer title with edit button
                const viewerTitle = document.getElementById('viewer-title');
                if (viewerTitle) {
                    viewerTitle.innerHTML = `
                        <span id="viewer-title-text">Generating...</span>
                        <button id="viewer-title-edit" style="background: none; border: none; color: #9ca3af; cursor: pointer; margin-left: 8px; padding: 4px; opacity: 0.7;" title="Edit name" disabled>
                            <i class="fas fa-pencil" style="font-size: 12px;"></i>
                        </button>
                    `;
                }
                
                // Clear viewer content but keep the structure
                const viewerMarkdown = document.getElementById('viewer-markdown');
                if (viewerMarkdown) {
                    viewerMarkdown.innerHTML = '';
                }
                
                // Hide action buttons during streaming
                const viewerActions = document.querySelector('.viewer-actions');
                if (viewerActions) {
                    viewerActions.style.display = 'none';
                }
                
                // Show streaming status in metadata area
                const viewerMeta = document.getElementById('viewer-meta');
                if (viewerMeta) {
                    viewerMeta.innerHTML = `
                        <span style="color: #8b5cf6;"><i class="fas fa-circle-notch fa-spin"></i> Generating ${documentType}...</span>
                    `;
                    viewerMeta.style.display = 'flex';
                }
                
                // Make sure back button is visible
                const backButton = document.querySelector('.viewer-back');
                if (backButton) {
                    backButton.style.display = 'flex';
                }
                
                // Open artifacts panel if not already open
                if (window.ArtifactsPanel && !window.ArtifactsPanel.isOpen()) {
                    window.ArtifactsPanel.open();
                    console.log('[ArtifactsLoader] Opened artifacts panel for document streaming');
                }
            }
            
            // Append content chunk
            if (contentChunk) {
                window[stateKey].fullContent += contentChunk;
                
                // Update viewer content
                const viewerMarkdown = document.getElementById('viewer-markdown');
                if (viewerMarkdown && typeof marked !== 'undefined') {
                    const renderedHTML = marked.parse(window[stateKey].fullContent);
                    viewerMarkdown.innerHTML = renderedHTML;
                } else if (viewerMarkdown) {
                    // Fallback to plain text
                    viewerMarkdown.innerHTML = window[stateKey].fullContent
                        .replace(/\n/g, '<br>')
                        .replace(/\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;');
                }
                
                // Auto-scroll to show new content
                if (viewerMarkdown) {
                    // Use requestAnimationFrame to ensure DOM has updated before scrolling
                    // Use instant scroll (not smooth) during streaming for better UX
                    requestAnimationFrame(() => {
                        requestAnimationFrame(() => {
                            const before = viewerMarkdown.scrollTop;
                            const scrollHeight = viewerMarkdown.scrollHeight;
                            viewerMarkdown.scrollTop = scrollHeight;
                            console.log(`[Stream Scroll] Before: ${before}, Height: ${scrollHeight}, After: ${viewerMarkdown.scrollTop}`);
                        });
                    });
                }
            }
            
            // Store streaming info for handleDocumentSaved to use later
            // This is crucial for the save notification to work properly
            window[`${documentType}StreamingInfo`] = {
                projectId: projectId,
                documentName: documentName,
                documentType: documentType,
                viewerTitle: `${documentType.toUpperCase()} - ${documentName}`
            };
            console.log(`[ArtifactsLoader] Stored streaming info for ${documentType}:`, window[`${documentType}StreamingInfo`]);
        },
        
        /**
         * Handle save notification after document is saved
         */
        handleDocumentSaved: function(notification) {
            console.log('[ArtifactsLoader] ==========================================');
            console.log('[ArtifactsLoader] DOCUMENT SAVED NOTIFICATION RECEIVED!');
            console.log('[ArtifactsLoader] Notification:', notification);
            console.log('[ArtifactsLoader] File ID:', notification.file_id);
            console.log('[ArtifactsLoader] File Type:', notification.file_type);
            console.log('[ArtifactsLoader] File Name:', notification.file_name);
            console.log('[ArtifactsLoader] Notification Type:', notification.notification_type);
            console.log('[ArtifactsLoader] Current Project ID:', window.currentProjectId);
            console.log('[ArtifactsLoader] ==========================================');
            
            const documentType = notification.file_type || notification.notification_type;
            console.log('[ArtifactsLoader] Looking for streaming info for type:', documentType);
            console.log('[ArtifactsLoader] Available streaming info keys:', Object.keys(window).filter(k => k.includes('StreamingInfo')));
            
            // Also check for all possible streaming info variations
            console.log('[ArtifactsLoader] Checking window.prdStreamingInfo:', window.prdStreamingInfo);
            console.log('[ArtifactsLoader] Checking window.implementationStreamingInfo:', window.implementationStreamingInfo);
            
            const streamingInfo = window[`${documentType}StreamingInfo`];
            
            if (!streamingInfo) {
                console.log('[ArtifactsLoader] No streaming info found for type:', documentType);
                console.log('[ArtifactsLoader] Will still try to load the file using file_id');
                // Don't return, continue to load the file
            }
            
            // Clear the streaming info if it exists
            if (streamingInfo) {
                window[`${documentType}StreamingInfo`] = null;
            }
            
            // Get project ID and file ID
            // Priority: notification.project_id > streamingInfo.projectId > window.currentProjectId
            const projectId = notification.project_id || streamingInfo?.projectId || window.currentProjectId;
            const documentName = streamingInfo?.documentName || notification.file_name;
            const viewerTitle = streamingInfo?.viewerTitle || `${documentType.toUpperCase()} - ${documentName}`;
            const fileId = notification.file_id;
            
            console.log(`[ArtifactsLoader] Using project ID: ${projectId} (from: ${notification.project_id ? 'notification' : streamingInfo?.projectId ? 'streamingInfo' : 'window.currentProjectId'})`)
            
            if (!fileId) {
                console.error('[ArtifactsLoader] No file_id in save notification');
                return;
            }
            
            console.log(`[ArtifactsLoader] Loading saved document with ID: ${fileId}`);
            console.log(`[ArtifactsLoader] Making API call to: /projects/${projectId}/api/files/${fileId}/content/`);
            
            // Ensure the viewFileContent function is available globally
            if (window.viewFileContent) {
                // Add a small delay to ensure UI is ready after streaming completes
                setTimeout(() => {
                    console.log(`[ArtifactsLoader] Calling viewFileContent after delay`);
                    window.viewFileContent(fileId, documentName);
                }, 100);
            } else {
                console.error('[ArtifactsLoader] viewFileContent function not available globally');
            }
            
        },
        
        
        /**
         * Save streamed document to the server
         */
        saveStreamedDocument: function(documentType, projectId) {
            const stateKey = `${documentType}StreamingState`;
            const state = window[stateKey];
            
            if (!state || !state.fullContent) {
                console.error('No content to save');
                return;
            }
            
            // Show saving indicator
            const viewerTitle = document.getElementById('viewer-title');
            if (viewerTitle) {
                viewerTitle.textContent = `${state.documentName} (Saving...)`;
            }
            
            // Create document via API
            const payload = {
                name: state.documentName,
                type: documentType,
                content: state.fullContent,
                project_id: projectId
            };
            
            fetch(`/projects/${projectId}/documents/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify(payload)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && data.file_id) {
                    window.showToast('Document saved successfully', 'success');
                    // Clear the streaming state
                    window[stateKey] = null;
                    
                    // Reload the file browser and open the saved document
                    this.loadFileBrowser(projectId, {
                        openFileId: data.file_id,
                        openFileName: state.documentName
                    });
                } else {
                    window.showToast('Error saving document', 'error');
                    if (viewerTitle) {
                        viewerTitle.textContent = state.documentName;
                    }
                }
            })
            .catch(error => {
                console.error('Error saving document:', error);
                window.showToast('Error saving document', 'error');
                if (viewerTitle) {
                    viewerTitle.textContent = state.documentName;
                }
            });
        },
        
        /**
         * Download streamed document
         */
        downloadStreamedDocument: function(documentType, documentName) {
            const stateKey = `${documentType}StreamingState`;
            const state = window[stateKey];
            
            if (!state || !state.fullContent) {
                console.error('No content to download');
                return;
            }
            
            // Create a blob and download
            const blob = new Blob([state.fullContent], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${documentName}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },
        
        /**
         * Load implementation from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadImplementation: function(projectId) {
            console.log(`[ArtifactsLoader] loadImplementation called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading implementation');
                return;
            }
            
            // Get implementation tab content element
            const implementationTab = document.getElementById('implementation');
            if (!implementationTab) {
                console.warn('[ArtifactsLoader] Implementation tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for implementation');
            implementationTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading implementation...</div></div>';
            
            // Fetch implementation from API
            const url = `/projects/${projectId}/api/implementation/`;
            console.log(`[ArtifactsLoader] Fetching implementation from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] Implementation API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Implementation API data received:', data);
                    // Process implementation data
                    const implementationContent = data.content || '';
                    
                    if (!implementationContent) {
                        // Show empty state if no implementation found
                        console.log('[ArtifactsLoader] No implementation found, showing empty state');
                        implementationTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-code"></i>
                                </div>
                                <div class="empty-state-text">
                                    No implementation plan available yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Render implementation content with markdown
                    implementationTab.innerHTML = `
                        <div class="implementation-container">
                            <div class="implementation-header">
                                <h2>${data.title || 'Implementation Plan'}</h2>
                                <div class="implementation-meta" style="display: flex; justify-content: space-between; align-items: center;">
                                    <span>${data.updated_at ? `Last updated: ${data.updated_at}` : ''}</span>
                                    <div class="implementation-actions" style="display: flex; gap: 4px;">
                                        <button class="artifact-edit-btn" id="implementation-edit-btn" data-project-id="${projectId}" title="Edit" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                            <i class="fas fa-edit"></i>
                                        </button>
                                        <button class="artifact-copy-btn" id="implementation-copy-btn" data-project-id="${projectId}" title="Copy" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                            <i class="fas fa-copy"></i>
                                        </button>
                                        <button class="artifact-delete-btn" id="implementation-delete-btn" data-project-id="${projectId}" title="Delete Implementation" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'; this.style.color='#ef4444'" onmouseout="this.style.opacity='0.7'; this.style.color='#fff'">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="implementation-content markdown-content">
                                ${typeof marked !== 'undefined' ? marked.parse(implementationContent) : implementationContent}
                            </div>
                        </div>
                    `;
                    
                    // Add click event listener for the edit button
                    const editBtn = document.getElementById('implementation-edit-btn');
                    if (editBtn) {
                        editBtn.addEventListener('click', function() {
                            ArtifactsEditor.enableImplementationEdit(projectId, implementationContent);
                        });
                    }
                    
                    // Add click event listener for the copy button
                    const copyBtn = document.getElementById('implementation-copy-btn');
                    if (copyBtn) {
                        copyBtn.addEventListener('click', function() {
                            ArtifactsLoader.copyToClipboard(implementationContent, 'Implementation plan');
                        });
                    }
                    
                    // Add click event listener for the delete button
                    const deleteBtn = document.getElementById('implementation-delete-btn');
                    if (deleteBtn) {
                        deleteBtn.addEventListener('click', function() {
                            if (confirm('Are you sure you want to delete the implementation plan?')) {
                                // Delete the implementation
                                fetch(`/projects/${projectId}/api/implementation/`, {
                                    method: 'DELETE',
                                    headers: {
                                        'X-CSRFToken': getCsrfToken()
                                    }
                                })
                                .then(response => response.json())
                                .then(deleteData => {
                                    if (deleteData.success) {
                                        window.showToast('Implementation plan deleted successfully', 'success');
                                        // Show empty state
                                        implementationTab.innerHTML = `
                                            <div class="empty-state" id="implementation-empty-state">
                                                <div class="empty-state-icon">
                                                    <i class="fas fa-code"></i>
                                                </div>
                                                <div class="empty-state-text">
                                                    No implementation plan available yet.
                                                </div>
                                            </div>
                                        `;
                                    } else {
                                        window.showToast(`Error deleting implementation: ${deleteData.error || 'Unknown error'}`, 'error');
                                    }
                                })
                                .catch(error => {
                                    console.error('[ArtifactsLoader] Error deleting implementation:', error);
                                    window.showToast('Error deleting implementation plan', 'error');
                                });
                            }
                        });
                    }
                })
                .catch(error => {
                    console.error('Error fetching implementation:', error);
                    implementationTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading implementation. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        /**
         * Load tickets from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadTickets: function(projectId) {
            console.log(`[ArtifactsLoader] loadTickets called with project ID: ${projectId}`);

            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading tickets');
                return;
            }

            const ticketsTab = document.getElementById('tickets');
            if (!ticketsTab) {
                console.warn('[ArtifactsLoader] Tickets tab element not found');
                return;
            }

            const modalHelpers = this.getTicketModalHelpers();
            modalHelpers.setProjectId(projectId);

            const getCsrfToken = () => {
                if (typeof getCookie === 'function') {
                    return getCookie('csrftoken');
                }
                if (typeof window.getCookie === 'function') {
                    return window.getCookie('csrftoken');
                }
                return '';
            };

            const deleteTicket = (ticket) => {
                if (!ticket) {
                    console.warn('[ArtifactsLoader] Attempted to delete an unknown ticket');
                    return Promise.resolve(false);
                }

                if (!confirm(`Are you sure you want to delete the ticket "${ticket.name}"?`)) {
                    return Promise.resolve(false);
                }

                return fetch(`/projects/${projectId}/api/checklist/${ticket.id}/delete/`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': getCsrfToken()
                    }
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Failed to delete ticket');
                    }
                    return response.json().catch(() => ({}));
                })
                .then(() => {
                    window.showToast('Ticket deleted successfully', 'success');
                    ArtifactsLoader.loadTickets(projectId);
                    return true;
                })
                .catch(error => {
                    console.error('Error deleting ticket:', error);
                    window.showToast('Error deleting ticket', 'error');
                    return false;
                });
            };

            console.log('[ArtifactsLoader] Showing loading state for tickets');
            ticketsTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading tickets...</div></div>';

            const url = `/projects/${projectId}/api/checklist/`;
            console.log(`[ArtifactsLoader] Fetching tickets from API: ${url}`);

            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] Tickets API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Tickets API data received:', data);
                    const tickets = data.checklist || [];
                    console.log(`[ArtifactsLoader] Found ${tickets.length} tickets`);

                    if (tickets.length === 0) {
                        ticketsTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-ticket"></i>
                                </div>
                                <div class="empty-state-text">
                                    No tickets created yet.
                                </div>
                            </div>
                        `;
                        modalHelpers.setHandlers();
                        return;
                    }

                    const priorities = [...new Set(tickets.map(ticket => ticket.priority || 'Medium'))].sort();

                    ticketsTab.innerHTML = `
                        <div class="tickets-container">
                            <div class="ticket-filters">
                                <div class="filter-options">
                                    <div class="filter-group">
                                        <select id="priority-filter" class="priority-filter-dropdown">
                                            <option value="all">All Priorities</option>
                                            ${priorities.map(priority => `<option value="${priority}">${priority}</option>`).join('')}
                                        </select>
                                        <button id="clear-filters" class="clear-filters-btn" title="Clear filters">
                                            <i class="fas fa-times"></i>
                                        </button>
                                        <button id="sync-linear" class="sync-linear-btn" title="Sync with Linear">
                                            <i class="fas fa-sync"></i> Sync with Linear
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="tickets-content" id="tickets-content"></div>
                        </div>
                    `;

                    const ticketsContent = document.getElementById('tickets-content');
                    const priorityFilter = document.getElementById('priority-filter');
                    const clearFiltersBtn = document.getElementById('clear-filters');
                    const syncLinearBtn = document.getElementById('sync-linear');

                    modalHelpers.ensure();
                    modalHelpers.setHandlers({
                        onEdit: (ticket) => {
                            modalHelpers.close();
                            if (typeof window.editChecklistItem === 'function' && ticket) {
                                window.editChecklistItem(ticket.id);
                            }
                        },
                        onDelete: (ticket) => deleteTicket(ticket).then((removed) => {
                            if (removed) {
                                modalHelpers.close();
                            }
                            return removed;
                        }),
                        onExecute: (ticket) => {
                            if (ticket) {
                                modalHelpers.close();
                                ArtifactsLoader.executeTicket(ticket.id);
                            }
                        }
                    });

                    const renderTickets = (filterPriority = 'all') => {
                        let filteredTickets = [...tickets];
                        if (filterPriority !== 'all') {
                            filteredTickets = filteredTickets.filter(ticket => (ticket.priority || 'Medium') === filterPriority);
                        }

                        let html = '<div class="tickets-by-status">';

                        if (filteredTickets.length === 0) {
                            html += `
                                <div class="no-results">
                                    <div class="empty-state-icon">
                                        <i class="fas fa-filter"></i>
                                    </div>
                                    <div class="empty-state-text">
                                        No tickets match your filter criteria.
                                    </div>
                                </div>
                            `;
                        } else {
                            filteredTickets.forEach(ticket => {
                                const priorityLevel = (ticket.priority || 'Medium').toLowerCase();
                                const priorityClass = `${priorityLevel}-priority`;
                                const status = ticket.status || 'open';
                                const isHighlighted = filterPriority !== 'all' && (ticket.priority || 'Medium') === filterPriority;

                                let summary = ticket.description || '';
                                const descriptionLimit = 300;
                                if (summary.length > descriptionLimit) {
                                    const lastSpaceIndex = summary.lastIndexOf(' ', descriptionLimit);
                                    const truncateIndex = lastSpaceIndex > 0 ? lastSpaceIndex : descriptionLimit;
                                    summary = `${summary.substring(0, truncateIndex)}...`;
                                }
                                summary = modalHelpers.escapeHtml(summary).replace(/\n/g, '<br>');

                                html += `
                                    <div class="ticket-card" data-ticket-id="${ticket.id}" data-priority="${ticket.priority || 'Medium'}">
                                        <div class="card-header ${status}">
                                            <h4 class="card-title">${modalHelpers.escapeHtml(ticket.name || 'Untitled Ticket')}</h4>
                                        </div>
                                        <div class="card-body">
                                            <div class="card-description">${summary}</div>
                                            <div class="card-meta">
                                                <div class="card-tags">
                                                    <span class="priority-tag ${priorityClass} ${isHighlighted ? 'filter-active' : ''}">
                                                        <i class="fas fa-flag"></i> ${modalHelpers.escapeHtml(ticket.priority || 'Medium')} Priority
                                                    </span>
                                                    <span class="status-tag status-${status}">
                                                        ${status.replace('_', ' ').charAt(0).toUpperCase() + status.replace('_', ' ').slice(1)}
                                                    </span>
                                                    ${ticket.linear_issue_id ? `
                                                    <span class="linear-sync-tag" title="Synced with Linear">
                                                        <svg viewBox="0 0 32 32" width="14" height="14" fill="currentColor">
                                                            <path d="M2.66675 2.66699H29.3334V7.46732H2.66675V2.66699Z"/>
                                                            <path d="M2.66675 9.86719H29.3334V14.6675H2.66675V9.86719Z"/>
                                                            <path d="M2.66675 17.0674H29.3334V21.8677H2.66675V17.0674Z"/>
                                                            <path d="M2.66675 24.2676H17.0668V29.0679H2.66675V24.2676Z"/>
                                                        </svg>
                                                        Synced
                                                    </span>
                                                    ` : ''}
                                                </div>
                                                <button class="view-details-btn" data-index="${filteredTickets.indexOf(ticket)}" title="View details">
                                                    <i class="fas fa-info-circle"></i>
                                                </button>
                                                <button class="delete-ticket-btn" data-ticket-id="${ticket.id}" title="Delete ticket">
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                `;
                            });
                        }

                        html += '</div>';
                        ticketsContent.innerHTML = html;

                        const detailButtons = ticketsContent.querySelectorAll('.view-details-btn');
                        detailButtons.forEach((button, index) => {
                            button.addEventListener('click', function(event) {
                                event.stopPropagation();
                                modalHelpers.open(filteredTickets, index);
                            });
                        });

                        const deleteButtons = ticketsContent.querySelectorAll('.delete-ticket-btn');
                        deleteButtons.forEach(button => {
                            button.addEventListener('click', function(event) {
                                event.stopPropagation();
                                const ticketId = parseInt(this.getAttribute('data-ticket-id'), 10);
                                const ticket = tickets.find(t => t.id === ticketId);
                                deleteTicket(ticket);
                            });
                        });
                    };

                    if (priorityFilter) {
                        priorityFilter.addEventListener('change', function() {
                            renderTickets(this.value);
                        });
                    }

                    if (clearFiltersBtn) {
                        clearFiltersBtn.addEventListener('click', function() {
                            if (priorityFilter) {
                                priorityFilter.value = 'all';
                            }
                            renderTickets('all');
                        });
                    }

                    if (syncLinearBtn) {
                        syncLinearBtn.addEventListener('click', function() {
                            if (!data.linear_sync_enabled) {
                                window.showToast('Linear sync is not enabled for this project. Please go to project settings to configure Linear integration.', 'error');
                                return;
                            }

                            const button = this;
                            button.disabled = true;
                            button.innerHTML = '<i class="fas fa-sync fa-spin"></i> Syncing...';

                            fetch(`/projects/${projectId}/api/linear/sync/`, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': getCsrfToken()
                                }
                            })
                            .then(response => response.json())
                            .then(syncData => {
                                if (syncData.success) {
                                    window.showToast(syncData.message || 'Tickets synced successfully!', 'success');
                                    ArtifactsLoader.loadTickets(projectId);
                                } else {
                                    if (syncData.error && syncData.error.includes('API key not configured')) {
                                        window.showToast('Linear API key not configured. Please go to Integrations to add your Linear API key.', 'error');
                                    } else if (syncData.error && syncData.error.includes('team ID not set')) {
                                        window.showToast('Linear team ID not set. Please go to project settings to configure Linear integration.', 'error');
                                    } else {
                                        window.showToast(syncData.error || 'Failed to sync tickets', 'error');
                                    }
                                    button.disabled = false;
                                    button.innerHTML = '<i class="fas fa-sync"></i> Sync with Linear';
                                }
                            })
                            .catch(error => {
                                console.error('Error syncing with Linear:', error);
                                window.showToast('Error syncing with Linear', 'error');
                                button.disabled = false;
                                button.innerHTML = '<i class="fas fa-sync"></i> Sync with Linear';
                            });
                        });
                    }

                    renderTickets();
                })
                .catch(error => {
                    console.error('Error fetching tickets:', error);
                    ticketsTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading tickets. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        closeTicketModal: function() {
            const helpers = this.getTicketModalHelpers();
            helpers.close();
        },
        
        /**
         * Load design schema from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadDesignSchema: function(projectId) {
            console.log(`[ArtifactsLoader] loadDesignSchema called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading design schema');
                return;
            }
            
            // Get design schema tab content element
            const designTab = document.getElementById('design');
            if (!designTab) {
                console.warn('[ArtifactsLoader] Design tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for design schema');
            designTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading design schema...</div></div>';
            
            // Fetch design schema from API
            const url = `/projects/${projectId}/api/design-schema/`;
            console.log(`[ArtifactsLoader] Fetching design schema from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] Design schema API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Design schema API data received:', data);
                    // Process design schema data
                    const designSchemaContent = data.content || '';
                    
                    if (!designSchemaContent) {
                        // Show empty state if no design schema found
                        console.log('[ArtifactsLoader] No design schema found, showing empty state');
                        designTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-file-alt"></i>
                                </div>
                                <div class="empty-state-text">
                                    No design schema available yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Render design schema content with markdown
                    designTab.innerHTML = `
                        <div class="design-schema-container">
                            <div class="design-schema-header">
                                <h2>${data.title || 'Design Schema'}</h2>
                                <div class="design-schema-meta">
                                    ${data.updated_at ? `<span>Last updated: ${data.updated_at}</span>` : ''}
                                </div>
                            </div>
                            <div class="design-schema-content markdown-content">
                                ${typeof marked !== 'undefined' ? marked.parse(designSchemaContent) : designSchemaContent}
                            </div>
                        </div>
                    `;
                })
                .catch(error => {
                    console.error('Error fetching design schema:', error);
                    designTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading design schema. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        /**
         * Load codebase explorer from the development module for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadCodebase: function(projectId) {
            console.log(`[ArtifactsLoader] loadCodebase called with project ID: ${projectId}`);
            console.log(`[ArtifactsLoader] Project ID type: ${typeof projectId}`);
            console.log(`[ArtifactsLoader] Project ID truthy: ${!!projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading codebase');
                return;
            }
            
            // Get codebase tab content element
            const codebaseTab = document.getElementById('codebase');
            if (!codebaseTab) {
                console.warn('[ArtifactsLoader] Codebase tab element not found');
                return;
            }
            
            // Get codebase UI elements
            const codebaseLoading = document.getElementById('codebase-loading');
            const codebaseEmpty = document.getElementById('codebase-empty');
            const codebaseFrameContainer = document.getElementById('codebase-frame-container');
            const codebaseIframe = document.getElementById('codebase-iframe');
            
            console.log('[ArtifactsLoader] UI Elements found:', {
                codebaseLoading: !!codebaseLoading,
                codebaseEmpty: !!codebaseEmpty,
                codebaseFrameContainer: !!codebaseFrameContainer,
                codebaseIframe: !!codebaseIframe
            });
            
            if (!codebaseLoading || !codebaseEmpty || !codebaseFrameContainer || !codebaseIframe) {
                console.warn('[ArtifactsLoader] Codebase UI elements not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for codebase');
            codebaseLoading.style.display = 'block';
            codebaseEmpty.style.display = 'none';
            codebaseFrameContainer.style.display = 'none';
            
            // Get conversation ID using the helper function
            const conversationId = getCurrentConversationId();
            console.log(`[ArtifactsLoader] Conversation ID: ${conversationId}`);
            
            // Build the editor URL with appropriate parameters
            let editorUrl = `/development/editor/?project_id=${projectId}`;
            
            // Add conversation ID if available
            if (conversationId) {
                editorUrl += `&conversation_id=${conversationId}`;
                console.log(`[ArtifactsLoader] Including conversation ID: ${conversationId}`);
            }
            
            console.log(`[ArtifactsLoader] Loading codebase explorer from URL: ${editorUrl}`);
            console.log(`[ArtifactsLoader] About to set iframe.src - this should trigger network request`);
            
            // Set up iframe event handlers
            codebaseIframe.onload = function() {
                // Hide loading and show iframe when loaded
                codebaseLoading.style.display = 'none';
                codebaseFrameContainer.style.display = 'block';
                console.log('[ArtifactsLoader] Codebase iframe loaded successfully');
                console.log('[ArtifactsLoader] Iframe content window:', codebaseIframe.contentWindow);
            };
            
            codebaseIframe.onerror = function() {
                // Show error state if loading fails
                codebaseLoading.style.display = 'none';
                codebaseEmpty.style.display = 'block';
                codebaseEmpty.innerHTML = `
                    <div class="error-state">
                        <div class="error-state-icon">
                            <i class="fas fa-exclamation-triangle"></i>
                        </div>
                        <div class="error-state-text">
                            Error loading codebase explorer. Please try again.
                        </div>
                    </div>
                `;
                console.error('[ArtifactsLoader] Error loading codebase iframe');
            };
            
            // Set the iframe source to load the editor
            console.log('[ArtifactsLoader] Setting iframe src now...');
            codebaseIframe.src = editorUrl;
            console.log('[ArtifactsLoader] Iframe src set to:', codebaseIframe.src);
        },
        
        /**
         * Render implementation content properly handling XML/HTML-like content
         * @param {string} content - The implementation content to render
         * @returns {string} The rendered HTML content
         */
        renderImplementationContent: function(content) {
            if (!content) return '';
            
            // Check if content looks like XML/HTML (contains tags)
            if (content.includes('<') && content.includes('>')) {
                // If it looks like structured data, wrap it in a code block
                const escapedContent = content
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
                
                return `<pre><code>${escapedContent}</code></pre>`;
            }
            
            // Otherwise, render as markdown
            if (typeof marked !== 'undefined') {
                return marked.parse(content);
            }
            
            // Fallback to plain text with basic escaping
            return content.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        },
        
        /**
         * Load checklist items from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadChecklist: function(projectId) {
            console.log(`[ArtifactsLoader] loadChecklist called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading checklist');
                return;
            }
            
            // Get checklist tab content element
            const checklistTab = document.getElementById('checklist');
            if (!checklistTab) {
                console.warn('[ArtifactsLoader] Checklist tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for checklist');
            checklistTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading checklist...</div></div>';
            
            // Fetch checklist from API
            const checklistUrl = `/projects/${projectId}/api/checklist/`;
            console.log(`[ArtifactsLoader] Fetching checklist from API: ${checklistUrl}`);
            
            fetch(checklistUrl)
                .then(response => {
                    console.log(`[ArtifactsLoader] Checklist API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Checklist API data received:', data);
                    // Process checklist data
                    const checklist = data.checklist || [];
                    console.log(`[ArtifactsLoader] Found ${checklist.length} checklist items`);

                    const modalHelpers = this.getTicketModalHelpers();
                    modalHelpers.setProjectId(projectId);
                    
                    if (checklist.length === 0) {
                        // Show empty state if no checklist items found
                        console.log('[ArtifactsLoader] No checklist items found, showing empty state');
                        checklistTab.innerHTML = `
                            <div class="checklist-empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-check-square"></i>
                                </div>
                                <div class="empty-state-text">
                                    No checklist items created yet.
                                </div>
                            </div>
                        `;
                        return;
                    }

                    // Extract unique statuses and roles for filter dropdowns
                    const statuses = [...new Set(checklist.map(item => item.status || 'open'))].sort();
                    const roles = [...new Set(checklist.map(item => item.role || 'user'))].sort();

                    // Create container with filters
                    let checklistHTML = `
                        <div class="checklist-wrapper">
                            <div class="checklist-header" style="display: flex; align-items: center; justify-content: flex-end; padding: 12px 16px;">
                                <div class="checklist-filters" style="margin-right: 12px;">
                                    <div class="filter-options">
                                        <div class="filter-group">
                                            <select id="status-filter" class="checklist-filter-dropdown">
                                                <option value="all">All Statuses</option>
                                                ${statuses.map(status => `<option value="${status}">${status.replace('_', ' ').charAt(0).toUpperCase() + status.replace('_', ' ').slice(1)}</option>`).join('')}
                                            </select>
                                            <select id="role-filter" class="checklist-filter-dropdown">
                                                <option value="all">All Assigned</option>
                                                ${roles.map(role => `<option value="${role}">${role.charAt(0).toUpperCase() + role.slice(1)}</option>`).join('')}
                                            </select>
                                            <button id="clear-checklist-filters" class="clear-filters-btn" title="Clear filters">
                                                <i class="fas fa-times"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                                <div class="dropdown" style="position: relative;">
                                    <button class="dropdown-toggle" id="checklist-actions-dropdown" style="background: rgba(40, 40, 40, 0.8); color: #888; border: 1px solid rgba(255, 255, 255, 0.08); width: 24px; height: 24px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.15s ease; padding: 0;"
                                            onmouseover="this.style.background='rgba(60, 60, 60, 0.9)'; this.style.color='#8b5cf6'; this.style.transform='scale(1.05)';" 
                                            onmouseout="this.style.background='rgba(40, 40, 40, 0.8)'; this.style.color='#888'; this.style.transform='scale(1)';">
                                        <i class="fas fa-ellipsis-v" style="font-size: 9px;"></i>
                                    </button>
                                    <div class="dropdown-menu" id="checklist-actions-menu" style="display: none; position: absolute; top: 100%; right: 0; background: #1e1e2e; border: 1px solid #313244; border-radius: 8px; min-width: 180px; box-shadow: 0 8px 16px rgba(0, 0, 0, 0.3); z-index: 1000; margin-top: 8px; overflow: hidden;">
                                        <button id="sync-checklist-linear" class="dropdown-item" style="display: block; width: 100%; text-align: left; padding: 12px 16px; background: none; border: none; color: #cdd6f4; cursor: pointer; transition: all 0.2s; font-size: 14px;" 
                                                onmouseover="this.style.background='#313244'; this.style.color='#b4befe';" onmouseout="this.style.background='none'; this.style.color='#cdd6f4';">
                                            <i class="fas fa-sync" style="margin-right: 10px; width: 14px; text-align: center; color: #8b5cf6;"></i> Sync with Linear
                                        </button>
                                        <div style="height: 1px; background: #313244;"></div>
                                        <button id="delete-all-checklist" class="dropdown-item" style="display: block; width: 100%; text-align: left; padding: 12px 16px; background: none; border: none; color: #f38ba8; cursor: pointer; transition: all 0.2s; font-size: 14px;"
                                                onmouseover="this.style.background='#313244'; this.style.color='#eba0ac';" onmouseout="this.style.background='none'; this.style.color='#f38ba8';">
                                            <i class="fas fa-trash-alt" style="margin-right: 10px; width: 14px; text-align: center;"></i> Delete All
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="checklist-container" id="checklist-content">
                                <!-- Checklist items will be loaded here -->
                            </div>
                        </div>
                    `;

                    checklistTab.innerHTML = checklistHTML;

                    // Get filter elements and content container
                    const checklistContent = document.getElementById('checklist-content');
                    const statusFilter = document.getElementById('status-filter');
                    const roleFilter = document.getElementById('role-filter');
                    const clearFiltersBtn = document.getElementById('clear-checklist-filters');

                    const deleteChecklistItem = (item) => {
                        if (!item) {
                            console.warn('[ArtifactsLoader] Attempted to delete an unknown checklist item');
                            return Promise.resolve(false);
                        }

                        if (!confirm(`Are you sure you want to delete "${item.name}"?`)) {
                            return Promise.resolve(false);
                        }

                        return fetch(`/projects/${projectId}/api/checklist/${item.id}/delete/`, {
                            method: 'DELETE',
                            headers: {
                                'X-CSRFToken': getCsrfToken()
                            }
                        })
                        .then(response => {
                            if (!response.ok) {
                                throw new Error('Failed to delete item');
                            }
                            return response.json();
                        })
                        .then(data => {
                            if (data.success) {
                                window.showToast('Item deleted successfully', 'success');
                                ArtifactsLoader.loadChecklist(projectId);
                                return true;
                            }
                            window.showToast(data.error || 'Failed to delete item', 'error');
                            return false;
                        })
                        .catch(error => {
                            console.error('Error deleting item:', error);
                            window.showToast('Error deleting item', 'error');
                            return false;
                        });
                    };

                    modalHelpers.setHandlers({
                        onEdit: (item) => {
                            modalHelpers.close();
                            if (item && typeof window.editChecklistItem === 'function') {
                                window.editChecklistItem(item.id);
                            }
                        },
                        onDelete: (item) => deleteChecklistItem(item).then(removed => {
                            if (removed) {
                                modalHelpers.close();
                            }
                            return removed;
                        }),
                        onExecute: (item) => {
                            if (item) {
                                modalHelpers.close();
                                ArtifactsLoader.executeTicket(item.id);
                            }
                        }
                    });

                    // Function to render checklist items based on filters
                    const renderChecklist = (filterStatus = 'all', filterRole = 'all') => {
                        let filteredChecklist = [...checklist];
                        
                        // Apply status filter
                        if (filterStatus !== 'all') {
                            filteredChecklist = filteredChecklist.filter(item => 
                                (item.status || 'open') === filterStatus
                            );
                        }
                        
                        // Apply role filter
                        if (filterRole !== 'all') {
                            filteredChecklist = filteredChecklist.filter(item => 
                                (item.role || 'user') === filterRole
                            );
                        }

                        if (filteredChecklist.length === 0) {
                            checklistContent.innerHTML = `
                                <div class="no-results">
                                    <div class="empty-state-icon">
                                        <i class="fas fa-filter"></i>
                                    </div>
                                    <div class="empty-state-text">
                                        No checklist items match your filter criteria.
                                    </div>
                                </div>
                            `;
                            return;
                        }

                        // Build checklist HTML with filtered items
                        let itemsHTML = '';
                        
                        filteredChecklist.forEach(item => {
                            const statusClass = item.status ? item.status.toLowerCase().replace(' ', '-') : 'open';
                            const priorityClass = item.priority ? item.priority.toLowerCase() : 'medium';
                            const roleClass = item.role ? item.role.toLowerCase() : 'user';
                            
                            // Get status icon
                            let statusIcon = 'fas fa-circle';
                            switch(statusClass) {
                                case 'open':
                                    statusIcon = 'fas fa-circle';
                                    break;
                                case 'in-progress':
                                    statusIcon = 'fas fa-play-circle';
                                    break;
                                case 'agent':
                                    statusIcon = 'fas fa-robot';
                                    break;
                                case 'closed':
                                    statusIcon = 'fas fa-check-circle';
                                    break;
                                case 'done':
                                    statusIcon = 'fas fa-check-circle';
                                    break;
                                case 'failed':
                                    statusIcon = 'fas fa-times-circle';
                                    break;
                                case 'blocked':
                                    statusIcon = 'fas fa-ban';
                                    break;
                            }
                            
                            // Check if this item matches active filters for highlighting
                            const isStatusHighlighted = filterStatus !== 'all' && (item.status || 'open') === filterStatus;
                            const isRoleHighlighted = filterRole !== 'all' && (item.role || 'user') === filterRole;
                            
                            // Extract dependencies if available
                            let dependenciesHtml = '';
                            if (item.dependencies && item.dependencies.length > 0) {
                                dependenciesHtml = `
                                    <div class="card-dependencies">
                                        <span class="dependencies-label"><i class="fas fa-link"></i> Dependencies:</span>
                                        ${item.dependencies.map(dep => `<span class="dependency-tag">${modalHelpers.escapeHtml(dep)}</span>`).join('')}
                                    </div>
                                `;
                            }
                            
                            // Extract details if available
                            let detailsPreview = '';
                            if (item.details && Object.keys(item.details).length > 0) {
                                // Show a preview of details
                                const detailKeys = Object.keys(item.details);
                                const previewKeys = detailKeys.slice(0, 2);
                                detailsPreview = `
                                    <div class="card-details-preview">
                                        ${previewKeys.map(key => {
                                            const value = item.details[key];
                                            const safeKey = modalHelpers.escapeHtml(key);
                                            if (Array.isArray(value) && value.length > 0) {
                                                return `<span class="detail-item"><i class="fas fa-info-circle"></i> ${safeKey}: ${value.length} items</span>`;
                                            } else if (typeof value === 'object' && value !== null) {
                                                return `<span class="detail-item"><i class="fas fa-info-circle"></i> ${safeKey}: ${Object.keys(value).length} properties</span>`;
                                            } else if (value) {
                                                return `<span class="detail-item"><i class="fas fa-info-circle"></i> ${safeKey}</span>`;
                                            }
                                            return '';
                                        }).filter(Boolean).join('')}
                                        ${detailKeys.length > 2 ? `<span class="more-details">+${detailKeys.length - 2} more...</span>` : ''}
                                    </div>
                                `;
                            }

                            let notesHtml = '';
                            if (item.notes) {
                                notesHtml = `
                                    <div class="card-notes" style="margin-top: 12px; font-size: 0.85rem; color: #cbd5f5;">
                                        <span class="notes-label" style="display: flex; align-items: center; gap: 6px; font-weight: 600; margin-bottom: 4px;"><i class="fas fa-sticky-note"></i> Notes</span>
                                        <div class="notes-text" style="background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.25); border-radius: 6px; padding: 8px; color: #e2e8f0;">${modalHelpers.escapeHtml(item.notes).replace(/\n/g, '<br>')}</div>
                                    </div>
                                `;
                            }
                            
                            itemsHTML += `
                                <div class="checklist-card ${statusClass}" data-id="${item.id}">
                                    <div class="card-header">
                                        <div class="card-status">
                                            <i class="${statusIcon} status-icon"></i>
                                            <h3 class="card-title">${modalHelpers.escapeHtml(item.name || 'Untitled Item')}</h3>
                                        </div>
                                        <div class="card-badges">
                                            <span class="priority-badge ${priorityClass} ${isStatusHighlighted ? 'filter-active' : ''}">${modalHelpers.escapeHtml(item.priority || 'Medium')}</span>
                                            <span class="role-badge ${roleClass} ${isRoleHighlighted ? 'filter-active' : ''}">${modalHelpers.escapeHtml(item.role || 'User')}</span>
                                        </div>
                                    </div>
                                    
                                    <div class="card-body">
                                        <div class="card-description">
                                            ${(() => {
                                                const summaryText = (item.description || '').trim();
                                                if (!summaryText) {
                                                    return 'No description provided.';
                                                }
                                                return modalHelpers.escapeHtml(summaryText).replace(/\n/g, '<br>');
                                        })()}
                                        </div>
                                        ${dependenciesHtml}
                                        ${detailsPreview}
                                        ${notesHtml}
                                    </div>
                                    
                                    <div class="card-footer">
                                        <div class="card-meta">
                                            <small class="created-date">
                                                <i class="fas fa-calendar-plus"></i>
                                                Created: ${new Date(item.created_at).toLocaleDateString()}
                                            </small>
                                            <small class="updated-date">
                                                <i class="fas fa-calendar-check"></i>
                                                Updated: ${new Date(item.updated_at).toLocaleDateString()}
                                            </small>
                                        </div>
                                        <div class="card-actions">
                                            <button class="action-btn view-details-btn" data-item-id="${item.id}" title="View Details">
                                                <i class="fas fa-eye"></i>
                                            </button>
                                            <button class="action-btn edit-btn" onclick="editChecklistItem(${item.id})" title="Edit">
                                                <i class="fas fa-edit"></i>
                                            </button>
                                            <button class="action-btn toggle-btn" onclick="toggleChecklistStatus(${item.id}, '${item.status}')" title="Toggle Status">
                                                <i class="fas fa-sync-alt"></i>
                                            </button>
                                            <button class="action-btn delete-checklist-btn" data-item-id="${item.id}" title="Delete">
                                                <i class="fas fa-trash"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            `;
                        });
                        
                        checklistContent.innerHTML = itemsHTML;

                        // Reattach event listeners after rendering
                        attachChecklistDetailListeners(filteredChecklist);

                        const deleteButtons = checklistContent.querySelectorAll('.delete-checklist-btn');
                        deleteButtons.forEach(button => {
                            button.addEventListener('click', function(e) {
                                e.stopPropagation();
                                const itemId = parseInt(this.getAttribute('data-item-id'), 10);
                                const item = checklist.find(i => i.id === itemId);
                                deleteChecklistItem(item);
                            });
                        });
                    };

                    // Function to attach event listeners for checklist detail view
                    const attachChecklistDetailListeners = (currentItems) => {
                        const checklistCards = checklistContent.querySelectorAll('.checklist-card');
                        const viewDetailsButtons = checklistContent.querySelectorAll('.view-details-btn');

                        checklistCards.forEach((card, index) => {
                            card.addEventListener('click', function(e) {
                                if (e.target.closest('.action-btn')) {
                                    return;
                                }

                                modalHelpers.open(currentItems, index);
                            });
                        });

                        viewDetailsButtons.forEach((button) => {
                            button.addEventListener('click', function(e) {
                                e.stopPropagation();
                                const card = this.closest('.checklist-card');
                                if (!card) {
                                    return;
                                }
                                const cardIndex = Array.from(checklistCards).indexOf(card);
                                if (cardIndex >= 0) {
                                    modalHelpers.open(currentItems, cardIndex);
                                }
                            });
                        });
                    };

                    // Function to update checklist item status
                    const updateChecklistItemStatus = (itemId, newStatus, oldStatus) => {
                        console.log(`[ArtifactsLoader] Updating checklist item ${itemId} status from ${oldStatus} to ${newStatus}`);
                        const projectId = getCurrentProjectId();
                        if (!projectId) {
                            console.warn('[ArtifactsLoader] No project ID available for status update');
                            showStatusUpdateError('Project ID not available');
                            return;
                        }
                        const dropdown = document.querySelector(`.status-dropdown[data-item-id="${itemId}"]`);
                        if (dropdown) {
                            dropdown.disabled = true;
                            dropdown.style.opacity = '0.6';
                        }
                        // Call backend API
                        fetch(`/projects/${projectId}/api/checklist/update/`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': getCsrfToken(),
                            },
                            body: JSON.stringify({ item_id: itemId, status: newStatus })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                if (dropdown) {
                                    dropdown.disabled = false;
                                    dropdown.style.opacity = '1';
                                    dropdown.setAttribute('data-current-status', newStatus);
                                }
                                // Update the item in the checklist array (if available)
                                const item = checklist.find(i => i.id == itemId);
                                if (item) {
                                    item.status = newStatus;
                                    item.updated_at = data.updated_at || new Date().toISOString();
                                }
                                // Update the visual state in the main list
                                const itemElement = document.querySelector(`[data-id="${itemId}"]`);
                                if (itemElement) {
                                    itemElement.classList.remove('open', 'in-progress', 'done', 'failed', 'blocked');
                                    itemElement.classList.add(newStatus.replace('_', '-'));
                                    const statusIcon = itemElement.querySelector('.status-icon');
                                    if (statusIcon) {
                                        let newIconClass = 'fas fa-circle';
                                        switch(newStatus) {
                                            case 'open': newIconClass = 'fas fa-circle'; break;
                                            case 'in_progress': newIconClass = 'fas fa-play-circle'; break;
                                            case 'done': newIconClass = 'fas fa-check-circle'; break;
                                            case 'failed': newIconClass = 'fas fa-times-circle'; break;
                                            case 'blocked': newIconClass = 'fas fa-ban'; break;
                                        }
                                        statusIcon.className = `${newIconClass} status-icon`;
                                    }
                                }
                                console.log(`[ArtifactsLoader] Status updated successfully to: ${newStatus}`);
                                showStatusUpdateSuccess(newStatus);
                            } else {
                                showStatusUpdateError(data.error || 'Failed to update status');
                                if (dropdown) {
                                    dropdown.disabled = false;
                                    dropdown.style.opacity = '1';
                                }
                            }
                        })
                        .catch(error => {
                            showStatusUpdateError(error.message || 'Failed to update status');
                            if (dropdown) {
                                dropdown.disabled = false;
                                dropdown.style.opacity = '1';
                            }
                        });
                    };

                    // Function to update checklist item role/assignment
                    const updateChecklistItemRole = (itemId, newRole, oldRole) => {
                        console.log(`[ArtifactsLoader] Updating checklist item ${itemId} role from ${oldRole} to ${newRole}`);
                        const projectId = getCurrentProjectId();
                        if (!projectId) {
                            console.warn('[ArtifactsLoader] No project ID available for role update');
                            showRoleUpdateError('Project ID not available');
                            return;
                        }
                        const dropdown = document.querySelector(`.role-dropdown[data-item-id="${itemId}"]`);
                        if (dropdown) {
                            dropdown.disabled = true;
                            dropdown.style.opacity = '0.6';
                        }
                        // Call backend API
                        fetch(`/projects/${projectId}/api/checklist/update/`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': getCsrfToken(),
                            },
                            body: JSON.stringify({ item_id: itemId, role: newRole })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                if (dropdown) {
                                    dropdown.disabled = false;
                                    dropdown.style.opacity = '1';
                                    dropdown.setAttribute('data-current-role', newRole);
                                }
                                // Update the item in the checklist array (if available)
                                const item = checklist.find(i => i.id == itemId);
                                if (item) {
                                    item.role = newRole;
                                    item.updated_at = data.updated_at || new Date().toISOString();
                                }
                                // Update the visual state in the main list
                                const itemElement = document.querySelector(`[data-id="${itemId}"]`);
                                if (itemElement) {
                                    itemElement.classList.remove('user', 'agent');
                                    itemElement.classList.add(newRole);
                                    const roleBadge = itemElement.querySelector('.role-badge');
                                    if (roleBadge) {
                                        roleBadge.className = `role-badge ${newRole}`;
                                        roleBadge.textContent = newRole.charAt(0).toUpperCase() + newRole.slice(1);
                                    }
                                }
                                console.log(`[ArtifactsLoader] Role updated successfully to: ${newRole}`);
                                showRoleUpdateSuccess(newRole);
                            } else {
                                showRoleUpdateError(data.error || 'Failed to update role');
                                if (dropdown) {
                                    dropdown.disabled = false;
                                    dropdown.style.opacity = '1';
                                }
                            }
                        })
                        .catch(error => {
                            showRoleUpdateError(error.message || 'Failed to update role');
                            if (dropdown) {
                                dropdown.disabled = false;
                                dropdown.style.opacity = '1';
                            }
                        });
                    };

                    // Function to show status update success message
                    const showStatusUpdateSuccess = (newStatus) => {
                        const statusUpdateMessage = document.getElementById('status-update-message');
                        if (statusUpdateMessage) {
                            statusUpdateMessage.textContent = `Status updated to: ${newStatus}`;
                            statusUpdateMessage.style.display = 'block';
                            setTimeout(() => {
                                statusUpdateMessage.style.display = 'none';
                            }, 3000);
                        }
                    };

                    // Function to show role update success message
                    const showRoleUpdateSuccess = (newRole) => {
                        const roleUpdateMessage = document.getElementById('role-update-message');
                        if (roleUpdateMessage) {
                            roleUpdateMessage.textContent = `Role updated to: ${newRole}`;
                            roleUpdateMessage.style.display = 'block';
                            setTimeout(() => {
                                roleUpdateMessage.style.display = 'none';
                            }, 3000);
                        }
                    };

                    // Function to show status update error message
                    const showStatusUpdateError = (errorMessage) => {
                        const statusUpdateError = document.getElementById('status-update-error');
                        if (statusUpdateError) {
                            statusUpdateError.textContent = `Error updating status: ${errorMessage}`;
                            statusUpdateError.style.display = 'block';
                            setTimeout(() => {
                                statusUpdateError.style.display = 'none';
                            }, 5000);
                        }
                    };

                    // Function to show role update error message
                    const showRoleUpdateError = (errorMessage) => {
                        const roleUpdateError = document.getElementById('role-update-error');
                        if (roleUpdateError) {
                            roleUpdateError.textContent = `Error updating role: ${errorMessage}`;
                            roleUpdateError.style.display = 'block';
                            setTimeout(() => {
                                roleUpdateError.style.display = 'none';
                            }, 5000);
                        }
                    };

                    // Attach event listeners for filters
                    statusFilter.addEventListener('change', function() {
                        const filterStatus = this.value;
                        const filterRole = roleFilter.value;
                        renderChecklist(filterStatus, filterRole);
                    });
                    
                    roleFilter.addEventListener('change', function() {
                        const filterStatus = statusFilter.value;
                        const filterRole = this.value;
                        renderChecklist(filterStatus, filterRole);
                    });
                    
                    clearFiltersBtn.addEventListener('click', function() {
                        statusFilter.value = 'all';
                        roleFilter.value = 'all';
                        renderChecklist();
                    });
                    
                    // Add delete all button event listener
                    const deleteAllBtn = document.getElementById('delete-all-checklist');
                    if (deleteAllBtn) {
                        deleteAllBtn.addEventListener('click', function() {
                            if (checklist.length === 0) {
                                showToast('No items to delete', 'info');
                                return;
                            }
                            
                            if (confirm(`Are you sure you want to delete ALL ${checklist.length} checklist items? This action cannot be undone.`)) {
                                // Show loading state
                                this.disabled = true;
                                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';
                                
                                // Delete all items
                                const deletePromises = checklist.map(item => 
                                    fetch(`/projects/${projectId}/api/checklist/${item.id}/delete/`, {
                                        method: 'DELETE',
                                        headers: {
                                            'X-CSRFToken': getCsrfToken()
                                        }
                                    })
                                );
                                
                                Promise.all(deletePromises)
                                    .then(responses => {
                                        const failedDeletions = responses.filter(r => !r.ok).length;
                                        if (failedDeletions === 0) {
                                            showToast('All checklist items deleted successfully', 'success');
                                        } else {
                                            showToast(`Deleted ${checklist.length - failedDeletions} items. ${failedDeletions} failed.`, 'warning');
                                        }
                                        // Reload the checklist
                                        ArtifactsLoader.loadChecklist(projectId);
                                    })
                                    .catch(error => {
                                        console.error('Error deleting items:', error);
                                        showToast('Error deleting items', 'error');
                                        // Re-enable button
                                        this.disabled = false;
                                        this.innerHTML = '<i class="fas fa-trash-alt"></i> Delete All';
                                    });
                            }
                        });
                    }

                    // Add Linear sync button event listener for checklist
                    const syncChecklistLinearBtn = document.getElementById('sync-checklist-linear');
                    if (syncChecklistLinearBtn) {
                        syncChecklistLinearBtn.addEventListener('click', async function() {
                            try {
                                // First check if Linear API key is configured
                                const configResponse = await fetch(`/projects/${projectId}/api/linear/teams/`);
                                const configData = await configResponse.json();
                                
                                if (!configData.success) {
                                    window.showToast(configData.error || 'Linear API key not configured. Please go to Integrations to add your Linear API key.', 'error');
                                    return;
                                }
                                
                                // Show project selection popup
                                window.showLinearProjectSelectionPopup(projectId, configData.teams);
                            } catch (error) {
                                console.error('Error checking Linear configuration:', error);
                                window.showToast('Error connecting to Linear. Please check your configuration.', 'error');
                            }
                        });
                    }
                    
                    // Add dropdown toggle functionality
                    const dropdownToggle = document.getElementById('checklist-actions-dropdown');
                    const dropdownMenu = document.getElementById('checklist-actions-menu');
                    
                    if (dropdownToggle && dropdownMenu) {
                        // Toggle dropdown on button click
                        dropdownToggle.addEventListener('click', function(e) {
                            e.stopPropagation();
                            const isVisible = dropdownMenu.style.display === 'block';
                            dropdownMenu.style.display = isVisible ? 'none' : 'block';
                        });
                        
                        // Close dropdown when clicking outside
                        document.addEventListener('click', function(e) {
                            if (!dropdownToggle.contains(e.target) && !dropdownMenu.contains(e.target)) {
                                dropdownMenu.style.display = 'none';
                            }
                        });
                        
                        // Prevent dropdown from closing when clicking inside the menu
                        dropdownMenu.addEventListener('click', function(e) {
                            e.stopPropagation();
                        });
                    }
                    
                    // Helper function to show toast notifications
                    function showToast(message, type = 'info') {
                        // Create toast element if it doesn't exist
                        let toastContainer = document.getElementById('toast-container');
                        if (!toastContainer) {
                            toastContainer = document.createElement('div');
                            toastContainer.id = 'toast-container';
                            toastContainer.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999;';
                            document.body.appendChild(toastContainer);
                        }
                        
                        const toast = document.createElement('div');
                        toast.className = `toast toast-${type}`;
                        toast.style.cssText = 'background: #333; color: white; padding: 12px 24px; border-radius: 4px; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); animation: slideIn 0.3s ease;';
                        
                        if (type === 'success') {
                            toast.style.background = '#4CAF50';
                        } else if (type === 'error') {
                            toast.style.background = '#f44336';
                        }
                        
                        toast.textContent = message;
                        toastContainer.appendChild(toast);
                        
                        // Remove toast after 5 seconds
                        setTimeout(() => {
                            toast.style.animation = 'slideOut 0.3s ease';
                            setTimeout(() => toast.remove(), 300);
                        }, 5000);
                    }
                    
                    // Helper function to get CSRF token
                    function getCookie(name) {
                        let cookieValue = null;
                        if (document.cookie && document.cookie !== '') {
                            const cookies = document.cookie.split(';');
                            for (let i = 0; i < cookies.length; i++) {
                                const cookie = cookies[i].trim();
                                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                                    break;
                                }
                            }
                        }
                        return cookieValue;
                    }
                    
                    // Function to show Linear project selection popup
                    async function showLinearProjectSelectionPopup(projectId, teams) {
                        // Create popup overlay
                        const overlay = document.createElement('div');
                        overlay.className = 'linear-popup-overlay';
                        overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center;';
                        
                        // Create popup container
                        const popup = document.createElement('div');
                        popup.className = 'linear-popup';
                        popup.style.cssText = 'background: #2a2a2a; padding: 30px; border-radius: 8px; max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.5);';
                        
                        // Check if we have teams
                        if (!teams || teams.length === 0) {
                            popup.innerHTML = `
                                <h3 style="color: #fff; margin-bottom: 20px;">No Linear Teams Found</h3>
                                <p style="color: #ccc; margin-bottom: 20px;">Please make sure your Linear API key has access to at least one team.</p>
                                <button class="close-popup-btn" style="background: #666; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Close</button>
                            `;
                            overlay.appendChild(popup);
                            document.body.appendChild(overlay);
                            
                            popup.querySelector('.close-popup-btn').addEventListener('click', () => {
                                overlay.remove();
                            });
                            return;
                        }
                        
                        // Get current project info
                        const projectResponse = await fetch(`/projects/${projectId}/`);
                        const projectData = await projectResponse.json();
                        const currentLinearProjectId = projectData.linear_project_id;
                        
                        let popupHTML = `
                            <h3 style="color: #fff; margin-bottom: 20px;">Sync with Linear Team</h3>
                            <div class="linear-teams-container">
                        `;
                        
                        // Add team selection if multiple teams
                        if (teams.length > 1) {
                            popupHTML += `
                                <div style="margin-bottom: 20px;">
                                    <label style="color: #ccc; display: block; margin-bottom: 8px;">Select Team:</label>
                                    <select id="linear-team-select" style="width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; color: #fff; border-radius: 4px;">
                                        ${teams.map(team => `<option value="${team.id}">${team.name}</option>`).join('')}
                                    </select>
                                </div>
                            `;
                        }
                        
                        popupHTML += `
                            <div style="margin-bottom: 20px;">
                                <label style="color: #ccc; display: block; margin-bottom: 8px;">Select Project:</label>
                                <div id="linear-projects-loading" style="color: #888; text-align: center; padding: 20px;">
                                    <i class="fas fa-spinner fa-spin"></i> Loading projects...
                                </div>
                                <select id="linear-project-select" style="width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; color: #fff; border-radius: 4px; display: none;">
                                    <option value="">Select a project...</option>
                                </select>
                            </div>
                            
                            <div style="margin-bottom: 20px;">
                                <button id="create-new-project-btn" style="background: #5856d6; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin-right: 10px;">
                                    <i class="fas fa-plus"></i> Create New Project
                                </button>
                            </div>
                            
                            <div id="new-project-form" style="display: none; margin-bottom: 20px; padding: 20px; background: #1a1a1a; border-radius: 4px;">
                                <h4 style="color: #fff; margin-bottom: 15px;">Create New Linear Project</h4>
                                <input type="text" id="new-project-name" placeholder="Project Name" style="width: 100%; padding: 8px; background: #2a2a2a; border: 1px solid #444; color: #fff; border-radius: 4px; margin-bottom: 10px;">
                                <textarea id="new-project-description" placeholder="Project Description (optional)" style="width: 100%; padding: 8px; background: #2a2a2a; border: 1px solid #444; color: #fff; border-radius: 4px; min-height: 80px; margin-bottom: 10px;"></textarea>
                                <button id="confirm-create-project" style="background: #4CAF50; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-right: 10px;">Create</button>
                                <button id="cancel-create-project" style="background: #666; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">Cancel</button>
                            </div>
                            
                            <div style="display: flex; justify-content: flex-end; gap: 10px;">
                                <button class="cancel-popup-btn" style="background: #666; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Cancel</button>
                                <button class="confirm-popup-btn" style="background: #5856d6; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Sync with Selected Team</button>
                            </div>
                        </div>
                        `;
                        
                        popup.innerHTML = popupHTML;
                        overlay.appendChild(popup);
                        document.body.appendChild(overlay);
                        
                        // Elements
                        const teamSelect = popup.querySelector('#linear-team-select');
                        const projectSelect = popup.querySelector('#linear-project-select');
                        const projectsLoading = popup.querySelector('#linear-projects-loading');
                        const createNewBtn = popup.querySelector('#create-new-project-btn');
                        const newProjectForm = popup.querySelector('#new-project-form');
                        const confirmBtn = popup.querySelector('.confirm-popup-btn');
                        const cancelBtn = popup.querySelector('.cancel-popup-btn');
                        
                        // Load projects for the selected team
                        async function loadProjects(teamId) {
                            projectsLoading.style.display = 'block';
                            projectSelect.style.display = 'none';
                            
                            const response = await fetch(`/projects/${projectId}/api/linear/projects/?team_id=${teamId}`);
                            const data = await response.json();
                            
                            if (data.success && data.projects) {
                                projectSelect.innerHTML = '<option value="">Select a project...</option>';
                                data.projects.forEach(project => {
                                    const selected = project.id === currentLinearProjectId ? 'selected' : '';
                                    projectSelect.innerHTML += `<option value="${project.id}" ${selected}>${project.name}</option>`;
                                });
                                projectsLoading.style.display = 'none';
                                projectSelect.style.display = 'block';
                                
                                // Enable confirm button if a project is already selected
                                if (currentLinearProjectId && projectSelect.value) {
                                    confirmBtn.disabled = false;
                                }
                            }
                        }
                        
                        // Initial load
                        const initialTeamId = teams.length === 1 ? teams[0].id : teamSelect.value;
                        loadProjects(initialTeamId);
                        
                        // Team change handler
                        if (teamSelect) {
                            teamSelect.addEventListener('change', (e) => {
                                loadProjects(e.target.value);
                            });
                        }
                        
                        // Project selection handler
                        projectSelect.addEventListener('change', (e) => {
                            confirmBtn.disabled = !e.target.value;
                        });
                        
                        // Create new project handlers
                        createNewBtn.addEventListener('click', () => {
                            newProjectForm.style.display = 'block';
                            createNewBtn.style.display = 'none';
                        });
                        
                        popup.querySelector('#cancel-create-project').addEventListener('click', () => {
                            newProjectForm.style.display = 'none';
                            createNewBtn.style.display = 'block';
                        });
                        
                        popup.querySelector('#confirm-create-project').addEventListener('click', async () => {
                            const projectName = popup.querySelector('#new-project-name').value;
                            const projectDescription = popup.querySelector('#new-project-description').value;
                            
                            if (!projectName) {
                                showToast('Please enter a project name', 'error');
                                return;
                            }
                            
                            const currentTeamId = teams.length === 1 ? teams[0].id : teamSelect.value;
                            
                            // Create the project via API
                            showToast('Creating new Linear project...', 'info');
                            
                            try {
                                const createResponse = await fetch(`/projects/${projectId}/api/linear/create-project/`, {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'X-CSRFToken': getCookie('csrftoken')
                                    },
                                    body: JSON.stringify({
                                        team_id: currentTeamId,
                                        name: projectName,
                                        description: projectDescription
                                    })
                                });
                                
                                const createData = await createResponse.json();
                                
                                if (createData.success) {
                                    showToast('Linear project created successfully!', 'success');
                                    
                                    // Hide the form
                                    newProjectForm.style.display = 'none';
                                    createNewBtn.style.display = 'block';
                                    
                                    // Clear form fields
                                    popup.querySelector('#new-project-name').value = '';
                                    popup.querySelector('#new-project-description').value = '';
                                    
                                    // Reload projects and select the new one
                                    await loadProjects(currentTeamId);
                                    
                                    // Select the newly created project
                                    if (createData.project && createData.project.id) {
                                        projectSelect.value = createData.project.id;
                                        confirmBtn.disabled = false;
                                    }
                                } else {
                                    showToast(createData.error || 'Failed to create Linear project', 'error');
                                }
                            } catch (error) {
                                console.error('Error creating Linear project:', error);
                                showToast('Error creating Linear project', 'error');
                            }
                        });
                        
                        // Cancel handler
                        cancelBtn.addEventListener('click', () => {
                            overlay.remove();
                        });
                        
                        // Confirm handler
                        confirmBtn.addEventListener('click', async () => {
                            const selectedTeamId = teams.length === 1 ? teams[0].id : teamSelect.value;
                            
                            if (!selectedTeamId) {
                                showToast('Please select a team', 'error');
                                return;
                            }
                            
                            // Save the selected team to the backend
                            const saveResponse = await fetch(`/projects/${projectId}/update/`, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/x-www-form-urlencoded',
                                    'X-CSRFToken': getCookie('csrftoken')
                                },
                                body: new URLSearchParams({
                                    'name': projectData.name || '',
                                    'description': projectData.description || '',
                                    'linear_sync_enabled': 'on',
                                    'linear_team_id': selectedTeamId,
                                    'linear_project_id': ''
                                })
                            });
                            
                            if (saveResponse.ok) {
                                // Close popup
                                overlay.remove();
                                
                                // Show progress overlay
                                const progressOverlay = document.createElement('div');
                                progressOverlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; z-index: 10000;';
                                
                                const progressContainer = document.createElement('div');
                                progressContainer.style.cssText = 'background: #2a2a2a; padding: 30px; border-radius: 8px; min-width: 400px; text-align: center;';
                                
                                progressContainer.innerHTML = `
                                    <h3 style="color: #fff; margin-bottom: 20px;">Syncing with Linear</h3>
                                    <div style="margin-bottom: 15px;">
                                        <div style="background: #444; height: 20px; border-radius: 10px; overflow: hidden;">
                                            <div id="sync-progress-bar-2" style="background: #5856d6; height: 100%; width: 0%; transition: width 0.3s ease;"></div>
                                        </div>
                                    </div>
                                    <p id="sync-progress-text-2" style="color: #ccc; margin: 0;">Initializing sync...</p>
                                `;
                                
                                progressOverlay.appendChild(progressContainer);
                                document.body.appendChild(progressOverlay);
                                
                                // Simulate progress while waiting for response
                                const progressBar = document.getElementById('sync-progress-bar-2');
                                const progressText = document.getElementById('sync-progress-text-2');
                                
                                progressBar.style.width = '20%';
                                progressText.textContent = 'Connecting to Linear...';
                                
                                try {
                                    const syncResponse = await fetch(`/projects/${projectId}/api/linear/sync/`, {
                                        method: 'POST',
                                        headers: {
                                            'Content-Type': 'application/json',
                                            'X-CSRFToken': getCookie('csrftoken')
                                        },
                                    });
                                    
                                    progressBar.style.width = '60%';
                                    progressText.textContent = 'Processing items...';
                                    
                                    const syncData = await syncResponse.json();
                                    
                                    progressBar.style.width = '100%';
                                    
                                    if (syncData.success) {
                                        progressText.textContent = `Synced ${syncData.results?.created || 0} items successfully!`;
                                        
                                        // Show completion for a moment
                                        setTimeout(() => {
                                            progressOverlay.remove();
                                            showToast(syncData.message || 'Tasks synced successfully!', 'success');
                                            ArtifactsLoader.loadChecklist(projectId);
                                        }, 1500);
                                    } else {
                                        progressText.textContent = 'Sync failed!';
                                        progressBar.style.background = '#f44336';
                                        
                                        setTimeout(() => {
                                            progressOverlay.remove();
                                            showToast(syncData.error || 'Failed to sync tasks', 'error');
                                        }, 1500);
                                    }
                                } catch (error) {
                                    progressBar.style.width = '100%';
                                    progressBar.style.background = '#f44336';
                                    progressText.textContent = 'Network error!';
                                    
                                    setTimeout(() => {
                                        progressOverlay.remove();
                                        showToast('Network error during sync', 'error');
                                    }, 1500);
                                }
                            } else {
                                showToast('Failed to save Linear team selection', 'error');
                            }
                        });
                        
                        // Close on overlay click
                        overlay.addEventListener('click', (e) => {
                            if (e.target === overlay) {
                                overlay.remove();
                            }
                        });
                    }

                    // Initial render
                    renderChecklist();
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error fetching checklist:', error);
                    checklistTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading checklist. Please try again.
                            </div>
                        </div>
                    `;
                });
        },

        /**
         * Load app preview from ServerConfig for the current project
         * @param {number} projectId - The ID of the current project
         * @param {number} conversationId - Optional conversation ID (not used for ServerConfig)
         */
        loadAppPreview: function(projectId, conversationId) {
            console.log(`[ArtifactsLoader] loadAppPreview called with project ID: ${projectId}, conversation ID: ${conversationId}`);

            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading app preview');
                return;
            }

            // Get app tab elements
            const appTab = document.getElementById('apps');
            const appLoading = document.getElementById('app-loading');
            const appEmpty = document.getElementById('app-empty');
            const appFrameContainer = document.getElementById('app-frame-container');
            const appIframe = document.getElementById('app-iframe');
            
            if (!appTab || !appLoading || !appEmpty || !appFrameContainer || !appIframe) {
                console.warn('[ArtifactsLoader] One or more app tab elements not found');
                return;
            }
            
            // Show loading state
            appEmpty.style.display = 'none';
            appFrameContainer.style.display = 'none';
            appLoading.style.display = 'block';
            
            // Fetch server configs from API
            const serverConfigsUrl = `/projects/${projectId}/api/server-configs/`;
            console.log(`[ArtifactsLoader] Fetching server configs from API: ${serverConfigsUrl}`);
            
            fetch(serverConfigsUrl)
                .then(response => {
                    console.log(`[ArtifactsLoader] Server configs API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Server configs API data received:', data);
                    
                    // Process server configs
                    const serverConfigs = data.server_configs || [];
                    console.log(`[ArtifactsLoader] Found ${serverConfigs.length} server configurations`);
                    
                    if (serverConfigs.length === 0) {
                        // Show empty state if no server configs found
                        console.log('[ArtifactsLoader] No server configs found, showing empty state');
                        showEmptyState("No application servers found. Start a server using the chat interface by running commands like 'npm start' or 'python manage.py runserver'.");
                        return;
                    }
                    
                    // Find the first application server or use the first config
                    let selectedConfig = serverConfigs.find(config => config.type === 'application') || serverConfigs[0];
                    console.log(`[ArtifactsLoader] Selected server config:`, selectedConfig);
                    
                    // If there are multiple configs, you could potentially show a selector here
                    if (serverConfigs.length > 1) {
                        console.log(`[ArtifactsLoader] Multiple server configs available, using: ${selectedConfig.type} on port ${selectedConfig.port}`);
                    }
                    
                    // Construct the URL for the iframe using localhost and the configured port
                    const appUrl = `http://localhost:${selectedConfig.port}/`;
                    console.log(`[ArtifactsLoader] Loading app from URL: ${appUrl}`);
                    
                    // First, check if the server is actually running by testing the URL
                    console.log(`[ArtifactsLoader] Testing server connectivity at: ${appUrl}`);
                    
                    // Test server connectivity before loading iframe
                    fetch(appUrl, {
                        method: 'GET',
                        mode: 'no-cors', // Avoid CORS issues for connectivity test
                        cache: 'no-cache'
                    })
                    .then(() => {
                        console.log(`[ArtifactsLoader] Server connectivity test passed for ${appUrl}`);
                        loadIframeApp(appUrl, selectedConfig);
                    })
                    .catch((error) => {
                        console.error(`[ArtifactsLoader] Server connectivity test failed for ${appUrl}:`, error);
                        showServerNotRunningError(selectedConfig.port);
                    });
                    
                    // Function to load the app in iframe after connectivity is confirmed
                    function loadIframeApp(iframeUrl, config) {
                        console.log(`[ArtifactsLoader] Loading verified server in iframe: ${iframeUrl}`);
                        
                        // Use setTimeout to ensure DOM is ready
                        setTimeout(() => {
                            // Show URL panel and update URL
                            const urlPanel = document.getElementById('app-url-panel');
                            const urlInput = document.getElementById('app-url-input');
                            const refreshBtn = document.getElementById('app-refresh-btn');
                            const restartServerBtn = document.getElementById('app-restart-server-btn');
                            
                            if (urlPanel && urlInput) {
                                console.log('[ArtifactsLoader] Setting URL in panel to:', iframeUrl);
                                urlPanel.style.display = 'block';
                                urlInput.value = iframeUrl;
                            
                            // Handle URL input
                            urlInput.onkeypress = function(e) {
                                if (e.key === 'Enter') {
                                    const newUrl = this.value.trim();
                                    if (newUrl) {
                                        console.log('[ArtifactsLoader] Navigating to:', newUrl);
                                        appIframe.src = newUrl;
                                    }
                                }
                            };
                            
                            // Select all on focus
                            urlInput.onfocus = function() {
                                this.select();
                            };
                        } else {
                            console.error('[ArtifactsLoader] URL panel elements not found', {urlPanel, urlInput});
                        }
                        
                        // Set up refresh button
                        if (refreshBtn) {
                            refreshBtn.onclick = function() {
                                console.log('[ArtifactsLoader] Refreshing iframe');
                                // Force reload by clearing and resetting src
                                const currentSrc = appIframe.src;
                                appIframe.src = '';
                                setTimeout(() => {
                                    appIframe.src = currentSrc;
                                }, 100);
                            };
                            
                            // Add hover effect
                            refreshBtn.onmouseover = function() {
                                this.style.background = '#5a6578';
                            };
                            refreshBtn.onmouseout = function() {
                                this.style.background = '#4a5568';
                            };
                        }
                        
                        // Set up restart server button
                        if (restartServerBtn) {
                            restartServerBtn.onclick = function() {
                                console.log('[ArtifactsLoader] Restarting server');
                                // Disable button and show loading state
                                this.disabled = true;
                                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Restarting...';
                                window.ArtifactsLoader.checkAndRestartServers(projectId);
                            };
                            
                            // Add hover effect
                            restartServerBtn.onmouseover = function() {
                                if (!this.disabled) {
                                    this.style.background = '#7c3aed';
                                }
                            };
                            restartServerBtn.onmouseout = function() {
                                if (!this.disabled) {
                                    this.style.background = '#8b5cf6';
                                }
                            };
                        }
                        }, 100); // Small delay to ensure DOM is ready
                        
                        // Set up iframe load tracking
                        let hasLoaded = false;
                        let timeoutId = null;
                        
                        // Set up iframe event handlers
                        appIframe.onload = function() {
                            console.log('[ArtifactsLoader] Iframe onload event triggered');
                            hasLoaded = true;
                            clearTimeout(timeoutId);
                            
                            appLoading.style.display = 'none';
                            appFrameContainer.style.display = 'flex';
                            console.log('[ArtifactsLoader] App iframe loaded successfully');
                        };
                        
                        appIframe.onerror = function(e) {
                            console.error('[ArtifactsLoader] Error loading app iframe:', e);
                            hasLoaded = true;
                            clearTimeout(timeoutId);
                            showErrorState(`Failed to load application from port ${config.port}. The server may have stopped or encountered an error.`);
                        };
                        
                        // Set up timeout as fallback
                        timeoutId = setTimeout(() => {
                            if (!hasLoaded) {
                                console.warn('[ArtifactsLoader] App iframe taking too long to load');
                                showErrorState(`Application is taking too long to load from port ${config.port}. The server may be slow to respond.`);
                            }
                        }, 10000); // 10 second timeout for verified servers
                        
                        // Set the iframe source to load the app
                        appIframe.src = iframeUrl;
                        
                        // Adjust the container to fill available space
                        appTab.style.overflow = 'hidden';
                        
                        // Set up console functionality
                        setupConsole();
                    }
                    
                    // Function to set up console functionality
                    function setupConsole() {
                        const consolePanel = document.getElementById('console-panel');
                        const consoleOutput = document.getElementById('console-output');
                        const showConsoleBtn = document.getElementById('show-console-btn');
                        const toggleConsoleBtn = document.getElementById('toggle-console-btn');
                        const clearConsoleBtn = document.getElementById('clear-console-btn');
                        const pipeConsoleBtn = document.getElementById('pipe-console-btn');
                        
                        if (!consolePanel || !consoleOutput || !showConsoleBtn) {
                            console.warn('[ArtifactsLoader] Console elements not found');
                            return;
                        }
                        
                        // Show the console button
                        showConsoleBtn.style.display = 'block';
                        
                        // Console visibility state
                        let isConsoleVisible = false;
                        
                        // Store all console logs
                        const consoleLogs = [];
                        
                        // Function to toggle console visibility
                        function toggleConsole() {
                            isConsoleVisible = !isConsoleVisible;
                            if (isConsoleVisible) {
                                consolePanel.style.display = 'flex';
                                showConsoleBtn.style.display = 'none';
                                // Adjust iframe container height
                                const iframeContainer = appIframe.parentElement;
                                if (iframeContainer) {
                                    iframeContainer.style.height = 'calc(100% - 200px)';
                                }
                            } else {
                                consolePanel.style.display = 'none';
                                showConsoleBtn.style.display = 'block';
                                // Restore iframe container height
                                const iframeContainer = appIframe.parentElement;
                                if (iframeContainer) {
                                    iframeContainer.style.height = '100%';
                                }
                            }
                        }
                        
                        // Set up event handlers
                        showConsoleBtn.onclick = toggleConsole;
                        if (toggleConsoleBtn) {
                            toggleConsoleBtn.onclick = toggleConsole;
                        }
                        
                        if (clearConsoleBtn) {
                            clearConsoleBtn.onclick = function() {
                                consoleOutput.innerHTML = '';
                                consoleLogs.length = 0; // Clear the logs array
                            };
                        }
                        
                        if (pipeConsoleBtn) {
                            // Add hover effect
                            pipeConsoleBtn.onmouseover = function() {
                                this.style.color = '#8b5cf6';
                            };
                            pipeConsoleBtn.onmouseout = function() {
                                this.style.color = '#999';
                            };
                            
                            pipeConsoleBtn.onclick = function() {
                                if (consoleLogs.length === 0) {
                                    alert('No console logs to send');
                                    return;
                                }
                                
                                // Format logs for chat
                                let formattedLogs = "```console\n";
                                consoleLogs.forEach(log => {
                                    const typeIcon = {
                                        'error': '❌',
                                        'warn': '⚠️',
                                        'info': 'ℹ️',
                                        'log': '📝'
                                    }[log.type] || '';
                                    
                                    formattedLogs += `${typeIcon} [${log.type.toUpperCase()}] ${log.message}\n`;
                                });
                                formattedLogs += "```";
                                
                                // Get the chat input element
                                const chatInput = document.getElementById('chat-input');
                                if (chatInput) {
                                    // Set the formatted logs as the input value
                                    chatInput.value = `Here are the console logs from the preview:\n\n${formattedLogs}`;
                                    
                                    // Focus the input
                                    chatInput.focus();
                                    
                                    // Optionally scroll to the chat input
                                    chatInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                    
                                    // Add a visual feedback
                                    this.innerHTML = '<i class="fas fa-check"></i> Sent!';
                                    setTimeout(() => {
                                        this.innerHTML = '<i class="fas fa-paper-plane"></i> Send to Chat';
                                    }, 2000);
                                } else {
                                    alert('Could not find chat input');
                                }
                            };
                        }
                        
                        // Function to add log to console
                        function addLog(type, ...args) {
                            const logEntry = document.createElement('div');
                            logEntry.style.marginBottom = '4px';
                            logEntry.style.fontFamily = 'monospace';
                            logEntry.style.fontSize = '12px';
                            
                            // Format the log message
                            const message = args.map(arg => {
                                if (typeof arg === 'object') {
                                    try {
                                        return JSON.stringify(arg, null, 2);
                                    } catch (e) {
                                        return String(arg);
                                    }
                                }
                                return String(arg);
                            }).join(' ');
                            
                            // Store the log
                            consoleLogs.push({
                                type: type,
                                message: message,
                                timestamp: new Date().toISOString()
                            });
                            
                            // Style based on type
                            switch(type) {
                                case 'error':
                                    logEntry.style.color = '#ff6b6b';
                                    logEntry.innerHTML = `<span style="color: #ff4444;">✖</span> ${escapeHtml(message)}`;
                                    break;
                                case 'warn':
                                    logEntry.style.color = '#ffd93d';
                                    logEntry.innerHTML = `<span style="color: #ffaa00;">⚠</span> ${escapeHtml(message)}`;
                                    break;
                                case 'info':
                                    logEntry.style.color = '#6bcfff';
                                    logEntry.innerHTML = `<span style="color: #4444ff;">ℹ</span> ${escapeHtml(message)}`;
                                    break;
                                default:
                                    logEntry.style.color = '#e2e8f0';
                                    logEntry.textContent = message;
                            }
                            
                            consoleOutput.appendChild(logEntry);
                            consoleOutput.scrollTop = consoleOutput.scrollHeight;
                        }
                        
                        // Helper function to escape HTML
                        function escapeHtml(text) {
                            const div = document.createElement('div');
                            div.textContent = text;
                            return div.innerHTML;
                        }
                        
                        // Try to intercept console logs from the iframe
                        try {
                            // Store original console methods
                            const originalLog = appIframe.contentWindow.console.log;
                            const originalError = appIframe.contentWindow.console.error;
                            const originalWarn = appIframe.contentWindow.console.warn;
                            const originalInfo = appIframe.contentWindow.console.info;
                            
                            // Override console methods in iframe
                            appIframe.contentWindow.console.log = function(...args) {
                                addLog('log', ...args);
                                originalLog.apply(this, args);
                            };
                            
                            appIframe.contentWindow.console.error = function(...args) {
                                addLog('error', ...args);
                                originalError.apply(this, args);
                            };
                            
                            appIframe.contentWindow.console.warn = function(...args) {
                                addLog('warn', ...args);
                                originalWarn.apply(this, args);
                            };
                            
                            appIframe.contentWindow.console.info = function(...args) {
                                addLog('info', ...args);
                                originalInfo.apply(this, args);
                            };
                            
                            // Listen for errors in iframe
                            appIframe.contentWindow.addEventListener('error', function(event) {
                                addLog('error', `${event.message} at ${event.filename}:${event.lineno}:${event.colno}`);
                            });
                            
                        } catch (e) {
                            console.warn('[ArtifactsLoader] Cannot intercept iframe console due to cross-origin restrictions');
                            addLog('warn', 'Console interception not available due to cross-origin restrictions');
                        }
                    }
                    
                    // Function to show server not running error
                    function showServerNotRunningError(port) {
                        appLoading.style.display = 'none';
                        appEmpty.style.display = 'block';
                        
                        // Hide URL panel when showing error
                        const urlPanel = document.getElementById('app-url-panel');
                        if (urlPanel) {
                            urlPanel.style.display = 'none';
                        }
                        
                        // Hide console button
                        const showConsoleBtn = document.getElementById('show-console-btn');
                        if (showConsoleBtn) {
                            showConsoleBtn.style.display = 'none';
                        }
                        
                        appEmpty.innerHTML = `
                            <div class="error-state" style="display: flex; flex-direction: column; align-items: center; padding: 2rem;">
                                <div class="error-state-icon">
                                    <i class="fas fa-server" style="font-size: 3rem; color: #ff6b6b; margin-bottom: 1rem;"></i>
                                </div>
                                <div class="error-state-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: #ff6b6b;">
                                    Server Not Running
                                </div>
                                <div class="error-state-text" style="color: #666; line-height: 1.5; margin-bottom: 1rem;">
                                    The application server on port <strong>${port}</strong> is not accessible.
                                </div>
                                 
                                <div style="margin-top: 1rem;">
                                    <button onclick="window.ArtifactsLoader.checkAndRestartServers(${projectId})" style="background: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-right: 0.5rem;">
                                        <i class="fas fa-refresh"></i> Check Again
                                    </button>
                                    <button onclick="window.open('http://localhost:${port}', '_blank')" style="background: #6c757d; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">
                                        <i class="fas fa-external-link-alt"></i> Open in New Tab
                                    </button>
                                </div>
                            </div>
                        `;
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error fetching server configs:', error);
                    showErrorState(`Error loading server configurations: ${error.message}. Please try refreshing the page or check if the server is running.`);
                });
                
            // Helper function to show the empty state
            function showEmptyState(message) {
                appLoading.style.display = 'none';
                appEmpty.style.display = 'block';
                appEmpty.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">
                            <i class="fas fa-server" style="font-size: 3rem; color: #666; margin-bottom: 1rem;"></i>
                        </div>
                        <div class="empty-state-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: #333;">
                            No Application Server Running
                        </div>
                        <div class="empty-state-text" style="color: #666; line-height: 1.5; white-space: pre-line;">
                            ${message}
                        </div>
                    </div>
                `;
            }
            
            // Helper function to show error state
            function showErrorState(message) {
                appLoading.style.display = 'none';
                appEmpty.style.display = 'block';
                
                // Hide URL panel when showing error
                const urlPanel = document.getElementById('app-url-panel');
                if (urlPanel) {
                    urlPanel.style.display = 'none';
                }
                
                // Hide console button
                const showConsoleBtn = document.getElementById('show-console-btn');
                if (showConsoleBtn) {
                    showConsoleBtn.style.display = 'none';
                }
                
                appEmpty.innerHTML = `
                    <div class="error-state">
                        <div class="error-state-icon">
                            <i class="fas fa-exclamation-triangle" style="font-size: 3rem; color: #ff6b6b; margin-bottom: 1rem;"></i>
                        </div>
                        <div class="error-state-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: #ff6b6b;">
                            Server Connection Failed
                        </div>
                        <div class="error-state-text" style="color: #666; line-height: 1.5; white-space: pre-line;">
                            ${message}
                        </div>
                        <div style="margin-top: 1rem;">
                            <button onclick="window.ArtifactsLoader.loadAppPreview(${projectId})" style="background: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">
                                <i class="fas fa-refresh"></i> Try Again
                            </button>
                        </div>
                    </div>
                `;
            }
        },

        /**
         * Check server status and restart if needed
         * @param {number} projectId - The ID of the current project
         */
        checkAndRestartServers: function(projectId) {
            console.log(`[ArtifactsLoader] checkAndRestartServers called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for checking servers');
                return;
            }
            
            // Get app tab elements
            const appLoading = document.getElementById('app-loading');
            const appEmpty = document.getElementById('app-empty');
            const appFrameContainer = document.getElementById('app-frame-container');
            
            if (!appLoading || !appEmpty || !appFrameContainer) {
                console.warn('[ArtifactsLoader] One or more app tab elements not found');
                return;
            }
            
            // Show loading state
            appEmpty.style.display = 'none';
            appFrameContainer.style.display = 'none';
            appLoading.style.display = 'block';
            
            // Update loading message to indicate server check
            appLoading.innerHTML = '<div class="spinner"></div><div>Checking and restarting servers...</div>';
            
            // Call the new check servers API
            const url = `/projects/${projectId}/api/check-servers/`;
            console.log(`[ArtifactsLoader] Calling server check API: ${url}`);
            
            fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                }
            })
            .then(response => {
                console.log(`[ArtifactsLoader] Server check API response received, status: ${response.status}`);
                if (!response.ok) {
                    throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('[ArtifactsLoader] Server check API data received:', data);
                
                // Check the overall status
                if (data.status === 'all_running') {
                    // All servers are running, reload the app preview
                    console.log('[ArtifactsLoader] All servers running, reloading app preview');
                    setTimeout(() => {
                        this.loadAppPreview(projectId);
                    }, 1000); // Small delay to ensure servers are fully ready
                } else if (data.status === 'partial_running') {
                    // Some servers are running
                    this.showServerCheckResult(data, projectId);
                } else {
                    // Show error or status information
                    this.showServerCheckResult(data, projectId);
                }
            })
            .catch(error => {
                console.error('[ArtifactsLoader] Error checking servers:', error);
                appLoading.style.display = 'none';
                appEmpty.style.display = 'block';
                appEmpty.innerHTML = `
                    <div class="error-state">
                        <div class="error-state-icon">
                            <i class="fas fa-exclamation-triangle" style="font-size: 3rem; color: #ff6b6b; margin-bottom: 1rem;"></i>
                        </div>
                        <div class="error-state-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: #ff6b6b;">
                            Server Check Failed
                        </div>
                        <div class="error-state-text" style="color: #666; line-height: 1.5; margin-bottom: 1rem;">
                            Error checking server status: ${error.message}
                        </div>
                        <div style="margin-top: 1rem;">
                            <button onclick="window.ArtifactsLoader.checkAndRestartServers(${projectId})" style="background: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">
                                <i class="fas fa-refresh"></i> Try Again
                            </button>
                        </div>
                    </div>
                `;
            });
        },

        /**
         * Show server check results
         * @param {object} data - Server check result data
         * @param {number} projectId - The project ID
         */
        showServerCheckResult: function(data, projectId) {
            const appLoading = document.getElementById('app-loading');
            const appEmpty = document.getElementById('app-empty');
            
            appLoading.style.display = 'none';
            appEmpty.style.display = 'block';
            
            let statusIcon = 'fas fa-server';
            let statusColor = '#666';
            let statusTitle = 'Server Status';
            
            if (data.status === 'all_running') {
                statusIcon = 'fas fa-check-circle';
                statusColor = '#28a745';
                statusTitle = 'All Servers Running';
            } else if (data.status === 'partial_running') {
                statusIcon = 'fas fa-exclamation-triangle';
                statusColor = '#ffc107';
                statusTitle = 'Some Servers Running';
            } else if (data.status === 'none_running') {
                statusIcon = 'fas fa-times-circle';
                statusColor = '#dc3545';
                statusTitle = 'No Servers Running';
            } else if (data.status === 'error') {
                statusIcon = 'fas fa-exclamation-triangle';
                statusColor = '#dc3545';
                statusTitle = 'Server Check Error';
            }
            
            let serversHtml = '';
            if (data.servers && data.servers.length > 0) {
                serversHtml = '<div style="margin-top: 1rem; text-align: left;">';
                data.servers.forEach(server => {
                    let serverStatusColor = '#666';
                    let serverStatusIcon = 'fas fa-circle';
                    
                    switch(server.status) {
                        case 'running':
                            serverStatusColor = '#28a745';
                            serverStatusIcon = 'fas fa-check-circle';
                            break;
                        case 'restarted':
                            serverStatusColor = '#17a2b8';
                            serverStatusIcon = 'fas fa-sync';
                            break;
                        case 'failed':
                            serverStatusColor = '#dc3545';
                            serverStatusIcon = 'fas fa-times-circle';
                            break;
                        case 'no_command':
                            serverStatusColor = '#ffc107';
                            serverStatusIcon = 'fas fa-exclamation-circle';
                            break;
                    }
                    
                    serversHtml += `
                        <div style="margin-bottom: 0.5rem; padding: 0.5rem; background: #f8f9fa; border-radius: 4px;">
                            <div style="display: flex; align-items: center; margin-bottom: 0.25rem;">
                                <i class="${serverStatusIcon}" style="color: ${serverStatusColor}; margin-right: 0.5rem;"></i>
                                <strong>${server.type.charAt(0).toUpperCase() + server.type.slice(1)} Server (Port ${server.port})</strong>
                            </div>
                            <div style="color: #666; font-size: 0.9rem;">
                                ${server.message}
                            </div>
                            ${server.status === 'running' || server.status === 'restarted' ? 
                                `<div style="margin-top: 0.25rem;">
                                    <a href="${server.url}" target="_blank" style="color: #007bff; text-decoration: none; font-size: 0.9rem;">
                                        <i class="fas fa-external-link-alt"></i> Open ${server.url}
                                    </a>
                                </div>` : ''
                            }
                        </div>
                    `;
                });
                serversHtml += '</div>';
            }
            
            appEmpty.innerHTML = `
                <div class="server-status-state" style="display: flex; flex-direction: column; align-items: center; padding: 2rem;">
                    <div class="status-icon">
                        <i class="${statusIcon}" style="font-size: 3rem; color: ${statusColor}; margin-bottom: 1rem;"></i>
                    </div>
                    <div class="status-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: ${statusColor};">
                        ${statusTitle}
                    </div>
                    <div class="status-message" style="color: #666; line-height: 1.5; margin-bottom: 1rem; text-align: center;">
                        ${data.message}
                    </div>
                    ${serversHtml}
                    <div style="margin-top: 1rem;">
                        <button onclick="window.ArtifactsLoader.checkAndRestartServers(${projectId})" style="background: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-right: 0.5rem;">
                            <i class="fas fa-refresh"></i> Check Again
                        </button>
                        ${data.status === 'all_running' || data.status === 'partial_running' ? 
                            `<button onclick="window.ArtifactsLoader.loadAppPreview(${projectId})" style="background: #28a745; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">
                                <i class="fas fa-eye"></i> View App
                            </button>` : ''
                        }
                    </div>
                </div>
            `;
        },

        /**
         * Load Tool Call History for a project
         * @param {number} projectId - The project ID
         */
        loadToolHistory: function(projectId) {
            console.log(`[ArtifactsLoader] Loading tool history for project ${projectId}`);
            
            const toolhistoryContainer = document.getElementById('toolhistory');
            const toolhistoryLoading = document.getElementById('toolhistory-loading');
            const toolhistoryEmpty = document.getElementById('toolhistory-empty');
            const toolhistoryList = document.getElementById('toolhistory-list');
            const toolFilter = document.getElementById('tool-filter');
            const refreshButton = document.getElementById('refresh-toolhistory');
            
            if (!toolhistoryContainer || !toolhistoryLoading || !toolhistoryEmpty || !toolhistoryList) {
                console.error('[ArtifactsLoader] Tool history UI elements not found');
                return;
            }
            
            // Function to fetch and display tool history
            const fetchToolHistory = (filterValue = '') => {
                // Show loading state
                toolhistoryLoading.style.display = 'block';
                toolhistoryEmpty.style.display = 'none';
                toolhistoryList.style.display = 'none';
                
                let url = `/projects/${projectId}/api/tool-call-history/`;
                if (filterValue) {
                    url += `?tool_name=${encodeURIComponent(filterValue)}`;
                }
                
                fetch(url, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    toolhistoryLoading.style.display = 'none';
                    
                    if (data.tool_call_history && data.tool_call_history.length > 0) {
                        toolhistoryList.style.display = 'block';
                        toolhistoryEmpty.style.display = 'none';
                        
                        // Build the HTML for tool history items
                        let html = '';
                        data.tool_call_history.forEach(item => {
                            const date = new Date(item.created_at);
                            const formattedDate = date.toLocaleString();
                            const hasError = item.metadata && item.metadata.has_error;
                            
                            html += `
                                <div class="tool-history-item" style="background: #2a2a2a; border: 1px solid #333; border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                        <h4 style="margin: 0; color: ${hasError ? '#ff6b6b' : '#8b5cf6'};">
                                            <i class="fas ${hasError ? 'fa-exclamation-circle' : 'fa-tools'}"></i> ${item.tool_name}
                                        </h4>
                                        <span style="color: #666; font-size: 0.875rem;">${formattedDate}</span>
                                    </div>
                                    ${item.tool_input && Object.keys(item.tool_input).length > 0 ? `
                                        <div style="margin-bottom: 10px;">
                                            <strong style="color: #999;">Input:</strong>
                                            <pre style="background: #1a1a1a; padding: 10px; border-radius: 4px; overflow-x: auto; margin-top: 5px; font-size: 0.875rem;">${JSON.stringify(item.tool_input, null, 2)}</pre>
                                        </div>
                                    ` : ''}
                                    <div>
                                        <strong style="color: #999;">Generated Content:</strong>
                                        <div style="background: #1a1a1a; padding: 10px; border-radius: 4px; margin-top: 5px; max-height: 300px; overflow-y: auto;">
                                            <pre style="white-space: pre-wrap; margin: 0; font-size: 0.875rem;">${item.generated_content}</pre>
                                        </div>
                                    </div>
                                </div>
                            `;
                        });
                        
                        toolhistoryList.innerHTML = html;
                        
                        // Add "Load More" button if there are more items
                        if (data.has_more) {
                            toolhistoryList.innerHTML += `
                                <div style="text-align: center; margin-top: 20px;">
                                    <button id="load-more-toolhistory" class="btn btn-primary" style="background: #8b5cf6; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">
                                        Load More
                                    </button>
                                </div>
                            `;
                            
                            // Add event listener for load more button
                            const loadMoreBtn = document.getElementById('load-more-toolhistory');
                            if (loadMoreBtn) {
                                loadMoreBtn.addEventListener('click', () => {
                                    const newOffset = data.offset + data.limit;
                                    fetchToolHistory(filterValue, newOffset);
                                });
                            }
                        }
                    } else {
                        toolhistoryList.style.display = 'none';
                        toolhistoryEmpty.style.display = 'block';
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error loading tool history:', error);
                    toolhistoryLoading.style.display = 'none';
                    toolhistoryEmpty.style.display = 'block';
                    toolhistoryEmpty.innerHTML = `
                        <div class="empty-state-icon">
                            <i class="fas fa-exclamation-triangle"></i>
                        </div>
                        <div class="empty-state-text">
                            Error loading tool history: ${error.message}
                        </div>
                    `;
                });
            };
            
            // Initial load
            fetchToolHistory();
            
            // Add event listeners
            if (toolFilter) {
                let filterTimeout;
                toolFilter.addEventListener('input', (e) => {
                    clearTimeout(filterTimeout);
                    filterTimeout = setTimeout(() => {
                        fetchToolHistory(e.target.value);
                    }, 300);
                });
            }
            
            if (refreshButton) {
                refreshButton.addEventListener('click', () => {
                    fetchToolHistory(toolFilter ? toolFilter.value : '');
                });
            }
        },
        
        /**
         * Add a pending tool call to the history immediately
         * @param {string} toolName - The name of the tool being called
         * @param {object} toolInput - The input parameters for the tool
         * @returns {string} - The ID of the pending element
         */
        addPendingToolCall: function(toolName, toolInput, options = {}) {
            console.log(`[ArtifactsLoader] Adding pending tool call: ${toolName}`);
            
            const toolhistoryList = document.getElementById('toolhistory-list');
            const toolhistoryEmpty = document.getElementById('toolhistory-empty');
            
            if (!toolhistoryList) {
                console.warn('[ArtifactsLoader] Tool history list not found');
                return;
            }
            
            const escapeHtml = (value) => {
                if (value === null || value === undefined) {
                    return '';
                }
                return String(value)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            };

            const formatTimestamp = (isoString) => {
                if (!isoString) return '';
                const date = new Date(isoString);
                if (Number.isNaN(date.getTime())) return '';
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            };

            // Hide empty state
            if (toolhistoryEmpty) {
                toolhistoryEmpty.style.display = 'none';
            }
            
            // Make sure list is visible
            toolhistoryList.style.display = 'block';
            
            // Create a unique ID for this pending call
            const pendingId = `pending-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            
            const explanationBlock = options.explanation ? `
                <div style="margin-bottom: 10px;">
                    <strong style="color: #999;">Plan:</strong>
                    <div style="background: #1a1a1a; padding: 10px; border-radius: 4px; margin-top: 5px;">
                        ${escapeHtml(options.explanation)}
                    </div>
                </div>
            ` : '';

            const ticket = options.ticket || {};
            const ticketBlock = ticket && (ticket.id || ticket.name) ? `
                <div style="margin-bottom: 10px; display: flex; gap: 8px; align-items: center; color: #c4b5fd;">
                    <i class="fas fa-ticket-alt"></i>
                    <span>Ticket: ${escapeHtml(ticket.id || ticket.name || '')}${ticket.name && ticket.id ? ' • ' + escapeHtml(ticket.name) : ''}</span>
                </div>
            ` : '';

            const startedAtLabel = options.startedAt ? `
                <span style="color: #666; font-size: 0.75rem;">Started ${formatTimestamp(options.startedAt)}</span>
            ` : '';

            const inputPreview = toolInput && Object.keys(toolInput).length > 0
                ? `<pre style="background: #1a1a1a; padding: 10px; border-radius: 4px; overflow-x: auto; margin-top: 5px; font-size: 0.875rem;">${escapeHtml(JSON.stringify(toolInput, null, 2))}</pre>`
                : '';

            // Create the pending tool call HTML
            const pendingHtml = `
                <div id="${pendingId}" class="tool-history-item pending-tool-call" style="background: #2a2a2a; border: 1px solid #666; border-radius: 8px; padding: 15px; margin-bottom: 15px; opacity: 0.8;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <h4 style="margin: 0; color: #fbbf24;">
                            <i class="fas fa-spinner fa-spin"></i> ${toolName}
                        </h4>
                        <span style="color: #666; font-size: 0.875rem;">Executing... ${startedAtLabel}</span>
                    </div>
                    ${explanationBlock}
                    ${ticketBlock}
                    ${inputPreview ? `
                        <div style="margin-bottom: 10px;">
                            <strong style="color: #999;">Input Preview:</strong>
                            ${inputPreview}
                        </div>
                    ` : ''}
                    <div>
                        <strong style="color: #999;">Generated Content:</strong>
                        <div style="background: #1a1a1a; padding: 10px; border-radius: 4px; margin-top: 5px;">
                            <div style="color: #666; font-style: italic;">
                                <i class="fas fa-hourglass-half"></i> Waiting for response...
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            // Prepend to the list
            toolhistoryList.insertAdjacentHTML('afterbegin', pendingHtml);
            
            // Return the pending ID so it can be updated later
            return pendingId;
        },

        updatePendingToolCall: function(pendingId, updateData = {}) {
            const pendingElement = document.getElementById(pendingId);
            if (!pendingElement) {
                console.warn('[ArtifactsLoader] Pending tool call element not found:', pendingId);
                const projectId = this.getCurrentProjectId();
                if (projectId && typeof this.loadToolHistory === 'function') {
                    this.loadToolHistory(projectId);
                }
                return;
            }

            const escapeHtml = (value) => {
                if (value === null || value === undefined) {
                    return '';
                }
                return String(value)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            };

            const truncateText = (value, limit = 400) => {
                if (value === null || value === undefined) {
                    return '';
                }
                const str = String(value);
                if (str.length <= limit) {
                    return str;
                }
                const overflow = str.length - limit;
                return `${str.substring(0, limit)}... (+${overflow} chars)`;
            };

            const status = (updateData.status || 'completed').toLowerCase();
            const errorStatuses = ['failed', 'error', 'timeout'];
            const runningStatuses = ['in_progress', 'running'];
            const queuedStatuses = ['queued', 'pending'];

            let statusColor = '#34d399';
            let statusIcon = 'fas fa-check-circle';
            let statusLabel = 'Completed';

            if (errorStatuses.includes(status)) {
                statusColor = '#f87171';
                statusIcon = 'fas fa-exclamation-circle';
                statusLabel = 'Failed';
            } else if (runningStatuses.includes(status)) {
                statusColor = '#fbbf24';
                statusIcon = 'fas fa-spinner fa-spin';
                statusLabel = 'In Progress';
            } else if (queuedStatuses.includes(status)) {
                statusColor = '#60a5fa';
                statusIcon = 'fas fa-clock';
                statusLabel = 'Queued';
            }

            const message = updateData.message || updateData.result_excerpt || '';
            const resultDetails = updateData.result_excerpt && updateData.result_excerpt !== message
                ? updateData.result_excerpt
                : '';

            const stderr = updateData.stderr ? truncateText(updateData.stderr, 400) : '';
            const stdout = updateData.stdout ? truncateText(updateData.stdout, 400) : '';

            pendingElement.classList.remove('pending-tool-call');
            pendingElement.style.opacity = '1';

            pendingElement.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <h4 style="margin: 0; color: ${statusColor};">
                        <i class="${statusIcon}"></i> ${escapeHtml(updateData.function_name || 'tool_call')}
                    </h4>
                    <span style="color: ${statusColor}; font-size: 0.875rem; font-weight: 600; text-transform: uppercase;">
                        ${statusLabel}
                    </span>
                </div>
                ${message ? `
                    <div style="margin-bottom: 10px;">
                        <strong style="color: #999;">Summary:</strong>
                        <div style="background: #1a1a1a; padding: 10px; border-radius: 4px; margin-top: 5px;">
                            ${escapeHtml(message)}
                        </div>
                    </div>
                ` : ''}
                ${resultDetails ? `
                    <div style="margin-bottom: 10px;">
                        <strong style="color: #999;">Details:</strong>
                        <div style="background: #1a1a1a; padding: 10px; border-radius: 4px; margin-top: 5px; max-height: 200px; overflow-y: auto;">
                            ${escapeHtml(resultDetails)}
                        </div>
                    </div>
                ` : ''}
                ${stdout ? `
                    <div style="margin-bottom: 10px;">
                        <strong style="color: #999;">stdout:</strong>
                        <pre style="background: #111827; padding: 10px; border-radius: 4px; overflow-x: auto;">${escapeHtml(stdout)}</pre>
                    </div>
                ` : ''}
                ${stderr ? `
                    <div style="margin-bottom: 10px;">
                        <strong style="color: #f87171;">stderr:</strong>
                        <pre style="background: #111827; padding: 10px; border-radius: 4px; overflow-x: auto; color: #fca5a5;">${escapeHtml(stderr)}</pre>
                    </div>
                ` : ''}
            `;
        },
        
        /**
         * Execute a ticket by sending a command to build the feature
         * @param {number} ticketId - The ID of the ticket to execute
         */
        executeTicket: function(ticketId) {
            console.log(`[ArtifactsLoader] Executing ticket ${ticketId}`);
            
            // Find the ticket data
            const projectId = this.getCurrentProjectId();
            if (!projectId) {
                console.error('[ArtifactsLoader] No project ID found');
                alert('Unable to execute ticket: No project ID found');
                return;
            }
            
            // Get ticket details from the stored tickets data
            fetch(`/projects/${projectId}/api/checklist/`)
                .then(response => response.json())
                .then(data => {
                    const tickets = data.checklist || [];
                    const ticket = tickets.find(t => t.id == ticketId);
                    
                    if (!ticket) {
                        console.error('[ArtifactsLoader] Ticket not found:', ticketId);
                        alert('Unable to execute ticket: Ticket not found');
                        return;
                    }
                    
                    // Construct the command to send
                    let command = `Build the following feature from ticket #${ticket.id}: "${ticket.name}"\n\n`;
                    command += `Description: ${ticket.description}\n\n`;
                    
                    if (ticket.details && Object.keys(ticket.details).length > 0) {
                        command += `Technical Details:\n${JSON.stringify(ticket.details, null, 2)}\n\n`;
                    }
                    
                    if (ticket.acceptance_criteria && ticket.acceptance_criteria.length > 0) {
                        command += `Acceptance Criteria:\n`;
                        ticket.acceptance_criteria.forEach(criteria => {
                            command += `- ${criteria}\n`;
                        });
                        command += `\n`;
                    }
                    
                    command += `Please implement this feature following the specifications above.`;
                    
                    // Close any open ticket modal before sending the command
                    if (window.ArtifactsLoader && typeof window.ArtifactsLoader.closeTicketModal === 'function') {
                        window.ArtifactsLoader.closeTicketModal();
                    }
                    
                    // Send the command to the chat
                    if (window.sendMessage && typeof window.sendMessage === 'function') {
                        console.log('[ArtifactsLoader] Sending ticket execution command to chat');
                        window.sendMessage(command);
                    } else {
                        // Fallback: try to find the chat input and trigger send
                        const chatInput = document.getElementById('chat-input');
                        const sendButton = document.getElementById('send-btn');
                        
                        if (chatInput && sendButton) {
                            chatInput.value = command;
                            // Trigger input event to update any listeners
                            chatInput.dispatchEvent(new Event('input', { bubbles: true }));
                            // Click the send button
                            sendButton.click();
                        } else {
                            console.error('[ArtifactsLoader] Unable to send message - no chat interface found');
                            alert('Unable to send command to chat. Please copy the command manually.');
                        }
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error fetching ticket details:', error);
                    alert('Error executing ticket: ' + error.message);
                });
        },
        
        /**
         * Download file content as PDF
         * @param {number} projectId - The ID of the current project
         * @param {string} title - The title of the document
         * @param {string} content - The markdown content
         */
        downloadFileAsPDF: function(projectId, title, content) {
            console.log('[ArtifactsLoader] downloadFileAsPDF called');
            
            // Check if jsPDF is available
            if (typeof window.jspdf === 'undefined' || typeof window.jspdf.jsPDF === 'undefined') {
                console.error('[ArtifactsLoader] jsPDF library not loaded');
                alert('PDF generation library not loaded. Please refresh the page and try again.');
                return;
            }
            
            // Create progress indicator
            const progressOverlay = document.createElement('div');
            progressOverlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
            `;
            
            const progressContent = document.createElement('div');
            progressContent.style.cssText = `
                background: white;
                padding: 30px;
                border-radius: 8px;
                text-align: center;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            `;
            progressContent.innerHTML = `
                <div style="margin-bottom: 15px;">
                    <div class="spinner" style="border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
                </div>
                <div style="color: #333; font-family: Arial, sans-serif;">Generating PDF...</div>
            `;
            
            // Add spinner animation
            const style = document.createElement('style');
            style.textContent = `
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
            
            progressOverlay.appendChild(progressContent);
            document.body.appendChild(progressOverlay);
            
            // Use setTimeout to allow the progress indicator to render
            setTimeout(() => {
                try {
                    // Initialize jsPDF
                    const { jsPDF } = window.jspdf;
                    const doc = new jsPDF({
                        orientation: 'portrait',
                        unit: 'mm',
                        format: 'a4'
                    });
                    
                    // Parse markdown to plain text and HTML structure
                    const htmlContent = typeof marked !== 'undefined' ? marked.parse(content) : content;
                    
                    // Create temporary div to parse HTML
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = htmlContent;
                    
                    // Define margins and spacing
                    const leftMargin = 20;
                    const rightMargin = 20;
                    const topMargin = 25;  // Header space
                    const bottomMargin = 20;  // Footer space  
                    const pageWidth = 210 - leftMargin - rightMargin;
                    const pageHeight = 297;
                    const maxY = pageHeight - bottomMargin;
                    let currentY = topMargin;
                    let pageNumber = 1;
                    
                    // Function to check if we need a new page
                    const checkNewPage = (additionalHeight = 10) => {
                        if (currentY + additionalHeight > maxY) {
                            addPageNumber();
                            doc.addPage();
                            currentY = topMargin;
                            pageNumber++;
                            return true;
                        }
                        return false;
                    };
                    
                    // Function to add page number
                    const addPageNumber = () => {
                        doc.setFontSize(10);
                        doc.setTextColor(100, 100, 100);
                        const pageNumText = `Page ${pageNumber}`;
                        const textWidth = doc.getTextWidth(pageNumText);
                        doc.text(pageNumText, (210 - textWidth) / 2, pageHeight - 10);
                        doc.setTextColor(0, 0, 0); // Reset to black
                    };
                    
                    // Add title
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(24);
                    doc.setTextColor(0, 0, 0);
                    const titleLines = doc.splitTextToSize(title, pageWidth);
                    titleLines.forEach(line => {
                        checkNewPage();
                        doc.text(line, leftMargin, currentY);
                        currentY += 10;
                    });
                    currentY += 15; // Extra space after title
                    
                    // Process content
                    const processNode = (node) => {
                        if (node.nodeType === Node.TEXT_NODE) {
                            const text = node.textContent.trim();
                            if (text) {
                                doc.setFont('helvetica', 'normal');
                                doc.setFontSize(11);
                                const lines = doc.splitTextToSize(text, pageWidth);
                                lines.forEach(line => {
                                    checkNewPage();
                                    doc.text(line, leftMargin, currentY);
                                    currentY += 6;
                                });
                            }
                        } else if (node.nodeType === Node.ELEMENT_NODE) {
                            const tagName = node.tagName.toLowerCase();
                            
                            switch (tagName) {
                                case 'h1':
                                case 'h2':
                                case 'h3':
                                case 'h4':
                                case 'h5':
                                case 'h6':
                                    currentY += 8; // Space before heading
                                    const headingSize = 20 - (parseInt(tagName.charAt(1)) * 2);
                                    doc.setFont('helvetica', 'bold');
                                    doc.setFontSize(headingSize);
                                    const headingLines = doc.splitTextToSize(node.textContent.trim(), pageWidth);
                                    headingLines.forEach(line => {
                                        checkNewPage();
                                        doc.text(line, leftMargin, currentY);
                                        currentY += headingSize * 0.4;
                                    });
                                    currentY += 6; // Space after heading
                                    doc.setFont('helvetica', 'normal');
                                    break;
                                    
                                case 'p':
                                    node.childNodes.forEach(child => processNode(child));
                                    currentY += 8; // Paragraph spacing
                                    break;
                                    
                                case 'ul':
                                case 'ol':
                                    currentY += 4; // Space before list
                                    Array.from(node.children).forEach((li, index) => {
                                        checkNewPage();
                                        const bullet = tagName === 'ol' ? `${index + 1}. ` : '• ';
                                        doc.setFont('helvetica', 'normal');
                                        doc.setFontSize(11);
                                        const text = li.textContent.trim();
                                        const bulletWidth = doc.getTextWidth(bullet);
                                        
                                        // Add bullet
                                        doc.text(bullet, leftMargin + 5, currentY);
                                        
                                        // Add text with indent
                                        const lines = doc.splitTextToSize(text, pageWidth - 10);
                                        lines.forEach((line, lineIndex) => {
                                            if (lineIndex > 0) {
                                                checkNewPage();
                                            }
                                            doc.text(line, leftMargin + 5 + bulletWidth, currentY);
                                            currentY += 6;
                                        });
                                        currentY += 2; // Space between list items
                                    });
                                    currentY += 4; // Space after list
                                    break;
                                    
                                case 'br':
                                    currentY += 6;
                                    break;
                                    
                                case 'strong':
                                case 'b':
                                    doc.setFont('helvetica', 'bold');
                                    node.childNodes.forEach(child => processNode(child));
                                    doc.setFont('helvetica', 'normal');
                                    break;
                                    
                                case 'em':
                                case 'i':
                                    doc.setFont('helvetica', 'italic');
                                    node.childNodes.forEach(child => processNode(child));
                                    doc.setFont('helvetica', 'normal');
                                    break;
                                    
                                case 'code':
                                    doc.setFont('courier', 'normal');
                                    doc.setFontSize(10);
                                    const codeText = node.textContent.trim();
                                    const codeLines = doc.splitTextToSize(codeText, pageWidth - 10);
                                    codeLines.forEach(line => {
                                        checkNewPage();
                                        doc.text(line, leftMargin + 5, currentY);
                                        currentY += 5;
                                    });
                                    doc.setFont('helvetica', 'normal');
                                    doc.setFontSize(11);
                                    break;
                                    
                                case 'pre':
                                    currentY += 4;
                                    doc.setFont('courier', 'normal');
                                    doc.setFontSize(9);
                                    const preText = node.textContent;
                                    const preLines = preText.split('\n');
                                    preLines.forEach(line => {
                                        const wrappedLines = doc.splitTextToSize(line || ' ', pageWidth - 10);
                                        wrappedLines.forEach(wrappedLine => {
                                            checkNewPage();
                                            doc.text(wrappedLine, leftMargin + 5, currentY);
                                            currentY += 5;
                                        });
                                    });
                                    doc.setFont('helvetica', 'normal');
                                    doc.setFontSize(11);
                                    currentY += 4;
                                    break;
                                    
                                case 'table':
                                    currentY += 8; // Space before table
                                    
                                    // Extract table data first
                                    const rows = node.querySelectorAll('tr');
                                    const tableRows = [];
                                    let maxColumns = 0;
                                    
                                    // Process all rows to get data and find max columns
                                    rows.forEach((row) => {
                                        const cells = row.querySelectorAll('td, th');
                                        const rowData = [];
                                        cells.forEach(cell => {
                                            rowData.push(cell.textContent.trim());
                                        });
                                        if (rowData.length > maxColumns) {
                                            maxColumns = rowData.length;
                                        }
                                        tableRows.push({
                                            data: rowData,
                                            isHeader: row.querySelector('th') !== null || row.parentElement.tagName === 'THEAD'
                                        });
                                    });
                                    
                                    if (tableRows.length > 0 && maxColumns > 0) {
                                        // Calculate column widths
                                        const totalTableWidth = pageWidth;
                                        const columnWidth = totalTableWidth / maxColumns;
                                        const cellPadding = 3;
                                        
                                        // Draw the table
                                        doc.setFontSize(9);
                                        
                                        // First, calculate all row heights
                                        const rowHeights = [];
                                        tableRows.forEach((row) => {
                                            let maxHeight = 10; // minimum row height
                                            row.data.forEach((cellText) => {
                                                const cellTextLines = doc.splitTextToSize(cellText, columnWidth - (cellPadding * 2));
                                                const cellHeight = cellTextLines.length * 4 + 6;
                                                if (cellHeight > maxHeight) {
                                                    maxHeight = cellHeight;
                                                }
                                            });
                                            rowHeights.push(maxHeight);
                                        });
                                        
                                        // Calculate total table height
                                        const totalTableHeight = rowHeights.reduce((sum, height) => sum + height, 0);
                                        
                                        // Check if entire table fits on current page
                                        if (checkNewPage(totalTableHeight + 10)) {
                                            currentY += 10; // Add some space at top of new page
                                        }
                                        
                                        const tableStartY = currentY;
                                        
                                        // Draw table
                                        tableRows.forEach((row, rowIndex) => {
                                            const rowHeight = rowHeights[rowIndex];
                                            const rowY = currentY;
                                            
                                            // Draw background for entire row first
                                            if (row.isHeader) {
                                                doc.setFillColor(66, 66, 66);
                                                doc.rect(leftMargin, rowY, totalTableWidth, rowHeight, 'F');
                                            } else if (rowIndex % 2 === 1) {
                                                doc.setFillColor(245, 245, 245);
                                                doc.rect(leftMargin, rowY, totalTableWidth, rowHeight, 'F');
                                            }
                                            
                                            // Draw cells
                                            row.data.forEach((cellText, colIndex) => {
                                                const cellX = leftMargin + (colIndex * columnWidth);
                                                
                                                // Set font style
                                                if (row.isHeader) {
                                                    doc.setFont('helvetica', 'bold');
                                                    doc.setTextColor(255, 255, 255);
                                                } else {
                                                    doc.setFont('helvetica', 'normal');
                                                    doc.setTextColor(0, 0, 0);
                                                }
                                                
                                                // Split text to fit in cell
                                                const cellTextLines = doc.splitTextToSize(cellText, columnWidth - (cellPadding * 2));
                                                
                                                // Draw text vertically centered in cell
                                                const textStartY = rowY + ((rowHeight - (cellTextLines.length * 4)) / 2) + 4;
                                                cellTextLines.forEach((line, lineIndex) => {
                                                    doc.text(line, cellX + cellPadding, textStartY + (lineIndex * 4));
                                                });
                                                
                                                // Draw vertical cell border
                                                if (colIndex < row.data.length - 1) {
                                                    doc.setDrawColor(200, 200, 200);
                                                    doc.setLineWidth(0.1);
                                                    doc.line(cellX + columnWidth, rowY, cellX + columnWidth, rowY + rowHeight);
                                                }
                                            });
                                            
                                            // Draw horizontal border after row
                                            doc.setDrawColor(200, 200, 200);
                                            doc.setLineWidth(0.1);
                                            doc.line(leftMargin, rowY + rowHeight, leftMargin + totalTableWidth, rowY + rowHeight);
                                            
                                            // Reset text color
                                            doc.setTextColor(0, 0, 0);
                                            
                                            // Move to next row
                                            currentY += rowHeight;
                                        });
                                        
                                        // Draw outer table border
                                        doc.setDrawColor(0, 0, 0);
                                        doc.setLineWidth(0.3);
                                        doc.rect(leftMargin, tableStartY, totalTableWidth, totalTableHeight, 'S');
                                        
                                        doc.setFontSize(11); // Reset font size
                                    }
                                    
                                    currentY += 8; // Space after table
                                    break;
                                    
                                default:
                                    // Process children for other elements
                                    node.childNodes.forEach(child => processNode(child));
                            }
                        }
                    };
                    
                    // Process all content nodes
                    tempDiv.childNodes.forEach(node => processNode(node));
                    
                    // Add page number to last page
                    addPageNumber();
                    
                    // Remove progress indicator
                    document.body.removeChild(progressOverlay);
                    document.head.removeChild(style);
                    
                    // Save the PDF
                    const fileName = `${title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.pdf`;
                    doc.save(fileName);
                    
                } catch (error) {
                    console.error('[ArtifactsLoader] Error generating PDF:', error);
                    alert('Error generating PDF: ' + error.message);
                    
                    // Clean up
                    if (progressOverlay.parentNode) {
                        document.body.removeChild(progressOverlay);
                    }
                    if (style.parentNode) {
                        document.head.removeChild(style);
                    }
                }
            }, 100); // Small delay to show progress indicator
        },

        copyToClipboard: function(text, contentType) {
            if (!text) {
                console.error('No text to copy');
                return;
            }

            // Use the Clipboard API if available
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text)
                    .then(() => {
                        // Show success message
                        const message = document.createElement('div');
                        message.style.cssText = `
                            position: fixed;
                            top: 20px;
                            right: 20px;
                            background: #28a745;
                            color: white;
                            padding: 12px 20px;
                            border-radius: 4px;
                            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                            z-index: 10000;
                            font-size: 14px;
                            animation: slideIn 0.3s ease-out;
                        `;
                        message.textContent = `${contentType || 'Content'} copied to clipboard!`;
                        document.body.appendChild(message);

                        // Remove the message after 3 seconds
                        setTimeout(() => {
                            message.style.animation = 'slideOut 0.3s ease-out';
                            setTimeout(() => document.body.removeChild(message), 300);
                        }, 3000);
                    })
                    .catch(err => {
                        console.error('Failed to copy text: ', err);
                        alert('Failed to copy to clipboard. Please try again.');
                    });
            } else {
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-9999px';
                document.body.appendChild(textArea);
                textArea.select();
                
                try {
                    document.execCommand('copy');
                    alert(`${contentType || 'Content'} copied to clipboard!`);
                } catch (err) {
                    console.error('Fallback copy failed: ', err);
                    alert('Failed to copy to clipboard. Please try again.');
                }
                
                document.body.removeChild(textArea);
            }
        },
        
        /**
         * Download content as Word document
         * @param {string} fileName - The name of the file (without extension)
         * @param {string} content - The markdown content
         */
        downloadAsDoc: function(fileName, content) {
            if (!content) {
                console.error('No content to download');
                return;
            }
            
            // Convert markdown to HTML for better formatting in Word
            let htmlContent = content;
            if (typeof marked !== 'undefined') {
                htmlContent = marked.parse(content);
            }
            
            // Create a blob with HTML content that Word can understand
            const html = `
                <html xmlns:o='urn:schemas-microsoft-com:office:office' 
                      xmlns:w='urn:schemas-microsoft-com:office:word' 
                      xmlns='http://www.w3.org/TR/REC-html40'>
                <head>
                    <meta charset='utf-8'>
                    <title>${fileName}</title>
                    <style>
                        body { font-family: Arial, sans-serif; line-height: 1.6; }
                        h1 { font-size: 24pt; font-weight: bold; }
                        h2 { font-size: 18pt; font-weight: bold; }
                        h3 { font-size: 14pt; font-weight: bold; }
                        p { margin: 10pt 0; }
                        pre { background: #f4f4f4; padding: 10pt; }
                        code { background: #f4f4f4; padding: 2pt 4pt; }
                    </style>
                </head>
                <body>
                    ${htmlContent}
                </body>
                </html>
            `;
            
            const blob = new Blob(['\ufeff', html], { 
                type: 'application/msword' 
            });
            
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${fileName}.doc`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            window.showToast('Document downloaded successfully', 'success');
        },
        
        /**
         * Download content as Markdown file
         * @param {string} fileName - The name of the file (without extension)
         * @param {string} content - The markdown content
         */
        downloadAsMarkdown: function(fileName, content) {
            if (!content) {
                console.error('No content to download');
                return;
            }
            
            const blob = new Blob([content], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${fileName}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            window.showToast('Markdown file downloaded successfully', 'success');
        },
        
        /**
         * Load File Browser for a project
         * @param {number} projectId - The project ID
         * @param {object} options - Optional settings
         * @param {string} options.openFileId - File ID to open after loading
         * @param {string} options.openFileName - File name to open after loading
         */
        loadFileBrowser: function(projectId, options = {}) {
            console.log(`[ArtifactsLoader] Loading file browser for project ${projectId}`, options);
            
            // Store project ID for use in file operations
            window.currentFileBrowserProjectId = projectId;
            
            const fileBrowserContainer = document.getElementById('filebrowser');
            const fileBrowserMain = document.getElementById('filebrowser-main');
            const fileBrowserViewer = document.getElementById('filebrowser-viewer');
            const fileBrowserLoading = document.getElementById('filebrowser-loading');
            const fileBrowserEmpty = document.getElementById('filebrowser-empty');
            const fileBrowserList = document.getElementById('filebrowser-list');
            const fileBrowserPagination = document.getElementById('filebrowser-pagination');
            const fileSearch = document.getElementById('file-search');
            const fileTypeFilter = document.getElementById('file-type-filter');
            const refreshButton = document.getElementById('refresh-filebrowser');
            
            // Viewer elements
            const viewerBack = document.getElementById('viewer-back');
            const viewerTitle = document.getElementById('viewer-title');
            const viewerMarkdown = document.getElementById('viewer-markdown');
            
            if (!fileBrowserContainer || !fileBrowserLoading || !fileBrowserEmpty || !fileBrowserList) {
                console.error('[ArtifactsLoader] File browser UI elements not found', {
                    container: !!fileBrowserContainer,
                    loading: !!fileBrowserLoading,
                    empty: !!fileBrowserEmpty,
                    list: !!fileBrowserList
                });
                return;
            }
            
            let currentPage = 1;
            let currentSearch = '';
            let currentType = '';
            let currentSort = 'updated_at';
            let currentOrder = 'desc';
            let searchTimeout = null;
            
            // Function to fetch and display files
            const fetchFiles = (page = 1) => {
                // Show loading state
                fileBrowserLoading.style.display = 'block';
                fileBrowserEmpty.style.display = 'none';
                fileBrowserList.style.display = 'none';
                fileBrowserPagination.style.display = 'none';
                
                const params = new URLSearchParams({
                    page: page,
                    per_page: 10,
                    search: currentSearch,
                    type: currentType,
                    sort: currentSort,
                    order: currentOrder
                });
                
                fetch(`/projects/${projectId}/api/files/browser/?${params}`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    fileBrowserLoading.style.display = 'none';
                    
                    // Update filter options if first load
                    if (page === 1 && data.filters && data.filters.types) {
                        updateTypeFilterOptions(data.filters.types);
                    }
                    
                    if (data.files && data.files.length > 0) {
                        fileBrowserList.style.display = 'block';
                        fileBrowserEmpty.style.display = 'none';
                        const tableHeader = document.getElementById('file-table-header');
                        if (tableHeader) {
                            tableHeader.style.display = 'grid';
                        } else {
                            console.error('[FileBrowser] Table header element not found');
                        }
                        
                        // Clear the list first
                        fileBrowserList.innerHTML = '';
                        
                        // Create file items with table-like layout
                        data.files.forEach(file => {
                            const icon = getFileIcon(file.type);
                            const typeClass = `file-type-${file.type}`;
                            
                            // Create the main container
                            const fileItem = document.createElement('div');
                            fileItem.className = `file-list-item ${typeClass}`;
                            fileItem.dataset.fileId = file.id;
                            fileItem.dataset.fileType = file.type;
                            fileItem.dataset.fileName = file.name;
                            
                            // Create icon
                            const fileIcon = document.createElement('div');
                            fileIcon.className = 'file-icon';
                            fileIcon.innerHTML = `<i class="${icon}"></i>`;
                            
                            // Create name element
                            const fileName = document.createElement('div');
                            fileName.className = 'file-name';
                            fileName.textContent = file.name || file.type_display || 'Unnamed File';
                            
                            // Create type cell with badge
                            const fileType = document.createElement('div');
                            fileType.className = 'file-type-cell';
                            const typeBadge = document.createElement('span');
                            typeBadge.className = 'file-type-badge';
                            // Use the raw type if type_display is not available
                            const displayType = file.type_display || file.type || 'Unknown';
                            typeBadge.textContent = displayType;
                            typeBadge.title = displayType;
                            fileType.appendChild(typeBadge);
                            
                            // Create owner cell
                            const fileOwner = document.createElement('div');
                            fileOwner.className = 'file-owner-cell';
                            fileOwner.textContent = file.owner || 'System';
                            
                            // Create date cell
                            const fileDate = document.createElement('div');
                            fileDate.className = 'file-date-cell';
                            fileDate.textContent = formatRelativeTime(file.updated_at);
                            
                            // Create context menu button (three dots)
                            const contextMenuBtn = document.createElement('button');
                            contextMenuBtn.className = 'file-context-menu-btn';
                            contextMenuBtn.innerHTML = '<i class="fas fa-ellipsis-v"></i>';
                            contextMenuBtn.style.cssText = `
                                background: none;
                                border: none;
                                color: #9ca3af;
                                cursor: pointer;
                                padding: 4px 8px;
                                opacity: 0;
                                transition: opacity 0.2s;
                                position: absolute;
                                right: 10px;
                                top: 50%;
                                transform: translateY(-50%);
                            `;
                            
                            // Show context button on hover
                            fileItem.addEventListener('mouseenter', () => {
                                contextMenuBtn.style.opacity = '0.7';
                            });
                            fileItem.addEventListener('mouseleave', (e) => {
                                // Check if we're moving to the context menu or its button
                                const relatedTarget = e.relatedTarget;
                                const contextMenu = document.querySelector('.file-context-dropdown');
                                
                                // Don't hide if moving to context button or menu
                                if (relatedTarget && (
                                    relatedTarget === contextMenuBtn ||
                                    relatedTarget.closest('.file-context-dropdown') ||
                                    (contextMenu && contextMenu.contains(relatedTarget))
                                )) {
                                    return;
                                }
                                
                                contextMenuBtn.style.opacity = '0';
                            });
                            
                            // Context menu click handler
                            contextMenuBtn.addEventListener('click', (e) => {
                                e.stopPropagation();
                                
                                // Remove any existing context menu
                                const existingMenu = document.querySelector('.file-context-dropdown');
                                if (existingMenu) {
                                    existingMenu.remove();
                                }
                                
                                // Create context menu
                                const contextMenu = document.createElement('div');
                                contextMenu.className = 'file-context-dropdown';
                                
                                // Get button position
                                const btnRect = contextMenuBtn.getBoundingClientRect();
                                const menuTop = btnRect.bottom + window.scrollY + 5;
                                const menuLeft = btnRect.right + window.scrollX - 160;
                                
                                contextMenu.style.cssText = `
                                    position: fixed;
                                    top: ${btnRect.bottom + 5}px;
                                    left: ${btnRect.right - 160}px;
                                    background: #2a2a2a;
                                    border: 1px solid #444;
                                    border-radius: 6px;
                                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                                    z-index: 1000;
                                    min-width: 150px;
                                    padding: 4px;
                                `;
                                
                                // Delete option
                                const deleteOption = document.createElement('button');
                                deleteOption.style.cssText = `
                                    display: flex;
                                    align-items: center;
                                    gap: 8px;
                                    width: 100%;
                                    padding: 8px 12px;
                                    background: none;
                                    border: none;
                                    color: #e2e8f0;
                                    cursor: pointer;
                                    text-align: left;
                                    font-size: 14px;
                                    transition: background 0.2s;
                                    border-radius: 4px;
                                `;
                                deleteOption.innerHTML = '<i class="fas fa-trash"></i> Delete';
                                deleteOption.onmouseover = function() { this.style.background = 'rgba(239, 68, 68, 0.1)'; this.style.color = '#ef4444'; };
                                deleteOption.onmouseout = function() { this.style.background = 'transparent'; this.style.color = '#e2e8f0'; };
                                deleteOption.addEventListener('click', () => {
                                    contextMenu.remove();
                                    if (confirm(`Are you sure you want to delete "${file.name}"? This action cannot be undone.`)) {
                                        deleteFile(file.id);
                                    }
                                });
                                
                                contextMenu.appendChild(deleteOption);
                                document.body.appendChild(contextMenu);
                                
                                // Keep context button visible when hovering over the menu
                                contextMenu.addEventListener('mouseenter', () => {
                                    contextMenuBtn.style.opacity = '0.7';
                                });
                                
                                contextMenu.addEventListener('mouseleave', (e) => {
                                    // Check if we're going back to the file item
                                    if (!fileItem.contains(e.relatedTarget)) {
                                        contextMenuBtn.style.opacity = '0';
                                        contextMenu.remove();
                                    }
                                });
                                
                                // Close menu when clicking outside
                                const closeMenu = (event) => {
                                    if (!contextMenu.contains(event.target) && event.target !== contextMenuBtn) {
                                        contextMenu.remove();
                                        document.removeEventListener('click', closeMenu);
                                    }
                                };
                                setTimeout(() => document.addEventListener('click', closeMenu), 0);
                            });
                            
                            // Make file item container relative for absolute positioning
                            fileItem.style.position = 'relative';
                            
                            // Assemble the structure
                            fileItem.appendChild(fileIcon);
                            fileItem.appendChild(fileName);
                            fileItem.appendChild(fileType);
                            fileItem.appendChild(fileOwner);
                            fileItem.appendChild(fileDate);
                            fileItem.appendChild(contextMenuBtn);
                            
                            // Add to list
                            fileBrowserList.appendChild(fileItem);
                        });
                        
                        // Show pagination if needed
                        if (data.pagination && data.pagination.pages > 1) {
                            fileBrowserPagination.style.display = 'block';
                            fileBrowserPagination.innerHTML = buildPaginationHTML(data.pagination);
                            attachPaginationListeners();
                        } else {
                            fileBrowserPagination.style.display = 'none';
                        }
                        
                        // Attach event listeners to file items
                        attachFileItemListeners();
                        
                        // Auto-open file if specified
                        if (options.openFileId && options.openFileName) {
                            console.log(`[ArtifactsLoader] Auto-opening file: ${options.openFileId} - ${options.openFileName}`);
                            // Directly call the API to load the file content
                            setTimeout(() => {
                                console.log('[ArtifactsLoader] Loading file content via API');
                                
                                // Call the file content API directly
                                fetch(`/projects/${projectId}/api/files/${options.openFileId}/content/`, {
                                    method: 'GET',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'X-CSRFToken': getCsrfToken(),
                                    }
                                })
                                .then(response => response.json())
                                .then(data => {
                                    // Switch to viewer mode
                                    fileBrowserMain.style.display = 'none';
                                    fileBrowserViewer.style.display = 'flex';
                                    
                                    // Set title
                                    const viewerTitle = document.getElementById('viewer-title');
                                    if (viewerTitle) {
                                        viewerTitle.innerHTML = `
                                            <span id="viewer-title-text">${data.name || options.openFileName}</span>
                                            <button id="viewer-title-edit" style="background: none; border: none; color: #9ca3af; cursor: pointer; margin-left: 8px; padding: 4px; opacity: 0.7;" title="Edit name">
                                                <i class="fas fa-pencil" style="font-size: 12px;"></i>
                                            </button>
                                        `;
                                    }
                                    
                                    // Store current file data
                                    window.currentFileData = {
                                        fileId: options.openFileId,
                                        fileName: data.name || options.openFileName,
                                        fileType: data.type,
                                        content: data.content
                                    };
                                    
                                    // Render the content
                                    const viewerMarkdown = document.getElementById('viewer-markdown');
                                    if (viewerMarkdown) {
                                        // Configure marked if not already configured
                                        if (typeof marked !== 'undefined' && !window.markedConfigured) {
                                            marked.setOptions({
                                                gfm: true,          // Enable GitHub Flavored Markdown
                                                breaks: true,       // Add <br> on line breaks
                                                headerIds: true,    // Add IDs to headers
                                                mangle: false,      // Don't mangle header IDs
                                                tables: true,       // Enable table support
                                                smartLists: true,   // Improve behavior of lists
                                                xhtml: false        // Don't use XHTML compatible tags
                                            });
                                            window.markedConfigured = true;
                                        }
                                        
                                        // Check if content appears to be markdown by looking for common markdown patterns
                                        const isMarkdownContent = (content) => {
                                            if (!content) return false;
                                            // Check for headers, lists, code blocks, tables, links, or emphasis
                                            return /^#{1,6}\s|^\*\s|^\-\s|^\d+\.\s|```|^\|.*\|$|\[.*\]\(.*\)|\*\*.*\*\*|\*.*\*/m.test(content);
                                        };
                                        
                                        // Always render as markdown if it contains markdown patterns or is a known markdown type
                                        const knownMarkdownTypes = ['prd', 'implementation', 'design', 'analysis', 'documentation', 'readme'];
                                        if (knownMarkdownTypes.includes(data.type) || isMarkdownContent(data.content)) {
                                            // Render as markdown
                                            viewerMarkdown.innerHTML = marked.parse(data.content || '');
                                        } else {
                                            // Render as plain text
                                            viewerMarkdown.innerHTML = (data.content || '').replace(/\n/g, '<br>').replace(/\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;');
                                        }
                                    }
                                    
                                    // Set metadata
                                    const viewerMeta = document.getElementById('viewer-meta');
                                    if (viewerMeta) {
                                        viewerMeta.innerHTML = `
                                            <span><i class="fas fa-user"></i> ${data.owner || 'Unknown'}</span>
                                            <span><i class="fas fa-calendar"></i> ${data.created_at ? new Date(data.created_at).toLocaleDateString() : 'Unknown'}</span>
                                            <span><i class="fas fa-tag"></i> ${data.type_display || data.type || 'Document'}</span>
                                        `;
                                    }
                                    
                                    console.log('[ArtifactsLoader] File content loaded and displayed');
                                })
                                .catch(error => {
                                    console.error('[ArtifactsLoader] Error loading file content:', error);
                                    showToast('Failed to load file content', 'error');
                                });
                            }, 100); // Small delay to ensure DOM is ready
                        }
                        
                    } else {
                        fileBrowserList.style.display = 'none';
                        fileBrowserEmpty.style.display = 'block';
                        fileBrowserPagination.style.display = 'none';
                        document.getElementById('file-table-header').style.display = 'none';
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error loading file browser:', error);
                    fileBrowserLoading.style.display = 'none';
                    fileBrowserEmpty.style.display = 'block';
                    showToast('Failed to load files', 'error');
                });
            };
            
            // Helper function to get file icon based on type
            const getFileIcon = (type) => {
                const icons = {
                    'prd': 'fas fa-file-alt',
                    'implementation': 'fas fa-code',
                    'design': 'fas fa-palette',
                    'test': 'fas fa-vial',
                    'analysis': 'fas fa-chart-line',
                    'documentation': 'fas fa-book',
                    'readme': 'fas fa-info-circle',
                    'report': 'fas fa-file-contract',
                    'research': 'fas fa-microscope',
                    'spec': 'fas fa-clipboard-list',
                    'other': 'fas fa-file'
                };
                // Return specific icon if available, otherwise return generic file icon
                return icons[type.toLowerCase()] || icons.other;
            };
            
            // Helper function to escape HTML
            const escapeHtml = (text) => {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            };
            
            // Helper function to format relative time
            const formatRelativeTime = (dateString) => {
                const date = new Date(dateString);
                const now = new Date();
                const diff = now - date;
                const minutes = Math.floor(diff / 60000);
                const hours = Math.floor(minutes / 60);
                const days = Math.floor(hours / 24);
                
                if (days > 0) return `${days}d ago`;
                if (hours > 0) return `${hours}h ago`;
                if (minutes > 0) return `${minutes}m ago`;
                return 'just now';
            };
            
            // Update type filter options
            const updateTypeFilterOptions = (types) => {
                let html = '<option value="">All Types</option>';
                Object.keys(types).forEach(type => {
                    html += `<option value="${type}">${types[type].name} (${types[type].count})</option>`;
                });
                fileTypeFilter.innerHTML = html;
            };
            
            // Build pagination HTML
            const buildPaginationHTML = (pagination) => {
                let html = '<div class="pagination-controls">';
                
                // Previous button
                html += `<button class="pagination-btn" data-page="${pagination.page - 1}" ${!pagination.has_previous ? 'disabled' : ''}>
                    <i class="fas fa-chevron-left"></i>
                </button>`;
                
                // Page numbers
                const maxPages = 5;
                let startPage = Math.max(1, pagination.page - Math.floor(maxPages / 2));
                let endPage = Math.min(pagination.pages, startPage + maxPages - 1);
                
                if (endPage - startPage < maxPages - 1) {
                    startPage = Math.max(1, endPage - maxPages + 1);
                }
                
                for (let i = startPage; i <= endPage; i++) {
                    html += `<button class="pagination-btn ${i === pagination.page ? 'active' : ''}" data-page="${i}">${i}</button>`;
                }
                
                // Next button
                html += `<button class="pagination-btn" data-page="${pagination.page + 1}" ${!pagination.has_next ? 'disabled' : ''}>
                    <i class="fas fa-chevron-right"></i>
                </button>`;
                
                html += `<span class="pagination-info">${pagination.total} files</span>`;
                html += '</div>';
                
                return html;
            };
            
            // Attach pagination event listeners
            const attachPaginationListeners = () => {
                document.querySelectorAll('.pagination-btn').forEach(btn => {
                    btn.addEventListener('click', function() {
                        if (!this.disabled) {
                            currentPage = parseInt(this.dataset.page);
                            fetchFiles(currentPage);
                        }
                    });
                });
            };
            
            // Attach file item event listeners
            const attachFileItemListeners = () => {
                // Click on file item to view
                document.querySelectorAll('.file-list-item').forEach(item => {
                    item.addEventListener('click', function(e) {
                        const fileId = this.dataset.fileId;
                        const fileName = this.querySelector('.file-name').textContent;
                        viewFileContent(fileId, fileName);
                    });
                    
                    // Add right-click context menu
                    item.addEventListener('contextmenu', function(e) {
                        e.preventDefault();
                        const fileId = this.dataset.fileId;
                        const fileName = this.querySelector('.file-name').textContent;
                        showContextMenu(e.pageX, e.pageY, fileId, fileName);
                    });
                });
            };
            
            // Context menu functionality
            let contextMenu = null;
            
            const showContextMenu = (x, y, fileId, fileName) => {
                // Remove existing menu
                if (contextMenu) {
                    contextMenu.remove();
                }
                
                // Create context menu
                contextMenu = document.createElement('div');
                contextMenu.className = 'file-context-menu';
                contextMenu.style.left = x + 'px';
                contextMenu.style.top = y + 'px';
                contextMenu.style.display = 'block';
                
                contextMenu.innerHTML = `
                    <div class="context-menu-item" data-action="view">
                        <i class="fas fa-eye"></i> View
                    </div>
                    <div class="context-menu-item" data-action="copy">
                        <i class="fas fa-copy"></i> Copy Content
                    </div>
                    <div class="context-menu-item" data-action="archive">
                        <i class="fas fa-archive"></i> Archive
                    </div>
                    <div class="context-menu-item delete" data-action="delete">
                        <i class="fas fa-trash"></i> Delete
                    </div>
                `;
                
                document.body.appendChild(contextMenu);
                
                // Handle menu item clicks
                contextMenu.querySelectorAll('.context-menu-item').forEach(item => {
                    item.addEventListener('click', function() {
                        const action = this.dataset.action;
                        contextMenu.remove();
                        
                        switch(action) {
                            case 'view':
                                viewFileContent(fileId, fileName);
                                break;
                            case 'copy':
                                copyFileContent(fileId);
                                break;
                            case 'archive':
                                if (confirm(`Are you sure you want to archive "${fileName}"?`)) {
                                    archiveFile(fileId);
                                }
                                break;
                            case 'delete':
                                if (confirm(`Are you sure you want to delete "${fileName}"? This action cannot be undone.`)) {
                                    deleteFile(fileId);
                                }
                                break;
                        }
                    });
                });
                
                // Close menu when clicking outside
                const closeMenu = (e) => {
                    if (contextMenu && !contextMenu.contains(e.target)) {
                        contextMenu.remove();
                        contextMenu = null;
                        document.removeEventListener('click', closeMenu);
                    }
                };
                
                setTimeout(() => {
                    document.addEventListener('click', closeMenu);
                }, 0);
            };
            
            // View file content in the viewer panel
            const viewFileContent = (fileId, fileName) => {
                const projectId = getCurrentProjectId();
                if (!projectId) {
                    console.error('[ArtifactsLoader] No project ID available for viewing file');
                    showToast('Error: No project ID available', 'error');
                    return;
                }
                
                console.log('[ArtifactsLoader] Viewing file:', { fileId, fileName, projectId });
                
                // Ensure artifacts panel is open and documents tab is active
                const artifactsPanel = document.getElementById('artifacts-panel');
                const isArtifactsPanelOpen = artifactsPanel && artifactsPanel.classList.contains('expanded');
                
                if (!isArtifactsPanelOpen) {
                    console.log('[ArtifactsLoader] Opening artifacts panel');
                    if (window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function') {
                        window.ArtifactsPanel.toggle(true); // Force open
                    }
                }
                
                // Switch to filebrowser tab instead of documents
                const filebrowserTab = document.querySelector('[data-tab="filebrowser"]');
                if (filebrowserTab && !filebrowserTab.classList.contains('active')) {
                    console.log('[ArtifactsLoader] Switching to filebrowser tab');
                    
                    // Try multiple methods to switch tab
                    if (window.switchTab) {
                        window.switchTab('filebrowser');
                    } else {
                        // Fallback: manually trigger tab switch
                        console.log('[ArtifactsLoader] Using fallback tab switch method');
                        
                        // Remove active class from all tabs and panes
                        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
                        document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
                        
                        // Activate filebrowser tab
                        filebrowserTab.classList.add('active');
                        const filebrowserPane = document.getElementById('filebrowser');
                        if (filebrowserPane) {
                            filebrowserPane.classList.add('active');
                        }
                    }
                }
                
                // Close any open version drawer when viewing a different file
                const existingDrawer = document.querySelector('.version-drawer');
                if (existingDrawer && existingDrawer.dataset.fileId !== String(fileId)) {
                    window.closeVersionDrawer();
                }
                
                fetch(`/projects/${projectId}/api/files/${fileId}/content/`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => response.json())
                .then(data => {
                    // Switch to viewer mode
                    fileBrowserMain.style.display = 'none';
                    fileBrowserViewer.style.display = 'flex';
                    
                    // Set title with inline edit capability
                    viewerTitle.innerHTML = `
                        <span id="viewer-title-text" title="${data.name || fileName}">${data.name || fileName}</span>
                        <button id="viewer-title-edit" title="Edit name">
                            <i class="fas fa-pencil" style="font-size: 12px;"></i>
                        </button>
                    `;
                    
                    // Add inline edit functionality
                    const titleEditBtn = document.getElementById('viewer-title-edit');
                    const titleText = document.getElementById('viewer-title-text');
                    
                    if (titleEditBtn && titleText) {
                        titleEditBtn.addEventListener('click', function(e) {
                            e.stopPropagation();
                            
                            // Get current name
                            const currentName = titleText.textContent;
                            
                            // Create input field
                            const input = document.createElement('input');
                            input.type = 'text';
                            input.value = currentName;
                            input.style.cssText = `
                                background: #1a1a1a;
                                border: 1px solid #333;
                                border-radius: 4px;
                                color: #e2e8f0;
                                padding: 4px 8px;
                                font-size: 16px;
                                font-weight: 600;
                                width: 300px;
                            `;
                            
                            // Replace text with input
                            titleText.style.display = 'none';
                            titleEditBtn.style.display = 'none';
                            viewerTitle.insertBefore(input, titleText);
                            input.focus();
                            input.select();
                            
                            // Handle save
                            const saveTitle = async () => {
                                const newName = input.value.trim();
                                if (newName && newName !== currentName) {
                                    try {
                                        const response = await fetch(`/projects/${projectId}/api/files/${fileId}/rename/`, {
                                            method: 'POST',
                                            headers: {
                                                'Content-Type': 'application/json',
                                                'X-CSRFToken': getCsrfToken(),
                                            },
                                            body: JSON.stringify({ name: newName })
                                        });
                                        
                                        const result = await response.json();
                                        if (result.success) {
                                            titleText.textContent = newName;
                                            window.currentFileData.fileName = newName;
                                            showToast('File renamed successfully', 'success');
                                            // Refresh file list
                                            fetchFiles(currentPage);
                                        } else {
                                            showToast('Failed to rename file: ' + (result.error || 'Unknown error'), 'error');
                                        }
                                    } catch (error) {
                                        console.error('Error renaming file:', error);
                                        showToast('Failed to rename file', 'error');
                                    }
                                }
                                
                                // Restore original view
                                input.remove();
                                titleText.style.display = '';
                                titleEditBtn.style.display = '';
                            };
                            
                            // Handle cancel
                            const cancelEdit = () => {
                                input.remove();
                                titleText.style.display = '';
                                titleEditBtn.style.display = '';
                            };
                            
                            // Event listeners
                            input.addEventListener('blur', saveTitle);
                            input.addEventListener('keydown', function(e) {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    saveTitle();
                                } else if (e.key === 'Escape') {
                                    e.preventDefault();
                                    cancelEdit();
                                }
                            });
                        });
                    }
                    
                    // Reset editor state
                    if (window.currentWysiwygEditor) {
                        window.currentWysiwygEditor = null;
                    }
                    window.currentFileData = {
                        fileId: fileId,
                        fileName: data.name || fileName,
                        content: data.content || '',
                        type: data.type
                    };
                    
                    // Render markdown content
                    const content = data.content || 'No content available';

                    console.log('[ArtifactsLoader] Getting Viewer Actions');
                    
                    // Create compact action buttons
                    const viewerActions = document.getElementById('viewer-actions');

                    console.log('[ArtifactsLoader] Getting Viewer Actions', viewerActions);

                    if (viewerActions) {
                        // Clear existing buttons
                        viewerActions.innerHTML = '';

                        console.log('[ArtifactsLoader] Viewer Actions', viewerActions);
                        
                        // Common button style
                        const buttonStyle = `
                            background: transparent;
                            border: none;
                            color: #9ca3af;
                            cursor: pointer;
                            padding: 6px;
                            font-size: 14px;
                            transition: all 0.2s;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        `;
                        
                        console.log('[ArtifactsLoader] Button Style', buttonStyle);

                        // Edit button with full text
                        const editButton = document.createElement('button');
                        editButton.id = 'viewer-edit';
                        editButton.style.cssText = buttonStyle + 'padding: 6px; gap: 6px;';
                        editButton.innerHTML = '<i class="fas fa-edit"></i>';
                        editButton.title = 'Edit full text';
                        editButton.onmouseover = function() { this.style.color = '#e2e8f0'; };
                        editButton.onmouseout = function() { this.style.color = '#9ca3af'; };
                        editButton.addEventListener('click', () => enableEditMode());
                        
                        // Copy button
                        const copyButton = document.createElement('button');
                        copyButton.id = 'viewer-copy';
                        copyButton.style.cssText = buttonStyle;
                        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
                        copyButton.title = 'Copy';
                        copyButton.onmouseover = function() { this.style.color = '#e2e8f0'; };
                        copyButton.onmouseout = function() { this.style.color = '#9ca3af'; };
                        copyButton.addEventListener('click', () => {
                            if (window.currentFileData && window.currentFileData.content) {
                                ArtifactsLoader.copyToClipboard(window.currentFileData.content, 'Markdown content');
                            }
                        });
                        
                        // Options dropdown button
                        const optionsButton = document.createElement('button');
                        optionsButton.id = 'viewer-options';
                        optionsButton.style.cssText = buttonStyle + 'position: relative;';
                        optionsButton.innerHTML = '<i class="fas fa-ellipsis-v"></i>';
                        optionsButton.title = 'More options';
                        optionsButton.onmouseover = function() { this.style.color = '#e2e8f0'; };
                        optionsButton.onmouseout = function() { this.style.color = '#9ca3af'; };
                        
                        // Create dropdown menu
                        const dropdownMenu = document.createElement('div');
                        dropdownMenu.id = 'viewer-options-dropdown';
                        dropdownMenu.style.cssText = `
                            position: absolute;
                            top: 100%;
                            right: 0;
                            background: #1a1a1a;
                            border: 1px solid #333;
                            border-radius: 6px;
                            min-width: 160px;
                            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                            display: none;
                            z-index: 1000;
                            margin-top: 4px;
                        `;
                        
                        // Download option with submenu
                        const downloadOption = document.createElement('div');
                        downloadOption.style.cssText = `
                            position: relative;
                        `;
                        
                        const downloadButton = document.createElement('button');
                        downloadButton.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        downloadButton.innerHTML = '<span><i class="fas fa-download"></i> Download</span>';
                        downloadButton.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        downloadButton.onmouseout = function() { this.style.background = 'transparent'; };
                        
                        // Create download format submenu
                        const downloadSubmenu = document.createElement('div');
                        downloadSubmenu.style.cssText = `
                            position: absolute;
                            right: 100%;
                            top: 0;
                            background: #1a1a1a;
                            border: 1px solid #333;
                            border-radius: 6px;
                            min-width: 120px;
                            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                            display: none;
                            margin-right: 4px;
                        `;
                        
                        // PDF option
                        const pdfOption = document.createElement('button');
                        pdfOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        pdfOption.innerHTML = '<i class="fas fa-file-pdf"></i> PDF';
                        pdfOption.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        pdfOption.onmouseout = function() { this.style.background = 'transparent'; };
                        pdfOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            if (window.currentFileData) {
                                const title = window.currentFileData.fileName || 'Document';
                                const content = window.currentFileData.content || '';
                                ArtifactsLoader.downloadFileAsPDF(projectId, title, content);
                            }
                        });
                        
                        // DOC option
                        const docOption = document.createElement('button');
                        docOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        docOption.innerHTML = '<i class="fas fa-file-word"></i> DOC';
                        docOption.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        docOption.onmouseout = function() { this.style.background = 'transparent'; };
                        docOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            if (window.currentFileData) {
                                const fileName = window.currentFileData.fileName || 'document';
                                const content = window.currentFileData.content || '';
                                ArtifactsLoader.downloadAsDoc(fileName, content);
                            }
                        });
                        
                        // Markdown option
                        const mdOption = document.createElement('button');
                        mdOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        mdOption.innerHTML = '<i class="fas fa-file-code"></i> Markdown';
                        mdOption.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        mdOption.onmouseout = function() { this.style.background = 'transparent'; };
                        mdOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            if (window.currentFileData) {
                                const fileName = window.currentFileData.fileName || 'document';
                                const content = window.currentFileData.content || '';
                                ArtifactsLoader.downloadAsMarkdown(fileName, content);
                            }
                        });
                        
                        downloadSubmenu.appendChild(pdfOption);
                        downloadSubmenu.appendChild(docOption);
                        downloadSubmenu.appendChild(mdOption);
                        
                        downloadOption.appendChild(downloadButton);
                        downloadOption.appendChild(downloadSubmenu);
                        
                        // Show submenu on hover - use the parent div for better hover handling
                        downloadOption.addEventListener('mouseenter', () => {
                            downloadSubmenu.style.display = 'block';
                        });
                        
                        downloadOption.addEventListener('mouseleave', () => {
                            downloadSubmenu.style.display = 'none';
                        });
                        
                        // Delete option
                        const deleteOption = document.createElement('button');
                        deleteOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #ef4444;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        deleteOption.innerHTML = '<i class="fas fa-trash"></i> Delete';
                        deleteOption.onmouseover = function() { this.style.background = 'rgba(239, 68, 68, 0.1)'; };
                        deleteOption.onmouseout = function() { this.style.background = 'transparent'; };
                        deleteOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            const fileName = data.name || window.currentFileData.fileName;
                            if (confirm(`Are you sure you want to delete "${fileName}"? This action cannot be undone.`)) {
                                deleteFile(fileId);
                            }
                        });
                        
                        // Version history option
                        const versionOption = document.createElement('button');
                        versionOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        versionOption.innerHTML = '<i class="fas fa-history"></i> Version History';
                        versionOption.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        versionOption.onmouseout = function() { this.style.background = 'transparent'; };
                        versionOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            const currentFileId = window.currentFileData ? window.currentFileData.fileId : fileId;
                            console.log('[VersionButton] Clicked for fileId:', currentFileId);
                            showVersionHistory(currentFileId);
                        });
                        
                        dropdownMenu.appendChild(versionOption);
                        dropdownMenu.appendChild(downloadOption);
                        dropdownMenu.appendChild(deleteOption);
                        
                        // Toggle dropdown
                        optionsButton.addEventListener('click', (e) => {
                            e.stopPropagation();
                            const isOpen = dropdownMenu.style.display === 'block';
                            dropdownMenu.style.display = isOpen ? 'none' : 'block';
                        });
                        
                        // Close dropdown when clicking outside
                        document.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                        });
                        
                        // Create wrapper for options button with dropdown
                        const optionsWrapper = document.createElement('div');
                        optionsWrapper.style.cssText = 'position: relative; display: flex;';
                        optionsWrapper.appendChild(optionsButton);
                        optionsWrapper.appendChild(dropdownMenu);
                        
                        // Append buttons to actions container
                        viewerActions.appendChild(editButton);
                        viewerActions.appendChild(copyButton);
                        viewerActions.appendChild(optionsWrapper);
                        
                        // Ensure viewer actions are always visible
                        viewerActions.style.display = 'flex';
                        console.log('[ArtifactsLoader] Viewer actions display set to flex');
                    }
                    
                    // Configure marked if not already configured
                    if (typeof marked !== 'undefined' && !window.markedConfigured) {
                        marked.setOptions({
                            gfm: true,          // Enable GitHub Flavored Markdown
                            breaks: true,       // Add <br> on line breaks
                            headerIds: true,    // Add IDs to headers
                            mangle: false,      // Don't mangle header IDs
                            tables: true,       // Enable table support
                            smartLists: true,   // Improve behavior of lists
                            xhtml: false        // Don't use XHTML compatible tags
                        });
                        window.markedConfigured = true;
                    }
                    
                    // Check if content appears to be markdown by looking for common markdown patterns
                    const isMarkdownContent = (content) => {
                        if (!content) return false;
                        // Check for headers, lists, code blocks, tables, links, or emphasis
                        return /^#{1,6}\s|^\*\s|^\-\s|^\d+\.\s|```|^\|.*\|$|\[.*\]\(.*\)|\*\*.*\*\*|\*.*\*/m.test(content);
                    };
                    
                    // Always render as markdown if it contains markdown patterns or is a known markdown type
                    const knownMarkdownTypes = ['prd', 'implementation', 'design', 'analysis', 'documentation', 'readme'];
                    if (knownMarkdownTypes.includes(data.type) || isMarkdownContent(content)) {
                        // Use marked.js if available, otherwise basic rendering
                        if (typeof marked !== 'undefined') {
                            viewerMarkdown.innerHTML = marked.parse(content);
                        } else {
                            // Simple markdown rendering
                            let renderedContent = escapeHtml(content);
                            
                            // Convert markdown to HTML (basic conversion)
                            // Headers
                            renderedContent = renderedContent.replace(/^#### (.*$)/gim, '<h4>$1</h4>');
                            renderedContent = renderedContent.replace(/^### (.*$)/gim, '<h3>$1</h3>');
                            renderedContent = renderedContent.replace(/^## (.*$)/gim, '<h2>$1</h2>');
                            renderedContent = renderedContent.replace(/^# (.*$)/gim, '<h1>$1</h1>');
                            
                            // Bold and italic
                            renderedContent = renderedContent.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
                            renderedContent = renderedContent.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                            renderedContent = renderedContent.replace(/\*(.*?)\*/g, '<em>$1</em>');
                            
                            // Links
                            renderedContent = renderedContent.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
                            
                            // Lists
                            renderedContent = renderedContent.replace(/^\* (.+)$/gim, '<li>$1</li>');
                            renderedContent = renderedContent.replace(/^\d+\. (.+)$/gim, '<li>$1</li>');
                            
                            // Wrap consecutive list items
                            renderedContent = renderedContent.replace(/(<li>.*?<\/li>\s*)+/gs, function(match) {
                                return '<ul>' + match + '</ul>';
                            });
                            
                            // Code blocks
                            renderedContent = renderedContent.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
                            renderedContent = renderedContent.replace(/`([^`]+)`/g, '<code>$1</code>');
                            
                            // Paragraphs
                            renderedContent = renderedContent.split('\n\n').map(para => {
                                if (para.trim() && !para.startsWith('<') && !para.match(/^[\*\d]/)) {
                                    return '<p>' + para + '</p>';
                                }
                                return para;
                            }).join('\n');
                            
                            viewerMarkdown.innerHTML = renderedContent;
                        }
                    } else {
                        // For other file types, display as preformatted text
                        viewerMarkdown.innerHTML = '<pre style="white-space: pre-wrap; word-wrap: break-word;">' + escapeHtml(content) + '</pre>';
                    }
                    
                    // File info is now stored in window.currentFileData and used by action buttons
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error loading file content:', error);
                    showToast('Failed to load file content', 'error');
                });
            };
            window.viewFileContent = viewFileContent;
            
            // Auto-save functionality
            let autoSaveTimer = null;
            let hasUnsavedChanges = false;
            
            // Function to perform auto-save
            const performAutoSave = async () => {
                if (hasUnsavedChanges && window.currentWysiwygEditor) {
                    console.log('[AutoSave] Performing auto-save...');
                    await saveFileContent(true); // true indicates auto-save
                    hasUnsavedChanges = false;
                }
            };
            
            // Start auto-save timer
            const startAutoSave = () => {
                // Clear existing timer
                if (autoSaveTimer) {
                    clearInterval(autoSaveTimer);
                }
                
                // Set up auto-save every 15 seconds
                autoSaveTimer = setInterval(performAutoSave, 15000);
            };
            
            // Stop auto-save timer
            const stopAutoSave = () => {
                if (autoSaveTimer) {
                    clearInterval(autoSaveTimer);
                    autoSaveTimer = null;
                }
            };
            
            // Create auto-save indicator
            const createAutoSaveIndicator = () => {
                const indicator = document.createElement('span');
                indicator.id = 'auto-save-indicator';
                indicator.style.cssText = `
                    display: none;
                    margin-left: 15px;
                    font-size: 14px;
                    color: #10b981;
                    font-weight: normal;
                `;
                
                // Add to viewer header
                const viewerTitle = document.getElementById('viewer-title');
                if (viewerTitle && viewerTitle.parentElement) {
                    viewerTitle.parentElement.appendChild(indicator);
                }
                
                return indicator;
            };
            
            // Enable edit mode with WYSIWYG editor
            const enableEditMode = () => {
                if (!window.currentFileData) return;
                
                const viewerMarkdown = document.getElementById('viewer-markdown');
                const viewerContent = document.querySelector('.viewer-content');
                const fileBrowserViewer = document.getElementById('filebrowser-viewer');
                
                if (!viewerMarkdown || !fileBrowserViewer) return;
                
                // Create container for WYSIWYG editor
                const editorContainer = document.createElement('div');
                editorContainer.id = 'wysiwyg-editor';
                editorContainer.style.cssText = 'flex: 1; height: calc(100% - 60px); position: relative;';
                
                // Hide the viewer-content to avoid nested scrolling
                if (viewerContent) {
                    viewerContent.style.display = 'none';
                }
                
                // Insert editor directly in the viewer, after header
                const viewerHeader = fileBrowserViewer.querySelector('.viewer-header');
                if (viewerHeader && viewerHeader.nextSibling) {
                    fileBrowserViewer.insertBefore(editorContainer, viewerHeader.nextSibling);
                } else {
                    fileBrowserViewer.appendChild(editorContainer);
                }
                
                // Load Jodit editor if not already loaded
                if (!window.Jodit) {
                    // Load Jodit CSS
                    const joditCss = document.createElement('link');
                    joditCss.rel = 'stylesheet';
                    joditCss.href = 'https://unpkg.com/jodit@3.24.9/build/jodit.min.css';
                    document.head.appendChild(joditCss);
                    
                    // Load Jodit JS
                    const joditScript = document.createElement('script');
                    joditScript.src = 'https://unpkg.com/jodit@3.24.9/build/jodit.min.js';
                    joditScript.onload = () => {
                        setTimeout(() => initializeWysiwygEditor(), 100);
                    };
                    document.head.appendChild(joditScript);
                } else {
                    // Initialize editor immediately
                    initializeWysiwygEditor();
                }
                
                // Hide all viewer buttons
                const editButton = document.getElementById('viewer-edit');
                const copyButton = document.getElementById('viewer-copy');
                const versionButton = document.getElementById('viewer-versions');
                const optionsButton = document.getElementById('viewer-options');
                
                if (editButton) editButton.style.display = 'none';
                if (copyButton) copyButton.style.display = 'none';
                if (versionButton) versionButton.style.display = 'none';
                if (optionsButton) optionsButton.style.display = 'none';
                
                // Add save and cancel buttons
                let saveButton = document.getElementById('viewer-save');
                let cancelButton = document.getElementById('viewer-cancel');
                
                if (!saveButton) {
                    saveButton = document.createElement('button');
                    saveButton.id = 'viewer-save';
                    saveButton.className = 'btn btn-sm';
                    saveButton.style = 'padding: 8px 16px; background: #10b981; color: white; border: none; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 6px;';
                    saveButton.innerHTML = '<i class="fas fa-save"></i> Save';
                    saveButton.title = 'Save changes';
                    saveButton.addEventListener('click', () => saveFileContent());
                    const viewerActions = document.getElementById('viewer-actions');
                    if (viewerActions) viewerActions.appendChild(saveButton);
                }
                
                if (!cancelButton) {
                    cancelButton = document.createElement('button');
                    cancelButton.id = 'viewer-cancel';
                    cancelButton.className = 'btn btn-sm';
                    cancelButton.style = 'padding: 8px 16px; background: #6b7280; color: white; border: none; border-radius: 6px; cursor: pointer; margin-left: 10px; display: flex; align-items: center; gap: 6px;';
                    cancelButton.innerHTML = '<i class="fas fa-times"></i> Cancel';
                    cancelButton.title = 'Cancel editing';
                    cancelButton.addEventListener('click', () => cancelEditMode());
                    if (viewerActions) viewerActions.appendChild(cancelButton);
                }
                
                saveButton.style.display = 'inline-block';
                cancelButton.style.display = 'inline-block';
            };
            
            // Initialize the WYSIWYG editor
            const initializeWysiwygEditor = () => {
                const editorContainer = document.getElementById('wysiwyg-editor');
                if (!editorContainer) return;
                
                // Clear the container
                editorContainer.innerHTML = '';
                
                // Create textarea for Jodit
                const textarea = document.createElement('textarea');
                textarea.id = 'jodit-editor';
                editorContainer.appendChild(textarea);
                
                // Convert markdown to HTML
                let initialHTML = window.currentFileData.content;
                if (window.marked) {
                    marked.setOptions({
                        gfm: true,
                        breaks: true,
                        tables: true
                    });
                    initialHTML = marked.parse(window.currentFileData.content);
                }
                
                // Calculate height to fill the entire viewer area
                const viewerContainer = document.getElementById('filebrowser-viewer');
                const viewerHeader = viewerContainer ? viewerContainer.querySelector('.viewer-header') : null;
                const headerHeight = viewerHeader ? viewerHeader.offsetHeight : 60;
                // Subtract header height and some padding
                const viewerHeight = viewerContainer ? viewerContainer.offsetHeight - headerHeight - 20 : 600;
                
                // Initialize Jodit with dark theme
                try {
                    window.currentWysiwygEditor = Jodit.make('#jodit-editor', {
                    theme: 'dark',
                    height: '100%',
                    minHeight: 400,
                    toolbarSticky: true,
                    toolbarStickyOffset: 0,
                    showCharsCounter: false,
                    showWordsCounter: false,
                    showXPathInStatusbar: false,
                    // Add keyboard shortcuts
                    hotkeys: {
                        'ctrl+s,cmd+s': function(editor) {
                            saveFileContent();
                            return false; // Prevent default browser save
                        }
                    },
                    buttons: [
                        'bold', 'italic', 'underline', 'strikethrough', '|',
                        'ul', 'ol', '|',
                        'font', 'fontsize', 'paragraph', '|',
                        'table', 'link', 'image', '|',
                        'align', '|',
                        'undo', 'redo', '|',
                        'eraser', 'fullsize'
                    ],
                    buttonsMD: [
                        'bold', 'italic', 'underline', '|',
                        'ul', 'ol', '|',
                        'table', 'link', '|',
                        'dots'
                    ],
                    buttonsXS: [
                        'bold', 'italic', '|',
                        'ul', 'ol', '|',
                        'dots'
                    ],
                    style: {
                        background: '#1a1a1a',
                        color: '#e2e8f0'
                    },
                    editorCssClass: 'dark-editor',
                    toolbarAdaptive: false,
                    enter: 'p',
                    defaultMode: Jodit.MODE_WYSIWYG,
                    useSplitMode: false,
                    colors: {
                        greyscale: ['#000000', '#434343', '#666666', '#999999', '#B7B7B7', '#CCCCCC', '#D9D9D9', '#EFEFEF', '#F3F3F3', '#FFFFFF'],
                        palette: ['#8B5CF6', '#60A5FA', '#10B981', '#F59E0B', '#EF4444', '#EC4899', '#8B5CF6', '#3B82F6', '#06B6D4', '#84CC16']
                    },
                    controls: {
                        font: {
                            list: {
                                "'Open Sans', sans-serif": 'Open Sans',
                                'Helvetica, sans-serif': 'Helvetica',
                                'Arial, sans-serif': 'Arial',
                                'Georgia, serif': 'Georgia',
                                'Impact, sans-serif': 'Impact',
                                'Tahoma, sans-serif': 'Tahoma',
                                'Verdana, sans-serif': 'Verdana'
                            }
                        }
                    },
                    events: {
                        afterInit: function(editor) {
                            // Ensure text color persists
                            editor.editor.style.color = '#e2e8f0';
                            editor.editor.style.backgroundColor = '#1a1a1a';
                            
                            // Also set default paragraph style
                            const style = editor.createInside.element('style');
                            style.innerHTML = `
                                * { color: #e2e8f0 !important; }
                                p { color: #e2e8f0 !important; }
                                div { color: #e2e8f0 !important; }
                                span { color: #e2e8f0 !important; }
                            `;
                            editor.editor.appendChild(style);
                        },
                        change: function() {
                            // Mark as having unsaved changes
                            hasUnsavedChanges = true;
                            // Keep text color on change
                            const editor = this.editor;
                            if (editor) {
                                const walker = document.createTreeWalker(
                                    editor,
                                    NodeFilter.SHOW_ELEMENT,
                                    null,
                                    false
                                );
                                
                                let node;
                                while (node = walker.nextNode()) {
                                    if (!node.style.color || node.style.color === '') {
                                        node.style.color = '#e2e8f0';
                                    }
                                }
                            }
                        },
                        beforeEnter: function() {
                            // Ensure new paragraphs have the right color
                            const selection = this.selection;
                            if (selection.current()) {
                                const current = selection.current();
                                if (current && current.style) {
                                    current.style.color = '#e2e8f0';
                                }
                            }
                        }
                    }
                });
                } catch (error) {
                    console.error('[ArtifactsLoader] Error initializing Jodit editor:', error);
                    if (error.message && error.message.includes('plugin')) {
                        showToast('Editor initialization error: ' + error.message, 'error');
                    } else {
                        showToast('Failed to initialize editor', 'error');
                    }
                    // Fallback to textarea
                    const fallbackTextarea = document.createElement('textarea');
                    fallbackTextarea.id = 'fallback-editor';
                    fallbackTextarea.className = 'artifact-editor';
                    fallbackTextarea.value = window.currentFileData.content;
                    fallbackTextarea.style.cssText = 'width: 100%; height: ' + viewerHeight + 'px; background: #1a1a1a; color: #e2e8f0; border: 1px solid #333; padding: 20px; font-family: monospace;';
                    editorContainer.innerHTML = '';
                    editorContainer.appendChild(fallbackTextarea);
                    window.currentWysiwygEditor = {
                        value: fallbackTextarea.value,
                        get value() { return fallbackTextarea.value; },
                        set value(val) { fallbackTextarea.value = val; }
                    };
                    return;
                }
                
                // Set initial content
                window.currentWysiwygEditor.value = initialHTML;
                
                // Start auto-save timer
                startAutoSave();
                console.log('[AutoSave] Auto-save timer started');
                
                // Reset unsaved changes flag
                hasUnsavedChanges = false;
                
                // Force text color after content is set
                setTimeout(() => {
                    const editorBody = window.currentWysiwygEditor.editor;
                    if (editorBody) {
                        editorBody.style.color = '#e2e8f0';
                        // Apply color to all existing elements
                        const allElements = editorBody.querySelectorAll('*');
                        allElements.forEach(el => {
                            if (!el.style.color || el.style.color === '') {
                                el.style.color = '#e2e8f0';
                            }
                        });
                    }
                }, 100);
                
                // Apply custom dark theme styles
                const style = document.createElement('style');
                style.textContent = `
                    /* Jodit Dark Theme Overrides */
                    .jodit-container:not(.jodit_inline) {
                        border: 1px solid #333 !important;
                        background: #1a1a1a !important;
                        height: 100% !important;
                    }
                    
                    .jodit-toolbar__box {
                        background: #2a2a2a !important;
                        border-bottom: 1px solid #333 !important;
                    }
                    
                    .jodit-toolbar-button {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-toolbar-button:hover {
                        background: #333 !important;
                    }
                    
                    .jodit-toolbar-button:active,
                    .jodit-toolbar-button[aria-pressed="true"] {
                        background: #8b5cf6 !important;
                    }
                    
                    .jodit-wysiwyg {
                        background: #1a1a1a !important;
                        color: #e2e8f0 !important;
                        padding: 20px !important;
                        min-height: calc(100% - 60px) !important;
                        line-height: 1.6 !important;
                    }
                    
                    /* Fix list formatting */
                    .jodit-wysiwyg ul,
                    .jodit-wysiwyg ol {
                        margin: 1em 0 !important;
                        padding-left: 2em !important;
                        line-height: 1.6 !important;
                    }
                    
                    .jodit-wysiwyg li {
                        margin: 0.5em 0 !important;
                        line-height: 1.6 !important;
                    }
                    
                    /* Fix paragraph spacing */
                    .jodit-wysiwyg p {
                        margin: 1em 0 !important;
                        line-height: 1.6 !important;
                    }
                    
                    /* Fix heading spacing */
                    .jodit-wysiwyg h1,
                    .jodit-wysiwyg h2,
                    .jodit-wysiwyg h3,
                    .jodit-wysiwyg h4,
                    .jodit-wysiwyg h5,
                    .jodit-wysiwyg h6 {
                        margin-top: 1.5em !important;
                        margin-bottom: 0.5em !important;
                        line-height: 1.3 !important;
                    }
                    
                    /* First heading should not have top margin */
                    .jodit-wysiwyg > h1:first-child,
                    .jodit-wysiwyg > h2:first-child,
                    .jodit-wysiwyg > h3:first-child {
                        margin-top: 0 !important;
                    }
                    
                    .jodit-wysiwyg,
                    .jodit-wysiwyg * {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg p,
                    .jodit-wysiwyg div,
                    .jodit-wysiwyg span {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg h1,
                    .jodit-wysiwyg h2,
                    .jodit-wysiwyg h3,
                    .jodit-wysiwyg h4,
                    .jodit-wysiwyg h5,
                    .jodit-wysiwyg h6 {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg table {
                        border-collapse: collapse !important;
                        width: 100% !important;
                        margin: 1.5em 0 !important;
                    }
                    
                    .jodit-wysiwyg table td,
                    .jodit-wysiwyg table th {
                        border: 1px solid #444 !important;
                        padding: 10px 15px !important;
                        color: #e2e8f0 !important;
                        line-height: 1.5 !important;
                        vertical-align: top !important;
                    }
                    
                    .jodit-wysiwyg table th {
                        background: #2a2a2a !important;
                        font-weight: bold !important;
                    }
                    
                    .jodit-wysiwyg blockquote {
                        border-left: 4px solid #8b5cf6 !important;
                        background: rgba(139, 92, 246, 0.1) !important;
                        padding: 10px 20px !important;
                        margin: 10px 0 !important;
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg pre {
                        background: #0a0a0a !important;
                        border: 1px solid #333 !important;
                        border-radius: 4px !important;
                        padding: 1em !important;
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg code {
                        background: #2a2a2a !important;
                        color: #e2e8f0 !important;
                        padding: 0.2em 0.4em !important;
                        border-radius: 3px !important;
                    }
                    
                    .jodit-wysiwyg a {
                        color: #60a5fa !important;
                    }
                    
                    /* Status bar */
                    .jodit-status-bar {
                        background: #2a2a2a !important;
                        border-top: 1px solid #333 !important;
                        color: #9ca3af !important;
                    }
                    
                    /* Popup and dropdown styles */
                    .jodit-popup__content {
                        background: #2a2a2a !important;
                        border: 1px solid #444 !important;
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-dropdown__content {
                        background: #2a2a2a !important;
                        border: 1px solid #444 !important;
                    }
                    
                    .jodit-dropdown__item {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-dropdown__item:hover {
                        background: #333 !important;
                    }
                    
                    /* Table selector */
                    .jodit-toolbar-button__button[aria-controls*="table"] {
                        color: #e2e8f0 !important;
                    }
                    
                    /* Color picker */
                    .jodit-color-picker__box {
                        background: #2a2a2a !important;
                        border: 1px solid #444 !important;
                    }
                    
                    /* Icons */
                    .jodit-icon {
                        fill: #e2e8f0 !important;
                    }
                    
                    .jodit-toolbar-button:hover .jodit-icon {
                        fill: #fff !important;
                    }
                    
                    .jodit-toolbar-button[aria-pressed="true"] .jodit-icon {
                        fill: #fff !important;
                    }
                `;
                document.head.appendChild(style);
                
                // Focus the editor
                window.currentWysiwygEditor.focus();
                
                // Additional style injection to ensure visibility
                const additionalStyles = document.createElement('style');
                additionalStyles.textContent = `
                    .jodit-wysiwyg[contenteditable="true"] {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg[contenteditable="true"] * {
                        color: inherit !important;
                    }
                    
                    /* Force text color for all possible elements */
                    .jodit-wysiwyg p,
                    .jodit-wysiwyg div,
                    .jodit-wysiwyg span,
                    .jodit-wysiwyg h1,
                    .jodit-wysiwyg h2,
                    .jodit-wysiwyg h3,
                    .jodit-wysiwyg h4,
                    .jodit-wysiwyg h5,
                    .jodit-wysiwyg h6,
                    .jodit-wysiwyg li,
                    .jodit-wysiwyg td,
                    .jodit-wysiwyg th,
                    .jodit-wysiwyg a,
                    .jodit-wysiwyg strong,
                    .jodit-wysiwyg em,
                    .jodit-wysiwyg u,
                    .jodit-wysiwyg s {
                        color: #e2e8f0 !important;
                    }
                `;
                document.head.appendChild(additionalStyles);
            };
            
            
            // Save file content
            const saveFileContent = async (isAutoSave = false) => {
                if (!window.currentWysiwygEditor || !window.currentFileData) {
                    console.error('[ArtifactsLoader] Missing editor or file data');
                    return;
                }
                
                // Get project ID
                const projectId = getCurrentProjectId();
                if (!projectId) {
                    console.error('[ArtifactsLoader] No project ID available');
                    showToast('Error: No project ID available', 'error');
                    return;
                }
                
                // Show saving indicator
                const saveButton = document.getElementById('viewer-save');
                let originalText = saveButton ? saveButton.innerHTML : '';
                
                if (isAutoSave) {
                    // For auto-save, show a subtle indicator
                    const autoSaveIndicator = document.getElementById('auto-save-indicator') || createAutoSaveIndicator();
                    autoSaveIndicator.style.display = 'inline-block';
                    autoSaveIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Auto-saving...';
                } else {
                    // For manual save, update the save button
                    if (saveButton) {
                        originalText = saveButton.innerHTML;
                        saveButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
                        saveButton.disabled = true;
                    }
                }
                
                try {
                    // Get HTML content from Jodit editor
                    const htmlContent = window.currentWysiwygEditor.value;
                    
                    // Convert HTML back to markdown
                    let content = htmlContent;
                    
                    // Load Turndown if not available for better conversion
                    if (!window.TurndownService) {
                        // Load Turndown dynamically
                        await new Promise((resolve) => {
                            const script = document.createElement('script');
                            script.src = 'https://unpkg.com/turndown/dist/turndown.js';
                            script.onload = resolve;
                            document.head.appendChild(script);
                        });
                    }
                    
                    if (window.TurndownService) {
                        const turndownService = new TurndownService({
                            headingStyle: 'atx',
                            codeBlockStyle: 'fenced',
                            bulletListMarker: '-'
                        });
                        
                        // Add table support using the correct plugin format
                        turndownService.use(function(service) {
                            service.addRule('table', {
                                filter: 'table',
                                replacement: function(content, node) {
                                    // Convert HTML table back to markdown table
                                    const rows = Array.from(node.querySelectorAll('tr'));
                                    if (rows.length === 0) return '';
                                    
                                    let markdown = '';
                                    rows.forEach((row, index) => {
                                        const cells = Array.from(row.querySelectorAll('td, th'));
                                        markdown += '| ' + cells.map(cell => cell.textContent.trim()).join(' | ') + ' |\n';
                                        
                                        // Add separator after header row
                                        if (index === 0) {
                                            markdown += '|' + cells.map(() => '---').join('|') + '|\n';
                                        }
                                    });
                                    
                                    return '\n' + markdown + '\n';
                                }
                            });
                        });
                        
                        content = turndownService.turndown(htmlContent);
                    } else {
                        // Simple HTML to markdown conversion
                        content = htmlContent
                            .replace(/<h1[^>]*>(.*?)<\/h1>/gi, '# $1\n')
                            .replace(/<h2[^>]*>(.*?)<\/h2>/gi, '## $1\n')
                            .replace(/<h3[^>]*>(.*?)<\/h3>/gi, '### $1\n')
                            .replace(/<h4[^>]*>(.*?)<\/h4>/gi, '#### $1\n')
                            .replace(/<strong[^>]*>(.*?)<\/strong>/gi, '**$1**')
                            .replace(/<b[^>]*>(.*?)<\/b>/gi, '**$1**')
                            .replace(/<em[^>]*>(.*?)<\/em>/gi, '*$1*')
                            .replace(/<i[^>]*>(.*?)<\/i>/gi, '*$1*')
                            .replace(/<ul[^>]*>([\s\S]*?)<\/ul>/gi, function(match, content) {
                                return content.replace(/<li[^>]*>(.*?)<\/li>/gi, '- $1\n');
                            })
                            .replace(/<ol[^>]*>([\s\S]*?)<\/ol>/gi, function(match, content) {
                                let counter = 1;
                                return content.replace(/<li[^>]*>(.*?)<\/li>/gi, function(m, text) {
                                    return (counter++) + '. ' + text + '\n';
                                });
                            })
                            .replace(/<blockquote[^>]*>(.*?)<\/blockquote>/gi, '> $1\n')
                            .replace(/<br[^>]*>/gi, '\n')
                            .replace(/<p[^>]*>(.*?)<\/p>/gi, '$1\n\n')
                            .replace(/<[^>]+>/g, '')
                            .replace(/\n{3,}/g, '\n\n')
                            .trim();
                    }
                    
                    const { fileId, fileName, type } = window.currentFileData;
                    console.log('[ArtifactsLoader] Saving file:', { fileId, fileName, type, projectId });
                    
                    // Determine the correct API endpoint based on file type
                    let url, method, body;
                    
                    if (type === 'prd') {
                        url = `/projects/${projectId}/api/prd/?prd_name=${encodeURIComponent(fileName)}`;
                        method = 'POST';
                        body = JSON.stringify({ content: content });
                    } else if (type === 'implementation') {
                        url = `/projects/${projectId}/api/implementation/`;
                        method = 'POST';
                        body = JSON.stringify({ content: content });
                    } else {
                        // For other file types, use the generic files API
                        // The type should match the file_type in the model (e.g., 'design', 'test', 'other')
                        const fileType = type || 'other';
                        url = `/projects/${projectId}/api/files/?type=${fileType}&name=${encodeURIComponent(fileName)}`;
                        method = 'POST';
                        body = JSON.stringify({ content: content });
                    }
                    
                    console.log('[ArtifactsLoader] Request URL:', url);
                    console.log('[ArtifactsLoader] Request method:', method);
                    
                    const response = await fetch(url, {
                        method: method,
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        },
                        body: body
                    });
                    
                    console.log('[ArtifactsLoader] Response status:', response.status);
                    
                    let data;
                    try {
                        data = await response.json();
                        console.log('[ArtifactsLoader] Response data:', data);
                    } catch (e) {
                        console.error('[ArtifactsLoader] Failed to parse response:', e);
                        data = { success: false, error: 'Failed to parse server response' };
                    }
                    
                    if (data.success || response.ok) {
                        // Show toast with proper function
                        if (isAutoSave) {
                            // For auto-save, show subtle indicator
                            const autoSaveIndicator = document.getElementById('auto-save-indicator');
                            if (autoSaveIndicator) {
                                autoSaveIndicator.innerHTML = '<i class="fas fa-check"></i> Auto-saved';
                                setTimeout(() => {
                                    autoSaveIndicator.style.display = 'none';
                                }, 2000);
                            }
                            console.log('[AutoSave] File auto-saved successfully');
                        } else {
                            // For manual save, show toast
                            if (typeof showToast === 'function') {
                                showToast('File saved successfully', 'success');
                            } else if (window.showToast && typeof window.showToast === 'function') {
                                window.showToast('File saved successfully', 'success');
                            } else {
                                alert('File saved successfully');
                            }
                        }
                        window.currentFileData.content = content;
                        
                        // Also save the file ID if it was created
                        if (data.file_id) {
                            window.currentFileData.fileId = data.file_id;
                        }
                        
                        // Exit edit mode and refresh view (only for manual save)
                        if (!isAutoSave) {
                            cancelEditMode(true);
                        }
                    } else {
                        console.error('[ArtifactsLoader] Save error:', data);
                        const errorMsg = 'Failed to save file: ' + (data.error || 'Unknown error');
                        
                        if (isAutoSave) {
                            console.error('[AutoSave] Auto-save failed:', errorMsg);
                            const autoSaveIndicator = document.getElementById('auto-save-indicator');
                            if (autoSaveIndicator) {
                                autoSaveIndicator.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Auto-save failed';
                                autoSaveIndicator.style.color = '#ef4444';
                                setTimeout(() => {
                                    autoSaveIndicator.style.display = 'none';
                                    autoSaveIndicator.style.color = '';
                                }, 3000);
                            }
                        } else {
                            if (typeof showToast === 'function') {
                                showToast(errorMsg, 'error');
                            } else if (window.showToast && typeof window.showToast === 'function') {
                                window.showToast(errorMsg, 'error');
                            } else {
                                alert(errorMsg);
                            }
                        }
                    }
                } catch (error) {
                    console.error('[ArtifactsLoader] Error saving file:', error);
                    const errorMsg = 'Failed to save file: ' + error.message;
                    
                    if (isAutoSave) {
                        console.error('[AutoSave] Auto-save error:', error);
                        const autoSaveIndicator = document.getElementById('auto-save-indicator');
                        if (autoSaveIndicator) {
                            autoSaveIndicator.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Auto-save failed';
                            autoSaveIndicator.style.color = '#ef4444';
                            setTimeout(() => {
                                autoSaveIndicator.style.display = 'none';
                                autoSaveIndicator.style.color = '';
                            }, 3000);
                        }
                    } else {
                        if (typeof showToast === 'function') {
                            showToast(errorMsg, 'error');
                        } else if (window.showToast && typeof window.showToast === 'function') {
                            window.showToast(errorMsg, 'error');
                        } else {
                            alert(errorMsg);
                        }
                    }
                } finally {
                    if (!isAutoSave && saveButton) {
                        saveButton.innerHTML = originalText;
                        saveButton.disabled = false;
                    }
                }
            };
            
            // Cancel edit mode
            const cancelEditMode = (skipConfirm = false) => {
                if (!skipConfirm && window.currentWysiwygEditor && hasUnsavedChanges) {
                    if (!confirm('Are you sure you want to cancel? Any unsaved changes will be lost.')) {
                        return;
                    }
                }
                
                // Stop auto-save timer
                stopAutoSave();
                console.log('[AutoSave] Auto-save timer stopped');
                
                // Clear reference
                if (window.currentWysiwygEditor) {
                    window.currentWysiwygEditor = null;
                }
                
                // Remove the editor container
                const editorContainer = document.getElementById('wysiwyg-editor');
                if (editorContainer) {
                    editorContainer.remove();
                }
                
                // Show the viewer-content again
                const viewerContent = document.querySelector('.viewer-content');
                if (viewerContent) {
                    viewerContent.style.display = '';
                }
                
                // Hide save/cancel buttons
                const saveButton = document.getElementById('viewer-save');
                const cancelButton = document.getElementById('viewer-cancel');
                if (saveButton) saveButton.style.display = 'none';
                if (cancelButton) cancelButton.style.display = 'none';
                
                // Show original buttons
                const editButton = document.getElementById('viewer-edit');
                const copyButton = document.getElementById('viewer-copy');
                const versionButton = document.getElementById('viewer-versions');
                const optionsButton = document.getElementById('viewer-options');
                if (editButton) editButton.style.display = 'flex';
                if (copyButton) copyButton.style.display = 'flex';
                if (versionButton) versionButton.style.display = 'flex';
                if (optionsButton) optionsButton.style.display = 'flex';
                
                // Refresh the file view
                if (window.currentFileData) {
                    viewFileContent(window.currentFileData.fileId, window.currentFileData.fileName);
                }
            };
            
            // Show version history in side drawer
            const showVersionHistory = async (fileId) => {
                const projectId = getCurrentProjectId();
                if (!projectId || !fileId) {
                    showToast('Error: Missing project or file ID', 'error');
                    return;
                }
                
                // Check if drawer already exists for this file
                const existingDrawer = document.querySelector('.version-drawer');
                if (existingDrawer && existingDrawer.dataset.fileId === String(fileId)) {
                    // Drawer already open for this file, do nothing
                    return;
                } else if (existingDrawer) {
                    // Close existing drawer for different file
                    window.closeVersionDrawer();
                }
                
                try {
                    const response = await fetch(`/projects/${projectId}/api/files/${fileId}/versions/`, {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        }
                    });
                    
                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.error || 'Failed to load versions');
                    }
                    
                    console.log('[VersionHistory] API Response for file', fileId, ':', data);
                    
                    // Get filename from current file data
                    const fileName = window.currentFileData ? window.currentFileData.fileName : 'Unknown File';
                    
                    // Create version history drawer with fresh data
                    createVersionHistoryDrawer(fileId, fileName, data.versions || []);
                    
                } catch (error) {
                    console.error('[ArtifactsLoader] Error loading versions:', error);
                    showToast('Failed to load version history', 'error');
                }
            };
            
            // Create version history drawer
            const createVersionHistoryDrawer = (fileId, fileName, versions) => {
                console.log('[VersionDrawer] Creating drawer for file:', { fileId, fileName, versionCount: versions.length });
                
                // Remove existing drawer and overlay if any
                const existingDrawer = document.querySelector('.version-drawer');
                const existingOverlay = document.querySelector('.version-drawer-overlay');
                if (existingDrawer) {
                    existingDrawer.remove();
                }
                if (existingOverlay) {
                    existingOverlay.remove();
                }

                const drawer = document.createElement('div');
                drawer.className = 'version-drawer';
                
                // Group versions by date
                const versionsByDate = {};
                const today = new Date().toDateString();
                const yesterday = new Date(Date.now() - 86400000).toDateString();
                
                // Make sure we're using fresh version data
                const fileVersions = [...versions]; // Create a copy to avoid reference issues
                
                fileVersions.forEach(version => {
                    const versionDate = new Date(version.created_at);
                    const dateStr = versionDate.toDateString();
                    let groupLabel;
                    
                    if (dateStr === today) {
                        groupLabel = 'Today';
                    } else if (dateStr === yesterday) {
                        groupLabel = 'Yesterday';
                    } else {
                        groupLabel = versionDate.toLocaleDateString('en-US', { 
                            month: 'short', 
                            day: 'numeric',
                            year: versionDate.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined
                        });
                    }
                    
                    if (!versionsByDate[groupLabel]) {
                        versionsByDate[groupLabel] = [];
                    }
                    versionsByDate[groupLabel].push(version);
                });
                
                drawer.innerHTML = `
                    <div class="version-drawer-header">
                        <h5>Version History</h5>
                        <button class="btn btn-ghost btn-sm" onclick="closeVersionDrawer()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="version-drawer-subheader">
                        <span class="file-name">${fileName}</span>
                        <span class="version-count">${fileVersions.length} version${fileVersions.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="version-drawer-content">
                        ${fileVersions.length === 0 ? '<p class="no-versions">No version history available.</p>' : 
                            Object.entries(versionsByDate).map(([date, dateVersions]) => `
                                <div class="version-date-group">
                                    <div class="version-date-label">${date}</div>
                                    ${dateVersions.map(version => {
                                        const versionDate = new Date(version.created_at);
                                        const timeStr = versionDate.toLocaleTimeString('en-US', { 
                                            hour: 'numeric', 
                                            minute: '2-digit',
                                            hour12: true 
                                        });
                                        const isCurrentVersion = version.version_number === fileVersions[0].version_number;
                                        
                                        return `
                                            <div class="version-item ${isCurrentVersion ? 'current-version' : ''}" 
                                                 onclick="selectVersion(${fileId}, ${version.version_number}, this)">
                                                <div class="version-item-content">
                                                    <div class="version-item-header">
                                                        <span class="version-time">${timeStr}</span>
                                                        ${isCurrentVersion ? '<span class="current-badge">Current</span>' : ''}
                                                    </div>
                                                    <div class="version-item-info">
                                                        <span class="version-number">Version ${version.version_number}</span>
                                                        ${version.created_by ? `<span class="version-author">${version.created_by}</span>` : ''}
                                                    </div>
                                                    ${version.change_description ? 
                                                        `<div class="version-description">${version.change_description}</div>` : ''}
                                                </div>
                                                <div class="version-item-actions">
                                                    <button class="btn btn-ghost btn-sm" title="View this version" 
                                                            onclick="event.stopPropagation(); viewVersion(${fileId}, ${version.version_number})">
                                                        <i class="fas fa-eye"></i>
                                                    </button>
                                                    ${!isCurrentVersion ? `
                                                        <button class="btn btn-ghost btn-sm" title="Restore this version" 
                                                                onclick="event.stopPropagation(); restoreVersion(${fileId}, ${version.version_number}, '${fileName.replace(/'/g, "\\'")}')">  
                                                            <i class="fas fa-undo"></i>
                                                        </button>
                                                    ` : ''}
                                                </div>
                                            </div>
                                        `;
                                    }).join('')}
                                </div>
                            `).join('')
                        }
                    </div>
                `;
                
                document.body.appendChild(drawer);
                
                // Add styles if not already present
                addVersionDrawerStyles();
                
                // Create overlay for click outside functionality
                let overlay = document.querySelector('.version-drawer-overlay');
                if (!overlay) {
                    overlay = document.createElement('div');
                    overlay.className = 'version-drawer-overlay';
                    document.body.appendChild(overlay);
                }
                
                // Open drawer with animation
                setTimeout(() => {
                    drawer.classList.add('open');
                    overlay.classList.add('active');
                }, 10);
                
                // Store current file ID in drawer for verification
                drawer.dataset.fileId = String(fileId);
                console.log('[VersionDrawer] Drawer created with fileId:', drawer.dataset.fileId);
                
                // Close drawer function
                const closeDrawer = () => {
                    const drawer = document.querySelector('.version-drawer');
                    const overlay = document.querySelector('.version-drawer-overlay');
                    if (drawer) {
                        drawer.classList.remove('open');
                        if (overlay) overlay.classList.remove('active');
                        setTimeout(() => {
                            drawer.remove();
                            if (overlay) overlay.remove();
                        }, 300);
                    }
                };
                
                // Attach global functions for drawer
                window.closeVersionDrawer = closeDrawer;
                
                // Click outside to close
                overlay.addEventListener('click', closeDrawer);
                
                // ESC key to close
                const escHandler = (e) => {
                    if (e.key === 'Escape') {
                        closeDrawer();
                        document.removeEventListener('keydown', escHandler);
                    }
                };
                document.addEventListener('keydown', escHandler);
                
                window.selectVersion = (fileId, versionNumber, element) => {
                    // Remove previous selection
                    document.querySelectorAll('.version-item.selected').forEach(item => {
                        item.classList.remove('selected');
                    });
                    
                    // Add selection to clicked item
                    element.classList.add('selected');
                    
                    // View the version
                    viewVersion(fileId, versionNumber);
                };
                
                window.viewVersion = viewVersion;
                window.restoreVersion = restoreVersion;
            };
            
            // Add version drawer styles
            const addVersionDrawerStyles = () => {
                if (!document.querySelector('#versionDrawerStyles')) {
                    const style = document.createElement('style');
                    style.id = 'versionDrawerStyles';
                    style.textContent = `
                        .version-drawer {
                            position: fixed;
                            top: 0;
                            right: -400px;
                            width: 400px;
                            height: 100%;
                            background: #1a1a1a;
                            box-shadow: -2px 0 10px rgba(0,0,0,0.5);
                            z-index: 2050;
                            display: flex;
                            flex-direction: column;
                            transition: right 0.3s ease;
                        }
                        
                        .version-drawer.open {
                            right: 0;
                        }
                        
                        .version-drawer-header {
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            padding: 1rem 1.5rem;
                            border-bottom: 1px solid #333;
                            background: #0a0a0a;
                        }
                        
                        .version-drawer-header h5 {
                            margin: 0;
                            font-size: 1.1rem;
                            font-weight: 600;
                            color: #e2e8f0;
                        }
                        
                        .version-drawer-subheader {
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            padding: 0.75rem 1.5rem;
                            border-bottom: 1px solid #333;
                            background: #1a1a1a;
                        }
                        
                        .version-drawer-subheader .file-name {
                            font-weight: 500;
                            color: #94a3b8;
                            font-size: 0.9rem;
                        }
                        
                        .version-drawer-subheader .version-count {
                            font-size: 0.85rem;
                            color: #64748b;
                        }
                        
                        .version-drawer-content {
                            flex: 1;
                            overflow-y: auto;
                            padding: 1rem 0;
                        }
                        
                        .version-date-group {
                            margin-bottom: 1.5rem;
                        }
                        
                        .version-date-label {
                            font-size: 0.75rem;
                            font-weight: 600;
                            color: #64748b;
                            text-transform: uppercase;
                            letter-spacing: 0.5px;
                            padding: 0 1.5rem;
                            margin-bottom: 0.5rem;
                        }
                        
                        .version-item {
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            padding: 0.75rem 1.5rem;
                            cursor: pointer;
                            transition: all 0.2s ease;
                            border-left: 3px solid transparent;
                        }
                        
                        .version-item:hover {
                            background-color: #262626;
                        }
                        
                        .version-item.selected {
                            background-color: #1e293b;
                            border-left-color: #3b82f6;
                        }
                        
                        .version-item.current-version {
                            background-color: #1e1e2e;
                        }
                        
                        .version-item-content {
                            flex: 1;
                            min-width: 0;
                        }
                        
                        .version-item-header {
                            display: flex;
                            align-items: center;
                            gap: 0.5rem;
                            margin-bottom: 0.25rem;
                        }
                        
                        .version-time {
                            font-size: 0.875rem;
                            font-weight: 500;
                            color: #e2e8f0;
                        }
                        
                        .current-badge {
                            font-size: 0.7rem;
                            font-weight: 600;
                            color: #3b82f6;
                            background: #1e293b;
                            padding: 0.125rem 0.5rem;
                            border-radius: 10px;
                            text-transform: uppercase;
                        }
                        
                        .version-item-info {
                            display: flex;
                            align-items: center;
                            gap: 0.5rem;
                            font-size: 0.8rem;
                            color: #94a3b8;
                        }
                        
                        .version-number {
                            font-weight: 500;
                        }
                        
                        .version-author::before {
                            content: '•';
                            margin-right: 0.5rem;
                        }
                        
                        .version-description {
                            font-size: 0.8rem;
                            color: #64748b;
                            margin-top: 0.25rem;
                            white-space: nowrap;
                            overflow: hidden;
                            text-overflow: ellipsis;
                        }
                        
                        .version-item-actions {
                            display: flex;
                            gap: 0.25rem;
                            opacity: 0;
                            transition: opacity 0.2s ease;
                        }
                        
                        .version-item:hover .version-item-actions {
                            opacity: 1;
                        }
                        
                        .btn-ghost {
                            background: transparent;
                            border: none;
                            color: #64748b;
                            padding: 0.25rem 0.5rem;
                            border-radius: 4px;
                            transition: all 0.2s ease;
                        }
                        
                        .btn-ghost:hover {
                            background: #334155;
                            color: #94a3b8;
                        }
                        
                        .no-versions {
                            text-align: center;
                            color: #64748b;
                            padding: 2rem;
                        }
                        
                        /* Overlay for click outside */
                        .version-drawer-overlay {
                            position: fixed;
                            top: 0;
                            left: 0;
                            right: 0;
                            bottom: 0;
                            background: rgba(0, 0, 0, 0.5);
                            z-index: 2049;
                            opacity: 0;
                            visibility: hidden;
                            transition: opacity 0.3s ease, visibility 0.3s ease;
                        }
                        
                        .version-drawer-overlay.active {
                            opacity: 1;
                            visibility: visible;
                        }
                    `;
                    document.head.appendChild(style);
                }
            };
            
            // View specific version
            const viewVersion = async (fileId, versionNumber) => {
                const projectId = getCurrentProjectId();
                if (!projectId || !fileId) return;
                
                try {
                    const response = await fetch(`/projects/${projectId}/api/files/${fileId}/versions/${versionNumber}/`, {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        }
                    });
                    
                    const data = await response.json();
                    if (!data.success) {
                        throw new Error(data.error || 'Failed to load version');
                    }
                    
                    // Show version content in viewer
                    const viewerMarkdown = document.getElementById('viewer-markdown');
                    if (viewerMarkdown) {
                        // Add version notice
                        const versionNotice = document.createElement('div');
                        versionNotice.style.cssText = `
                            background: #333;
                            border: 1px solid #8b5cf6;
                            padding: 10px 15px;
                            margin-bottom: 20px;
                            border-radius: 6px;
                            color: #e2e8f0;
                            display: flex;
                            justify-content: space-between;
                            align-items: center;
                        `;
                        versionNotice.innerHTML = `
                            <span><i class="fas fa-info-circle"></i> Viewing version ${versionNumber} from ${new Date(data.created_at).toLocaleDateString()}</span>
                            <button id="close-version-view" style="background: #8b5cf6; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">
                                Back to Current
                            </button>
                        `;
                        
                        // Render version content
                        viewerMarkdown.innerHTML = '';
                        viewerMarkdown.appendChild(versionNotice);
                        
                        const contentDiv = document.createElement('div');
                        if (typeof marked !== 'undefined') {
                            contentDiv.innerHTML = marked.parse(data.content);
                        } else {
                            contentDiv.innerHTML = data.content.replace(/\n/g, '<br>');
                        }
                        viewerMarkdown.appendChild(contentDiv);
                        
                        // Style the viewer for version view
                        viewerMarkdown.style.opacity = '0.95';
                        
                        // Back to current button
                        document.getElementById('close-version-view').addEventListener('click', () => {
                            viewFileContent(fileId, window.currentFileData.fileName);
                        });
                    }
                    
                } catch (error) {
                    console.error('[ArtifactsLoader] Error viewing version:', error);
                    showToast('Failed to load version', 'error');
                }
            };
            
            // Restore version
            const restoreVersion = async (fileId, versionNumber) => {
                const projectId = getCurrentProjectId();
                if (!projectId || !fileId) return;
                
                try {
                    const response = await fetch(`/projects/${projectId}/api/files/${fileId}/versions/${versionNumber}/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        }
                    });
                    
                    const data = await response.json();
                    if (!data.success) {
                        throw new Error(data.error || 'Failed to restore version');
                    }
                    
                    showToast(data.message, 'success');
                    // Close the version drawer
                    closeVersionDrawer();
                    // Reload the file content
                    viewFileContent(fileId, window.currentFileData.fileName);
                    
                } catch (error) {
                    console.error('[ArtifactsLoader] Error restoring version:', error);
                    showToast('Failed to restore version', 'error');
                }
            };
            
            // Delete file
            const deleteFile = (fileId) => {
                // Get the file information from the DOM data attributes
                const fileItem = document.querySelector(`[data-file-id="${fileId}"]`);
                let fileType = 'other';
                let fileName = '';
                
                if (fileItem) {
                    // Use data attributes which have the actual backend values
                    fileType = fileItem.dataset.fileType || 'other';
                    fileName = fileItem.dataset.fileName || '';
                    
                    console.log('[ArtifactsLoader] Delete - Using data attributes:', {
                        fileType: fileType,
                        fileName: fileName
                    });
                }
                
                console.log('[ArtifactsLoader] Deleting file:', {
                    fileId: fileId,
                    fileName: fileName,
                    fileType: fileType,
                    url: `/projects/${projectId}/api/files/?type=${fileType}&name=${encodeURIComponent(fileName)}`
                });
                
                // Use the unified files API with query parameters
                fetch(`/projects/${projectId}/api/files/?type=${fileType}&name=${encodeURIComponent(fileName)}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showToast('File deleted successfully', 'success');
                        // Go back to file browser
                        const fileBrowserViewer = document.getElementById('filebrowser-viewer');
                        const fileBrowserMain = document.getElementById('filebrowser-main');
                        if (fileBrowserViewer && fileBrowserMain) {
                            fileBrowserViewer.style.display = 'none';
                            fileBrowserMain.style.display = 'flex';
                        }
                        fetchFiles(currentPage);
                    } else {
                        showToast(data.error || 'Failed to delete file', 'error');
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error deleting file:', error);
                    showToast('Failed to delete file', 'error');
                });
            };
            
            // Archive file (for now, same as delete but could be different)
            const archiveFile = (fileId) => {
                // In a real implementation, you'd have a separate archive endpoint
                // For now, we'll just show a message
                showToast('Archive feature coming soon', 'info');
            };
            
            // Copy file content to clipboard
            const copyFileContent = (fileId) => {
                fetch(`/projects/${projectId}/api/files/${fileId}/content/`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.content) {
                        copyToClipboard(data.content);
                        showToast('Content copied to clipboard!', 'success');
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error copying file content:', error);
                    showToast('Failed to copy file content', 'error');
                });
            };
            
            // Event listeners for search and filters
            if (fileSearch) {
                fileSearch.addEventListener('input', function() {
                    currentSearch = this.value;
                    
                    // Debounce search
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        currentPage = 1;
                        fetchFiles(currentPage);
                    }, 300);
                });
            }
            
            if (fileTypeFilter) {
                fileTypeFilter.addEventListener('change', function() {
                    currentType = this.value;
                    currentPage = 1;
                    fetchFiles(currentPage);
                });
            }
            
            if (refreshButton) {
                refreshButton.addEventListener('click', function() {
                    fetchFiles(currentPage);
                });
            }
            
            // Viewer event listeners
            if (viewerBack) {
                viewerBack.addEventListener('click', async function() {
                    // Check if we're in edit mode with unsaved changes
                    if (window.currentWysiwygEditor && hasUnsavedChanges) {
                        // Auto-save before going back
                        console.log('[FileBrowser] Auto-saving before navigating back...');
                        await saveFileContent(true); // true for auto-save
                    }
                    
                    // If still in edit mode, cancel it without refreshing
                    if (window.currentWysiwygEditor) {
                        // Stop auto-save timer
                        if (window.autoSaveTimer) {
                            clearInterval(window.autoSaveTimer);
                            window.autoSaveTimer = null;
                        }
                        
                        // Clear reference
                        window.currentWysiwygEditor = null;
                        
                        // Remove the editor container
                        const editorContainer = document.getElementById('wysiwyg-editor');
                        if (editorContainer) {
                            editorContainer.remove();
                        }
                        
                        // Show viewer content again
                        const viewerContent = document.querySelector('.viewer-content');
                        if (viewerContent) {
                            viewerContent.style.display = '';
                        }
                        
                        // Hide save/cancel buttons
                        const saveButton = document.getElementById('viewer-save');
                        const cancelButton = document.getElementById('viewer-cancel');
                        if (saveButton) saveButton.style.display = 'none';
                        if (cancelButton) cancelButton.style.display = 'none';
                        
                        // Show original buttons
                        const editButton = document.getElementById('viewer-edit');
                        const copyButton = document.getElementById('viewer-copy');
                        const versionButton = document.getElementById('viewer-versions');
                        const optionsButton = document.getElementById('viewer-options');
                        if (editButton) editButton.style.display = 'flex';
                        if (copyButton) copyButton.style.display = 'flex';
                        if (versionButton) versionButton.style.display = 'flex';
                        if (optionsButton) optionsButton.style.display = 'flex';
                    }
                    
                    // Navigate back to file list
                    fileBrowserViewer.style.display = 'none';
                    fileBrowserMain.style.display = 'flex';
                    
                    // Refresh the file list
                    fetchFiles(currentPage);
                });
            }
            
            // Event listeners for viewer buttons are now attached when buttons are created dynamically
            
            // Initial load
            fetchFiles(1);
        } // End of loadFileBrowser function
    }; // End of ArtifactsLoader object

    // ArtifactsLoader is now ready to use
    console.log('[ArtifactsLoader] Loaded and ready');
    
    // Add event handlers for custom PRD selector
    setTimeout(() => {
        const prdSelector = document.getElementById('prd-selector');
        const selectorButton = document.getElementById('prd-selector-button');
        const selectorDropdown = document.getElementById('prd-selector-dropdown');
        const selectorText = document.getElementById('prd-selector-text');
        
        // Handle custom dropdown toggle
        if (selectorButton) {
            selectorButton.addEventListener('click', function(e) {
                e.stopPropagation();
                const isOpen = selectorDropdown.style.display === 'block';
                
                if (isOpen) {
                    selectorDropdown.style.display = 'none';
                    selectorButton.classList.remove('active');
                } else {
                    selectorDropdown.style.display = 'block';
                    selectorButton.classList.add('active');
                }
            });
        }
        
        // Handle option selection
        document.addEventListener('click', function(e) {
            // Handle PRD selection
            if (e.target.classList.contains('prd-dropdown-option') || e.target.closest('.prd-dropdown-option')) {
                const optionEl = e.target.classList.contains('prd-dropdown-option') ? e.target : e.target.closest('.prd-dropdown-option');
                const selectedValue = optionEl.getAttribute('data-value');
                
                // Update UI
                if (selectorText) selectorText.textContent = selectedValue;
                if (prdSelector) prdSelector.value = selectedValue;
                
                // Update selected state
                document.querySelectorAll('.prd-dropdown-option').forEach(opt => {
                    opt.classList.remove('selected');
                });
                optionEl.classList.add('selected');
                
                // Close dropdown
                if (selectorDropdown) selectorDropdown.style.display = 'none';
                if (selectorButton) selectorButton.classList.remove('active');
                
                // Get project ID and load PRD
                const urlParams = new URLSearchParams(window.location.search);
                const urlProjectId = urlParams.get('project_id');
                let projectId = urlProjectId;
                
                if (!projectId) {
                    const pathMatch = window.location.pathname.match(/\/chat\/project\/([a-f0-9-]+)\//);
                    if (pathMatch && pathMatch[1]) {
                        projectId = pathMatch[1];
                    }
                }
                
                if (projectId && selectedValue) {
                    console.log(`[ArtifactsLoader] PRD selection changed to: ${selectedValue} for project: ${projectId}`);
                    window.ArtifactsLoader.loadPRD(projectId, selectedValue);
                }
            }
        });
        
        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.prd-selector-wrapper')) {
                if (selectorDropdown) selectorDropdown.style.display = 'none';
                if (selectorButton) selectorButton.classList.remove('active');
            }
        });
        
        // Handle keyboard navigation
        if (selectorButton) {
            selectorButton.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    selectorButton.click();
                }
            });
        }
    }, 500); // Small delay to ensure elements are loaded

}); // End of DOMContentLoaded

// Global functions for checklist item editing (accessible from inline onclick handlers)
window.editChecklistItem = function(itemId) {
    const projectId = window.getCurrentProjectId ? window.getCurrentProjectId() : window.ArtifactsLoader?.getCurrentProjectId();
    if (!projectId) {
        console.error('[EditChecklistItem] No project ID available');
        alert('Unable to edit item: No project ID found');
        return;
    }

    // Fetch current checklist data
    fetch(`/projects/${projectId}/api/checklist/`)
        .then(response => response.json())
        .then(data => {
            const checklist = data.checklist || [];
            const item = checklist.find(i => i.id == itemId);

            if (!item) {
                alert('Checklist item not found');
                return;
            }

            const escapeHtml = (value) => {
                if (value === null || value === undefined) {
                    return '';
                }
                return String(value)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            };

            const formatStatusText = (value) => {
                if (!value) {
                    return 'OPEN';
                }
                return value.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()).toUpperCase();
            };

            const formatTitleUpper = (value, fallback = '') => {
                const source = value || fallback;
                if (!source) {
                    return fallback.toUpperCase();
                }
                return String(source)
                    .toLowerCase()
                    .replace(/(^|\s|[_-])(\w)/g, (_, sep, char) => `${sep === '_' || sep === '-' ? ' ' : sep}${char.toUpperCase()}`)
                    .trim()
                    .toUpperCase();
            };

            // Create modal overlay
            const overlay = document.createElement('div');
            overlay.className = 'edit-checklist-overlay';
            overlay.style.cssText = 'position: fixed; inset: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(12px); background: rgba(5,7,12,0.55); z-index: 10000; padding: 24px;';

            // Create modal container
            const modal = document.createElement('div');
            modal.className = 'edit-checklist-modal';
            modal.style.cssText = 'background: rgba(30,30,30,0.88); border: 1px solid rgba(255,255,255,0.05); border-radius: 18px; max-width: 700px; width: 100%; max-height: 92vh; overflow-y: auto; box-shadow: 0 28px 60px rgba(0,0,0,0.55); color: #e2e8f0; padding: 32px; display: flex; flex-direction: column; gap: 24px;';

            const sanitizedDescription = escapeHtml(item.description || '');

            modal.innerHTML = `
                <header style="display: flex; flex-direction: column; gap: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
                        <div style="display: flex; flex-direction: column; gap: 4px;">
                            <span style="font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; color: rgba(148, 163, 184, 0.6);">Edit Ticket</span>
                            <h3 style="margin: 0; font-size: 22px; font-weight: 600; color: #f8fafc;">${escapeHtml(item.name || 'Checklist Item')}</h3>
                            <span style="font-size: 13px; color: rgba(203, 213, 225, 0.65);">Update ticket details to keep the plan in sync.</span>
                        </div>
                        <button type="button" id="close-edit-modal" style="width: 34px; height: 34px; border-radius: 10px; border: 1px solid rgba(148,163,184,0.2); background: rgba(148,163,184,0.09); color: #ccd3f6; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 16px;">
                            <span style="transform: translateY(-1px);">×</span>
                        </button>
                    </div>
                    <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                        <span class="ticket-chip" style="padding: 6px 12px; min-height: 26px; border-radius: 9px; font-size: 11px; letter-spacing: 0.09em;">${formatStatusText(item.status)}</span>
                        <span class="ticket-chip" style="padding: 6px 12px; min-height: 26px; border-radius: 9px; font-size: 11px; letter-spacing: 0.09em;">${formatTitleUpper(item.complexity, 'Medium')}</span>
                        <span class="ticket-chip" style="padding: 6px 12px; min-height: 26px; border-radius: 9px; font-size: 11px; letter-spacing: 0.09em;">${formatTitleUpper(item.priority, 'Medium')}</span>
                    </div>
                </header>
                <form id="edit-checklist-form" style="display: flex; flex-direction: column; gap: 20px;">
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Name *</label>
                        <input type="text" id="edit-name" value="${(item.name || '').replace(/"/g, '&quot;')}"
                            style="width: 100%; padding: 12px 14px; background: rgba(12,12,16,0.75); border: 1px solid rgba(71,85,105,0.45); color: #f8fafc; border-radius: 12px; font-size: 15px; font-weight: 500;" required>
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Description</label>
                        <textarea id="edit-description" rows="6"
                            style="width: 100%; padding: 14px; background: rgba(12,12,16,0.75); border: 1px solid rgba(71,85,105,0.45); color: #f1f5f9; border-radius: 12px; font-size: 14px; line-height: 1.6; resize: vertical; min-height: 160px;">${sanitizedDescription}</textarea>
                    </div>

                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr)); gap: 10px; align-items: flex-end;">
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Status</label>
                            <select id="edit-status" class="ticket-form-select">
                                <option value="open" ${item.status === 'open' ? 'selected' : ''}>Open</option>
                                <option value="in_progress" ${item.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
                                <option value="done" ${item.status === 'done' ? 'selected' : ''}>Done</option>
                                <option value="failed" ${item.status === 'failed' ? 'selected' : ''}>Failed</option>
                                <option value="blocked" ${item.status === 'blocked' ? 'selected' : ''}>Blocked</option>
                            </select>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Priority</label>
                            <select id="edit-priority" class="ticket-form-select">
                                <option value="High" ${item.priority === 'High' ? 'selected' : ''}>High</option>
                                <option value="Medium" ${item.priority === 'Medium' ? 'selected' : ''}>Medium</option>
                                <option value="Low" ${item.priority === 'Low' ? 'selected' : ''}>Low</option>
                            </select>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Role</label>
                            <select id="edit-role" class="ticket-form-select">
                                <option value="agent" ${item.role === 'agent' ? 'selected' : ''}>Agent</option>
                                <option value="user" ${item.role === 'user' ? 'selected' : ''}>User</option>
                            </select>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Complexity</label>
                            <select id="edit-complexity" class="ticket-form-select">
                                <option value="simple" ${item.complexity === 'simple' ? 'selected' : ''}>Simple</option>
                                <option value="medium" ${item.complexity === 'medium' ? 'selected' : ''}>Medium</option>
                                <option value="complex" ${item.complexity === 'complex' ? 'selected' : ''}>Complex</option>
                            </select>
                        </div>
                    </div>

                    <label style="display: inline-flex; align-items: center; gap: 10px; padding: 14px; border-radius: 12px; background: rgba(15,23,42,0.4); border: 1px solid rgba(71,85,105,0.45); color: rgba(226,232,240,0.8); font-size: 13px;">
                        <input type="checkbox" id="edit-requires-worktree" ${item.requires_worktree ? 'checked' : ''}
                            style="width: 18px; height: 18px; border-radius: 4px; border: 1px solid rgba(71,85,105,0.6); background: rgba(12,12,16,0.75);">
                        Requires git worktree for code changes
                    </label>

                    <div style="display: flex; justify-content: flex-end; gap: 10px;">
                        <button type="button" id="cancel-edit-btn"
                            style="padding: 12px 20px; border-radius: 10px; border: 1px solid rgba(148,163,184,0.25); background: rgba(51,65,85,0.35); color: #e2e8f0; font-size: 14px; font-weight: 600; cursor: pointer;">
                            Cancel
                        </button>
                        <button type="submit" id="save-edit-btn"
                            style="padding: 12px 20px; border-radius: 10px; border: none; background: linear-gradient(135deg, #7c3aed, #a855f7); color: #f8fafc; font-size: 14px; font-weight: 600; cursor: pointer; box-shadow: 0 10px 26px rgba(124,58,237,0.28);">
                            Save Changes
                        </button>
                    </div>
                </form>
            `;

            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            const cancelBtn = modal.querySelector('#cancel-edit-btn');
            const saveBtn = modal.querySelector('#save-edit-btn');
            const originalSaveLabel = saveBtn.innerHTML;
            const closeBtn = modal.querySelector('#close-edit-modal');

            const removeModal = () => overlay.remove();

            cancelBtn.addEventListener('click', removeModal);
            closeBtn.addEventListener('click', removeModal);
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    removeModal();
                }
            });

            // Handle form submission
            const form = modal.querySelector('#edit-checklist-form');
            form.addEventListener('submit', async (e) => {
                e.preventDefault();

                const updatedData = {
                    item_id: itemId,
                    name: document.getElementById('edit-name').value,
                    description: document.getElementById('edit-description').value,
                    status: document.getElementById('edit-status').value,
                    priority: document.getElementById('edit-priority').value,
                    role: document.getElementById('edit-role').value,
                    complexity: document.getElementById('edit-complexity').value,
                    requires_worktree: document.getElementById('edit-requires-worktree').checked
                };

                // Disable submit button and show loading state
                saveBtn.disabled = true;
                saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

                try {
                    const getCsrfToken = () => {
                        return document.querySelector('[name=csrfmiddlewaretoken]')?.value
                            || document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1]
                            || '';
                    };

                    const response = await fetch(`/projects/${projectId}/api/checklist/update/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify(updatedData)
                    });

                    const result = await response.json();

                    if (result.success) {
                        if (window.showToast) {
                            window.showToast('Checklist item updated successfully', 'success');
                        }
                        overlay.remove();

                        // Reload checklist to show updated data
                        if (window.ArtifactsLoader && window.ArtifactsLoader.loadChecklist) {
                            window.ArtifactsLoader.loadChecklist(projectId);
                        }
                    } else {
                        throw new Error(result.error || 'Failed to update item');
                    }
                } catch (error) {
                    console.error('Error updating checklist item:', error);
                    if (window.showToast) {
                        window.showToast('Error updating item: ' + error.message, 'error');
                    } else {
                        alert('Error updating item: ' + error.message);
                    }
                    // Re-enable button
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = originalSaveLabel;
                }
            });
        })
        .catch(error => {
            console.error('Error fetching checklist data:', error);
            alert('Error loading checklist data: ' + error.message);
        });
};

window.toggleChecklistStatus = function(itemId, currentStatus) {
    const projectId = window.getCurrentProjectId ? window.getCurrentProjectId() : window.ArtifactsLoader?.getCurrentProjectId();
    if (!projectId) {
        console.error('[ToggleChecklistStatus] No project ID available');
        alert('Unable to toggle status: No project ID found');
        return;
    }

    // Define status cycle: open -> in_progress -> done -> open
    const statusCycle = {
        'open': 'in_progress',
        'in_progress': 'done',
        'done': 'open',
        'failed': 'open',
        'blocked': 'open'
    };

    const newStatus = statusCycle[currentStatus] || 'in_progress';

    const getCsrfToken = () => {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value
            || document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1]
            || '';
    };

    // Update status via API
    fetch(`/projects/${projectId}/api/checklist/update/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ item_id: itemId, status: newStatus })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            if (window.showToast) {
                window.showToast(`Status updated to ${newStatus.replace('_', ' ')}`, 'success');
            }

            // Reload checklist to show updated data
            if (window.ArtifactsLoader && window.ArtifactsLoader.loadChecklist) {
                window.ArtifactsLoader.loadChecklist(projectId);
            }
        } else {
            throw new Error(result.error || 'Failed to update status');
        }
    })
    .catch(error => {
        console.error('Error toggling status:', error);
        if (window.showToast) {
            window.showToast('Error updating status: ' + error.message, 'error');
        } else {
            alert('Error updating status: ' + error.message);
        }
    });
};

/* ==== End: artifacts-loader.js ==== */

/* ==== Begin: artifacts-editor.js ==== */
/**
 * Artifacts Editor JavaScript
 * Handles editing functionality for PRD and Implementation in the artifacts panel
 */

(function() {
    window.ArtifactsEditor = {
        // Track current editing states
        editingStates: {
            prd: false,
            implementation: false
        },
        
        // Original content for cancel functionality
        originalContent: {
            prd: '',
            implementation: ''
        },
        
        // Initialize editor functionality
        init: function() {
            console.log('[ArtifactsEditor] Initializing editor functionality');
            this.setupStyles();
        },
        
        // Add required styles for editor
        setupStyles: function() {
            const style = document.createElement('style');
            style.textContent = `
                .artifact-edit-controls {
                    display: flex;
                    gap: 10px;
                    margin-bottom: 15px;
                    justify-content: flex-end;
                }
                
                .artifact-edit-btn {
                    padding: 6px 12px;
                    background: #8b5cf6;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    gap: 5px;
                    font-size: 14px;
                    transition: background 0.2s;
                }
                
                .artifact-edit-btn:hover {
                    background: #7c3aed;
                }
                
                .artifact-edit-btn.cancel {
                    background: #6b7280;
                }
                
                .artifact-edit-btn.cancel:hover {
                    background: #4b5563;
                }
                
                .artifact-edit-btn.save {
                    background: #10b981;
                }
                
                .artifact-edit-btn.save:hover {
                    background: #059669;
                }
                
                .artifact-editor {
                    width: 100%;
                    min-height: 400px;
                    padding: 15px;
                    background: #1a1a1a;
                    border: 1px solid #333;
                    border-radius: 4px;
                    color: #e2e8f0;
                    font-family: 'Monaco', 'Consolas', monospace;
                    font-size: 14px;
                    line-height: 1.6;
                    resize: vertical;
                }
                
                .artifact-editor:focus {
                    outline: none;
                    border-color: #8b5cf6;
                }
                
                .saving-indicator {
                    display: none;
                    align-items: center;
                    gap: 8px;
                    color: #8b5cf6;
                    font-size: 14px;
                }
                
                .saving-indicator.active {
                    display: flex;
                }
                
                .saving-indicator .spinner {
                    width: 16px;
                    height: 16px;
                    border: 2px solid #8b5cf6;
                    border-top-color: transparent;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                }
                
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        },
        
        // Enable edit mode for PRD
        enablePRDEdit: function(projectId, currentContent) {
            console.log('[ArtifactsEditor] Enabling PRD edit mode');
            this.editingStates.prd = true;
            this.originalContent.prd = currentContent;
            
            const prdContainer = document.getElementById('prd-container');
            if (!prdContainer) return;
            
            // Get existing PRD selector HTML if it exists
            const prdMeta = prdContainer.querySelector('.prd-meta');
            const existingSelectorHTML = prdMeta ? prdMeta.innerHTML : '';
            
            // Replace the PRD content area with editor
            const streamingContainer = document.getElementById('prd-streaming-content');
            if (streamingContainer) {
                streamingContainer.innerHTML = `<textarea id="prd-editor" class="artifact-editor">${currentContent}</textarea>`;
            }
            
            // Clear the actions container
            const prdActionsContainer = prdContainer.querySelector('.prd-actions-container');
            if (prdActionsContainer) {
                prdActionsContainer.innerHTML = `
                    <div class="artifact-edit-controls">
                        <div class="saving-indicator" id="prd-saving-indicator">
                            <div class="spinner"></div>
                            <span>Saving...</span>
                        </div>
                        <button class="artifact-edit-btn cancel" id="prd-cancel-btn">
                            <i class="fas fa-times"></i> Cancel
                        </button>
                        <button class="artifact-edit-btn save" id="prd-save-btn">
                            <i class="fas fa-save"></i> Save
                        </button>
                    </div>
                `;
                
                // Add event listeners
                const saveBtn = document.getElementById('prd-save-btn');
                const cancelBtn = document.getElementById('prd-cancel-btn');
                
                if (saveBtn) {
                    console.log('[ArtifactsEditor] Adding save button listener, projectId:', projectId);
                    saveBtn.addEventListener('click', () => {
                        console.log('[ArtifactsEditor] Save button clicked, projectId:', projectId);
                        window.ArtifactsEditor.savePRD(projectId);
                    });
                } else {
                    console.error('[ArtifactsEditor] Save button not found!');
                }
                
                if (cancelBtn) {
                    cancelBtn.addEventListener('click', () => {
                        window.ArtifactsEditor.cancelPRDEdit();
                    });
                }
            }
            
            // Focus on the editor
            setTimeout(() => {
                const editor = document.getElementById('prd-editor');
                if (editor) {
                    editor.focus();
                    editor.setSelectionRange(0, 0);
                }
            }, 100);
        },
        
        // Enable edit mode for Implementation
        enableImplementationEdit: function(projectId, currentContent) {
            console.log('[ArtifactsEditor] Enabling Implementation edit mode');
            this.editingStates.implementation = true;
            this.originalContent.implementation = currentContent;
            
            const implementationTab = document.getElementById('implementation');
            if (!implementationTab) return;
            
            implementationTab.innerHTML = `
                <div class="implementation-container">
                    <div class="implementation-header">
                        <h2>Implementation Plan</h2>
                        <div class="artifact-edit-controls">
                            <div class="saving-indicator" id="implementation-saving-indicator">
                                <div class="spinner"></div>
                                <span>Saving...</span>
                            </div>
                            <button class="artifact-edit-btn cancel" onclick="ArtifactsEditor.cancelImplementationEdit()">
                                <i class="fas fa-times"></i> Cancel
                            </button>
                            <button class="artifact-edit-btn save" onclick="ArtifactsEditor.saveImplementation(${projectId})">
                                <i class="fas fa-save"></i> Save
                            </button>
                        </div>
                    </div>
                    <textarea id="implementation-editor" class="artifact-editor">${currentContent}</textarea>
                </div>
            `;
            
            // Focus on the editor
            setTimeout(() => {
                const editor = document.getElementById('implementation-editor');
                if (editor) {
                    editor.focus();
                    editor.setSelectionRange(0, 0);
                }
            }, 100);
        },
        
        // Save PRD content
        savePRD: async function(projectId) {
            console.log('[ArtifactsEditor] Saving PRD, projectId:', projectId);
            const editor = document.getElementById('prd-editor');
            const savingIndicator = document.getElementById('prd-saving-indicator');
            
            if (!editor) {
                console.error('[ArtifactsEditor] PRD editor not found!');
                return;
            }
            
            if (!projectId) {
                console.error('[ArtifactsEditor] Project ID is missing!');
                return;
            }
            
            const content = editor.value;
            if (savingIndicator) {
                savingIndicator.classList.add('active');
            }
            
            // Get the current PRD name from the selector if it exists
            const prdSelector = document.getElementById('prd-selector');
            const prdName = prdSelector ? prdSelector.value : 'Main PRD';
            
            console.log('[ArtifactsEditor] PRD content length:', content.length);
            console.log('[ArtifactsEditor] PRD name:', prdName);
            
            try {
                const response = await fetch(`/projects/${projectId}/api/prd/?prd_name=${encodeURIComponent(prdName)}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({ content: content })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    console.log('[ArtifactsEditor] PRD saved successfully');
                    this.editingStates.prd = false;
                    
                    // Check if PRD is currently streaming
                    if (window.prdStreamingState && window.prdStreamingState.isStreaming) {
                        console.log('[ArtifactsEditor] PRD is currently streaming, skipping reload');
                        return;
                    }
                    
                    // Reload the PRD content with the correct PRD name
                    if (window.ArtifactsLoader && window.ArtifactsLoader.loadPRD) {
                        console.log('[ArtifactsEditor] Reloading PRD after save');
                        window.ArtifactsLoader.loadPRD(projectId, prdName);
                    }
                } else {
                    console.error('[ArtifactsEditor] Error saving PRD:', data.error);
                    alert('Error saving PRD: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('[ArtifactsEditor] Error saving PRD:', error);
                alert('Error saving PRD: ' + error.message);
            } finally {
                if (savingIndicator) {
                    savingIndicator.classList.remove('active');
                }
            }
        },
        
        // Save Implementation content
        saveImplementation: async function(projectId) {
            console.log('[ArtifactsEditor] Saving Implementation');
            const editor = document.getElementById('implementation-editor');
            const savingIndicator = document.getElementById('implementation-saving-indicator');
            
            if (!editor || !projectId) return;
            
            const content = editor.value;
            savingIndicator.classList.add('active');
            
            try {
                const response = await fetch(`/projects/${projectId}/api/implementation/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({ content: content })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    console.log('[ArtifactsEditor] Implementation saved successfully');
                    this.editingStates.implementation = false;
                    // Reload the Implementation content
                    if (window.ArtifactsLoader && window.ArtifactsLoader.loadImplementation) {
                        window.ArtifactsLoader.loadImplementation(projectId);
                    }
                } else {
                    console.error('[ArtifactsEditor] Error saving Implementation:', data.error);
                    alert('Error saving Implementation: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('[ArtifactsEditor] Error saving Implementation:', error);
                alert('Error saving Implementation: ' + error.message);
            } finally {
                savingIndicator.classList.remove('active');
            }
        },
        
        // Cancel PRD edit
        cancelPRDEdit: function() {
            console.log('[ArtifactsEditor] Cancelling PRD edit');
            this.editingStates.prd = false;
            
            // Check if PRD is currently streaming
            if (window.prdStreamingState && window.prdStreamingState.isStreaming) {
                console.log('[ArtifactsEditor] PRD is currently streaming, skipping reload');
                return;
            }
            
            // Get the current PRD name from the selector if it exists
            const prdSelector = document.getElementById('prd-selector');
            const prdName = prdSelector ? prdSelector.value : 'Main PRD';
            
            // Now reload the PRD content
            const projectId = window.ArtifactsLoader.getCurrentProjectId();
            console.log('[ArtifactsEditor] Project ID for cancel:', projectId);
            if (projectId && window.ArtifactsLoader && window.ArtifactsLoader.loadPRD) {
                console.log('[ArtifactsEditor] Calling loadPRD to restore content');
                window.ArtifactsLoader.loadPRD(projectId, prdName);
            }
        },
        
        // Cancel Implementation edit
        cancelImplementationEdit: function() {
            console.log('[ArtifactsEditor] Cancelling Implementation edit');
            this.editingStates.implementation = false;
            const projectId = window.ArtifactsLoader.getCurrentProjectId();
            if (projectId && window.ArtifactsLoader && window.ArtifactsLoader.loadImplementation) {
                window.ArtifactsLoader.loadImplementation(projectId);
            }
        },
        
        // Get CSRF token
        getCsrfToken: function() {
            const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (metaToken) return metaToken;
            
            const inputToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            if (inputToken) return inputToken;
            
            const cookieValue = document.cookie
                .split('; ')
                .find(row => row.startsWith('csrftoken='))
                ?.split('=')[1];
            
            return cookieValue || '';
        }
    };
    
    // Initialize on DOM load
    document.addEventListener('DOMContentLoaded', function() {
        window.ArtifactsEditor.init();
    });
})();
/* ==== End: artifacts-editor.js ==== */

/* ==== Begin: design-loader.js ==== */
/**
 * Design Schema Loader JavaScript
 * Handles loading design schema data from the server and updating the design tab with an iframe
 */
document.addEventListener('DOMContentLoaded', function() {
    // Add design schema loader to the ArtifactsLoader if it exists
    if (window.ArtifactsLoader) {
        /**
         * Load design schema from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        window.ArtifactsLoader.loadDesignSchema = function(projectId) {
            console.log(`[ArtifactsLoader] loadDesignSchema called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading design schema');
                return;
            }
            
            // Get elements
            const designTab = document.getElementById('design');
            const designLoading = document.getElementById('design-loading');
            const designEmpty = document.getElementById('design-empty');
            const designFrameContainer = document.getElementById('design-frame-container');
            const designIframe = document.getElementById('design-iframe');
            
            if (!designTab || !designLoading || !designEmpty || !designFrameContainer || !designIframe) {
                console.warn('[ArtifactsLoader] One or more design tab elements not found');
                return;
            }
            
            // Show loading state
            designEmpty.style.display = 'none';
            designFrameContainer.style.display = 'none';
            designLoading.style.display = 'block';
            
            // Fetch design schema from API
            const url = `/projects/${projectId}/api/design-schema/`;
            console.log(`[ArtifactsLoader] Fetching design schema from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] Design schema API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Design schema API data received:', data);
                    // Process design schema data
                    const designContent = data.content || '';
                    
                    if (!designContent) {
                        // Show empty state if no design schema found
                        console.log('[ArtifactsLoader] No design schema found, showing empty state');
                        designLoading.style.display = 'none';
                        designEmpty.style.display = 'block';
                        return;
                    }
                    
                    // Setup iframe content
                    const iframeDoc = designIframe.contentWindow.document;
                    
                    // Write content to the iframe
                    iframeDoc.open();
                    iframeDoc.write(designContent);
                    iframeDoc.close();
                    
                    // Make sure the iframe body takes up full height
                    const style = iframeDoc.createElement('style');
                    style.textContent = `
                        html, body {
                            height: 100%;
                            margin: 0;
                            padding: 0;
                            overflow: auto;
                        }
                        body {
                            min-height: 100%;
                        }
                    `;
                    iframeDoc.head.appendChild(style);
                    
                    // Show iframe container
                    designLoading.style.display = 'none';
                    designFrameContainer.style.display = 'block';
                    
                    // Adjust the container to fill available space
                    designTab.style.overflow = 'hidden';
                })
                .catch(error => {
                    console.error('Error fetching design schema:', error);
                    designLoading.style.display = 'none';
                    designEmpty.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading design schema. Please try again.
                            </div>
                        </div>
                    `;
                    designEmpty.style.display = 'block';
                });
        };
    }
    
    // Update the loadTabData function in artifacts.js if it exists
    const originalLoadTabData = window.loadTabData;
    if (typeof originalLoadTabData === 'function') {
        window.loadTabData = function(tabId) {
            // Call the original function
            originalLoadTabData(tabId);
            
            // Add support for design tab
            const projectId = window.getCurrentProjectId();
            if (tabId === 'design' && projectId && window.ArtifactsLoader && typeof window.ArtifactsLoader.loadDesignSchema === 'function') {
                window.ArtifactsLoader.loadDesignSchema(projectId);
            }
        };
    }
}); 
/* ==== End: design-loader.js ==== */

/* ==== Begin: custom-dropdown.js ==== */
document.addEventListener('DOMContentLoaded', function() {
    // Initialize custom dropdowns
    initializeCustomDropdowns();
    // Initialize settings button
    initializeSettingsButton();
});

function initializeCustomDropdowns() {
    const dropdowns = document.querySelectorAll('.custom-dropdown');
    
    dropdowns.forEach(dropdown => {
        const button = dropdown.querySelector('.custom-dropdown-button');
        const menu = dropdown.querySelector('.custom-dropdown-menu');
        const items = menu.querySelectorAll('.custom-dropdown-item');
        const textSpan = button.querySelector('span');
        
        // Toggle dropdown on button click
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = dropdown.classList.contains('open');
            
            // Close all other dropdowns
            document.querySelectorAll('.custom-dropdown.open').forEach(d => {
                if (d !== dropdown) {
                    d.classList.remove('open');
                    d.querySelector('.custom-dropdown-button').classList.remove('active');
                }
            });
            
            // Toggle current dropdown
            dropdown.classList.toggle('open');
            button.classList.toggle('active');
        });
        
        // Handle item selection
        items.forEach(item => {
            // Skip group labels
            if (item.classList.contains('dropdown-group-label')) {
                return;
            }
            
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                
                // Remove selected class from all items
                items.forEach(i => i.classList.remove('selected'));
                
                // Add selected class to clicked item
                item.classList.add('selected');
                
                // Update button text
                textSpan.textContent = item.textContent;
                
                // Close dropdown
                dropdown.classList.remove('open');
                button.classList.remove('active');
                
                // Trigger change event for compatibility with existing code
                const dropdownId = button.id;
                const value = item.getAttribute('data-value');
                
                // Create and dispatch custom event
                const event = new CustomEvent('dropdownChange', {
                    detail: { value: value, text: item.textContent }
                });
                button.dispatchEvent(event);
                
                // For role dropdown
                if (dropdownId === 'role-dropdown') {
                    // Update the global variable if it exists
                    if (typeof window.currentRole !== 'undefined') {
                        window.currentRole = value;
                    }
                    // Update status display
                    const currentRoleSpan = document.getElementById('current-role');
                    if (currentRoleSpan) {
                        currentRoleSpan.textContent = item.textContent;
                    }
                    // Trigger role change event
                    if (typeof handleRoleChange === 'function') {
                        handleRoleChange(value);
                    }
                }
                
                // For model dropdown
                if (dropdownId === 'model-dropdown') {
                    // Update the global variable if it exists
                    if (typeof window.currentModel !== 'undefined') {
                        window.currentModel = value;
                    }
                    // Update status display
                    const currentModelSpan = document.getElementById('current-model');
                    if (currentModelSpan) {
                        currentModelSpan.textContent = item.textContent;
                    }
                    // Trigger model change event
                    if (typeof handleModelChange === 'function') {
                        handleModelChange(value);
                    }
                }
            });
        });
    });
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.custom-dropdown')) {
            document.querySelectorAll('.custom-dropdown.open').forEach(dropdown => {
                dropdown.classList.remove('open');
                dropdown.querySelector('.custom-dropdown-button').classList.remove('active');
            });
        }
    });
}

// Helper function to get selected value
function getCustomDropdownValue(dropdownId) {
    const dropdown = document.getElementById(dropdownId + '-wrapper');
    if (dropdown) {
        const selectedItem = dropdown.querySelector('.custom-dropdown-item.selected');
        return selectedItem ? selectedItem.getAttribute('data-value') : null;
    }
    return null;
}

// Helper function to set dropdown value
function setCustomDropdownValue(dropdownId, value) {
    const dropdown = document.getElementById(dropdownId + '-wrapper');
    if (dropdown) {
        const items = dropdown.querySelectorAll('.custom-dropdown-item');
        const button = dropdown.querySelector('.custom-dropdown-button');
        const textSpan = button.querySelector('span');
        
        items.forEach(item => {
            if (item.getAttribute('data-value') === value) {
                // Remove selected class from all items
                items.forEach(i => i.classList.remove('selected'));
                
                // Add selected class to matching item
                item.classList.add('selected');
                
                // Update button text
                textSpan.textContent = item.textContent;
                
                // Trigger change event
                const event = new CustomEvent('dropdownChange', {
                    detail: { value: value, text: item.textContent }
                });
                button.dispatchEvent(event);
            }
        });
    }
}

// Export functions for global use
window.getCustomDropdownValue = getCustomDropdownValue;
window.setCustomDropdownValue = setCustomDropdownValue;

// Global functions to handle dropdown changes
window.handleRoleChange = function(value) {
    console.log('Role changed to:', value);
    // Additional role change logic can be added here
};

window.handleModelChange = function(value) {
    console.log('Model changed to:', value);
    // Additional model change logic can be added here
};

// Initialize settings button functionality
function initializeSettingsButton() {
    const settingsBtn = document.getElementById('settings-btn');
    const settingsDropdown = document.getElementById('settings-dropdown');
    
    // Submenus
    const roleSubmenu = document.getElementById('role-submenu');
    const modelSubmenu = document.getElementById('model-submenu');
    
    // Status display
    const currentRoleSpan = document.getElementById('current-role');
    const currentModelSpan = document.getElementById('current-model');
    const currentRoleLeftSpan = document.getElementById('current-role-left');
    const currentModelLeftSpan = document.getElementById('current-model-left');
    
    // Status click buttons
    const roleStatusBtn = document.getElementById('role-status-btn');
    const modelStatusBtn = document.getElementById('model-status-btn');
    
    if (!settingsBtn || !settingsDropdown) return;
    
    let closeTimeout;
    let clickedOpen = false;
    
    // Show dropdown on click for settings button
    settingsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        const isOpen = settingsDropdown.classList.contains('open');
        if (isOpen) {
            settingsDropdown.classList.remove('open');
            clickedOpen = false;
        } else {
            settingsDropdown.classList.add('open');
            clickedOpen = true;
        }
    });
    
    // Handle menu item clicks to show submenus
    const menuItems = settingsDropdown.querySelectorAll('.menu-item');
    menuItems.forEach(menuItem => {
        menuItem.addEventListener('click', (e) => {
            e.stopPropagation();
            
            // Close other open submenus
            menuItems.forEach(item => {
                if (item !== menuItem) {
                    item.classList.remove('active');
                }
            });
            
            // Toggle current submenu
            menuItem.classList.toggle('active');
        });
    });
    
    // Handle clicking on role status
    if (roleStatusBtn) {
        roleStatusBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            clickedOpen = true;
            settingsDropdown.classList.add('open');
            // Show role submenu directly
            setTimeout(() => {
                const roleMenuItem = document.querySelector('[data-submenu="role"]');
                if (roleMenuItem) {
                    roleMenuItem.classList.add('active');
                }
            }, 50);
        });
    }
    
    // Handle clicking on model status
    if (modelStatusBtn) {
        modelStatusBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            clickedOpen = true;
            settingsDropdown.classList.add('open');
            // Show model submenu directly
            setTimeout(() => {
                const modelMenuItem = document.querySelector('[data-submenu="model"]');
                if (modelMenuItem) {
                    modelMenuItem.classList.add('active');
                }
            }, 50);
        });
    }
    
    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#settings-dropdown') && !e.target.closest('#settings-btn') && 
            !e.target.closest('#role-status-btn') && !e.target.closest('#model-status-btn')) {
            settingsDropdown.classList.remove('open');
            clickedOpen = false;
        }
    });
    
    // Handle role option selection
    roleSubmenu.querySelectorAll('.submenu-option').forEach(option => {
        option.addEventListener('click', (e) => {
            e.stopPropagation();
            
            // Update selection
            roleSubmenu.querySelectorAll('.submenu-option').forEach(opt => opt.classList.remove('selected'));
            option.classList.add('selected');
            
            // Update display
            const value = option.getAttribute('data-value');
            const text = option.querySelector('span').textContent;
            
            // Update status display
            if (currentRoleSpan) {
                currentRoleSpan.textContent = text;
            }
            if (currentRoleLeftSpan) {
                currentRoleLeftSpan.textContent = text;
            }
            
            // Update global variable
            if (typeof window.currentRole !== 'undefined') {
                window.currentRole = value;
            }
            
            // Trigger role change event
            if (typeof handleRoleChange === 'function') {
                handleRoleChange(value);
            }
            
            // Close dropdown
            settingsDropdown.classList.remove('open');
            clickedOpen = false;
        });
    });
    
    // Handle model option selection
    modelSubmenu.querySelectorAll('.submenu-option').forEach(option => {
        option.addEventListener('click', (e) => {
            e.stopPropagation();
            
            // Update selection
            modelSubmenu.querySelectorAll('.submenu-option').forEach(opt => opt.classList.remove('selected'));
            option.classList.add('selected');
            
            // Update display
            const value = option.getAttribute('data-value');
            const text = option.querySelector('span').textContent;
            
            // Update status display
            if (currentModelSpan) {
                currentModelSpan.textContent = text;
            }
            if (currentModelLeftSpan) {
                currentModelLeftSpan.textContent = text;
            }
            
            // Update global variable
            if (typeof window.currentModel !== 'undefined') {
                window.currentModel = value;
            }
            
            // Trigger model change event
            if (typeof handleModelChange === 'function') {
                handleModelChange(value);
            }
            
            // Close dropdown
            settingsDropdown.classList.remove('open');
            clickedOpen = false;
        });
    });
}


/* ==== End: custom-dropdown.js ==== */

/* ==== Begin: role-handler.js ==== */
// This script handles fetching the user_role from the database 
// and updates the dropdown accordingly
(function() {
    // Function to extract user_role from conversation data and set the dropdown
    function updateRoleDropdownFromDatabase(conversationData) {
        if (!conversationData || !conversationData.messages || !conversationData.messages.length) {
            console.log('No messages found in conversation data');
            return;
        }
        
        // Find the most recent user role from messages (search in reverse)
        let lastUserRole = null;
        for (let i = conversationData.messages.length - 1; i >= 0; i--) {
            const message = conversationData.messages[i];
            if (message.role === 'user' && message.user_role && message.user_role !== 'default') {
                lastUserRole = message.user_role;
                console.log('Found last user role in conversation:', lastUserRole);
                break;
            }
        }
        
        // Set the dropdown value based on the last user role
        if (lastUserRole) {
            // Update left menu submenu
            const roleSubmenu = document.getElementById('role-submenu');
            if (roleSubmenu) {
                const roleOptions = roleSubmenu.querySelectorAll('.submenu-option');
                roleOptions.forEach(option => {
                    if (option.getAttribute('data-value') === lastUserRole) {
                        option.classList.add('selected');
                        // Update the status display
                        const roleText = option.querySelector('span').textContent;
                        const currentRoleLeft = document.getElementById('current-role-left');
                        if (currentRoleLeft) {
                            currentRoleLeft.textContent = roleText;
                        }
                    } else {
                        option.classList.remove('selected');
                    }
                });
                console.log('Set role submenu to last used role from DB:', lastUserRole);
            }
            
            // Use custom dropdown helper function (if dropdown still exists)
            if (typeof setCustomDropdownValue === 'function' && document.getElementById('role-dropdown')) {
                setCustomDropdownValue('role-dropdown', lastUserRole);
                console.log('Set role dropdown to last used role from DB:', lastUserRole);
            } else {
                // Fallback for old dropdown
                const roleDropdown = document.getElementById('role-dropdown');
                if (roleDropdown && roleDropdown.tagName === 'SELECT') {
                    // Check if this option exists in the dropdown
                    const optionExists = Array.from(roleDropdown.options).some(option => 
                        option.value === lastUserRole
                    );
                    
                    if (optionExists) {
                        roleDropdown.value = lastUserRole;
                        console.log('Set role dropdown to last used role from DB:', lastUserRole);
                    } else {
                        console.log('Role not available in dropdown:', lastUserRole);
                    }
                }
            }
        }
    }
    
    // Override the original loadConversation function to set user role
    document.addEventListener('DOMContentLoaded', function() {
        // Wait until the chat.js script has loaded and defined the function
        setTimeout(() => {
            if (typeof loadConversation === 'function') {
                const originalLoadConversation = loadConversation;
                
                // Override the loadConversation function
                window.loadConversation = function(conversationId) {
                    // Call the original function first
                    const result = originalLoadConversation.apply(this, arguments);
                    
                    // Then fetch the conversation data again to get the user_role
                    fetch(`/api/conversations/${conversationId}/`)
                        .then(response => response.json())
                        .then(data => {
                            updateRoleDropdownFromDatabase(data);
                        })
                        .catch(error => {
                            console.error('Error fetching conversation for role update:', error);
                        });
                    
                    return result;
                };
                
                console.log('Successfully overrode loadConversation function');
            } else {
                console.warn('loadConversation function not found, cannot override');
            }
        }, 500);
        
        // Also use localStorage for backup persistence between refreshes
        const roleDropdown = document.getElementById('role-dropdown');
        if (roleDropdown) {
            // For custom dropdown
            if (roleDropdown.classList.contains('custom-dropdown-button')) {
                // Listen for custom dropdown change event
                roleDropdown.addEventListener('dropdownChange', function(e) {
                    localStorage.setItem('user_role', e.detail.value);
                    console.log('Saved role to localStorage:', e.detail.value);
                });
                
                // Load from localStorage as a fallback
                const savedRole = localStorage.getItem('user_role');
                if (savedRole && typeof setCustomDropdownValue === 'function') {
                    setCustomDropdownValue('role-dropdown', savedRole);
                    console.log('Loaded saved role from localStorage:', savedRole);
                }
            } else if (roleDropdown.tagName === 'SELECT') {
                // Fallback for old select dropdown
                roleDropdown.addEventListener('change', function() {
                    localStorage.setItem('user_role', this.value);
                    console.log('Saved role to localStorage:', this.value);
                });
                
                const savedRole = localStorage.getItem('user_role');
                if (savedRole) {
                    const optionExists = Array.from(roleDropdown.options).some(option => 
                        option.value === savedRole
                    );
                    
                    if (optionExists) {
                        roleDropdown.value = savedRole;
                        console.log('Loaded saved role from localStorage:', savedRole);
                    }
                }
            }
        }
    });
})();

class RoleHandler {
    constructor() {
        this.roleDropdown = document.getElementById('role-dropdown');
        this.roleSubmenu = document.getElementById('role-submenu');
        this.init();
    }

    init() {
        // First try to load from page data
        const roleKeyFromPage = document.body.dataset.roleKey;
        if (roleKeyFromPage) {
            this.setDropdownValue(roleKeyFromPage);
            console.log('Initialized role from page data:', roleKeyFromPage);
        }
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Listen to left menu submenu options
        if (this.roleSubmenu) {
            const roleOptions = this.roleSubmenu.querySelectorAll('.submenu-option');
            roleOptions.forEach(option => {
                option.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const value = option.getAttribute('data-value');
                    this.updateRole(value);
                    
                    // Update UI to show selected state
                    roleOptions.forEach(opt => opt.classList.remove('selected'));
                    option.classList.add('selected');
                    
                    // Update the status display
                    const roleText = option.querySelector('span').textContent;
                    const currentRoleLeft = document.getElementById('current-role-left');
                    if (currentRoleLeft) {
                        currentRoleLeft.textContent = roleText;
                    }
                    
                    // Save to localStorage
                    localStorage.setItem('user_role', value);
                });
            });
        }
        
        // Keep old dropdown listener if it exists
        if (this.roleDropdown) {
            // For custom dropdown
            if (this.roleDropdown.classList.contains('custom-dropdown-button')) {
                this.roleDropdown.addEventListener('dropdownChange', (e) => {
                    this.updateRole(e.detail.value);
                });
            } else if (this.roleDropdown.tagName === 'SELECT') {
                // Fallback for old select dropdown
                this.roleDropdown.addEventListener('change', (e) => {
                    this.updateRole(e.target.value);
                });
            }
        }
    }


    async updateRole(roleName) {
        try {
            const response = await fetch('/api/user/agent-role/', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    name: roleName
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    console.log('Role updated successfully:', data.message);
                    // this.showSuccessMessage(data.message);
                } else {
                    console.error('Failed to update role:', data.error);
                    this.showErrorMessage(data.error);
                }
            } else {
                const errorData = await response.json();
                console.error('Failed to update role:', errorData.error);
                this.showErrorMessage(errorData.error || 'Failed to update role');
            }
        } catch (error) {
            console.error('Error updating role:', error);
            this.showErrorMessage('Network error occurred while updating role');
        }
    }

    setDropdownValue(roleName) {
        // Map backend role names to dropdown values
        const roleMapping = {
            'developer': 'developer',
            'product_analyst': 'product_analyst',
            'designer': 'designer',
            'default': 'product_analyst' // Changed default to product_analyst
        };

        const dropdownValue = roleMapping[roleName] || 'product_analyst';
        
        // Update left menu submenu
        if (this.roleSubmenu) {
            const roleOptions = this.roleSubmenu.querySelectorAll('.submenu-option');
            roleOptions.forEach(option => {
                if (option.getAttribute('data-value') === dropdownValue) {
                    option.classList.add('selected');
                    // Update the status display
                    const roleText = option.querySelector('span').textContent;
                    const currentRoleLeft = document.getElementById('current-role-left');
                    if (currentRoleLeft) {
                        currentRoleLeft.textContent = roleText;
                    }
                } else {
                    option.classList.remove('selected');
                }
            });
        }
        
        // For custom dropdown (if it still exists)
        if (typeof setCustomDropdownValue === 'function' && this.roleDropdown) {
            setCustomDropdownValue('role-dropdown', dropdownValue);
        } else if (this.roleDropdown && this.roleDropdown.tagName === 'SELECT') {
            // Fallback for old select dropdown
            this.roleDropdown.value = dropdownValue;
        }
    }

    showSuccessMessage(message) {
        // Create a temporary success notification
        const notification = document.createElement('div');
        notification.className = 'role-notification success';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4CAF50;
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            z-index: 1000;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;

        document.body.appendChild(notification);

        // Remove after 3 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 3000);
    }

    showErrorMessage(message) {
        // Create a temporary error notification
        const notification = document.createElement('div');
        notification.className = 'role-notification error';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #f44336;
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            z-index: 1000;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;

        document.body.appendChild(notification);

        // Remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    getCSRFToken() {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
        return csrfToken ? csrfToken.value : '';
    }
}

// Initialize role handler when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.userAuthenticated === 'true') {
        new RoleHandler();
    }
}); 
/* ==== End: role-handler.js ==== */

/* ==== Begin: model-handler.js ==== */
class ModelHandler {
    constructor() {
        this.modelDropdown = document.getElementById('model-dropdown');
        this.modelSubmenu = document.getElementById('model-submenu');
        this.init();
    }

    init() {
        // First try to load from page data
        const modelKeyFromPage = document.body.dataset.modelKey;
        if (modelKeyFromPage) {
            this.setDropdownValue(modelKeyFromPage);
            console.log('Initialized model from page data:', modelKeyFromPage);
        }
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Listen to left menu submenu options
        if (this.modelSubmenu) {
            const modelOptions = this.modelSubmenu.querySelectorAll('.submenu-option');
            modelOptions.forEach(option => {
                option.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const value = option.getAttribute('data-value');
                    this.updateModel(value);
                    
                    // Update UI to show selected state
                    modelOptions.forEach(opt => opt.classList.remove('selected'));
                    option.classList.add('selected');
                    
                    // Update the status display
                    const modelText = option.querySelector('span').textContent;
                    const currentModelLeft = document.getElementById('current-model-left');
                    if (currentModelLeft) {
                        currentModelLeft.textContent = modelText;
                    }
                });
            });
        }
        
        // Keep old dropdown listener if it exists
        if (this.modelDropdown) {
            // For custom dropdown
            if (this.modelDropdown.classList.contains('custom-dropdown-button')) {
                this.modelDropdown.addEventListener('dropdownChange', (e) => {
                    this.updateModel(e.detail.value);
                });
            } else if (this.modelDropdown.tagName === 'SELECT') {
                // Fallback for old select dropdown
                this.modelDropdown.addEventListener('change', (e) => {
                    this.updateModel(e.target.value);
                });
            }
        }
    }


    async updateModel(selectedModel) {
        try {
            const response = await fetch('/api/user/model-selection/', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    selected_model: selectedModel
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    console.log('Model updated successfully:', data.message);
                    // this.showSuccessMessage(data.message);
                } else {
                    console.error('Failed to update model:', data.error);
                    this.showErrorMessage(data.error);
                }
            } else {
                const errorData = await response.json();
                console.error('Failed to update model:', errorData.error);
                this.showErrorMessage(errorData.error || 'Failed to update model');
            }
        } catch (error) {
            console.error('Error updating model:', error);
            this.showErrorMessage('Network error occurred while updating model');
        }
    }

    setDropdownValue(selectedModel) {
        // Update left menu submenu
        if (this.modelSubmenu) {
            const modelOptions = this.modelSubmenu.querySelectorAll('.submenu-option');
            modelOptions.forEach(option => {
                if (option.getAttribute('data-value') === selectedModel) {
                    option.classList.add('selected');
                    // Update the status display
                    const modelText = option.querySelector('span').textContent;
                    const currentModelLeft = document.getElementById('current-model-left');
                    if (currentModelLeft) {
                        currentModelLeft.textContent = modelText;
                    }
                } else {
                    option.classList.remove('selected');
                }
            });
        }
        
        // For custom dropdown (if it still exists)
        if (typeof setCustomDropdownValue === 'function' && this.modelDropdown) {
            setCustomDropdownValue('model-dropdown', selectedModel);
        } else if (this.modelDropdown && this.modelDropdown.tagName === 'SELECT') {
            // Fallback for old select dropdown
            // Check if the model exists in the dropdown options
            const optionExists = Array.from(this.modelDropdown.options).some(option => 
                option.value === selectedModel
            );
            
            if (optionExists) {
                this.modelDropdown.value = selectedModel;
            } else {
                console.warn('Model not found in dropdown options:', selectedModel);
                // Default to first option if selected model not found
                this.modelDropdown.value = this.modelDropdown.options[0].value;
            }
        }
    }

    showSuccessMessage(message) {
        // Create a temporary success notification
        const notification = document.createElement('div');
        notification.className = 'model-notification success';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4CAF50;
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            z-index: 1000;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;

        document.body.appendChild(notification);

        // Remove after 3 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 3000);
    }

    showErrorMessage(message) {
        // Create a temporary error notification
        const notification = document.createElement('div');
        notification.className = 'model-notification error';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #f44336;
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            z-index: 1000;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;

        document.body.appendChild(notification);

        // Remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    getCSRFToken() {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
        return csrfToken ? csrfToken.value : '';
    }
}

// Initialize model handler when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.userAuthenticated === 'true') {
        new ModelHandler();
    }
}); 
/* ==== End: model-handler.js ==== */

/* ==== Begin: turbo-handler.js ==== */
class TurboHandler {
    constructor() {
        this.turboToggle = document.getElementById('turbo-mode-toggle');
        this.init();
    }

    init() {
        // First try to load from page data
        const turboModeFromPage = document.body.dataset.turboMode === 'true';
        if (this.turboToggle) {
            this.turboToggle.checked = turboModeFromPage;
            console.log('Initialized turbo mode from page data:', turboModeFromPage);
        }
        
        // Setup event listeners after initialization
        this.setupEventListeners();
    }

    setupEventListeners() {
        if (this.turboToggle) {
            this.turboToggle.addEventListener('change', (e) => {
                this.updateTurboMode(e.target.checked);
            });
        }
    }


    async updateTurboMode(turboMode) {
        try {
            const response = await fetch('/api/user/turbo-mode/', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    turbo_mode: turboMode
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    console.log('Turbo mode updated successfully:', data.message);
                } else {
                    console.error('Failed to update turbo mode:', data.error);
                    this.showErrorMessage(data.error);
                    // Revert the toggle state on error
                    this.turboToggle.checked = !turboMode;
                }
            } else {
                const errorData = await response.json();
                console.error('Failed to update turbo mode:', errorData.error);
                this.showErrorMessage(errorData.error || 'Failed to update turbo mode');
                // Revert the toggle state on error
                this.turboToggle.checked = !turboMode;
            }
        } catch (error) {
            console.error('Error updating turbo mode:', error);
            this.showErrorMessage('Network error occurred while updating turbo mode');
            // Revert the toggle state on error
            this.turboToggle.checked = !turboMode;
        }
    }

    showErrorMessage(message) {
        // Create a temporary error notification
        const notification = document.createElement('div');
        notification.className = 'turbo-notification error';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #f44336;
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            z-index: 1000;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;

        document.body.appendChild(notification);

        // Remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    getCSRFToken() {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
        return csrfToken ? csrfToken.value : '';
    }
}

// Initialize turbo handler when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.userAuthenticated === 'true') {
        new TurboHandler();
    }
});
/* ==== End: turbo-handler.js ==== */

/* ==== Begin: app-loader.js ==== */
/**
 * App Loader JavaScript
 * Handles loading the app running on the sandbox port into an iframe
 * NOTE: This file is now deprecated in favor of the loadAppPreview function in artifacts-loader.js
 * which uses ServerConfig data instead of sandbox port mappings.
 */

// Create a self-contained module for the app loader to avoid scope issues
(function() {
    // Flag to track if loadAppPreview has been defined
    let isAppPreviewDefined = false;

    // Main initialization function - now disabled to avoid conflicts
    function initAppLoader() {
        console.log('[AppLoader] App loader initialization disabled - using artifacts-loader.js implementation');
        
        // Don't override loadAppPreview if it already exists in ArtifactsLoader
        if (window.ArtifactsLoader && window.ArtifactsLoader.loadAppPreview) {
            console.log('[AppLoader] loadAppPreview already defined in ArtifactsLoader, skipping override');
            return;
        }
        
        // Only define if ArtifactsLoader doesn't have it yet (fallback)
        if (window.ArtifactsLoader && !window.ArtifactsLoader.loadAppPreview) {
            console.log('[AppLoader] Defining fallback loadAppPreview function (sandbox-based)');
            
            /**
             * FALLBACK: Load running app from the sandbox port for the current project or conversation
             * This is a fallback implementation that uses sandbox port mappings
             * @param {number} projectId - The ID of the current project
             * @param {number} conversationId - The ID of the current conversation (optional)
             */
            window.ArtifactsLoader.loadAppPreview = function(projectId, conversationId) {
                console.log(`[AppLoader] FALLBACK loadAppPreview called with project ID: ${projectId}, conversation ID: ${conversationId}`);
                
                if (!projectId && !conversationId) {
                    console.warn('[AppLoader] No project ID or conversation ID provided for loading app');
                    return;
                }
                
                // Get elements
                const appTab = document.getElementById('apps');
                const appLoading = document.getElementById('app-loading');
                const appEmpty = document.getElementById('app-empty');
                const appFrameContainer = document.getElementById('app-frame-container');
                const appIframe = document.getElementById('app-iframe');
                
                if (!appTab || !appLoading || !appEmpty || !appFrameContainer || !appIframe) {
                    console.warn('[AppLoader] One or more app tab elements not found');
                    return;
                }
                
                // Show loading state
                appEmpty.style.display = 'none';
                appFrameContainer.style.display = 'none';
                appLoading.style.display = 'block';
                
                // Build the request data
                const requestData = {};
                if (projectId) {
                    requestData.project_id = projectId;
                } else if (conversationId) {
                    requestData.conversation_id = conversationId;
                }
                
                // Fetch sandbox information from the API
                const url = '/development/get_sandbox_info/';
                console.log(`[AppLoader] Fetching sandbox info from API: ${url}`, requestData);
                
                fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken(),
                    },
                    body: JSON.stringify(requestData)
                })
                .then(response => {
                    console.log(`[AppLoader] Sandbox info API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[AppLoader] Sandbox info API data received:', data);
                    
                    // Check if port mappings exist and not empty
                    if (!data.port_mappings || data.port_mappings.length === 0) {
                        console.warn('[AppLoader] No port mappings found in API response');
                        showEmptyState("No port mappings available. Make sure your app is running on port 8000 in the sandbox.");
                        return;
                    }
                    
                    // Get the port from port mappings
                    const port = data.port_mappings[0].host_port;
                    
                    if (!port) {
                        // Show empty state if no port is available
                        console.warn('[AppLoader] Port value is missing or invalid in API response');
                        showEmptyState("No running app available. Make sure your app is running on port 8000 in the sandbox.");
                        return;
                    }
                    
                    // Construct the URL for the iframe
                    const appUrl = `http://${window.location.hostname}:${port}/`;
                    console.log(`[AppLoader] Loading app from URL: ${appUrl}`);
                    
                    // Set iframe source
                    appIframe.src = appUrl;
                    
                    // Add load event listeners
                    appIframe.onload = function() {
                        appLoading.style.display = 'none';
                        appFrameContainer.style.display = 'block';
                        console.log('[AppLoader] App iframe loaded successfully');
                    };
                    
                    appIframe.onerror = function(e) {
                        console.error('[AppLoader] Error loading app iframe:', e);
                        showErrorState("Error loading app. Please check if your app is running.");
                    };
                    
                    // Adjust the container to fill available space
                    appTab.style.overflow = 'hidden';
                })
                .catch(error => {
                    console.error('[AppLoader] Error fetching sandbox info:', error);
                    showErrorState(`Error loading app: ${error.message}`);
                });
                
                // Helper function to show the empty state
                function showEmptyState(message) {
                    appLoading.style.display = 'none';
                    appEmpty.style.display = 'block';
                    appEmpty.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">
                                <i class="fas fa-cube"></i>
                            </div>
                            <div class="empty-state-text">
                                ${message}
                            </div>
                        </div>
                    `;
                }
                
                // Helper function to show error state
                function showErrorState(message) {
                    appLoading.style.display = 'none';
                    appEmpty.style.display = 'block';
                    appEmpty.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                ${message}
                            </div>
                        </div>
                    `;
                }
            };
            
            isAppPreviewDefined = true;
            console.log('[AppLoader] FALLBACK loadAppPreview function has been defined');
        }
    }

    // Setup tab handler with better checking
    function setupTabHandler() {
        if (typeof window.loadTabData === 'function') {
            console.log('[AppLoader] Found loadTabData function, extending it to handle apps tab');
            
            const originalLoadTabData = window.loadTabData;
            window.loadTabData = function(tabId) {
                // Call the original function
                originalLoadTabData(tabId);
                
                console.log(`[AppLoader] Tab changed to: ${tabId}`);
                
                // Add support for app tab
                if (tabId === 'apps') {
                    console.log('[AppLoader] Apps tab selected, loading app preview');
                    
                    // Check if ArtifactsLoader has the proper loadAppPreview function
                    if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadAppPreview === 'function') {
                        console.log('[AppLoader] Using ArtifactsLoader.loadAppPreview (preferred)');
                        
                        // Get project or conversation ID
                        const projectId = window.getCurrentProjectId ? window.getCurrentProjectId() : null;
                        const conversationId = window.getCurrentConversationId ? window.getCurrentConversationId() : null;
                        
                        console.log(`[AppLoader] Project ID: ${projectId}, Conversation ID: ${conversationId}`);
                        window.ArtifactsLoader.loadAppPreview(projectId, conversationId);
                    } else {
                        // If ArtifactsLoader doesn't exist yet or loadAppPreview isn't defined, try to initialize fallback
                        console.log('[AppLoader] ArtifactsLoader or loadAppPreview not ready, initializing fallback');
                        initAppLoader();
                        
                        // Get project or conversation ID
                        const projectId = window.getCurrentProjectId ? window.getCurrentProjectId() : null;
                        const conversationId = window.getCurrentConversationId ? window.getCurrentConversationId() : null;
                        
                        console.log(`[AppLoader] Project ID: ${projectId}, Conversation ID: ${conversationId}`);
                        
                        if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadAppPreview === 'function') {
                            window.ArtifactsLoader.loadAppPreview(projectId, conversationId);
                        } else {
                            console.error('[AppLoader] loadAppPreview function not available despite initialization attempt');
                        }
                    }
                }
            };
            
            return true;
        }
        
        return false;
    }

    // Helper function to get CSRF token
    function getCSRFToken() {
        let csrfToken = null;
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const cookiePair = cookie.trim().split('=');
            if (cookiePair[0] === 'csrftoken') {
                csrfToken = decodeURIComponent(cookiePair[1]);
                break;
            }
        }
        return csrfToken;
    }

    // Helper functions to get project and conversation IDs
    function getCurrentProjectId() {
        // Use the same logic as extractProjectIdFromPath in chat.js
        const pathParts = window.location.pathname.split('/').filter(part => part);
        if (pathParts.length >= 3 && pathParts[0] === 'chat' && pathParts[1] === 'project') {
            return pathParts[2];
        }
        
        throw new Error('No project ID found in path. Expected format: /chat/project/{id}/');
    }

    function getCurrentConversationId() {
        return window.getCurrentConversationId ? window.getCurrentConversationId() : 
               (window.conversation_id || (window.CONVERSATION_DATA && window.CONVERSATION_DATA.id));
    }

    // Initialize on DOMContentLoaded
    document.addEventListener('DOMContentLoaded', function() {
        // Initial attempt to initialize
        initAppLoader();
        
        // Try to set up the tab handler 
        if (!setupTabHandler()) {
            console.log('[AppLoader] loadTabData not available yet, will retry shortly');
            
            // If not available, try again in a short while
            let attempts = 0;
            const maxAttempts = 5;
            const checkInterval = setInterval(function() {
                attempts++;
                if (setupTabHandler()) {
                    console.log('[AppLoader] Successfully set up tab handler after waiting');
                    clearInterval(checkInterval);
                } else if (attempts >= maxAttempts) {
                    console.warn('[AppLoader] loadTabData not available after maximum attempts - this is not critical');
                    clearInterval(checkInterval);
                    // Define a basic loadTabData if it doesn't exist
                    if (typeof window.loadTabData !== 'function') {
                        window.loadTabData = function(tabId) {
                            console.log(`[AppLoader] Basic loadTabData called for tab: ${tabId}`);
                            if (tabId === 'apps' && window.ArtifactsLoader && window.ArtifactsLoader.loadAppPreview) {
                                const projectId = window.currentProjectId || getCurrentProjectId();
                                if (projectId) {
                                    window.ArtifactsLoader.loadAppPreview(projectId);
                                }
                            }
                        };
                    }
                }
            }, 1000);
        }
        
        // Add direct click handler to the apps tab button as a backup
        document.addEventListener('click', function(event) {
            const target = event.target.closest('.tab-button[data-tab="apps"]');
            if (target) {
                console.log('[AppLoader] Apps tab button clicked directly');
                
                // Try to initialize if not already done
                if (!window.ArtifactsLoader || !window.ArtifactsLoader.loadAppPreview) {
                    console.log('[AppLoader] Initializing from click handler');
                    initAppLoader();
                }
                
                // Get project or conversation ID
                const projectId = getCurrentProjectId();
                const conversationId = getCurrentConversationId();
                
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadAppPreview === 'function') {
                    console.log('[AppLoader] Calling loadAppPreview from direct click handler');
                    window.ArtifactsLoader.loadAppPreview(projectId, conversationId);
                } else {
                    console.error('[AppLoader] loadAppPreview still not available after direct click');
                }
            }
        });
        
        // Additional safety: check every few seconds until ArtifactsLoader is available
        // This helps with pages where the ArtifactsLoader is loaded after our script
        if (!window.ArtifactsLoader) {
            console.log('[AppLoader] Setting up interval to check for ArtifactsLoader');
            let loaderAttempts = 0;
            const maxLoaderAttempts = 10;
            const loaderInterval = setInterval(function() {
                loaderAttempts++;
                if (window.ArtifactsLoader && !isAppPreviewDefined) {
                    console.log('[AppLoader] ArtifactsLoader found through interval check');
                    initAppLoader();
                    clearInterval(loaderInterval);
                } else if (isAppPreviewDefined || loaderAttempts >= maxLoaderAttempts) {
                    console.log('[AppLoader] Stopping interval checks - found:', isAppPreviewDefined);
                    clearInterval(loaderInterval);
                }
            }, 2000);
        }
    });
})(); 
/* ==== End: app-loader.js ==== */
