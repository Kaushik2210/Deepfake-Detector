import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(`../src/${relative}`, import.meta.url)), "utf8");
}

const page = source("app/accuracy/page.tsx");
const loader = source("lib/eval-report.ts");

describe("accuracy page", () => {
  it("contains no hardcoded accuracy figure", () => {
    // Principle 5. Percentages and bare decimals in JSX would mean a number that
    // does not trace to the eval harness. Class names and Tailwind sizes are
    // stripped before checking.
    const jsxText = page
      .replace(/className="[^"]*"/g, "")
      .replace(/import[^\n]*\n/g, "")
      .replace(/toFixed\(\d\)/g, "");

    expect(jsxText).not.toMatch(/\d{2}(\.\d+)?%\s*(accurate|accuracy|AUC)/i);
    expect(jsxText).not.toMatch(/\b(0\.9\d|9\d(\.\d)?%)\b/);
  });

  it("renders every figure from the loaded report", () => {
    expect(page).toContain("latestEvalReport");
    for (const field of ["auc", "eer", "ece", "fusion_weights"]) {
      expect(page).toContain(field);
    }
  });

  it("states explicitly when no evaluation exists", () => {
    expect(page).toContain("No evaluation has been run yet");
    expect(page).toContain("will not publish a figure");
  });

  it("shows unmeasurable metrics as unmeasurable", () => {
    expect(page).toContain("not measurable");
    expect(page).toMatch(/t\.measurable/);
  });

  it("shows the confidence interval alongside AUC", () => {
    expect(page).toContain("auc_ci95");
    expect(page).toContain("confidence interval");
  });

  it("leads with caveats rather than the headline number", () => {
    expect(page.indexOf("How to read these numbers")).toBeLessThan(
      page.indexOf("Cross-dataset results"),
    );
  });

  it("names the reporting corpus and its licence", () => {
    expect(page).toContain("reportingSet");
    expect(page).toContain("licence");
  });

  it("warns that training-data overlap cannot be ruled out", () => {
    expect(page).toMatch(/overlap/i);
  });
});

describe("eval report loader", () => {
  it("returns null rather than inventing a report", () => {
    expect(loader).toContain("return null");
    expect(loader).not.toMatch(/auc:\s*0\.\d+/);
  });

  it("reads the newest report", () => {
    expect(loader).toContain("sort()");
    expect(loader).toContain("at(-1)");
  });
});
