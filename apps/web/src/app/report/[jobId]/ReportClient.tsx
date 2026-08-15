"use client";

import type { AnalysisReport } from "@veriframe/core";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ReportView } from "@/components/ReportView";

type JobState =
  | { status: "queued" }
  | { status: "processing" }
  | { status: "complete"; report: AnalysisReport; media_deleted_at: string | null }
  | { status: "failed"; error: string };

export function ReportClient({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);

  const { data, error } = useQuery<JobState>({
    queryKey: ["job", jobId],
    queryFn: async () => {
      const response = await fetch(`/api/analyze/${jobId}`);
      if (!response.ok) throw new Error("could not load this report");
      return response.json();
    },
    // Poll while the job is in flight, then stop.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "processing" ? 1500 : false;
    },
  });

  async function remove() {
    if (!confirm("Delete this analysis and its media? This cannot be undone.")) return;
    setDeleting(true);
    await fetch(`/api/analyze/${jobId}`, { method: "DELETE" });
    router.push("/");
  }

  if (error) {
    return <p className="text-sm text-red-800">{(error as Error).message}</p>;
  }

  if (!data || data.status === "queued" || data.status === "processing") {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-center">
        <p className="text-slate-700">
          {data?.status === "processing" ? "Analysing…" : "Queued…"}
        </p>
        <p className="mt-1 text-sm text-slate-500">This usually takes a few seconds.</p>
      </div>
    );
  }

  if (data.status === "failed") {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4">
        <p className="font-medium text-red-900">Analysis failed</p>
        <p className="mt-1 text-sm text-red-800">{data.error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <ReportView report={data.report} />

      <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-4">
        <p className="text-sm text-slate-600">
          {data.media_deleted_at
            ? `Media was deleted on ${new Date(data.media_deleted_at).toLocaleString()}.`
            : "Media is deleted automatically when the retention period ends."}
        </p>
        <button
          onClick={remove}
          disabled={deleting}
          className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-800 hover:bg-red-50 disabled:opacity-50"
        >
          {deleting ? "Deleting…" : "Delete now"}
        </button>
      </div>
    </div>
  );
}
