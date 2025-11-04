
'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';

interface SidebarConversation {
  id: string;
  title: string;
  updatedAt?: string;
}

interface SidebarProject {
  id: string;
  name: string;
  icon?: string;
}

interface SidebarProps {
  conversations: SidebarConversation[];
  activeConversationId?: string | null;
  onSelectConversation: (conversationId: string) => void;
  onNewChat: () => void;
  projects?: SidebarProject[];
  activeProjectId?: string | null;
  onSelectProject?: (projectId: string) => void;
}

export default function Sidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  projects = [],
  activeProjectId,
  onSelectProject,
}: SidebarProps) {
  const [isMinimized, setIsMinimized] = useState(false);

  const sortedConversations = useMemo(() => {
    return [...conversations].sort((a, b) => {
      if (a.id === activeConversationId) return -1;
      if (b.id === activeConversationId) return 1;
      if (a.updatedAt && b.updatedAt) {
        return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
      }
      return a.title.localeCompare(b.title);
    });
  }, [conversations, activeConversationId]);

  return (
    <aside
      className={`${
        isMinimized ? 'w-16' : 'w-64'
      } bg-white border-r border-gray-200 h-screen flex flex-col transition-all duration-300`}
    >
      {/* Header */}
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        {!isMinimized && (
          <Link href="/" className="flex items-center space-x-2">
            <span className="text-xl font-bold text-purple-600">
              LFG
            </span>
            <span>🚀</span>
          </Link>
        )}
        <button
          onClick={() => setIsMinimized(!isMinimized)}
          className="p-1 hover:bg-gray-100 rounded transition-colors"
        >
          <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {isMinimized ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            )}
          </svg>
        </button>
      </div>

      {/* New Chat Button */}
      <div className="p-4">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm font-medium"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {!isMinimized && <span>New Chat</span>}
        </button>
      </div>

      {/* Project Selection */}
      {!isMinimized && projects.length > 0 && (
        <div className="px-4">
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Active Project
          </label>
          <div className="space-y-2">
            {projects.map((project) => (
              <button
                key={project.id}
                onClick={() => onSelectProject?.(project.id)}
                className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors border ${
                  project.id === activeProjectId
                    ? 'bg-purple-50 border-purple-200 text-purple-700'
                    : 'border-transparent text-gray-700 hover:bg-gray-100 hover:text-gray-900'
                }`}
              >
                <span className="text-lg">{project.icon ?? '🚀'}</span>
                <span className="truncate">{project.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Navigation */}
      {!isMinimized && (
        <nav className="flex-1 overflow-y-auto px-2">
          <div className="mb-4">
            <h3 className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Recent Conversations
            </h3>
            <div className="space-y-1">
              {sortedConversations.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => onSelectConversation(conv.id)}
                  className={`w-full text-left px-3 py-2 text-sm rounded-lg transition-colors truncate ${
                    conv.id === activeConversationId
                      ? 'bg-purple-50 text-purple-600'
                      : 'text-gray-700 hover:bg-purple-50 hover:text-purple-600'
                  }`}
                >
                  {conv.title}
                </button>
              ))}
              {sortedConversations.length === 0 && (
                <p className="px-3 py-4 text-xs text-gray-500">No conversations yet. Start a new one!</p>
              )}
            </div>
          </div>
        </nav>
      )}

      {/* Bottom Navigation */}
      <div className="border-t border-gray-200 p-2">
        <Link
          href="/tickets"
          className="flex items-center gap-3 px-3 py-2 text-sm text-gray-700 hover:bg-purple-50 hover:text-purple-600 rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {!isMinimized && <span>Tickets</span>}
        </Link>
        <Link
          href="/projects"
          className="flex items-center gap-3 px-3 py-2 text-sm text-gray-700 hover:bg-purple-50 hover:text-purple-600 rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
          {!isMinimized && <span>Projects</span>}
        </Link>
        <Link
          href="/settings"
          className="flex items-center gap-3 px-3 py-2 text-sm text-gray-700 hover:bg-purple-50 hover:text-purple-600 rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          {!isMinimized && <span>Settings</span>}
        </Link>
      </div>
    </aside>
  );
}
