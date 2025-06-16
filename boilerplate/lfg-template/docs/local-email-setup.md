# Local Email Setup for Development

## Option 1: Mailhog (Recommended)

Mailhog captures all emails locally with a web UI to view them.

### Setup:
```bash
# Using Docker:
docker run -d -p 1025:1025 -p 8025:8025 mailhog/mailhog

# Or install with Homebrew (macOS):
brew install mailhog
mailhog
```

### Configuration (.env.local):
```env
SMTP_HOST="localhost"
SMTP_PORT="1025"
SMTP_SECURE="false"
SMTP_USER=""
SMTP_PASSWORD=""
SMTP_FROM="noreply@localhost"
```

### View emails:
Open http://localhost:8025 in your browser

## Option 2: Console Email

For the simplest setup, log emails to console:

```typescript
// In src/lib/email.ts, add:
if (process.env.NODE_ENV === 'development') {
  console.log('📧 Email would be sent:', mailOptions)
  return // Skip actual sending
}
```

## Option 3: File-based Email

Save emails to local files:

```typescript
// In src/lib/email.ts
import fs from 'fs/promises'
import path from 'path'

if (process.env.NODE_ENV === 'development') {
  const emailDir = path.join(process.cwd(), 'tmp/emails')
  await fs.mkdir(emailDir, { recursive: true })
  
  const filename = `${Date.now()}-${email}.html`
  await fs.writeFile(
    path.join(emailDir, filename),
    mailOptions.html
  )
  console.log(`📧 Email saved to: tmp/emails/${filename}`)
  return
}
```

## Production Options

For production, use:
- Gmail with App Password
- SendGrid (generous free tier)
- Resend (modern, developer-friendly)
- AWS SES (cost-effective at scale)