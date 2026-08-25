/**
 * User preferences, in `chrome.storage.sync` -- small, cross-device settings
 * only. Analysis history and the local hash cache are a different, much
 * larger, single-device concern and live in `chrome.storage.local` instead
 * (see history.ts), matching the architecture spec's split between the two
 * storage areas.
 */

export interface Settings {
  /** Hostnames the user has disabled VeriFrame on. A denylist, not an
   * allowlist: the badge is opt-out per site, not opt-in, since showing a
   * passive badge is not itself an upload or a privacy action. */
  disabledHostnames: string[];
  /** Smallest dimension (px) an <img>/<video> must have before a badge is
   * shown. Filters out icons, avatars, and decorative images. */
  minMediaSizePx: number;
  inferenceServiceUrl: string;
}

export const DEFAULT_SETTINGS: Settings = {
  disabledHostnames: [],
  minMediaSizePx: 200,
  inferenceServiceUrl: "http://localhost:8000",
};

export async function getSettings(): Promise<Settings> {
  // storage.sync's typings want a plain index-signature object; Settings is
  // exactly that shape at runtime (every field is JSON-serialisable), just
  // without a formal index signature TypeScript can see structurally here.
  const stored = await browser.storage.sync.get(
    DEFAULT_SETTINGS as unknown as Record<string, unknown>,
  );
  return { ...DEFAULT_SETTINGS, ...stored } as Settings;
}

export async function updateSettings(patch: Partial<Settings>): Promise<Settings> {
  const current = await getSettings();
  const next = { ...current, ...patch };
  await browser.storage.sync.set(next as unknown as Record<string, unknown>);
  return next;
}

export async function isEnabledForHostname(hostname: string): Promise<boolean> {
  const settings = await getSettings();
  return !settings.disabledHostnames.includes(hostname);
}

export async function setEnabledForHostname(
  hostname: string,
  enabled: boolean,
): Promise<Settings> {
  const settings = await getSettings();
  const disabled = new Set(settings.disabledHostnames);
  if (enabled) {
    disabled.delete(hostname);
  } else {
    disabled.add(hostname);
  }
  return updateSettings({ disabledHostnames: [...disabled] });
}
