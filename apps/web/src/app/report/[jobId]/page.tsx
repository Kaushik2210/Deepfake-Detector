import { ReportClient } from "./ReportClient";

export default async function ReportPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Analysis report</h1>
      <ReportClient jobId={jobId} />
    </div>
  );
}
