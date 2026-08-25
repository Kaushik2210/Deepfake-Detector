import { AnalysisReportSchema, type AnalysisReport } from "@veriframe/core";
import { getSettings } from "./settings";

/**
 * Calls the inference service's public REST surface directly, unauthenticated
 * -- not through the web app's Clerk-gated `/api/analyze` route. The
 * extension has to work without the user being signed into a web session,
 * and `POST /v1/analyze` is already the same synchronous, self-contained
 * endpoint the web app's worker calls; there is no queue to bypass. See
 * DECISIONS.md.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function baseUrl(): Promise<string> {
  const settings = await getSettings();
  return settings.inferenceServiceUrl.replace(/\/+$/, "");
}

/** Look up a previously analysed report by perceptual hash. Null on a miss --
 * a 404 is the expected, common outcome here, not an error to throw on. */
export async function lookupByHash(phash: string): Promise<AnalysisReport | null> {
  const response = await fetch(`${await baseUrl()}/v1/analyze/hash`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phash }),
  });

  if (response.status === 404) return null;
  if (!response.ok) {
    throw new ApiError(`hash lookup failed: HTTP ${response.status}`, response.status);
  }

  return AnalysisReportSchema.parse(await response.json());
}

/** Upload media for a real analysis. Only called after explicit per-item
 * consent -- see the content script's consent dialog. */
export async function analyzeMedia(
  blob: Blob,
  filename: string,
  mimeType: string,
): Promise<AnalysisReport> {
  const form = new FormData();
  form.append("file", new File([blob], filename, { type: mimeType }));

  const response = await fetch(`${await baseUrl()}/v1/analyze`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(`analysis failed: HTTP ${response.status} ${detail}`.trim(), response.status);
  }

  return AnalysisReportSchema.parse(await response.json());
}
