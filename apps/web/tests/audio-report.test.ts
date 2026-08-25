import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(`../src/${relative}`, import.meta.url)), "utf8");
}

describe("spectrum_plot artifact rendering", () => {
  const reportView = source("components/ReportView.tsx");

  it("the spectrum_plot artifact type is handled, not dropped", () => {
    // Regression guard: the artifact union has included "spectrum_plot" since
    // Phase 3 (Stream B's frequency spectrum), but nothing rendered it until
    // Phase 6 gave audio the same artifact type -- an unrendered artifact type
    // silently violates principle 2 (every score ships visual evidence).
    expect(reportView).toContain('artifact.type === "spectrum_plot"');
  });

  it("renders it as an image, the same shape a heatmap artifact has", () => {
    const start = reportView.indexOf('artifact.type === "spectrum_plot"');
    expect(start).toBeGreaterThan(-1);
    const nextBlock = reportView.slice(start, start + 400);
    expect(nextBlock).toContain("<img");
    expect(nextBlock).toContain("artifact.url");
  });
});

describe("audio-aware wording", () => {
  const reportView = source("components/ReportView.tsx");

  it("derives audio-ness from media_meta.kind, not a guess", () => {
    expect(reportView).toContain('report.media_meta.kind === "audio"');
  });

  it("gives audio its own unit label rather than reusing face/frame", () => {
    expect(reportView).toMatch(/isAudio\s*\?\s*"clip"/);
  });
});

describe("upload form accepts audio", () => {
  const uploadForm = source("components/UploadForm.tsx");
  const route = source("app/api/analyze/route.ts");

  it("accepts common audio containers", () => {
    for (const type of ["audio/wav", "audio/flac", "audio/ogg", "audio/mpeg"]) {
      expect(uploadForm).toContain(type);
      expect(route).toContain(type);
    }
  });

  it("applies a separate byte limit to audio than images", () => {
    expect(route).toContain("MAX_AUDIO_BYTES");
    expect(route).toContain("isAudio");
  });
});

describe("faces stays empty for audio without special-casing the renderer", () => {
  it("FaceFindings already no-ops on an empty array", () => {
    const faceFindings = source("components/FaceFindings.tsx");
    expect(faceFindings).toContain("if (faces.length === 0) return null");
  });

  it("ConclusionPanel is conditionally rendered, so a null conclusion is skipped", () => {
    const reportView = source("components/ReportView.tsx");
    expect(reportView).toMatch(/\{report\.conclusion\s*&&/);
  });
});
