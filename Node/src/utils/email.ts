import { env } from "../config/env.ts";

interface EmailOptions {
  to: string;
  subject: string;
  html: string;
  text?: string;
}

/**
 * Send an email via SendGrid HTTP API.
 * Falls back to console.log in development if no API key is set.
 */
export async function sendEmail(options: EmailOptions): Promise<boolean> {
  if (!env.SENDGRID_API_KEY) {
    console.log(`[Email] No SENDGRID_API_KEY set. Would send to ${options.to}: ${options.subject}`);
    if (options.text) console.log(`[Email] Body: ${options.text}`);
    return true;
  }

  try {
    const res = await fetch("https://api.sendgrid.com/v3/mail/send", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.SENDGRID_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: options.to }] }],
        from: { email: env.EMAIL_FROM, name: "LFG" },
        subject: options.subject,
        content: [
          ...(options.text ? [{ type: "text/plain", value: options.text }] : []),
          { type: "text/html", value: options.html },
        ],
      }),
    });

    if (!res.ok) {
      const body = await res.text();
      console.error(`[Email] SendGrid error ${res.status}: ${body}`);
      return false;
    }
    return true;
  } catch (err) {
    console.error("[Email] Failed to send:", err);
    return false;
  }
}
