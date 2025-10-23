'use client';

import { useState, useRef, useEffect } from 'react';

export default function ArtifactsPanel({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [activeTab, setActiveTab] = useState<'docs' | 'tasks'>('docs');
  const [panelWidth, setPanelWidth] = useState(384); // 24rem = 384px
  const [isResizing, setIsResizing] = useState(false);
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const documents = [
    {
      id: '1',
      name: 'Technical Implementation Plan',
      type: 'technical-plan',
      owner: 'AI',
      modified: '2h ago',
      content: `# Technical Implementation Plan

## Architecture Overview
- **Frontend**: React Native with TypeScript
- **State Management**: Redux Toolkit
- **Backend**: Node.js + Express
- **Database**: PostgreSQL with Redis cache
- **Authentication**: Firebase Auth

## Core Components
1. Habit Management Module
2. Streak Tracking System
3. Notification Service
4. Analytics Dashboard

## Development Timeline
- Week 1-2: Setup and core data models
- Week 3-4: Habit CRUD operations
- Week 5-6: Streak tracking & notifications
- Week 7-8: Analytics and testing`
    },
    {
      id: '2',
      name: 'Competitor Analysis - iOS Habit Tracker',
      type: 'competitor-analysis',
      owner: 'AI',
      modified: '5h ago',
      content: `# Competitor Analysis

## Top Competitors
1. **Streaks** - $4.99
   - Minimalist design
   - 12 habit limit
   - iCloud sync

2. **Habitify** - Freemium
   - Unlimited habits (premium)
   - Rich analytics
   - Cross-platform

3. **Productive** - $4.99/month
   - Smart scheduling
   - Mood tracking
   - Team features

## Key Differentiators
- Focus on simplicity
- One-tap check-ins
- Beautiful visualizations`
    },
    {
      id: '3',
      name: 'Habit Tracker iOS - PRD',
      type: 'prd',
      owner: 'AI',
      modified: '1d ago',
      content: `# Product Requirements Document

## Product Overview
A minimalist habit tracking app for iOS that helps users build and maintain positive habits through simple daily check-ins and visual progress tracking.

## Target Users
- Age: 18-45
- Tech-savvy individuals
- Self-improvement enthusiasts
- Busy professionals

## Core Features
### Must Have (V1)
- Create/edit/delete habits
- Daily check-in interface
- Streak counter
- Basic statistics

### Nice to Have (V2)
- Reminders
- Habit categories
- Export data
- Widgets

## Success Metrics
- Daily Active Users (DAU)
- Average habits per user
- Retention rate (D7, D30)
- Check-in completion rate`
    },
  ];

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;

      const newWidth = window.innerWidth - e.clientX;
      if (newWidth >= 300 && newWidth <= 800) {
        setPanelWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  if (!isOpen) return null;

  return (
    <>
      {/* Resize Handle */}
      <div
        className={`w-1 bg-gray-200 hover:bg-purple-400 cursor-col-resize transition-colors ${
          isResizing ? 'bg-purple-500' : ''
        }`}
        onMouseDown={() => setIsResizing(true)}
      />

      <aside
        ref={panelRef}
        className="bg-white border-l border-gray-200 h-full flex flex-col"
        style={{ width: `${panelWidth}px` }}
      >
      {/* Header */}
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
          </svg>
          <h2 className="font-semibold text-gray-900">Artifacts</h2>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-gray-100 rounded transition-colors"
        >
          <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200">
        <button
          onClick={() => setActiveTab('docs')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            activeTab === 'docs'
              ? 'text-purple-600 border-b-2 border-purple-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Docs
        </button>
        <button
          onClick={() => setActiveTab('tasks')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            activeTab === 'tasks'
              ? 'text-purple-600 border-b-2 border-purple-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Task List
        </button>
      </div>

      {/* Search */}
      <div className="p-4 border-b border-gray-200">
        <div className="relative">
          <input
            type="text"
            placeholder="Search documents..."
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent outline-none text-sm"
          />
          <svg className="w-5 h-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
      </div>

      {/* Content */}
      {activeTab === 'docs' && (
        <div className="flex-1 overflow-y-auto p-4">
          {!expandedDoc ? (
            <>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-gray-700">Documents</h3>
                <button className="p-1 hover:bg-gray-100 rounded transition-colors">
                  <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>
              </div>

              <div className="space-y-2">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    onClick={() => setExpandedDoc(doc.id)}
                    className="p-3 border border-gray-200 rounded-lg hover:border-purple-300 hover:bg-purple-50/50 cursor-pointer transition-all group"
                  >
                    <div className="flex items-start gap-3">
                      <div className="p-2 bg-purple-100 rounded-lg group-hover:bg-purple-200 transition-colors">
                        <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                      </div>
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-medium text-gray-900 truncate">
                          {doc.name}
                        </h4>
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">
                            {doc.type}
                          </span>
                          <span className="text-xs text-gray-500">{doc.owner}</span>
                          <span className="text-xs text-gray-400">·</span>
                          <span className="text-xs text-gray-500">{doc.modified}</span>
                        </div>
                      </div>
                      <svg className="w-4 h-4 text-gray-400 group-hover:text-purple-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="h-full flex flex-col">
              {/* Document Header */}
              <div className="flex items-center gap-2 mb-4 pb-4 border-b border-gray-200">
                <button
                  onClick={() => setExpandedDoc(null)}
                  className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-gray-900 truncate">
                    {documents.find(d => d.id === expandedDoc)?.name}
                  </h3>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">
                      {documents.find(d => d.id === expandedDoc)?.type}
                    </span>
                  </div>
                </div>
                <button className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
                  <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                  </svg>
                </button>
              </div>

              {/* Document Content */}
              <div className="flex-1 overflow-y-auto">
                <div className="prose prose-sm max-w-none">
                  <pre className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">
                    {documents.find(d => d.id === expandedDoc)?.content}
                  </pre>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'tasks' && (
        <div className="flex-1 overflow-y-auto p-4">
          <div className="text-center py-12">
            <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <p className="text-gray-500">No tasks yet</p>
          </div>
        </div>
      )}
    </aside>
    </>
  );
}
