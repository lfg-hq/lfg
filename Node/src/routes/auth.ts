import { Hono } from "hono";
import { AuthPage } from "../templates/pages/auth.tsx";

const authRoutes = new Hono();

// ── Login / Register page ──────────────────────────────────────────
authRoutes.get("/auth/login", (c) => c.html(AuthPage()));
authRoutes.get("/auth/register", (c) => c.html(AuthPage()));

// NOTE: Better Auth API handler (/api/auth/**) is registered directly
// on the main app in index.ts so it runs before sub-router middleware.

export default authRoutes;
