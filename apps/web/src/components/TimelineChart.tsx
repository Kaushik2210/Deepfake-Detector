import { scoreToBand } from "@veriframe/core";

const BAND_DOT: Record<string, string> = {
  low: "#3d8015",
  weak: "#0da365",
  mixed: "#048aca",
  strong: "#1665ea",
  very_strong: "#1c1cb9",
};

/**
 * A plain inline-SVG line chart of score over time, for a video's per-frame
 * timeline. No charting library: this is one small, self-contained chart, and
 * pulling in a dependency for it would cost more than it saves.
 */
export function TimelineChart({
  points,
}: {
  points: { t: number; score: number }[];
}) {
  if (points.length === 0) return null;

  const width = 640;
  const height = 160;
  const pad = { top: 12, right: 16, bottom: 24, left: 32 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const sorted = [...points].sort((a, b) => a.t - b.t);
  const maxT = Math.max(...sorted.map((p) => p.t), 0.001);

  const x = (t: number) => pad.left + (t / maxT) * plotW;
  const y = (score: number) => pad.top + (1 - score) * plotH;

  const linePath = sorted
    .map((p, i) => `${i === 0 ? "M" : "L"} ${x(p.t).toFixed(1)} ${y(p.score).toFixed(1)}`)
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      role="img"
      aria-label="Score across sampled frames, plotted over time"
    >
      {/* Band guide lines at 0.2 / 0.45 / 0.7 / 0.88, matching the assessment bar */}
      {[0.2, 0.45, 0.7, 0.88].map((threshold) => (
        <line
          key={threshold}
          x1={pad.left}
          x2={width - pad.right}
          y1={y(threshold)}
          y2={y(threshold)}
          stroke="#e2e8f0"
          strokeWidth={1}
        />
      ))}

      <line
        x1={pad.left}
        x2={width - pad.right}
        y1={pad.top}
        y2={pad.top}
        stroke="#cbd5e1"
      />
      <line
        x1={pad.left}
        x2={pad.left}
        y1={pad.top}
        y2={height - pad.bottom}
        stroke="#cbd5e1"
      />
      <line
        x1={pad.left}
        x2={width - pad.right}
        y1={height - pad.bottom}
        y2={height - pad.bottom}
        stroke="#cbd5e1"
      />

      <path d={linePath} fill="none" stroke="#94a3b8" strokeWidth={1.5} />

      {sorted.map((p, i) => (
        <circle
          key={i}
          cx={x(p.t)}
          cy={y(p.score)}
          r={3.5}
          fill={BAND_DOT[scoreToBand(p.score).id] ?? "#64748b"}
        >
          <title>
            t={p.t.toFixed(2)}s, score={p.score.toFixed(3)}
          </title>
        </circle>
      ))}

      <text x={pad.left} y={height - 6} fontSize={10} fill="#64748b">
        0s
      </text>
      <text x={width - pad.right} y={height - 6} fontSize={10} fill="#64748b" textAnchor="end">
        {maxT.toFixed(1)}s
      </text>
      <text x={pad.left - 4} y={pad.top + 4} fontSize={10} fill="#64748b" textAnchor="end">
        1.0
      </text>
      <text x={pad.left - 4} y={height - pad.bottom} fontSize={10} fill="#64748b" textAnchor="end">
        0.0
      </text>
    </svg>
  );
}
