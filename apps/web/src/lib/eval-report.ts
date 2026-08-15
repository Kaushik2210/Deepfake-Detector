import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

/**
 * Loads the most recent evaluation report produced by the harness.
 *
 * Principle 5: no accuracy figure may be hardcoded. Everything the accuracy page
 * shows is read from here, so if the harness has never been run the page says so
 * rather than falling back to a placeholder number.
 */

export interface ThresholdMetric {
  target_fpr: number;
  tpr: number | null;
  threshold: number | null;
  measurable: boolean;
  note: string;
}

export interface StreamMetrics {
  n: number;
  n_positive: number;
  n_negative: number;
  auc: number;
  auc_ci95: [number, number];
  eer: number;
  eer_threshold: number;
  thresholds: ThresholdMetric[];
  ece: number;
  mean_score_positive: number;
  mean_score_negative: number;
}

export interface EvalReport {
  provenance: {
    generated_at: string;
    calibration_dataset: string;
    reporting_dataset: string;
    samples_per_dataset: number;
    seed: number;
  };
  datasets: Record<
    string,
    { hf_id: string; licence: string; commercial_use: boolean; description: string }
  >;
  coverage: Record<string, { scored: number; no_face_detected: number; seconds: number }>;
  in_dataset_metrics: Record<string, StreamMetrics>;
  cross_dataset_metrics: Record<string, { raw: StreamMetrics; calibrated: StreamMetrics }>;
  temperature: Record<string, number>;
  fusion_weights: { stream: string; auc: number; weight: number; rationale: string }[];
  robustness_auc_by_jpeg_quality: Record<string, Record<string, number>>;
  provenance_stream?: {
    measurable: boolean;
    fired_on_calibration_split: number;
    fired_on_reporting_split: number;
    note: string;
  };
}

function reportsDir(): string {
  // apps/web/src/lib -> repo root -> services/inference/eval/reports
  return path.resolve(process.cwd(), "..", "..", "services", "inference", "eval", "reports");
}

export async function latestEvalReport(): Promise<EvalReport | null> {
  try {
    const dir = reportsDir();
    const files = (await readdir(dir)).filter((f) => f.endsWith(".json")).sort();
    const newest = files.at(-1);
    if (!newest) return null;

    return JSON.parse(await readFile(path.join(dir, newest), "utf8")) as EvalReport;
  } catch {
    // Missing directory or unreadable file both mean "no evaluation available",
    // which the page renders explicitly.
    return null;
  }
}
