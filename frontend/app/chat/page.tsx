'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import ArtifactsPanel from '@/components/ArtifactsPanel';
import { useAuth } from '@/app/context/AuthContext';
import { buildApiUrl, buildWsUrl } from '@/app/lib/config';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  streaming?: boolean;
}

interface SidebarProject {
  id: string;
  name: string;
  icon?: string;
}

interface SidebarConversation {
  id: string;
  title: string;
  updatedAt?: string;
}

interface ArtifactDocument {
  id: string;
  name: string;
  content?: string | null;
  updated_at?: string | null;
  file_type?: string;
}

interface ArtifactTask {
  id: number | string;
  name: string;
  status: string;
  priority?: string;
  description?: string;
}

export default function ChatPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialProjectParam = searchParams.get('project');

  const { user, loading, fetchWithAuth, accessToken } = useAuth();

  const [projects, setProjects] = useState<SidebarProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);

  const [conversations, setConversations] = useState<SidebarConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const [socketReady, setSocketReady] = useState(false);

  const [showArtifacts, setShowArtifacts] = useState(false);
  const [documents, setDocuments] = useState<ArtifactDocument[]>([]);
  const [tasks, setTasks] = useState<ArtifactTask[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [loadingTasks, setLoadingTasks] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace('/auth');
    }
  }, [user, loading, router]);

  const loadProjects = useCallback(async () => {
    setLoadingProjects(true);
    try {
      const response = await fetchWithAuth(buildApiUrl('projects/'));
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data?.error || 'Unable to load projects');
      }
      const data = (await response.json()) as Array<{ id: string; name: string; icon?: string }>;
      setProjects(data);
      if (data.length > 0) {
        const preferred = data.find((project) => project.id === initialProjectParam);
        setSelectedProjectId((prev) => prev ?? preferred?.id ?? data[0].id);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setLoadingProjects(false);
    }
  }, [fetchWithAuth, initialProjectParam]);

  useEffect(() => {
    if (!user || loading) return;
    loadProjects();
  }, [user, loading, loadProjects]);

  const loadProjectArtifacts = useCallback(
    async (projectId: string) => {
      setLoadingDocuments(true);
      setLoadingTasks(true);

      try {
        const [docsResponse, tasksResponse] = await Promise.all([
          fetchWithAuth(buildApiUrl(`projects/${projectId}/documents/`)),
          fetchWithAuth(buildApiUrl(`projects/${projectId}/checklist/`)),
        ]);

        if (docsResponse.ok) {
          const docsData = (await docsResponse.json()) as ArtifactDocument[];
          setDocuments(docsData);
        } else {
          setDocuments([]);
        }

        if (tasksResponse.ok) {
          const tasksData = (await tasksResponse.json()) as ArtifactTask[];
          setTasks(tasksData);
        } else {
          setTasks([]);
        }
      } catch (error) {
        console.error(error);
        setDocuments([]);
        setTasks([]);
      } finally {
        setLoadingDocuments(false);
        setLoadingTasks(false);
      }
    },
    [fetchWithAuth]
  );

  const loadConversations = useCallback(
    async (projectId: string) => {
      try {
        const response = await fetchWithAuth(buildApiUrl(`projects/${projectId}/conversations/`));
        if (!response.ok) {
          throw new Error('Failed to load conversations');
        }
        const data = (await response.json()) as Array<{ id: string; title: string; updated_at?: string }>;
        const mapped: SidebarConversation[] = data.map((item) => ({
          id: String(item.id),
          title: item.title || `Conversation ${item.id}`,
          updatedAt: item.updated_at,
        }));
        setConversations(mapped);
        if (mapped.length > 0) {
          setActiveConversationId((prev) => prev ?? mapped[0].id);
        } else {
          const createResponse = await fetchWithAuth(buildApiUrl('conversations/'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: projectId }),
          });
          const created = await createResponse.json();
          if (!createResponse.ok) {
            throw new Error(created?.error || 'Failed to create conversation');
          }
          const newConversation = {
            id: String(created.id),
            title: created.title || `Conversation ${created.id}`,
            updatedAt: created.updated_at,
          };
          setConversations([newConversation]);
          setActiveConversationId(newConversation.id);
        }
      } catch (error) {
        console.error(error);
        setConversations([]);
      }
    },
    [fetchWithAuth]
  );

  useEffect(() => {
    if (!selectedProjectId) return;
    loadProjectArtifacts(selectedProjectId);
    loadConversations(selectedProjectId);
  }, [selectedProjectId, loadProjectArtifacts, loadConversations]);

  useEffect(() => {
    if (!selectedProjectId || !activeConversationId || !accessToken) {
      if (socketRef.current) {
        socketRef.current.close(1000);
        socketRef.current = null;
      }
      setSocketReady(false);
      return;
    }

    if (socketRef.current) {
      socketRef.current.close(1000);
      socketRef.current = null;
    }
    setSocketReady(false);
    setMessages([]);
    setConnectionError(null);

    const url = new URL(buildWsUrl('ws/chat/'));
    url.searchParams.set('token', accessToken);
    url.searchParams.set('project_id', selectedProjectId);
    url.searchParams.set('conversation_id', activeConversationId);

    const ws = new WebSocket(url.toString());
    socketRef.current = ws;

    ws.onopen = () => {
      setSocketReady(true);
      setConnectionError(null);
    };

    ws.onclose = (event) => {
      if (socketRef.current === ws) {
        socketRef.current = null;
        setSocketReady(false);
      }
      if (!event.wasClean) {
        setConnectionError('Chat connection lost. Trying to reconnect…');
      }
    };

    ws.onerror = () => {
      setConnectionError('Unable to connect to chat server.');
      setSocketReady(false);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case 'chat_history': {
          const history: ChatMessage[] = (data.messages as Array<{ role: 'user' | 'assistant'; content: string; timestamp: string }>).map(
            (msg, index) => ({
              id: `history-${index}`,
              role: msg.role,
              content: msg.content ?? '',
              timestamp: msg.timestamp ?? new Date().toISOString(),
            })
          );
          setMessages(history);
          break;
        }
        case 'message': {
          const newMessage: ChatMessage = {
            id: `${data.sender}-${Date.now()}`,
            role: data.sender === 'assistant' ? 'assistant' : 'user',
            content: data.message ?? '',
            timestamp: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, newMessage]);
          break;
        }
        case 'ai_chunk': {
          if (!data.chunk && !data.is_final) {
            break;
          }
          setMessages((prev) => {
            const next = [...prev];
            if (!data.is_final) {
              const last = next[next.length - 1];
              if (last && last.role === 'assistant' && last.streaming) {
                last.content += data.chunk ?? '';
              } else {
                next.push({
                  id: `assistant-stream-${Date.now()}`,
                  role: 'assistant',
                  content: data.chunk ?? '',
                  timestamp: new Date().toISOString(),
                  streaming: true,
                });
              }
            } else {
              const last = next[next.length - 1];
              if (last && last.role === 'assistant' && last.streaming) {
                last.content += data.chunk ?? '';
                last.streaming = false;
              } else {
                next.push({
                  id: `assistant-${Date.now()}`,
                  role: 'assistant',
                  content: data.chunk ?? '',
                  timestamp: new Date().toISOString(),
                });
              }
            }
            return next;
          });
          break;
        }
        case 'error': {
          setConnectionError(data.message || 'Chat error occurred.');
          break;
        }
        default:
          break;
      }
    };

    return () => {
      if (socketRef.current === ws) {
        socketRef.current = null;
        setSocketReady(false);
      }
      ws.close(1000);
    };
  }, [selectedProjectId, activeConversationId, accessToken]);

  const sendMessage = useCallback(async () => {
    const socket = socketRef.current;
    if (!inputValue.trim() || !socket || socket.readyState !== WebSocket.OPEN || !selectedProjectId) {
      return;
    }

    setIsSending(true);

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputValue,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);

    try {
      socket.send(
        JSON.stringify({
          type: 'message',
          message: inputValue,
          conversation_id: activeConversationId,
          project_id: selectedProjectId,
        })
      );
      setInputValue('');
    } catch (error) {
      console.error('Failed to send message', error);
      setConnectionError('Failed to send message.');
    } finally {
      setIsSending(false);
    }
  }, [inputValue, activeConversationId, selectedProjectId]);

  const handleFormSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      void sendMessage();
    },
    [sendMessage]
  );

  const handleSelectConversation = useCallback(
    (conversationId: string) => {
      setActiveConversationId(conversationId);
      setMessages([]);
    },
    []
  );

  const sidebarConversations = useMemo(() => conversations, [conversations]);

  const sidebarProjects = useMemo(() => projects, [projects]);

  return (
    <div className="flex h-screen bg-[var(--chat-bg)]">
      <Sidebar
        conversations={sidebarConversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={() => {
          if (!selectedProjectId) return;
          fetchWithAuth(buildApiUrl('conversations/'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: selectedProjectId }),
          })
            .then(async (response) => {
              const data = await response.json();
              if (!response.ok || !data?.id) {
                throw new Error(data?.error || 'Unable to create conversation');
              }
              const newConversation = {
                id: String(data.id),
                title: data.title || `Conversation ${data.id}`,
                updatedAt: data.updated_at,
              };
              setConversations((prev) => [newConversation, ...prev]);
              setActiveConversationId(newConversation.id);
            })
            .catch(() => setConnectionError('Unable to create a new conversation.'));
        }}
        projects={sidebarProjects}
        activeProjectId={selectedProjectId}
        onSelectProject={(projectId) => {
          setSelectedProjectId(projectId);
          setActiveConversationId(null);
          setMessages([]);
        }}
      />

      <div className="flex-1 flex flex-col">
        <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-gray-900">
              {projects.find((project) => project.id === selectedProjectId)?.name || 'Select a project'}
            </h1>
            {connectionError && <p className="text-xs text-red-600 mt-1">{connectionError}</p>}
          </div>
          <button
            onClick={() => setShowArtifacts((prev) => !prev)}
            className={`p-2 rounded-lg transition-colors ${
              showArtifacts ? 'bg-purple-100 text-purple-600' : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
            </svg>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          {loadingProjects ? (
            <div className="h-full flex items-center justify-center text-gray-500">Loading projects…</div>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <h2 className="text-3xl font-bold text-gray-900 mb-2">LFG 🚀🚀</h2>
              <p className="text-gray-600">Start a conversation with the AI assistant below.</p>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((message) => (
                <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] px-4 py-3 rounded-2xl ${
                      message.role === 'user'
                        ? 'bg-purple-600 text-white'
                        : 'bg-white border border-gray-200 text-gray-900'
                    }`}
                  >
                    <p className="text-[15px] leading-relaxed whitespace-pre-wrap">
                      {message.content || (message.streaming ? '…' : '')}
                    </p>
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="px-6 py-4 bg-[var(--chat-bg)]">
          <form onSubmit={handleFormSubmit} className="max-w-3xl mx-auto">
            <div className="relative bg-white rounded-2xl shadow-sm">
              <textarea
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void sendMessage();
                  }
                }}
                placeholder="Type your message here..."
                className="w-full pl-4 pr-32 pt-3 pb-12 text-[15px] text-gray-900 placeholder-gray-400 resize-none outline-none bg-transparent rounded-2xl"
                rows={1}
                style={{ minHeight: '52px' }}
                disabled={!selectedProjectId || isSending}
              />

              <div className="absolute right-3 bottom-3 flex items-center gap-2">
                <button
                  type="submit"
                  disabled={!inputValue.trim() || !selectedProjectId || isSending || !socketReady}
                  className="p-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      {showArtifacts && (
        <ArtifactsPanel
          isOpen={showArtifacts}
          onClose={() => setShowArtifacts(false)}
          documents={documents}
          tasks={tasks}
          loadingDocuments={loadingDocuments}
          loadingTasks={loadingTasks}
        />
      )}
    </div>
  );
}
