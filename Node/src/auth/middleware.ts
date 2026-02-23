import { createMiddleware } from "hono/factory";
import { auth } from "./index.ts";

/**
 * Hono middleware that requires an authenticated session.
 * Sets `user` and `session` on the context for downstream handlers.
 */
export const requireAuth = createMiddleware<{
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
}>(async (c, next) => {
  // Never block Better Auth's own API endpoints (sign-in, sign-up, callback, etc.)
  if (c.req.path.startsWith("/api/auth/")) {
    return await next();
  }

  const session = await auth.api.getSession({
    headers: c.req.raw.headers,
  });

  if (!session) {
    // For API routes, return 401 JSON
    if (c.req.path.startsWith("/api/")) {
      return c.json({ error: "Unauthorized" }, 401);
    }
    // For page routes, redirect to login
    return c.redirect("/auth/login");
  }

  c.set("user", session.user);
  c.set("session", session.session);
  await next();
});

/**
 * Optional auth middleware — sets user/session if present, but doesn't block.
 */
export const optionalAuth = createMiddleware<{
  Variables: {
    user: typeof auth.$Infer.Session.user | null;
    session: typeof auth.$Infer.Session.session | null;
  };
}>(async (c, next) => {
  const session = await auth.api.getSession({
    headers: c.req.raw.headers,
  });

  c.set("user", session?.user ?? null);
  c.set("session", session?.session ?? null);
  await next();
});
