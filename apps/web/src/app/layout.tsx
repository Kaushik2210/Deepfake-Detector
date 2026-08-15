import type { Metadata } from "next";
import Link from "next/link";

import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "VeriFrame",
  description:
    "Synthetic media analysis with calibrated likelihoods, uncertainty ranges, and visual evidence.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      {/*
        Browser extensions (Grammarly, password managers) inject attributes onto
        <body> before React hydrates, which reads as a server/client mismatch.
        This suppresses the warning for attributes on this element only — nested
        content is still checked normally.
      */}
      <body className="min-h-screen" suppressHydrationWarning>
        <Providers>
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
              <Link href="/" className="text-lg font-semibold">
                VeriFrame
              </Link>
              <nav className="flex gap-5 text-sm text-slate-600">
                <Link href="/" className="hover:text-slate-900">
                  Analyse
                </Link>
                <Link href="/accuracy" className="hover:text-slate-900">
                  Accuracy
                </Link>
                <Link href="/privacy" className="hover:text-slate-900">
                  Privacy
                </Link>
              </nav>
            </div>
          </header>

          <main className="mx-auto max-w-4xl px-6 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
