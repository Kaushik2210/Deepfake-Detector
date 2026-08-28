import { scoreToBand, type FaceFinding } from "@veriframe/core";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const BAND_STYLE: Record<string, { chip: string; border: string }> = {
  low: { chip: "bg-band-low", border: "border-l-band-low" },
  weak: { chip: "bg-band-weak", border: "border-l-band-weak" },
  mixed: { chip: "bg-band-mixed", border: "border-l-band-mixed" },
  strong: { chip: "bg-band-strong", border: "border-l-band-strong" },
  very_strong: { chip: "bg-band-very-strong", border: "border-l-band-very-strong" },
};

function FaceCard({ face }: { face: FaceFinding }) {
  const band = scoreToBand(face.score);
  const style = BAND_STYLE[face.band] ?? BAND_STYLE.mixed;
  const [lo, hi] = face.uncertainty;

  return (
    <Card className={cn("border-l-4 py-4", style.border)}>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded bg-foreground text-xs font-bold text-background">
                {face.index}
              </span>
              <span
                className={cn(
                  "rounded px-2 py-0.5 text-sm font-semibold text-white",
                  style.chip,
                )}
              >
                {band.label}
              </span>
            </div>
            <p className="mt-1.5 text-sm text-muted-foreground">{band.copy}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Likely range {lo.toFixed(2)}–{hi.toFixed(2)} · {face.box.w}×{face.box.h}px
              {face.timestamp !== undefined
                ? ` · at ${face.timestamp.toFixed(1)}s`
                : ` at (${face.box.x}, ${face.box.y})`}
            </p>
          </div>

          {face.heatmap_url && (
            <figure className="shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={face.heatmap_url}
                alt={`Grad-CAM heatmap for face ${face.index}`}
                className="size-24 rounded border"
              />
              <figcaption className="mt-1 text-center text-[10px] text-muted-foreground">
                what drove it
              </figcaption>
            </figure>
          )}
        </div>

        {/*
          Per-face caveats, not the image's. A small or blurred face deserves its
          own warning even when the rest of the photo is fine.
        */}
        {face.penalties.length > 0 && (
          <ul className="space-y-1.5">
            {face.penalties.map((penalty, index) => (
              <li
                key={index}
                className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200"
              >
                {penalty.reason}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function FaceFindings({
  faces,
  unit = "face",
}: {
  faces: FaceFinding[];
  // "clip" is accepted for type parity with ReportView's shared `unit` value;
  // audio reports always have an empty `faces` array, so the early return
  // below means this component never actually renders with it.
  unit?: "face" | "frame" | "clip";
}) {
  if (faces.length === 0) return null;

  // Most notable first, so a reader scanning a group photo (or a long clip)
  // sees the findings that need attention without hunting through the rest.
  const ordered = [...faces].sort((a, b) => b.score - a.score);

  return (
    <section aria-labelledby="per-unit-heading" className="rounded-lg border bg-card p-5">
      <h2
        id="per-unit-heading"
        className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Per-{unit} results
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">
        {unit === "frame"
          ? "Each sampled frame's primary face is scored on its own; timestamps match the timeline above."
          : "Each face is scored on its own. Numbers match the labelled image above."}
        {faces.length > 1 && " Sorted by score, highest first."}
      </p>

      <div className="space-y-3">
        {ordered.map((face) => (
          <FaceCard key={face.index} face={face} />
        ))}
      </div>
    </section>
  );
}
