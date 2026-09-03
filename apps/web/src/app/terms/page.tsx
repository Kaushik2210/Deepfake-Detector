export const metadata = {
  title: "Terms of use — VeriFrame",
};

export default function TermsPage() {
  return (
    <article className="max-w-none space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Terms of use</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Applies to the VeriFrame web application, browser extension, and public API.
        </p>
      </div>

      <section className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950">
        <p className="text-sm text-amber-900 dark:text-amber-200">
          This is a product-level draft describing what VeriFrame actually does and does
          not do. It has not been reviewed by a lawyer — get it reviewed before it covers a
          real deployment handling real users&rsquo; data.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">What VeriFrame is</h2>
        <p className="text-muted-foreground">
          VeriFrame analyses an image, video, or audio clip you submit and returns a
          calibrated probability, an uncertainty range, and visual evidence for how likely
          it is to have been synthetically generated or manipulated. It never returns a
          binary &ldquo;fake&rdquo; or &ldquo;real&rdquo; label. Every result is a signal for
          human review, not proof, and is not admissible as forensic evidence on its own.
          Accuracy figures shown anywhere in the product trace to a dated evaluation report
          under <code>services/inference/eval/reports/</code> — see the{" "}
          <a href="/accuracy" className="underline underline-offset-2">
            accuracy page
          </a>{" "}
          and{" "}
          <a href="/methodology" className="underline underline-offset-2">
            methodology page
          </a>{" "}
          for what those numbers do and do not support.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Acceptable use</h2>
        <p className="text-muted-foreground">You agree not to use VeriFrame to:</p>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>
            Identify, deanonymize, or investigate a specific person. VeriFrame detects
            manipulation; it does not perform face recognition or identity matching, and it
            is not built or licensed for that purpose.
          </li>
          <li>
            Repeatedly submit the same person&rsquo;s genuine content in an attempt to
            harass them by &ldquo;proving&rdquo; it is fake, or otherwise use a report as a
            tool for harassment, defamation, or intimidation. This is the specific misuse
            pattern the rate limits and abuse-pattern logging described below exist to
            catch.
          </li>
          <li>
            Present a VeriFrame report, on its own, as proof of authenticity or forgery in a
            legal, journalistic, or accusatory context without independent corroboration.
          </li>
          <li>
            Circumvent or attempt to circumvent rate limits, or submit content you do not
            have the legal right to analyse.
          </li>
          <li>
            Upload content that is otherwise unlawful to possess or distribute in your
            jurisdiction.
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Rate limits and fair use</h2>
        <p className="text-muted-foreground">
          To keep the service usable for everyone and to make the harassment pattern above
          harder to run at scale, requests are rate-limited: the web app allows 10 analyses
          per minute per signed-in account, and the public API allows 20 analyses and 60
          hash lookups per minute per IP address by default. Requests beyond these limits
          are rejected, not queued. Unusually frequent repeat lookups of the same piece of
          content are logged as a possible abuse pattern even when individually within
          limits.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Your content</h2>
        <p className="text-muted-foreground">
          You retain all rights to media you upload. Submitting it to VeriFrame grants us
          only the limited right to process it for the purpose of generating your report.
          Upload requires explicit, per-item consent, enforced by the service itself and not
          only shown in the interface. Uploaded media is deleted automatically 24 hours
          after upload, or immediately if you delete it yourself — see the{" "}
          <a href="/privacy" className="underline underline-offset-2">
            privacy policy
          </a>{" "}
          for exactly what is and is not retained after either path.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">No warranty</h2>
        <p className="text-muted-foreground">
          VeriFrame is provided &ldquo;as is,&rdquo; without warranty of any kind, express or
          implied, including accuracy, fitness for a particular purpose, or non-infringement.
          Detectors degrade on manipulation methods they have not seen, and the generators in
          circulation change faster than any fixed evaluation set — the measured limitations
          of the current models are stated plainly on the{" "}
          <a href="/accuracy" className="underline underline-offset-2">
            accuracy
          </a>{" "}
          and{" "}
          <a href="/methodology" className="underline underline-offset-2">
            methodology
          </a>{" "}
          pages rather than in this document, because those numbers change as the harness is
          re-run and this document should not have to.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Suspension and termination</h2>
        <p className="text-muted-foreground">
          Access may be suspended or terminated for violating the acceptable-use terms
          above, for abusive request patterns, or to protect the service or its other users.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Changes to these terms</h2>
        <p className="text-muted-foreground">
          These terms may change as the product changes. Material changes will be reflected
          by updating this page; continued use after a change constitutes acceptance of the
          updated terms.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Who operates VeriFrame</h2>
        <p className="text-muted-foreground">
          VeriFrame is an individual project operated by Kaushik, not a registered company —
          there is no separate corporate entity to name here, and this document should not
          be read to imply one.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Governing law and contact</h2>
        <p className="text-muted-foreground">
          These terms are governed by the laws of India, and any dispute arising from them is
          subject to the exclusive jurisdiction of the courts of India. For questions about
          these terms, contact{" "}
          <a href="mailto:svkaushik2210@gmail.com" className="underline underline-offset-2">
            svkaushik2210@gmail.com
          </a>
          .
        </p>
      </section>
    </article>
  );
}
