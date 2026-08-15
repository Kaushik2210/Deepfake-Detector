import { REPORT_FOOTER_DISCLAIMER, type AnalysisReport } from "@veriframe/core";

import { ScoreBand } from "./ScoreBand";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function ReportView({ report }: { report: AnalysisReport }) {
  const { envelope } = report;

  return (
    <div className="space-y-5">
      <Section title="Assessment">
        <ScoreBand score={report.score} uncertainty={report.uncertainty} />
      </Section>

      {/*
        Principle 3: limitations are surfaced next to the result, not buried.
        When the input is outside the training envelope that fact appears above
        the evidence, because it changes how the evidence should be read.
      */}
      {!envelope.in_distribution && (
        <Section title="Confidence reduced">
          <p className="mb-3 text-sm text-slate-700">
            This input falls outside the range the detector was validated on. The
            reported likelihood has been moved toward &ldquo;inconclusive&rdquo; and its range
            widened for the reasons below.
          </p>
          <ul className="space-y-2">
            {envelope.penalties.map((penalty, index) => (
              <li
                key={index}
                className="rounded border-l-4 border-amber-400 bg-amber-50 px-3 py-2 text-sm text-slate-800"
              >
                {penalty.reason}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {envelope.in_distribution && envelope.penalties.length > 0 && (
        <Section title="Caveats">
          <ul className="space-y-2">
            {envelope.penalties.map((penalty, index) => (
              <li
                key={index}
                className="rounded border-l-4 border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-700"
              >
                {penalty.reason}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Evidence">
        {report.streams.length === 0 ? (
          <p className="text-sm text-slate-700">
            No detector was able to run on this media, so there is no evidence to
            show. This is why the result above is inconclusive rather than clean.
          </p>
        ) : (
          <div className="space-y-6">
            {report.streams.map((stream) => (
              <div key={stream.name}>
                <div className="mb-2 flex items-baseline justify-between">
                  <h3 className="font-medium capitalize text-slate-900">
                    {stream.name} analysis
                  </h3>
                  <span className="text-sm text-slate-500">
                    raw score {stream.score.toFixed(3)} · weight {stream.weight}
                  </span>
                </div>

                <div className="space-y-3">
                  {stream.artifacts.map((artifact, index) => {
                    if (artifact.type === "heatmap") {
                      return (
                        <figure key={index}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={artifact.url}
                            alt={artifact.label}
                            className="max-w-xs rounded border border-slate-200"
                          />
                          <figcaption className="mt-1 text-xs text-slate-500">
                            {artifact.label}. Warmer regions contributed more to the score.
                          </figcaption>
                        </figure>
                      );
                    }

                    if (artifact.type === "note") {
                      return (
                        <div key={index} className="text-sm text-slate-700">
                          <span className="font-medium">{artifact.label}:</span>{" "}
                          {artifact.detail}
                        </div>
                      );
                    }

                    return null;
                  })}
                </div>

                <p className="mt-2 text-xs text-slate-500">
                  Models: {stream.models.join(", ")}
                </p>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Input characteristics">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          {Object.entries(envelope.factors_checked)
            .filter(([, value]) => value)
            .map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="text-slate-500">{key.replace(/_/g, " ")}</dt>
                <dd className="text-slate-900">{value}</dd>
              </div>
            ))}
        </dl>
      </Section>

      <Section title="Provenance and retention">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-slate-500">Perceptual hash</dt>
          <dd className="font-mono text-xs text-slate-900">
            {report.provenance.phash ?? "—"}
          </dd>
          <dt className="text-slate-500">Processed at</dt>
          <dd className="text-slate-900">
            {new Date(report.processed_at).toLocaleString()}
          </dd>
          <dt className="text-slate-500">Media deleted after</dt>
          <dd className="text-slate-900">
            {new Date(report.ttl_expires_at).toLocaleString()}
          </dd>
        </dl>
        <p className="mt-3 text-xs text-slate-500">
          Model versions: {Object.values(report.model_versions).join(" · ")}
        </p>
      </Section>

      {/* Principle 6: non-dismissible, on every report. */}
      <footer className="rounded-lg border-2 border-slate-900 bg-slate-100 p-4">
        <p className="text-sm font-medium text-slate-900">
          {REPORT_FOOTER_DISCLAIMER}
        </p>
      </footer>
    </div>
  );
}
