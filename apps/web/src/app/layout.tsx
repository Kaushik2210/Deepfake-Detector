import type { Metadata } from "next";
import Link from "next/link";

import { Providers } from "./providers";
import "./globals.css";
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";
import { TooltipProvider } from "@/components/ui/tooltip";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "VeriFrame",
  description:
    "Synthetic media analysis with calibrated likelihoods, uncertainty ranges, and visual evidence.",
};

const NAV_LINKS = [
  { href: "/", label: "Analyse" },
  { href: "/accuracy", label: "Accuracy" },
  { href: "/privacy", label: "Privacy" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={cn("font-sans", geist.variable)}>
      {/*
        Browser extensions (Grammarly, password managers) inject attributes onto
        <body> before React hydrates, which reads as a server/client mismatch.
        This suppresses the warning for attributes on this element only — nested
        content is still checked normally.
      */}
      <body className="min-h-screen bg-background text-foreground" suppressHydrationWarning>
        {/* Visible only on keyboard focus, so a screen-reader or keyboard user
            can jump past the repeated nav without a mouse-only affordance. */}
        <a
          href="#main"
          className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:top-3 focus-visible:left-3 focus-visible:z-50 focus-visible:rounded-md focus-visible:bg-primary focus-visible:px-4 focus-visible:py-2 focus-visible:text-sm focus-visible:font-medium focus-visible:text-primary-foreground"
        >
          Skip to main content
        </a>

        <TooltipProvider delayDuration={200}>
          <Providers>
            <header className="border-b bg-card/60 backdrop-blur supports-[backdrop-filter]:bg-card/60">
              <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
                <Link href="/" className="flex items-center gap-2 text-lg font-semibold tracking-tight">
                  <span
                    aria-hidden="true"
                    className="inline-flex size-6 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground"
                  >
                    V
                  </span>
                  VeriFrame
                </Link>
                <nav aria-label="Primary" className="flex gap-1 text-sm">
                  {NAV_LINKS.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      className="rounded-md px-3 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                      {link.label}
                    </Link>
                  ))}
                </nav>
              </div>
            </header>

            <main id="main" className="mx-auto max-w-4xl px-6 py-8">
              {children}
            </main>
          </Providers>
        </TooltipProvider>
      </body>
    </html>
  );
}
