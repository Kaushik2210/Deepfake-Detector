import { fakeBrowser } from "wxt/testing/fake-browser";
import { beforeEach, describe, expect, it } from "vitest";
import { addHistoryEntry, clearHistory, getHistory, MAX_HISTORY_ENTRIES } from "../history";
import type { HistoryEntry } from "../history";

function entry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    requestId: overrides.requestId ?? Math.random().toString(36),
    jobId: "job-1",
    score: 0.5,
    band: "mixed",
    mediaKind: "image",
    pageUrl: "https://example.com/",
    pageTitle: "Example",
    analyzedAt: new Date().toISOString(),
    ttlExpiresAt: new Date(Date.now() + 86_400_000).toISOString(),
    ...overrides,
  };
}

describe("history", () => {
  beforeEach(() => {
    fakeBrowser.reset();
  });

  it("starts empty", async () => {
    expect(await getHistory()).toEqual([]);
  });

  it("records an entry", async () => {
    await addHistoryEntry(entry({ requestId: "r1" }));
    const history = await getHistory();
    expect(history).toHaveLength(1);
    expect(history[0]?.requestId).toBe("r1");
  });

  it("newest entries come first", async () => {
    await addHistoryEntry(entry({ requestId: "r1" }));
    await addHistoryEntry(entry({ requestId: "r2" }));

    const history = await getHistory();
    expect(history.map((h) => h.requestId)).toEqual(["r2", "r1"]);
  });

  it("re-adding the same requestId replaces rather than duplicates it", async () => {
    await addHistoryEntry(entry({ requestId: "r1", score: 0.2 }));
    await addHistoryEntry(entry({ requestId: "r1", score: 0.9 }));

    const history = await getHistory();
    expect(history).toHaveLength(1);
    expect(history[0]?.score).toBe(0.9);
  });

  it("evicts the oldest entry once the cap is exceeded", async () => {
    for (let i = 0; i < MAX_HISTORY_ENTRIES + 5; i++) {
      await addHistoryEntry(entry({ requestId: `r${i}` }));
    }

    const history = await getHistory();
    expect(history).toHaveLength(MAX_HISTORY_ENTRIES);
    // Most recently added should survive; earliest should have been evicted.
    expect(history.map((h) => h.requestId)).toContain(
      `r${MAX_HISTORY_ENTRIES + 4}`,
    );
    expect(history.map((h) => h.requestId)).not.toContain("r0");
  });

  it("clearHistory empties it", async () => {
    await addHistoryEntry(entry());
    await clearHistory();
    expect(await getHistory()).toEqual([]);
  });

  it("never stores raw media, only the report summary fields", async () => {
    await addHistoryEntry(entry({ requestId: "r1" }));
    const [stored] = await getHistory();
    const keys = Object.keys(stored ?? {});
    // Explicit allowlist, so a future field added carelessly (e.g. an
    // artifact URL or raw bytes) fails this test rather than silently
    // starting to persist something it shouldn't.
    expect(keys.sort()).toEqual(
      [
        "requestId",
        "jobId",
        "score",
        "band",
        "mediaKind",
        "pageUrl",
        "pageTitle",
        "analyzedAt",
        "ttlExpiresAt",
      ].sort(),
    );
  });
});
