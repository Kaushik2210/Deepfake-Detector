import { z } from "zod";
import { BAND_IDS } from "../bands.js";

export const BandIdSchema = z.enum(BAND_IDS);

export const BandSchema = z.object({
  id: BandIdSchema,
  label: z.string(),
  copy: z.string(),
});

export type Band = z.infer<typeof BandSchema>;
