import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LFG 🚀 - AI-Powered Development Platform",
  description: "Build amazing products with AI assistance",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
