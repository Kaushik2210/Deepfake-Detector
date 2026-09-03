import type { Metadata } from "next";
import Link from "next/link";

import { Providers } from "./providers";
import "./globals.css";
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Footer } from "@/components/Footer";
import { NavLinks } from "@/components/NavLinks";

// Runs before hydration so the correct theme class is present on first
// paint — without this, the page would flash the light theme for a dark-mode
// visitor before React ever runs. Kept as a tiny inline script rather than a
// dependency: it does one thing (read a stored choice or the OS preference,
// toggle a class) that doesn't warrant next-themes for a single boolean.
const NO_FLASH_THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("veriframe-theme");
    var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {}
})();
`;

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "VeriFrame",
  description:
    "Synthetic media analysis with calibrated likelihoods, uncertainty ranges, and visual evidence.",
};

const NAV_LINKS = [
  { href: "/", label: "Analyse" },
  { href: "/accuracy", label: "Accuracy" },
  { href: "/methodology", label: "Methodology" },
  { href: "/privacy", label: "Privacy" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={cn("font-sans", geist.variable)} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      {/*
        Browser extensions (Grammarly, password managers) inject attributes onto
        <body> before React hydrates, which reads as a server/client mismatch.
        This suppresses the warning for attributes on this element only — nested
        content is still checked normally.
      */}
      <body
        className="flex min-h-screen flex-col bg-background text-foreground"
        suppressHydrationWarning
      >
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
            <header className="sticky top-0 z-40 border-b bg-card/70 shadow-[var(--shadow-xs)] backdrop-blur supports-[backdrop-filter]:bg-card/70">
              <div className="mx-auto flex max-w-4xl items-center gap-2 px-4 py-4 sm:gap-4 sm:px-6">
                <Link
                  href="/"
                  className="flex shrink-0 items-center gap-2 text-lg font-semibold tracking-tight"
                >
                  <span
                    aria-hidden="true"
                    className="inline-flex size-6 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground"
                  >
                    V
                  </span>
                  <span className="hidden sm:inline">VeriFrame</span>
                </Link>
                {/* Scrolls within its own row on narrow viewports rather than
                    letting the whole page overflow horizontally — logo and
                    toggle stay put either way. */}
                <NavLinks links={NAV_LINKS} />
                <ThemeToggle />
              </div>
            </header>

            <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-6 py-8">
              {children}
            </main>

            <Footer />
          </Providers>
        </TooltipProvider>
      </body>
    </html>
  );
}
