import type { CalibrationBin } from "@/lib/eval-report";

const SIZE = 320;
const PAD = 38;
const PLOT = SIZE - PAD * 2;
const HIST_HEIGHT = PLOT * 0.22;

const toX = (v: number) => PAD + v * PLOT;
const toY = (v: number) => PAD + (1 - v) * PLOT;

/**
 * Reliability diagram: observed frequency vs. claimed confidence per bin,
 * against the "perfectly calibrated" diagonal, with a faint histogram strip
 * showing how many samples fell in each bin -- a confident-looking point
 * built from two samples should read differently than one built from two
 * hundred, and the strip is what makes that visible.
 */
export function ReliabilityDiagram({ bins, ece, caption }: { bins: CalibrationBin[]; ece: number; caption?: string }) {
  const label = caption ?? `Reliability diagram, expected calibration error ${ece.toFixed(4)}`;
  const maxCount = Math.max(...bins.map((b) => b.count), 1);
  const populated = bins.filter((b) => b.count > 0);

  return (
    <figure className="space-y-2">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={label}
        className="h-auto w-full max-w-sm"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <line
            key={`gx-${t}`}
            x1={toX(t)}
            y1={PAD}
            x2={toX(t)}
            y2={SIZE - PAD}
            stroke="var(--border)"
            strokeWidth={0.5}
          />
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <line
            key={`gy-${t}`}
            x1={PAD}
            y1={toY(t)}
            x2={SIZE - PAD}
            y2={toY(t)}
            stroke="var(--border)"
            strokeWidth={0.5}
          />
        ))}

        {/* bin-population histogram, faint, anchored to the bottom axis */}
        {bins.map((b) => {
          const barW = PLOT / bins.length;
          const x = toX(b.lower);
          const h = (b.count / maxCount) * HIST_HEIGHT;
          return (
            <rect
              key={`${b.lower}-${b.upper}`}
              x={x + 1}
              y={SIZE - PAD - h}
              width={Math.max(barW - 2, 0)}
              height={h}
              fill="var(--muted)"
            />
          );
        })}

        {/* perfect-calibration diagonal */}
        <line
          x1={toX(0)}
          y1={toY(0)}
          x2={toX(1)}
          y2={toY(1)}
          stroke="var(--muted-foreground)"
          strokeWidth={1}
          strokeDasharray="4 3"
        />

        <polyline
          points={populated
            .map((b) => `${toX((b.lower + b.upper) / 2)},${toY(b.observed_frequency)}`)
            .join(" ")}
          fill="none"
          stroke="var(--primary)"
          strokeWidth={2}
          strokeLinejoin="round"
        />
        {populated.map((b) => (
          <circle
            key={`${b.lower}-${b.upper}`}
            cx={toX((b.lower + b.upper) / 2)}
            cy={toY(b.observed_frequency)}
            r={3}
            fill="var(--primary)"
          />
        ))}

        <line x1={PAD} y1={PAD} x2={PAD} y2={SIZE - PAD} stroke="var(--foreground)" strokeWidth={1} />
        <line
          x1={PAD}
          y1={SIZE - PAD}
          x2={SIZE - PAD}
          y2={SIZE - PAD}
          stroke="var(--foreground)"
          strokeWidth={1}
        />

        <text x={SIZE / 2} y={SIZE - 8} textAnchor="middle" fontSize={10} fill="var(--muted-foreground)">
          Predicted score
        </text>
        <text
          x={12}
          y={SIZE / 2}
          textAnchor="middle"
          fontSize={10}
          fill="var(--muted-foreground)"
          transform={`rotate(-90 12 ${SIZE / 2})`}
        >
          Observed frequency
        </text>
      </svg>
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2 w-2 rounded-full bg-primary" />
          observed (ECE {ece.toFixed(4)})
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2 w-3 border-t border-dashed border-muted-foreground" />
          perfectly calibrated
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2 w-2 bg-muted" />
          bin population
        </span>
      </figcaption>
    </figure>
  );
}
