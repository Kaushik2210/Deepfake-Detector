import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { AnalysisModal, type ModalState } from "../components/AnalysisModal";
import { Badge } from "../components/Badge";
import { CaptureError, captureElement } from "../lib/capture";
import { isEnabledForHostname, getSettings } from "../lib/settings";
import { newRequestId } from "../lib/request-id";
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  CheckCacheRequest,
  CheckCacheResponse,
  MediaRef,
} from "../lib/messages";

export default defineContentScript({
  matches: ["<all_urls>"],
  // Registered for every page (that's what "matches" means to the manifest),
  // but does nothing at all beyond this early-exit check unless the badge is
  // actually clicked -- no scanning result, hash, or network call happens on
  // page load. See settings.ts: this is a denylist the user can add to per
  // site, not a permission the manifest grants per site.
  async main(ctx) {
    if (!(await isEnabledForHostname(location.hostname))) return;

    const settings = await getSettings();
    const trackedElements = new WeakSet<Element>();
    let busyRequestId: string | null = null;
    // Set when an image is captured directly (see onBadgeClick), read back
    // in handleConsentConfirmed if the user proceeds past the consent dialog.
    // Not part of ModalState: the modal itself never needs to know about it,
    // it is purely internal hand-off between this flow's two steps.
    let pendingImageUpload:
      | { blobDataUrl: string; mimeType: string; filename: string }
      | undefined;

    // --- Shared modal (consent / loading / result / error), one instance
    // reused for whichever media item is currently being interacted with. ---
    let modalRoot: Root | null = null;
    let modalState: ModalState | null = null;

    const modalUi = await createShadowRootUi(ctx, {
      name: "veriframe-modal",
      position: "overlay",
      anchor: "body",
      onMount(container) {
        modalRoot = createRoot(container);
        return modalRoot;
      },
      onRemove(root) {
        root?.unmount();
      },
    });

    function renderModal() {
      if (!modalState) {
        modalUi.remove();
        return;
      }
      modalUi.mount();
      modalRoot?.render(
        createElement(AnalysisModal, {
          state: modalState,
          ttlHours: 24,
          webAppUrl: settings.inferenceServiceUrl.includes("localhost")
            ? "http://localhost:3000"
            : settings.inferenceServiceUrl,
          onConfirmConsent: () => {
            if (modalState?.kind === "consent") void handleConsentConfirmed(modalState.media);
          },
          onClose: () => {
            modalState = null;
            busyRequestId = null;
            renderModal();
          },
        }),
      );
    }

    // --- Per-element badge ---

    async function attachBadge(el: HTMLImageElement | HTMLVideoElement) {
      if (trackedElements.has(el)) return;
      trackedElements.add(el);

      const badgeUi = await createShadowRootUi(ctx, {
        name: "veriframe-badge",
        position: "overlay",
        anchor: el,
        onMount(container) {
          const root = createRoot(container);
          const render = (busy: boolean) =>
            root.render(createElement(Badge, { busy, onClick: () => void onBadgeClick(el) }));
          render(false);
          return { root, render };
        },
        onRemove(instance) {
          instance?.root.unmount();
        },
      });

      badgeUi.mount();
    }

    function mediaRefFor(el: HTMLImageElement | HTMLVideoElement): MediaRef {
      return {
        kind: el instanceof HTMLVideoElement ? "video" : "image",
        src: el instanceof HTMLVideoElement ? el.currentSrc || el.src : el.currentSrc || el.src,
        pageUrl: location.href,
        pageTitle: document.title,
        currentTime: el instanceof HTMLVideoElement ? el.currentTime : undefined,
      };
    }

    async function onBadgeClick(el: HTMLImageElement | HTMLVideoElement) {
      if (busyRequestId) return; // one in-flight request at a time is plenty
      const requestId = newRequestId();
      busyRequestId = requestId;

      const media = mediaRefFor(el);
      modalState = { kind: "loading", stage: "checking" };
      renderModal();

      pendingImageUpload = undefined;

      try {
        let phash: string | undefined;

        if (media.kind === "image") {
          // Captured directly here: the content script has real DOM access
          // to the already-rendered element, so this costs no extra network
          // request and needs no offscreen document (that exists for video,
          // which the background cannot capture itself -- see messages.ts).
          const captured = await captureElement(el as HTMLImageElement, "image/jpeg");
          phash = captured.hash;
          pendingImageUpload = {
            blobDataUrl: await blobToDataUrl(captured.blob),
            mimeType: "image/jpeg",
            filename: "image.jpg",
          };
        }

        const checkRequest: CheckCacheRequest = {
          type: "CHECK_CACHE",
          requestId,
          media,
          phash,
        };
        const checkResponse = (await browser.runtime.sendMessage(
          checkRequest,
        )) as CheckCacheResponse;

        if (checkResponse.type === "CHECK_FAILED") {
          modalState = { kind: "error", message: checkResponse.reason };
          renderModal();
          return;
        }

        if (checkResponse.type === "CACHE_HIT") {
          modalState = { kind: "result", report: checkResponse.report };
          renderModal();
          return;
        }

        // Cache miss: this is the point an upload becomes possible, so this
        // is the point consent is required -- not before.
        modalState = { kind: "consent", media };
        renderModal();
      } catch (error) {
        modalState = { kind: "error", message: describeError(error) };
        renderModal();
      }
    }

    async function handleConsentConfirmed(media: MediaRef) {
      const requestId = busyRequestId;
      if (!requestId) return;

      modalState = { kind: "loading", stage: "uploading" };
      renderModal();

      const analyzeRequest: AnalyzeRequest = {
        type: "ANALYZE",
        requestId,
        media,
        upload: pendingImageUpload,
      };

      try {
        const response = (await browser.runtime.sendMessage(analyzeRequest)) as AnalyzeResponse;
        if (response.type === "ANALYZE_FAILED") {
          modalState = { kind: "error", message: response.reason };
        } else {
          modalState = { kind: "result", report: response.report };
        }
      } catch (error) {
        modalState = {
          kind: "error",
          message: error instanceof Error ? error.message : "Analysis failed.",
        };
      } finally {
        pendingImageUpload = undefined;
      }
      renderModal();
    }

    // --- Detection: scan existing media, then watch for more (SPA
    // navigation, lazy loading) via MutationObserver rather than only
    // page-load, per the architecture spec. ---

    function isEligible(el: Element): el is HTMLImageElement | HTMLVideoElement {
      if (!(el instanceof HTMLImageElement) && !(el instanceof HTMLVideoElement)) return false;
      const width = el instanceof HTMLVideoElement ? el.videoWidth || el.clientWidth : el.naturalWidth || el.clientWidth;
      const height = el instanceof HTMLVideoElement ? el.videoHeight || el.clientHeight : el.naturalHeight || el.clientHeight;
      return width >= settings.minMediaSizePx && height >= settings.minMediaSizePx;
    }

    function scan(root: ParentNode) {
      const candidates = root.querySelectorAll("img, video");
      for (const el of candidates) {
        if (isEligible(el)) void attachBadge(el);
      }
    }

    scan(document);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node instanceof HTMLImageElement || node instanceof HTMLVideoElement) {
            if (isEligible(node)) void attachBadge(node);
          } else if (node instanceof Element) {
            scan(node);
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    ctx.onInvalidated(() => observer.disconnect());

    // --- Right-click "Analyse with VeriFrame" from the background's context
    // menu. It only has the clicked srcUrl, not a direct element reference,
    // so the matching element is found by comparing src/currentSrc. ---
    browser.runtime.onMessage.addListener((message: unknown) => {
      if (
        typeof message !== "object" ||
        message === null ||
        (message as { type?: unknown }).type !== "CONTEXT_MENU_ANALYZE"
      ) {
        return undefined;
      }
      const { srcUrl } = message as { srcUrl: string };
      const match = [...document.querySelectorAll("img, video")].find(
        (el) => (el as HTMLImageElement | HTMLVideoElement).currentSrc === srcUrl ||
          (el as HTMLImageElement).src === srcUrl,
      );
      if (match && isEligible(match)) void onBadgeClick(match);
      return undefined;
    });
  },
});

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

const CAPTURE_ERROR_MESSAGES: Record<string, string> = {
  cors_tainted:
    "This image is served without permission for scripts to read its pixels (no CORS headers), which is a browser security restriction VeriFrame cannot work around.",
  load_failed: "The image could not be loaded for analysis.",
  unknown: "The image could not be captured.",
};

function describeError(error: unknown): string {
  if (error instanceof CaptureError) {
    return CAPTURE_ERROR_MESSAGES[error.reason] ?? "The image could not be captured.";
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}
