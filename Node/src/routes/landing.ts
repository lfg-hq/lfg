import { Hono } from "hono";
import { LandingPage } from "../templates/pages/landing.tsx";
import { AgentPage } from "../templates/pages/agent.tsx";
import { ServicesPage } from "../templates/pages/services.tsx";
import { BlogPage } from "../templates/pages/blog.tsx";

const landing = new Hono();

landing.get("/", (c) => {
  return c.html(LandingPage());
});

landing.get("/agent", (c) => c.redirect("/agent/"));
landing.get("/agent/", (c) => c.html(AgentPage()));

landing.get("/services", (c) => c.redirect("/services/"));
landing.get("/services/", (c) => c.html(ServicesPage()));

landing.get("/blog", (c) => c.redirect("/blog/"));
landing.get("/blog/", (c) => c.html(BlogPage()));

// Services inquiry form submission
landing.post("/api/services/inquiry", async (c) => {
  try {
    const body = await c.req.json();
    const { name, email, requirements } = body;
    if (!name || !email || !requirements) {
      return c.json({ error: "Name, email, and requirements are required." }, 400);
    }
    // Log the inquiry (in production, send an email or save to DB)
    console.log("Services inquiry:", { name, email, company: body.company, role: body.role, timeline: body.timeline, budget: body.budget, requirements });
    return c.json({ success: true });
  } catch {
    return c.json({ error: "Invalid request." }, 400);
  }
});

export default landing;
