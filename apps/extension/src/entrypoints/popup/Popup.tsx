import { scoreToBand } from "@veriframe/core";
import { useEffect, useState } from "react";
import { clearHistory, getHistory, type HistoryEntry } from "../../lib/history";
import {
  getSettings,
  setEnabledForHostname,
  type Settings,
} from "../../lib/settings";

function bandColor(id: string): string {
  const colors: Record<string, string> = {
    low: "#3d8015",
    weak: "#0da365",
    mixed: "#048aca",
    strong: "#1665ea",
    very_strong: "#1c1cb9",
  };
  return colors[id] ?? "#64748b";
}

async function currentTabHostname(): Promise<string | null> {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return null;
  try {
    return new URL(tab.url).hostname;
  } catch {
    return null;
  }
}

export function Popup() {
  const [history, setHistory] = useState<HistoryEntry[] | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [hostname, setHostname] = useState<string | null>(null);

  useEffect(() => {
    void getHistory().then(setHistory);
    void getSettings().then(setSettings);
    void currentTabHostname().then(setHostname);
  }, []);

  const siteEnabled = hostname && settings ? !settings.disabledHostnames.includes(hostname) : true;

  async function toggleSite() {
    if (!hostname) return;
    const next = await setEnabledForHostname(hostname, !siteEnabled);
    setSettings(next);
  }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h1 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>VeriFrame</h1>
      </div>

      {hostname && (
        <label
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginTop: 12,
            padding: "8px 10px",
            borderRadius: 8,
            background: "#f1f5f9",
            fontSize: 12,
          }}
        >
          <span>
            Active on <strong>{hostname}</strong>
          </span>
          <input
            type="checkbox"
            checked={siteEnabled ?? true}
            onChange={() => void toggleSite()}
          />
        </label>
      )}

      <h2
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: 0.4,
          color: "#64748b",
          marginTop: 18,
          marginBottom: 8,
        }}
      >
        Recent analyses
      </h2>

      {history === null && <p style={{ fontSize: 12, color: "#94a3b8" }}>Loading…</p>}

      {history?.length === 0 && (
        <p style={{ fontSize: 12, color: "#94a3b8" }}>
          Nothing analysed yet. Hover an image or video on a page and click the badge that
          appears.
        </p>
      )}

      <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 280, overflowY: "auto" }}>
        {history?.map((entry) => {
          const band = scoreToBand(entry.score);
          return (
            <li
              key={entry.requestId}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 0",
                borderBottom: "1px solid #f1f5f9",
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  flexShrink: 0,
                  background: bandColor(entry.band),
                }}
              />
              <div style={{ minWidth: 0, flex: 1 }}>
                <p
                  style={{
                    margin: 0,
                    fontSize: 12,
                    fontWeight: 500,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {band.label}
                </p>
                <p
                  style={{
                    margin: 0,
                    fontSize: 11,
                    color: "#94a3b8",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {entry.pageTitle || entry.pageUrl}
                </p>
              </div>
              <span style={{ fontSize: 11, color: "#94a3b8", flexShrink: 0 }}>
                {entry.score.toFixed(2)}
              </span>
            </li>
          );
        })}
      </ul>

      {history && history.length > 0 && (
        <button
          type="button"
          onClick={() => void clearHistory().then(() => setHistory([]))}
          style={{
            all: "unset",
            boxSizing: "border-box",
            display: "block",
            width: "100%",
            textAlign: "center",
            marginTop: 12,
            padding: "6px 0",
            fontSize: 11,
            color: "#94a3b8",
            cursor: "pointer",
          }}
        >
          Clear history
        </button>
      )}

      <p style={{ fontSize: 10, color: "#cbd5e1", marginTop: 16, marginBottom: 0 }}>
        History is stored only on this device. Media itself is never kept here.
      </p>
    </div>
  );
}
