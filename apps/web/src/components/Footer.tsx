import Link from "next/link";

const POLICY_LINKS = [
  { href: "/terms", label: "Terms of use" },
  { href: "/privacy", label: "Privacy policy" },
  { href: "/cookies", label: "Cookie policy" },
  { href: "/responsible-ai", label: "Responsible AI" },
  { href: "/methodology", label: "Methodology" },
];

export function Footer() {
  return (
    <footer className="mt-16 border-t bg-card/40">
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-8 sm:px-6">
        <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground">
          Every VeriFrame result is a signal for human review, not proof, and is not
          admissible as forensic evidence on its own.
        </p>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {POLICY_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              {link.label}
            </Link>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          © {new Date().getFullYear()} VeriFrame. Detection is advisory, not evidentiary.
        </p>
      </div>
    </footer>
  );
}
