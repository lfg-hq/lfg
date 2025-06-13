import Link from 'next/link'
import { Button } from '@/components/ui/button'

export default function Home() {
  return (
    <div className="flex flex-col min-h-screen">
      {/* Header */}
      <header className="border-b">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="text-2xl font-bold">
            LFG Template
          </Link>
          <nav className="flex items-center gap-6">
            <Link href="/features" className="hover:underline">
              Features
            </Link>
            <Link href="/pricing" className="hover:underline">
              Pricing
            </Link>
            <Link href="/docs" className="hover:underline">
              Docs
            </Link>
            <Link href="/auth/signin">
              <Button variant="outline">Sign In</Button>
            </Link>
            <Link href="/auth/signup">
              <Button>Get Started</Button>
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <section className="flex-1 flex items-center justify-center py-20 px-4">
        <div className="container mx-auto text-center max-w-4xl">
          <h1 className="text-6xl font-bold mb-6 bg-gradient-to-r from-primary to-purple-600 bg-clip-text text-transparent">
            Ship Your SaaS Faster
          </h1>
          <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
            The ultimate Next.js boilerplate with authentication, payments, email, storage, and more. 
            Everything you need to launch your product.
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/auth/signup">
              <Button size="lg" className="text-lg px-8">
                Start Building Now
              </Button>
            </Link>
            <Link href="https://github.com/yourusername/lfg-template" target="_blank">
              <Button size="lg" variant="outline" className="text-lg px-8">
                View on GitHub
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-4 bg-muted/50">
        <div className="container mx-auto">
          <h2 className="text-4xl font-bold text-center mb-12">
            Everything You Need
          </h2>
          <div className="grid md:grid-cols-3 gap-8">
            <FeatureCard
              title="Authentication"
              description="Google SSO, credentials, email verification, and secure sessions with Auth.js"
            />
            <FeatureCard
              title="Payments"
              description="Stripe integration with subscriptions, webhooks, and customer portal"
            />
            <FeatureCard
              title="Database"
              description="Prisma ORM with SQLite for development and easy migration to production DBs"
            />
            <FeatureCard
              title="File Storage"
              description="AWS S3 integration with secure uploads and signed URLs"
            />
            <FeatureCard
              title="Email"
              description="SMTP configuration with Nodemailer for transactional emails"
            />
            <FeatureCard
              title="Background Jobs"
              description="BullMQ workers with Redis for reliable background processing"
            />
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4">
        <div className="container mx-auto text-center">
          <h2 className="text-4xl font-bold mb-6">
            Ready to Launch?
          </h2>
          <p className="text-xl text-muted-foreground mb-8">
            Join developers who ship faster with LFG Template
          </p>
          <Link href="/auth/signup">
            <Button size="lg" className="text-lg px-8">
              Get Started Free
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-8 px-4">
        <div className="container mx-auto text-center text-muted-foreground">
          <p>© 2024 LFG Template. Built with Next.js, Tailwind CSS, and shadcn/ui.</p>
        </div>
      </footer>
    </div>
  )
}

function FeatureCard({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg border bg-card p-6">
      <h3 className="text-xl font-semibold mb-2">{title}</h3>
      <p className="text-muted-foreground">{description}</p>
    </div>
  )
}