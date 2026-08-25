import { z } from "zod";

/**
 * Lives in its own module because both the image-level envelope and the
 * per-face findings need it, and having either import the other would make the
 * schema modules circular.
 */
export const EnvelopePenaltySchema = z.object({
  reason: z.string(),
  factor: z
    .number()
    .min(0)
    .max(1)
    .describe("multiplicative confidence penalty applied for this reason"),
});

export const EnvelopeSchema = z.object({
  in_distribution: z.boolean(),
  penalties: z.array(EnvelopePenaltySchema),
  factors_checked: z.object({
    resolution: z.string().optional(),
    compression_estimate: z.string().optional(),
    face_size: z.string().optional(),
    blur: z.string().optional(),
    illumination: z.string().optional(),
    // Audio envelope factors.
    duration: z.string().optional(),
    sample_rate: z.string().optional(),
    clipping: z.string().optional(),
    silence_ratio: z.string().optional(),
  }),
});

export type EnvelopePenalty = z.infer<typeof EnvelopePenaltySchema>;
export type Envelope = z.infer<typeof EnvelopeSchema>;
