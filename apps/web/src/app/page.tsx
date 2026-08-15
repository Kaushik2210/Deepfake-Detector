import { UploadForm } from "@/components/UploadForm";

export default function HomePage() {
  const ttlHours = Number(process.env.MEDIA_TTL_HOURS ?? 24);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Analyse an image</h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          VeriFrame estimates how likely an image is to have been manipulated and
          shows you the evidence behind that estimate. It does not return a
          verdict, and results are a signal for human review rather than proof.
        </p>
      </div>

      <UploadForm ttlHours={ttlHours} />

      <section className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-700">
        <h2 className="mb-2 font-medium text-slate-900">What this tool cannot do</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            It cannot tell you who created an image or who appears in it. There is no
            face recognition or identity matching.
          </li>
          <li>
            It cannot prove an image is genuine or fabricated. Detectors degrade
            sharply on media unlike what they were validated on, and the report says
            so when that applies.
          </li>
          <li>
            No accuracy figure is published yet. Cross-dataset evaluation is still
            outstanding, so any number quoted now would not be defensible.
          </li>
        </ul>
      </section>
    </div>
  );
}
