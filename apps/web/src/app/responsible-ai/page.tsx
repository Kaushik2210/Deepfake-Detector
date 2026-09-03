import Link from "next/link";

export const metadata = {
  title: "Responsible AI — VeriFrame",
  description:
    "VeriFrame's commitments on human oversight, identity, bias, misuse prevention, and how to dispute a result.",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-medium">{title}</h2>
      <div className="space-y-2 text-muted-foreground [&_a]:text-foreground [&_a]:underline [&_a]:underline-offset-2">
        {children}
      </div>
    </section>
  );
}

export default function ResponsibleAiPage() {
  return (
    <article className="max-w-none space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Responsible AI</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This page states VeriFrame&rsquo;s commitments in plain terms. The technical detail
          behind them — the evaluation protocol, a bias its own harness caught and fixed, the
          exact numbers — lives on the{" "}
          <Link href="/methodology">methodology page</Link>; this page is the governance
          summary a non-technical reader or reviewer would want first.
        </p>
      </div>

      <Section title="A person stays in the loop">
        <p>
          VeriFrame never outputs a verdict. Every report is a calibrated probability, an
          uncertainty range, a plain-language band (something like &ldquo;mixed signals,
          manual review advised&rdquo;, never &ldquo;fake&rdquo; or &ldquo;real&rdquo;), and
          the visual evidence behind that number — a heatmap, a per-frame timeline, or a
          frequency-spectrum plot. The design goal is a second opinion for a human reviewer
          to weigh, not an automated decision. Every report carries the same footer
          regardless of score: this result is a signal for human review, not proof, and is
          not admissible as forensic evidence on its own.
        </p>
      </Section>

      <Section title="VeriFrame does not identify people">
        <p>
          The product detects signs of manipulation in media. It has no face-recognition
          model, no identity-matching capability, and no database of subjects to match
          against. It cannot tell you who created a piece of media or who appears in it, and
          it is not built or licensed to be extended into that use — see the{" "}
          <Link href="/terms">terms of use</Link> for the acceptable-use restriction this
          backs.
        </p>
      </Section>

      <Section title="Limitations are surfaced, not buried">
        <p>
          Out-of-envelope inputs — low resolution, heavy compression, a small or poorly lit
          face, unusual audio conditions — get an explicit confidence penalty that widens the
          uncertainty range, rather than a quietly overconfident score. No accuracy figure
          anywhere in the product is hand-typed; every one traces to a dated run of the
          evaluation harness, reported cross-dataset (measured on a corpus different from the
          one used to tune the model) rather than the in-distribution number that flatters
          most published results. Where a measured gap between two detection streams turns
          out not to be statistically significant, that is stated rather than glossed over —
          see the <Link href="/accuracy">accuracy page</Link> for the current numbers,
          including where the confidence intervals are wide enough that a result should be
          read with real caution.
        </p>
      </Section>

      <Section title="Misuse prevention">
        <p>
          A synthetic-media detector can itself be misused — most concretely, to harass
          someone by repeatedly &ldquo;proving&rdquo; their genuine content is fake. Requests
          are rate-limited (per signed-in account on the web app, per IP address on the
          public API), and unusually frequent repeat checks against the same piece of content
          are logged as a possible abuse pattern even when each individual request is within
          limits. See the <Link href="/terms">terms of use</Link> for the exact limits and
          the conduct they exist to make harder.
        </p>
      </Section>

      <Section title="If you believe a report is wrong, or being used against you">
        <p>
          A VeriFrame score is a probability with a stated uncertainty range, not an
          accusation — a low-confidence or borderline result about your content is not a
          claim that you did anything wrong, and is not evidence on its own of anything. If
          you believe a report about your own content is inaccurate, or that someone is using
          a VeriFrame report to harass or misrepresent you, you can:
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            Delete your own uploaded content and its report immediately from that
            report&rsquo;s page, rather than waiting for the 24-hour automatic expiry — see{" "}
            <Link href="/privacy">what deletion actually removes</Link>.
          </li>
          <li>
            Contact{" "}
            <span className="rounded bg-muted px-1 py-0.5 font-mono text-xs text-foreground">
              [operator contact email — not yet specified]
            </span>{" "}
            to report suspected misuse of a report or request a review.
          </li>
        </ul>
      </Section>

      <Section title="This is a public, running log — including our own mistakes">
        <p>
          Architectural and methodology decisions, and their rationale, are logged
          chronologically and kept visible rather than edited away once superseded — including
          a real inverted-label bug the evaluation harness caught before it shipped, and a
          measurement bias in an earlier fusion-weighting approach that the project&rsquo;s
          own protocol surfaced and then fixed. That log (<code>DECISIONS.md</code> in the
          project repository) is the most concrete evidence of how this system is actually
          governed day to day, more so than any static policy page, this one included.
        </p>
      </Section>
    </article>
  );
}
