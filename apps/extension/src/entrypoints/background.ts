import { lookupByHash, analyzeMedia } from "../lib/api-client";
import { addHistoryEntry } from "../lib/history";
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  CaptureVideoFrameResponse,
  CheckCacheRequest,
  CheckCacheResponse,
} from "../lib/messages";

const OFFSCREEN_PATH = "offscreen.html";

// Video blobs captured for a CHECK_CACHE, kept in memory only long enough for
// the matching ANALYZE to arrive (or never, if the user declines consent).
// Never persisted -- this is working memory for one in-flight request, not a
// cache in the privacy-relevant sense; the actual cache is the server-side
// phash_cache table from stage 1.
const pendingVideoBlobs = new Map<string, string>(); // requestId -> data URL

let creatingOffscreen: Promise<void> | null = null;

async function ensureOffscreenDocument(): Promise<void> {
  const existing = await browser.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT" as chrome.runtime.ContextType],
    documentUrls: [browser.runtime.getURL(`/${OFFSCREEN_PATH}`)],
  });
  if (existing.length > 0) return;

  if (creatingOffscreen) {
    await creatingOffscreen;
    return;
  }

  creatingOffscreen = chrome.offscreen
    .createDocument({
      url: OFFSCREEN_PATH,
      reasons: [chrome.offscreen.Reason.BLOBS],
      justification:
        "Load a <video> element to seek to the frame the user saw and capture it via canvas, producing a perceptual hash and an upload Blob. The background service worker has no DOM and cannot do this itself.",
    })
    .then(() => undefined);

  try {
    await creatingOffscreen;
  } finally {
    creatingOffscreen = null;
  }
}

async function captureVideoFrame(
  requestId: string,
  src: string,
  currentTime: number,
): Promise<{ hash: string } | { error: string }> {
  await ensureOffscreenDocument();

  const response = (await browser.runtime.sendMessage({
    type: "CAPTURE_VIDEO_FRAME",
    requestId,
    src,
    currentTime,
  })) as CaptureVideoFrameResponse;

  if (response.type === "FRAME_CAPTURE_FAILED") {
    const fallback = "The video frame could not be captured.";
    if (response.reason === "cors_tainted") {
      return {
        error:
          "This video is served without permission for scripts to read its pixels (no CORS headers), which is a browser security restriction VeriFrame cannot work around.",
      };
    }
    if (response.reason === "load_failed") {
      return { error: "The video could not be loaded for analysis." };
    }
    return { error: fallback };
  }

  pendingVideoBlobs.set(requestId, response.blobDataUrl);
  return { hash: response.hash };
}

function dataUrlToBlob(dataUrl: string): Blob {
  const commaIndex = dataUrl.indexOf(",");
  if (commaIndex === -1) {
    throw new Error("malformed data URL");
  }
  const header = dataUrl.slice(0, commaIndex);
  const base64 = dataUrl.slice(commaIndex + 1);

  const mimeMatch = header.match(/data:([^;]+);base64/);
  const mimeType = mimeMatch?.[1] ?? "application/octet-stream";
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mimeType });
}

async function handleCheckCache(request: CheckCacheRequest): Promise<CheckCacheResponse> {
  let phash = request.phash ?? null;

  if (!phash && request.media.kind === "video") {
    const result = await captureVideoFrame(
      request.requestId,
      request.media.src,
      request.media.currentTime ?? 0,
    );
    if ("error" in result) {
      return { type: "CHECK_FAILED", requestId: request.requestId, reason: result.error };
    }
    phash = result.hash;
  }

  if (!phash) {
    return {
      type: "CHECK_FAILED",
      requestId: request.requestId,
      reason: "no hash available for this media",
    };
  }

  try {
    const cached = await lookupByHash(phash);
    if (cached) {
      return { type: "CACHE_HIT", requestId: request.requestId, report: cached };
    }
    return { type: "CACHE_MISS", requestId: request.requestId, phash };
  } catch {
    // A cache we can't reach degrades to "treat it as a miss": the caller's
    // job either way is to fall back to asking for consent and uploading.
    return { type: "CACHE_MISS", requestId: request.requestId, phash };
  }
}

async function handleAnalyze(request: AnalyzeRequest): Promise<AnalyzeResponse> {
  try {
    let blobDataUrl: string | undefined;
    let mimeType: string;
    let filename: string;

    if (request.upload) {
      ({ blobDataUrl, mimeType, filename } = request.upload);
    } else {
      blobDataUrl = pendingVideoBlobs.get(request.requestId);
      mimeType = "image/jpeg";
      filename = "frame.jpg";
    }

    if (!blobDataUrl) {
      return {
        type: "ANALYZE_FAILED",
        requestId: request.requestId,
        reason: "no captured media available for this request",
      };
    }

    const blob = dataUrlToBlob(blobDataUrl);
    const report = await analyzeMedia(blob, filename, mimeType);

    await addHistoryEntry({
      requestId: request.requestId,
      jobId: report.job_id,
      score: report.score,
      band: report.band,
      mediaKind: request.media.kind,
      pageUrl: request.media.pageUrl,
      pageTitle: request.media.pageTitle,
      analyzedAt: report.processed_at,
      ttlExpiresAt: report.ttl_expires_at,
    });

    return { type: "ANALYZE_COMPLETE", requestId: request.requestId, report };
  } catch (error) {
    return {
      type: "ANALYZE_FAILED",
      requestId: request.requestId,
      reason: error instanceof Error ? error.message : "analysis failed",
    };
  } finally {
    pendingVideoBlobs.delete(request.requestId);
  }
}

const CONTEXT_MENU_ID = "veriframe-analyze";

export default defineBackground(() => {
  browser.runtime.onInstalled.addListener(() => {
    browser.contextMenus.create({
      id: CONTEXT_MENU_ID,
      title: "Analyse with VeriFrame",
      contexts: ["image", "video"],
    });
  });

  browser.contextMenus.onClicked.addListener((info, tab) => {
    if (info.menuItemId !== CONTEXT_MENU_ID || !tab?.id) return;
    // The content script owns badge/consent/capture logic; the context menu
    // just tells it "the user picked this specific element from the menu."
    browser.tabs.sendMessage(tab.id, {
      type: "CONTEXT_MENU_ANALYZE",
      srcUrl: info.srcUrl,
      mediaType: info.mediaType,
    });
  });

  browser.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
    if (!isBackgroundMessage(message)) return undefined;

    (async () => {
      if (message.type === "CHECK_CACHE") {
        sendResponse(await handleCheckCache(message));
      } else if (message.type === "ANALYZE") {
        sendResponse(await handleAnalyze(message));
      }
    })();

    return true; // keep the message channel open for the async response
  });
});

function isBackgroundMessage(
  message: unknown,
): message is CheckCacheRequest | AnalyzeRequest {
  const type = (message as { type?: unknown } | null)?.type;
  return type === "CHECK_CACHE" || type === "ANALYZE";
}
