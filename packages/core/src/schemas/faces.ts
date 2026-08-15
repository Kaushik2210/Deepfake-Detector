import { z } from "zod";
import { BandIdSchema } from "./band.js";
import { EnvelopePenaltySchema } from "./envelope.js";

export const FaceBoxSchema = z.object({
  x: z.number().int().nonnegative(),
  y: z.number().int().nonnegative(),
  w: z.number().int().positive(),
  h: z.number().int().positive(),
});

/**
 * One analysed face.
 *
 * Each face carries its own band, uncertainty and envelope penalties rather than
 * inheriting the image's. In a group photo a front-row face may be 200px tall
 * while a back-row face is 30px, and those two results do not deserve equal
 * confidence.
 */
export const FaceFindingSchema = z.object({
  // 1-based, matching the numbering drawn on the face-map artifact.
  index: z.number().int().positive(),
  box: FaceBoxSchema,
  score: z.number().min(0).max(1),
  band: BandIdSchema,
  uncertainty: z.tuple([z.number().min(0).max(1), z.number().min(0).max(1)]),
  detector_confidence: z.number().min(0).max(1),
  penalties: z.array(EnvelopePenaltySchema),
  heatmap_url: z.string().url().optional(),
});

export type FaceBox = z.infer<typeof FaceBoxSchema>;
export type FaceFinding = z.infer<typeof FaceFindingSchema>;

/**
 * How the individual face scores relate to each other. This shapes the
 * conclusion, because the same maximum score means different things depending
 * on whether one face stands out or every face looks alike.
 */
export const FacePatternSchema = z.enum([
  // Nothing elevated anywhere.
  "none_elevated",
  // Exactly one face elevated among several — the face-swap shape, but also the
  // shape random chance produces when many faces are tested at once.
  "single_outlier",
  // Some but not all faces elevated.
  "several_elevated",
  // Every face elevated — more often a property of the whole image than of the
  // individual people in it.
  "all_elevated",
  // Only one face present, so there is no pattern to speak of.
  "single_face",
]);

export type FacePattern = z.infer<typeof FacePatternSchema>;

/**
 * Plain-language summary shown at the top of a report.
 *
 * Principle 1 applies here as much as anywhere: this text must never resolve to
 * a verdict, however much a reader might want one.
 */
export const ConclusionSchema = z.object({
  headline: z.string(),
  detail: z.string(),
  next_steps: z.string(),
  pattern: FacePatternSchema,
  faces_analyzed: z.number().int().nonnegative(),
  faces_elevated: z.number().int().nonnegative(),
});

export type Conclusion = z.infer<typeof ConclusionSchema>;
