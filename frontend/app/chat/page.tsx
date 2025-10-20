'use client';

import { useState, useRef, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import ArtifactsPanel from '@/components/ArtifactsPanel';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'user',
      content: 'Can you help me design a mobile app for habit tracking?',
      timestamp: new Date(Date.now() - 3600000),
    },
    {
      id: '2',
      role: 'assistant',
      content: 'I\'d be happy to help you design a mobile app for habit tracking! Let me break down the key components we should consider:\n\n**Core Features:**\n- Daily habit checklist with custom habits\n- Streak tracking and visual progress indicators\n- Reminder notifications\n- Analytics and insights\n\n**User Experience:**\n- Clean, minimalist interface\n- Quick check-in process (< 5 seconds)\n- Motivational feedback\n- Dark and light theme options\n\nWould you like me to create a detailed PRD for this app?',
      timestamp: new Date(Date.now() - 3500000),
    },
    {
      id: '3',
      role: 'user',
      content: 'Yes, please create a PRD with technical implementation details.',
      timestamp: new Date(Date.now() - 3400000),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [selectedModel, setSelectedModel] = useState('GPT-5 mini');
  const [selectedRole, setSelectedRole] = useState('Analyst');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;

    const newMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages([...messages, newMessage]);
    setInputValue('');

    // Simulate AI response
    setTimeout(() => {
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'This is a dummy AI response. In a real application, this would connect to your backend API.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, aiMessage]);
    }, 1000);
  };

  return (
    <div className="flex h-screen bg-[var(--chat-bg)]">
      <Sidebar />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Project Header */}
        <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-900">Test Project</h1>
          <button
            onClick={() => setShowArtifacts(!showArtifacts)}
            className={`p-2 rounded-lg transition-colors ${
              showArtifacts
                ? 'bg-purple-100 text-purple-600'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
            </svg>
          </button>
        </header>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <h2 className="text-3xl font-bold text-gray-900 mb-2">LFG 🚀🚀</h2>
              <p className="text-gray-600">Start a conversation with the AI assistant below.</p>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] px-4 py-3 rounded-2xl ${
                      message.role === 'user'
                        ? 'bg-purple-600 text-white'
                        : 'bg-white border border-gray-200 text-gray-900'
                    }`}
                  >
                    <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{message.content}</p>
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="px-6 py-4 bg-[var(--chat-bg)]">
          <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
            <div className="relative bg-white rounded-2xl shadow-sm">
              {/* Left Actions */}
              <div className="absolute left-3 bottom-3 flex items-center gap-2 z-10">
                <button
                  type="button"
                  className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                  title="Upload file"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                  </svg>
                </button>
                <button
                  type="button"
                  className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                  title="Settings"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                  </svg>
                </button>
                <div className="flex items-center gap-1.5 text-xs text-gray-500">
                  <span className="text-purple-600 font-medium">{selectedRole}</span>
                  <span>•</span>
                  <span className="text-purple-600 font-medium">{selectedModel}</span>
                </div>
              </div>

              {/* Text Input */}
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                placeholder="Type your message here..."
                className="w-full pl-4 pr-32 pt-3 pb-12 text-[15px] text-gray-900 placeholder-gray-400 resize-none outline-none bg-transparent rounded-2xl"
                rows={1}
                style={{ minHeight: '52px' }}
              />

              {/* Right Actions */}
              <div className="absolute right-3 bottom-3 flex items-center gap-2">
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer hover:text-gray-700">
                    <input type="checkbox" className="w-3 h-3 text-purple-600 border-gray-300 rounded focus:ring-purple-500" />
                    Turbo
                  </label>
                </div>
                <button
                  type="button"
                  className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                  title="Voice input"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  </svg>
                </button>
                <button
                  type="submit"
                  disabled={!inputValue.trim()}
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

      {/* Artifacts Panel */}
      <ArtifactsPanel isOpen={showArtifacts} onClose={() => setShowArtifacts(false)} />
    </div>
  );
}
