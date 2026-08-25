import { REPORT_FOOTER_DISCLAIMER, scoreToBand, type AnalysisReport } from "@veriframe/core";
import type { MediaRef } from "../lib/messages";

export type ModalState =
  | { kind: "consent"; media: MediaRef }
  | { kind: "loading"; stage: "checking" | "uploading" }
  | { kind: "result"; report: AnalysisReport }
  | { kind: "error"; message: string };

const PANEL_STYLE: React.CSSProperties = {
  all: "initial",
  boxSizing: "border-box",
  position: "fixed",
  top: "50%",
  left: "50%",
  transform: "translate(-50%, -50%)",
  zIndex: 2147483647,
  width: 340,
  maxWidth: "calc(100vw - 32px)",
  background: "white",
  color: "#0f172a",
  borderRadius: 12,
  padding: 20,
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  fontSize: 13,
  lineHeight: 1.5,
  boxShadow: "0 20px 50px rgba(0,0,0,0.35)",
};

const BACKDROP_STYLE: React.CSSProperties = {
  all: "initial",
  position: "fixed",
  inset: 0,
  zIndex: 2147483646,
  background: "rgba(15, 23, 42, 0.45)",
};

function Backdrop({ onClose }: { onClose: () => void }) {
  return (
    <div
      style={BACKDROP_STYLE}
      onClick={onClose}
      role="presentation"
    />
  );
}

function ConsentView({
  media,
  ttlHours,
  onConfirm,
  onCancel,
}: {
  media: MediaRef;
  ttlHours: number;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <>
      <Backdrop onClose={onCancel} />
      <div style={PANEL_STYLE}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Analyse this {media.kind}?</h2>
        <p style={{ marginTop: 10, color: "#334155" }}>
          It will be uploaded to VeriFrame&rsquo;s servers for analysis and
          automatically deleted after {ttlHours} hours. Nothing is uploaded
          without this confirmation, for this item only.
        </p>
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button type="button" onClick={onCancel} style={secondaryButtonStyle}>
            Cancel
          </button>
          <button type="button" onClick={onConfirm} style={primaryButtonStyle}>
            Analyse
          </button>
        </div>
      </div>
    </>
  );
}

function LoadingView({ stage }: { stage: "checking" | "uploading" }) {
  return (
    <>
      <Backdrop onClose={() => {}} />
      <div style={PANEL_STYLE}>
        <p style={{ margin: 0, color: "#334155" }}>
          {stage === "checking"
            ? "Checking for a previous analysis…"
            : "Uploading and analysing…"}
        </p>
      </div>
    </>
  );
}

function ResultView({
  report,
  webAppUrl,
  onClose,
}: {
  report: AnalysisReport;
  webAppUrl: string;
  onClose: () => void;
}) {
  const band = scoreToBand(report.score);
  const [lo, hi] = report.uncertainty;

  return (
    <>
      <Backdrop onClose={onClose} />
      <div style={PANEL_STYLE}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span
            style={{
              display: "inline-block",
              padding: "3px 10px",
              borderRadius: 999,
              background: bandColor(band.id),
              color: "white",
              fontWeight: 600,
              fontSize: 12,
            }}
          >
            {band.label}
          </span>
          <button type="button" onClick={onClose} style={closeButtonStyle} aria-label="Close">
            ×
          </button>
        </div>

        <p style={{ marginTop: 12, color: "#334155" }}>{band.copy}</p>

        {report.conclusion && (
          <p style={{ marginTop: 8, fontWeight: 500 }}>{report.conclusion.headline}</p>
        )}

        <p style={{ marginTop: 8, fontSize: 12, color: "#64748b" }}>
          Likely range {lo.toFixed(2)}&ndash;{hi.toFixed(2)} (point estimate{" "}
          {report.score.toFixed(2)})
        </p>

        <a
          href={`${webAppUrl}/report/${report.job_id}`}
          target="_blank"
          rel="noreferrer"
          style={{ ...primaryButtonStyle, display: "block", textAlign: "center", marginTop: 14 }}
        >
          View full report
        </a>

        <p style={{ marginTop: 12, fontSize: 11, color: "#94a3b8" }}>{REPORT_FOOTER_DISCLAIMER}</p>
      </div>
    </>
  );
}

function ErrorView({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <>
      <Backdrop onClose={onClose} />
      <div style={PANEL_STYLE}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Couldn&rsquo;t analyse this</h2>
        <p style={{ marginTop: 10, color: "#334155" }}>{message}</p>
        <button
          type="button"
          onClick={onClose}
          style={{ ...secondaryButtonStyle, marginTop: 16 }}
        >
          Close
        </button>
      </div>
    </>
  );
}

export function AnalysisModal({
  state,
  ttlHours,
  webAppUrl,
  onConfirmConsent,
  onClose,
}: {
  state: ModalState;
  ttlHours: number;
  webAppUrl: string;
  onConfirmConsent: () => void;
  onClose: () => void;
}) {
  if (state.kind === "consent") {
    return <ConsentView media={state.media} ttlHours={ttlHours} onConfirm={onConfirmConsent} onCancel={onClose} />;
  }
  if (state.kind === "loading") {
    return <LoadingView stage={state.stage} />;
  }
  if (state.kind === "result") {
    return <ResultView report={state.report} webAppUrl={webAppUrl} onClose={onClose} />;
  }
  return <ErrorView message={state.message} onClose={onClose} />;
}

const primaryButtonStyle: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  flex: 1,
  textAlign: "center",
  padding: "8px 14px",
  borderRadius: 8,
  background: "#0f172a",
  color: "white",
  fontWeight: 500,
  cursor: "pointer",
};

const secondaryButtonStyle: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  flex: 1,
  textAlign: "center",
  padding: "8px 14px",
  borderRadius: 8,
  background: "#e2e8f0",
  color: "#0f172a",
  cursor: "pointer",
};

const closeButtonStyle: React.CSSProperties = {
  all: "unset",
  boxSizing: "border-box",
  cursor: "pointer",
  fontSize: 18,
  lineHeight: 1,
  color: "#94a3b8",
  padding: 4,
};

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
