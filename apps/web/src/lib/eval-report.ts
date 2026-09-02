import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

/**
 * Loads the most recent evaluation reports produced by the harness.
 *
 * Principle 5: no accuracy figure may be hardcoded. Everything the accuracy page
 * shows is read from here, so if a harness has never been run the page says so
 * rather than falling back to a placeholder number.
 *
 * Image and audio reports live in the same directory (services/inference/eval/reports/)
 * with different shapes -- audio's carries a second stream and a
 * fused-vs-alone comparison the image report has no equivalent of. Picking
 * "the newest JSON file" without distinguishing them would silently render one
 * kind's data as if it were the other's the moment both exist, which is
 * exactly what happened here until this filtered on the audio- prefix.
 */

export interface ThresholdMetric {
  target_fpr: number;
  tpr: number | null;
  threshold: number | null;
  measurable: boolean;
  note: string;
}

export interface RocPoint {
  fpr: number;
  tpr: number;
}

export interface CalibrationBin {
  lower: number;
  upper: number;
  count: number;
  mean_confidence: number;
  observed_frequency: number;
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
  calibration_bins: CalibrationBin[];
  roc_points: RocPoint[];
  mean_score_positive: number;
  mean_score_negative: number;
}

export interface WeightStability {
  median: number | null;
  p10: number | null;
  p90: number | null;
  n_replicates: number;
}

export interface StreamComparison {
  stream_a: string;
  stream_b: string;
  n: number;
  auc_a: number;
  auc_b: number;
  auc_diff: number;
  auc_diff_ci95: [number, number];
  p_value_two_sided: number;
  significant_at_0_05: boolean;
  note: string;
}

interface DatasetMeta {
  hf_id: string;
  licence: string;
  commercial_use: boolean;
  description: string;
}

interface Provenance {
  generated_at: string;
  calibration_dataset: string;
  reporting_dataset: string;
  samples_per_dataset: number;
  validation_samples?: number;
  final_reporting_samples?: number;
  seed: number;
}

export interface EvalReport {
  provenance: Provenance;
  datasets: Record<string, DatasetMeta>;
  coverage: Record<
    string,
    {
      scored: number;
      no_face_detected: number;
      seconds: number;
      validation_scored?: number;
      final_reporting_scored?: number;
    }
  >;
  in_dataset_metrics: Record<string, StreamMetrics>;
  weight_validation_metrics?: Record<string, StreamMetrics>;
  weight_stability?: Record<string, WeightStability> | null;
  cross_dataset_metrics: Record<string, { raw: StreamMetrics; calibrated: StreamMetrics }>;
  stream_comparison?: StreamComparison | null;
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

export interface AudioEvalReport {
  provenance: Provenance;
  datasets: Record<string, DatasetMeta>;
  coverage: Record<
    string,
    {
      scored: number;
      seconds: number;
      validation_scored?: number;
      final_reporting_scored?: number;
    }
  >;
  in_dataset_metrics: Record<string, StreamMetrics>;
  weight_validation_metrics?: Record<string, StreamMetrics>;
  weight_stability?: Record<string, WeightStability> | null;
  cross_dataset_metrics: Record<string, { raw: StreamMetrics; calibrated: StreamMetrics }>;
  stream_comparison?: StreamComparison | null;
  fused_cross_dataset_metrics: StreamMetrics | null;
  temperature: Record<string, number>;
  fusion_weights: { stream: string; auc: number; weight: number; rationale: string }[];
  robustness_auc_by_snr_db: Record<string, Record<string, number>>;
}

function reportsDir(): string {
  // apps/web/src/lib -> repo root -> services/inference/eval/reports
  return path.resolve(process.cwd(), "..", "..", "services", "inference", "eval", "reports");
}

async function listReportFiles(): Promise<string[]> {
  try {
    return (await readdir(reportsDir())).filter((f) => f.endsWith(".json")).sort();
  } catch {
    return [];
  }
}

async function readReport<T>(filename: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path.join(reportsDir(), filename), "utf8")) as T;
  } catch {
    return null;
  }
}

export async function latestEvalReport(): Promise<EvalReport | null> {
  const files = await listReportFiles();
  const newest = files.filter((f) => !f.startsWith("audio-")).at(-1);
  if (!newest) return null;
  return readReport<EvalReport>(newest);
}

export async function latestAudioEvalReport(): Promise<AudioEvalReport | null> {
  const files = await listReportFiles();
  const newest = files.filter((f) => f.startsWith("audio-")).at(-1);
  if (!newest) return null;
  return readReport<AudioEvalReport>(newest);
}
