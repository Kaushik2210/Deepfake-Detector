import { BAND_DEFINITIONS, REPORT_FOOTER_DISCLAIMER, scoreToBand } from "@veriframe/core";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(`../src/${relative}`, import.meta.url)), "utf8");
}

describe("report presentation", () => {
  it("renders the disclaimer from core rather than a copied string", () => {
    // Principle 6: if this were hardcoded, editing bands.json would silently
    // leave a stale disclaimer on screen.
    const view = source("components/ReportView.tsx");
    expect(view).toContain("REPORT_FOOTER_DISCLAIMER");
    expect(view).not.toContain("not admissible as forensic evidence");
  });

  it("derives band labels from core rather than restating them", () => {
    const band = source("components/ScoreBand.tsx");
    expect(band).toContain("scoreToBand");

    for (const definition of BAND_DEFINITIONS) {
      expect(band).not.toContain(definition.label);
    }
  });

  it("covers every band id with a colour", () => {
    const band = source("components/ScoreBand.tsx");
    for (const definition of BAND_DEFINITIONS) {
      expect(band).toContain(definition.id);
    }
  });

  it("shows an uncertainty range, not only a point estimate", () => {
    const band = source("components/ScoreBand.tsx");
    expect(band).toContain("uncertainty");
    expect(band).toMatch(/lo|hi/);
  });
});

describe("no binary verdict reaches the UI", () => {
  const uiFiles = [
    "components/ReportView.tsx",
    "components/ScoreBand.tsx",
    "app/page.tsx",
  ];

  it("never labels a result FAKE or REAL", () => {
    for (const file of uiFiles) {
      const text = source(file);
      expect(text).not.toMatch(/\b(FAKE|REAL|AUTHENTIC|GENUINE)\b/);
    }
  });

  it("every band a score can produce is a hedged label", () => {
    for (const score of [0, 0.1, 0.3, 0.5, 0.75, 0.9, 1]) {
      const band = scoreToBand(score);
      expect(band.label.toLowerCase()).not.toMatch(/\bfake\b|\breal\b/);
      expect(REPORT_FOOTER_DISCLAIMER).toContain("not proof");
    }
  });
});

describe("consent gate", () => {
  it("disables submission until consent is given", () => {
    const form = source("components/UploadForm.tsx");
    expect(form).toContain("consented");
    expect(form).toMatch(/disabled=\{[^}]*!consented/);
  });

  it("requires consent server-side, not only in the browser", () => {
    const route = source("app/api/analyze/route.ts");
    expect(route).toContain('form.get("consent")');
    // The check must precede any storage write. Matches the call site, not the import.
    expect(route.indexOf('form.get("consent")')).toBeLessThan(route.indexOf("putMedia("));
  });
});

describe("retention", () => {
  it("sets a TTL on every uploaded job", () => {
    const route = source("app/api/analyze/route.ts");
    expect(route).toContain("ttlExpiresAt");
    expect(route).toContain("MEDIA_TTL_HOURS");
  });

  it("exposes a deletion endpoint", () => {
    const route = source("app/api/analyze/[jobId]/route.ts");
    expect(route).toContain("export async function DELETE");
    expect(route).toContain("deleteMedia");
  });

  it("scopes job lookups to the owning user", () => {
    const route = source("app/api/analyze/[jobId]/route.ts");
    expect(route).toContain("analysisJobs.userId");
  });
});
