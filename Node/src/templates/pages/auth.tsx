import { html } from "hono/html";

/**
 * Combined login/register page.
 * Uses Better Auth client-side API for form submission (no Django CSRF needed).
 * Auth endpoints: POST /api/auth/sign-up/email, POST /api/auth/sign-in/email
 */
export const AuthPage = () => html`
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LFG | Login / Register</title>
    <link rel="shortcut icon" type="image/x-icon" href="/public/images/favicon.ico">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700;800&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {
            fontFamily: {
              sans: ['Inter', 'sans-serif'],
              display: ['Space Grotesk', 'sans-serif'],
            },
            colors: {
              primary: {
                50: '#eef2ff',
                100: '#e0e7ff',
                500: '#6366f1',
                600: '#4f46e5',
                700: '#4338ca',
              },
              secondary: { 500: '#ec4899' }
            }
          }
        }
      }
    </script>
    <style>body { background-color: #f8fafc; }</style>
</head>
<body class="font-sans text-slate-900 h-screen flex overflow-hidden">

    <!-- Left Side: Dark Marketing Panel -->
    <div class="hidden lg:flex lg:w-1/2 bg-slate-900 relative flex-col justify-between p-12 overflow-hidden">
        <div class="absolute top-0 right-0 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2"></div>
        <div class="absolute bottom-0 left-0 w-64 h-64 bg-pink-600/10 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2"></div>
        <div class="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20"></div>

        <a href="/" class="flex items-center gap-2 group relative z-10">
            <div class="bg-indigo-600 text-white p-1.5 rounded-lg">
                <i data-lucide="rocket" class="w-5 h-5"></i>
            </div>
            <span class="font-display font-bold text-xl tracking-tight text-white">LFG</span>
        </a>

        <div class="relative z-10 space-y-8">
            <h1 class="font-display font-bold text-4xl text-white leading-tight">
                The AI Software Factory.
            </h1>
            <p class="text-indigo-200 text-lg max-w-md leading-relaxed">
                From idea to production without the friction. Let agents draft your PRDs, write your tickets, and ship your code.
            </p>
            <div class="space-y-4 pt-4">
                <div class="flex items-center gap-4 text-white/80">
                    <div class="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center text-indigo-400">
                        <i data-lucide="file-text" class="w-4 h-4"></i>
                    </div>
                    <span>Instant PRDs & Documentation</span>
                </div>
                <div class="flex items-center gap-4 text-white/80">
                    <div class="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center text-indigo-400">
                        <i data-lucide="ticket" class="w-4 h-4"></i>
                    </div>
                    <span>Automated Ticketing & Planning</span>
                </div>
                <div class="flex items-center gap-4 text-white/80">
                    <div class="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center text-indigo-400">
                        <i data-lucide="terminal" class="w-4 h-4"></i>
                    </div>
                    <span>Autonomous Coding Agents</span>
                </div>
            </div>
        </div>

        <div class="relative z-10 text-slate-500 text-sm">&copy; 2026 LFG Inc.</div>
    </div>

    <!-- Right Side: Auth Form -->
    <div class="w-full lg:w-1/2 bg-slate-50 flex flex-col relative overflow-y-auto">
        <!-- Mobile Navbar -->
        <nav class="lg:hidden bg-white/80 backdrop-blur border-b border-slate-200 py-4 px-4 flex justify-between items-center sticky top-0 z-50">
            <a href="/" class="flex items-center gap-2 group">
                <div class="bg-indigo-600 text-white p-1.5 rounded-lg">
                    <i data-lucide="rocket" class="w-5 h-5"></i>
                </div>
                <span class="font-display font-bold text-xl tracking-tight text-slate-900">LFG</span>
            </a>
        </nav>

        <div class="flex-grow flex items-center justify-center p-4 sm:p-8">
            <div class="w-full max-w-md bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
                <div class="px-8 pt-8 pb-6 text-center">
                    <h2 class="font-display font-bold text-2xl text-slate-900 mb-2">Welcome to LFG</h2>
                    <p class="text-slate-500 text-sm">The AI software factory for builders.</p>
                </div>

                <!-- Tabs -->
                <div class="flex border-b border-slate-100 px-8">
                    <button onclick="switchTab('login')" class="auth-tab login-tab flex-1 py-3 text-sm font-semibold border-b-2 transition-colors focus:outline-none">Login</button>
                    <button onclick="switchTab('register')" class="auth-tab register-tab flex-1 py-3 text-sm font-semibold border-b-2 transition-colors focus:outline-none">Register</button>
                </div>

                <div class="p-8">
                    <!-- Error Banner -->
                    <div id="auth-error" class="hidden bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg text-sm mb-4"></div>
                    <div id="auth-success" class="hidden bg-green-50 border border-green-200 text-green-600 px-4 py-3 rounded-lg text-sm mb-4"></div>

                    <!-- Login Form -->
                    <div class="auth-form login-form">
                        <button type="button" onclick="signInWithGoogle()" class="w-full flex items-center justify-center gap-3 bg-white border border-slate-200 p-3 rounded-lg text-slate-700 font-medium hover:bg-slate-50 transition-colors mb-6">
                            <img src="https://www.google.com/favicon.ico" alt="Google" class="w-5 h-5" />
                            Sign in with Google
                        </button>

                        <div class="relative mb-6">
                            <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-slate-200"></div></div>
                            <div class="relative flex justify-center text-xs uppercase"><span class="bg-white px-2 text-slate-400">Or continue with email</span></div>
                        </div>

                        <form id="login-form" class="space-y-4">
                            <div>
                                <label for="login-email" class="block text-sm font-medium text-slate-700 mb-1">Email</label>
                                <input type="email" id="login-email" class="w-full p-3 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all" placeholder="Enter your email" required>
                            </div>
                            <div>
                                <label for="login-password" class="block text-sm font-medium text-slate-700 mb-1">Password</label>
                                <div class="relative">
                                    <input type="password" id="login-password" class="w-full p-3 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all" placeholder="Enter your password" required>
                                    <button type="button" class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-indigo-600 toggle-password">
                                        <i data-lucide="eye" class="w-4 h-4"></i>
                                    </button>
                                </div>
                            </div>
                            <div class="flex items-center justify-between text-sm">
                                <label class="flex items-center gap-2 text-slate-600 cursor-pointer">
                                    <input type="checkbox" class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500">
                                    <span>Remember me</span>
                                </label>
                                <button type="button" onclick="showForgotPassword()" class="text-indigo-600 hover:text-indigo-700 font-medium">Forgot password?</button>
                            </div>
                            <button type="submit" class="w-full bg-indigo-600 text-white p-3 rounded-lg font-bold hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-500/30">
                                Sign In
                            </button>
                        </form>
                    </div>

                    <!-- Register Form -->
                    <div class="auth-form register-form hidden">
                        <button type="button" onclick="signInWithGoogle()" class="w-full flex items-center justify-center gap-3 bg-white border border-slate-200 p-3 rounded-lg text-slate-700 font-medium hover:bg-slate-50 transition-colors mb-6">
                            <img src="https://www.google.com/favicon.ico" alt="Google" class="w-5 h-5" />
                            Sign up with Google
                        </button>

                        <div class="relative mb-6">
                            <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-slate-200"></div></div>
                            <div class="relative flex justify-center text-xs uppercase"><span class="bg-white px-2 text-slate-400">Or continue with email</span></div>
                        </div>

                        <form id="register-form" class="space-y-4">
                            <div>
                                <label for="register-name" class="block text-sm font-medium text-slate-700 mb-1">Name</label>
                                <input type="text" id="register-name" class="w-full p-3 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all" placeholder="Your name" required>
                            </div>
                            <div>
                                <label for="register-email" class="block text-sm font-medium text-slate-700 mb-1">Email</label>
                                <input type="email" id="register-email" class="w-full p-3 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all" placeholder="Enter your email" required>
                            </div>
                            <div>
                                <label for="register-password" class="block text-sm font-medium text-slate-700 mb-1">Password</label>
                                <div class="relative">
                                    <input type="password" id="register-password" class="w-full p-3 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all" placeholder="Create a password (min 8 chars)" required minlength="8">
                                    <button type="button" class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-indigo-600 toggle-password">
                                        <i data-lucide="eye" class="w-4 h-4"></i>
                                    </button>
                                </div>
                            </div>
                            <div>
                                <label for="register-password2" class="block text-sm font-medium text-slate-700 mb-1">Confirm Password</label>
                                <div class="relative">
                                    <input type="password" id="register-password2" class="w-full p-3 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all" placeholder="Confirm your password" required>
                                    <button type="button" class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-indigo-600 toggle-password">
                                        <i data-lucide="eye" class="w-4 h-4"></i>
                                    </button>
                                </div>
                            </div>
                            <button type="submit" class="w-full bg-indigo-600 text-white p-3 rounded-lg font-bold hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-500/30">
                                Create Account
                            </button>
                        </form>
                    </div>
                    <!-- Forgot Password Form (hidden by default) -->
                    <div class="auth-form forgot-form hidden">
                        <div class="text-center mb-6">
                            <div class="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-full flex items-center justify-center mx-auto mb-3">
                                <i data-lucide="key-round" class="w-5 h-5"></i>
                            </div>
                            <h3 class="font-display font-bold text-lg text-slate-900">Reset your password</h3>
                            <p class="text-slate-500 text-sm mt-1">Enter your email and we'll send you a reset link.</p>
                        </div>
                        <form id="forgot-form" class="space-y-4">
                            <input type="email" id="forgot-email" class="w-full p-3 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none" placeholder="Email address" required />
                            <div id="forgot-message" class="hidden text-sm text-center"></div>
                            <button type="submit" class="w-full bg-indigo-600 text-white p-3 rounded-lg font-bold hover:bg-indigo-700 transition-colors">
                                Send Reset Link
                            </button>
                            <button type="button" onclick="switchTab('login')" class="w-full text-sm font-semibold text-slate-500 hover:text-slate-700">
                                Back to login
                            </button>
                        </form>
                    </div>
                </div>

                <div class="px-8 py-4 border-t border-slate-50 text-center">
                    <p class="text-xs text-slate-400">
                        By continuing, you agree to LFG's <a href="#" class="text-indigo-600 hover:underline">Terms</a> and <a href="#" class="text-indigo-600 hover:underline">Privacy Policy</a>.
                    </p>
                </div>
            </div>
        </div>
    </div>

    <script>
        lucide.createIcons();

        function switchTab(tab) {
            const loginTab = document.querySelector('.login-tab');
            const registerTab = document.querySelector('.register-tab');
            const loginForm = document.querySelector('.login-form');
            const registerForm = document.querySelector('.register-form');
            const activeClasses = ['border-indigo-600', 'text-indigo-600'];
            const inactiveClasses = ['border-transparent', 'text-slate-500', 'hover:text-indigo-600', 'hover:bg-slate-50'];

            loginForm.classList.add('hidden');
            registerForm.classList.add('hidden');
            document.querySelector('.forgot-form').classList.add('hidden');
            document.getElementById('auth-error').classList.add('hidden');
            document.getElementById('auth-success').classList.add('hidden');

            if (tab === 'login') {
                loginTab.classList.add(...activeClasses);
                loginTab.classList.remove(...inactiveClasses);
                registerTab.classList.add(...inactiveClasses);
                registerTab.classList.remove(...activeClasses);
                loginForm.classList.remove('hidden');
            } else {
                registerTab.classList.add(...activeClasses);
                registerTab.classList.remove(...inactiveClasses);
                loginTab.classList.add(...inactiveClasses);
                loginTab.classList.remove(...activeClasses);
                registerForm.classList.remove('hidden');
            }
        }

        // Initialize default tab
        switchTab('login');

        // Toggle password visibility
        document.querySelectorAll('.toggle-password').forEach(btn => {
            btn.addEventListener('click', function() {
                const input = this.parentElement.querySelector('input');
                input.type = input.type === 'password' ? 'text' : 'password';
            });
        });

        function showError(msg) {
            const el = document.getElementById('auth-error');
            el.textContent = msg;
            el.classList.remove('hidden');
            document.getElementById('auth-success').classList.add('hidden');
        }

        function showSuccess(msg) {
            const el = document.getElementById('auth-success');
            el.textContent = msg;
            el.classList.remove('hidden');
            document.getElementById('auth-error').classList.add('hidden');
        }

        // Login
        document.getElementById('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('login-email').value;
            const password = document.getElementById('login-password').value;
            const btn = e.target.querySelector('button[type=submit]');
            btn.disabled = true;
            btn.textContent = 'Signing in...';
            try {
                const res = await fetch('/api/auth/sign-in/email', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password }),
                    credentials: 'include',
                });
                if (res.ok) {
                    window.location.href = '/projects';
                } else {
                    const data = await res.json().catch(() => ({}));
                    showError(data.message || 'Invalid email or password. Please try again.');
                }
            } catch (err) {
                showError('An error occurred. Please try again.');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Sign In';
            }
        });

        // Register
        document.getElementById('register-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = document.getElementById('register-name').value;
            const email = document.getElementById('register-email').value;
            const password = document.getElementById('register-password').value;
            const password2 = document.getElementById('register-password2').value;

            if (password !== password2) {
                showError('Passwords do not match.');
                return;
            }

            const btn = e.target.querySelector('button[type=submit]');
            btn.disabled = true;
            btn.textContent = 'Creating account...';
            try {
                const res = await fetch('/api/auth/sign-up/email', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, email, password }),
                    credentials: 'include',
                });
                if (res.ok) {
                    window.location.href = '/projects';
                } else {
                    const data = await res.json().catch(() => ({}));
                    showError(data.message || 'Registration failed. The email may already be in use.');
                }
            } catch (err) {
                showError('An error occurred. Please try again.');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Create Account';
            }
        });

        // Forgot password flow
        function showForgotPassword() {
            document.querySelector('.login-form').classList.add('hidden');
            document.querySelector('.register-form').classList.add('hidden');
            document.querySelector('.forgot-form').classList.remove('hidden');
            document.getElementById('auth-error').classList.add('hidden');
            document.getElementById('auth-success').classList.add('hidden');
        }

        document.getElementById('forgot-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('forgot-email').value;
            const btn = e.target.querySelector('button[type=submit]');
            btn.disabled = true;
            btn.textContent = 'Sending...';
            try {
                const res = await fetch('/api/auth/forget-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, redirectTo: '/auth/reset-password' }),
                });
                const msgEl = document.getElementById('forgot-message');
                msgEl.style.display = 'block';
                if (res.ok) {
                    msgEl.className = 'text-sm text-green-400 text-center';
                    msgEl.textContent = 'Check your email for a reset link.';
                } else {
                    msgEl.className = 'text-sm text-red-400 text-center';
                    msgEl.textContent = 'Failed to send reset email. Please try again.';
                }
            } catch (err) {
                showError('An error occurred. Please try again.');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Send Reset Link';
            }
        });

        // Google OAuth — must be POST to get back a redirect URL
        async function signInWithGoogle() {
            try {
                const res = await fetch('/api/auth/sign-in/social', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ provider: 'google', callbackURL: '/projects' }),
                    credentials: 'include',
                });
                const text = await res.text();
                let data;
                try { data = JSON.parse(text); } catch { data = {}; }
                console.log('Google OAuth response', res.status, text);
                if (data.url) {
                    window.location.href = data.url;
                } else {
                    showError(data.message || data.error || 'Failed to initiate Google sign-in. (status ' + res.status + ')');
                }
            } catch (err) {
                showError('An error occurred. Please try again.');
            }
        }

        // Check URL for tab param
        const params = new URLSearchParams(window.location.search);
        if (params.get('tab') === 'register') switchTab('register');
    </script>
</body>
</html>
`;
