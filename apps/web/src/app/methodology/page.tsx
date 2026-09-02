import Link from "next/link";

import { latestAudioEvalReport, latestEvalReport } from "@/lib/eval-report";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata = {
  title: "Methodology — VeriFrame",
  description:
    "How VeriFrame's cross-dataset evaluation protocol works, a fusion-weight bias it caught, and the fix — written for anyone citing or auditing this project.",
};

export const dynamic = "force-dynamic";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <div className="space-y-3 text-sm leading-relaxed text-muted-foreground [&_strong]:text-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs [&_code]:text-foreground">
        {children}
      </div>
    </section>
  );
}

export default async function MethodologyPage() {
  const [report, audioReport] = await Promise.all([latestEvalReport(), latestAudioEvalReport()]);

  return (
    <article className="max-w-none space-y-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Methodology</h1>
        <p className="mt-2 text-muted-foreground">
          What this page is for: a single, citable account of how VeriFrame is evaluated, a
          real measurement bias its own protocol caught, and the fix — written for anyone
          auditing the numbers on the{" "}
          <Link href="/accuracy" className="underline underline-offset-2">
            accuracy page
          </Link>{" "}
          or citing this project. Every number below traces to a dated file in{" "}
          <code>services/inference/eval/reports/</code>; nothing here is a marketing figure.
        </p>
      </div>

      <Section title="Architecture in brief">
        <p>
          Each media kind is scored by two or more independent, architecturally distinct
          streams. Images: a ViT classifier (<strong>spatial</strong>) and a hand-derived
          frequency/DCT-artifact stream (<strong>frequency</strong>); audio: a graph-attention
          anti-spoofing network,{" "}
          <a
            className="underline underline-offset-2"
            href="https://github.com/clovaai/aasist"
            target="_blank"
            rel="noreferrer"
          >
            AASIST
          </a>{" "}
          (<strong>audio</strong>), and a hand-derived harmonics-to-noise-ratio stream (
          <strong>audio_frequency</strong>). A provenance stream reads embedded C2PA
          manifests and generator metadata where present. Streams are combined by a weighted
          average, with provenance able to override the statistical streams outright when
          cryptographic signing or self-declared generator metadata is present.
        </p>
      </Section>

      <Section title="The evaluation protocol">
        <p>
          Two rules are enforced in code, not just convention. <strong>Cross-dataset is
          mandatory</strong>: a temperature-scaling parameter is fitted on one corpus, and
          every headline number is measured on a different one that shares no
          images/utterances with it — passing the same corpus for both is a CLI error in
          the harness. <strong>Unmeasurable metrics say so</strong>: true-positive rate at a
          false-positive rate the negative sample can&rsquo;t resolve returns a labelled
          &ldquo;not measurable&rdquo; row instead of a number built from a handful of
          events, and every AUC carries a bootstrap 95% confidence interval rather than a
          bare point estimate.
        </p>
      </Section>

      <Section title="A finding the protocol itself caught: calibration AUC doesn't predict cross-dataset generalisation">
        <p>
          Fusion weights were originally derived from each stream&rsquo;s AUC on the{" "}
          <em>calibration</em> corpus — the same split used to fit temperature scaling.
          That is in-distribution performance, and it turned out to be a biased predictor of
          how a stream performs on genuinely unseen data, independently confirmed in two
          unrelated modalities:
        </p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong>Images (Phase 3).</strong> The frequency stream scored 0.713 AUC on the
            calibration split against spatial&rsquo;s 0.534, and received 86.4% of the fusion
            weight on that basis. On the held-out reporting split, spatial generalised
            better (0.663 vs. 0.589) — the more heavily weighted stream was the one that
            transferred worse.
          </li>
          <li>
            <strong>Audio (Phase 7).</strong> A newly added harmonics-to-noise-ratio stream
            (<code>audio_frequency</code>) scored 0.907 AUC in-distribution but only 0.685
            cross-dataset. Fusing it in at its calibration-derived weight <em>reduced</em>{" "}
            cross-dataset AUC from 0.962 (AASIST alone) to 0.933.
          </li>
        </ul>
        <p>
          Both are documented in full, including the exact numbers and dates, in{" "}
          <code>DECISIONS.md</code>.
        </p>
      </Section>

      <Section title="The fix: fusion weights from a genuine held-out validation split">
        <p>
          The methodologically purest fix is a third, fully independent corpus — fit
          calibration on one, select the fitting procedure on a second, report only on a
          third untouched by either. That is not yet implemented: it is blocked on finding a
          second commercially-licensed, reporting-quality corpus per media kind (see the
          rejected-candidates lists in <code>LICENSES.md</code> — most attempts at a third
          corpus failed on licence or provenance grounds before this one).
        </p>
        <p>
          The fix actually shipped gets the same guarantee from the one reporting corpus
          that already exists: it is split once, stratified by label, into a{" "}
          <strong>weight-validation half</strong> (a genuine cross-dataset measurement,
          since it comes from a different corpus than calibration — used only to derive
          fusion weights) and a <strong>final reporting half</strong>, touched exactly once,
          after weights are already fixed, for the headline numbers. Implemented once in{" "}
          <code>eval/splits.py</code> and applied identically to both harnesses.
        </p>
        <p>Measured effect of switching from calibration-split to validation-split weights:</p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong>Audio:</strong> the fused-vs-alone AUC gap shrank from <strong>−0.0294</strong>{" "}
            to <strong>−0.0064</strong> — a &gt;4× reduction, though it did not close to
            zero.
          </li>
          <li>
            <strong>Images:</strong> the calibration-split weights (86.4% / 13.6%) corrected
            to near-even (spatial 51.5%, frequency 48.5%), matching what the genuine
            cross-dataset validation AUCs actually show (0.592 vs. 0.586 — nearly tied).
          </li>
        </ul>
        {(report || audioReport) && (
          <div className="grid gap-4 sm:grid-cols-2">
            {report && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">
                    Current image weights ({new Date(report.provenance.generated_at).toLocaleDateString()})
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  {report.fusion_weights.map((w) => (
                    <div key={w.stream} className="flex justify-between font-mono">
                      <span className="capitalize text-muted-foreground">{w.stream}</span>
                      <span>{w.weight.toFixed(4)}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
            {audioReport && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">
                    Current audio weights (
                    {new Date(audioReport.provenance.generated_at).toLocaleDateString()})
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  {audioReport.fusion_weights.map((w) => (
                    <div key={w.stream} className="flex justify-between font-mono">
                      <span className="capitalize text-muted-foreground">
                        {w.stream.replace(/_/g, " ")}
                      </span>
                      <span>{w.weight.toFixed(4)}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </Section>

      <Section title="Statistical rigor added on top of the fix">
        <p>
          Fixing <em>how</em> weights are derived does not by itself tell you whether a
          measured gap between two streams is a real, reproducible difference or sampling
          noise on a few hundred clips. Two additional checks now run alongside every
          harness pass, visible on the{" "}
          <Link href="/accuracy" className="underline underline-offset-2">
            accuracy page
          </Link>{" "}
          for whichever report is current:
        </p>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong>Paired bootstrap significance testing</strong> between the two streams on
            the final held-out split — the same resampled indices applied to both streams
            per replicate, since they were scored on the exact same clips, producing a
            95% CI and two-sided p-value on the AUC difference rather than eyeballing two
            independent confidence intervals for overlap.
          </li>
          <li>
            <strong>Weight-stability bootstrap</strong>: 500 resamples of the
            weight-validation split itself, fusion weights rederived from{" "}
            <code>derive_fusion_weights</code> exactly as the real harness does each time.
            The median and p10–p90 spread across resamples answers whether a given weight
            split is a stable property of the two streams or a lucky draw from that
            particular validation sample — deliberately not a rerun of the whole harness at
            a different seed, which would conflate this sampling question with unrelated
            decode/network noise from rescoring every clip.
          </li>
        </ul>
      </Section>

      <Section title="Limitations, stated plainly">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            Sample sizes are modest by publication standards (typically low hundreds per
            split) — a direct consequence of scoring corpora over ranged HTTP against
            rate-limited public hosts rather than a local copy. Every report states its
            exact n, and every AUC carries its bootstrap interval so the resulting sampling
            error is visible rather than implied.
          </li>
          <li>
            Both reporting corpora describe a narrow slice of real-world conditions — DF40
            manipulation techniques for images, studio-adjacent TTS/voice-conversion attacks
            for audio — not the full space of generators in circulation, which changes
            faster than any fixed evaluation set.
          </li>
          <li>
            The validation-split fix removes the calibration-split bias but does not, and
            cannot, prove a stream generalises to media unlike anything in either corpus.
            That is a distinct, harder claim this protocol does not make.
          </li>
        </ul>
      </Section>

      <Section title="For researchers">
        <p>
          The harness that produces every number on this site is at{" "}
          <code>services/inference/eval/</code> (<code>run.py</code> for images,{" "}
          <code>audio_run.py</code> for audio), documented in its own{" "}
          <code>README.md</code>. Architectural decisions and their rationale — including
          every wrong AI-generated claim caught and corrected along the way — are logged
          chronologically in <code>DECISIONS.md</code>. Dataset and model licences, and every
          candidate rejected and why, are in <code>LICENSES.md</code>.
        </p>
        <p>
          Detection is advisory, not evidentiary — see the{" "}
          <Link href="/privacy" className="underline underline-offset-2">
            privacy policy
          </Link>{" "}
          for the full statement. Nothing on this page or the accuracy page constitutes a
          claim about any individual piece of media.
        </p>
      </Section>
    </article>
  );
}
