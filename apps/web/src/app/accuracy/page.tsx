import { latestAudioEvalReport, latestEvalReport, type StreamMetrics } from "@/lib/eval-report";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

export const metadata = {
  title: "Model accuracy — VeriFrame",
};

// Read at request time so the page reflects the newest report without a rebuild.
export const dynamic = "force-dynamic";

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="border-b py-2 last:border-0">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="font-mono text-sm font-medium">{value}</span>
      </div>
      {note && <p className="mt-0.5 text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

function StreamCard({ name, raw, label }: { name: string; raw: StreamMetrics; label?: string }) {
  const [lo, hi] = raw.auc_ci95;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-baseline justify-between gap-4">
          <CardTitle className="capitalize">{label ?? name.replace(/_/g, " ")}</CardTitle>
          <span className="text-xs text-muted-foreground">
            n = {raw.n} ({raw.n_positive} / {raw.n_negative})
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <Metric
          label="AUC"
          value={raw.auc.toFixed(4)}
          note={`95% confidence interval ${lo.toFixed(4)} – ${hi.toFixed(4)}`}
        />
        <Metric
          label="Equal error rate"
          value={raw.eer.toFixed(4)}
          note={`at threshold ${raw.eer_threshold.toFixed(4)}`}
        />
        {raw.thresholds.map((t) => (
          <Metric
            key={t.target_fpr}
            label={`TPR at ${(t.target_fpr * 100).toFixed(1)}% FPR`}
            value={t.measurable && t.tpr !== null ? t.tpr.toFixed(4) : "not measurable"}
            note={t.note}
          />
        ))}
        <Metric label="Expected calibration error" value={raw.ece.toFixed(4)} />
      </CardContent>
    </Card>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </h2>
  );
}

export default async function AccuracyPage() {
  const [report, audioReport] = await Promise.all([latestEvalReport(), latestAudioEvalReport()]);

  if (!report && !audioReport) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Model accuracy</h1>
        <Card className="border-amber-300 bg-amber-50 dark:border-amber-900 dark:bg-amber-950">
          <CardContent>
            <p className="font-medium text-amber-900 dark:text-amber-200">
              No evaluation has been run yet.
            </p>
            <p className="mt-2 text-sm text-amber-800 dark:text-amber-300">
              This page renders only from the output of our own evaluation harness. Until
              it has been run there is nothing to show, and we will not publish a figure
              that does not trace to a measured result.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Model accuracy</h1>
        <p className="mt-2 text-muted-foreground">
          Every figure here is read from our evaluation harness output. Nothing on this
          page is hand-entered.
        </p>
      </div>

      {report && <ImageAccuracySection report={report} />}
      {report && audioReport && <Separator />}
      {audioReport && <AudioAccuracySection report={audioReport} />}
    </div>
  );
}

function Separator() {
  return <div className="border-t" />;
}

function ImageAccuracySection({ report }: { report: NonNullable<Awaited<ReturnType<typeof latestEvalReport>>> }) {
  const { provenance, datasets, coverage, cross_dataset_metrics: cross } = report;
  const calibrationSet = datasets[provenance.calibration_dataset];
  const reportingSet = datasets[provenance.reporting_dataset];
  const robustness = report.robustness_auc_by_jpeg_quality ?? {};
  const robustnessStreams = [
    ...new Set(Object.values(robustness).flatMap((row) => Object.keys(row))),
  ];

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Images</h2>
        <p className="text-sm text-muted-foreground">
          Generated {new Date(provenance.generated_at).toLocaleDateString()}.
        </p>
      </div>

      {/* Caveats first: a reader who stops after the headline should still have them. */}
      <Card className="border-2 border-foreground/80">
        <CardHeader>
          <CardTitle>How to read these numbers</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>
              These describe performance on two specific collections of images, not on
              media in general. Detectors degrade sharply on manipulation methods they
              have not seen, and the methods in circulation change faster than any fixed
              test set.
            </li>
            <li>
              Results are reported on <strong className="text-foreground">{reportingSet?.hf_id}</strong>,
              which is a different corpus from the one calibration was fitted on.
              In-dataset numbers — the ones most published results quote — are higher
              and less meaningful.
            </li>
            <li>
              {provenance.samples_per_dataset} calibration images
              {provenance.validation_samples != null && provenance.final_reporting_samples != null
                ? `, ${provenance.validation_samples} weight-validation images, and ${provenance.final_reporting_samples} final held-out reporting images`
                : " were sampled per corpus"}
              . Where that is too few to measure something, the row below says so instead
              of showing a number.
            </li>
            <li>
              The classifier&rsquo;s training data is not fully published, so overlap with
              these test corpora cannot be ruled out. If it exists, these figures are
              optimistic.
            </li>
          </ul>
        </CardContent>
      </Card>

      <div>
        <SectionHeading>Cross-dataset results</SectionHeading>
        {Object.keys(cross).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No stream produced enough scored samples to report.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {Object.entries(cross).map(([name, entry]) => (
              <StreamCard key={name} name={name} raw={entry.raw} />
            ))}
          </div>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Fusion weights
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Derived from each stream&rsquo;s measured performance on a held-out
            weight-validation split of the reporting corpus — not the calibration
            corpus&rsquo;s in-distribution performance, which does not predict
            cross-dataset generalisation (see <span className="font-mono">DECISIONS.md</span>).
            Never chosen by hand. A stream that performs at chance receives zero weight.
          </p>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Stream</TableHead>
                <TableHead>Validation AUC</TableHead>
                <TableHead>Weight</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.fusion_weights.map((w) => (
                <TableRow key={w.stream}>
                  <TableCell className="capitalize">{w.stream}</TableCell>
                  <TableCell className="font-mono">{w.auc.toFixed(4)}</TableCell>
                  <TableCell className="font-mono">{w.weight.toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {robustnessStreams.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Degradation under recompression
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              AUC after re-encoding the test images at each JPEG quality. Most media
              arrives recompressed, so this is closer to real conditions than the headline.
            </p>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>JPEG quality</TableHead>
                  {robustnessStreams.map((s) => (
                    <TableHead key={s} className="capitalize">
                      {s}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.keys(robustness)
                  .sort((a, b) => Number(b) - Number(a))
                  .map((quality) => (
                    <TableRow key={quality}>
                      <TableCell>q{quality}</TableCell>
                      {robustnessStreams.map((s) => (
                        <TableCell key={s} className="font-mono">
                          {robustness[quality][s]?.toFixed(4) ?? "—"}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {report.provenance_stream && !report.provenance_stream.measurable && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Provenance stream
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{report.provenance_stream.note}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Evaluation corpora
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            {[
              [calibrationSet, "calibration", provenance.calibration_dataset],
              [reportingSet, "reporting", provenance.reporting_dataset],
            ].map(([set, role, key]) =>
              set && typeof set !== "string" ? (
                <div key={key as string}>
                  <dt className="font-mono">{set.hf_id}</dt>
                  <dd className="text-muted-foreground">
                    {role as string} · {set.licence} · {set.description}
                    {" · "}
                    {coverage[key as string]?.scored ?? 0} scored,{" "}
                    {coverage[key as string]?.no_face_detected ?? 0} with no detectable face
                  </dd>
                </div>
              ) : null,
            )}
          </dl>
        </CardContent>
      </Card>
    </section>
  );
}

function AudioAccuracySection({ report }: { report: NonNullable<Awaited<ReturnType<typeof latestAudioEvalReport>>> }) {
  const { provenance, datasets, coverage, cross_dataset_metrics: cross, fused_cross_dataset_metrics: fused } = report;
  const calibrationSet = datasets[provenance.calibration_dataset];
  const reportingSet = datasets[provenance.reporting_dataset];
  const aasistOnly = cross.audio?.raw;

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Audio</h2>
        <p className="text-sm text-muted-foreground">
          Generated {new Date(provenance.generated_at).toLocaleDateString()}.
        </p>
      </div>

      <Card className="border-2 border-foreground/80">
        <CardHeader>
          <CardTitle>How to read these numbers</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>
              These describe performance on two corpora of studio-adjacent TTS/voice-conversion
              attacks, not on real-world audio in general — phone calls, compressed voice
              notes, and background noise are exactly the out-of-distribution conditions the
              envelope check flags with a confidence penalty.
            </li>
            <li>
              Results are reported on <strong className="text-foreground">{reportingSet?.hf_id}</strong>,
              a different corpus from the one calibration was fitted on and from the corpus
              AASIST itself was trained on ({calibrationSet?.hf_id}).
            </li>
            <li>
              {provenance.samples_per_dataset} calibration clips
              {provenance.validation_samples != null && provenance.final_reporting_samples != null
                ? `, ${provenance.validation_samples} weight-validation clips, and ${provenance.final_reporting_samples} final held-out reporting clips`
                : " were sampled per corpus"}
              .
            </li>
          </ul>
        </CardContent>
      </Card>

      {fused && aasistOnly && (
        <Card>
          <CardHeader>
            <CardTitle>Does the second stream actually help?</CardTitle>
            <p className="text-sm text-muted-foreground">
              A second, independently-designed stream (harmonics-to-noise ratio) was added
              alongside AASIST. Reported honestly either way — see{" "}
              <span className="font-mono">DECISIONS.md</span> for the full story.
            </p>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead></TableHead>
                  <TableHead>AASIST alone</TableHead>
                  <TableHead>Fused</TableHead>
                  <TableHead>Δ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="font-medium">AUC</TableCell>
                  <TableCell className="font-mono">{aasistOnly.auc.toFixed(4)}</TableCell>
                  <TableCell className="font-mono">{fused.auc.toFixed(4)}</TableCell>
                  <TableCell
                    className={cn(
                      "font-mono",
                      fused.auc >= aasistOnly.auc ? "text-emerald-600" : "text-destructive",
                    )}
                  >
                    {fused.auc >= aasistOnly.auc ? "+" : ""}
                    {(fused.auc - aasistOnly.auc).toFixed(4)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
            {fused.auc < aasistOnly.auc && (
              <p className="mt-3 text-sm text-muted-foreground">
                Fusion did not improve cross-dataset AUC here. The measured weight ships
                as-is rather than being hand-corrected — see the fusion weights below.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <div>
        <SectionHeading>Cross-dataset results</SectionHeading>
        {Object.keys(cross).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No stream produced enough scored samples to report.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {Object.entries(cross).map(([name, entry]) => (
              <StreamCard key={name} name={name} raw={entry.raw} />
            ))}
          </div>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Fusion weights
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Derived from each stream&rsquo;s measured performance on a held-out
            weight-validation split of the reporting corpus — not the calibration
            corpus&rsquo;s in-distribution performance, which does not predict
            cross-dataset generalisation (see <span className="font-mono">DECISIONS.md</span>).
            Never chosen by hand.
          </p>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Stream</TableHead>
                <TableHead>Validation AUC</TableHead>
                <TableHead>Weight</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.fusion_weights.map((w) => (
                <TableRow key={w.stream}>
                  <TableCell className="capitalize">{w.stream.replace(/_/g, " ")}</TableCell>
                  <TableCell className="font-mono">{w.auc.toFixed(4)}</TableCell>
                  <TableCell className="font-mono">{w.weight.toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Evaluation corpora
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            {[
              [calibrationSet, "calibration", provenance.calibration_dataset],
              [reportingSet, "reporting", provenance.reporting_dataset],
            ].map(([set, role, key]) =>
              set && typeof set !== "string" ? (
                <div key={key as string}>
                  <dt className="font-mono">{set.hf_id}</dt>
                  <dd className="text-muted-foreground">
                    {role as string} · {set.licence} · {set.description}
                    {" · "}
                    {coverage[key as string]?.scored ?? 0} scored
                  </dd>
                </div>
              ) : null,
            )}
          </dl>
        </CardContent>
      </Card>
    </section>
  );
}
