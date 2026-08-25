import { scoreToBand, type FaceFinding } from "@veriframe/core";

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
    <article
      className={cn(
        "rounded-lg border border-slate-200 border-l-4 bg-white p-4",
        style.border,
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-slate-900 text-xs font-bold text-white">
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
          <p className="mt-1.5 text-sm text-slate-600">{band.copy}</p>
          <p className="mt-1 text-xs text-slate-500">
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
              className="h-24 w-24 rounded border border-slate-200"
            />
            <figcaption className="mt-1 text-center text-[10px] text-slate-500">
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
        <ul className="mt-3 space-y-1.5">
          {face.penalties.map((penalty, index) => (
            <li
              key={index}
              className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-900"
            >
              {penalty.reason}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function FaceFindings({
  faces,
  unit = "face",
}: {
  faces: FaceFinding[];
  unit?: "face" | "frame";
}) {
  if (faces.length === 0) return null;

  // Most notable first, so a reader scanning a group photo (or a long clip)
  // sees the findings that need attention without hunting through the rest.
  const ordered = [...faces].sort((a, b) => b.score - a.score);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Per-{unit} results
      </h2>
      <p className="mb-4 text-sm text-slate-600">
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
