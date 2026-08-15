import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(`../src/${relative}`, import.meta.url)), "utf8");
}

describe("per-face results", () => {
  const component = source("components/FaceFindings.tsx");

  it("derives each face's label from core rather than restating it", () => {
    expect(component).toContain("scoreToBand");
    expect(component).not.toContain("Strong indication");
  });

  it("shows each face's own uncertainty range", () => {
    expect(component).toContain("face.uncertainty");
  });

  it("renders each face's own caveats, not the image's", () => {
    expect(component).toContain("face.penalties");
  });

  it("shows a heatmap per face so every score is evidence-backed", () => {
    expect(component).toContain("face.heatmap_url");
  });

  it("orders faces by score so the notable ones surface first", () => {
    expect(component).toMatch(/sort\(\(a, b\) => b\.score - a\.score\)/);
  });

  it("numbers faces to match the face-map artifact", () => {
    expect(component).toContain("face.index");
  });
});

describe("conclusion panel", () => {
  const component = source("components/ConclusionPanel.tsx");

  it("renders all three parts of the conclusion", () => {
    for (const field of ["headline", "detail", "next_steps"]) {
      expect(component).toContain(`conclusion.${field}`);
    }
  });

  it("reports how many faces were analysed and how many were elevated", () => {
    expect(component).toContain("faces_analyzed");
    expect(component).toContain("faces_elevated");
  });

  it("hardcodes no verdict language", () => {
    expect(component).not.toMatch(/\b(FAKE|REAL|fake|authentic|genuine)\b/);
  });
});

describe("report view", () => {
  const component = source("components/ReportView.tsx");

  it("puts the plain-language conclusion above the numeric assessment", () => {
    expect(component.indexOf("ConclusionPanel")).toBeLessThan(
      component.indexOf("ScoreBand"),
    );
  });

  it("explains that the overall score is the maximum across faces", () => {
    expect(component).toContain("highest of the");
  });

  it("renders the face map artifact", () => {
    expect(component).toContain('artifact.type === "face_map"');
  });

  it("tolerates a report with no faces field", () => {
    // Reports created before per-face analysis existed must still render.
    expect(component).toContain("report.faces ?? []");
  });
});
