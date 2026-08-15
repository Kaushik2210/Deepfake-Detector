import bandsData from "./bands.json";

/**
 * Band definitions are loaded from bands.json, which is the canonical table shared
 * with the Python inference service (services/inference/app/bands.py reads the same
 * file). Never redeclare these thresholds — change bands.json instead.
 *
 * Non-negotiable: never collapse this to a binary FAKE/REAL verdict anywhere
 * that consumes this table (web, extension, API responses).
 */
export interface BandDefinition {
  readonly id: string;
  readonly min: number;
  readonly max: number;
  readonly label: string;
  readonly copy: string;
}

export const BAND_DEFINITIONS: readonly BandDefinition[] = bandsData.bands;

export type BandId = "low" | "weak" | "mixed" | "strong" | "very_strong";

export const BAND_IDS = BAND_DEFINITIONS.map((b) => b.id) as [BandId, ...BandId[]];

/**
 * Maps a calibrated score in [0, 1] to its band definition.
 * Upper bound of the last band is inclusive; every other upper bound is exclusive,
 * so a score sitting exactly on a boundary (e.g. 0.45) falls into the higher band.
 */
export function scoreToBand(score: number): BandDefinition {
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

export const REPORT_FOOTER_DISCLAIMER: string = bandsData.report_footer_disclaimer;
