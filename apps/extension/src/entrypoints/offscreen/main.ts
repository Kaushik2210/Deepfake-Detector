import { captureElement, CaptureError } from "../../lib/capture";
import type { CaptureVideoFrameRequest, CaptureVideoFrameResponse } from "../../lib/messages";

/**
 * Loads a *fresh* `<video>` element for the requested source rather than
 * reusing the page's own element (which the background cannot see at all --
 * it has no DOM, and this document runs in its own isolated
 * chrome-extension:// page, not the site's). Two consequences worth knowing:
 *
 * - It re-requests the video resource, so this costs bandwidth the content
 *   script capturing the already-loaded element directly (as images do)
 *   would not. Kept this way because it matches the architecture spec's
 *   instruction and keeps heavy video/canvas processing out of the content
 *   script's page-injected footprint. A future optimisation could transfer
 *   an ImageBitmap captured in the content script instead -- noted in
 *   DECISIONS.md rather than built now.
 * - It is subject to exactly the same CORS-tainted-canvas restriction as
 *   image capture is. Loading fresh does not and cannot bypass that; it is a
 *   browser security boundary, not an implementation detail.
 */
async function captureFrame(src: string, currentTime: number) {
  const video = document.createElement("video");
  video.muted = true;
  video.crossOrigin = "anonymous";
  video.src = src;
  video.preload = "auto";

  await new Promise<void>((resolve, reject) => {
    video.addEventListener("loadedmetadata", () => resolve(), { once: true });
    video.addEventListener("error", () => reject(new CaptureError("load_failed")), {
      once: true,
    });
  });

  const seekTarget = Math.min(currentTime, Math.max(0, video.duration - 0.1));
  await new Promise<void>((resolve, reject) => {
    video.addEventListener("seeked", () => resolve(), { once: true });
    video.addEventListener("error", () => reject(new CaptureError("load_failed")), {
      once: true,
    });
    video.currentTime = seekTarget;
  });

  return captureElement(video, "image/jpeg");
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

browser.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
  if (!isCaptureRequest(message)) return undefined;

  (async () => {
    try {
      const { hash, blob } = await captureFrame(message.src, message.currentTime);
      const blobDataUrl = await blobToDataUrl(blob);
      const response: CaptureVideoFrameResponse = {
        type: "FRAME_CAPTURED",
        requestId: message.requestId,
        hash,
        blobDataUrl,
      };
      sendResponse(response);
    } catch (error) {
      const reason = error instanceof CaptureError ? error.reason : "unknown";
      const response: CaptureVideoFrameResponse = {
        type: "FRAME_CAPTURE_FAILED",
        requestId: message.requestId,
        reason,
      };
      sendResponse(response);
    }
  })();

  return true; // keep the message channel open for the async response
});

function isCaptureRequest(message: unknown): message is CaptureVideoFrameRequest {
  return (
    typeof message === "object" &&
    message !== null &&
    (message as { type?: unknown }).type === "CAPTURE_VIDEO_FRAME"
  );
}
