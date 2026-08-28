import { REPORT_FOOTER_DISCLAIMER, type AnalysisReport } from "@veriframe/core";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { AlertTriangle, Info } from "lucide-react";

import { ConclusionPanel } from "./ConclusionPanel";
import { FaceFindings } from "./FaceFindings";
import { ScoreBand } from "./ScoreBand";
import { TimelineChart } from "./TimelineChart";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function ReportView({ report }: { report: AnalysisReport }) {
  const { envelope } = report;

  const faces = report.faces ?? [];
  const isVideo = report.media_meta.kind === "video";
  const isAudio = report.media_meta.kind === "audio";
  const unit = isVideo ? "frame" : isAudio ? "clip" : "face";

  return (
    <div className="space-y-5">
      {report.conclusion && (
        <ConclusionPanel conclusion={report.conclusion} unit={unit} />
      )}

      <Section title={faces.length > 1 ? "Overall assessment" : "Assessment"}>
        <ScoreBand score={report.score} uncertainty={report.uncertainty} />
        {faces.length > 1 && (
          <p className="mt-3 text-sm text-muted-foreground">
            This is the highest of the {faces.length} individual {unit} scores,
            adjusted for the caveats below.{" "}
            {isVideo
              ? `Sampled ${unit}s are reported separately further down.`
              : `Each ${unit} is reported separately further down.`}
          </p>
        )}
      </Section>

      {/*
        Principle 3: limitations are surfaced next to the result, not buried.
        When the input is outside the training envelope that fact appears above
        the evidence, because it changes how the evidence should be read.
      */}
      {!envelope.in_distribution && (
        <Alert variant="destructive" className="border-amber-300 bg-amber-50 dark:border-amber-900 dark:bg-amber-950">
          <AlertTriangle className="text-amber-600 dark:text-amber-400" />
          <AlertTitle className="text-amber-900 dark:text-amber-200">Confidence reduced</AlertTitle>
          <AlertDescription className="text-amber-900/90 dark:text-amber-200/90">
            This input falls outside the range the detector was validated on. The
            reported likelihood has been moved toward &ldquo;inconclusive&rdquo; and its
            range widened for the reasons below.
          </AlertDescription>
          <ul className="col-start-2 mt-2 space-y-1.5">
            {envelope.penalties.map((penalty, index) => (
              <li key={index} className="text-sm text-amber-900/90 dark:text-amber-200/90">
                {penalty.reason}
              </li>
            ))}
          </ul>
        </Alert>
      )}

      {envelope.in_distribution && envelope.penalties.length > 0 && (
        <Alert>
          <Info />
          <AlertTitle>Caveats</AlertTitle>
          <ul className="col-start-2 mt-2 space-y-1.5">
            {envelope.penalties.map((penalty, index) => (
              <li key={index} className="text-sm text-muted-foreground">
                {penalty.reason}
              </li>
            ))}
          </ul>
        </Alert>
      )}

      <Section title="Evidence">
        {report.streams.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No detector was able to run on this media, so there is no evidence to
            show. This is why the result above is inconclusive rather than clean.
          </p>
        ) : (
          <div className="space-y-6">
            {report.streams.map((stream, streamIndex) => (
              <div key={stream.name}>
                {streamIndex > 0 && <Separator className="mb-6" />}
                <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <h3 className="font-medium capitalize">{stream.name.replace(/_/g, " ")} analysis</h3>
                  <span className="text-sm text-muted-foreground">
                    raw score {stream.score.toFixed(3)} · weight {stream.weight}
                  </span>
                </div>

                <div className="space-y-3">
                  {stream.artifacts.map((artifact, index) => {
                    if (artifact.type === "face_map") {
                      return (
                        <figure key={index}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={artifact.url}
                            alt={artifact.label}
                            className="w-full rounded-md border"
                          />
                          <figcaption className="mt-1 text-xs text-muted-foreground">
                            {artifact.label}. Box colour matches each face&rsquo;s band.
                          </figcaption>
                        </figure>
                      );
                    }

                    if (artifact.type === "timeline") {
                      return (
                        <figure key={index}>
                          <TimelineChart points={artifact.points} />
                          <figcaption className="mt-1 text-xs text-muted-foreground">
                            {artifact.label}. Dot colour matches each sampled {unit}
                            &rsquo;s band.
                          </figcaption>
                        </figure>
                      );
                    }

                    if (artifact.type === "heatmap") {
                      return (
                        <figure key={index}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={artifact.url}
                            alt={artifact.label}
                            className="max-w-xs rounded-md border"
                          />
                          <figcaption className="mt-1 text-xs text-muted-foreground">
                            {artifact.label}. Warmer regions contributed more to the score.
                          </figcaption>
                        </figure>
                      );
                    }

                    if (artifact.type === "spectrum_plot") {
                      return (
                        <figure key={index}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={artifact.url}
                            alt={artifact.label}
                            className="w-full max-w-xl rounded-md border"
                          />
                          <figcaption className="mt-1 text-xs text-muted-foreground">
                            {artifact.label}.
                          </figcaption>
                        </figure>
                      );
                    }

                    if (artifact.type === "note") {
                      return (
                        <div key={index} className="text-sm text-muted-foreground">
                          <span className="font-medium text-foreground">{artifact.label}:</span>{" "}
                          {artifact.detail}
                        </div>
                      );
                    }

                    return null;
                  })}
                </div>

                <p className="mt-2 text-xs text-muted-foreground">
                  Models: {stream.models.join(", ")}
                </p>
              </div>
            ))}
          </div>
        )}
      </Section>

      <FaceFindings faces={faces} unit={unit} />

      <Section title="Input characteristics">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          {Object.entries(envelope.factors_checked)
            .filter(([, value]) => value)
            .map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="text-muted-foreground">{key.replace(/_/g, " ")}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
      </Section>

      <Section title="Provenance and retention">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Perceptual hash</dt>
          <dd className="font-mono text-xs">{report.provenance.phash ?? "—"}</dd>
          <dt className="text-muted-foreground">Processed at</dt>
          <dd>{new Date(report.processed_at).toLocaleString()}</dd>
          <dt className="text-muted-foreground">Media deleted after</dt>
          <dd>{new Date(report.ttl_expires_at).toLocaleString()}</dd>
        </dl>
        <p className="mt-3 text-xs text-muted-foreground">
          Model versions: {Object.values(report.model_versions).join(" · ")}
        </p>
      </Section>

      {/* Principle 6: non-dismissible, on every report. */}
      <footer className="rounded-lg border-2 border-foreground bg-muted p-4">
        <p className="text-sm font-medium">{REPORT_FOOTER_DISCLAIMER}</p>
      </footer>
    </div>
  );
}
