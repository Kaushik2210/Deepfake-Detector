import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(`../src/${relative}`, import.meta.url)), "utf8");
}

describe("video-aware wording", () => {
  const reportView = source("components/ReportView.tsx");
  const conclusionPanel = source("components/ConclusionPanel.tsx");
  const faceFindings = source("components/FaceFindings.tsx");

  it("derives video-ness from media_meta.kind, not a guess", () => {
    expect(reportView).toContain('report.media_meta.kind === "video"');
  });

  it("passes the derived unit down to ConclusionPanel and FaceFindings", () => {
    expect(reportView).toMatch(/ConclusionPanel conclusion=\{report\.conclusion\} unit=\{unit\}/);
    expect(reportView).toContain("<FaceFindings faces={faces} unit={unit} />");
  });

  it("ConclusionPanel accepts a face/frame unit and defaults to face", () => {
    expect(conclusionPanel).toContain('unit = "face"');
    expect(conclusionPanel).toMatch(/unit\?:\s*"face"\s*\|\s*"frame"/);
  });

  it("FaceFindings heading and description change for frame unit", () => {
    expect(faceFindings).toContain("Per-{unit} results");
    expect(faceFindings).toMatch(/unit === "frame"/);
  });

  it("shows a timestamp instead of image coordinates when one is present", () => {
    expect(faceFindings).toContain("face.timestamp !== undefined");
  });
});

describe("timeline artifact rendering", () => {
  const reportView = source("components/ReportView.tsx");

  it("the timeline artifact type is handled, not dropped", () => {
    // Regression guard: the artifact union already included "timeline" from
    // Phase 0's schema design, but nothing rendered it until video existed.
    expect(reportView).toContain('artifact.type === "timeline"');
  });

  it("renders it via the dedicated chart component", () => {
    expect(reportView).toContain("TimelineChart");
    expect(reportView).toMatch(/<TimelineChart points=\{artifact\.points\}/);
  });
});

describe("TimelineChart", () => {
  const chart = source("components/TimelineChart.tsx");

  it("renders nothing for an empty series rather than an empty chart shell", () => {
    expect(chart).toContain("if (points.length === 0) return null");
  });

  it("colours points by the shared band logic, not a hardcoded duplicate scale", () => {
    expect(chart).toContain("scoreToBand");
  });

  it("is self-contained SVG, no charting dependency", () => {
    expect(chart).toContain("<svg");
    expect(chart).not.toMatch(/from ["'](recharts|chart\.js|d3)["']/);
  });
});

describe("upload form accepts video", () => {
  const uploadForm = source("components/UploadForm.tsx");
  const route = source("app/api/analyze/route.ts");

  it("accepts common video containers", () => {
    for (const type of ["video/mp4", "video/quicktime", "video/webm", "video/x-matroska"]) {
      expect(uploadForm).toContain(type);
      expect(route).toContain(type);
    }
  });

  it("applies a separate, larger byte limit to video than images", () => {
    expect(route).toContain("MAX_VIDEO_BYTES");
    expect(route).toContain("isVideo");
  });
});
