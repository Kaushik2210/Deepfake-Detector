/**
 * Single source of truth for score -> band mapping.
 * Non-negotiable: never collapse this to a binary FAKE/REAL verdict anywhere
 * that consumes this table (web, extension, API responses).
 */
export const BAND_DEFINITIONS = [
  {
    id: "low",
    min: 0.0,
    max: 0.2,
    label: "Low indication",
    copy: "No manipulation signals detected",
  },
  {
    id: "weak",
    min: 0.2,
    max: 0.45,
    label: "Weak indication",
    copy: "Some anomalies, likely benign",
  },
  {
    id: "mixed",
    min: 0.45,
    max: 0.7,
    label: "Mixed signals",
    copy: "Inconclusive — manual review advised",
  },
  {
    id: "strong",
    min: 0.7,
    max: 0.88,
    label: "Strong indication",
    copy: "Multiple manipulation signals",
  },
  {
    id: "very_strong",
    min: 0.88,
    max: 1.0,
    label: "Very strong indication",
    copy: "Consistent manipulation signals across detectors",
  },
] as const;

export type BandId = (typeof BAND_DEFINITIONS)[number]["id"];

export const BAND_IDS = BAND_DEFINITIONS.map((b) => b.id) as [BandId, ...BandId[]];

/**
 * Maps a calibrated score in [0, 1] to its band definition.
 * Upper bound of the last band is inclusive; every other upper bound is exclusive,
 * so a score sitting exactly on a boundary (e.g. 0.45) falls into the higher band.
 */
export function scoreToBand(score: number): (typeof BAND_DEFINITIONS)[number] {
  if (score < 0 || score > 1 || Number.isNaN(score)) {
    throw new RangeError(`score must be a finite number in [0, 1], got ${score}`);
  }

  const band = BAND_DEFINITIONS.find((b, i) => {
    const isLast = i === BAND_DEFINITIONS.length - 1;
    return score >= b.min && (isLast ? score <= b.max : score < b.max);
  });

  if (!band) {
    throw new RangeError(`no band matched score ${score}`);
  }

  return band;
}

export const REPORT_FOOTER_DISCLAIMER =
  "This result is a signal for human review, not proof, and is not admissible as forensic evidence on its own.";
