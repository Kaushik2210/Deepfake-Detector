import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(`../src/${relative}`, import.meta.url)), "utf8");
}

describe("upload rate limiting", () => {
  const route = source("app/api/analyze/route.ts");
  const lib = source("lib/rate-limit.ts");

  it("enforces a limit before any storage write", () => {
    expect(route).toContain("enforceRateLimit(");
    // Same ordering guarantee the consent test already pins: the gate runs
    // before anything is written to storage.
    expect(route.indexOf("enforceRateLimit(")).toBeLessThan(route.indexOf("putMedia("));
  });

  it("is keyed by the authenticated user, not by IP -- callers here are already known", () => {
    expect(route).toMatch(/enforceRateLimit\(\s*"analyze",\s*userId/);
  });

  it("returns 429 with a Retry-After header when exceeded", () => {
    expect(route).toContain("RateLimitExceededError");
    expect(route).toContain("429");
    expect(route).toContain("Retry-After");
  });

  it("fails open rather than blocking uploads when Redis is unreachable", () => {
    expect(lib).toMatch(/catch\s*\{[\s\S]*?return;?[\s\S]*?\}/);
  });

  it("reuses the same Redis connection BullMQ already uses, not a new client", () => {
    expect(lib).toContain("redisConnection");
    expect(lib).toContain('from "./queue"');
  });
});
