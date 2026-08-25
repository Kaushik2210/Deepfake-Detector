import { dctPerceptualHash, grayscaleGridFromCanvas } from "@veriframe/core";

/**
 * Draws an already-loaded `<img>` or `<video>` element to a real `<canvas>`
 * and produces both the perceptual hash and an upload-ready Blob from it.
 *
 * Used from two different DOM contexts -- the content script (for images,
 * captured directly from the live element the page already rendered, no
 * extra network request) and the offscreen document (for video, see
 * capture-video.ts for why that one goes through a fresh element instead).
 * Both have a real `document`, so both can use this the same way; only the
 * background service worker cannot, which is exactly why it delegates video
 * capture to the offscreen document rather than doing this itself.
 *
 * Failure mode worth naming: an element loaded without permissive CORS
 * headers taints the canvas, and `toBlob`/`getImageData` then throw a
 * SecurityError. That's a real, unfixable browser security boundary -- no
 * amount of extension permission changes that -- so it's surfaced as its own
 * CaptureError reason rather than swallowed or reported as a generic failure.
 */

export class CaptureError extends Error {
  constructor(public reason: "cors_tainted" | "load_failed" | "unknown") {
    super(`media capture failed: ${reason}`);
  }
}

const HASH_SIZE = 32;
// Long edge capped for upload -- Stream A's classifier and the DCT-based
// forensics streams both work from a modest resolution; there is no benefit
// to uploading a multi-megapixel source, only cost.
const MAX_UPLOAD_EDGE = 1600;

function naturalSize(
  el: HTMLImageElement | HTMLVideoElement,
): { width: number; height: number } {
  if (el instanceof HTMLVideoElement) {
    return { width: el.videoWidth, height: el.videoHeight };
  }
  return { width: el.naturalWidth, height: el.naturalHeight };
}

export interface CaptureResult {
  hash: string;
  blob: Blob;
  width: number;
  height: number;
}

export async function captureElement(
  el: HTMLImageElement | HTMLVideoElement,
  mimeType: "image/jpeg" | "image/png" = "image/jpeg",
): Promise<CaptureResult> {
  const { width, height } = naturalSize(el);
  if (!width || !height) {
    throw new CaptureError("load_failed");
  }

  const scale = Math.min(1, MAX_UPLOAD_EDGE / Math.max(width, height));
  const uploadW = Math.max(1, Math.round(width * scale));
  const uploadH = Math.max(1, Math.round(height * scale));

  const uploadCanvas = document.createElement("canvas");
  uploadCanvas.width = uploadW;
  uploadCanvas.height = uploadH;
  const uploadCtx = uploadCanvas.getContext("2d");
  if (!uploadCtx) throw new CaptureError("unknown");

  const hashCanvas = document.createElement("canvas");
  hashCanvas.width = HASH_SIZE;
  hashCanvas.height = HASH_SIZE;
  const hashCtx = hashCanvas.getContext("2d");
  if (!hashCtx) throw new CaptureError("unknown");

  try {
    uploadCtx.drawImage(el, 0, 0, uploadW, uploadH);
    const grid = grayscaleGridFromCanvas(hashCtx, el, HASH_SIZE);
    const hash = dctPerceptualHash(grid, HASH_SIZE);

    const blob = await new Promise<Blob | null>((resolve) => {
      uploadCanvas.toBlob(resolve, mimeType, 0.9);
    });
    if (!blob) throw new CaptureError("unknown");

    return { hash, blob, width, height };
  } catch (error) {
    if (error instanceof CaptureError) throw error;
    if (error instanceof DOMException && error.name === "SecurityError") {
      throw new CaptureError("cors_tainted");
    }
    throw new CaptureError("unknown");
  }
}
