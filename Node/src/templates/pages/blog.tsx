import { html } from "hono/html";

export const BlogPage = () => html`
<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LFG Blog | Engineering Notes and Build Playbooks</title>
    <meta name="description" content="Practical engineering notes, build playbooks, and shipping lessons from LFG.">
    <link rel="icon" type="image/x-icon" href="/static/images/favicon.ico">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
      body { font-family: 'Manrope', sans-serif; }
      .font-display { font-family: 'Sora', sans-serif; }
    </style>
</head>
<body class="text-slate-900 bg-slate-50">
    <nav class="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-slate-200">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <a href="/" class="flex items-center gap-2">
                <i data-lucide="rocket" class="w-5 h-5 text-indigo-600"></i>
                <span class="font-display font-bold text-lg">LFG</span>
            </a>
            <div class="hidden md:flex items-center gap-6">
                <a href="/" class="text-sm font-medium text-slate-600 hover:text-indigo-600 transition-colors">Home</a>
                <a href="/agent/" class="text-sm font-medium text-slate-600 hover:text-indigo-600 transition-colors">Agent</a>
                <a href="/services/" class="text-sm font-medium text-slate-600 hover:text-indigo-600 transition-colors">Services</a>
                <a href="/blog/" class="text-sm font-medium text-indigo-600 font-semibold">Blog</a>
                <div class="flex items-center gap-4 ml-2">
                    <a href="https://github.com/lfg-hq/lfg" target="_blank" rel="noopener noreferrer" class="text-slate-500 hover:text-slate-900 transition-colors">
                        <i data-lucide="github" class="w-5 h-5"></i>
                    </a>
                    <a href="/auth/register" class="bg-slate-900 hover:bg-indigo-700 text-white px-5 py-2 rounded-full text-sm font-semibold transition-all shadow-lg">
                        Get Started
                    </a>
                </div>
            </div>
            <div class="md:hidden">
                <button id="mobile-menu-btn" class="text-slate-600"><i data-lucide="menu" class="w-6 h-6"></i></button>
            </div>
        </div>
        <div id="mobile-menu" class="hidden md:hidden absolute top-full left-0 w-full bg-white border-b border-slate-200 p-4 flex-col gap-3 shadow-xl z-50">
            <a href="/" class="text-base font-medium text-slate-700 py-2 mobile-link">Home</a>
            <a href="/agent/" class="text-base font-medium text-slate-700 py-2 mobile-link">Agent</a>
            <a href="/services/" class="text-base font-medium text-slate-700 py-2 mobile-link">Services</a>
            <a href="/blog/" class="text-base font-medium text-slate-700 py-2 mobile-link">Blog</a>
            <a href="/auth/register" class="bg-indigo-600 text-white w-full py-3 rounded-lg font-semibold text-center block mobile-link">Get Started</a>
        </div>
    </nav>

    <main class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-16">
        <header class="mb-10">
            <p class="text-xs font-bold uppercase tracking-wider text-indigo-700 mb-2">Blog</p>
            <h1 class="font-display font-bold text-4xl sm:text-5xl text-slate-900">Engineering notes that stay practical</h1>
            <p class="text-slate-600 mt-4 text-lg max-w-3xl">Shipping lessons, build playbooks, and engineering insights from the LFG team.</p>
        </header>

        <section class="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            <article class="rounded-2xl border border-dashed border-slate-300 bg-white p-8 md:col-span-2 lg:col-span-3 text-center">
                <div class="w-14 h-14 bg-indigo-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
                    <i data-lucide="pen-line" class="w-7 h-7 text-indigo-500"></i>
                </div>
                <h2 class="font-display text-xl font-bold text-slate-900 mb-2">Posts coming soon</h2>
                <p class="text-slate-500 text-sm max-w-md mx-auto">We're writing up what we've learned building LFG — shipping AI-powered products, orchestrating Claude Code sessions, and running fast build cycles. Check back soon.</p>
                <div class="mt-6 flex items-center justify-center gap-3">
                    <a href="https://github.com/lfg-hq/lfg" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-indigo-600 transition-colors">
                        <i data-lucide="github" class="w-4 h-4"></i> Follow on GitHub
                    </a>
                </div>
            </article>
        </section>
    </main>

    <footer class="bg-slate-900 border-t border-slate-800 pt-12 pb-8 mt-16">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-4">
            <div class="flex items-center gap-2 text-white font-bold">
                <i data-lucide="rocket" class="w-5 h-5 text-indigo-400"></i><span>LFG</span>
            </div>
            <div class="flex items-center gap-6 text-sm text-slate-400">
                <a href="/" class="hover:text-indigo-400 transition-colors">Home</a>
                <a href="/agent/" class="hover:text-indigo-400 transition-colors">Agent</a>
                <a href="/services/" class="hover:text-indigo-400 transition-colors">Services</a>
                <a href="https://github.com/lfg-hq/lfg" target="_blank" rel="noopener noreferrer" class="hover:text-indigo-400 transition-colors">GitHub</a>
            </div>
            <p class="text-xs text-slate-500">&copy; 2026 LFG Inc.</p>
        </div>
    </footer>

    <script>
      lucide.createIcons();
      const mobileBtn = document.getElementById('mobile-menu-btn');
      const mobileMenu = document.getElementById('mobile-menu');
      if (mobileBtn && mobileMenu) {
          mobileBtn.addEventListener('click', () => { mobileMenu.classList.toggle('hidden'); mobileMenu.classList.toggle('flex'); });
          document.querySelectorAll('.mobile-link').forEach(link => {
              link.addEventListener('click', () => { mobileMenu.classList.add('hidden'); mobileMenu.classList.remove('flex'); });
          });
      }
    </script>
</body>
</html>
`;
