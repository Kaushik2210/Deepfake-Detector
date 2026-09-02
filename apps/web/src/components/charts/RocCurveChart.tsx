import type { RocPoint } from "@/lib/eval-report";

export interface RocSeries {
  label: string;
  auc: number;
  points: RocPoint[];
  colorVar: "--primary" | "--chart-3" | "--chart-4" | "--chart-5";
}

const SIZE = 320;
const PAD = 38;
const PLOT = SIZE - PAD * 2;

const toX = (fpr: number) => PAD + fpr * PLOT;
const toY = (tpr: number) => PAD + (1 - tpr) * PLOT;

/**
 * ROC curve(s) as a plain inline SVG line plot -- no charting dependency.
 * Accepts multiple series so two streams can be overlaid for direct comparison,
 * which is the figure a paper about stream-vs-stream generalisation wants.
 */
export function RocCurveChart({ series, caption }: { series: RocSeries[]; caption?: string }) {
  const label = caption ?? `ROC curve for ${series.map((s) => s.label).join(", ")}`;

  return (
    <figure className="space-y-2">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={label}
        className="h-auto w-full max-w-sm"
      >
        {/* gridlines */}
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

        {/* chance diagonal */}
        <line
          x1={toX(0)}
          y1={toY(0)}
          x2={toX(1)}
          y2={toY(1)}
          stroke="var(--muted-foreground)"
          strokeWidth={1}
          strokeDasharray="4 3"
        />

        {series.map((s) => (
          <polyline
            key={s.label}
            points={s.points.map((p) => `${toX(p.fpr)},${toY(p.tpr)}`).join(" ")}
            fill="none"
            stroke={`var(${s.colorVar})`}
            strokeWidth={2}
            strokeLinejoin="round"
          />
        ))}

        {/* axes */}
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
          False positive rate
        </text>
        <text
          x={12}
          y={SIZE / 2}
          textAnchor="middle"
          fontSize={10}
          fill="var(--muted-foreground)"
          transform={`rotate(-90 12 ${SIZE / 2})`}
        >
          True positive rate
        </text>
      </svg>
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {series.map((s) => (
          <span key={s.label} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: `var(${s.colorVar})` }}
            />
            {s.label} (AUC {s.auc.toFixed(3)})
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2 w-3 border-t border-dashed border-muted-foreground" />
          chance
        </span>
      </figcaption>
    </figure>
  );
}
