import type { AnalysisReport } from "@veriframe/core";

/**
 * Typed message contract between the content script, the background service
 * worker, the offscreen document, and the popup.
 *
 * All network calls to the inference service happen in the background, never
 * in the content script directly: a content script's own `fetch()` can be
 * blocked by the *hosting page's* Content-Security-Policy `connect-src`
 * directive, which the background service worker -- not injected into any
 * page -- is not subject to.
 *
 * Images and video reach the background differently, and the message shapes
 * below reflect that rather than pretending they're symmetric:
 *
 * - **Images**: the content script has direct DOM access to the already-
 *   rendered `<img>`, so it captures the hash (and, on a cache miss, the
 *   upload blob) itself, cheaply, with no extra round trip.
 * - **Video**: the background has no DOM at all and cannot capture a frame
 *   itself, so `CHECK_CACHE` for a video carries only a `MediaRef`, and the
 *   background delegates the actual capture to the offscreen document (see
 *   `CaptureVideoFrameRequest`). The resulting blob is kept in the
 *   background's own memory, keyed by `requestId`, so a later `ANALYZE` for
 *   the same request doesn't re-trigger a second video fetch.
 */

export interface MediaRef {
  kind: "image" | "video";
  src: string;
  pageUrl: string;
  pageTitle: string;
  /** Video only: the element's currentTime, so the offscreen document seeks
   * to the same frame the user actually saw, not frame zero. */
  currentTime?: number;
}

/** Content script -> background. Sent immediately on badge click -- this is
 * only a local hash + cache check, not an upload, so it needs no consent.
 * `phash` is set for images (already computed by the content script) and
 * left undefined for video (the background must capture it first). */
export interface CheckCacheRequest {
  type: "CHECK_CACHE";
  requestId: string;
  media: MediaRef;
  phash?: string;
}

export type CheckCacheResponse =
  | { type: "CACHE_HIT"; requestId: string; report: AnalysisReport }
  | { type: "CACHE_MISS"; requestId: string; phash: string | null }
  | { type: "CHECK_FAILED"; requestId: string; reason: string };

/** Content script -> background, sent only after the user has explicitly
 * confirmed the consent dialog for this specific item. For an image, the
 * content script attaches the blob it already captured (as a data URL,
 * since Blob objects don't survive chrome.runtime message passing); for
 * video, it attaches nothing and the background reuses what it cached from
 * the CHECK_CACHE step. */
export interface AnalyzeRequest {
  type: "ANALYZE";
  requestId: string;
  media: MediaRef;
  upload?: { blobDataUrl: string; mimeType: string; filename: string };
}

export type AnalyzeResponse =
  | { type: "ANALYZE_COMPLETE"; requestId: string; report: AnalysisReport }
  | { type: "ANALYZE_FAILED"; requestId: string; reason: string };

/** Background -> offscreen document. */
export interface CaptureVideoFrameRequest {
  type: "CAPTURE_VIDEO_FRAME";
  requestId: string;
  src: string;
  currentTime: number;
}

export type CaptureVideoFrameResponse =
  | { type: "FRAME_CAPTURED"; requestId: string; hash: string; blobDataUrl: string }
  | {
      type: "FRAME_CAPTURE_FAILED";
      requestId: string;
      // Distinguished because a CORS-tainted canvas is a real, common,
      // unfixable browser restriction, not a bug -- the badge/overlay should
      // say so plainly rather than show a generic "something went wrong".
      reason: "cors_tainted" | "load_failed" | "unknown";
    };

export type ExtensionMessage =
  | CheckCacheRequest
  | AnalyzeRequest
  | CaptureVideoFrameRequest;
