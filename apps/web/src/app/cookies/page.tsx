export const metadata = {
  title: "Cookie policy — VeriFrame",
};

export default function CookiesPage() {
  return (
    <article className="max-w-none space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Cookie policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          What VeriFrame stores in your browser, and what it deliberately does not.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">The short version</h2>
        <p className="text-muted-foreground">
          VeriFrame does not use tracking or advertising cookies, and does not run any
          analytics or third-party tracking script. There is no cookie consent banner
          because there is nothing non-essential to consent to. If that ever changes — an
          analytics tool is added, for instance — this page and a consent mechanism will be
          updated before it ships, not after.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">What is actually stored</h2>
        <ul className="list-disc space-y-2 pl-5 text-muted-foreground">
          <li>
            <strong className="text-foreground">Theme preference</strong> — one entry in
            your browser&rsquo;s local storage (<code>veriframe-theme</code>), holding only
            <code>&quot;light&quot;</code> or <code>&quot;dark&quot;</code>. It never leaves
            your browser, is not sent to our servers, and carries no personal data. This is
            technically local storage rather than a cookie, but it is the only piece of
            client-side state the site itself sets, so it is disclosed here for completeness.
          </li>
          <li>
            <strong className="text-foreground">Sign-in session</strong> — when
            account-based features are enabled in production, our authentication provider
            (Clerk) sets its own session cookies to keep you signed in. These are functional,
            not advertising or tracking cookies: they exist so the service can tell your
            requests apart from another signed-in user&rsquo;s, which is what makes
            per-account rate limiting and report ownership possible. We do not read or
            repurpose them ourselves.
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">What we don&rsquo;t do</h2>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>No advertising or retargeting cookies.</li>
          <li>No analytics, session-recording, or heatmap scripts.</li>
          <li>No third-party trackers embedded in any page.</li>
          <li>No cookies set by the browser extension beyond what per-item analysis requires.</li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Managing storage</h2>
        <p className="text-muted-foreground">
          You can clear the theme preference at any time by clearing your browser&rsquo;s
          site data for this domain, or by toggling the theme control in the header, which
          overwrites it. Clearing it simply resets the site to your operating system&rsquo;s
          light/dark preference on your next visit.
        </p>
      </section>
    </article>
  );
}
