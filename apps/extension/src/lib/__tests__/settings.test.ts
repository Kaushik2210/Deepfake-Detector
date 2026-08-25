import { fakeBrowser } from "wxt/testing/fake-browser";
import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_SETTINGS,
  getSettings,
  isEnabledForHostname,
  setEnabledForHostname,
  updateSettings,
} from "../settings";

describe("settings", () => {
  beforeEach(() => {
    fakeBrowser.reset();
  });

  it("returns defaults when nothing has been stored", async () => {
    expect(await getSettings()).toEqual(DEFAULT_SETTINGS);
  });

  it("persists updates across calls", async () => {
    await updateSettings({ minMediaSizePx: 400 });
    expect((await getSettings()).minMediaSizePx).toBe(400);
  });

  it("updateSettings merges rather than replacing the whole object", async () => {
    await updateSettings({ minMediaSizePx: 400 });
    await updateSettings({ inferenceServiceUrl: "https://example.com" });

    const settings = await getSettings();
    expect(settings.minMediaSizePx).toBe(400);
    expect(settings.inferenceServiceUrl).toBe("https://example.com");
  });

  it("a fresh hostname is enabled by default", async () => {
    expect(await isEnabledForHostname("example.com")).toBe(true);
  });

  it("disabling a hostname is reflected immediately", async () => {
    await setEnabledForHostname("example.com", false);
    expect(await isEnabledForHostname("example.com")).toBe(false);
  });

  it("re-enabling removes the hostname from the denylist rather than leaving a stale entry", async () => {
    await setEnabledForHostname("example.com", false);
    await setEnabledForHostname("example.com", true);

    const settings = await getSettings();
    expect(settings.disabledHostnames).not.toContain("example.com");
    expect(await isEnabledForHostname("example.com")).toBe(true);
  });

  it("disabling one hostname does not affect another", async () => {
    await setEnabledForHostname("a.com", false);
    expect(await isEnabledForHostname("b.com")).toBe(true);
  });

  it("disabling the same hostname twice does not duplicate it in the list", async () => {
    await setEnabledForHostname("example.com", false);
    await setEnabledForHostname("example.com", false);

    const settings = await getSettings();
    expect(settings.disabledHostnames.filter((h) => h === "example.com")).toHaveLength(1);
  });
});
