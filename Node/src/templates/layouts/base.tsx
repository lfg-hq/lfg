import type { FC, PropsWithChildren } from "hono/jsx";

type BaseLayoutProps = PropsWithChildren<{
  title?: string;
  extraCss?: string;
  extraJs?: string;
  user?: { username: string; avatarUrl?: string } | null;
  activePage?: string;
}>;

export const BaseLayout: FC<BaseLayoutProps> = ({
  title = "Projects - LFG",
  extraCss,
  extraJs,
  user,
  activePage,
  children,
}) => (
  <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <script
        dangerouslySetInnerHTML={{
          __html: `(function(){var t=localStorage.getItem('lfg-theme')||'dark';document.documentElement.setAttribute('data-theme',t)})();`,
        }}
      />
      <title>{title}</title>
      <link rel="stylesheet" href="/public/css/theme-variables.css" />
      <link rel="stylesheet" href="/public/css/common.css" />
      <link rel="stylesheet" href="/public/css/projects.css" />
      <link rel="stylesheet" href="/public/css/settings.css" />
      <link rel="stylesheet" href="/public/css/auth.css" />
      <link rel="stylesheet" href="/public/css/integrations.css" />
      <link rel="stylesheet" href="/public/css/light/light-mode.css?v=5" />
      <link
        rel="stylesheet"
        href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css"
      />
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="" />
      <link
        href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap"
        rel="stylesheet"
      />
      <link rel="icon" type="image/x-icon" href="/public/images/favicon.ico" />
      <meta name="color-scheme" content="dark light" />
      <script src="/public/js/theme-switcher.js?v=3" />
      {extraCss && <link rel="stylesheet" href={extraCss} />}
    </head>
    <body>
      <div class="app-container">
        <header class="main-header">
          <div class="container">
            <div class="header-content">
              <div class="header-left">
                <div class="logo">
                  <a href="/projects">
                    <span class="logo-text">LFG</span>
                    <span class="logo-emoji">🚀🚀</span>
                  </a>
                </div>
                <nav class="main-nav">
                  <a
                    href="/projects"
                    class={activePage === "projects" ? "active" : ""}
                  >
                    Projects
                  </a>
                  <a
                    href="/integrations"
                    class={activePage === "integrations" ? "active" : ""}
                  >
                    Integrations
                  </a>
                </nav>
              </div>
              <div class="header-right">
                <button
                  id="theme-toggle"
                  class="theme-toggle-btn"
                  title="Toggle theme"
                  data-theme-toggle
                >
                  <i class="fas fa-sun" />
                </button>
                <div class="user-menu">
                  {user ? (
                    <div class="dropdown">
                      <button class="dropdown-button user-dropdown-button">
                        <div class="user-avatar">
                          {user.avatarUrl ? (
                            <img
                              src={user.avatarUrl}
                              alt={`${user.username}'s avatar`}
                            />
                          ) : (
                            <div class="avatar-text">
                              {user.username.charAt(0).toUpperCase()}
                            </div>
                          )}
                        </div>
                        <span class="username">{user.username}</span>
                        <i class="fas fa-chevron-down" />
                      </button>
                      <div class="dropdown-menu">
                        <div class="dropdown-divider" />
                        <a href="/auth/logout" class="dropdown-item">
                          <i class="fas fa-sign-out-alt" /> Logout
                        </a>
                      </div>
                    </div>
                  ) : (
                    <a href="/auth/login" class="btn btn-primary">
                      Log In
                    </a>
                  )}
                </div>
              </div>
            </div>
          </div>
        </header>

        <main class="main-content">
          <div class="container">{children}</div>
        </main>

        <footer class="main-footer">
          <div class="container">
            <p>
              &copy; {new Date().getFullYear()} LFG 🚀 Project. All rights
              reserved.
            </p>
          </div>
        </footer>
      </div>

      <script src="/public/js/projects.js" />
      {extraJs && <script src={extraJs} />}
    </body>
  </html>
);
