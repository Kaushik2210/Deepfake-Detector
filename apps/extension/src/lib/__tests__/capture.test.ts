import { describe, expect, it } from "vitest";
import { captureElement, CaptureError } from "../capture";

/**
 * jsdom's `getContext('2d')` returns null without the native `canvas`
 * package installed, which this project deliberately doesn't add just for
 * tests -- so the real pixel-capture pipeline (drawImage, getImageData,
 * toBlob) is exercised by manually testing the built extension, the same
 * scope decision already made for phash.ts's canvas adapter. What jsdom can
 * genuinely reproduce is the failure path when no context is available,
 * which is worth covering: a silently-swallowed capture failure would be
 * far worse than a loud one.
 */
describe("captureElement error handling", () => {
  it("CaptureError carries its reason and a readable message", () => {
    const error = new CaptureError("cors_tainted");
    expect(error.reason).toBe("cors_tainted");
    expect(error.message).toContain("cors_tainted");
    expect(error).toBeInstanceOf(Error);
  });

  it("throws load_failed for an element with no natural size", async () => {
    const img = document.createElement("img");
    // Never given a src, so naturalWidth/naturalHeight are 0 -- the same
    // shape as a broken/未-loaded image, which must fail loudly rather than
    // hang or produce a garbage all-zero hash.
    await expect(captureElement(img)).rejects.toMatchObject({ reason: "load_failed" });
  });

  it("fails rather than silently succeeding when canvas 2D context is unavailable", async () => {
    // jsdom's canvas has no real 2D context without the native `canvas`
    // package (not a project dependency), so any element with a nonzero
    // reported size still fails here -- correctly, since there is genuinely
    // no way to capture pixels in this environment.
    const img = document.createElement("img");
    Object.defineProperty(img, "naturalWidth", { value: 100 });
    Object.defineProperty(img, "naturalHeight", { value: 100 });

    await expect(captureElement(img)).rejects.toBeInstanceOf(CaptureError);
  });
});
