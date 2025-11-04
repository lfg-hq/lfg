'use client';

import { useMemo, useRef, useState } from 'react';

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

interface ArtifactsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  documents: ArtifactDocument[];
  tasks: ArtifactTask[];
  loadingDocuments?: boolean;
  loadingTasks?: boolean;
}

export default function ArtifactsPanel({
  isOpen,
  onClose,
  documents,
  tasks,
  loadingDocuments = false,
  loadingTasks = false,
}: ArtifactsPanelProps) {
  const [activeTab, setActiveTab] = useState<'docs' | 'tasks'>('docs');
  const [panelWidth, setPanelWidth] = useState(384);
  const [isResizing, setIsResizing] = useState(false);
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const documentList = useMemo(() => documents, [documents]);
  const taskList = useMemo(() => tasks, [tasks]);

  if (!isOpen) {
    return null;
  }

  return (
    <>
      <div
        className={`w-1 bg-gray-200 hover:bg-purple-400 cursor-col-resize transition-colors ${
          isResizing ? 'bg-purple-500' : ''
        }`}
        onMouseDown={() => setIsResizing(true)}
        onMouseUp={() => setIsResizing(false)}
      />

      <aside
        ref={panelRef}
        className="bg-white border-l border-gray-200 h-full flex flex-col"
        style={{ width: `${panelWidth}px` }}
        onMouseMove={(event) => {
          if (!isResizing) return;
          const newWidth = window.innerWidth - event.clientX;
          if (newWidth >= 320 && newWidth <= 800) {
            setPanelWidth(newWidth);
          }
        }}
        onMouseUp={() => setIsResizing(false)}
        onMouseLeave={() => setIsResizing(false)}
      >
        <div className="p-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
            </svg>
            <h2 className="font-semibold text-gray-900">Artifacts</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded transition-colors">
            <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

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

        {activeTab === 'docs' ? (
          <div className="flex-1 overflow-y-auto">
            {loadingDocuments ? (
              <div className="space-y-3 p-4">
                {[...Array(3)].map((_, index) => (
                  <div key={index} className="h-16 bg-gray-100 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : documentList.length > 0 ? (
              <div className="divide-y divide-gray-100">
                {documentList.map((doc) => {
                  const isExpanded = expandedDoc === doc.id;
                  return (
                    <div key={doc.id} className="p-4">
                      <button
                        onClick={() => setExpandedDoc((prev) => (prev === doc.id ? null : doc.id))}
                        className="w-full text-left"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-semibold text-gray-900">{doc.name}</p>
                            <p className="text-xs text-gray-500 mt-1">
                              {doc.updated_at ? `Updated ${new Date(doc.updated_at).toLocaleString()}` : 'Draft'}
                            </p>
                          </div>
                          <svg
                            className={`w-4 h-4 text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </div>
                      </button>
                      {isExpanded && doc.content && (
                        <div className="mt-3 bg-gray-50 border border-gray-200 rounded-lg p-3 text-sm text-gray-700 whitespace-pre-wrap max-h-64 overflow-y-auto">
                          {doc.content}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full px-6 text-center text-gray-500">
                <svg className="w-10 h-10 mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21H5a2 2 0 01-2-2V7a2 2 0 012-2h4l2-2h6a2 2 0 012 2v12a2 2 0 01-2 2z" />
                </svg>
                <p className="text-sm">No documents yet. Generate PRDs, technical plans, or upload files in chat.</p>
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            {loadingTasks ? (
              <div className="space-y-3 p-4">
                {[...Array(4)].map((_, index) => (
                  <div key={index} className="h-14 bg-gray-100 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : taskList.length > 0 ? (
              <ul className="divide-y divide-gray-100">
                {taskList.map((task) => (
                  <li key={task.id} className="px-4 py-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{task.name}</p>
                        {task.description && (
                          <p className="text-xs text-gray-500 mt-1 line-clamp-2">{task.description}</p>
                        )}
                      </div>
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          task.status === 'done'
                            ? 'bg-green-100 text-green-700'
                            : task.status === 'in_progress'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-yellow-100 text-yellow-700'
                        }`}
                      >
                        {task.status.replace('_', ' ')}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex flex-col items-center justify-center h-full px-6 text-center text-gray-500">
                <svg className="w-10 h-10 mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                </svg>
                <p className="text-sm">No tasks yet. Ask the assistant to create tickets or sync from Linear.</p>
              </div>
            )}
          </div>
        )}
      </aside>
    </>
  );
}
