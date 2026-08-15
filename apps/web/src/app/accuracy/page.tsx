import { latestEvalReport, type StreamMetrics } from "@/lib/eval-report";

export const metadata = {
  title: "Model accuracy — VeriFrame",
};

// Read at request time so the page reflects the newest report without a rebuild.
export const dynamic = "force-dynamic";

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="border-b border-slate-100 py-2 last:border-0">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm text-slate-600">{label}</span>
        <span className="font-mono text-sm font-medium text-slate-900">{value}</span>
      </div>
      {note && <p className="mt-0.5 text-xs text-slate-500">{note}</p>}
    </div>
  );
}

function StreamCard({ name, raw }: { name: string; raw: StreamMetrics }) {
  const [lo, hi] = raw.auc_ci95;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="font-medium capitalize text-slate-900">{name}</h3>
        <span className="text-xs text-slate-500">
          n = {raw.n} ({raw.n_positive} manipulated / {raw.n_negative} authentic)
        </span>
      </div>

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
    </div>
  );
}

export default async function AccuracyPage() {
  const report = await latestEvalReport();

  if (!report) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Model accuracy</h1>
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-5">
          <p className="font-medium text-amber-900">No evaluation has been run yet.</p>
          <p className="mt-2 text-sm text-amber-800">
            This page renders only from the output of our own evaluation harness. Until
            it has been run there is nothing to show, and we will not publish a figure
            that does not trace to a measured result.
          </p>
        </div>
      </div>
    );
  }

  const { provenance, datasets, coverage, cross_dataset_metrics: cross } = report;
  const calibrationSet = datasets[provenance.calibration_dataset];
  const reportingSet = datasets[provenance.reporting_dataset];
  const robustness = report.robustness_auc_by_jpeg_quality ?? {};
  const robustnessStreams = [
    ...new Set(Object.values(robustness).flatMap((row) => Object.keys(row))),
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Model accuracy</h1>
        <p className="mt-2 text-slate-600">
          Every figure here is read from our evaluation harness output, generated{" "}
          {new Date(provenance.generated_at).toLocaleDateString()}. Nothing on this page
          is hand-entered.
        </p>
      </div>

      {/* Caveats first: a reader who stops after the headline should still have them. */}
      <section className="rounded-lg border-2 border-slate-900 bg-white p-5">
        <h2 className="font-medium text-slate-900">How to read these numbers</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-700">
          <li>
            These describe performance on two specific collections of images, not on
            media in general. Detectors degrade sharply on manipulation methods they
            have not seen, and the methods in circulation change faster than any fixed
            test set.
          </li>
          <li>
            Results are reported on <strong>{reportingSet?.hf_id}</strong>, which is a
            different corpus from the one calibration was fitted on. In-dataset
            numbers — the ones most published results quote — are higher and less
            meaningful.
          </li>
          <li>
            {provenance.samples_per_dataset} images were sampled per corpus. Where that
            is too few to measure something, the row below says so instead of showing a
            number.
          </li>
          <li>
            The classifier&rsquo;s training data is not fully published, so overlap with
            these test corpora cannot be ruled out. If it exists, these figures are
            optimistic.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Cross-dataset results
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          {Object.entries(cross).map(([name, entry]) => (
            <StreamCard key={name} name={name} raw={entry.raw} />
          ))}
        </div>
        {Object.keys(cross).length === 0 && (
          <p className="text-sm text-slate-600">
            No stream produced enough scored samples to report.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Fusion weights
        </h2>
        <p className="mb-3 text-sm text-slate-600">
          Derived from each stream&rsquo;s measured performance on the calibration split,
          never chosen by hand. A stream that performs at chance receives zero weight.
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="pb-2 font-medium">Stream</th>
              <th className="pb-2 font-medium">Validation AUC</th>
              <th className="pb-2 font-medium">Weight</th>
            </tr>
          </thead>
          <tbody>
            {report.fusion_weights.map((w) => (
              <tr key={w.stream} className="border-b border-slate-100 last:border-0">
                <td className="py-2 capitalize text-slate-900">{w.stream}</td>
                <td className="py-2 font-mono text-slate-700">{w.auc.toFixed(4)}</td>
                <td className="py-2 font-mono text-slate-700">{w.weight.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {Object.keys(robustness).length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Degradation under recompression
          </h2>
          <p className="mb-3 text-sm text-slate-600">
            AUC after re-encoding the test images at each JPEG quality. Most media
            arrives recompressed, so this is closer to real conditions than the headline.
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="pb-2 font-medium">JPEG quality</th>
                {robustnessStreams.map((s) => (
                  <th key={s} className="pb-2 font-medium capitalize">
                    {s}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.keys(robustness)
                .sort((a, b) => Number(b) - Number(a))
                .map((quality) => (
                  <tr key={quality} className="border-b border-slate-100 last:border-0">
                    <td className="py-2 text-slate-900">q{quality}</td>
                    {robustnessStreams.map((s) => (
                      <td key={s} className="py-2 font-mono text-slate-700">
                        {robustness[quality][s]?.toFixed(4) ?? "—"}
                      </td>
                    ))}
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
      )}

      {report.provenance_stream && !report.provenance_stream.measurable && (
        <section className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Provenance stream
          </h2>
          <p className="text-sm text-slate-700">{report.provenance_stream.note}</p>
        </section>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-5 text-sm">
        <h2 className="mb-3 font-semibold uppercase tracking-wide text-slate-500">
          Evaluation corpora
        </h2>
        <dl className="space-y-3">
          {[
            [calibrationSet, "calibration", provenance.calibration_dataset],
            [reportingSet, "reporting", provenance.reporting_dataset],
          ].map(([set, role, key]) =>
            set && typeof set !== "string" ? (
              <div key={key as string}>
                <dt className="font-mono text-slate-900">{set.hf_id}</dt>
                <dd className="text-slate-600">
                  {role as string} · {set.licence} · {set.description}
                  {" · "}
                  {coverage[key as string]?.scored ?? 0} scored,{" "}
                  {coverage[key as string]?.no_face_detected ?? 0} with no detectable face
                </dd>
              </div>
            ) : null,
          )}
        </dl>
      </section>
    </div>
  );
}
