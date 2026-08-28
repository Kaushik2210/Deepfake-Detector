"use client";

import type { AnalysisReport } from "@veriframe/core";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";

import { ReportView } from "@/components/ReportView";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type JobState =
  | { status: "queued" }
  | { status: "processing" }
  | { status: "complete"; report: AnalysisReport; media_deleted_at: string | null }
  | { status: "failed"; error: string };

export function ReportClient({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

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
    setConfirmOpen(false);
    setDeleting(true);
    await fetch(`/api/analyze/${jobId}`, { method: "DELETE" });
    router.push("/");
  }

  if (error) {
    return (
      <Card className="border-destructive/30">
        <CardContent className="text-sm text-destructive">
          {(error as Error).message}
        </CardContent>
      </Card>
    );
  }

  if (!data || data.status === "queued" || data.status === "processing") {
    return (
      <div
        role="status"
        aria-live="polite"
        className="space-y-4 rounded-lg border bg-card p-8 text-center"
      >
        <Loader2 className="mx-auto size-6 animate-spin text-muted-foreground" aria-hidden="true" />
        <p className="font-medium">
          {data?.status === "processing" ? "Analysing…" : "Queued…"}
        </p>
        <p className="text-sm text-muted-foreground">This usually takes a few seconds.</p>
        <div className="mx-auto max-w-sm space-y-2 pt-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
    );
  }

  if (data.status === "failed") {
    return (
      <Card className="border-destructive/30">
        <CardContent>
          <p className="font-medium text-destructive">Analysis failed</p>
          <p className="mt-1 text-sm text-muted-foreground">{data.error}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <ReportView report={data.report} />

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {data.media_deleted_at
              ? `Media was deleted on ${new Date(data.media_deleted_at).toLocaleString()}.`
              : "Media is deleted automatically when the retention period ends."}
          </p>
          <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
            <Button
              variant="destructive"
              size="sm"
              disabled={deleting}
              onClick={() => setConfirmOpen(true)}
            >
              <Trash2 />
              {deleting ? "Deleting…" : "Delete now"}
            </Button>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete this analysis?</DialogTitle>
                <DialogDescription>
                  This permanently removes the media and the report. This cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                  Cancel
                </Button>
                <Button variant="destructive" onClick={remove}>
                  Delete
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>
    </div>
  );
}
