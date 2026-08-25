import type { BandId } from "@veriframe/core";

/**
 * Recent-analyses history, in `chrome.storage.local`.
 *
 * Deliberately a lightweight summary, not the full `AnalysisReport`: the
 * report's artifact URLs (heatmaps, timelines) point at the inference
 * service's `.artifacts/` directory, which is deleted along with everything
 * else after the same 24h TTL every report already carries -- persisting the
 * full report here would just accumulate dead links. `chrome.storage.local`
 * also has a real quota (unlimitedStorage is deliberately not requested, per
 * the minimal-permissions principle), so history is capped at
 * `MAX_HISTORY_ENTRIES` with oldest-first eviction.
 */

export interface HistoryEntry {
  requestId: string;
  jobId: string;
  score: number;
  band: BandId;
  mediaKind: "image" | "video";
  pageUrl: string;
  pageTitle: string;
  analyzedAt: string; // ISO 8601
  ttlExpiresAt: string; // ISO 8601 -- the popup uses this to say when the
  // server-side evidence backing this entry will be gone, not to hide the
  // history entry itself. The entry (score/band/page) is the user's own
  // record of what they checked, independent of the server's retention.
}

const STORAGE_KEY = "veriframe.history";
export const MAX_HISTORY_ENTRIES = 50;

export async function getHistory(): Promise<HistoryEntry[]> {
  const stored = await browser.storage.local.get(STORAGE_KEY);
  const entries = stored[STORAGE_KEY];
  return Array.isArray(entries) ? (entries as HistoryEntry[]) : [];
}

export async function addHistoryEntry(entry: HistoryEntry): Promise<void> {
  const existing = await getHistory();
  const next = [entry, ...existing.filter((e) => e.requestId !== entry.requestId)].slice(
    0,
    MAX_HISTORY_ENTRIES,
  );
  await browser.storage.local.set({ [STORAGE_KEY]: next });
}

export async function clearHistory(): Promise<void> {
  await browser.storage.local.remove(STORAGE_KEY);
}
