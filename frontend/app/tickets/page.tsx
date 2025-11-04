'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/app/context/AuthContext';

type TicketPriority = 'urgent' | 'high' | 'medium' | 'low';

interface Ticket {
  id: string;
  title: string;
  status: string;
  priority: TicketPriority;
  description: string;
  assignee: string;
  dueDate?: string;
  tags: string[];
  order: number;
}

type ColumnColor = 'purple' | 'blue' | 'amber' | 'emerald' | 'rose' | 'slate';

interface ColumnDefinition {
  id: string;
  name: string;
  color: ColumnColor;
}

interface ColumnVisualStyle {
  dotClass: string;
  badgeBgClass: string;
  badgeTextClass: string;
  ringClass: string;
  softBgClass: string;
}

const columnVisualStyles: Record<ColumnColor, ColumnVisualStyle> = {
  purple: {
    dotClass: 'bg-purple-500',
    badgeBgClass: 'bg-purple-100',
    badgeTextClass: 'text-purple-700',
    ringClass: 'ring-purple-200',
    softBgClass: 'bg-purple-50/60',
  },
  blue: {
    dotClass: 'bg-sky-500',
    badgeBgClass: 'bg-sky-100',
    badgeTextClass: 'text-sky-700',
    ringClass: 'ring-sky-200',
    softBgClass: 'bg-sky-50/60',
  },
  amber: {
    dotClass: 'bg-amber-500',
    badgeBgClass: 'bg-amber-100',
    badgeTextClass: 'text-amber-700',
    ringClass: 'ring-amber-200',
    softBgClass: 'bg-amber-50/60',
  },
  emerald: {
    dotClass: 'bg-emerald-500',
    badgeBgClass: 'bg-emerald-100',
    badgeTextClass: 'text-emerald-700',
    ringClass: 'ring-emerald-200',
    softBgClass: 'bg-emerald-50/60',
  },
  rose: {
    dotClass: 'bg-rose-500',
    badgeBgClass: 'bg-rose-100',
    badgeTextClass: 'text-rose-700',
    ringClass: 'ring-rose-200',
    softBgClass: 'bg-rose-50/60',
  },
  slate: {
    dotClass: 'bg-slate-500',
    badgeBgClass: 'bg-slate-100',
    badgeTextClass: 'text-slate-700',
    ringClass: 'ring-slate-200',
    softBgClass: 'bg-slate-50/70',
  },
};

const priorityMeta: Record<
  TicketPriority,
  {
    label: string;
    icon: string;
    badgeBgClass: string;
    badgeTextClass: string;
  }
> = {
  urgent: { label: 'Urgent', icon: '⚡', badgeBgClass: 'bg-rose-100', badgeTextClass: 'text-rose-700' },
  high: { label: 'High', icon: '⬆️', badgeBgClass: 'bg-amber-100', badgeTextClass: 'text-amber-700' },
  medium: { label: 'Medium', icon: '⏳', badgeBgClass: 'bg-sky-100', badgeTextClass: 'text-sky-700' },
  low: { label: 'Low', icon: '🍃', badgeBgClass: 'bg-emerald-100', badgeTextClass: 'text-emerald-700' },
};

const initialColumns: ColumnDefinition[] = [
  { id: 'backlog', name: 'Backlog', color: 'slate' },
  { id: 'todo', name: 'To Do', color: 'purple' },
  { id: 'in_progress', name: 'In Progress', color: 'blue' },
  { id: 'in_review', name: 'In Review', color: 'amber' },
  { id: 'done', name: 'Done', color: 'emerald' },
];

const initialTickets: Ticket[] = [
  {
    id: 'LFG-104',
    title: 'Design ticket board templates',
    status: 'backlog',
    priority: 'medium',
    description: 'Create reusable board presets to mirror Linear, Jira, and Trello experiences.',
    assignee: 'Ravi Nair',
    tags: ['Design'],
    order: 0,
  },
  {
    id: 'LFG-108',
    title: 'Draft June launch narrative',
    status: 'backlog',
    priority: 'low',
    description: 'Partner with marketing and product to outline launch messaging and rollout plan.',
    assignee: 'Jules Martin',
    tags: ['Marketing'],
    order: 1,
  },
  {
    id: 'LFG-101',
    title: 'Implement onboarding flow',
    status: 'todo',
    priority: 'high',
    description: 'Ship the multi-step onboarding for new teams with role-based templates.',
    assignee: 'Maya Patel',
    dueDate: '2024-06-07',
    tags: ['Product', 'UX'],
    order: 0,
  },
  {
    id: 'LFG-105',
    title: 'Add GitHub PR sync',
    status: 'todo',
    priority: 'high',
    description: 'Automatically surface linked pull requests and branch status within tickets.',
    assignee: 'Sarah Lee',
    dueDate: '2024-06-08',
    tags: ['Integrations'],
    order: 1,
  },
  {
    id: 'LFG-102',
    title: 'Integrate billing usage charts',
    status: 'in_progress',
    priority: 'urgent',
    description: 'Expose new analytics API to power billing and usage dashboards with history.',
    assignee: 'Hugo Klein',
    dueDate: '2024-06-05',
    tags: ['Growth', 'Analytics'],
    order: 0,
  },
  {
    id: 'LFG-106',
    title: 'Record project level metrics',
    status: 'in_progress',
    priority: 'low',
    description: 'Capture deployment frequency and ticket lead time to power project insights.',
    assignee: 'Diego Martínez',
    tags: ['Platform', 'Data'],
    order: 1,
  },
  {
    id: 'LFG-103',
    title: 'Refactor chat message streaming',
    status: 'in_review',
    priority: 'medium',
    description: 'Stabilize websocket reconnection logic and ensure idempotent chunk delivery.',
    assignee: 'Lina Chen',
    dueDate: '2024-06-04',
    tags: ['Platform'],
    order: 0,
  },
  {
    id: 'LFG-107',
    title: 'Close workspace permissions audit',
    status: 'done',
    priority: 'medium',
    description: 'Finalize audit log exports and share the report with the compliance team.',
    assignee: 'Maya Patel',
    dueDate: '2024-05-30',
    tags: ['Security'],
    order: 0,
  },
];

const colorPalette: ColumnColor[] = ['purple', 'blue', 'amber', 'emerald', 'rose', 'slate'];

const fallbackColumnStyle = columnVisualStyles.purple;

const DropIndicator = ({ active }: { active: boolean }) => (
  <div
    className={`h-2 rounded-full transition-all duration-150 ${
      active ? 'opacity-100 bg-gradient-to-r from-purple-400 via-purple-500 to-purple-400' : 'opacity-0 bg-purple-200'
    }`}
  />
);

const getInitials = (name: string) => {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0) return '??';
  const first = parts[0]?.[0] ?? '';
  const last = parts[parts.length - 1]?.[0] ?? '';
  return (first + last).toUpperCase();
};

const formatDueDate = (input?: string) => {
  if (!input) return null;
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

const normalizeColumnOrders = (ticketList: Ticket[], columnIds: string[]) => {
  const uniqueColumnIds = Array.from(new Set(columnIds));
  uniqueColumnIds.forEach((columnId) => {
    const columnTickets = ticketList
      .filter((ticket) => ticket.status === columnId)
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    columnTickets.forEach((ticket, index) => {
      ticket.order = index;
    });
  });
};

export default function TicketsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  const [viewMode, setViewMode] = useState<'board' | 'list'>('board');
  const [columns, setColumns] = useState<ColumnDefinition[]>(initialColumns);
  const [tickets, setTickets] = useState<Ticket[]>(initialTickets);
  const [showColumnManager, setShowColumnManager] = useState(false);
  const [draggingTicketId, setDraggingTicketId] = useState<string | null>(null);
  const [dropIndicator, setDropIndicator] = useState<{ columnId: string; beforeTicketId?: string } | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace('/auth');
    }
  }, [loading, user, router]);

  const columnPosition = useMemo(() => {
    const map = new Map<string, number>();
    columns.forEach((column, index) => {
      map.set(column.id, index);
    });
    return map;
  }, [columns]);

  const columnStyleMap = useMemo(() => {
    const map = new Map<string, ColumnVisualStyle>();
    columns.forEach((column) => {
      map.set(column.id, columnVisualStyles[column.color] ?? fallbackColumnStyle);
    });
    return map;
  }, [columns]);

  const ticketsByColumn = useMemo(
    () =>
      columns.map((column) => ({
        column,
        tickets: tickets
          .filter((ticket) => ticket.status === column.id)
          .sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
      })),
    [columns, tickets]
  );

  const readyTickets = useMemo(() => {
    const sorted = tickets
      .filter((ticket) => columnPosition.has(ticket.status))
      .map((ticket) => ({ ...ticket }));
    sorted.sort((a, b) => {
      const columnOrder = (columnPosition.get(a.status) ?? 0) - (columnPosition.get(b.status) ?? 0);
      if (columnOrder !== 0) return columnOrder;
      return (a.order ?? 0) - (b.order ?? 0);
    });
    return sorted;
  }, [tickets, columnPosition]);

  const metrics = useMemo(() => {
    const active = tickets.filter((ticket) => ticket.status !== 'done').length;
    const inProgress = tickets.filter((ticket) => ticket.status === 'in_progress').length;
    const inReview = tickets.filter((ticket) => ticket.status === 'in_review').length;
    const completed = tickets.filter((ticket) => ticket.status === 'done').length;
    return [
      {
        label: 'Active tickets',
        value: active,
        description: 'Open issues across all stages',
      },
      {
        label: 'In progress',
        value: inProgress,
        description: 'Currently being worked on',
      },
      {
        label: 'In review',
        value: inReview,
        description: 'Awaiting approvals or QA',
      },
      {
        label: 'Completed',
        value: completed,
        description: 'Shipped in the current cycle',
      },
    ];
  }, [tickets]);

  const handleUpdateTicketStatus = (ticketId: string, status: string) => {
    setTickets((prev) => {
      const next = prev.map((ticket) => ({ ...ticket }));
      const target = next.find((ticket) => ticket.id === ticketId);
      if (!target) return prev;
      if (target.status === status) return prev;

      const sourceStatus = target.status;
      target.status = status;

      const targetTickets = next
        .filter((ticket) => ticket.status === status && ticket.id !== ticketId)
        .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
      targetTickets.push(target);
      targetTickets.forEach((ticket, index) => {
        ticket.order = index;
      });

      const sourceTickets = next
        .filter((ticket) => ticket.status === sourceStatus && ticket.id !== ticketId)
        .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
      sourceTickets.forEach((ticket, index) => {
        ticket.order = index;
      });

      return next;
    });
  };

  const handleDragStart = (event: React.DragEvent<HTMLElement>, ticketId: string) => {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', ticketId);
    setDraggingTicketId(ticketId);
  };

  const handleDragEnd = () => {
    setDraggingTicketId(null);
    setDropIndicator(null);
  };

  const handleDragOverColumn = (event: React.DragEvent<HTMLDivElement>, columnId: string) => {
    if (!draggingTicketId) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    setDropIndicator((current) => {
      if (current?.columnId === columnId && typeof current?.beforeTicketId === 'undefined') {
        return current;
      }
      return { columnId };
    });
  };

  const handleDragOverTicket = (
    event: React.DragEvent<HTMLElement>,
    columnId: string,
    ticketId: string
  ) => {
    if (!draggingTicketId || draggingTicketId === ticketId) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    setDropIndicator((current) => {
      if (current?.columnId === columnId && current?.beforeTicketId === ticketId) {
        return current;
      }
      return { columnId, beforeTicketId: ticketId };
    });
  };

  const finalizeDrop = (columnId: string, beforeTicketId?: string) => {
    if (!draggingTicketId) return;
    setTickets((prev) => {
      const next = prev.map((ticket) => ({ ...ticket }));
      const dragged = next.find((ticket) => ticket.id === draggingTicketId);
      if (!dragged) return prev;

      const sourceColumnId = dragged.status;
      const targetColumnId = columnId;

      const targetTickets = next
        .filter((ticket) => ticket.status === targetColumnId && ticket.id !== dragged.id)
        .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

      const insertIndex = beforeTicketId
        ? targetTickets.findIndex((ticket) => ticket.id === beforeTicketId)
        : targetTickets.length;

      dragged.status = targetColumnId;

      if (insertIndex === -1) {
        targetTickets.push(dragged);
      } else {
        targetTickets.splice(insertIndex, 0, dragged);
      }

      targetTickets.forEach((ticket, index) => {
        ticket.order = index;
      });

      if (sourceColumnId !== targetColumnId) {
        const sourceTickets = next
          .filter((ticket) => ticket.status === sourceColumnId && ticket.id !== dragged.id)
          .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
        sourceTickets.forEach((ticket, index) => {
          ticket.order = index;
        });
      }

      return next;
    });
    handleDragEnd();
  };

  const handleColumnDrop = (event: React.DragEvent<HTMLDivElement>, columnId: string) => {
    if (!draggingTicketId) return;
    event.preventDefault();
    event.stopPropagation();
    const beforeTicketId = dropIndicator?.columnId === columnId ? dropIndicator.beforeTicketId : undefined;
    finalizeDrop(columnId, beforeTicketId);
  };

  const handleCardDrop = (event: React.DragEvent<HTMLElement>, columnId: string, ticketId: string) => {
    if (!draggingTicketId) return;
    event.preventDefault();
    event.stopPropagation();
    finalizeDrop(columnId, ticketId);
  };

  const handleRenameColumn = (columnId: string, name: string) => {
    setColumns((prev) => prev.map((column) => (column.id === columnId ? { ...column, name } : column)));
  };

  const handleMoveColumn = (columnId: string, direction: 'up' | 'down') => {
    setColumns((prev) => {
      const index = prev.findIndex((column) => column.id === columnId);
      if (index === -1) return prev;
      const targetIndex = direction === 'up' ? index - 1 : index + 1;
      if (targetIndex < 0 || targetIndex >= prev.length) return prev;
      const next = [...prev];
      const [moved] = next.splice(index, 1);
      next.splice(targetIndex, 0, moved);
      return next;
    });
  };

  const handleRemoveColumn = (columnId: string) => {
    setColumns((prev) => {
      if (prev.length <= 1) return prev;
      const updated = prev.filter((column) => column.id !== columnId);
      if (updated.length === prev.length) return prev;
      const fallbackStatus = updated[0]?.id ?? prev[0].id;

      setTickets((existing) => {
        const next = existing.map((ticket) =>
          ticket.status === columnId ? { ...ticket, status: fallbackStatus } : { ...ticket }
        );
        normalizeColumnOrders(next, [columnId, fallbackStatus]);
        return next;
      });

      return updated;
    });
  };

  const handleAddColumn = () => {
    setColumns((prev) => {
      const color = colorPalette[prev.length % colorPalette.length];
      const newColumn: ColumnDefinition = {
        id: `custom-${Date.now()}`,
        name: `Column ${prev.length + 1}`,
        color,
      };
      return [...prev, newColumn];
    });
  };

  const activeDropColumnId = dropIndicator?.columnId;

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 via-white to-gray-100">
      <header className="bg-white/80 backdrop-blur border-b border-gray-200 sticky top-0 z-20">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-2xl font-semibold text-purple-600">LFG</span>
            <span className="text-2xl">🚀</span>
          </Link>
          <nav className="flex items-center gap-6 text-sm font-medium text-gray-600">
            <Link href="/projects" className="transition hover:text-gray-900">
              Projects
            </Link>
            <Link href="/chat" className="transition hover:text-gray-900">
              Chat
            </Link>
            <Link href="/tickets" className="text-purple-600">
              Tickets
            </Link>
            <Link href="/settings" className="transition hover:text-gray-900">
              Settings
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-purple-500" />
              <span>Workspace</span>
            </div>
            <h1 className="mt-1 flex items-center gap-3 text-3xl font-semibold text-gray-900">
              Ticket Workspace
              <span className="rounded-full bg-purple-100 px-2.5 py-1 text-xs font-medium text-purple-700">
                Linear-inspired flow
              </span>
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-gray-600">
              Stay aligned with a sleek, Linear-style board. Drag tickets between stages, fine-tune your workflow columns,
              and flip into list view for deep triage.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex items-center rounded-xl border border-gray-200 bg-white/80 p-1 shadow-sm">
              <button
                type="button"
                onClick={() => setViewMode('board')}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${
                  viewMode === 'board'
                    ? 'bg-purple-600 text-white shadow'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h4v12H4V6zm6 0h4v12h-4V6zm6 0h4v12h-4V6z" />
                </svg>
                Board
              </button>
              <button
                type="button"
                onClick={() => setViewMode('list')}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${
                  viewMode === 'list'
                    ? 'bg-purple-600 text-white shadow'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
                List
              </button>
            </div>
            <button
              type="button"
              onClick={() => setShowColumnManager(true)}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white/80 px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-100"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 012 2v2a2 2 0 01-2 2m0-6a2 2 0 00-2 2v2a2 2 0 002 2m-7 6a2 2 0 012-2h2a2 2 0 012 2m-6 0a2 2 0 002 2h2a2 2 0 002-2m6 0a2 2 0 012-2h2a2 2 0 012 2m-6 0a2 2 0 002 2h2a2 2 0 002-2" />
              </svg>
              Manage Columns
            </button>
          </div>
        </div>

        <section className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {metrics.map((metric) => (
            <div
              key={metric.label}
              className="rounded-2xl border border-gray-200 bg-white/80 px-5 py-4 shadow-sm transition hover:shadow-md"
            >
              <p className="text-xs font-medium uppercase tracking-wider text-gray-400">{metric.label}</p>
              <p className="mt-3 text-3xl font-semibold text-gray-900">{metric.value}</p>
              <p className="mt-2 text-xs text-gray-500">{metric.description}</p>
            </div>
          ))}
        </section>

        <section className="mt-10">
          {viewMode === 'board' ? (
            <div className="overflow-x-auto pb-10">
              <div className="flex min-w-max gap-5">
                {ticketsByColumn.map(({ column, tickets: columnTickets }) => {
                  const styles = columnStyleMap.get(column.id) ?? fallbackColumnStyle;
                  const isDropTarget = activeDropColumnId === column.id;
                  return (
                    <div key={column.id} className="w-80 flex-shrink-0">
                      <div
                        className={`flex h-full flex-col rounded-3xl border border-gray-100 bg-white/80 backdrop-blur-sm shadow-sm transition-all duration-200 ${
                          isDropTarget ? `ring-2 ${styles.ringClass} shadow-lg` : 'hover:shadow-md'
                        }`}
                      >
                        <div className="flex items-center justify-between px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className={`h-2.5 w-2.5 flex-shrink-0 rounded-full ${styles.dotClass}`} />
                            <span className="text-sm font-semibold text-gray-900">{column.name}</span>
                            <span className="text-xs font-medium text-gray-400">{columnTickets.length}</span>
                          </div>
                          <button
                            type="button"
                            className="rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
                            title="Add ticket"
                          >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                            </svg>
                          </button>
                        </div>
                        <div
                          className="flex-1 space-y-3 overflow-y-auto px-4 pb-4"
                          onDragOver={(event) => handleDragOverColumn(event, column.id)}
                          onDrop={(event) => handleColumnDrop(event, column.id)}
                        >
                          {columnTickets.map((ticket) => (
                            <div key={ticket.id} className="space-y-2">
                              <DropIndicator
                                active={
                                  dropIndicator?.columnId === column.id &&
                                  dropIndicator?.beforeTicketId === ticket.id
                                }
                              />
                              <article
                                draggable
                                onDragStart={(event) => handleDragStart(event, ticket.id)}
                                onDragEnd={handleDragEnd}
                                onDragOver={(event) => handleDragOverTicket(event, column.id, ticket.id)}
                                onDrop={(event) => handleCardDrop(event, column.id, ticket.id)}
                                className={`group rounded-2xl border border-gray-100 bg-white px-4 py-4 shadow-sm transition-all duration-200 ${
                                  draggingTicketId === ticket.id
                                    ? 'opacity-80 ring-2 ring-purple-200'
                                    : 'hover:shadow-md'
                                }`}
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div>
                                    <p className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">
                                      {ticket.id}
                                    </p>
                                    <h3 className="mt-1 text-sm font-semibold text-gray-900">
                                      {ticket.title}
                                    </h3>
                                  </div>
                                  <span
                                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                                      priorityMeta[ticket.priority].badgeBgClass
                                    } ${priorityMeta[ticket.priority].badgeTextClass}`}
                                  >
                                    {priorityMeta[ticket.priority].icon}
                                    {priorityMeta[ticket.priority].label}
                                  </span>
                                </div>
                                <p className="mt-2 text-sm text-gray-600 line-clamp-3">{ticket.description}</p>
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {ticket.tags.map((tag) => (
                                    <span
                                      key={tag}
                                      className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600"
                                    >
                                      #{tag}
                                    </span>
                                  ))}
                                </div>
                                <div className="mt-4 flex items-center justify-between text-xs text-gray-500">
                                  <div className="flex items-center gap-2">
                                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-purple-100 to-purple-200 text-[11px] font-semibold text-purple-700">
                                      {getInitials(ticket.assignee)}
                                    </div>
                                    <span className="font-medium text-gray-700">{ticket.assignee}</span>
                                  </div>
                                  {formatDueDate(ticket.dueDate) && (
                                    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600">
                                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V4m8 3V4m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                      </svg>
                                      {formatDueDate(ticket.dueDate)}
                                    </span>
                                  )}
                                </div>
                                <div className="mt-4">
                                  <label className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">
                                    Status
                                  </label>
                                  <select
                                    value={ticket.status}
                                    onChange={(event) => handleUpdateTicketStatus(ticket.id, event.target.value)}
                                    className="mt-1 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-200"
                                  >
                                    {columns.map((option) => (
                                      <option key={option.id} value={option.id}>
                                        {option.name}
                                      </option>
                                    ))}
                                  </select>
                                </div>
                              </article>
                            </div>
                          ))}

                          <DropIndicator
                            active={dropIndicator?.columnId === column.id && !dropIndicator?.beforeTicketId}
                          />

                          {columnTickets.length === 0 && (
                            <div className="rounded-2xl border border-dashed border-gray-200 bg-gray-50 px-4 py-6 text-center text-sm text-gray-500">
                              Drop a ticket here to populate this stage.
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="overflow-hidden rounded-3xl border border-gray-200 bg-white/80 shadow-sm">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50/80">
                    <tr>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Ticket
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Status
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Priority
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Assignee
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Due
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Tags
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white/70">
                    {readyTickets.map((ticket) => {
                      const due = formatDueDate(ticket.dueDate);
                      return (
                        <tr key={ticket.id} className="hover:bg-gray-50">
                          <td className="px-6 py-4 text-sm text-gray-700">
                            <p className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">
                              {ticket.id}
                            </p>
                            <p className="mt-1 font-medium text-gray-900">{ticket.title}</p>
                            <p className="mt-1 text-xs text-gray-500 line-clamp-2">{ticket.description}</p>
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-700">
                            <select
                              value={ticket.status}
                              onChange={(event) => handleUpdateTicketStatus(ticket.id, event.target.value)}
                              className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-200"
                            >
                              {columns.map((option) => (
                                <option key={option.id} value={option.id}>
                                  {option.name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-700">
                            <span
                              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                                priorityMeta[ticket.priority].badgeBgClass
                              } ${priorityMeta[ticket.priority].badgeTextClass}`}
                            >
                              {priorityMeta[ticket.priority].icon}
                              {priorityMeta[ticket.priority].label}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-700">
                            <div className="flex items-center gap-2">
                              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-purple-100 to-purple-200 text-[11px] font-semibold text-purple-700">
                                {getInitials(ticket.assignee)}
                              </div>
                              <span className="font-medium text-gray-800">{ticket.assignee}</span>
                            </div>
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-500">{due ?? '—'}</td>
                          <td className="px-6 py-4 text-sm text-gray-700">
                            <div className="flex flex-wrap gap-2">
                              {ticket.tags.map((tag) => (
                                <span
                                  key={tag}
                                  className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600"
                                >
                                  #{tag}
                                </span>
                              ))}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      </main>

      {showColumnManager && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-gray-900/60 px-4 py-8">
          <div className="w-full max-w-3xl overflow-hidden rounded-3xl bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-5">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Customize columns</h2>
                <p className="text-sm text-gray-500">
                  Rename, reorder, or remove workflow stages to mirror your team’s delivery process.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowColumnManager(false)}
                className="rounded-full p-2 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
                aria-label="Close column manager"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="max-h-[70vh] overflow-y-auto px-6 py-6">
              <div className="space-y-4">
                {columns.map((column, index) => {
                  const styles = columnVisualStyles[column.color] ?? fallbackColumnStyle;
                  return (
                    <div
                      key={column.id}
                      className="flex flex-col gap-4 rounded-2xl border border-gray-100 bg-gray-50/80 px-4 py-4 shadow-sm sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex flex-1 items-center gap-3">
                        <span className={`h-2.5 w-2.5 flex-shrink-0 rounded-full ${styles.dotClass}`} />
                        <input
                          value={column.name}
                          onChange={(event) => handleRenameColumn(column.id, event.target.value)}
                          className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-200"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleMoveColumn(column.id, 'up')}
                          disabled={index === 0}
                          className="rounded-xl border border-gray-200 bg-white p-2 text-gray-500 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
                          aria-label="Move column up"
                        >
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                          </svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleMoveColumn(column.id, 'down')}
                          disabled={index === columns.length - 1}
                          className="rounded-xl border border-gray-200 bg-white p-2 text-gray-500 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
                          aria-label="Move column down"
                        >
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveColumn(column.id)}
                          disabled={columns.length <= 1}
                          className="rounded-xl border border-red-200 bg-white p-2 text-red-500 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
                          aria-label="Remove column"
                        >
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <button
                type="button"
                onClick={handleAddColumn}
                className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-purple-300 bg-purple-50/80 px-4 py-3 text-sm font-medium text-purple-700 transition hover:bg-purple-100"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Add column
              </button>
            </div>
            <div className="flex items-center justify-end gap-3 border-t border-gray-100 px-6 py-4">
              <button
                type="button"
                onClick={() => setShowColumnManager(false)}
                className="rounded-xl border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-100"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
