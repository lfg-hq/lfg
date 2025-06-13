# LFG Template - Next.js SaaS Boilerplate

A production-ready Next.js boilerplate with everything you need to launch your SaaS product quickly. Built with TypeScript, featuring authentication, payments, email, storage, and more.

## 🚀 Features

- **Authentication**: Google SSO + Email/Password with Auth.js (NextAuth v5)
- **Database**: Prisma ORM with SQLite (easily switchable to PostgreSQL/MySQL)
- **Payments**: Stripe integration with subscriptions and webhooks
- **Email**: SMTP configuration with email verification
- **File Storage**: AWS S3 integration with presigned URLs
- **Styling**: Tailwind CSS + shadcn/ui components
- **Analytics**: PostHog and Google Analytics support
- **Background Jobs**: BullMQ with Redis for async processing
- **SEO**: Dynamic landing pages with SSG/ISR support
- **Security**: Environment-based configuration, secure sessions

## 📋 Prerequisites

- Node.js 18+ 
- Redis (for background workers)
- AWS Account (for S3 storage)
- Stripe Account (for payments)
- Google OAuth App (for SSO)
- SMTP Service (Gmail, SendGrid, etc.)

## 🛠️ Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/lfg-template.git
cd lfg-template
```

2. Install dependencies:
```bash
npm install
```

3. Copy environment variables:
```bash
cp .env.example .env.local
```

4. Configure your environment variables (see Configuration section)

5. Initialize the database:
```bash
npx prisma migrate dev
```

6. Run the development server:
```bash
npm run dev
```

Visit `http://localhost:3000` to see your app!

## 🔧 Configuration

### Environment Variables

All configuration is managed through environment variables. Here's what each one does:

#### Database
- `DATABASE_URL`: SQLite connection string (default: `file:./dev.db`)

#### Authentication
- `AUTH_SECRET`: Secret for JWT signing (generate with `openssl rand -base64 32`)
- `AUTH_URL`: Your app URL (e.g., `http://localhost:3000`)
- `AUTH_GOOGLE_ID`: Google OAuth client ID
- `AUTH_GOOGLE_SECRET`: Google OAuth client secret

#### Email (SMTP)
- `SMTP_HOST`: SMTP server host
- `SMTP_PORT`: SMTP server port
- `SMTP_SECURE`: Use TLS (true/false)
- `SMTP_USER`: SMTP username
- `SMTP_PASSWORD`: SMTP password
- `SMTP_FROM`: Default from email

#### AWS S3
- `AWS_REGION`: AWS region
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `AWS_S3_BUCKET_NAME`: S3 bucket name

#### Stripe
- `STRIPE_PUBLIC_KEY`: Stripe publishable key
- `STRIPE_SECRET_KEY`: Stripe secret key
- `STRIPE_WEBHOOK_SECRET`: Stripe webhook signing secret

#### Analytics
- `NEXT_PUBLIC_POSTHOG_KEY`: PostHog project API key
- `NEXT_PUBLIC_POSTHOG_HOST`: PostHog instance URL
- `NEXT_PUBLIC_GA_MEASUREMENT_ID`: Google Analytics 4 measurement ID

#### Redis
- `REDIS_URL`: Redis connection URL

### Setting up Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URIs:
   - `http://localhost:3000/api/auth/callback/google` (development)
   - `https://yourdomain.com/api/auth/callback/google` (production)

### Setting up Stripe

1. Create a Stripe account at [stripe.com](https://stripe.com)
2. Get your API keys from the dashboard
3. Set up webhook endpoint:
   - URL: `https://yourdomain.com/api/webhooks/stripe`
   - Events: `checkout.session.completed`, `customer.subscription.*`

### Setting up AWS S3

1. Create an S3 bucket
2. Configure CORS:
```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
    "AllowedOrigins": ["http://localhost:3000", "https://yourdomain.com"],
    "ExposeHeaders": []
  }
]
```
3. Create IAM user with S3 access
4. Generate access keys

## 📁 Project Structure

```
lfg-template/
├── src/
│   ├── app/                 # Next.js app directory
│   │   ├── api/            # API routes
│   │   ├── auth/           # Authentication pages
│   │   └── dashboard/      # Protected pages
│   ├── components/         # React components
│   │   └── ui/            # shadcn/ui components
│   ├── lib/               # Utility functions
│   │   ├── prisma.ts      # Prisma client
│   │   ├── auth.ts        # Auth configuration
│   │   ├── email.ts       # Email utilities
│   │   ├── s3.ts          # S3 utilities
│   │   ├── stripe.ts      # Stripe utilities
│   │   └── queue.ts       # Job queue setup
│   ├── workers/           # Background job workers
│   └── types/             # TypeScript types
├── prisma/
│   └── schema.prisma      # Database schema
├── public/                # Static assets
└── .env.example          # Environment variables template
```

## 🔐 Authentication

### Email/Password Authentication

Users can sign up with email and password. Email verification is required:

```typescript
// Sign up new user
const res = await fetch('/api/auth/register', {
  method: 'POST',
  body: JSON.stringify({ name, email, password })
})

// Sign in
import { signIn } from 'next-auth/react'
await signIn('credentials', { email, password })
```

### Google SSO

Users can sign in with Google:

```typescript
import { signIn } from 'next-auth/react'
await signIn('google')
```

### Protecting Routes

Use middleware to protect routes:

```typescript
// src/middleware.ts
export const config = {
  matcher: ['/dashboard/:path*', '/api/protected/:path*']
}
```

## 💳 Payments

### Creating Subscriptions

```typescript
import { stripe } from '@/lib/stripe'

// Create checkout session
const session = await stripe.checkout.sessions.create({
  customer: customerId,
  payment_method_types: ['card'],
  line_items: [{
    price: 'price_xxx',
    quantity: 1
  }],
  mode: 'subscription',
  success_url: `${url}/success`,
  cancel_url: `${url}/cancel`
})
```

### Webhook Handling

Stripe webhooks are handled at `/api/webhooks/stripe`:

```typescript
// Verify webhook signature
const event = await stripe.webhooks.constructEvent(
  body,
  signature,
  process.env.STRIPE_WEBHOOK_SECRET
)

// Handle events
switch (event.type) {
  case 'checkout.session.completed':
    // Handle successful checkout
    break
  case 'customer.subscription.updated':
    // Update subscription status
    break
}
```

## 📤 File Storage

### Uploading Files

```typescript
import { uploadToS3 } from '@/lib/s3'

const url = await uploadToS3(
  buffer,
  'uploads/filename.jpg',
  'image/jpeg'
)
```

### Generating Presigned URLs

```typescript
import { getSignedUploadUrl } from '@/lib/s3'

// Get upload URL for client-side upload
const uploadUrl = await getSignedUploadUrl(
  'uploads/filename.jpg',
  'image/jpeg'
)
```

## 📧 Email

### Sending Emails

```typescript
import { sendVerificationEmail } from '@/lib/email'

await sendVerificationEmail(email, verificationToken)
```

### Email Templates

Customize email templates in `src/lib/email.ts`

## 🎨 Styling

### Using shadcn/ui Components

```bash
# Add a new component
npx shadcn@latest add button

# Available components
npx shadcn@latest add
```

### Customizing Theme

Edit `src/app/globals.css` to customize colors:

```css
:root {
  --primary: 222.2 47.4% 11.2%;
  --secondary: 210 40% 96.1%;
  /* ... */
}
```

## 📊 Analytics

### PostHog

Analytics are automatically initialized if `NEXT_PUBLIC_POSTHOG_KEY` is set:

```typescript
import { trackEvent } from '@/lib/analytics'

trackEvent('button_clicked', {
  button_name: 'signup',
  page: 'landing'
})
```

### Google Analytics

Add GA measurement ID to enable:
- `NEXT_PUBLIC_GA_MEASUREMENT_ID`

## 🔄 Background Jobs

### Creating Jobs

```typescript
import { emailQueue } from '@/lib/queue'

await emailQueue.add('send-welcome-email', {
  to: user.email,
  subject: 'Welcome!',
  html: '<h1>Welcome to our app!</h1>'
})
```

### Running Workers

```bash
# In a separate terminal
npm run workers
```

## 🚀 Deployment

### Vercel

1. Push to GitHub
2. Import project in Vercel
3. Add environment variables
4. Deploy

### Docker

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY . .
RUN npm ci --only=production
RUN npx prisma generate
RUN npm run build
CMD ["npm", "start"]
```

### Database Migration

For production, switch from SQLite to PostgreSQL:

1. Update `DATABASE_URL` in `.env`
2. Update schema.prisma provider:
```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}
```
3. Run migrations:
```bash
npx prisma migrate deploy
```

## 🔒 Security Best Practices

1. **Environment Variables**: Never commit `.env` files
2. **Authentication**: Always use secure session configuration
3. **API Routes**: Validate and sanitize all inputs
4. **File Uploads**: Validate file types and sizes
5. **CORS**: Configure appropriate origins
6. **Rate Limiting**: Implement rate limiting for APIs
7. **SQL Injection**: Prisma prevents SQL injection by default
8. **XSS**: React prevents XSS by default

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [Next.js](https://nextjs.org/)
- [Auth.js](https://authjs.dev/)
- [Prisma](https://www.prisma.io/)
- [Stripe](https://stripe.com/)
- [Tailwind CSS](https://tailwindcss.com/)
- [shadcn/ui](https://ui.shadcn.com/)
- [PostHog](https://posthog.com/)

---

Built with ❤️ by [Your Name]
