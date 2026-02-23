import { html } from "hono/html";

export const AgentPage = () => html`
<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LFG | AI Agents Build Your Software. Humans Verify.</title>
    <meta name="description" content="LFG is an AI-first software factory. Autonomous agents handle requirements, ticketing, coding, and testing. Humans verify. Ship 10x faster at 80% less cost.">
    <link rel="icon" type="image/x-icon" href="/static/images/favicon.ico">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {
            fontFamily: {
              sans: ['Manrope', 'sans-serif'],
              display: ['Sora', 'sans-serif'],
              mono: ['JetBrains Mono', 'monospace'],
            },
            colors: {
              brand: { 50:'#eef2ff',100:'#e0e7ff',200:'#c7d2fe',300:'#a5b4fc',400:'#818cf8',500:'#6366f1',600:'#4f46e5',700:'#4338ca',800:'#3730a3',900:'#312e81' },
              ink: { 900:'#0f172a' },
              accent: { 500:'#ec4899',600:'#db2777' }
            },
            animation: {
              'fade-in':'fadeIn 0.5s ease-out','fade-up':'fadeUp 0.6s ease-out both','drift':'drift 8s ease-in-out infinite',
            },
            keyframes: {
              fadeIn:{'0%':{opacity:'0'},'100%':{opacity:'1'}},
              fadeUp:{'0%':{opacity:'0',transform:'translateY(20px)'},'100%':{opacity:'1',transform:'translateY(0)'}},
              drift:{'0%,100%':{transform:'translateY(0px)'},'50%':{transform:'translateY(-10px)'}},
            }
          }
        }
      }
    </script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
      body { background: radial-gradient(circle at 20% 0%, #eef2ff 0%, #f8fafc 38%, #ffffff 100%); overflow-x: hidden; }
      .mesh { background-image: radial-gradient(circle at 10% 20%, rgba(99,102,241,0.14), transparent 40%), radial-gradient(circle at 80% 0%, rgba(236,72,153,0.12), transparent 35%); }
      .glass { background: rgba(255,255,255,0.85); border: 1px solid rgba(148,163,184,0.24); backdrop-filter: blur(10px); }
      .no-scrollbar::-webkit-scrollbar { display: none; }
      .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
      .glow-brand { box-shadow: 0 0 30px rgba(99,102,241,0.15), 0 0 60px rgba(99,102,241,0.05); }
      .stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(99,102,241,0.12); }
      .step-card { transition: all 0.3s ease; }
      .step-card:hover { border-color: #6366f1; transform: translateY(-3px); box-shadow: 0 12px 40px rgba(99,102,241,0.1); }
      @keyframes slideUp { from { opacity:0; transform:translateY(24px); } to { opacity:1; transform:translateY(0); } }
      .pipeline-step { opacity: 0; }
      .pipeline-step.animate { animation: slideUp 0.5s ease-out forwards; }
    </style>
</head>
<body class="text-slate-900 font-sans selection:bg-indigo-600 selection:text-white">

    <nav id="navbar" class="fixed top-0 left-0 right-0 z-50 transition-all duration-300 bg-transparent py-5">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center">
        <a href="/" class="flex items-center gap-2 group">
          <div class="bg-brand-600 text-white p-1.5 rounded-lg transform group-hover:rotate-12 transition-transform">
            <i data-lucide="rocket" class="w-5 h-5"></i>
          </div>
          <span class="font-display font-bold text-xl tracking-tight text-slate-900">LFG</span>
        </a>
        <div class="hidden md:flex items-center gap-6">
          <a href="/" class="text-sm font-medium text-slate-600 hover:text-brand-600 transition-colors">Home</a>
          <a href="/agent/" class="text-sm font-medium text-brand-600 font-semibold">Agent</a>
          <a href="/services/" class="text-sm font-medium text-slate-600 hover:text-brand-600 transition-colors">Services</a>
          <a href="/blog/" class="text-sm font-medium text-slate-600 hover:text-brand-600 transition-colors">Blog</a>
          <div class="flex items-center gap-4 ml-2">
            <a href="https://github.com/lfg-hq/lfg" target="_blank" rel="noopener noreferrer" class="text-slate-500 hover:text-slate-900 transition-colors">
              <i data-lucide="github" class="w-5 h-5"></i>
            </a>
            <a href="/auth/login" class="bg-slate-900 hover:bg-brand-700 text-white px-5 py-2 rounded-full text-sm font-semibold transition-all shadow-lg">
              Get Started
            </a>
          </div>
        </div>
        <div class="md:hidden">
          <button id="mobile-menu-btn" class="text-slate-600"><i data-lucide="menu" class="w-6 h-6"></i></button>
        </div>
      </div>
      <div id="mobile-menu" class="hidden md:hidden absolute top-full left-0 w-full bg-white border-b border-slate-200 p-4 flex-col gap-3 shadow-xl">
        <a href="/" class="text-base font-medium text-slate-700 py-2 mobile-link">Home</a>
        <a href="/agent/" class="text-base font-medium text-slate-700 py-2 mobile-link">Agent</a>
        <a href="/services/" class="text-base font-medium text-slate-700 py-2 mobile-link">Services</a>
        <a href="/blog/" class="text-base font-medium text-slate-700 py-2 mobile-link">Blog</a>
        <a href="/auth/login" class="bg-brand-600 text-white w-full py-3 rounded-lg font-semibold text-center block mobile-link">Get Started</a>
      </div>
    </nav>

    <main>
        <!-- HERO -->
        <section class="relative pt-28 sm:pt-40 pb-20 sm:pb-28 overflow-hidden mesh">
            <div class="absolute -top-10 right-[8%] w-72 h-72 rounded-full bg-brand-100 blur-3xl animate-drift"></div>
            <div class="absolute top-20 left-[5%] w-80 h-80 rounded-full bg-pink-100 blur-3xl animate-drift" style="animation-delay:1s"></div>
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
                <div class="text-center max-w-4xl mx-auto">
                    <div class="inline-flex items-center gap-2 px-4 py-2 rounded-full glass shadow-sm mb-8 animate-fade-up">
                        <span class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                        <span class="text-xs font-bold text-slate-600 uppercase tracking-wider">Your AI product manager</span>
                    </div>
                    <h1 class="font-display font-semibold text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-[1.1] tracking-tight text-slate-900 animate-fade-up" style="animation-delay: 0.1s">
                        Your AI product manager that helps your team <span class="text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 to-pink-500">build</span>
                    </h1>
                    <p class="text-lg sm:text-xl text-slate-600 mt-7 max-w-2xl mx-auto leading-relaxed animate-fade-up" style="animation-delay: 0.2s">
                        LFG Agent is your AI product manager. It analyzes requirements, creates PRDs and technical plans, generates prioritized tickets, and orchestrates Claude Code sessions to build your product. You stay in control.
                    </p>
                    <div class="mt-10 flex flex-wrap items-center justify-center gap-4 animate-fade-up" style="animation-delay: 0.3s">
                        <a href="/auth/register" class="px-8 py-3.5 rounded-full bg-brand-600 text-white font-semibold hover:bg-brand-700 transition-all inline-flex items-center gap-2 shadow-lg shadow-brand-600/25">
                            Try LFG Agent <i data-lucide="arrow-right" class="w-4 h-4"></i>
                        </a>
                        <a href="#features" class="px-8 py-3.5 rounded-full bg-white border border-slate-200 text-slate-700 font-semibold hover:border-brand-300 hover:text-brand-700 transition-colors inline-flex items-center gap-2">
                            See Features
                        </a>
                    </div>
                </div>
                <!-- Stats Bar -->
                <div class="mt-16 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto animate-fade-up" style="animation-delay: 0.4s">
                    <div class="stat-card glass rounded-xl p-5 text-center transition-all cursor-default">
                        <p class="font-display font-semibold text-2xl sm:text-3xl text-brand-600">PRDs</p>
                        <p class="text-sm font-medium text-slate-500 mt-1">Auto-generated</p>
                    </div>
                    <div class="stat-card glass rounded-xl p-5 text-center transition-all cursor-default">
                        <p class="font-display font-semibold text-2xl sm:text-3xl text-brand-600">Tickets</p>
                        <p class="text-sm font-medium text-slate-500 mt-1">Created &amp; prioritized</p>
                    </div>
                    <div class="stat-card glass rounded-xl p-5 text-center transition-all cursor-default">
                        <p class="font-display font-semibold text-2xl sm:text-3xl text-brand-600">Code</p>
                        <p class="text-sm font-medium text-slate-500 mt-1">Sandboxed sessions</p>
                    </div>
                    <div class="stat-card glass rounded-xl p-5 text-center transition-all cursor-default">
                        <p class="font-display font-semibold text-2xl sm:text-3xl text-brand-600">Ship</p>
                        <p class="text-sm font-medium text-slate-500 mt-1">Review &amp; merge</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- SCREENSHOTS -->
        <section class="py-16 bg-white border-t border-slate-100">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="text-center mb-12">
                    <p class="text-sm font-bold text-brand-600 uppercase tracking-wider mb-2">See it in action</p>
                    <h2 class="font-display font-bold text-3xl md:text-4xl text-slate-900">Your AI product manager at work</h2>
                    <p class="text-slate-600 text-lg mt-4">From requirements analysis to ticket execution, every step is visible and trackable.</p>
                </div>
                <div class="space-y-16">
                    <div class="grid lg:grid-cols-2 gap-10 items-center">
                        <div class="order-2 lg:order-1">
                            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 border border-brand-200 mb-4">
                                <i data-lucide="file-text" class="w-4 h-4 text-brand-600"></i>
                                <span class="text-xs font-bold text-brand-700 uppercase tracking-wider">PRD generation</span>
                            </div>
                            <h3 class="font-display font-bold text-2xl text-slate-900 mb-3">Analyze requirements. Generate PRDs.</h3>
                            <p class="text-slate-600 leading-relaxed mb-4">Feed your idea into the AI chat. LFG Agent reads through your context-heavy data, analyzes requirements, and generates a comprehensive product requirements document with feature breakdowns, technical approach, and stack recommendations.</p>
                            <ul class="space-y-2 text-sm text-slate-600">
                                <li class="flex gap-2"><i data-lucide="check" class="w-4 h-4 text-brand-600 mt-0.5 shrink-0"></i> Full PRD with features, priorities, and acceptance criteria</li>
                                <li class="flex gap-2"><i data-lucide="check" class="w-4 h-4 text-brand-600 mt-0.5 shrink-0"></i> Technical analysis with stack and architecture decisions</li>
                                <li class="flex gap-2"><i data-lucide="check" class="w-4 h-4 text-brand-600 mt-0.5 shrink-0"></i> Document versioning — iterate and refine with the agent</li>
                            </ul>
                        </div>
                        <div class="order-1 lg:order-2">
                            <div class="rounded-2xl border border-slate-200 bg-white shadow-xl overflow-hidden">
                                <div class="flex items-center gap-1.5 px-4 py-2.5 bg-slate-100 border-b border-slate-200">
                                    <span class="w-2.5 h-2.5 rounded-full bg-red-400"></span>
                                    <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                                    <span class="ml-2 text-xs text-slate-400">LFG Agent — PRD &amp; Analysis</span>
                                </div>
                                <img src="/static/images/screenshots/agent-prd-chat.png" alt="LFG Agent generating a PRD" class="w-full" />
                            </div>
                        </div>
                    </div>

                    <div class="grid lg:grid-cols-2 gap-10 items-center">
                        <div>
                            <div class="rounded-2xl border border-slate-200 bg-white shadow-xl overflow-hidden">
                                <div class="flex items-center gap-1.5 px-4 py-2.5 bg-slate-100 border-b border-slate-200">
                                    <span class="w-2.5 h-2.5 rounded-full bg-red-400"></span>
                                    <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                                    <span class="ml-2 text-xs text-slate-400">LFG Agent — Ticket Board</span>
                                </div>
                                <img src="/static/images/screenshots/agent-ticket-board.png" alt="LFG ticket board" class="w-full" />
                            </div>
                        </div>
                        <div>
                            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 border border-brand-200 mb-4">
                                <i data-lucide="list-checks" class="w-4 h-4 text-brand-600"></i>
                                <span class="text-xs font-bold text-brand-700 uppercase tracking-wider">Ticket management</span>
                            </div>
                            <h3 class="font-display font-bold text-2xl text-slate-900 mb-3">Create and prioritize tickets automatically.</h3>
                            <p class="text-slate-600 leading-relaxed mb-4">Once the PRD is approved, LFG Agent breaks it into user stories and implementation tickets — scoped, prioritized, and ready for execution. All within the app. No external tools needed.</p>
                            <ul class="space-y-2 text-sm text-slate-600">
                                <li class="flex gap-2"><i data-lucide="check" class="w-4 h-4 text-brand-600 mt-0.5 shrink-0"></i> User stories with acceptance criteria auto-generated</li>
                                <li class="flex gap-2"><i data-lucide="check" class="w-4 h-4 text-brand-600 mt-0.5 shrink-0"></i> Kanban board with Open, In Progress, Review, Done</li>
                                <li class="flex gap-2"><i data-lucide="check" class="w-4 h-4 text-brand-600 mt-0.5 shrink-0"></i> Priority and dependency-aware ordering</li>
                            </ul>
                        </div>
                    </div>

                    <div class="grid lg:grid-cols-2 gap-10 items-center">
                        <div class="order-2 lg:order-1">
                            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 border border-brand-200 mb-4">
                                <i data-lucide="terminal" class="w-4 h-4 text-brand-600"></i>
                                <span class="text-xs font-bold text-brand-700 uppercase tracking-wider">Agent execution</span>
                            </div>
                            <h3 class="font-display font-bold text-2xl text-slate-900 mb-3">Track and course-correct Claude Code sessions.</h3>
                            <p class="text-slate-600 leading-relaxed mb-4">Each ticket is executed by Claude Code in a sandboxed environment. LFG Agent tracks progress, shows you exactly what was built, and lets you continue, restart, or course-correct at any point.</p>
                            <ul class="space-y-2 text-sm text-slate-600">
                                <li class="flex gap-2"><i data-lucide="check" class="w-4 h-4 text-brand-600 mt-0.5 shrink-0"></i> Sandboxed Claude Code sessions per ticket</li>
                                <li class="flex gap-2"><i data-lucide="check" class="w-4 h-4 text-brand-600 mt-0.5 shrink-0"></i> Live execution logs, git diffs, and server preview</li>
                                <li class="flex gap-2"><i data-lucide="check" class="w-4 h-4 text-brand-600 mt-0.5 shrink-0"></i> Continue or restart sessions with full context</li>
                            </ul>
                        </div>
                        <div class="order-1 lg:order-2">
                            <div class="rounded-2xl border border-slate-200 bg-white shadow-xl overflow-hidden">
                                <div class="flex items-center gap-1.5 px-4 py-2.5 bg-slate-100 border-b border-slate-200">
                                    <span class="w-2.5 h-2.5 rounded-full bg-red-400"></span>
                                    <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                                    <span class="ml-2 text-xs text-slate-400">LFG Agent — Ticket Execution</span>
                                </div>
                                <img src="/static/images/screenshots/agent-ticket-execution.png" alt="LFG ticket execution" class="w-full" />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- FEATURES -->
        <section id="features" class="py-20 bg-slate-50">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="text-center max-w-3xl mx-auto mb-16">
                    <p class="text-sm font-bold text-brand-600 uppercase tracking-wider mb-2">What LFG Agent does</p>
                    <h2 class="font-display font-bold text-3xl md:text-4xl text-slate-900">Your AI product manager, end to end</h2>
                    <p class="text-slate-600 text-lg mt-4">LFG Agent handles the entire product lifecycle — from understanding what needs to be built to making sure it gets built right.</p>
                </div>
                <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                    <div class="step-card rounded-2xl border border-slate-200 bg-white p-6">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-10 h-10 rounded-xl bg-indigo-100 text-brand-700 flex items-center justify-center"><i data-lucide="brain" class="w-5 h-5"></i></div>
                            <h3 class="font-display font-bold text-lg">Requirements Analysis</h3>
                        </div>
                        <p class="text-sm text-slate-600 leading-relaxed">Reads through your context-heavy data — briefs, docs, conversations — and distills it into clear, structured requirements. Asks the right questions so nothing gets missed.</p>
                    </div>
                    <div class="step-card rounded-2xl border border-slate-200 bg-white p-6">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-10 h-10 rounded-xl bg-indigo-100 text-brand-700 flex items-center justify-center"><i data-lucide="file-text" class="w-5 h-5"></i></div>
                            <h3 class="font-display font-bold text-lg">PRD Generation</h3>
                        </div>
                        <p class="text-sm text-slate-600 leading-relaxed">Generates comprehensive product requirement documents with feature tables, priority levels, technical approach, and stack recommendations. Iterate and version them with the agent.</p>
                    </div>
                    <div class="step-card rounded-2xl border border-slate-200 bg-white p-6">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-10 h-10 rounded-xl bg-indigo-100 text-brand-700 flex items-center justify-center"><i data-lucide="git-branch" class="w-5 h-5"></i></div>
                            <h3 class="font-display font-bold text-lg">Technical Planning</h3>
                        </div>
                        <p class="text-sm text-slate-600 leading-relaxed">Selects the right stack, designs system architecture, maps data models and APIs. Produces a technical plan that becomes the blueprint for implementation tickets.</p>
                    </div>
                    <div class="step-card rounded-2xl border border-slate-200 bg-white p-6">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-10 h-10 rounded-xl bg-indigo-100 text-brand-700 flex items-center justify-center"><i data-lucide="list-todo" class="w-5 h-5"></i></div>
                            <h3 class="font-display font-bold text-lg">Ticket Creation</h3>
                        </div>
                        <p class="text-sm text-slate-600 leading-relaxed">Breaks the plan into scoped, dependency-aware tickets with user stories and acceptance criteria. All created within the app — no external project management tool needed.</p>
                    </div>
                    <div class="step-card rounded-2xl border border-slate-200 bg-white p-6">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-10 h-10 rounded-xl bg-indigo-100 text-brand-700 flex items-center justify-center"><i data-lucide="terminal" class="w-5 h-5"></i></div>
                            <h3 class="font-display font-bold text-lg">Claude Code Sessions</h3>
                        </div>
                        <p class="text-sm text-slate-600 leading-relaxed">Each ticket is handed off to Claude Code running in a sandboxed environment. Track execution logs, view git diffs, preview the running server, and course-correct when needed.</p>
                    </div>
                    <div class="step-card rounded-2xl border border-slate-200 bg-white p-6">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-10 h-10 rounded-xl bg-indigo-100 text-brand-700 flex items-center justify-center"><i data-lucide="history" class="w-5 h-5"></i></div>
                            <h3 class="font-display font-bold text-lg">Versioning &amp; Iteration</h3>
                        </div>
                        <p class="text-sm text-slate-600 leading-relaxed">PRDs and technical documents are versioned as you iterate. Refine scope, adjust priorities, and re-plan — the agent keeps full context across every revision.</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- PIPELINE -->
        <section id="how-it-works" class="py-20 bg-white border-t border-slate-100">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="text-center max-w-3xl mx-auto mb-16">
                    <p class="text-sm font-bold text-brand-600 uppercase tracking-wider mb-2">The pipeline</p>
                    <h2 class="font-display font-bold text-3xl md:text-4xl text-slate-900">From idea to working product</h2>
                    <p class="text-slate-600 text-lg mt-4">You describe what you need. LFG Agent handles every step. You review and approve.</p>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-0 items-stretch">
                    <div class="pipeline-step relative flex flex-col" style="animation-delay: 0s">
                        <article class="step-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm flex-1">
                            <div class="w-10 h-10 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center mb-4"><i data-lucide="message-square-text" class="w-5 h-5"></i></div>
                            <p class="text-xs uppercase font-bold tracking-wider text-brand-600 mb-2">01 — You</p>
                            <h3 class="font-display font-bold text-lg mb-2">Describe your idea</h3>
                            <p class="text-sm text-slate-600">Share what you need in plain English. A product concept, a feature set, a whole system.</p>
                        </article>
                        <div class="hidden lg:flex items-center justify-center absolute -right-3 top-1/2 -translate-y-1/2 z-10 w-6 h-6 rounded-full bg-white border border-slate-200 shadow-sm text-brand-500"><i data-lucide="chevron-right" class="w-3.5 h-3.5"></i></div>
                    </div>
                    <div class="pipeline-step relative flex flex-col" style="animation-delay: 0.1s">
                        <article class="step-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm flex-1">
                            <div class="w-10 h-10 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center mb-4"><i data-lucide="file-text" class="w-5 h-5"></i></div>
                            <p class="text-xs uppercase font-bold tracking-wider text-brand-600 mb-2">02 — Agent</p>
                            <h3 class="font-display font-bold text-lg mb-2">PRD &amp; plan</h3>
                            <p class="text-sm text-slate-600">Agent generates a full PRD, technical architecture, and implementation plan you can review and iterate on.</p>
                        </article>
                        <div class="hidden lg:flex items-center justify-center absolute -right-3 top-1/2 -translate-y-1/2 z-10 w-6 h-6 rounded-full bg-white border border-slate-200 shadow-sm text-brand-500"><i data-lucide="chevron-right" class="w-3.5 h-3.5"></i></div>
                    </div>
                    <div class="pipeline-step relative flex flex-col" style="animation-delay: 0.2s">
                        <article class="step-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm flex-1">
                            <div class="w-10 h-10 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center mb-4"><i data-lucide="list-checks" class="w-5 h-5"></i></div>
                            <p class="text-xs uppercase font-bold tracking-wider text-brand-600 mb-2">03 — Agent</p>
                            <h3 class="font-display font-bold text-lg mb-2">Tickets created</h3>
                            <p class="text-sm text-slate-600">The plan is broken into prioritized tickets with user stories. Each is scoped and queued for execution.</p>
                        </article>
                        <div class="hidden lg:flex items-center justify-center absolute -right-3 top-1/2 -translate-y-1/2 z-10 w-6 h-6 rounded-full bg-white border border-slate-200 shadow-sm text-brand-500"><i data-lucide="chevron-right" class="w-3.5 h-3.5"></i></div>
                    </div>
                    <div class="pipeline-step relative flex flex-col" style="animation-delay: 0.3s">
                        <article class="step-card bg-white rounded-xl p-6 border border-slate-200 shadow-sm flex-1">
                            <div class="w-10 h-10 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center mb-4"><i data-lucide="terminal" class="w-5 h-5"></i></div>
                            <p class="text-xs uppercase font-bold tracking-wider text-brand-600 mb-2">04 — Agent</p>
                            <h3 class="font-display font-bold text-lg mb-2">Code &amp; test</h3>
                            <p class="text-sm text-slate-600">Claude Code executes each ticket in a sandbox. You can watch, course-correct, or let it run autonomously.</p>
                        </article>
                        <div class="hidden lg:flex items-center justify-center absolute -right-3 top-1/2 -translate-y-1/2 z-10 w-6 h-6 rounded-full bg-white border border-slate-200 shadow-sm text-brand-500"><i data-lucide="chevron-right" class="w-3.5 h-3.5"></i></div>
                    </div>
                    <div class="pipeline-step relative flex flex-col" style="animation-delay: 0.4s">
                        <article class="step-card bg-white rounded-xl p-6 border border-brand-200 shadow-sm bg-brand-50 flex-1">
                            <div class="w-10 h-10 rounded-lg bg-brand-600 text-white flex items-center justify-center mb-4"><i data-lucide="check-circle-2" class="w-5 h-5"></i></div>
                            <p class="text-xs uppercase font-bold tracking-wider text-brand-700 mb-2">05 — You</p>
                            <h3 class="font-display font-bold text-lg mb-2">Review &amp; ship</h3>
                            <p class="text-sm text-slate-700">Review the working product. Approve and merge, or leave feedback. The agent iterates instantly.</p>
                        </article>
                    </div>
                </div>
                <div class="mt-10 text-center">
                    <p class="text-slate-500 text-sm font-medium"><span class="text-brand-600 font-bold">You touch 2 of 5 steps.</span> The rest is fully autonomous.</p>
                </div>
            </div>
        </section>

        <!-- CTA -->
        <section id="start" class="py-20 bg-white border-t border-slate-100">
            <div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
                <div class="glass rounded-2xl p-8 sm:p-10 shadow-2xl border border-slate-200/70 glow-brand">
                    <div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-green-50 border border-green-200 mb-5">
                        <span class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                        <span class="text-xs font-bold text-green-700 uppercase tracking-wider">Agents ready</span>
                    </div>
                    <h2 class="font-display font-bold text-3xl md:text-4xl text-slate-900 mb-4">Start building with AI</h2>
                    <p class="text-slate-500 mb-8">Sign up free. Describe your product idea and LFG Agent will create a PRD, tickets, and start building.</p>
                    <div class="flex flex-col sm:flex-row gap-3 justify-center">
                        <a href="/auth/register" class="inline-flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-700 text-white px-8 py-3.5 rounded-lg font-semibold transition-all shadow-lg shadow-brand-600/25">
                            <i data-lucide="sparkles" class="w-4 h-4"></i> Get started free
                        </a>
                        <a href="/auth/login" class="inline-flex items-center justify-center gap-2 bg-white border border-slate-200 text-slate-700 px-8 py-3.5 rounded-lg font-semibold hover:border-brand-300 hover:text-brand-700 transition-colors">
                            Sign in
                        </a>
                    </div>
                </div>
            </div>
        </section>

        <!-- OPEN SOURCE -->
        <section class="py-16 bg-slate-50 border-t border-slate-100">
            <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex flex-col md:flex-row items-center justify-between mb-8 gap-6">
                    <div>
                        <h2 class="font-display font-bold text-2xl text-slate-900 mb-1">Open source. Self-host it.</h2>
                        <p class="text-slate-500 text-sm">LFG is open source. Clone it, run it, own it.</p>
                    </div>
                    <button onclick="copyCommands(this)" class="flex items-center gap-2 text-sm font-medium text-brand-700 bg-brand-50 hover:bg-brand-100 px-4 py-2 rounded-lg transition-colors shrink-0">
                        <i data-lucide="copy" class="w-4 h-4"></i>
                        <span class="btn-text">Copy Commands</span>
                    </button>
                </div>
                <div class="bg-[#0f172a] rounded-xl shadow-2xl overflow-hidden border border-slate-800 font-mono text-sm leading-relaxed">
                    <div class="flex items-center gap-2 px-4 py-3 bg-[#1e293b] border-b border-slate-700">
                        <div class="w-3 h-3 rounded-full bg-[#ff5f56]"></div>
                        <div class="w-3 h-3 rounded-full bg-[#ffbd2e]"></div>
                        <div class="w-3 h-3 rounded-full bg-[#27c93f]"></div>
                        <span class="ml-2 text-xs text-slate-400">bash — lfg</span>
                    </div>
                    <div class="p-6 text-slate-300 overflow-x-auto">
<pre id="command-block">
# Clone the repository
git clone https://github.com/lfg-hq/lfg.git

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start server
uvicorn LFG.asgi:application --host 0.0.0.0 --port 8000
</pre>
                    </div>
                </div>
            </div>
        </section>
    </main>

    <footer class="bg-slate-900 border-t border-slate-800 pt-16 pb-8">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="grid grid-cols-1 md:grid-cols-4 gap-12 mb-12">
                <div class="col-span-1 md:col-span-2">
                    <div class="flex items-center gap-2 mb-4 text-white font-bold text-xl">
                        <i data-lucide="rocket" class="w-6 h-6 text-brand-500"></i><span>LFG</span>
                    </div>
                    <p class="text-slate-400 max-w-sm leading-relaxed">AI-first software factory. Agents build. Humans verify. Ship faster than you thought possible.</p>
                </div>
                <div>
                    <h4 class="font-bold text-white mb-4 uppercase text-xs tracking-wider">Company</h4>
                    <ul class="space-y-3 text-sm text-slate-400">
                        <li><a href="/agent/" class="hover:text-brand-400 transition-colors">Agent</a></li>
                        <li><a href="/services/" class="hover:text-brand-400 transition-colors">Services</a></li>
                        <li><a href="/blog/" class="hover:text-brand-400 transition-colors">Blog</a></li>
                    </ul>
                </div>
                <div>
                    <h4 class="font-bold text-white mb-4 uppercase text-xs tracking-wider">Community</h4>
                    <ul class="space-y-3 text-sm text-slate-400">
                        <li><a href="https://github.com/lfg-hq/lfg" target="_blank" rel="noopener noreferrer" class="hover:text-brand-400 transition-colors flex items-center gap-2"><i data-lucide="github" class="w-4 h-4"></i> GitHub</a></li>
                        <li><a href="/auth/login" class="hover:text-brand-400 transition-colors flex items-center gap-2"><i data-lucide="rocket" class="w-4 h-4"></i> Platform</a></li>
                    </ul>
                </div>
            </div>
            <div class="border-t border-slate-800 pt-8 text-center text-sm text-slate-500">&copy; 2026 LFG Inc. Open Source Apache 2.0.</div>
        </div>
    </footer>

    <script>
        lucide.createIcons();

        const pipelineObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.querySelectorAll('.pipeline-step').forEach(step => step.classList.add('animate'));
                    pipelineObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.2 });
        const pipelineGrid = document.querySelector('#how-it-works .grid');
        if (pipelineGrid) pipelineObserver.observe(pipelineGrid);

        window.addEventListener('scroll', () => {
            const nav = document.getElementById('navbar');
            if (window.scrollY > 20) {
                nav.classList.add('bg-white/90', 'backdrop-blur-md', 'border-b', 'border-slate-200', 'shadow-sm', 'py-3');
                nav.classList.remove('bg-transparent', 'py-5');
            } else {
                nav.classList.remove('bg-white/90', 'backdrop-blur-md', 'border-b', 'border-slate-200', 'shadow-sm', 'py-3');
                nav.classList.add('bg-transparent', 'py-5');
            }
        });

        const mobileBtn = document.getElementById('mobile-menu-btn');
        const mobileMenu = document.getElementById('mobile-menu');
        mobileBtn.addEventListener('click', () => { mobileMenu.classList.toggle('hidden'); mobileMenu.classList.toggle('flex'); });
        document.querySelectorAll('.mobile-link').forEach(link => {
            link.addEventListener('click', () => { mobileMenu.classList.add('hidden'); mobileMenu.classList.remove('flex'); });
        });

        function copyCommands(btn) {
            const commands = \`# Clone the repository
git clone https://github.com/lfg-hq/lfg.git

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start server
uvicorn LFG.asgi:application --host 0.0.0.0 --port 8000\`;
            navigator.clipboard.writeText(commands);
            const textSpan = btn.querySelector('.btn-text');
            if (textSpan) { textSpan.textContent = 'Copied!'; setTimeout(() => { textSpan.textContent = 'Copy Commands'; }, 2000); }
        }
    </script>
</body>
</html>
`;
