"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";

const STORAGE_KEY = "veriframe-theme";

function applyTheme(dark: boolean) {
  document.documentElement.classList.toggle("dark", dark);
}

/**
 * No external theme library: the CSS variables and `.dark` selector already
 * exist from the redesign, so this only needs a class toggle plus persistence.
 * The no-flash inline script in layout.tsx sets the initial class before
 * hydration; this component just keeps it in sync afterward.
 */
export function ThemeToggle() {
  const [dark, setDark] = useState<boolean | null>(null);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  if (dark === null) {
    // Avoids a hydration-mismatch flash: render nothing until the real state
    // (set by the inline script) is read from the DOM on mount.
    return <div className="size-9" aria-hidden />;
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => {
        const next = !dark;
        setDark(next);
        applyTheme(next);
        try {
          localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
        } catch {
          // Private browsing or blocked storage: theme just won't persist.
        }
      }}
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}

export const THEME_STORAGE_KEY = STORAGE_KEY;
