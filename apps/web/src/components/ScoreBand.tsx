import { BAND_DEFINITIONS, scoreToBand } from "@veriframe/core";

import { cn } from "@/lib/utils";

const BAND_COLOR: Record<string, string> = {
  low: "bg-band-low",
  weak: "bg-band-weak",
  mixed: "bg-band-mixed",
  strong: "bg-band-strong",
  very_strong: "bg-band-very-strong",
};

interface ScoreBandProps {
  score: number;
  uncertainty: [number, number];
}

/**
 * Renders the score as an interval on the full band scale.
 *
 * The uncertainty range is drawn as a bar rather than the point estimate as a
 * marker, because a single tick invites reading the number as precise. The band
 * label carries the meaning; the number is secondary.
 */
export function ScoreBand({ score, uncertainty }: ScoreBandProps) {
  const band = scoreToBand(score);
  const [lo, hi] = uncertainty;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <span
          className={cn(
            "inline-block rounded-md px-3 py-1 text-lg font-semibold text-white",
            BAND_COLOR[band.id],
          )}
        >
          {band.label}
        </span>
        <span className="text-sm text-muted-foreground">{band.copy}</span>
      </div>

      <div>
        <div
          className="relative h-8 w-full overflow-hidden rounded-md border"
          role="img"
          aria-label={`Likely range ${lo.toFixed(2)} to ${hi.toFixed(2)} on a 0 to 1 scale, point estimate ${score.toFixed(3)}`}
        >
          {BAND_DEFINITIONS.map((definition) => (
            <div
              key={definition.id}
              className={cn("absolute top-0 h-full opacity-25", BAND_COLOR[definition.id])}
              style={{
                left: `${definition.min * 100}%`,
                width: `${(definition.max - definition.min) * 100}%`,
              }}
            />
          ))}

          <div
            className="absolute top-0 h-full border-x-2 border-foreground bg-foreground/25"
            style={{ left: `${lo * 100}%`, width: `${Math.max(hi - lo, 0.004) * 100}%` }}
          />
        </div>

        <div className="mt-1 flex justify-between text-xs text-muted-foreground">
          <span>0.0</span>
          <span>0.5</span>
          <span>1.0</span>
        </div>
      </div>

      <p className="text-sm text-foreground/90">
        Estimated likelihood of manipulation:{" "}
        <strong className="font-semibold">
          {lo.toFixed(2)} – {hi.toFixed(2)}
        </strong>{" "}
        <span className="text-muted-foreground">(point estimate {score.toFixed(3)})</span>
      </p>
    </div>
  );
}
