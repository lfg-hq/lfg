import { auth } from "@/auth"
import { redirect } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import Link from "next/link"

export default async function ExamplePage() {
  const session = await auth()
  
  if (!session) {
    redirect("/auth/login")
  }

  return (
    <div className="container mx-auto py-10 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-8">Welcome to Example Page</h1>
        
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Hello, {session.user?.name || session.user?.email}!</CardTitle>
            <CardDescription>
              You&apos;ve successfully logged in and been redirected to the example page.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <h3 className="font-semibold mb-2">Your Session Details:</h3>
                <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
                  <li>Email: {session.user?.email}</li>
                  <li>Name: {session.user?.name || "Not set"}</li>
                  <li>User ID: {session.user?.id}</li>
                </ul>
              </div>
              
              <div className="pt-4 space-x-4">
                <Link href="/dashboard">
                  <Button>Go to Dashboard</Button>
                </Link>
                <Link href="/api/auth/signout">
                  <Button variant="outline">Sign Out</Button>
                </Link>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What&apos;s Next?</CardTitle>
            <CardDescription>
              This is a sample page to demonstrate the authentication flow.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              From here you can:
            </p>
            <ul className="list-disc list-inside space-y-2 text-sm">
              <li>Navigate to your dashboard for more features</li>
              <li>Update your profile information</li>
              <li>Explore the application&apos;s features</li>
              <li>Sign out when you&apos;re done</li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}