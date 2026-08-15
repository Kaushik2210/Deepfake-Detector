import { z } from "zod";
import { BandIdSchema } from "./band.js";
import { ConclusionSchema, FaceFindingSchema } from "./faces.js";
import { EnvelopeSchema } from "./envelope.js";

export const MediaKindSchema = z.enum(["image", "video", "audio"]);

export const StreamNameSchema = z.enum([
  "spatial", // Stream A: CNN/ViT ensemble
  "frequency", // Stream B: frequency/signal forensics
  "temporal", // Stream C: temporal & biological (video)
  "provenance", // Stream D: provenance & metadata
  "audio", // audio anti-spoofing pipeline
]);

export const ArtifactSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("heatmap"),
    label: z.string(),
    url: z.string().url(),
  }),
  z.object({
    // The source image with numbered boxes drawn on each analysed face, so a
    // reader can map a finding back to a person. Survives media deletion,
    // because it is a derived artifact rather than the original upload.
    type: z.literal("face_map"),
    label: z.string(),
    url: z.string().url(),
  }),
  z.object({
    type: z.literal("timeline"),
    label: z.string(),
    // per-frame or per-window scores, timestamp in seconds
    points: z.array(z.object({ t: z.number().nonnegative(), score: z.number().min(0).max(1) })),
  }),
  z.object({
    type: z.literal("spectrum_plot"),
    label: z.string(),
    url: z.string().url(),
  }),
  z.object({
    type: z.literal("note"),
    label: z.string(),
    detail: z.string(),
  }),
]);

export type Artifact = z.infer<typeof ArtifactSchema>;

export const StreamResultSchema = z.object({
  name: StreamNameSchema,
  score: z.number().min(0).max(1),
  weight: z.number().min(0).max(1),
  models: z.array(z.string()).describe("model identifiers/versions that contributed to this stream"),
  artifacts: z.array(ArtifactSchema),
});

export type StreamResult = z.infer<typeof StreamResultSchema>;

export { EnvelopePenaltySchema, EnvelopeSchema } from "./envelope.js";
export type { EnvelopePenalty, Envelope } from "./envelope.js";

export const ProvenanceSchema = z.object({
  c2pa: z
    .object({
      present: z.boolean(),
      valid: z.boolean().optional(),
      signer: z.string().optional(),
      trusted_signer: z.boolean().optional(),
    })
    .optional(),
  exif_consistent: z.boolean().optional(),
  known_generator_watermark: z.string().optional(),
  phash: z.string().optional(),
});

export type Provenance = z.infer<typeof ProvenanceSchema>;

export const MediaMetaSchema = z.object({
  kind: MediaKindSchema,
  filename: z.string().optional(),
  mime_type: z.string(),
  size_bytes: z.number().nonnegative(),
  duration_seconds: z.number().nonnegative().optional(),
  width: z.number().int().positive().optional(),
  height: z.number().int().positive().optional(),
});

export type MediaMeta = z.infer<typeof MediaMetaSchema>;

export const ModelVersionsSchema = z.record(z.string(), z.string());

export const AnalysisReportSchema = z.object({
  job_id: z.string(),
  score: z.number().min(0).max(1),
  band: BandIdSchema,
  uncertainty: z.tuple([z.number().min(0).max(1), z.number().min(0).max(1)]),
  streams: z.array(StreamResultSchema),

  // Per-face results. Empty when no face was found, or for media where faces
  // are not the unit of analysis.
  faces: z.array(FaceFindingSchema).default([]),

  // Plain-language summary. Optional so a report produced before this field
  // existed still parses.
  conclusion: ConclusionSchema.optional(),

  envelope: EnvelopeSchema,
  provenance: ProvenanceSchema,
  media_meta: MediaMetaSchema,
  model_versions: ModelVersionsSchema,
  processed_at: z.string().datetime(),
  ttl_expires_at: z.string().datetime(),
  disclaimer: z.string(),
});

export type AnalysisReport = z.infer<typeof AnalysisReportSchema>;
