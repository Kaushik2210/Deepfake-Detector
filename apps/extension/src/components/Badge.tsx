import { useState } from "react";

/**
 * The passive, per-media badge. Shows nothing but a small icon until
 * hovered, and does *nothing* -- no capture, no hash, no request of any
 * kind -- until actually clicked. Privacy principle 4: no background
 * scanning or uploading; every analysis is an explicit per-item action, and
 * that starts with this component doing nothing on its own.
 */
export function Badge({ onClick, busy }: { onClick: () => void; busy: boolean }) {
  const [hovered, setHovered] = useState(false);

  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      disabled={busy}
      title="Analyse with VeriFrame"
      style={{
        all: "unset",
        boxSizing: "border-box",
        display: "flex",
        alignItems: "center",
        gap: 6,
        position: "absolute",
        top: 6,
        right: 6,
        zIndex: 2147483646,
        padding: hovered ? "4px 10px 4px 6px" : 4,
        borderRadius: 999,
        background: "rgba(15, 23, 42, 0.88)",
        color: "white",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        fontSize: 12,
        fontWeight: 500,
        cursor: busy ? "wait" : "pointer",
        boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
        opacity: busy ? 0.75 : 1,
        transition: "padding 120ms ease",
      }}
    >
      <span
        style={{
          width: 16,
          height: 16,
          borderRadius: "50%",
          flexShrink: 0,
          background: busy
            ? "conic-gradient(white 0deg 270deg, transparent 270deg 360deg)"
            : "white",
          animation: busy ? "veriframe-spin 900ms linear infinite" : undefined,
        }}
      />
      {hovered && !busy && <span>Analyse with VeriFrame</span>}
      {busy && <span>Analysing…</span>}
      <style>{`@keyframes veriframe-spin { to { transform: rotate(360deg); } }`}</style>
    </button>
  );
}
