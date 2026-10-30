import Link from "next/link";
import {
  Activity,
  FileAudio,
  FileVideo,
  ImageIcon,
  LockKeyhole,
  ScanSearch,
  ShieldCheck,
  Upload,
} from "lucide-react";

import { UploadForm } from "@/components/UploadForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TRUST_POINTS = [
  { icon: Activity, label: "Calibrated likelihood, never a verdict" },
  { icon: ScanSearch, label: "Visual evidence behind every score" },
  { icon: LockKeyhole, label: "Private by default, auto-deleted" },
];

const STEPS = [
  {
    icon: Upload,
    title: "Upload with consent",
    body: "Pick a file and confirm. Nothing leaves your browser until you do.",
  },
  {
    icon: ScanSearch,
    title: "Multi-signal analysis",
    body: "Spatial, frequency, temporal, and audio detectors run independently, then are fused.",
  },
  {
    icon: ShieldCheck,
    title: "Evidence-backed report",
    body: "A probability range, a plain-language label, heatmaps or timelines, and every caveat.",
  },
];

const MODALITIES = [
  { icon: ImageIcon, title: "Images", detail: "JPEG, PNG, WebP, BMP" },
  { icon: FileVideo, title: "Video", detail: "MP4, MOV, WebM, MKV · up to 60 s" },
  { icon: FileAudio, title: "Audio", detail: "WAV, FLAC, OGG, MP3 · up to 5 min" },
];

export default function HomePage() {
  const ttlHours = Number(process.env.MEDIA_TTL_HOURS ?? 24);

  return (
    <div className="space-y-16">
      <section className="relative -mx-4 overflow-hidden rounded-3xl border bg-card px-6 py-12 shadow-[var(--shadow-md)] sm:mx-0 sm:px-12 sm:py-16">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-32 -right-24 size-[28rem] rounded-full bg-primary/15 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-40 -left-24 size-[26rem] rounded-full bg-chart-2/15 blur-3xl"
        />

        <div className="relative grid items-start gap-10 lg:grid-cols-[1.05fr_1fr]">
          <div className="space-y-6">
            <span className="inline-flex items-center gap-2 rounded-full border bg-background/70 px-3 py-1 text-xs font-medium text-muted-foreground">
              <ShieldCheck className="size-3.5 text-primary" aria-hidden="true" />
              Synthetic-media analysis · advisory, not evidentiary
            </span>

            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              See the evidence behind
              <span className="text-primary"> every score.</span>
            </h1>

            <p className="max-w-xl text-lg leading-relaxed text-muted-foreground">
              VeriFrame estimates how likely an image, video, or audio clip is to have been
              manipulated, and shows you why. You get a calibrated probability range with its
              limitations stated up front, never a one-word verdict.
            </p>

            <ul className="space-y-3">
              {TRUST_POINTS.map(({ icon: Icon, label }) => (
                <li key={label} className="flex items-center gap-3 text-sm font-medium">
                  <span className="inline-flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                    <Icon className="size-4" aria-hidden="true" />
                  </span>
                  {label}
                </li>
              ))}
            </ul>

            <p className="text-sm text-muted-foreground">
              Every accuracy figure is read from a real evaluation run. See the{" "}
              <Link href="/accuracy" className="font-medium text-primary underline underline-offset-4">
                accuracy page
              </Link>{" "}
              for the numbers and their caveats.
            </p>
          </div>

          <div className="rounded-2xl border bg-background/60 p-5 shadow-[var(--shadow-sm)] backdrop-blur sm:p-6">
            <UploadForm ttlHours={ttlHours} />
          </div>
        </div>
      </section>

      <section aria-labelledby="how-it-works" className="space-y-6">
        <div className="space-y-2 text-center">
          <h2 id="how-it-works" className="text-2xl font-semibold tracking-tight">
            How it works
          </h2>
          <p className="mx-auto max-w-2xl text-muted-foreground">
            Three steps from file to a report you can read, challenge, and hand to a human
            reviewer.
          </p>
        </div>
        <ol className="grid gap-4 md:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, body }, index) => (
            <li key={title}>
              <Card className="h-full">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <span className="inline-flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
                      <Icon className="size-5" aria-hidden="true" />
                    </span>
                    <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Step {index + 1}
                    </span>
                  </div>
                  <CardTitle className="mt-2 text-base">{title}</CardTitle>
                </CardHeader>
                <CardContent className="text-muted-foreground">{body}</CardContent>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="modalities" className="space-y-6">
        <h2 id="modalities" className="text-center text-2xl font-semibold tracking-tight">
          One platform, three kinds of media
        </h2>
        <ul className="grid gap-4 sm:grid-cols-3">
          {MODALITIES.map(({ icon: Icon, title, detail }) => (
            <li
              key={title}
              className="flex items-center gap-4 rounded-xl border bg-card p-5 shadow-[var(--shadow-xs)]"
            >
              <span className="inline-flex size-11 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                <Icon className="size-5" aria-hidden="true" />
              </span>
              <div>
                <p className="font-medium">{title}</p>
                <p className="text-xs text-muted-foreground">{detail}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <Card className="border-amber-300/70 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/30">
        <CardHeader>
          <CardTitle className="text-base">What this tool cannot do</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
            <li>
              It cannot tell you who created a piece of media or who appears in it.
              There is no face recognition or identity matching.
            </li>
            <li>
              It cannot prove media is genuine or fabricated. Detectors degrade
              sharply on media unlike what they were validated on, and the report
              says so when that applies.
            </li>
            <li>
              Results are a signal for human review rather than proof, and are not a
              substitute for forensic examination.
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
