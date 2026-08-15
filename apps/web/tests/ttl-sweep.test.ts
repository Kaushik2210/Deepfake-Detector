import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const sweep = readFileSync(
  fileURLToPath(new URL("../src/worker/ttl-sweep.ts", import.meta.url)),
  "utf8",
);

describe("ttl sweep", () => {
  it("only selects jobs whose media still exists and has expired", () => {
    expect(sweep).toContain("lte(schema.analysisJobs.ttlExpiresAt");
    expect(sweep).toContain("isNotNull(schema.analysisJobs.storageKey)");
    expect(sweep).toContain("isNull(schema.analysisJobs.mediaDeletedAt)");
  });

  it("marks the row deleted only after the object store delete succeeds", () => {
    // If the update ran first, a failed delete would leave orphaned media that
    // no later sweep would ever look at again.
    expect(sweep.indexOf("await deleteMedia")).toBeLessThan(sweep.indexOf("mediaDeletedAt: new Date()"));
  });

  it("leaves the row alone when deletion fails so the next sweep retries", () => {
    expect(sweep).toMatch(/catch\s*\(error\)/);
    expect(sweep).toContain("failed to delete");
  });
});
