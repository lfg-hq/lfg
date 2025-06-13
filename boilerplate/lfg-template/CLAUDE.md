# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

LFG Template is a production-ready Next.js SaaS boilerplate with authentication, payments, email, storage, analytics, and background job processing. It uses Next.js 15 with App Router, TypeScript, Prisma ORM, Auth.js, Stripe, and shadcn/ui components.

## Common Commands

```bash
# Development
npm run dev          # Start development server with Turbopack
npm run build        # Build for production  
npm run start        # Start production server
npm run lint         # Run ESLint

# Database
npm run db:migrate   # Run Prisma migrations
npm run db:push      # Push schema changes without migration
npm run db:studio    # Open Prisma Studio GUI

# Background Workers
npm run workers      # Start email worker process
```

## High-Level Architecture

### Directory Structure
- `/src/app/` - Next.js App Router pages and API routes
  - `/api/` - API endpoints including auth, stripe webhooks, protected routes
  - `/auth/` - Authentication pages (login, register, forgot-password)
  - `/dashboard/` - Protected user dashboard pages
- `/src/lib/` - Core utilities and configurations
  - `prisma.ts` - Database client singleton
  - `auth.ts` - Auth.js configuration with Google OAuth and credentials
  - `email.ts` - Email sending utilities
  - `s3.ts` - AWS S3 file storage utilities
  - `stripe.ts` - Stripe payment processing
  - `queue.ts` - BullMQ background job setup
- `/src/components/` - React components using shadcn/ui
- `/prisma/` - Database schema and migrations

### Key Technologies
- **Frontend**: Next.js 15.3.3, React 19, TypeScript, Tailwind CSS
- **Database**: Prisma with SQLite (dev) / PostgreSQL/MySQL (prod)
- **Auth**: Auth.js v5 with Google SSO and email/password
- **Payments**: Stripe subscriptions with webhook handling
- **Background Jobs**: BullMQ with Redis for email processing

### Authentication Flow
- Auth.js handles session management
- Protected routes use `auth()` from `@/lib/auth`
- Middleware in `middleware.ts` protects `/dashboard/*` routes
- Email verification tokens stored in database

### Database Models
- User, Account, Session (Auth.js)
- Subscription (Stripe integration)
- Upload (S3 file storage)
- VerificationToken (email verification)

## Development Notes

- Environment variables are loaded from `.env.local` (copy from `.env.example`)
- Redis must be running for background jobs (`redis-server`)
- Run database migrations before starting: `npm run db:migrate`
- All `/dashboard/` and `/api/protected/` routes require authentication
- Stripe webhooks are handled at `/api/webhooks/stripe`
- Email sending is queued as background jobs via BullMQ