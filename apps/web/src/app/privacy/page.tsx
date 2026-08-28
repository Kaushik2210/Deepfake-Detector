const TTL_HOURS = Number(process.env.MEDIA_TTL_HOURS ?? 24);

export const metadata = {
  title: "Privacy policy — VeriFrame",
};

export default function PrivacyPage() {
  return (
    <article className="max-w-none space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Privacy policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Applies to the VeriFrame web application and browser extension.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">What we collect</h2>
        <p className="text-muted-foreground">
          Only media you explicitly choose to analyse, plus the account identifier
          supplied by our authentication provider. Nothing is collected in the
          background. The browser extension never uploads media without a separate,
          per-item action from you.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">How long we keep it</h2>
        <p className="text-muted-foreground">
          Uploaded media is deleted automatically {TTL_HOURS} hours after upload. Two
          things can happen to your data, and they differ:
        </p>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>
            <strong className="text-foreground">Automatic expiry.</strong> After{" "}
            {TTL_HOURS} hours the stored file is deleted. The report itself remains
            visible to you, along with the media&rsquo;s perceptual hash — a short
            irreversible fingerprint that cannot be used to reconstruct or view the
            original — so a repeat analysis of the same file can reuse the earlier
            result.
          </li>
          <li>
            <strong className="text-foreground">Deleting it yourself.</strong> The
            delete control on any report removes everything immediately: the stored
            file, the report, and the perceptual hash. Nothing about that upload is
            retained.
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">What we never do</h2>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>No face recognition, identity matching, or subject database.</li>
          <li>No selling or sharing of uploaded media with third parties.</li>
          <li>No raw media content written to our logs.</li>
          <li>No background scanning of pages you visit.</li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Your rights</h2>
        <p className="text-muted-foreground">
          Under India&rsquo;s Digital Personal Data Protection Act 2023 and the GDPR you
          may access, correct, or delete your data at any time. Deletion is available
          directly in the product via the delete control on each report; it takes
          effect immediately rather than being queued.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Analysis results are not proof</h2>
        <p className="text-muted-foreground">
          VeriFrame reports a likelihood with an explicit uncertainty range, never a
          verdict. Results are a signal for human review and are not admissible as
          forensic evidence on their own.
        </p>
      </section>
    </article>
  );
}
